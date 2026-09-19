# OrderGuard Roadmap

This tracks the actual build order. It is a working document, not a promise —
update it as milestones complete or scope shifts. Status reflects the real
state of the repo, checked against tests, not intent.

Legend: `[ ]` not started · `[~]` in progress · `[x]` done and tested

## Milestone 1 — Repo + Simulation Engine
- [x] Repo scaffolding, `.gitignore`, roadmap, architecture doc
- [x] Domain model: `Merchant`, `Driver`, `Customer`, `Order`, `Delivery`, `DeliveryEvent`
- [x] Order lifecycle state machine (created → confirmed → assigned → en route →
      arrived → picked up → delivered, + cancel/fail branches)
- [x] Driver state machine (available / en route / waiting / delivering / offline)
- [x] Environment factors: time of day (rush-hour windows), demand curve, traffic/congestion
- [x] Deterministic seeded randomness (same seed ⇒ same simulation run — verified
      by test and by manual two-run comparison)
- [x] Config-driven marketplace generation (merchant count, driver count, demand
      profile, etc. — no magic numbers baked into code)
- [x] Scales from 100 → 100,000 deliveries — sanity-checked manually (~20K orders /
      147K events in ~9s); full benchmark with baseline/bottleneck analysis is
      still Milestone 8's job, not done here
- [x] Unit tests for domain model + lifecycle transitions (59 tests passing:
      `tests/test_domain.py`, `tests/test_simulation.py`)

## Milestone 2 — Event System
- [x] In-process event bus (publish/subscribe), swappable backend interface
      (`EventBus` protocol + `InProcessEventBus`)
- [x] Simulation engine emits domain events on every state change (wired via
      optional `event_bus` param)
- [x] Risk engine (Milestone 3) subscribes/reacts instead of polling
- [x] Tests: subscriber isolation, wildcard + specific-type dispatch, no
      dropped events (`tests/test_events.py`)

## Milestone 3 — Rules-Based Risk Engine
- [x] Per-delivery: overall risk score (0–100), predicted failure type,
      confidence, predicted delay
- [x] Explainable contributing factors with weighted contributions
      (`RiskFactor` list on every `RiskAssessment`)
- [x] All inputs derived from observable simulation state — nothing randomly
      assigned (risk engine never reads the simulation's hidden hazard rolls)
- [x] Thresholds/weights configurable via `RiskEngine.__init__` kwargs, not
      hardcoded in rule bodies
- [x] Tests: known scenarios produce known risk bands + full-run integration
      against a live simulation (`tests/test_risk.py`)
- Known limitation (documented, not fixed): purely event-reactive, so risk
  for an order sitting untouched between two events isn't updated until the
  next event fires. Acceptable for v1; revisit if the dashboard needs
  continuous risk decay/growth between events.

## Milestone 4 — Intervention Engine
- [x] Intervention catalog: `DO_NOTHING`, `UPDATE_ETA`, `NOTIFY_CUSTOMER`,
      `NOTIFY_MERCHANT`, `MERCHANT_ESCALATION`, `OFFER_CREDIT`,
      `REASSIGN_DRIVER` — each with cost + applicability conditions
- [x] Expected-value selection model: cost(intervention) + residual
      P(failure) × cost(failure), compared against `DO_NOTHING`'s baseline
- [x] Tests: selection is deterministic given identical risk state, expected
      savings vs. `DO_NOTHING` never negative, full-run integration
      (`tests/test_interventions.py`)

## Milestone 5 — Experiment Framework
- [x] Strategies compared on identical seeded conditions: no intervention,
      threshold-based, OrderGuard expected-value (`experiments/runner.py`)
- [x] Real metrics collected: late rate, cancellation rate, avg delay, P50/P95
      delay, intervention rate, intervention cost, failure/success counts
- [x] Results reproducible given the same config (verified by test); a fresh
      `SimulationEngine` per strategy re-seeds from `config.seed`, so all
      three start from identical conditions and diverge only once an
      intervention actually changes an outcome
- [x] Intervention effects are now causally wired into the simulation
      (`SimulationEngine.apply_intervention_effect`) — this is the piece
      that makes the three strategies actually produce different outcomes,
      not just different bookkeeping
- [x] Tests: metrics internally consistent, reproducibility, and a
      scenario-specific test proving a measurable causal effect
      (`tests/test_experiments.py`)

## Milestone 6 — PostgreSQL + FastAPI
- [x] Normalized schema + migrations (Alembic; initial migration verified
      reversible — upgrade → downgrade → upgrade cycle tested)
- [x] REST API: simulations (create/list/get), per-run orders + high-risk
      feed + metrics, order detail (timeline/risk/interventions)
- [x] OpenAPI docs via FastAPI (auto-generated, verified at `/openapi.json`)
- [x] API integration tests (`tests/test_api.py`, using `TestClient` against
      a real Postgres test database, not mocks)
- Dev environment note: this required installing Homebrew, Python 3.12, and
  PostgreSQL 16 locally (none were present) — see `docs/interview-notes.md`.

## Milestone 7 — Operations Dashboard
- [x] Live stats: active deliveries, high-risk count, failure rate,
      interventions triggered (polled every 20s — no WebSocket push yet,
      per the out-of-scope list)
- [x] Map (MapLibre GL) — merchants/drivers/customers plotted on a blank
      style using their synthetic x/y km coordinates directly as the
      projection (there is no real geography to show; see
      `components/MapView.tsx`)
- [x] High-risk order feed
- [x] Order inspector: timeline, risk factors, recommended intervention, cost
      math (`/orders/[id]`)
- [x] Simulation Lab: configure + run experiments, view comparative results
      (`/simulation-lab`)
- [x] Every number on screen traces to a backend calculation — the frontend
      has no mock data or fallback fixtures; every page fetches from the
      real FastAPI backend
- Verified: `tsc --noEmit`, `eslint`, and `next build` all clean; all three
  routes return HTTP 200 against a live backend with real seeded data.
  Not yet verified in an actual browser (no browser/screenshot tool
  available this session) — dev servers were left running on :3000/:8000
  for manual visual check.

## Milestone 8 — Tests + Benchmarks
- [ ] Unit/integration/API coverage: risk calc, intervention selection,
      lifecycle transitions, reproducibility, concurrent state changes
- [ ] Throughput benchmarks at 1K / 10K / 100K orders
- [ ] API latency benchmarks
- [ ] Documented: baseline → bottleneck → change → result

## Milestone 9 — Docker + CI + README
- [ ] `docker compose up` works end to end
- [ ] GitHub Actions: lint, test, build
- [ ] README as engineering case study (problem, architecture, methodology,
      measured results, benchmarks, engineering-decisions, honest limitations)
- [ ] `docs/interview-notes.md` complete and current

## Explicitly out of scope (until MVP is solid and deployed)
Kafka/Redis Streams, service decomposition, ML risk model, WebSocket real-time
push, marketplace-wide bipartite-graph optimization, Prometheus/Grafana,
AWS-specific deployment, chaos/load testing.

If time remains after deployment: **WebSocket live updates** is next, before
anything else on the above list.

## Environment note (2026-09-18)
Dev machine had no Python ≥3.12 available (system Python was 3.9.6 via Xcode
CLI tools, no Homebrew/pyenv). Installing Homebrew + `python@3.12` before
backend work starts.
