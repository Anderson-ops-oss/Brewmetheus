"""Tests for the exporter's request routing (no sockets opened)."""

from datetime import datetime, timezone
from pathlib import Path

from brewmetheus.exporter import handle
from brewmetheus.models import IntakeEvent
from brewmetheus.store import FileStore


def test_metrics_endpoint_ok(tmp_path: Path) -> None:
    status, content_type, body = handle("/metrics", FileStore(tmp_path))
    assert status == 200
    assert "version=0.0.4" in content_type
    assert "brewmetheus_blood_caffeine_mg_per_litre" in body
    assert "brewmetheus_build_info" in body


def test_index_points_to_metrics(tmp_path: Path) -> None:
    status, content_type, body = handle("/", FileStore(tmp_path))
    assert status == 200
    assert "text/html" in content_type
    assert "/metrics" in body


def test_brew_is_a_teapot(tmp_path: Path) -> None:
    status, _content_type, body = handle("/brew", FileStore(tmp_path))
    assert status == 418
    assert "teapot" in body.lower()


def test_unknown_path_is_404(tmp_path: Path) -> None:
    status, _content_type, _body = handle("/nope", FileStore(tmp_path))
    assert status == 404


def test_metrics_reflect_a_logged_intake(tmp_path: Path) -> None:
    store = FileStore(tmp_path)
    store.add_intake(IntakeEvent(timestamp_utc=datetime.now(timezone.utc), caffeine_mg=95.0))
    _status, _content_type, body = handle("/metrics", store)
    assert "brewmetheus_caffeine_intake_mg_total 95.0" in body
