from __future__ import annotations

from collections.abc import Iterable

import numpy as np
from numpy.typing import NDArray

from brewmetheus.models import CrashInterval, PKParams, SLOReport
from brewmetheus.pk_model import concentration_curve

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


def day_slo(
    intakes: Iterable[tuple[float, float]],
    params: PKParams,
    wake_h: float,
    sleep_h: float,
    awake_threshold: float,
    sla_target: float,
) -> SLOReport:
    """Reliability report over the waking window ``[wake_h, sleep_h]``.

    ``intakes`` should already include any carry-over doses from before ``wake_h``
    (their offsets are simply negative relative to the same reference).
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
    )
