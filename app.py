from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from brewmetheus.alerts import HTTP_STATUS, RUNBOOKS, evaluate_incidents, primary_incident
from brewmetheus.beverages import BEVERAGES, caffeine_for
from brewmetheus.models import Incident, IntakeEvent, Severity, SLOReport, UserProfile
from brewmetheus.notify import send_ntfy
from brewmetheus.params import derive_params
from brewmetheus.pk_model import auc, concentration_band, concentration_curve
from brewmetheus.postmortem import render_postmortem
from brewmetheus.predict import crash_time_h, refill_window_h, sleep_forecast
from brewmetheus.render import render_badge, render_card
from brewmetheus.slo import day_slo, golden_signals
from brewmetheus.store import FileStore
from brewmetheus.timeutil import day_window_offsets, resolve_sleep_offset, to_offsets

STANDARD_DOSE_MG = 95.0  # a drip coffee, used for the refill suggestion
MODEL_WINDOW_H = 48.0  # how far back to pull intakes for modeling
FORECAST_HORIZON_H = 24.0
REFRESH_SECONDS = 30  # how often the live panel re-runs on its own
HISTORY_DAYS = 14


@st.cache_resource
def get_store() -> FileStore:
    return FileStore()


def _offset_to_clock(offset_h: float, now: datetime, tz: ZoneInfo) -> str:
    return (now + timedelta(hours=offset_h)).astimezone(tz).strftime("%H:%M")


def _render_status(incident: Incident) -> None:
    status = HTTP_STATUS.get(incident.code)
    prefix = f"`{status}` " if status else ""
    text = f"{prefix}**{incident.title}** — {incident.detail}"
    if incident.severity is Severity.OK:
        st.success(text)
    elif incident.severity is Severity.P2:
        st.warning(text)
    else:  # P1 or OVERLOAD
        st.error(text)
    runbook = RUNBOOKS.get(incident.code)
    if runbook:
        with st.expander("Runbook"):
            for i, step in enumerate(runbook, start=1):
                st.write(f"{i}. {step}")


def _resolve_tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        st.error(f"Unknown timezone {name!r}; falling back to UTC.")
        return ZoneInfo("UTC")


def _sidebar_profile(store: FileStore) -> UserProfile:
    st.sidebar.header("Profile")
    current = store.load_profile()
    weight_kg = st.sidebar.number_input("Weight (kg)", 30.0, 250.0, current.weight_kg, step=1.0)
    st.sidebar.subheader("Hepatic clearance (CYP1A2)")
    st.sidebar.caption(
        "The eagle's appetite. Smoking induces the enzyme (caffeine clears faster); "
        "oral contraceptives and pregnancy inhibit it (slower)."
    )
    profile = UserProfile(
        weight_kg=weight_kg,
        smoker=st.sidebar.checkbox("Smoker", current.smoker),
        oral_contraceptives=st.sidebar.checkbox("Oral contraceptives", current.oral_contraceptives),
        pregnant=st.sidebar.checkbox("Pregnant", current.pregnant),
        base_half_life_h=st.sidebar.number_input(
            "Baseline half-life (h)", 1.0, 12.0, current.base_half_life_h, step=0.5
        ),
        ka_per_h=current.ka_per_h,
        bioavailability=current.bioavailability,
        vd_per_kg=current.vd_per_kg,
        awake_threshold_mg_l=st.sidebar.number_input(
            "Awake threshold (mg/L)", 0.1, 10.0, current.awake_threshold_mg_l, step=0.1
        ),
        sleep_insomnia_threshold_mg_l=st.sidebar.number_input(
            "Insomnia threshold (mg/L)", 0.1, 10.0, current.sleep_insomnia_threshold_mg_l, step=0.1
        ),
        safe_ceiling_mg_l=current.safe_ceiling_mg_l,
        daily_cap_mg=st.sidebar.number_input(
            "Daily cap (mg)", 100.0, 1000.0, current.daily_cap_mg, step=10.0
        ),
        clarity_sla_target=st.sidebar.slider(
            "Clarity SLA target", 0.5, 1.0, current.clarity_sla_target, step=0.01
        ),
        wake_time_local=st.sidebar.time_input("Wake time", current.wake_time_local),
        sleep_time_local=st.sidebar.time_input("Bedtime", current.sleep_time_local),
        timezone=st.sidebar.text_input("Timezone (IANA)", current.timezone),
        ntfy_topic=st.sidebar.text_input("ntfy topic (mobile push)", current.ntfy_topic or "")
        or None,
    )
    if st.sidebar.button("Save profile"):
        store.save_profile(profile)
        st.sidebar.success("Saved.")
    return profile


