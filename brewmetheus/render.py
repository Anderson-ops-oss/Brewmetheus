"""Render an SLOReport into self-contained SVG (badge + status card).

Pure string functions, no dependencies. Output is standalone SVG suitable for
embedding in a GitHub profile README or downloading. This is the render half of
the "publish" feature; a separate step decides where to put the files.
"""

from __future__ import annotations

from brewmetheus.models import SLOReport

_GREEN = "#3fb950"
_AMBER = "#d29922"
_RED = "#f85149"
_FONT = "Verdana,DejaVu Sans,sans-serif"

# Rough monospace-ish width estimate for badge sizing (Verdana at 11px).
_CHAR_W = 6.5
_PAD = 10.0


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _status_color(report: SLOReport) -> str:
    if report.sla_met:
        return _GREEN
    if report.uptime_ratio >= report.sla_target - 0.1:
        return _AMBER  # within 10 percentage points of target
    return _RED


def _svg_badge(label: str, message: str, color: str) -> str:
    label = _esc(label)
    message = _esc(message)
    label_w = round(len(label) * _CHAR_W + 2 * _PAD)
    msg_w = round(len(message) * _CHAR_W + 2 * _PAD)
    total = label_w + msg_w
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="20" '
        f'role="img" aria-label="{label}: {message}">'
        f'<clipPath id="r"><rect width="{total}" height="20" rx="3"/></clipPath>'
        f'<g clip-path="url(#r)">'
        f'<rect width="{label_w}" height="20" fill="#555"/>'
        f'<rect x="{label_w}" width="{msg_w}" height="20" fill="{color}"/>'
        f"</g>"
        f'<g fill="#fff" font-family="{_FONT}" font-size="11" text-anchor="middle">'
        f'<text x="{label_w / 2:.0f}" y="14">{label}</text>'
        f'<text x="{label_w + msg_w / 2:.0f}" y="14">{message}</text>'
        f"</g></svg>"
    )


def render_badge(report: SLOReport) -> str:
    """A one-line shields-style SVG badge: 'caffeine SLA | 92.3%'."""
    return _svg_badge("caffeine SLA", f"{report.uptime_ratio * 100:.1f}%", _status_color(report))


def render_card(report: SLOReport, subtitle: str = "") -> str:
    """A status-page-style SVG card with the day's reliability metrics."""
    color = _status_color(report)
    pct = report.uptime_ratio * 100
    mttr = f"{report.mttr_h * 60:.0f} min" if report.mttr_h is not None else "—"
    lines = [
        f"P1 incidents: {report.incident_count}",
        f"MTTR: {mttr}",
        f"Error budget left: {report.budget_remaining_h * 60:.0f} min",
        f"Avg concentration: {report.avg_mg_l:.2f} mg/L",
    ]
    stats = "".join(
        f'<text x="250" y="{104 + i * 26}" fill="#8b949e" font-size="14">{_esc(line)}</text>'
        for i, line in enumerate(lines)
    )
    caption = f"clarity SLA (today) · target {report.sla_target * 100:.0f}%"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="480" height="200" '
        f'role="img" aria-label="Caffeine service status card" font-family="{_FONT}">'
        f'<rect width="480" height="200" rx="12" fill="#0d1117"/>'
        f'<circle cx="34" cy="40" r="9" fill="{color}"/>'
        f'<text x="52" y="46" fill="#e6edf3" font-size="20" font-weight="bold">'
        f"Caffeine Service</text>"
        f'<text x="34" y="74" fill="#8b949e" font-size="13">{_esc(subtitle)}</text>'
        f'<text x="34" y="150" fill="{color}" font-size="56" font-weight="bold">{pct:.1f}%</text>'
        f'<text x="34" y="178" fill="#8b949e" font-size="13">{_esc(caption)}</text>'
        f"<g>{stats}</g>"
        f"</svg>"
    )
