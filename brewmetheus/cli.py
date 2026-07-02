"""Console entry point: the ``brewmetheus`` command launches the Streamlit app.

Registered via ``[project.scripts]`` in pyproject.toml. It shells out to
``python -m streamlit run app.py`` in the current interpreter, forwarding any
extra arguments (e.g. ``brewmetheus --server.headless=true``).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_APP = Path(__file__).resolve().parent.parent / "app.py"


def _streamlit_command(extra_args: list[str]) -> list[str]:
    return [sys.executable, "-m", "streamlit", "run", str(_APP), *extra_args]


def main() -> None:
    if not _APP.exists():
        sys.exit(f"Cannot find {_APP}. Launch from a source checkout of Brewmetheus.")
    raise SystemExit(subprocess.call(_streamlit_command(sys.argv[1:])))
