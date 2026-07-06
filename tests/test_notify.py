"""Tests for the ntfy delivery adapter (network-free)."""

from pathlib import Path

import pytest

from brewmetheus.models import Incident, Severity
from brewmetheus.notify import (
    _build_request,
    notify_incidents,
    run_notify_loop,
    should_notify,
    should_notify_on_change,
)
from brewmetheus.store import FileStore


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


@pytest.mark.parametrize(
    ("last_severity", "current_severity", "expected"),
    [
        (None, Severity.OK, False),  # nothing observed yet; don't alert on startup
        (None, Severity.P1, True),  # first-ever alert
        (Severity.OK, Severity.P2, True),  # escalation, crosses the bar
        (Severity.P2, Severity.P1, True),  # escalation, still above bar
        (Severity.OVERLOAD, Severity.P1, True),  # de-escalation, still above bar
        (Severity.P1, Severity.OK, True),  # full recovery, drops below the bar
        (Severity.OK, Severity.OK, False),  # no change
        (Severity.P2, Severity.P2, False),  # no change; this is what stops the repeat spam
    ],
)
def test_should_notify_on_change(
    last_severity: Severity | None, current_severity: Severity, expected: bool
) -> None:
    assert should_notify_on_change(current_severity, last_severity, Severity.P2) is expected


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


def test_run_notify_loop_pushes_only_on_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store = FileStore(tmp_path)
    profile = store.load_profile()
    profile.ntfy_topic = "t"
    store.save_profile(profile)

    severities = iter([Severity.OK, Severity.P1, Severity.P1, Severity.OK])
    sent: list[str] = []
    sleep_calls = 0

    def fake_current_incidents(_store: FileStore) -> list[Incident]:
        return [_incident(next(severities))]

    def fake_send(
        topic: str,
        title: str,
        message: str,
        *,
        priority: str = "default",
        tags: str = "",
        server: str = "https://ntfy.sh",
    ) -> int:
        sent.append(title)
        return 200

    def fake_sleep(_interval_s: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls >= 4:
            raise StopIteration  # unwind the infinite loop after 4 polls

    monkeypatch.setattr("brewmetheus.notify._current_incidents", fake_current_incidents)
    monkeypatch.setattr("brewmetheus.notify.send_ntfy", fake_send)
    monkeypatch.setattr("brewmetheus.notify.time.sleep", fake_sleep)

    with pytest.raises(StopIteration):
        run_notify_loop(store, min_severity=Severity.P2)

    # poll 1: OK from an unknown baseline -> no push. poll 2: escalates to P1 -> push.
    # poll 3: still P1, unchanged -> no push (the dedup). poll 4: recovers to OK -> push.
    assert sent == ["P1 title", "OK title"]
