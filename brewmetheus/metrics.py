"""Render a Snapshot into Prometheus text exposition format (version 0.0.4).

The render.py of metrics: a pure string function, zero dependencies, golden-string
testable. No ``prometheus_client`` -- Brewmetheus is named after a monitoring system, so
it speaks the protocol by hand rather than dragging in a mutable global registry. Point
real Prometheus at the exporter and you can graph your own bloodstream.
"""

from __future__ import annotations

import math

from brewmetheus.models import Severity, Snapshot

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

_SECONDS_PER_HOUR = 3600.0


def _fmt(value: float) -> str:
    """Format a float for Prometheus: round-trippable, non-finite rendered as NaN."""
    if not math.isfinite(value):
        return "NaN"
    return repr(float(value))


def _esc_help(text: str) -> str:
    return text.replace("\\", "\\\\").replace("\n", "\\n")


def _esc_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _block(name: str, help_text: str, type_: str, samples: list[tuple[str, float]]) -> list[str]:
    lines = [f"# HELP {name} {_esc_help(help_text)}", f"# TYPE {name} {type_}"]
    lines += [f"{name}{labels} {_fmt(value)}" for labels, value in samples]
    return lines


def render_metrics(snap: Snapshot) -> str:
    """Serialize a Snapshot to the Prometheus text format (a full scrape response body)."""
    lines: list[str] = []

    lines += _block(
        "brewmetheus_blood_caffeine_mg_per_litre",
        "Current modelled blood caffeine concentration (mg/L).",
        "gauge",
        [("", snap.blood_caffeine_mg_l)],
    )
    lines += _block(
        "brewmetheus_awake_threshold_mg_per_litre",
        "Concentration below which attention is 'unavailable' (mg/L).",
        "gauge",
        [("", snap.awake_threshold_mg_l)],
    )
    lines += _block(
        "brewmetheus_insomnia_threshold_mg_per_litre",
        "Bedtime residual above which sleep is at risk (mg/L).",
        "gauge",
        [("", snap.insomnia_threshold_mg_l)],
    )
    lines += _block(
        "brewmetheus_bedtime_residual_mg_per_litre",
        "Projected caffeine still on board at bedtime (mg/L).",
        "gauge",
        [("", snap.bedtime_residual_mg_l)],
    )
    lines += _block(
        "brewmetheus_caffeine_daily_total_mg",
        "Caffeine ingested so far today (mg).",
        "gauge",
        [("", snap.daily_total_mg)],
    )
    lines += _block(
        "brewmetheus_caffeine_daily_cap_mg",
        "Configured daily caffeine cap (mg).",
        "gauge",
        [("", snap.daily_cap_mg)],
    )
    lines += _block(
        "brewmetheus_effective_half_life_seconds",
        "Effective caffeine elimination half-life (seconds).",
        "gauge",
        [("", snap.effective_half_life_h * _SECONDS_PER_HOUR)],
    )

    if snap.clarity_sla_ratio is not None:
        lines += _block(
            "brewmetheus_clarity_sla_ratio",
            "Fraction of the waking window spent above the awake threshold so far (0-1).",
            "gauge",
            [("", snap.clarity_sla_ratio)],
        )
    if snap.error_budget_remaining_h is not None:
        lines += _block(
            "brewmetheus_error_budget_remaining_seconds",
            "Remaining clarity error budget today (seconds; negative if over budget).",
            "gauge",
            [("", snap.error_budget_remaining_h * _SECONDS_PER_HOUR)],
        )
    if snap.burn_rate is not None:
        lines += _block(
            "brewmetheus_error_budget_burn_rate",
            "Error-budget burn rate: downtime fraction so far / allowed fraction.",
            "gauge",
            [("", snap.burn_rate)],
        )
    if snap.time_to_crash_h is not None:
        lines += _block(
            "brewmetheus_time_to_crash_seconds",
            "Predicted time until caffeine crosses below the awake threshold (seconds).",
            "gauge",
            [("", snap.time_to_crash_h * _SECONDS_PER_HOUR)],
        )

    lines += _block(
        "brewmetheus_service_status",
        "Active incident severity (1 for the current level, 0 otherwise).",
        "gauge",
        [(f'{{severity="{sev.name}"}}', 1.0 if sev is snap.severity else 0.0) for sev in Severity],
    )
    lines += _block(
        "brewmetheus_caffeine_intake_mg_total",
        "Cumulative caffeine logged over all time (mg). Resets only on data loss.",
        "counter",
        [("", snap.lifetime_intake_mg)],
    )
    lines += _block(
        "brewmetheus_build_info",
        "Build metadata; always 1.",
        "gauge",
        [(f'{{version="{_esc_label(snap.version)}"}}', 1.0)],
    )

    return "\n".join(lines) + "\n"