def _intake_form(store: FileStore) -> None:
    st.subheader("Log an intake")
    with st.form("intake"):
        names = {b.name: key for key, b in BEVERAGES.items()}
        choice = st.selectbox("Beverage", list(names.keys()))
        key = names[choice]
        note = BEVERAGES[key].note
        if note:
            st.caption(note)
        if key in {"black_tea", "green_tea"}:
            st.caption(
                "HTTP 418 — I'm a teapot (RFC 2324). This is a coffee service; logged anyway."
            )
        elif key == "decaf":
            st.caption(
                "No-op deploy — decaf ships no functional change to production. "
                "(Death before decaf.)"
            )
        serving = st.number_input(
            "Serving (ml)", 0.0, 2000.0, BEVERAGES[key].default_serving_ml, step=10.0
        )
        custom = st.number_input("Or custom caffeine (mg); 0 = use table", 0.0, 1000.0, 0.0)
        submitted = st.form_submit_button("Add")
    if submitted:
        mg = custom if custom > 0 else caffeine_for(key, serving_ml=serving)
        store.add_intake(
            IntakeEvent(
                timestamp_utc=datetime.now(timezone.utc),
                caffeine_mg=mg,
                beverage_key=None if custom > 0 else key,
                serving_ml=None if custom > 0 else serving,
            )
        )
        st.success(f"Logged {mg:.0f} mg.")
        st.rerun()


