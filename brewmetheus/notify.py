"""Mobile push via ntfy.sh (feature #5): deliver incidents to your phone.

The alert engine (``alerts.evaluate_incidents``) is pure and unchanged; this is
just the delivery adapter plus a CLI you can run on a schedule (cron / launchd)
so alerts reach you even when the dashboard tab is closed.

Usage:
    1. Pick a hard-to-guess topic, e.g. "brewmetheus-<something-random>".
    2. Install the ntfy app on your phone and subscribe to that topic.
    3. Set the topic in the dashboard sidebar (it is saved to the profile), then:
         python -m brewmetheus.notify
       or override the topic explicitly:
         python -m brewmetheus.notify --topic brewmetheus-xyz
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from brewmetheus.alerts import evaluate_incidents, primary_incident
from brewmetheus.models import Incident, Severity
from brewmetheus.params import derive_params
from brewmetheus.store import FileStore
from brewmetheus.timeutil import resolve_sleep_offset, to_offsets

_DEFAULT_SERVER = "https://ntfy.sh"
_MODEL_WINDOW_H = 48.0
_DEFAULT_LOOP_INTERVAL_S = 180.0  # 3 min; under the "must notice within 5 min" target

# ntfy (priority, emoji tag) per severity.
_SEVERITY_META: dict[Severity, tuple[str, str]] = {
    Severity.OVERLOAD: ("urgent", "warning"),
    Severity.P1: ("high", "rotating_light"),
    Severity.P2: ("default", "coffee"),
    Severity.OK: ("low", "white_check_mark"),
}


def _build_request(
    topic: str, title: str, message: str, priority: str, tags: str, server: str
) -> urllib.request.Request:
    """Construct the ntfy POST request (pure; no network)."""
    url = f"{server.rstrip('/')}/{topic}"
    request = urllib.request.Request(url, data=message.encode("utf-8"), method="POST")
    request.add_header("Title", title)
    request.add_header("Priority", priority)
    if tags:
        request.add_header("Tags", tags)
    return request


def send_ntfy(
    topic: str,
    title: str,
    message: str,
    *,
    priority: str = "default",
    tags: str = "",
    server: str = _DEFAULT_SERVER,
) -> int:
    """POST a notification to an ntfy topic; returns the HTTP status code."""
    request = _build_request(topic, title, message, priority, tags, server)
    with urllib.request.urlopen(request, timeout=10) as response:
        return int(response.status)


def should_notify(incidents: list[Incident], min_severity: Severity) -> Incident | None:
    """The incident worth pushing (the primary one, if at/above ``min_severity``)."""
    primary = primary_incident(incidents)
    return primary if primary.severity >= min_severity else None


def should_notify_on_change(
    current_severity: Severity, last_severity: Severity | None, min_severity: Severity
) -> bool:
    """True if the severity changed and either side is at/above ``min_severity``."""
    return current_severity != last_severity and (
        current_severity >= min_severity
        or (last_severity is not None and last_severity >= min_severity)
    )


def _push_incident(topic: str, incident: Incident, server: str) -> None:
    priority, tags = _SEVERITY_META.get(incident.severity, ("default", ""))
    send_ntfy(topic, incident.title, incident.detail, priority=priority, tags=tags, server=server)


def notify_incidents(
    topic: str,
    incidents: list[Incident],
    *,
    min_severity: Severity = Severity.P2,
    server: str = _DEFAULT_SERVER,
) -> bool:
    """Push the primary incident if it meets the severity bar; returns whether sent."""
    incident = should_notify(incidents, min_severity)
    if incident is None:
        return False
    _push_incident(topic, incident, server)
    return True


def _current_incidents(store: FileStore) -> list[Incident]:
    """Evaluate incidents for right now (the same boundary wiring the app uses)."""
    profile = store.load_profile()
    now = datetime.now(timezone.utc)
    intakes = to_offsets(store.get_recent_intakes(within_h=_MODEL_WINDOW_H, now=now), reference=now)
    params = derive_params(profile)
    sleep_h = resolve_sleep_offset(profile.sleep_time_local, profile.timezone, now)
    today = now.astimezone(ZoneInfo(profile.timezone)).date()
    daily_total = store.daily_total_mg(today, profile)
    return evaluate_incidents(intakes, params, profile, sleep_h, current_daily_total_mg=daily_total)


def run_notify_loop(
    store: FileStore,
    *,
    interval_s: float = _DEFAULT_LOOP_INTERVAL_S,
    min_severity: Severity = Severity.P2,
    server: str = _DEFAULT_SERVER,
) -> None:
    """Poll forever, pushing only on a severity change (escalation or recovery).

    Meant to run alongside the dashboard (see ``cli.main``), not as a
    replacement for the one-shot ``main`` below, which stays for cron/launchd.
    """
    last_severity: Severity | None = None
    while True:
        try:
            topic = store.load_profile().ntfy_topic
            if topic:
                primary = primary_incident(_current_incidents(store))
                if should_notify_on_change(primary.severity, last_severity, min_severity):
                    _push_incident(topic, primary, server)
                last_severity = primary.severity
        except Exception as exc:  # a single failed poll must not kill the loop
            print(f"[brewmetheus.notify] poll failed: {exc}", file=sys.stderr)
        time.sleep(interval_s)


def main() -> None:
    parser = argparse.ArgumentParser(description="Push current caffeine incidents to ntfy.")
    parser.add_argument("--topic", default=None, help="ntfy topic (overrides the profile).")
    parser.add_argument("--server", default=_DEFAULT_SERVER, help="ntfy server base URL.")
    parser.add_argument(
        "--min-severity",
        default="P2",
        choices=[s.name for s in Severity],
        help="Only push at or above this severity.",
    )
    args = parser.parse_args()

    store = FileStore()
    topic = args.topic or store.load_profile().ntfy_topic
    if not topic:
        parser.error("No ntfy topic set. Use --topic or set one in the dashboard sidebar.")

    incidents = _current_incidents(store)
    sent = notify_incidents(
        topic, incidents, min_severity=Severity[args.min_severity], server=args.server
    )
    primary = primary_incident(incidents)
    print(f"[{primary.severity.name}] {primary.title} -> {'sent' if sent else 'no push'}")


if __name__ == "__main__":
    main()
