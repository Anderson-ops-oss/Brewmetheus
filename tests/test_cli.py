"""Tests for the console entry point (no server launch)."""

import sys

from brewmetheus.cli import _APP, _streamlit_command


def test_streamlit_command_targets_app() -> None:
    cmd = _streamlit_command(["--server.headless=true"])
    assert cmd[:4] == [sys.executable, "-m", "streamlit", "run"]
    assert cmd[4].endswith("app.py")
    assert cmd[-1] == "--server.headless=true"


def test_app_path_exists() -> None:
    assert _APP.exists()  # app.py is present in the source checkout
