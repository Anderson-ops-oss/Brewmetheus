"""Tests for the Prometheus text-exposition renderer."""

from dataclasses import replace

from brewmetheus.metrics import CONTENT_TYPE, render_metrics
from brewmetheus.models import Severity, Snapshot

_BASE = Snapshot(
    blood_caffeine_mg_l=2.5,
    awake_threshold_mg_l=1.5,
    insomnia_threshold_mg_l=2.0,
    bedtime_residual_mg_l=0.4,
    daily_total_mg=190.0,
    daily_cap_mg=400.0,
    effective_half_life_h=5.0,
    lifetime_intake_mg=12345.0,
    severity=Severity.P1,
    incident_code="ATTENTION_UNAVAILABLE",
    incidents=[],
    version="0.1.0",
    clarity_sla_ratio=0.92,
    error_budget_remaining_h=0.3,
    burn_rate=1.4,
    time_to_crash_h=2.0,
)


def test_content_type_is_prometheus_text() -> None:
    assert "version=0.0.4" in CONTENT_TYPE


def test_core_metrics_have_help_and_type() -> None:
    text = render_metrics(_BASE)
    assert "# HELP brewmetheus_blood_caffeine_mg_per_litre" in text
    assert "# TYPE brewmetheus_blood_caffeine_mg_per_litre gauge" in text
    assert "# TYPE brewmetheus_caffeine_intake_mg_total counter" in text
    assert "brewmetheus_caffeine_intake_mg_total 12345.0" in text
    assert 'brewmetheus_build_info{version="0.1.0"} 1.0' in text


def test_half_life_is_converted_to_seconds() -> None:
    assert "brewmetheus_effective_half_life_seconds 18000.0" in render_metrics(_BASE)


def test_service_status_enum_has_exactly_one_active() -> None:
    text = render_metrics(replace(_BASE, severity=Severity.P1))
    assert 'brewmetheus_service_status{severity="P1"} 1.0' in text
    assert 'brewmetheus_service_status{severity="OK"} 0.0' in text
    active = [
        line
        for line in text.splitlines()
        if line.startswith("brewmetheus_service_status") and line.endswith(" 1.0")
    ]
    assert len(active) == 1


def test_optional_metrics_omitted_when_none() -> None:
    text = render_metrics(
        replace(
            _BASE,
            clarity_sla_ratio=None,
            error_budget_remaining_h=None,
            burn_rate=None,
            time_to_crash_h=None,
        )
    )
    assert "brewmetheus_clarity_sla_ratio" not in text
    assert "brewmetheus_error_budget_remaining_seconds" not in text
    assert "brewmetheus_error_budget_burn_rate" not in text
    assert "brewmetheus_time_to_crash_seconds" not in text


def test_every_sample_line_parses_as_a_float() -> None:
    for line in render_metrics(_BASE).splitlines():
        if not line or line.startswith("#"):
            continue
        float(line.rsplit(" ", 1)[1])  # value token must parse; raises on malformed output
