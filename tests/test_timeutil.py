from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from brewmetheus.models import IntakeEvent
from brewmetheus.timeutil import resolve_sleep_offset, to_offsets


def test_to_offsets_past_events_are_negative() -> None:
    now = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
    events = [
        IntakeEvent(now - timedelta(hours=2), 95.0),
        IntakeEvent(now, 63.0),
    ]
    offsets = to_offsets(events, reference=now)
    assert offsets[0] == pytest.approx((-2.0, 95.0))
    assert offsets[1] == pytest.approx((0.0, 63.0))


def test_resolve_sleep_offset_later_today() -> None:
    now = datetime(2026, 7, 1, 20, 0, tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(timezone.utc)
    assert resolve_sleep_offset(time(23, 30), "Asia/Shanghai", now) == pytest.approx(3.5)


def test_resolve_sleep_offset_rolls_to_tomorrow() -> None:
    # Bedtime already passed today -> next 23:30 is tomorrow (~23.75 h away).
    now = datetime(2026, 7, 1, 23, 45, tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(timezone.utc)
    assert resolve_sleep_offset(time(23, 30), "Asia/Shanghai", now) == pytest.approx(23.75)
