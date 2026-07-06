"""Render an SLOReport into a blameless postmortem (Markdown).

The "afterthought" half of the project, and the render.py of text: a pure string
function, no I/O, golden-string testable. Prometheus is *forethought* (the
predictions); his brother Epimetheus is *afterthought* -- which is exactly what a
postmortem is.

Built only from computed times, counts, and a caller-supplied clock formatter, never
from free-text input, so the output cannot be a Markdown-injection vector.
"""

from __future__ import annotations

from collections.abc import Callable

from brewmetheus.models import SLOReport


def render_postmortem(
    report: SLOReport,
    day: str,
    awake_threshold_mg_l: float,
    to_clock: Callable[[float], str],
) -> str:
    """A Google-SRE-style postmortem for one day's caffeine reliability.

    ``day`` is a pre-formatted date label (e.g. "2026-07-06"); ``to_clock`` maps an
    offset in hours to a wall-clock string, keeping this function free of tz/datetime.
    """
    pct = report.uptime_ratio * 100
    target_pct = report.sla_target * 100
    downtime_min = report.downtime_h * 60
    mttr = f"{report.mttr_h * 60:.0f} min" if report.mttr_h is not None else "n/a"
    status = "Resolved" if report.sla_met else "SLA breached"

    lines = [
        f"# Postmortem — Caffeine Service, {day}",
        "",
        f"**Status:** {status} · **Incidents:** {report.incident_count} · "
        f"**Downtime:** {downtime_min:.0f} min · **MTTR:** {mttr}",
        "",
        "## Impact",
        f"Attention was below the awake threshold ({awake_threshold_mg_l:.2f} mg/L) for "
        f"{downtime_min:.0f} min across {report.incident_count} incident(s), for a clarity "
        f"SLA of {pct:.1f}% against a {target_pct:.0f}% target.",
        "",
        "## Timeline",
    ]
    if report.crashes:
        for i, crash in enumerate(report.crashes, start=1):
            lines.append(
                f"- {to_clock(crash.start_h)}–{to_clock(crash.end_h)} — incident {i}, "
                f"down {crash.duration_h * 60:.0f} min"
            )
    else:
        lines.append("- No incidents. The service held above the awake threshold all day.")

    lines += ["", "## Root cause"]
    if report.crashes:
        lines.append(
            "Insufficient caffeine on board: prior doses eliminated faster than they were "
            "replenished."
        )
    else:
        lines.append("None. Caffeine stayed within the healthy band.")

    lines += ["", "## Action items"]
    if report.crashes:
        lines += [
            "- [ ] Schedule a top-up ~30 min before the next projected crash.",
            "- [ ] Shift the morning dose earlier or raise the baseline cup.",
        ]
    else:
        lines.append("- [ ] None. Keep doing whatever you did.")

    lines += ["", "*Blameless: the coffee is not to blame. Neither are you.*", ""]
    return "\n".join(lines)
