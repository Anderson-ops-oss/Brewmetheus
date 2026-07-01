from __future__ import annotations

from collections.abc import Iterable

import numpy as np
from scipy.optimize import brentq

from brewmetheus.models import PKParams, RefillSuggestion, SleepForecast, UserProfile
from brewmetheus.pk_model import concentration_curve, concentration_single

_GRID_STEP_H = 1.0 / 60.0  # 1-minute resolution


def _concentration_at(t_h: float, intakes: list[tuple[float, float]], params: PKParams) -> float:
    """Total concentration (mg/L) at a single time offset."""
    return float(concentration_curve(np.asarray([t_h], dtype=np.float64), intakes, params)[0])


def crash_time_h(
    intakes: Iterable[tuple[float, float]],
    params: PKParams,
    awake_threshold: float,
    from_h: float = 0.0,
    horizon_h: float = 24.0,
) -> float | None:
    """First time after ``from_h`` the curve crosses down through the awake threshold.

    Returns None if the curve never sits above the threshold in the window, or
    never crosses back below it within the horizon.
    """
    intake_list = list(intakes)  # materialize: reused by the grid scan and brentq
    n = int(round(horizon_h / _GRID_STEP_H)) + 1
    grid = from_h + np.arange(n, dtype=np.float64) * _GRID_STEP_H
    curve = concentration_curve(grid, intake_list, params)
    above = curve >= awake_threshold
    # Downward crossing: above at i, below at i + 1.
    crossings = above[:-1] & ~above[1:]
    if not bool(crossings.any()):
        return None
    i = int(np.argmax(crossings))

    def gap(t: float) -> float:
        return _concentration_at(t, intake_list, params) - awake_threshold

    return float(brentq(gap, float(grid[i]), float(grid[i + 1])))


def refill_window_h(
    intakes: Iterable[tuple[float, float]],
    params: PKParams,
    profile: UserProfile,
    sleep_h: float,
    standard_dose_mg: float,
    current_daily_total_mg: float,
    from_h: float = 0.0,
) -> RefillSuggestion:
    """the latest safe top-up before you crash.

    The candidate time is the crash itself (the latest possible moment). It is
    then checked against the daily cap and the pre-sleep insomnia ceiling.
    """
    intake_list = list(intakes)
    base_residual = _concentration_at(sleep_h, intake_list, params)
    crash = crash_time_h(intake_list, params, profile.awake_threshold_mg_l, from_h=from_h)

    if crash is None:
        # No crash ahead in the horizon: nothing to refill for.
        return RefillSuggestion(
            feasible=False,
            dose_mg=standard_dose_mg,
            projected_bedtime_residual_mg_l=base_residual,
            projected_daily_total_mg=current_daily_total_mg,
            at_h=None,
            blocked_by="NO_CRASH_COMING",
        )

    projected_total = current_daily_total_mg + standard_dose_mg
    # A dose added at the crash contributes this much to the bedtime residual.
    new_dose_residual = float(concentration_single(sleep_h - crash, standard_dose_mg, params))
    projected_residual = base_residual + new_dose_residual

    if projected_total > profile.daily_cap_mg:
        return RefillSuggestion(
            feasible=False,
            dose_mg=standard_dose_mg,
            projected_bedtime_residual_mg_l=projected_residual,
            projected_daily_total_mg=projected_total,
            at_h=None,
            blocked_by="DAILY_CAP",
        )

    if projected_residual > profile.sleep_insomnia_threshold_mg_l:
        return RefillSuggestion(
            feasible=False,
            dose_mg=standard_dose_mg,
            projected_bedtime_residual_mg_l=projected_residual,
            projected_daily_total_mg=projected_total,
            at_h=None,
            blocked_by="SLEEP",
        )

    return RefillSuggestion(
        feasible=True,
        dose_mg=standard_dose_mg,
        projected_bedtime_residual_mg_l=projected_residual,
        projected_daily_total_mg=projected_total,
        at_h=crash,
        blocked_by=None,
    )


def sleep_forecast(
    intakes: Iterable[tuple[float, float]],
    params: PKParams,
    profile: UserProfile,
    sleep_h: float,
) -> SleepForecast:
    """Residual concentration at bedtime and whether it risks insomnia."""
    residual = _concentration_at(sleep_h, list(intakes), params)
    return SleepForecast(
        residual_mg_l=residual,
        insomnia_risk=residual > profile.sleep_insomnia_threshold_mg_l,
        sleep_h=sleep_h,
    )
