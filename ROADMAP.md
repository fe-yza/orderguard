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
- [ ] Strategies compared on identical seeded conditions: no intervention,
      threshold-based, OrderGuard expected-value
- [ ] Real metrics collected: late rate, cancellation rate, avg delay, P50/P95
      delay, intervention rate, intervention cost, failure/success counts
- [ ] Results persisted and reproducible — this is the only source of resume
      numbers

## Milestone 6 — PostgreSQL + FastAPI
- [ ] Normalized schema + migrations (Alembic)
- [ ] REST API: orders, drivers, merchants, risk, interventions, simulations,
      metrics overview
- [ ] OpenAPI docs via FastAPI
- [ ] API integration tests

## Milestone 7 — Operations Dashboard
- [ ] Live stats: active deliveries, high-risk count, failure rate,
      interventions triggered
- [ ] Map (MapLibre GL)
- [ ] High-risk order feed
- [ ] Order inspector: timeline, risk factors, recommended intervention, cost
      math
- [ ] Simulation Lab: configure + run experiments, view comparative results
- [ ] Every number on screen traces to a backend calculation

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
