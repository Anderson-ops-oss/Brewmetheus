# Test script for the shared data models.
from datetime import datetime, time, timezone

from brewmetheus.models import (
    Incident,
    IntakeEvent,
    PKParams,
    RefillSuggestion,
    Severity,
    SleepForecast,
    UserProfile,
)


def test_default_profile_is_constructible() -> None:
    profile = UserProfile()
    assert profile.weight_kg == 70.0
    assert profile.daily_cap_mg == 400.0
    assert profile.sleep_time_local == time(23, 30)
    assert profile.safe_ceiling_mg_l is None
    assert profile.timezone == "UTC"


def test_intake_event_defaults() -> None:
    event = IntakeEvent(
        timestamp_utc=datetime(2026, 7, 1, 8, 0, tzinfo=timezone.utc),
        caffeine_mg=95.0,
    )
    assert event.id == 0  # unsaved until the store assigns a rowid
    assert event.beverage_key is None
    assert event.caffeine_mg == 95.0


def test_severity_is_ordered_by_escalation() -> None:
    assert Severity.OVERLOAD > Severity.P1 > Severity.P2 > Severity.OK
    assert max([Severity.OK, Severity.P1, Severity.P2]) is Severity.P1


def test_result_dataclasses_construct() -> None:
    params = PKParams(F=1.0, V_l=35.0, ka_per_h=6.0, ke_per_h=0.1386, effective_half_life_h=5.0)
    assert params.V_l == 35.0

    incident = Incident(severity=Severity.P1, code="ATTENTION_UNAVAILABLE", title="x", detail="y")
    assert incident.at_h == 0.0

    refill = RefillSuggestion(
        feasible=True,
        dose_mg=95.0,
        projected_bedtime_residual_mg_l=1.2,
        projected_daily_total_mg=190.0,
        at_h=3.5,
    )
    assert refill.feasible is True

    forecast = SleepForecast(residual_mg_l=1.2, insomnia_risk=False, sleep_h=15.5)
    assert forecast.insomnia_risk is False
