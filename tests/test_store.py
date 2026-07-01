from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest

from brewmetheus.models import IntakeEvent, UserProfile
from brewmetheus.store import FileStore

_DAY_START = datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)
_DAY_END = datetime(2026, 7, 2, 0, 0, tzinfo=timezone.utc)


# --- profile (JSON) ---
def test_profile_default_when_missing(tmp_path: Path) -> None:
    store = FileStore(tmp_path)
    profile = store.load_profile()
    assert profile.weight_kg == 70.0  # baseline defaults


def test_profile_save_load_roundtrip(tmp_path: Path) -> None:
    store = FileStore(tmp_path)
    original = UserProfile(
        weight_kg=90.0,
        smoker=True,
        sleep_time_local=time(22, 0),
        timezone="Asia/Shanghai",
        daily_cap_mg=350.0,
    )
    store.save_profile(original)
    assert store.load_profile() == original  # dataclass __eq__ over all fields


# --- intake log (SQLite) ---
def test_add_and_get_intake(tmp_path: Path) -> None:
    store = FileStore(tmp_path)
    ts = datetime(2026, 7, 1, 8, 0, tzinfo=timezone.utc)
    new_id = store.add_intake(IntakeEvent(ts, 95.0, beverage_key="drip_coffee"))
    assert new_id > 0

    events = store.get_intakes(_DAY_START, _DAY_END)
    assert len(events) == 1
    event = events[0]
    assert event.id == new_id
    assert event.caffeine_mg == 95.0
    assert event.beverage_key == "drip_coffee"
    assert event.timestamp_utc == ts  # UTC instant preserved across the round-trip


def test_get_intakes_filters_by_range(tmp_path: Path) -> None:
    store = FileStore(tmp_path)
    store.add_intake(IntakeEvent(datetime(2026, 7, 1, 8, 0, tzinfo=timezone.utc), 50.0))
    store.add_intake(IntakeEvent(datetime(2026, 7, 3, 8, 0, tzinfo=timezone.utc), 60.0))
    events = store.get_intakes(_DAY_START, _DAY_END)
    assert len(events) == 1
    assert events[0].caffeine_mg == 50.0


def test_get_recent_intakes(tmp_path: Path) -> None:
    store = FileStore(tmp_path)
    now = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
    store.add_intake(IntakeEvent(now - timedelta(hours=2), 40.0))  # recent
    store.add_intake(IntakeEvent(now - timedelta(hours=50), 40.0))  # outside 48 h
    recent = store.get_recent_intakes(within_h=48.0, now=now)
    assert len(recent) == 1


def test_update_intake(tmp_path: Path) -> None:
    store = FileStore(tmp_path)
    ts = datetime(2026, 7, 1, 8, 0, tzinfo=timezone.utc)
    new_id = store.add_intake(IntakeEvent(ts, 95.0))
    store.update_intake(IntakeEvent(timestamp_utc=ts, caffeine_mg=63.0, note="fixed", id=new_id))
    events = store.get_intakes(_DAY_START, _DAY_END)
    assert events[0].caffeine_mg == 63.0
    assert events[0].note == "fixed"


def test_delete_intake(tmp_path: Path) -> None:
    store = FileStore(tmp_path)
    new_id = store.add_intake(IntakeEvent(datetime(2026, 7, 1, 8, 0, tzinfo=timezone.utc), 95.0))
    store.delete_intake(new_id)
    assert store.get_intakes(_DAY_START, _DAY_END) == []


def test_daily_total_mg_respects_timezone(tmp_path: Path) -> None:
    store = FileStore(tmp_path)
    profile = UserProfile(timezone="Asia/Shanghai")  # UTC+8
    # 08:00 UTC == 16:00 Shanghai -> local date Jul 1
    store.add_intake(IntakeEvent(datetime(2026, 7, 1, 8, 0, tzinfo=timezone.utc), 95.0))
    # 20:00 UTC == 04:00 next day Shanghai -> local date Jul 2
    store.add_intake(IntakeEvent(datetime(2026, 7, 1, 20, 0, tzinfo=timezone.utc), 60.0))
    assert store.daily_total_mg(date(2026, 7, 1), profile) == pytest.approx(95.0)
    assert store.daily_total_mg(date(2026, 7, 2), profile) == pytest.approx(60.0)


def test_daily_total_mg_empty(tmp_path: Path) -> None:
    store = FileStore(tmp_path)
    assert store.daily_total_mg(date(2026, 7, 1), UserProfile()) == 0.0


def test_daily_totals_mg_spans_days(tmp_path: Path) -> None:
    store = FileStore(tmp_path)
    profile = UserProfile(timezone="UTC")
    store.add_intake(IntakeEvent(datetime(2026, 6, 30, 10, 0, tzinfo=timezone.utc), 100.0))
    store.add_intake(IntakeEvent(datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc), 50.0))
    store.add_intake(IntakeEvent(datetime(2026, 7, 1, 15, 0, tzinfo=timezone.utc), 30.0))
    totals = store.daily_totals_mg(3, date(2026, 7, 1), profile)
    assert [day for day, _ in totals] == [date(2026, 6, 29), date(2026, 6, 30), date(2026, 7, 1)]
    assert [mg for _, mg in totals] == pytest.approx([0.0, 100.0, 80.0])
