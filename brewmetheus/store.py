from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, fields
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from brewmetheus.models import IntakeEvent, UserProfile
from brewmetheus.timeutil import local_timezone_name

_SCHEMA = """
CREATE TABLE IF NOT EXISTS intake (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc TEXT    NOT NULL,
    caffeine_mg   REAL    NOT NULL,
    beverage_key  TEXT,
    serving_ml    REAL,
    note          TEXT
)
"""


class Store(Protocol):
    """The storage contract the rest of the app depends on."""

    def load_profile(self) -> UserProfile: ...
    def save_profile(self, profile: UserProfile) -> None: ...
    def add_intake(self, event: IntakeEvent) -> int: ...
    def get_intakes(self, since: datetime, until: datetime) -> list[IntakeEvent]: ...
    def get_recent_intakes(self, within_h: float, now: datetime) -> list[IntakeEvent]: ...
    def update_intake(self, event: IntakeEvent) -> None: ...
    def delete_intake(self, intake_id: int) -> None: ...
    def daily_total_mg(self, day_local_date: date, profile: UserProfile) -> float: ...
    def daily_totals_mg(
        self, days: int, end_local_date: date, profile: UserProfile
    ) -> list[tuple[date, float]]: ...
    def lifetime_total_mg(self) -> float: ...


# --- serialization helpers ---
def _to_utc_iso(dt: datetime) -> str:
    """Serialize a timezone-aware datetime to ISO-8601 UTC text."""
    if dt.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware (UTC).")
    return dt.astimezone(timezone.utc).isoformat()


def _from_iso(value: str) -> datetime:
    """Parse stored ISO text back into a timezone-aware UTC datetime."""
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _row_to_event(row: sqlite3.Row) -> IntakeEvent:
    return IntakeEvent(
        timestamp_utc=_from_iso(row["timestamp_utc"]),
        caffeine_mg=row["caffeine_mg"],
        beverage_key=row["beverage_key"],
        serving_ml=row["serving_ml"],
        note=row["note"],
        id=row["id"],
    )


# Profile fields that are datetime.time and need string (de)serialization for JSON.
_TIME_FIELDS = ("wake_time_local", "sleep_time_local")


def _profile_to_dict(profile: UserProfile) -> dict[str, Any]:
    data = asdict(profile)
    for name in _TIME_FIELDS:
        data[name] = getattr(profile, name).isoformat()
    return data


def _profile_from_dict(data: dict[str, Any]) -> UserProfile:
    # Filter to known fields so schema drift (missing/extra keys) degrades gracefully.
    valid = {f.name for f in fields(UserProfile)}
    kwargs = {k: v for k, v in data.items() if k in valid}
    for name in _TIME_FIELDS:
        raw = kwargs.get(name)
        if isinstance(raw, str):
            kwargs[name] = time.fromisoformat(raw)
    return UserProfile(**kwargs)


class FileStore:
    """Concrete ``Store``: a JSON profile file and a SQLite intake database."""

    def __init__(self, data_dir: Path | str = "data") -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.profile_path = self.data_dir / "profile.json"
        self.db_path = self.data_dir / "intake.sqlite3"
        self._init_db()

    # --- SQLite plumbing ---
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Connection]:
        """A short-lived connection wrapped in a transaction, closed on exit."""
        conn = self._connect()
        try:
            with conn:  # commits on success, rolls back on exception
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._cursor() as conn:
            conn.execute(_SCHEMA)

    # --- profile (JSON) ---
    def load_profile(self) -> UserProfile:
        if not self.profile_path.exists():
            # First run: adopt the machine's local timezone so times display locally.
            return UserProfile(timezone=local_timezone_name())
        with open(self.profile_path, encoding="utf-8") as fh:
            return _profile_from_dict(json.load(fh))

    def save_profile(self, profile: UserProfile) -> None:
        with open(self.profile_path, "w", encoding="utf-8") as fh:
            json.dump(_profile_to_dict(profile), fh, indent=2)

    # --- intake log (SQLite) ---
    def add_intake(self, event: IntakeEvent) -> int:
        with self._cursor() as conn:
            cursor = conn.execute(
                "INSERT INTO intake (timestamp_utc, caffeine_mg, beverage_key, serving_ml, note) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    _to_utc_iso(event.timestamp_utc),
                    event.caffeine_mg,
                    event.beverage_key,
                    event.serving_ml,
                    event.note,
                ),
            )
            new_id = cursor.lastrowid
        if new_id is None:
            raise RuntimeError("INSERT did not return a row id.")
        return new_id

    def get_intakes(self, since: datetime, until: datetime) -> list[IntakeEvent]:
        # Half-open interval [since, until) so day boundaries never double-count.
        with self._cursor() as conn:
            rows = conn.execute(
                "SELECT * FROM intake WHERE timestamp_utc >= ? AND timestamp_utc < ? "
                "ORDER BY timestamp_utc",
                (_to_utc_iso(since), _to_utc_iso(until)),
            ).fetchall()
        return [_row_to_event(row) for row in rows]

    def get_recent_intakes(self, within_h: float, now: datetime) -> list[IntakeEvent]:
        return self.get_intakes(now - timedelta(hours=within_h), now)

    def update_intake(self, event: IntakeEvent) -> None:
        with self._cursor() as conn:
            conn.execute(
                "UPDATE intake SET timestamp_utc = ?, caffeine_mg = ?, beverage_key = ?, "
                "serving_ml = ?, note = ? WHERE id = ?",
                (
                    _to_utc_iso(event.timestamp_utc),
                    event.caffeine_mg,
                    event.beverage_key,
                    event.serving_ml,
                    event.note,
                    event.id,
                ),
            )

    def delete_intake(self, intake_id: int) -> None:
        with self._cursor() as conn:
            conn.execute("DELETE FROM intake WHERE id = ?", (intake_id,))

    def daily_total_mg(self, day_local_date: date, profile: UserProfile) -> float:
        """Total caffeine (mg) consumed on a given local calendar day."""
        tz = ZoneInfo(profile.timezone)
        start_local = datetime.combine(day_local_date, time.min, tzinfo=tz)
        start_utc = start_local.astimezone(timezone.utc)
        end_utc = (start_local + timedelta(days=1)).astimezone(timezone.utc)
        events = self.get_intakes(start_utc, end_utc)
        return sum((event.caffeine_mg for event in events), 0.0)

    def daily_totals_mg(
        self, days: int, end_local_date: date, profile: UserProfile
    ) -> list[tuple[date, float]]:
        """Per-day totals for the ``days`` days ending at ``end_local_date`` (oldest first)."""
        result: list[tuple[date, float]] = []
        for offset in range(days - 1, -1, -1):
            day = end_local_date - timedelta(days=offset)
            result.append((day, self.daily_total_mg(day, profile)))
        return result

    def lifetime_total_mg(self) -> float:
        """Cumulative caffeine (mg) across every logged intake (the exporter's counter)."""
        with self._cursor() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(caffeine_mg), 0.0) AS total FROM intake"
            ).fetchone()
        return float(row["total"])
