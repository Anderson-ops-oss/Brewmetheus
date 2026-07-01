from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from brewmetheus.models import IntakeEvent


def to_offsets(events: Iterable[IntakeEvent], reference: datetime) -> list[tuple[float, float]]:
    """Convert intake events into (t_offset_h, dose_mg) pairs relative to ``reference``.

    Past events get negative offsets. ``reference`` and the timestamps must be
    timezone-aware.
    """
    return [
        ((event.timestamp_utc - reference).total_seconds() / 3600.0, event.caffeine_mg)
        for event in events
    ]


def resolve_sleep_offset(sleep_time_local: time, tz_name: str, now: datetime) -> float:
    """Hours from ``now`` until the next occurrence of the local bedtime clock time."""
    tz = ZoneInfo(tz_name)
    now_local = now.astimezone(tz)
    candidate = datetime.combine(now_local.date(), sleep_time_local, tzinfo=tz)
    if candidate <= now_local:
        candidate += timedelta(days=1)  # bedtime already passed today -> tomorrow
    delta = candidate.astimezone(timezone.utc) - now.astimezone(timezone.utc)
    return delta.total_seconds() / 3600.0
