"""Tests for the ntfy delivery adapter (network-free)."""

import pytest

from brewmetheus.models import Incident, Severity
from brewmetheus.notify import _build_request, notify_incidents, should_notify


def _incident(severity: Severity) -> Incident:
    return Incident(severity, severity.name, f"{severity.name} title", "detail")


def test_build_request_sets_url_and_headers() -> None:
    req = _build_request("mytopic", "Title X", "hello", "high", "coffee", "https://ntfy.sh")
    assert req.full_url == "https://ntfy.sh/mytopic"
    assert req.get_method() == "POST"
    assert req.data == b"hello"
    assert req.get_header("Title") == "Title X"
    assert req.get_header("Priority") == "high"
    assert req.get_header("Tags") == "coffee"


def test_build_request_omits_empty_tags() -> None:
    req = _build_request("t", "T", "m", "default", "", "https://ntfy.sh")
    assert req.get_header("Tags") is None


def test_should_notify_respects_threshold() -> None:
    assert should_notify([_incident(Severity.OK)], Severity.P2) is None
    picked = should_notify([_incident(Severity.OK), _incident(Severity.P1)], Severity.P2)
    assert picked is not None and picked.severity is Severity.P1
    assert should_notify([_incident(Severity.P2)], Severity.P2) is not None  # inclusive


def test_notify_incidents_sends_only_when_warranted(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str, str]] = []

    def fake_send(
        topic: str,
        title: str,
        message: str,
        *,
        priority: str = "default",
        tags: str = "",
        server: str = "https://ntfy.sh",
    ) -> int:
        sent.append((topic, title))
        return 200

    monkeypatch.setattr("brewmetheus.notify.send_ntfy", fake_send)

    assert notify_incidents("t", [_incident(Severity.OK)]) is False
    assert sent == []
    assert notify_incidents("t", [_incident(Severity.P1)]) is True
    assert sent == [("t", "P1 title")]