@st.fragment(run_every=f"{REFRESH_SECONDS}s")
def _live_dashboard(store: FileStore, profile: UserProfile, tz: ZoneInfo) -> None:
    """Time-sensitive panel; re-runs itself every REFRESH_SECONDS so "now" stays live."""
    now = datetime.now(timezone.utc)
    events = store.get_recent_intakes(within_h=MODEL_WINDOW_H, now=now)
    intakes = to_offsets(events, reference=now)
    params = derive_params(profile)
    sleep_h = resolve_sleep_offset(profile.sleep_time_local, profile.timezone, now)
    daily_total = store.daily_total_mg(now.astimezone(tz).date(), profile)

    incidents = evaluate_incidents(
        intakes, params, profile, sleep_h, current_daily_total_mg=daily_total
    )
    st.subheader("Service status")
    clock = now.astimezone(tz).strftime("%H:%M:%S")
    st.caption(f"Live · auto-refreshes every {REFRESH_SECONDS}s · updated {clock}")
    _render_status(primary_incident(incidents))

    c_now = float(concentration_curve(np.asarray([0.0]), intakes, params)[0])
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Now (mg/L)", f"{c_now:.2f}")
    col1.caption(f"= {c_now / 194.19 * 1000:.1f} µmol/L · caffeine Mr 194.19. We also accept SI.")
    col2.metric("Today (mg)", f"{daily_total:.0f} / {profile.daily_cap_mg:.0f}")
    col3.metric("Half-life (h)", f"{params.effective_half_life_h:.1f}")
    col4.metric(
        "Exposure (AUC)",
        f"{auc(daily_total, params):.0f} mg·h/L",
        help="Committed total exposure of today's intake (area under the curve, t→∞).",
    )
    st.caption(
        f"Hepatic clearance ≈ {params.ke_per_h * params.V_l:.1f} L/h via CYP1A2 — the liver "
        "enzyme Prometheus is famous for regrowing. The eagle's daily allotment."
    )

    grid = np.linspace(0.0, FORECAST_HORIZON_H, int(FORECAST_HORIZON_H * 12) + 1)
    curve = concentration_curve(grid, intakes, params)
    band_low, band_high = concentration_band(grid, intakes, params)
    times = [(now + timedelta(hours=float(h))).astimezone(tz).replace(tzinfo=None) for h in grid]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=times,
            y=band_low,
            mode="lines",
            line={"width": 0},
            hoverinfo="skip",
            showlegend=False,
            name="fast metabolizer",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=times,
            y=band_high,
            mode="lines",
            line={"width": 0},
            fill="tonexty",
            fillcolor="rgba(130,130,130,0.18)",
            hoverinfo="skip",
            name="metabolizer band",
        )
    )
    fig.add_trace(go.Scatter(x=times, y=curve, mode="lines", name="caffeine (mg/L)"))
    fig.add_trace(
        go.Scatter(
            x=times,
            y=[profile.awake_threshold_mg_l] * len(times),
            mode="lines",
            name="awake",
            line={"dash": "dot"},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=times,
            y=[profile.sleep_insomnia_threshold_mg_l] * len(times),
            mode="lines",
            name="insomnia",
            line={"dash": "dot"},
        )
    )
    fig.update_layout(
        hovermode="x unified",
        yaxis_title="mg/L",
        margin={"l": 0, "r": 0, "t": 10, "b": 0},
        height=320,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
    )
    fig.update_xaxes(tickformat="%m-%d %H:%M", hoverformat="%m-%d %H:%M")
    st.plotly_chart(fig)
    st.caption(
        "Shaded: fast–slow metabolizer band (CYP1A2 t½ 0.6–1.7×). Your true clearance "
        "is unmeasured; we assume a spherical liver."
    )

    st.subheader("Predictions")
    st.caption("Prometheus — literally 'forethought'. The part he was actually named for.")
    crash = crash_time_h(intakes, params, profile.awake_threshold_mg_l)
    if crash is None:
        st.write("**Crash:** not within the next 24 h.")
    else:
        st.write(f"**Crash:** ~{_offset_to_clock(crash, now, tz)} (in {crash:.1f} h).")

    refill = refill_window_h(intakes, params, profile, sleep_h, STANDARD_DOSE_MG, daily_total)
    if refill.feasible and refill.at_h is not None:
        st.write(
            f"**Refill window:** latest safe top-up ~{_offset_to_clock(refill.at_h, now, tz)} "
            f"(a {STANDARD_DOSE_MG:.0f} mg cup)."
        )
    else:
        blocked_reasons = {
            "DAILY_CAP": "you've drawn your daily ration of fire",
            "SLEEP": "another cup now would burn past bedtime",
            "NO_CRASH_COMING": "no crash on the horizon — nothing to refill for",
        }
        why = blocked_reasons.get(refill.blocked_by or "", refill.blocked_by or "unavailable")
        st.write(f"**Refill:** not advised — {why}.")

    forecast = sleep_forecast(intakes, params, profile, sleep_h)
    verdict = "insomnia risk" if forecast.insomnia_risk else "should be fine"
    st.write(
        f"**Bedtime residual:** {forecast.residual_mg_l:.2f} mg/L at "
        f"{_offset_to_clock(sleep_h, now, tz)} — {verdict}."
    )


