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


def day_window_offsets(
    wake_time_local: time, sleep_time_local: time, tz_name: str, now: datetime
) -> tuple[float, float]:
    """Offsets (hours from ``now``) of today's local waking window [wake, sleep].

    Anchored to ``now``'s local calendar date. Assumes bedtime is later than the
    wake time on the same day (the normal case).
    """
    tz = ZoneInfo(tz_name)
    today = now.astimezone(tz).date()
    ref_utc = now.astimezone(timezone.utc)
    wake_utc = datetime.combine(today, wake_time_local, tzinfo=tz).astimezone(timezone.utc)
    sleep_utc = datetime.combine(today, sleep_time_local, tzinfo=tz).astimezone(timezone.utc)
    wake_h = (wake_utc - ref_utc).total_seconds() / 3600.0
    sleep_h = (sleep_utc - ref_utc).total_seconds() / 3600.0
    return wake_h, sleep_h
