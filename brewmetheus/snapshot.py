"""Assemble a point-in-time Snapshot of the caffeine service.

A boundary module (it touches the store, timezones, and "now"), like notify.py. It is the
single source of truth for "current state": both the mobile-push notifier and the
Prometheus exporter read from here, so the two adapters cannot drift apart.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np

from brewmetheus import __version__
from brewmetheus.alerts import evaluate_incidents, primary_incident
from brewmetheus.models import Snapshot
from brewmetheus.params import derive_params
from brewmetheus.pk_model import concentration_curve
from brewmetheus.predict import crash_time_h, sleep_forecast
from brewmetheus.slo import day_slo
from brewmetheus.store import Store
from brewmetheus.timeutil import day_window_offsets, resolve_sleep_offset, to_offsets

_MODEL_WINDOW_H = 48.0


def build_snapshot(store: Store, now: datetime | None = None) -> Snapshot:
    """Evaluate the whole caffeine service at ``now`` (default: the current UTC time)."""
    now = now or datetime.now(timezone.utc)
    profile = store.load_profile()
    events = store.get_recent_intakes(within_h=_MODEL_WINDOW_H, now=now)
    intakes = to_offsets(events, reference=now)
    params = derive_params(profile)
    sleep_h = resolve_sleep_offset(profile.sleep_time_local, profile.timezone, now)
    today = now.astimezone(ZoneInfo(profile.timezone)).date()
    daily_total = store.daily_total_mg(today, profile)

    c_now = float(concentration_curve(np.asarray([0.0]), intakes, params)[0])
    incidents = evaluate_incidents(
        intakes, params, profile, sleep_h, current_daily_total_mg=daily_total
    )
    primary = primary_incident(incidents)
    forecast = sleep_forecast(intakes, params, profile, sleep_h)
    crash = crash_time_h(intakes, params, profile.awake_threshold_mg_l)

    clarity: float | None = None
    budget_remaining_h: float | None = None
    burn_rate: float | None = None
    if profile.sleep_time_local > profile.wake_time_local:
        wake_h, window_sleep_h = day_window_offsets(
            profile.wake_time_local, profile.sleep_time_local, profile.timezone, now
        )
        report = day_slo(
            intakes,
            params,
            wake_h,
            window_sleep_h,
            profile.awake_threshold_mg_l,
            profile.clarity_sla_target,
            now_h=0.0,
        )
        clarity = report.uptime_ratio
        budget_remaining_h = report.budget_remaining_h
        burn_rate = report.burn_rate

    return Snapshot(
        blood_caffeine_mg_l=c_now,
        awake_threshold_mg_l=profile.awake_threshold_mg_l,
        insomnia_threshold_mg_l=profile.sleep_insomnia_threshold_mg_l,
        bedtime_residual_mg_l=forecast.residual_mg_l,
        daily_total_mg=daily_total,
        daily_cap_mg=profile.daily_cap_mg,
        effective_half_life_h=params.effective_half_life_h,
        lifetime_intake_mg=store.lifetime_total_mg(),
        severity=primary.severity,
        incident_code=primary.code,
        incidents=incidents,
        version=__version__,
        clarity_sla_ratio=clarity,
        error_budget_remaining_h=budget_remaining_h,
        burn_rate=burn_rate,
        time_to_crash_h=crash,
    )
