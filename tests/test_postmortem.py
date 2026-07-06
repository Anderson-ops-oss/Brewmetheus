"""Tests for the blameless-postmortem renderer."""

from brewmetheus.models import CrashInterval, SLOReport
from brewmetheus.postmortem import render_postmortem


def _report(crashes: list[CrashInterval], uptime: float = 0.8, target: float = 0.9) -> SLOReport:
    return SLOReport(
        waking_h=16.0,
        uptime_ratio=uptime,
        downtime_h=(1.0 - uptime) * 16.0,
        crashes=crashes,
        incident_count=len(crashes),
        mttr_h=1.0 if crashes else None,
        mtbf_h=None,
        error_budget_h=1.6,
        budget_remaining_h=0.1,
        avg_mg_l=2.0,
        sla_target=target,
        sla_met=uptime >= target,
    )


def _clock(offset_h: float) -> str:
    return f"T{offset_h:+.1f}"


def test_postmortem_lists_each_incident() -> None:
    report = _report([CrashInterval(2.0, 3.0), CrashInterval(5.0, 5.5)])
    md = render_postmortem(report, "2026-07-06", 1.5, _clock)
    assert md.startswith("# Postmortem — Caffeine Service, 2026-07-06")
    assert "**Incidents:** 2" in md
    assert "incident 1" in md and "incident 2" in md
    assert "SLA breached" in md  # uptime 0.8 < 0.9 target
    assert "Blameless" in md


def test_postmortem_clean_day_is_resolved() -> None:
    md = render_postmortem(_report([], uptime=1.0), "2026-07-06", 1.5, _clock)
    assert "Resolved" in md
    assert "No incidents" in md
    assert "None. Keep doing whatever you did." in md


def test_postmortem_uses_the_clock_formatter() -> None:
    md = render_postmortem(
        _report([CrashInterval(2.0, 3.0)]), "2026-07-06", 1.5, lambda _h: "CLOCK"
    )
    assert "CLOCK–CLOCK" in md
