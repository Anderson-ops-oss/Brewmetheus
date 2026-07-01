"""Tests for the SLO reliability engine."""

import numpy as np
import pytest

from brewmetheus.models import UserProfile
from brewmetheus.params import derive_params
from brewmetheus.slo import _crash_intervals, day_slo

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
