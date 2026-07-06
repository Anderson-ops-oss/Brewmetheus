"""Tests for the SLO reliability engine."""

import numpy as np
import pytest

from brewmetheus.models import CrashInterval, UserProfile
from brewmetheus.params import derive_params
from brewmetheus.pk_model import tmax_h
from brewmetheus.slo import _crash_intervals, _downtime_before, day_slo, golden_signals

_TARGET = 0.9


def test_crash_intervals_detects_recovery_and_ongoing() -> None:
    # Direct test of the interval detector on a hand-made curve (threshold = 1.0).
    times = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    curve = np.array([2.0, 2.0, 0.5, 0.5, 2.0, 0.5, 0.5])
    intervals = _crash_intervals(times, curve, 1.0)
    assert len(intervals) == 2
    assert (intervals[0].start_h, intervals[0].end_h) == (2.0, 4.0)  # recovered at idx 4
    assert (intervals[1].start_h, intervals[1].end_h) == (5.0, 6.0)  # ongoing at close


def test_all_up_perfect_sla() -> None:
    params = derive_params(UserProfile())
    # A big dose 1 h before waking keeps us above threshold for the whole window.
    report = day_slo([(-1.0, 300.0)], params, 0.0, 8.0, awake_threshold=1.5, sla_target=_TARGET)
    assert report.uptime_ratio == pytest.approx(1.0)
    assert report.incident_count == 0
    assert report.downtime_h == pytest.approx(0.0)
    assert report.mttr_h is None
    assert report.mtbf_h is None
    assert report.sla_met is True
    assert report.budget_remaining_h == pytest.approx(report.error_budget_h)


def test_all_down_no_caffeine() -> None:
    params = derive_params(UserProfile())
    report = day_slo([], params, 0.0, 8.0, awake_threshold=1.5, sla_target=_TARGET)
    assert report.uptime_ratio == pytest.approx(0.0)
    assert report.incident_count == 1
    assert report.downtime_h == pytest.approx(8.0)
    assert report.mttr_h == pytest.approx(8.0)
    assert report.mtbf_h is None
    assert report.sla_met is False
    assert report.budget_remaining_h == pytest.approx(0.1 * 8.0 - 8.0)  # over budget


def test_single_dose_is_one_incident() -> None:
    params = derive_params(UserProfile())
    report = day_slo([(-1.0, 150.0)], params, 0.0, 12.0, awake_threshold=1.5, sla_target=_TARGET)
    assert report.incident_count == 1  # up at first, then one crash (the tail)
    assert 0.0 < report.uptime_ratio < 1.0
    assert report.mttr_h == pytest.approx(report.downtime_h)  # only one incident
    assert report.mtbf_h is None


def test_slo_invariants_hold() -> None:
    params = derive_params(UserProfile())
    report = day_slo(
        [(-1.0, 150.0), (4.0, 95.0), (9.0, 60.0)],
        params,
        0.0,
        16.0,
        awake_threshold=1.5,
        sla_target=_TARGET,
    )
    assert report.uptime_ratio == pytest.approx(1.0 - report.downtime_h / report.waking_h)
    assert report.downtime_h == pytest.approx(sum(c.duration_h for c in report.crashes))
    assert report.budget_remaining_h == pytest.approx(report.error_budget_h - report.downtime_h)
    assert report.error_budget_h == pytest.approx(0.1 * 16.0)
    assert report.sla_met == (report.uptime_ratio >= report.sla_target)


def test_sleep_before_wake_raises() -> None:
    params = derive_params(UserProfile())
    with pytest.raises(ValueError):
        day_slo([], params, 10.0, 5.0, awake_threshold=1.5, sla_target=_TARGET)


def test_downtime_before_clips_to_cutoff() -> None:
    crashes = [CrashInterval(-2.0, -1.0), CrashInterval(1.0, 3.0)]
    assert _downtime_before(crashes, cutoff_h=0.0) == pytest.approx(1.0)  # only the past one
    assert _downtime_before(crashes, cutoff_h=2.0) == pytest.approx(2.0)  # 1.0 + (2 - 1)
    assert _downtime_before(crashes, cutoff_h=10.0) == pytest.approx(3.0)  # both fully


def test_burn_rate_is_none_without_now() -> None:
    params = derive_params(UserProfile())
    report = day_slo([(-1.0, 150.0)], params, 0.0, 12.0, awake_threshold=1.5, sla_target=_TARGET)
    assert report.downtime_so_far_h is None
    assert report.burn_rate is None
    assert report.budget_exhaustion_h is None


def test_burn_rate_high_when_down_early() -> None:
    params = derive_params(UserProfile())
    # No caffeine at all; "now" is 2 h into an 8 h waking window -> fully down so far.
    report = day_slo([], params, -2.0, 6.0, awake_threshold=1.5, sla_target=_TARGET, now_h=0.0)
    assert report.downtime_so_far_h == pytest.approx(2.0)  # down the whole elapsed 2 h
    assert report.burn_rate == pytest.approx(10.0)  # 100% down / 10% allowed
    assert report.budget_exhaustion_h is None  # already over budget, nothing to project


def test_golden_signals_map_the_service() -> None:
    params = derive_params(UserProfile())
    sig = golden_signals(params, daily_total_mg=200.0, daily_cap_mg=400.0, downtime_so_far_h=0.5)
    assert sig.latency_h == pytest.approx(tmax_h(params))
    assert sig.traffic_mg == pytest.approx(200.0)
    assert sig.errors_h == pytest.approx(0.5)
    assert sig.saturation_ratio == pytest.approx(0.5)


def test_golden_signals_zero_cap_is_safe() -> None:
    params = derive_params(UserProfile())
    sig = golden_signals(params, 100.0, 0.0, 0.0)
    assert sig.saturation_ratio == 0.0
