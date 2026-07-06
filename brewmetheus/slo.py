from __future__ import annotations

from collections.abc import Iterable

import numpy as np
from numpy.typing import NDArray

from brewmetheus.models import CrashInterval, GoldenSignals, PKParams, SLOReport
from brewmetheus.pk_model import concentration_curve, tmax_h

FloatArray = NDArray[np.float64]

_GRID_STEP_H = 1.0 / 60.0  # 1-minute resolution


def _crash_intervals(times: FloatArray, curve: FloatArray, threshold: float) -> list[CrashInterval]:
    """Contiguous stretches where the curve is below the threshold.

    A stretch still below at the window's end is closed at the last sample (an
    incident ongoing at close of business). Boundaries are grid-resolution.
    """
    below = curve < threshold
    intervals: list[CrashInterval] = []
    start_idx: int | None = None
    for i in range(len(below)):
        if below[i] and start_idx is None:
            start_idx = i
        elif not below[i] and start_idx is not None:
            intervals.append(CrashInterval(float(times[start_idx]), float(times[i])))
            start_idx = None
    if start_idx is not None:
        intervals.append(CrashInterval(float(times[start_idx]), float(times[-1])))
    return intervals


def _downtime_before(crashes: list[CrashInterval], cutoff_h: float) -> float:
    """Total downtime within crash intervals up to ``cutoff_h`` (downtime consumed so far)."""
    total = 0.0
    for crash in crashes:
        end = min(crash.end_h, cutoff_h)
        if end > crash.start_h:
            total += end - crash.start_h
    return total


def day_slo(
    intakes: Iterable[tuple[float, float]],
    params: PKParams,
    wake_h: float,
    sleep_h: float,
    awake_threshold: float,
    sla_target: float,
    now_h: float | None = None,
) -> SLOReport:
    """Reliability report over the waking window ``[wake_h, sleep_h]``.

    ``intakes`` should already include any carry-over doses from before ``wake_h``
    (their offsets are simply negative relative to the same reference).

    When ``now_h`` is given, the report also carries the "so far" burn-rate view:
    downtime consumed over ``[wake_h, now_h]``, the error-budget burn rate (actual
    downtime fraction so far / the allowed fraction), and a projected exhaustion time
    if the budget would run out before bed at the current rate.
    """
    if sleep_h <= wake_h:
        raise ValueError("sleep_h must be after wake_h.")

    intake_list = list(intakes)
    waking_h = sleep_h - wake_h
    n = int(round(waking_h / _GRID_STEP_H)) + 1
    times = wake_h + np.arange(n, dtype=np.float64) * _GRID_STEP_H
    curve = concentration_curve(times, intake_list, params)

    crashes = _crash_intervals(times, curve, awake_threshold)
    downtime_h = sum((crash.duration_h for crash in crashes), 0.0)
    uptime_ratio = 1.0 - downtime_h / waking_h

    mttr_h = downtime_h / len(crashes) if crashes else None  # mean crash duration
    if len(crashes) >= 2:
        gaps = [crashes[i + 1].start_h - crashes[i].end_h for i in range(len(crashes) - 1)]
        mtbf_h: float | None = sum(gaps, 0.0) / len(gaps)
    else:
        mtbf_h = None

    error_budget_h = (1.0 - sla_target) * waking_h

    downtime_so_far_h: float | None = None
    burn_rate: float | None = None
    budget_exhaustion_h: float | None = None
    if now_h is not None:
        cutoff = min(max(now_h, wake_h), sleep_h)
        elapsed_h = cutoff - wake_h
        downtime_so_far_h = _downtime_before(crashes, cutoff)
        allowed_ratio = 1.0 - sla_target  # sustainable downtime fraction
        if elapsed_h > 0 and allowed_ratio > 0:
            burn_rate = (downtime_so_far_h / elapsed_h) / allowed_ratio
            rate_per_h = downtime_so_far_h / elapsed_h
            remaining = error_budget_h - downtime_so_far_h
            if rate_per_h > 0 and remaining > 0:
                projected = cutoff + remaining / rate_per_h
                if projected <= sleep_h:  # only if the budget runs out before bed
                    budget_exhaustion_h = projected

    return SLOReport(
        waking_h=waking_h,
        uptime_ratio=uptime_ratio,
        downtime_h=downtime_h,
        crashes=crashes,
        incident_count=len(crashes),
        mttr_h=mttr_h,
        mtbf_h=mtbf_h,
        error_budget_h=error_budget_h,
        budget_remaining_h=error_budget_h - downtime_h,
        avg_mg_l=float(curve.mean()),
        sla_target=sla_target,
        sla_met=uptime_ratio >= sla_target,
        downtime_so_far_h=downtime_so_far_h,
        burn_rate=burn_rate,
        budget_exhaustion_h=budget_exhaustion_h,
    )


def golden_signals(
    params: PKParams,
    daily_total_mg: float,
    daily_cap_mg: float,
    downtime_so_far_h: float,
) -> GoldenSignals:
    """The four SRE golden signals mapped onto the caffeine service.

    Pure: every input is already computed elsewhere (Tmax from the model, the daily
    total and cap from the profile/store, the downtime so far from ``day_slo``).
    """
    saturation = daily_total_mg / daily_cap_mg if daily_cap_mg > 0 else 0.0
    return GoldenSignals(
        latency_h=tmax_h(params),
        traffic_mg=daily_total_mg,
        errors_h=downtime_so_far_h,
        saturation_ratio=saturation,
    )
