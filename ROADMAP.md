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
- [ ] In-process event bus (publish/subscribe), swappable backend interface
- [ ] Simulation engine emits domain events on every state change
- [ ] Risk engine (Milestone 3) subscribes/reacts instead of polling
- [ ] Tests: event ordering, subscriber isolation, no dropped events

## Milestone 3 — Rules-Based Risk Engine
- [ ] Per-delivery: overall risk score (0–100), predicted failure type,
      confidence, predicted delay
- [ ] Explainable contributing factors with weighted contributions
- [ ] All inputs derived from observable simulation state — nothing randomly
      assigned
- [ ] Thresholds/weights documented and configurable (env/config, not hardcoded)
- [ ] Tests: known scenarios produce known risk bands

## Milestone 4 — Intervention Engine
- [ ] Intervention catalog: `DO_NOTHING`, `UPDATE_ETA`, `NOTIFY_CUSTOMER`,
      `NOTIFY_MERCHANT`, `MERCHANT_ESCALATION`, `OFFER_CREDIT`,
      `REASSIGN_DRIVER` — each with cost + applicability conditions
  Interventions
- [ ] Expected-value selection model: cost(intervention) vs.
      P(failure | no intervention) × cost(failure) vs. cost of doing nothing
- [ ] Tests: selection is deterministic given identical risk state

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