def _compute_today_slo(store: FileStore, profile: UserProfile, now: datetime) -> SLOReport | None:
    if profile.sleep_time_local <= profile.wake_time_local:
        return None
    wake_h, sleep_h = day_window_offsets(
        profile.wake_time_local, profile.sleep_time_local, profile.timezone, now
    )
    intakes = to_offsets(store.get_recent_intakes(within_h=MODEL_WINDOW_H, now=now), reference=now)
    params = derive_params(profile)
    return day_slo(
        intakes,
        params,
        wake_h,
        sleep_h,
        profile.awake_threshold_mg_l,
        profile.clarity_sla_target,
        now_h=0.0,  # offsets are relative to now, so "now" is the origin
    )


def _slo_section(
    report: SLOReport | None, profile: UserProfile, now: datetime, tz: ZoneInfo
) -> None:
    st.subheader("Reliability (SLO)")
    if report is None:
        st.info("Set bedtime later than wake time to compute the SLO.")
        return

    sla_pct = report.uptime_ratio * 100
    target_pct = report.sla_target * 100
    if report.sla_met:
        st.success(f"SLA met — {sla_pct:.1f}% ≥ {target_pct:.0f}% target")
    else:
        st.error(f"SLA breached — {sla_pct:.1f}% < {target_pct:.0f}% target")

    col1, col2, col3 = st.columns(3)
    col1.metric("Clarity SLA (today)", f"{sla_pct:.1f}%", delta=f"{sla_pct - target_pct:+.1f} pts")
    col2.metric("P1 incidents", report.incident_count)
    col3.metric("Error budget left", f"{report.budget_remaining_h * 60:.0f} min")

    mttr_txt = f"{report.mttr_h * 60:.0f} min" if report.mttr_h is not None else "—"
    st.caption(
        f"MTTR {mttr_txt} · avg concentration {report.avg_mg_l:.2f} mg/L over the waking window."
    )

    if report.burn_rate is not None:
        burn = f"Error budget burn rate: {report.burn_rate:.1f}×"
        if report.budget_exhaustion_h is not None:
            burn += (
                f" — budget exhausted by ~{_offset_to_clock(report.budget_exhaustion_h, now, tz)}"
            )
        st.caption(burn + ".")

    if report.crashes:
        st.write("**Incident log (P1):**")
        for i, crash in enumerate(report.crashes, start=1):
            start = _offset_to_clock(crash.start_h, now, tz)
            end = _offset_to_clock(crash.end_h, now, tz)
            st.write(f"{i}. {start}–{end} · down {crash.duration_h * 60:.0f} min")
        st.caption(
            "Epimetheus — 'afterthought', Prometheus's brother. The SRE calls it a postmortem."
        )
        postmortem = render_postmortem(
            report,
            now.astimezone(tz).strftime("%Y-%m-%d"),
            profile.awake_threshold_mg_l,
            lambda h: _offset_to_clock(h, now, tz),
        )
        st.download_button(
            "Download postmortem (.md)",
            postmortem,
            "caffeine-postmortem.md",
            "text/markdown",
        )
    else:
        st.write("**No P1 incidents today — all systems operational.**")


def _golden_signals_section(
    store: FileStore, profile: UserProfile, report: SLOReport | None, now: datetime, tz: ZoneInfo
) -> None:
    st.subheader("Golden signals")
    if report is None:
        st.info("Set bedtime later than wake time to compute the golden signals.")
        return
    params = derive_params(profile)
    daily_total = store.daily_total_mg(now.astimezone(tz).date(), profile)
    sig = golden_signals(params, daily_total, profile.daily_cap_mg, report.downtime_so_far_h or 0.0)
    st.caption("The four signals Google's SRE book says to watch above all else.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Latency", f"{sig.latency_h * 60:.0f} min", help="Tmax — a dose's time to peak effect."
    )
    c2.metric("Traffic", f"{sig.traffic_mg:.0f} mg", help="Caffeine ingested today.")
    c3.metric(
        "Errors", f"{sig.errors_h * 60:.0f} min", help="Minutes below the awake threshold today."
    )
    c4.metric(
        "Saturation", f"{sig.saturation_ratio * 100:.0f}%", help="Share of your daily cap used."
    )


