"""Tests for build_snapshot (the shared exporter/notifier data source)."""

from datetime import datetime, timezone
from pathlib import Path

from brewmetheus.models import IntakeEvent, Severity
from brewmetheus.snapshot import build_snapshot
from brewmetheus.store import FileStore


def test_cold_start_snapshot_is_p1(tmp_path: Path) -> None:
    snap = build_snapshot(FileStore(tmp_path))
    assert snap.severity is Severity.P1  # no caffeine -> attention unavailable
    assert snap.blood_caffeine_mg_l == 0.0
    assert snap.lifetime_intake_mg == 0.0


def test_lifetime_counter_sums_every_intake(tmp_path: Path) -> None:
    store = FileStore(tmp_path)
    store.add_intake(IntakeEvent(timestamp_utc=datetime.now(timezone.utc), caffeine_mg=95.0))
    store.add_intake(IntakeEvent(timestamp_utc=datetime.now(timezone.utc), caffeine_mg=63.0))
    assert build_snapshot(store).lifetime_intake_mg == 158.0


def test_snapshot_primary_is_consistent_with_its_incidents(tmp_path: Path) -> None:
    store = FileStore(tmp_path)
    store.add_intake(IntakeEvent(timestamp_utc=datetime.now(timezone.utc), caffeine_mg=150.0))
    snap = build_snapshot(store)
    assert snap.incident_code in {inc.code for inc in snap.incidents}
    assert snap.severity == max(inc.severity for inc in snap.incidents)
