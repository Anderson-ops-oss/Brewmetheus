"""Tests for the SVG badge / status-card renderers."""

from brewmetheus.models import CrashInterval, SLOReport
from brewmetheus.render import _AMBER, _GREEN, _RED, render_badge, render_card


def _report(uptime: float, target: float = 0.9, incidents: int = 0) -> SLOReport:
    crashes = [CrashInterval(0.0, 1.0) for _ in range(incidents)]
    return SLOReport(
        waking_h=16.0,
        uptime_ratio=uptime,
        downtime_h=(1.0 - uptime) * 16.0,
        crashes=crashes,
        incident_count=incidents,
        mttr_h=1.0 if incidents else None,
        mtbf_h=None,
        error_budget_h=(1.0 - target) * 16.0,
        budget_remaining_h=0.3,
        avg_mg_l=3.14,
        sla_target=target,
        sla_met=uptime >= target,
    )


def test_badge_is_wellformed_svg_with_value() -> None:
    svg = render_badge(_report(0.923))
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "92.3%" in svg
    assert "caffeine SLA" in svg


def test_badge_color_reflects_status() -> None:
    assert _GREEN in render_badge(_report(0.95))  # met -> green
    assert _AMBER in render_badge(_report(0.85))  # within 10 pts -> amber
    assert _RED in render_badge(_report(0.60))  # far below -> red


def test_card_contains_key_metrics() -> None:
    svg = render_card(_report(0.88, incidents=2), subtitle="2026-07-01")
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "87.5%" not in svg  # sanity: not a wrong number
    assert "88.0%" in svg
    assert "P1 incidents: 2" in svg
    assert "MTTR: 60 min" in svg
    assert "2026-07-01" in svg


def test_card_escapes_subtitle() -> None:
    svg = render_card(_report(0.9), subtitle="a<b&c")
    assert "a&lt;b&amp;c" in svg
    assert "a<b&c" not in svg