def _share_section(report: SLOReport | None, now: datetime, tz: ZoneInfo) -> None:
    st.subheader("Shareable status")
    if report is None:
        return
    subtitle = now.astimezone(tz).strftime("%Y-%m-%d")
    badge = render_badge(report)
    card = render_card(report, subtitle=subtitle)
    st.html(badge)
    st.html(card)
    st.download_button("Download SLA badge (SVG)", badge, "caffeine-sla.svg", "image/svg+xml")
    st.download_button("Download status card (SVG)", card, "caffeine-card.svg", "image/svg+xml")


def _notify_section(profile: UserProfile) -> None:
    st.subheader("Mobile push (ntfy)")
    if not profile.ntfy_topic:
        st.caption(
            "Set an ntfy topic in the sidebar, subscribe to it in the ntfy app, then test here."
        )
        return
    st.caption(
        f"Topic: `{profile.ntfy_topic}` — subscribe to it in the ntfy app to receive pushes."
    )
    if st.button("Send test push"):
        try:
            status = send_ntfy(
                profile.ntfy_topic,
                "Brewmetheus test",
                "If this reached your phone, push notifications work.",
                tags="coffee",
            )
            st.success(f"Sent (HTTP {status}).")
        except Exception as exc:  # surface any delivery error to the user
            st.error(f"Failed to send: {exc}")


def _history_section(store: FileStore, profile: UserProfile, tz: ZoneInfo) -> None:
    st.subheader("History")
    today = datetime.now(timezone.utc).astimezone(tz).date()
    totals = store.daily_totals_mg(HISTORY_DAYS, today, profile)
    frame = pd.DataFrame(
        {"caffeine (mg)": [mg for _, mg in totals]},
        index=pd.to_datetime([day for day, _ in totals]),
    )
    st.bar_chart(frame)
    week = [mg for _, mg in totals[-7:]]
    weekly_avg = sum(week) / len(week) if week else 0.0
    st.caption(f"7-day average: {weekly_avg:.0f} mg/day (daily cap {profile.daily_cap_mg:.0f} mg).")


def _recent_intakes(store: FileStore, tz: ZoneInfo) -> None:
    st.subheader("Recent intakes")
    events = store.get_recent_intakes(within_h=MODEL_WINDOW_H, now=datetime.now(timezone.utc))
    if not events:
        st.write("Nothing logged in the last 48 h.")
    for event in reversed(events):
        local = event.timestamp_utc.astimezone(tz).strftime("%m-%d %H:%M")
        label = event.beverage_key or "custom"
        cols = st.columns([4, 1])
        cols[0].write(f"{local} — {label} — {event.caffeine_mg:.0f} mg")
        if cols[1].button("Delete", key=f"del-{event.id}"):
            store.delete_intake(event.id)
            st.rerun()


def main() -> None:
    st.set_page_config(page_title="Brewmetheus", page_icon="☕")
    st.title("☕ Brewmetheus")
    st.caption("Blood-caffeine monitoring, taken far too seriously.")

    store = get_store()
    profile = _sidebar_profile(store)
    tz = _resolve_tz(profile.timezone)

    _intake_form(store)
    _live_dashboard(store, profile, tz)
    now = datetime.now(timezone.utc)
    report = _compute_today_slo(store, profile, now)
    _golden_signals_section(store, profile, report, now, tz)
    _slo_section(report, profile, now, tz)
    _share_section(report, now, tz)
    _notify_section(profile)
    _history_section(store, profile, tz)
    _recent_intakes(store, tz)
    st.divider()
    st.caption(
        "Not medical advice. Brewmetheus is not affiliated with Prometheus the systems "
        "monitor, Prometheus the Titan, or your physician. Thresholds are product knobs, "
        "not clinical values."
    )


if __name__ == "__main__":
    main()
