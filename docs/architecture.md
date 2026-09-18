# OrderGuard — Architecture Proposal

## Core question
Can we identify deliveries likely to fail before they fail, determine the
probable cause, and select a cost-effective intervention?

Everything below is scoped to answering that question as simply and honestly
as possible. No component exists unless it's load-bearing for that answer.

## What this is / isn't
- A synthetic marketplace simulation. No real company or customer data, ever.
- A rules-based system first. ML is explicitly deferred — see "Why rules
  before ML" below. If it's added later, it will be added as a *comparison*
  against the rules engine, not a replacement, and only after the rules
  baseline is measured.
- Every number the UI shows is computed by the backend from simulation state
  or a stored experiment result. If something can't be measured yet, it's
  labeled "unavailable" — never fabricated.

## Module boundaries

```
backend/src/orderguard/
├── domain/         # Entities + state machines. No I/O, no framework deps.
├── events/         # In-process pub/sub bus. Interface designed so the
│                   # backend (in-process → Kafka/Redis, someday) can be
│                   # swapped without touching business logic.
├── simulation/      # Generates the synthetic marketplace, drives the clock,
│                   # advances entity state, emits domain events.
├── risk/           # Subscribes to events, computes explainable risk scores.
├── interventions/  # Subscribes to risk assessments, selects an action via
│                   # expected-value model.
├── experiments/    # Runs the same seeded scenario under different
│                   # strategies (none / threshold / expected-value) and
│                   # collects comparison metrics.
├── persistence/    # SQLAlchemy models + repositories. Nothing above this
│                   # layer should import SQLAlchemy directly.
└── api/            # FastAPI routers + Pydantic schemas. Thin — delegates to
                    # the modules above, no business logic here.
```

Dependency direction is one-way: `api → {simulation, risk, interventions,
experiments, persistence} → domain`. `domain` and `events` depend on nothing
else in the project. `risk` and `interventions` depend on `events` and
`domain`, not on each other directly — they communicate only through events,
so either could be replaced independently.

## Domain model

Entities: `Merchant`, `Driver`, `Customer`, `Order`, `Delivery`,
`DeliveryEvent`, `RiskAssessment`, `Intervention`, `SimulationRun`,
`SimulationMetrics`.

Relationships:
- A `SimulationRun` owns a generated population of `Merchant`, `Driver`,
  `Customer` and the `Order`s created during the run, plus the resulting
  `SimulationMetrics`.
- An `Order` belongs to one `Merchant` and one `Customer`, and has exactly one
  `Delivery` once a driver is assigned (an order can fail before a delivery
  ever exists — e.g. merchant cancels — so this is optional, not 1:1 from
  creation).
- A `Delivery` belongs to one `Driver` and one `Order`, and accumulates an
  ordered list of `DeliveryEvent`s (its timeline) and zero or more
  `RiskAssessment`s (recomputed as state changes, not just once).
- Each `RiskAssessment` may lead to zero or one `Intervention` (the engine
  can decide `DO_NOTHING`, which is still a recorded decision, not an
  absence of one).

Order lifecycle (state machine, `domain/order.py`):
```
created → confirmed → assigned → en_route_to_merchant → arrived_at_merchant
        → picked_up → en_route_to_customer → delivered
                                            ↘ failed
        ↘ cancelled (from created/confirmed/assigned)
```
Failure and cancellation are distinct: cancellation is a deliberate stop
(merchant out of stock, customer changed mind); failure is the outcome
OrderGuard is trying to predict and prevent (missed window, spoiled/wrong
order, driver never arrives). This distinction matters for the risk engine —
we're not predicting cancellations, we're predicting failures.

Driver states (`domain/driver.py`): `available → en_route → waiting →
delivering → available`, with `offline` reachable from any state (shift end,
app closed). Idle time is tracked as a first-class field because it's a risk
factor for driver-side failure causes (driver unavailability, slow pickup).

## Why rules before ML
A rules engine forces every risk factor to be named, weighted, and
justified — which is exactly what an interview conversation (and an honest
README) needs. It also gives us a *baseline* to compare an ML model against
later, which is the scientifically correct order: you don't know if ML helped
until you've measured what simple rules already get you. Building ML first
would hide whether the complexity was earning its keep.

## Why no Kafka/Redis yet
The event bus interface (`events/bus.py`) is designed so a backend swap is an
implementation change, not a rewrite: publishers and subscribers depend on an
abstract `EventBus` protocol, not on any specific transport. Until the
in-process bus is a measured bottleneck (Milestone 8 benchmarks), adding a
message broker would be complexity with no evidence it's needed — it would
also mean standing up infrastructure that has nothing to do with the actual
question this project answers.

## Why PostgreSQL
Normalized relational data (orders, deliveries, drivers, merchants) with real
foreign-key relationships and the need for ad-hoc analytical queries
(experiment comparisons, percentile delay calculations) is a textbook
relational fit. No document-shaped or high-write-throughput requirement exists
here that would justify anything else.

## Determinism
The simulation is driven by a single seeded `random.Random` instance passed
explicitly through the generation and clock-advance code paths — no module
reaches into global `random` state. Same seed + same config ⇒ byte-identical
sequence of domain events. This is required for the experiment framework: the
three strategies (none / threshold / expected-value) must run against
*identical* underlying marketplace conditions, or the comparison is meaningless.

## Scaling posture
Domain entities are plain dataclasses (not Pydantic models) in the simulation
hot path — Pydantic's validation overhead is unnecessary once data originates
from trusted, typed generation code rather than external input. Pydantic is
used at the API boundary (`api/` schemas), where validating untrusted input is
exactly the job it's for. This is revisited if profiling in Milestone 8 says
otherwise.

## Status
See [`ROADMAP.md`](../ROADMAP.md) for milestone-by-milestone progress. This
document describes the target shape; it will be corrected as reality diverges
from the plan, not left to rot.
