"""A minimal Prometheus exporter for the caffeine service.

The notify.py of scraping: a stdlib HTTP adapter (no dependencies) serving the output of
``metrics.render_metrics`` at ``GET /metrics``. The model is evaluated at scrape time, so
Prometheus samples a live continuous function. Bound to localhost by default -- your
plasma is not a public endpoint.

    python -m brewmetheus.exporter --host 127.0.0.1 --port 9110
"""

from __future__ import annotations

import argparse
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import cast

from brewmetheus.metrics import CONTENT_TYPE, render_metrics
from brewmetheus.snapshot import build_snapshot
from brewmetheus.store import FileStore, Store

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 9110

_INDEX = (
    "<!doctype html><title>Brewmetheus exporter</title>"
    "<h1>Brewmetheus exporter</h1>"
    "<p>Your bloodstream, as Prometheus metrics: <a href='/metrics'>/metrics</a>.</p>"
)
_TEAPOT = "I'm a teapot. This service brews caffeine metrics, not tea. (RFC 2324)\n"


def handle(path: str, store: Store) -> tuple[int, str, str]:
    """Route a GET path to (status, content_type, body). The only I/O is build_snapshot."""
    if path == "/metrics":
        return 200, CONTENT_TYPE, render_metrics(build_snapshot(store))
    if path == "/":
        return 200, "text/html; charset=utf-8", _INDEX
    if path == "/brew":  # undocumented; a reward for the curious
        return 418, "text/plain; charset=utf-8", _TEAPOT
    return 404, "text/plain; charset=utf-8", "Not found. Try /metrics.\n"


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's API
        path = self.path.split("?", 1)[0]
        store = cast("_ExporterServer", self.server).store
        try:
            status, content_type, body = handle(path, store)
        except Exception as exc:  # a single bad scrape must not kill the exporter
            status, content_type = 500, "text/plain; charset=utf-8"
            body = f"# scrape failed: {exc}\n"
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        # Quiet by default; an access log would drown the notifier's output.
        pass


class _ExporterServer(HTTPServer):
    def __init__(self, address: tuple[str, int], store: Store) -> None:
        super().__init__(address, _Handler)
        self.store = store


def serve(store: Store, host: str = _DEFAULT_HOST, port: int = _DEFAULT_PORT) -> None:
    """Serve /metrics forever (blocking)."""
    server = _ExporterServer((host, port), store)
    print(
        f"[brewmetheus.exporter] scraping your bloodstream at http://{host}:{port}/metrics",
        file=sys.stderr,
    )
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve caffeine metrics for Prometheus.")
    parser.add_argument("--host", default=_DEFAULT_HOST, help="Bind host (default localhost).")
    parser.add_argument("--port", type=int, default=_DEFAULT_PORT, help="Bind port.")
    args = parser.parse_args()
    serve(FileStore(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
