import numpy as np
import pytest

from brewmetheus.models import PKParams, UserProfile
from brewmetheus.params import derive_params
from brewmetheus.pk_model import concentration_curve, tmax_h
from brewmetheus.predict import crash_time_h, refill_window_h, sleep_forecast


def _profile_and_params() -> tuple[UserProfile, PKParams]:
    profile = UserProfile()
    return profile, derive_params(profile)


# --- crash_time_h ---
def test_crash_after_single_dose() -> None:
    profile, params = _profile_and_params()
    intakes = [(0.0, 200.0)]
    crash = crash_time_h(intakes, params, profile.awake_threshold_mg_l)
    assert crash is not None
    assert crash > tmax_h(params)  # crash happens on the way down
    at_crash = float(concentration_curve(np.asarray([crash]), intakes, params)[0])
    assert at_crash == pytest.approx(profile.awake_threshold_mg_l, abs=1e-6)


def test_no_crash_when_never_above_threshold() -> None:
    _, params = _profile_and_params()
    assert crash_time_h([(0.0, 200.0)], params, awake_threshold=100.0) is None
    assert crash_time_h([], params, awake_threshold=1.5) is None


def test_crash_found_after_a_future_dose() -> None:
    profile, params = _profile_and_params()
    intakes = [(2.0, 200.0)]  # dose 2 h from now
    crash = crash_time_h(intakes, params, profile.awake_threshold_mg_l, from_h=0.0)
    assert crash is not None
    assert crash > 2.0 + tmax_h(params)  # after the dose has peaked and fallen back


# --- refill_window_h (Definition A) ---
def test_refill_feasible() -> None:
    profile, params = _profile_and_params()
    intakes = [(0.0, 200.0)]
    crash = crash_time_h(intakes, params, profile.awake_threshold_mg_l)
    assert crash is not None
    result = refill_window_h(
        intakes,
        params,
        profile,
        sleep_h=48.0,
        standard_dose_mg=95.0,
        current_daily_total_mg=0.0,
    )
    assert result.feasible is True
    assert result.blocked_by is None
    assert result.at_h == pytest.approx(crash, abs=0.02)
    assert result.projected_daily_total_mg == pytest.approx(95.0)


def test_refill_blocked_by_daily_cap() -> None:
    profile, params = _profile_and_params()
    result = refill_window_h(
        [(0.0, 200.0)],
        params,
        profile,
        sleep_h=48.0,
        standard_dose_mg=95.0,
        current_daily_total_mg=380.0,  # 380 + 95 > 400 cap
    )
    assert result.feasible is False
    assert result.blocked_by == "DAILY_CAP"


def test_refill_blocked_by_sleep() -> None:
    profile, params = _profile_and_params()
    intakes = [(0.0, 200.0)]
    crash = crash_time_h(intakes, params, profile.awake_threshold_mg_l)
    assert crash is not None
    # Bedtime set so the new dose peaks right at bedtime -> big residual.
    sleep_h = crash + tmax_h(params)
    result = refill_window_h(
        intakes,
        params,
        profile,
        sleep_h=sleep_h,
        standard_dose_mg=95.0,
        current_daily_total_mg=0.0,
    )
    assert result.feasible is False
    assert result.blocked_by == "SLEEP"


def test_refill_no_crash_coming() -> None:
    profile = UserProfile(awake_threshold_mg_l=0.01)  # so low you won't crash in 24 h
    params = derive_params(profile)
    result = refill_window_h(
        [(0.0, 200.0)],
        params,
        profile,
        sleep_h=20.0,
        standard_dose_mg=95.0,
        current_daily_total_mg=0.0,
    )
    assert result.feasible is False
    assert result.blocked_by == "NO_CRASH_COMING"


# --- sleep_forecast ---
def test_sleep_forecast_insomnia_risk() -> None:
    profile, params = _profile_and_params()
    forecast = sleep_forecast([(0.0, 200.0)], params, profile, sleep_h=1.0)
    assert forecast.residual_mg_l > profile.sleep_insomnia_threshold_mg_l
    assert forecast.insomnia_risk is True


def test_sleep_forecast_safe() -> None:
    profile, params = _profile_and_params()
    forecast = sleep_forecast([(0.0, 200.0)], params, profile, sleep_h=40.0)
    assert forecast.insomnia_risk is False


def test_sleep_forecast_matches_curve() -> None:
    profile, params = _profile_and_params()
    intakes = [(0.0, 200.0)]
    sleep_h = 12.0
    forecast = sleep_forecast(intakes, params, profile, sleep_h)
    expected = float(concentration_curve(np.asarray([sleep_h]), intakes, params)[0])
    assert forecast.residual_mg_l == pytest.approx(expected)
    assert forecast.sleep_h == sleep_h
