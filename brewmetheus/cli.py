"""Console entry point: the ``brewmetheus`` command launches the Streamlit app.

Registered via ``[project.scripts]`` in pyproject.toml. It shells out to
``python -m streamlit run app.py`` in the current interpreter, forwarding any
extra arguments (e.g. ``brewmetheus --server.headless=true``), and also starts
the ntfy notify loop in a background thread so mobile push works without a
separate cron/launchd job (see ``notify.run_notify_loop``).
"""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

from brewmetheus.notify import run_notify_loop
from brewmetheus.store import FileStore

_APP = Path(__file__).resolve().parent.parent / "app.py"


def _streamlit_command(extra_args: list[str]) -> list[str]:
    return [sys.executable, "-m", "streamlit", "run", str(_APP), *extra_args]


def main() -> None:
    if not _APP.exists():
        sys.exit(f"Cannot find {_APP}. Launch from a source checkout of Brewmetheus.")
    threading.Thread(target=run_notify_loop, args=(FileStore(),), daemon=True).start()
    raise SystemExit(subprocess.call(_streamlit_command(sys.argv[1:])))
