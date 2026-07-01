# ☕ Brewmetheus

**Blood-caffeine monitoring, taken far too seriously.**

Brewmetheus is an over-engineered dashboard that models the caffeine
concentration in your bloodstream in real time using a proper pharmacokinetic
model, then reports it with a straight face and a site-reliability aesthetic:
when you will "crash", the golden refill window, whether tonight's residual will
wreck your sleep, and your daily "clarity SLA".

You log what you drank and when; it does the rest.

## Features

- **Live dashboard** — current blood-caffeine concentration, a 24 h projection
  curve, and an auto-refreshing status panel.
- **Personalization** — weight scales the volume of distribution; smoking /
  oral contraceptives / pregnancy scale the elimination half-life.
- **Predictions** — crash time, latest safe refill window, and a pre-sleep
  residual (insomnia) forecast.
- **SRE-style alerting** — P1 "attention service unavailable", P2 "degradation
  imminent", an overload guardrail, and insomnia risk, as colored incidents.
- **Reliability (SLO)** — a daily "clarity SLA", error budget, a P1 incident
  log, and MTTR — your body treated like a production service.
- **History** — a 14-day caffeine trend and 7-day average.
- **Shareable status** — export an SVG badge / status card for a README embed.
- **Mobile push (ntfy)** — optional notifications to your phone.

## The model

A one-compartment pharmacokinetic model with first-order absorption and
elimination (the Bateman function):

```
C(t) = (F · D · ka) / (V · (ka − ke)) · (e^(−ke·t) − e^(−ka·t))
```

Multiple intakes superpose (caffeine follows linear PK). The pure math lives in
`brewmetheus/pk_model.py` and is validated against closed-form oracles (Tmax,
Cmax, AUC).

## Setup

Requires Python 3.10+. Using conda:

```bash
conda create -n brewmetheus python=3.12 -y
conda activate brewmetheus
pip install -e ".[dev]"
```

## Run

```bash
streamlit run app.py
```

On first launch Streamlit may prompt for an email; press Enter to skip, or run
headless to bypass it:

```bash
streamlit run app.py --server.headless=true
```

Then open the printed URL (default http://localhost:8501). Set your weight,
timezone, wake/bed times, and thresholds in the sidebar, and start logging
intakes. Data is stored locally under `data/` (a JSON profile and a SQLite log).

## Mobile push (ntfy)

The dashboard only alerts while its tab is open. For pushes that reach your
phone even when it is closed:

1. Pick a hard-to-guess topic, e.g. `brewmetheus-<something-random>`.
2. Install the [ntfy](https://ntfy.sh) app and subscribe to that topic.
3. Enter the topic in the dashboard sidebar and use **Send test push** to verify.
4. For background alerts, run the notifier on a schedule (cron / macOS launchd):

```bash
python -m brewmetheus.notify              # uses the topic saved in your profile
python -m brewmetheus.notify --topic brewmetheus-xyz --min-severity P1
```

It evaluates your current incidents and pushes the most severe one if it meets
the severity bar.

## Project structure

```
brewmetheus/
├── models.py       # shared dataclasses (the data contracts)
├── beverages.py    # static caffeine reference table
├── params.py       # UserProfile -> PKParams (personalization)
├── pk_model.py     # the pharmacokinetic core (pure numpy)
├── predict.py      # crash time / refill window / sleep forecast
├── alerts.py       # SRE-style incident engine
├── slo.py          # reliability metrics (clarity SLA, MTTR, error budget)
├── render.py       # SVG badge / status card
├── notify.py       # ntfy mobile push + CLI
├── store.py        # JSON profile + SQLite log (behind a Store interface)
└── timeutil.py     # datetime <-> float-hours boundary helpers
app.py              # Streamlit dashboard
tests/              # property + behavior tests
```

The pure core (`pk_model`, `params`, `predict`, `alerts`, `slo`) works in float
hours and never touches datetimes or I/O; the boundary (`timeutil`, `store`,
`app`) converts timezones and persists data.

## Development

```bash
ruff format . && ruff check .   # format + lint
mypy brewmetheus                # strict type checking
pytest -q                       # tests
```

## Status

A weekend-scale toy project — a serious model behind a deliberately absurd
premise. Built for fun and for learning pharmacokinetics.
