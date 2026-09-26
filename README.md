# OrderGuard

A real-time delivery failure prediction and intervention system, built
against a synthetic on-demand delivery marketplace simulation.

**No real company, customer, or order data is used anywhere in this
project.** Every number below — every count, rate, and millisecond — comes
from an actual seeded simulation run, computed by the code in this repo, not
invented for the page. Where something hasn't been measured, it's labeled
"unavailable" rather than guessed.

**Core question:** can we identify deliveries likely to fail before they
fail, determine the probable cause, and select a cost-effective
intervention?

## Table of contents
- [Problem](#problem)
- [Architecture](#architecture)
- [How it works](#how-it-works)
- [Experiment methodology and measured results](#experiment-methodology-and-measured-results)
- [Benchmarks](#benchmarks)
- [Engineering decisions](#engineering-decisions)
- [Running it](#running-it)
- [Deployment](#deployment)
- [Testing](#testing)
- [Honest limitations](#honest-limitations)
- [Repo structure](#repo-structure)

## Problem

On-demand delivery marketplaces (food, groceries, packages) lose money and
customer trust every time a delivery fails outright or arrives so late it
may as well have. Most of that damage is preventable *if* it's caught early
enough — a merchant running behind, a driver who's gone quiet, a customer
who never answers the door are all things a system can notice well before
the order actually fails. The hard part isn't noticing risk; it's deciding
*what to do about it* without spending more on the fix than the failure
would have cost in the first place.

OrderGuard is a small, complete, honestly-scoped answer to that problem: a
synthetic marketplace generates realistic failure conditions, a rules-based
engine scores risk explainably from observable state, an expected-value
model picks a cost-justified response, and an experiment framework proves
(or disproves) that any of it actually helps — on the same seeded
conditions, against two baselines, with the intervention effects fed back
into the simulation so the comparison is real rather than cosmetic.

## Architecture

```
domain/          entities + the order lifecycle state machine (no I/O)
events/          in-process pub/sub event bus (swappable backend)
simulation/      synthetic marketplace generator + tick-based engine
risk/            explainable, weighted-rules risk scoring
interventions/   expected-value intervention selection
experiments/     runs strategies head-to-head, computes comparison metrics
persistence/     SQLAlchemy models + repository (only module that imports SQLAlchemy)
api/             FastAPI routers — thin, no business logic
frontend/        Next.js operations dashboard
```

Dependency direction is one-way: `api → {simulation, risk, interventions,
experiments, persistence} → domain`. Full module boundaries, the domain
model's entity relationships, and the reasoning behind each architectural
choice are in [`docs/architecture.md`](docs/architecture.md).

## How it works

**Simulation** (`simulation/engine.py`): a fixed-tick (1 simulated minute)
discrete-time engine drives a seeded synthetic marketplace — merchants with
prep-time variance and backlog-driven slowdown, drivers with reliability and
speed, customers with reachability — through order arrival, driver
assignment, prep, travel, and a terminal outcome (delivered / failed /
cancelled). Every hazard (driver goes offline, customer unreachable, food
spoils, merchant stockout) is a real probabilistic draw *scaled by the
entity's observable attributes*, so the causal structure is realistic. One
seed always produces one exact sequence of events — verified across
different Python process hash seeds, not just repeated calls in the same
process (a real bug during development: see
[interview-notes.md](docs/interview-notes.md#domain-model--simulation-engine)).

**Risk engine** (`risk/engine.py`): for every delivery, a set of named,
individually-weighted rules — projected lateness, merchant backlog and
reliability, driver wait time and reliability, customer reachability,
perishable overdue — combine into a 0–100 score, a predicted failure type, a
confidence heuristic, and a predicted delay. Every input is something a real
ops dashboard could observe; the engine never reads the simulation's hidden
hazard probabilities. Reacts to domain events on the event bus rather than
polling.

**Intervention engine** (`interventions/engine.py`): a catalog of seven
actions (`DO_NOTHING`, `UPDATE_ETA`, `NOTIFY_CUSTOMER`, `NOTIFY_MERCHANT`,
`MERCHANT_ESCALATION`, `OFFER_CREDIT`, `REASSIGN_DRIVER`), each with a direct
cost and an effect — either a probability-of-failure reduction (levers that
fix the actual cause) or a cost/impact reduction (levers that soften the
blow without changing what happens). Picks whichever candidate — including
doing nothing — minimizes `direct_cost + residual_failure_probability ×
failure_cost`. The chosen intervention's probability reduction is fed back
into the simulation's actual hazard rolls, which is what makes the
experiment comparison below real rather than three sets of numbers that
happen to differ only in bookkeeping.

Full design rationale, weight tables, and the algorithms' complexity/
tradeoffs are in [`docs/interview-notes.md`](docs/interview-notes.md).

## Experiment methodology and measured results

`experiments/runner.py` runs the *same* `SimulationConfig` through three
strategies:

- **`no_intervention`** — bare simulation, no risk or intervention engine.
- **`threshold_based`** — a naive fixed policy: any order crossing a fixed
  risk-score threshold gets the same single action, same cost, same effect
  size, regardless of predicted cause. The "what an ops team might ship in
  a week" baseline.
- **`expected_value`** — OrderGuard's actual engine: cost-aware, cause-
  specific selection from the full catalog.

All three start from an identical seeded population. They are **not**
expected to produce identical outcomes beyond that starting point: the
moment a strategy prevents a hazard, that order keeps consuming random
draws in later ticks that it wouldn't have otherwise, which shifts
alignment for every subsequent draw. That's the real counterfactual
divergence the comparison exists to surface — a frozen-outcome comparison
would prove nothing.

**One real run** (seed 5, 720 simulated minutes, 25 merchants / 45 drivers /
400 customers, a rush-hour window from minute 60–240; reproduce with
`docker compose up` then `POST /simulations` with this config — see
[Running it](#running-it)):

| strategy | orders | delivered | failed | cancelled | late rate | interventions | cost |
|---|---|---|---|---|---|---|---|
| no_intervention | 1,012 | 856 | 4 | 123 | 2.22% | 0 | $0.00 |
| threshold_based | 1,012 | 856 | 4 | 123 | 2.22% | 13 | $13.00 |
| expected_value | 1,028 | 892 | 4 | 113 | 2.02% | 85 | $20.60 |

What this one run actually shows: the naive threshold policy spent $13 and
changed **nothing** — every risky order it flagged would have had the same
outcome regardless, because a fixed action applied without regard to cause
doesn't fix a cause. The expected-value engine, spending $20.60 (65 cents
more, not 65% more — it intervened on far more orders at much lower cost
each), reduced `no_driver_available` cancellations from 121 to 111 and
improved the late rate — a real, measured, modest win, not a dramatic one.

**This is one seeded run, not a proof that intervening always helps.** A
different, driver-supply-constrained scenario tested during development
showed the opposite risk: extending an at-risk order's patience for a
driver doesn't create more drivers, and can shift which orders fail rather
than reduce the total. Both findings are true and both are documented in
[`docs/interview-notes.md`](docs/interview-notes.md#experiment-framework) —
a rigorous version of this comparison would run many seeds per
configuration and report a distribution, not a point estimate. That's a
named limitation below, not something to paper over with a cherry-picked
seed and a confident headline.

## Benchmarks

Real measurements on a local dev machine (Apple Silicon, local Postgres) —
not portable guarantees. Full baseline → bottleneck → fix → result writeups,
including two real correctness bugs the benchmarking process itself
surfaced, are in
[`docs/interview-notes.md`](docs/interview-notes.md#benchmarks). Headlines:

- **Simulation throughput** collapsed from ~24-29K orders/sec at 1K–10K
  orders to ~2K orders/sec at 100K — a red flag for a tick-based engine that
  should scale flat. `cProfile` found 92% of runtime in one function
  (`_nearest_available_driver`) re-scanning every driver on every
  assignment attempt (~1.2 billion calls at 100K scale). Fixing it to
  maintain an incrementally-updated available-drivers set gave a **12.5x**
  speedup at 100K orders, and throughput is now flat across two orders of
  magnitude.
- **`GET .../high-risk`** took ~1.8s on a 5K-order run — it was
  eager-loading *every* historical risk assessment for *every* order just
  to pick the newest one in Python. A `ROW_NUMBER()` window-function query
  gave an **8.2x** speedup (218ms).
- The same benchmarking pass found two real correctness bugs no unit test
  had caught (ID collisions across simulation runs, and an order-lookup
  endpoint that became ambiguous once that was fixed) — see the writeup for
  why unit tests, by construction, didn't catch either.

## Engineering decisions

- **Rules before ML.** A rules engine forces every risk factor to be named
  and weighted, which is exactly what an honest README (and an interview
  conversation) needs, and it gives a measured baseline an ML model would
  need to beat later — you can't know if added complexity earned its keep
  until you've measured what simple rules already get you.
- **No Kafka/Redis yet.** The event bus is a `Protocol`, so a broker-backed
  implementation later is a new class, not a rewrite — deferring costs
  nothing architecturally, and adding one now would be infrastructure with
  no evidence it's needed.
- **PostgreSQL, not SQLite.** Real foreign-key relationships and ad-hoc
  analytical queries (percentile delays, experiment comparisons) are a
  textbook relational fit; this project is meant to demonstrate
  production-shaped decisions, not the path of least local-setup friction.
- **Tick-based simulation, not an event-priority-queue engine.** Simplest
  correct implementation first — easier to reason about and test, and cheap
  enough at this project's scale (confirmed by benchmarking, not assumed).
- **Composite `(simulation_run_id, id)` keys, not bare generated IDs.**
  Found the hard way (see Benchmarks) — a lesson worth generalizing:
  generated IDs that are only unique *within a scope* will eventually
  collide once more than one instance of that scope exists.

## Running it

```bash
docker compose up
```

Brings up Postgres, runs migrations automatically, and starts the API
(`:8000`, OpenAPI docs at `/docs`) and the dashboard (`:3000`). Verified
end-to-end in this repo's own development (build → up → real API call →
tear down), not just written and assumed to work.

To run a simulation from the API directly:

```bash
curl -X POST http://localhost:8000/simulations \
  -H "Content-Type: application/json" \
  -d '{"config": {"seed": 5, "start_time": "2026-01-01T08:00:00", "duration_minutes": 720, "num_merchants": 25, "num_drivers": 45, "num_customers": 400, "base_order_rate_per_minute": 1.2, "map_size_km": 12.0}, "threshold": 45.0}'
```

Or use the Simulation Lab page in the dashboard.

### Local development (without Docker)

```bash
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
createdb orderguard_dev
.venv/bin/alembic upgrade head
ORDERGUARD_DATABASE_URL=postgresql+psycopg://localhost:5432/orderguard_dev \
  .venv/bin/python -m uvicorn orderguard.api.app:app --app-dir src --reload

cd frontend
npm install && npm run dev
```

## Deployment

OrderGuard has no authentication layer by design (it's a public portfolio
demo, not a real product), so the hardening below is scoped to that: bound
the one genuinely expensive endpoint, rate-limit it, and lock CORS down to
known origins instead of `*`.

**Backend — environment variables** (`backend/.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `ORDERGUARD_DATABASE_URL` | `postgresql+psycopg://localhost:5432/orderguard_dev` | SQLAlchemy connection string. Set to your real Postgres instance in production. |
| `ORDERGUARD_ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated CORS allow-list. Add the deployed frontend's real origin (e.g. `https://orderguard.vercel.app`); never `*`. |
| `ORDERGUARD_DEBUG` | `false` | Must stay `false` on anything internet-reachable — `true` returns exception tracebacks in API responses. |
| `ORDERGUARD_RATE_LIMIT_MAX_REQUESTS` | `20` | Per-client-IP request budget for `POST /simulations` (the only endpoint that runs real simulation work — three full passes per request). |
| `ORDERGUARD_RATE_LIMIT_WINDOW_SECONDS` | `60` | Sliding window the budget above applies to. |

`SimulationConfigIn` also caps every size/rate field server-side
(`duration_minutes<=1440`, `num_customers<=2000`, `num_drivers<=300`,
`num_merchants<=100`, `base_order_rate_per_minute<=5`, rush-hour
`demand_multiplier<=5`, etc. — see `api/schemas.py`), so a request can't
force an arbitrarily long-running simulation regardless of rate limiting.
All limits sit well above every value the demo, guided tour, and Simulation
Lab UI actually use.

**Frontend — environment variables** (`frontend/.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Base URL the browser calls. Inlined into the client bundle at build time, so it must be set correctly *before* building/deploying, not just at runtime. Set to your deployed backend's public URL. |

**Production start commands** (what each Dockerfile actually runs):

```bash
# Backend (from backend/, with the env vars above set)
alembic upgrade head && uvicorn orderguard.api.app:app --host 0.0.0.0 --port 8000

# Frontend (standalone Next.js build)
npm run build
node .next/standalone/server.js
```

Deploying the frontend to Vercel instead of Docker: Vercel runs its own
build/start, so only `NEXT_PUBLIC_API_URL` needs to be set as a project
environment variable (build-time, not preview-only, since it's inlined).
Whatever origin Vercel assigns that deployment must then be added to the
backend's `ORDERGUARD_ALLOWED_ORIGINS`.

Rate limiting is an in-memory, single-process sliding window (see
`api/rate_limit.py`) — correct and sufficient for one backend instance, but
each replica would track its own counters if this ever ran horizontally
scaled; that would need a shared store (e.g. Redis) instead.

## Testing

119 backend tests (`cd backend && pytest`) covering domain lifecycle
transitions, the event bus, risk scoring, intervention selection, the
experiment framework (including a scenario-specific test that proves
interventions have a *measured* causal effect on outcomes, not just
recorded ones), persistence (against a real Postgres test database, not
mocks), the API (via `TestClient` against real Postgres) including its
config-size limits and per-IP rate limit, and concurrent request handling.
Frontend: `tsc --noEmit`, `eslint`, `next build` all pass clean.

CI (`.github/workflows/ci.yml`) runs the same lint/test/build steps on every
push and PR — every individual command in it has been run and verified
locally in this repo's own development; the workflow itself hasn't yet
executed on GitHub's infrastructure, since this repo has no GitHub remote
configured yet.

## Honest limitations

- **Event-reactive risk has a real gap.** Risk is recomputed when an event
  fires for an order, not continuously — an order sitting untouched between
  two events (e.g. still waiting for a driver) doesn't get its risk score
  updated in that gap. Deliberate: "react to events, don't poll" was a
  stated requirement, and this is its consequence, not an oversight.
- **Single-seed experiment comparisons are one sample path.** See
  [Measured results](#experiment-methodology-and-measured-results) above.
- **Intervention cost/effect numbers are documented assumptions, not
  learned from data.** There's no real marketplace to learn them from; a
  production system would.
- **No WebSocket live push.** The dashboard polls every 20 seconds. Named in
  [`ROADMAP.md`](ROADMAP.md) as the next highest-value addition after this
  MVP.
- **No ML risk model.** By design, for now — see Engineering decisions.
- **`POST /simulations` (~1.6s for a 1K-order, three-strategy experiment)
  was not optimized** — nothing measured points at it being disproportionate
  yet; noted rather than assumed fine.
- Explicitly out of scope until this MVP is solid and deployed: Kafka/Redis
  Streams, service decomposition, marketplace-wide bipartite-graph
  intervention optimization, Prometheus/Grafana, AWS-specific deployment,
  chaos/load testing.

## Repo structure

```
backend/     Python 3.12 / FastAPI / SQLAlchemy / Alembic
frontend/    Next.js / React / TypeScript (marketplace map is plain SVG, not a map library)
docs/
  architecture.md       module boundaries, domain model, design rationale
  interview-notes.md    component-by-component deep dive, maintained continuously
ROADMAP.md   milestone-by-milestone build status
```
