"""Tests for the console entry point (no server launch)."""

import sys
import threading
from pathlib import Path

import pytest

from brewmetheus.cli import _APP, _streamlit_command, main
from brewmetheus.store import FileStore


def test_streamlit_command_targets_app() -> None:
    cmd = _streamlit_command(["--server.headless=true"])
    assert cmd[:4] == [sys.executable, "-m", "streamlit", "run"]
    assert cmd[4].endswith("app.py")
    assert cmd[-1] == "--server.headless=true"


def test_app_path_exists() -> None:
    assert _APP.exists()  # app.py is present in the source checkout


def test_main_starts_notify_loop_and_launches_streamlit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    started = threading.Event()

    def fake_run_notify_loop(store: FileStore) -> None:
        started.set()

    monkeypatch.setattr("brewmetheus.cli.FileStore", lambda: FileStore(tmp_path))
    monkeypatch.setattr("brewmetheus.cli.run_notify_loop", fake_run_notify_loop)
    monkeypatch.setattr("brewmetheus.cli.subprocess.call", lambda cmd: 0)
    monkeypatch.setattr(sys, "argv", ["brewmetheus"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert started.wait(timeout=2)  # the notify loop was actually launched
    assert exc_info.value.code == 0
