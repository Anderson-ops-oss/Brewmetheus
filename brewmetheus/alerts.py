from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from brewmetheus.models import Incident, PKParams, Severity, UserProfile
from brewmetheus.pk_model import concentration_curve
from brewmetheus.predict import crash_time_h, sleep_forecast

_P2_WINDOW_H = 0.5  # "crash imminent" if predicted within 30 minutes

_NOMINAL = ("SERVICE_NOMINAL", "Service nominal", "Caffeine within your healthy band.")

# HTTP status codes an SRE would actually reach for, keyed by incident code. Dead
# accurate except INSOMNIA_RISK -> 508 Loop Detected (you are stuck awake in a loop),
# the one wink. Consumed by the dashboard banner; degrades gracefully via .get().
HTTP_STATUS: dict[str, str] = {
    "SERVICE_NOMINAL": "200 OK",
    "ATTENTION_UNAVAILABLE": "503 Service Unavailable",
    "DEGRADATION_IMMINENT": "503 Service Unavailable (degraded)",
    "OVERLOAD": "429 Too Many Requests",
    "INSOMNIA_RISK": "508 Loop Detected",
}

# On-call runbooks, keyed by incident code. Kept clinical on purpose: the humor is
# the deadpan register, not jokey copy. Step 1 of an outage is its own confirmation.
RUNBOOKS: dict[str, list[str]] = {
    "ATTENTION_UNAVAILABLE": [
        "Confirm the outage: still re-reading this line? Confirmed.",
        "Apply standard remediation: 1x drip coffee (95 mg).",
        "Expected recovery ~40 min (see the half-life). Do not stack doses.",
        "Unresolved after 2 cups? Escalate to a 20-minute nap.",
    ],
    "DEGRADATION_IMMINENT": [
        "A crash is predicted shortly; the refill window is closing.",
        "Apply a standard dose now to hold above the awake threshold.",
        "Consult the refill window below before it advises against it.",
    ],
    "OVERLOAD": [
        "Stop ingesting: you are over your safe ceiling or daily cap.",
        "No remediation required — the service self-heals as caffeine clears.",
        "Do not treat overload with more coffee. That is not a rollback.",
    ],
    "INSOMNIA_RISK": [
        "Freeze further intake for today (change freeze in effect).",
        "Verify no hidden dependencies: decaf, chocolate, pre-workout.",
        "If residual persists, accept degraded sleep as a known issue.",
    ],
}


def evaluate_incidents(
    intakes: Iterable[tuple[float, float]],
    params: PKParams,
    profile: UserProfile,
    sleep_h: float,
    current_daily_total_mg: float = 0.0,
    now_h: float = 0.0,
) -> list[Incident]:
    """All active incidents for the current state (a quiet state -> a single OK)."""
    intake_list = list(intakes)
    c_now = float(
        concentration_curve(np.asarray([now_h], dtype=np.float64), intake_list, params)[0]
    )
    incidents: list[Incident] = []

    # Awake status: already crashed (P1), or about to (P2).
    if c_now < profile.awake_threshold_mg_l:
        if intake_list:
            detail = (
                f"Blood caffeine {c_now:.2f} mg/L is below your awake threshold "
                f"({profile.awake_threshold_mg_l:.2f}). Reboot with coffee."
            )
        else:
            detail = "Cold start: no caffeine in the system. But first, coffee."
        incidents.append(
            Incident(
                severity=Severity.P1,
                code="ATTENTION_UNAVAILABLE",
                title="P1: attention service unavailable",
                detail=detail,
                at_h=now_h,
            )
        )
    else:
        crash = crash_time_h(intake_list, params, profile.awake_threshold_mg_l, from_h=now_h)
        if crash is not None and (crash - now_h) < _P2_WINDOW_H:
            incidents.append(
                Incident(
                    severity=Severity.P2,
                    code="DEGRADATION_IMMINENT",
                    title="P2: degradation imminent",
                    detail=f"Crash predicted in {round((crash - now_h) * 60)} min. "
                    "Refill window closing.",
                    at_h=crash,
                )
            )

    # Overload guardrail: over the safe ceiling now, or over the daily cap.
    over_ceiling = profile.safe_ceiling_mg_l is not None and c_now > profile.safe_ceiling_mg_l
    over_cap = current_daily_total_mg > profile.daily_cap_mg
    if over_ceiling or over_cap:
        reason = (
            f"daily intake {current_daily_total_mg:.0f} mg exceeds your cap "
            f"({profile.daily_cap_mg:.0f} mg)"
            if over_cap
            else f"concentration {c_now:.2f} mg/L exceeds your safe ceiling"
        )
        incidents.append(
            Incident(
                severity=Severity.OVERLOAD,
                code="OVERLOAD",
                title="Overload: throttling advised",
                detail=f"Caffeine {reason}. Consider easing off.",
                at_h=now_h,
            )
        )

    # Insomnia risk at bedtime.
    forecast = sleep_forecast(intake_list, params, profile, sleep_h)
    if forecast.insomnia_risk:
        incidents.append(
            Incident(
                severity=Severity.P2,
                code="INSOMNIA_RISK",
                title="Insomnia risk tonight",
                detail=f"Projected bedtime residual {forecast.residual_mg_l:.2f} mg/L exceeds "
                f"your ceiling ({profile.sleep_insomnia_threshold_mg_l:.2f}).",
                at_h=sleep_h,
            )
        )

    if not incidents:
        incidents.append(Incident(Severity.OK, *_NOMINAL, at_h=now_h))
    return incidents


def primary_incident(incidents: list[Incident]) -> Incident:
    """The highest-severity incident, for the top status banner."""
    if not incidents:
        return Incident(Severity.OK, *_NOMINAL)
    return max(incidents, key=lambda incident: incident.severity)
