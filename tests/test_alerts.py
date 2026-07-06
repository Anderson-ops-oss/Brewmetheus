from brewmetheus.alerts import (
    HTTP_STATUS,
    RUNBOOKS,
    evaluate_incidents,
    primary_incident,
)
from brewmetheus.models import Incident, Severity, UserProfile
from brewmetheus.params import derive_params
from brewmetheus.predict import crash_time_h

_ACTIONABLE_CODES = (
    "ATTENTION_UNAVAILABLE",
    "DEGRADATION_IMMINENT",
    "OVERLOAD",
    "INSOMNIA_RISK",
)


def _codes(incidents: list[Incident]) -> set[str]:
    return {incident.code for incident in incidents}


def _incident(incidents: list[Incident], code: str) -> Incident:
    return next(incident for incident in incidents if incident.code == code)


def test_nominal_when_comfortably_awake() -> None:
    profile = UserProfile()
    params = derive_params(profile)
    # Drank 1 h ago: above threshold, crash far off, bedtime far away, low total.
    incidents = evaluate_incidents([(-1.0, 150.0)], params, profile, sleep_h=15.0)
    assert _codes(incidents) == {"SERVICE_NOMINAL"}
    assert primary_incident(incidents).severity is Severity.OK


def test_p1_when_below_threshold() -> None:
    profile = UserProfile()
    params = derive_params(profile)
    incidents = evaluate_incidents([], params, profile, sleep_h=15.0)  # no caffeine at all
    assert "ATTENTION_UNAVAILABLE" in _codes(incidents)
    assert primary_incident(incidents).severity is Severity.P1


def test_p2_when_crash_imminent() -> None:
    profile = UserProfile()
    params = derive_params(profile)
    intakes = [(0.0, 200.0)]
    crash = crash_time_h(intakes, params, profile.awake_threshold_mg_l)
    assert crash is not None
    now_h = crash - 0.25  # 15 min before the crash: still above, crossing soon
    incidents = evaluate_incidents(intakes, params, profile, sleep_h=48.0, now_h=now_h)
    assert "DEGRADATION_IMMINENT" in _codes(incidents)


def test_overload_by_daily_cap() -> None:
    profile = UserProfile()
    params = derive_params(profile)
    incidents = evaluate_incidents(
        [(-1.0, 150.0)], params, profile, sleep_h=15.0, current_daily_total_mg=450.0
    )
    assert "OVERLOAD" in _codes(incidents)
    assert primary_incident(incidents).severity is Severity.OVERLOAD


def test_overload_by_safe_ceiling() -> None:
    profile = UserProfile(safe_ceiling_mg_l=3.0)
    params = derive_params(profile)
    # Drank 1 h ago -> ~3.8 mg/L now, above the 3.0 ceiling.
    incidents = evaluate_incidents([(-1.0, 150.0)], params, profile, sleep_h=15.0)
    assert "OVERLOAD" in _codes(incidents)


def test_insomnia_risk_flagged() -> None:
    profile = UserProfile()
    params = derive_params(profile)
    # Near the peak now (awake), but bedtime is only 1.5 h out -> high residual.
    incidents = evaluate_incidents([(0.0, 200.0)], params, profile, sleep_h=1.5, now_h=0.5)
    assert "INSOMNIA_RISK" in _codes(incidents)


def test_cold_start_detail_when_no_intakes() -> None:
    profile = UserProfile()
    params = derive_params(profile)
    incidents = evaluate_incidents([], params, profile, sleep_h=15.0)
    assert "Cold start" in _incident(incidents, "ATTENTION_UNAVAILABLE").detail


def test_below_threshold_with_history_is_not_cold_start() -> None:
    profile = UserProfile()
    params = derive_params(profile)
    # Drank 12 h ago: essentially eliminated now -> below threshold, but not a cold start.
    incidents = evaluate_incidents([(-12.0, 100.0)], params, profile, sleep_h=15.0)
    detail = _incident(incidents, "ATTENTION_UNAVAILABLE").detail
    assert "Cold start" not in detail
    assert "Reboot with coffee" in detail


def test_http_status_covers_every_emittable_code() -> None:
    codes = {"SERVICE_NOMINAL", *_ACTIONABLE_CODES}
    assert codes <= set(HTTP_STATUS)
    assert HTTP_STATUS["INSOMNIA_RISK"] == "508 Loop Detected"


def test_runbooks_cover_actionable_incidents_but_not_nominal() -> None:
    for code in _ACTIONABLE_CODES:
        assert RUNBOOKS.get(code), code
    assert "SERVICE_NOMINAL" not in RUNBOOKS  # a nominal service needs no runbook


def test_primary_incident_picks_highest_severity() -> None:
    ok = Incident(Severity.OK, "SERVICE_NOMINAL", "x", "y")
    p2 = Incident(Severity.P2, "DEGRADATION_IMMINENT", "x", "y")
    overload = Incident(Severity.OVERLOAD, "OVERLOAD", "x", "y")
    assert primary_incident([ok, p2, overload]) is overload
    assert primary_incident([]).code == "SERVICE_NOMINAL"
