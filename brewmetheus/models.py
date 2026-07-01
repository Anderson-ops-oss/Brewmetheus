# data models shared across the Brewmetheus package.


from __future__ import annotations  # I am the future :)

from dataclasses import dataclass
from datetime import datetime, time
from enum import IntEnum

# Default parameter values
DEFAULT_BASE_HALF_LIFE_H = 5.0  # typical healthy adult
DEFAULT_KA_PER_H = 6.0  # chosen so Tmax ~= 40 min
DEFAULT_BIOAVAILABILITY = 1.0  # caffeine is nearly fully absorbed
DEFAULT_VD_PER_KG = 0.5  # apparent volume of distribution, L/kg
DEFAULT_WEIGHT_KG = 70.0  # typical healthy adult
DEFAULT_AWAKE_THRESHOLD_MG_L = 1.5  # subjective product knob, not medical
DEFAULT_INSOMNIA_THRESHOLD_MG_L = 2.0  # subjective product knob, not medical
DEFAULT_DAILY_CAP_MG = 400.0  # common adult advised ceiling
DEFAULT_CLARITY_SLA_TARGET = 0.9  # SRE-meme uptime target for the waking window


@dataclass
class IntakeEvent:
    """A single caffeine intake; one row in the SQLite log.
    ``caffeine_mg`` is authoritative: it stores the resolved dose used by the
    model. Do not recompute it from ``beverage_key`` at read time, or historical
    curves would shift retroactively when the beverage table changes.
    """

    timestamp_utc: datetime  # tz-aware, UTC
    caffeine_mg: float  # authoritative dose used by the model
    beverage_key: str | None = None  # key into the beverage table; None if custom
    serving_ml: float | None = None
    note: str | None = None
    id: int = 0  # SQLite rowid; 0 == unsaved (store assigns on add)


@dataclass
class UserProfile:
    """The single user's configuration (persisted as JSON).
    All fields carry defaults so a first-run profile is fully constructible.
    """

    # physiology
    weight_kg: float = DEFAULT_WEIGHT_KG
    smoker: bool = False
    oral_contraceptives: bool = False
    pregnant: bool = False
    base_half_life_h: float = DEFAULT_BASE_HALF_LIFE_H
    # model baseline
    ka_per_h: float = DEFAULT_KA_PER_H
    bioavailability: float = DEFAULT_BIOAVAILABILITY
    vd_per_kg: float = DEFAULT_VD_PER_KG
    # thresholds and schedule
    awake_threshold_mg_l: float = DEFAULT_AWAKE_THRESHOLD_MG_L
    sleep_insomnia_threshold_mg_l: float = DEFAULT_INSOMNIA_THRESHOLD_MG_L
    safe_ceiling_mg_l: float | None = None
    daily_cap_mg: float = DEFAULT_DAILY_CAP_MG
    clarity_sla_target: float = DEFAULT_CLARITY_SLA_TARGET  # SLO target for the waking window
    wake_time_local: time = time(7, 0)
    sleep_time_local: time = time(23, 30)
    timezone: str = "UTC"  # IANA name, e.g. "Asia/Hong_Kong"
    # notifications
    ntfy_topic: str | None = None  # ntfy.sh topic for mobile push; None disables


@dataclass
class PKParams:
    """Model-ready parameters; the output of ``params.derive_params``.
    This is all ``pk_model`` consumes; it knows nothing about weight or lifestyle.
    """

    F: float
    V_l: float
    ka_per_h: float
    ke_per_h: float
    effective_half_life_h: float  # carried for display


class Severity(IntEnum):
    """Incident severity, ordered by escalation so ``max()`` picks the worst."""

    OK = 0
    P2 = 1
    P1 = 2
    OVERLOAD = 3


@dataclass
class Incident:
    """One alert produced by the SRE-style incident engine."""

    severity: Severity
    code: str  # e.g. "ATTENTION_UNAVAILABLE"
    title: str  # meme-facing message
    detail: str
    at_h: float = 0.0  # offset hours when it triggers / is predicted


@dataclass
class RefillSuggestion:
    """Result of the refill-window computation."""

    feasible: bool
    dose_mg: float
    projected_bedtime_residual_mg_l: float
    projected_daily_total_mg: float
    at_h: float | None = None  # latest safe top-up offset (if feasible)
    blocked_by: str | None = None  # "DAILY_CAP" | "SLEEP" | "NO_CRASH_COMING"


@dataclass
class SleepForecast:
    """Pre-sleep residual forecast."""

    residual_mg_l: float
    insomnia_risk: bool
    sleep_h: float


@dataclass
class CrashInterval:
    """A contiguous stretch below the awake threshold -- one "P1 incident"."""

    start_h: float
    end_h: float

    @property
    def duration_h(self) -> float:
        return self.end_h - self.start_h


@dataclass
class SLOReport:
    """SRE-style reliability metrics over one waking window (all float hours)."""

    waking_h: float
    uptime_ratio: float  # 0..1: fraction of the waking window above the awake threshold
    downtime_h: float
    crashes: list[CrashInterval]
    incident_count: int
    mttr_h: float | None  # mean time to recovery (mean crash duration); None if no crashes
    mtbf_h: float | None  # mean time between failures (mean uptime gap); None if < 2 crashes
    error_budget_h: float  # allowed downtime = (1 - sla_target) * waking_h
    budget_remaining_h: float  # error_budget_h - downtime_h (negative == over budget)
    avg_mg_l: float
    sla_target: float
    sla_met: bool
