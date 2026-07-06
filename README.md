# ☕ Brewmetheus

**Blood-caffeine monitoring, taken far too seriously.**

Brewmetheus is an over-engineered dashboard that models the caffeine
concentration in your bloodstream in real time using a proper pharmacokinetic
model, then reports it with a straight face and a site-reliability aesthetic:
when you will "crash", the golden refill window, whether tonight's residual will
wreck your sleep, and your daily "clarity SLA".

You log what you drank and when; it does the rest.

## Why "Brewmetheus"?

**Brew** + **Prometheus** — and *Prometheus* is pulling triple duty:

- **The monitoring system.** Prometheus is the open-source tool engineers use to
  watch whether a service is up. Brewmetheus watches whether *you* are — hence the
  clarity SLA, the error budget, and the P1 incidents.
- **The Titan who stole fire.** Prometheus gave mortals fire; caffeine is the fire.
  Zeus chained him to a rock and sent an eagle to eat his ever-regrowing **liver**,
  day after day — and caffeine really is cleared by the liver (the CYP1A2 enzyme),
  dose after dose. The myth's grisliest image is just this app's pharmacology.
- **The word itself.** *Prometheus* is Greek for **"forethought"**, which is why the
  app predicts your crash, your refill window, and tonight's residual. His
  lesser-known brother *Epimetheus* — **"afterthought"** — is what an SRE calls a
  postmortem.

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

After `pip install -e .` the `brewmetheus` command launches the dashboard:

```bash
brewmetheus                       # equivalent to: streamlit run app.py
brewmetheus --server.headless=true   # skip the first-run email prompt
```

Extra arguments are forwarded to Streamlit. You can also run it directly with
`streamlit run app.py`.

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

## Scrape your bloodstream (Prometheus)

Brewmetheus is named after a monitoring system. It can also *be* one. A built-in
exporter exposes your caffeine state as real Prometheus metrics, so you can point
actual Prometheus at your bloodstream and graph it in Grafana.

```bash
python -m brewmetheus.exporter              # serves http://127.0.0.1:9110/metrics
python -m brewmetheus.exporter --port 9111  # any extra port you like
```

It binds to localhost by default — your plasma is not a public endpoint. The model is
evaluated at scrape time, so Prometheus samples a live continuous function.

Point Prometheus at it (see `prometheus/prometheus.example.yml`):

```yaml
scrape_configs:
  - job_name: brewmetheus
    static_configs:
      - targets: ["127.0.0.1:9110"]
```

Exposed metrics include `brewmetheus_blood_caffeine_mg_per_litre`,
`brewmetheus_clarity_sla_ratio`, `brewmetheus_error_budget_burn_rate`, a
`brewmetheus_service_status{severity=...}` enum, and the
`brewmetheus_caffeine_intake_mg_total` counter (it resets only on data loss — you
cannot restart your liver). Import `grafana/brewmetheus-dashboard.json` for a ready-made
dashboard, and load `prometheus/brewmetheus.rules.yml` for alerts whose thresholds track
your own settings. Brewmetheus has always been named after a monitoring system; now it
is one.

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
├── postmortem.py   # blameless postmortem (Markdown)
├── metrics.py      # Prometheus text exposition (pure)
├── snapshot.py     # point-in-time service state (shared source of truth)
├── exporter.py     # Prometheus /metrics HTTP adapter + CLI
├── notify.py       # ntfy mobile push + CLI
├── store.py        # JSON profile + SQLite log (behind a Store interface)
└── timeutil.py     # datetime <-> float-hours boundary helpers
app.py              # Streamlit dashboard
grafana/            # importable Grafana dashboard
prometheus/         # example scrape config + alerting rules
tests/              # property + behavior tests
```

The pure core (`pk_model`, `params`, `predict`, `alerts`, `slo`, `render`,
`postmortem`, `metrics`) works in float hours / plain data and never touches datetimes
or I/O; the boundary (`timeutil`, `store`, `snapshot`, `notify`, `exporter`, `app`)
converts timezones, persists data, and talks to the network.

## Development

```bash
ruff format . && ruff check .   # format + lint
mypy brewmetheus                # strict type checking
pytest -q                       # tests
```

## Disclaimers

Brewmetheus is not affiliated with Prometheus the systems monitor, Prometheus the
Titan who stole fire, or your primary care physician. The thresholds are subjective
product knobs, not clinical values. **Not medical advice.**

