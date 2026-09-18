# Interview Notes

Maintained continuously as components are built — not written retroactively.
For each major component: what it does, why it exists, how it works,
alternatives considered, tradeoffs, complexity, failure modes, how it'd
scale, and likely interview questions.

This file is a working artifact. Sections are added as milestones complete
(see [`ROADMAP.md`](../ROADMAP.md)); an empty section below means that
component doesn't exist yet — never fill one in speculatively.

---

## Domain model & simulation engine

**What/why**: `domain/` holds framework-free dataclasses (`Merchant`,
`Driver`, `Customer`, `Order`, `Delivery`, `DeliveryEvent`) plus `Order`'s
enforced state machine (`ORDER_TRANSITIONS` in `domain/enums.py` —
`transition_to` raises on any move not in that table). `simulation/engine.py`
is a fixed-tick (default 1 simulated minute) discrete-time loop that
generates a population from a seeded `random.Random` and advances every
order through arrival → confirm → assignment → travel → prep → travel →
terminal outcome.

**Determinism**: every random draw goes through the single seeded RNG the
engine owns; nothing touches the global `random` module. Verified by test
(`test_run_is_deterministic`) and manually (two full runs, identical seed,
byte-identical order statuses and event counts).

**A real bug this surfaced**: the engine tracks in-flight orders in a few
`set[str]` fields (`_en_route_to_merchant`, `_at_merchant_waiting`,
`_en_route_to_customer`) and iterated them directly in the per-tick hazard
and travel loops. CPython's `set` iteration order depends on each string's
hash, and string hashing is randomized *per process* (`PYTHONHASHSEED`)
unless pinned — so two separate `python` invocations with the *identical*
config and seed could still process orders in a different order within a
tick, meaning two orders sharing the one seeded RNG stream would draw
different random numbers depending on which process happened to hash
`"order-000042"` first. Within a single process (e.g. two calls in the same
pytest run) this stayed invisible — same hash seed, same order, looked
perfectly reproducible — which is exactly why it slipped through initially
and only showed up as an intermittent failure when the full suite ran in a
fresh process. Fixed by iterating `sorted(...)` over these sets instead of
`list(...)`, which also happens to sort orders by creation order (IDs are
zero-padded and sequential). Confirmed fixed by running the same
config/seed under three different `PYTHONHASHSEED` values and diffing
outcomes.

This is a good illustration of why "looks deterministic when I ran it
twice" isn't sufficient evidence — the bug required varying something
(process/hash seed) that a single dev session wouldn't naturally vary.

**Ground truth vs. prediction**: hazards (driver goes offline, customer
unreachable, spoilage, merchant stockout) are real probabilistic draws
*scaled by observable entity attributes* (reliability scores, backlog) so
the causal structure is realistic. The risk engine is never allowed to read
these probabilities or rolls directly — only the same state a real ops
system would see. This separation is the single most important design
decision in the project: without it, "prediction" would just be an oracle
lookup.

**Alternatives considered**: an event-queue (next-event-time) simulation
engine instead of fixed ticks. Rejected for v1 as unnecessary complexity —
tick-based is easier to reason about/test, and per-tick iteration is cheap
at the entity counts this project targets. Revisit only if Milestone 8
benchmarks show tick overhead dominates.

**Likely interview questions**: "How do you guarantee the risk model isn't
cheating?" (see ground-truth separation above). "Why not an event-driven
simulation core?" (see alternatives). "How would this change at 10x scale?"
(tick overhead is O(active orders) per tick, not O(total orders) — a
100-order run and a 100K-order run over the same duration cost roughly the
same per tick as long as *concurrently active* orders stay bounded; the
duration × order-rate product is what actually stresses this, not total
count — worth benchmarking explicitly in Milestone 8 rather than assuming).

## Event system

**What/why**: `events/bus.py`'s `InProcessEventBus` implements an `EventBus`
`Protocol` (subscribe/publish). The simulation engine publishes a
`DeliveryEvent` on every state change; subscribers are called synchronously,
in registration order, on the same call stack — no queue, no async.

**Why this matters for ordering**: `RiskAssessmentService` and
`InterventionService` are both wildcard subscribers. Because dispatch is
synchronous and in registration order, constructing the risk service first
guarantees `InterventionService`'s handler always sees a freshly computed
assessment for the *same* event, with no explicit coordination needed.

**Alternatives considered**: Kafka/Redis Streams. Explicitly deferred — the
`Protocol` boundary means a broker-backed implementation is a new class, not
a rewrite of engine/risk/intervention code, so deferring costs nothing
architecturally.

**Known limitation**: purely reactive, no polling. An order sitting
untouched between two events doesn't get its risk re-evaluated in that gap —
e.g. an order waiting for a driver only gets scored at `CONFIRMED` and then
not again until `DRIVER_ASSIGNED` or a cancellation event fires. Observed
concretely in experiment runs: interventions occasionally fire "too late"
because the hazard that caused a failure was itself the very next event.
Fixing this cleanly would mean either periodic re-evaluation (which the
"react to events, don't poll" requirement explicitly avoids) or synthetic
"time elapsed" events — deferred as a documented v1 limitation, not silently
papered over.

## Risk engine

**What/why**: `risk/engine.py`'s `RiskEngine.assess()` is a pure function:
observable state in, `RiskAssessment` out (0-100 score, predicted failure
type, confidence, predicted delay, and a list of weighted `RiskFactor`s).
Each factor has a name, a `[0,1]` raw signal, a max weight, and a
contribution — the score is the applicable factors' weighted average, so it
stays in `[0,100]` regardless of how many factors happened to apply at a
given delivery stage.

**Rules** (weights in `_RULE_WEIGHTS`): lateness projection (35, dominant —
projected completion vs. promise, using *estimated* not exact remaining prep/
travel), merchant backlog (15) and reliability (10, both pre-pickup only),
driver-unassigned wait (15, pre-assignment only), driver reliability (10,
once assigned), customer reachability (10, once en route to customer),
perishable-overdue (5, perishable + already late + en route).

**Alternatives considered**: an ML model (e.g. logistic regression on
simulated outcomes) instead of hand-weighted rules. Deferred deliberately —
rules first gives an interpretable baseline and forces every risk factor to
be named and justified; ML would be a *comparison* against this baseline
later, not a replacement, and only after this baseline is measured.

**Failure modes**: garbage-in-garbage-out on the weights/thresholds — they're
documented assumptions (see docstrings in `risk/engine.py`), not fitted
constants, because there's no real outcome data to fit them to. Confidence
is a heuristic (more applicable factors → higher confidence), not a
calibrated probability.

**Likely interview questions**: "How would you validate these weights are
right?" (you can't, not from simulation alone — you'd want outcome data from
a real marketplace, or at minimum a much larger multi-seed experiment
measuring calibration: of orders predicted >80% risk, did ~80% actually
fail?). "Why treat the score as an implied probability in the intervention
engine?" (documented simplification — it's the only failure-likelihood
signal in the system, so it's used consistently rather than introducing a
second, disconnected notion of probability).

## Intervention engine

**What/why**: `interventions/engine.py` scores every applicable intervention
(including the implicit `DO_NOTHING`) by
`total_expected_cost = direct_cost + failure_probability × (1 -
probability_reduction) × failure_cost × (1 - cost_reduction_fraction)`,
picks the minimum. `probability_reduction` (root-cause levers:
`REASSIGN_DRIVER`, `MERCHANT_ESCALATION`, `NOTIFY_MERCHANT`) and
`cost_reduction_fraction` (impact-softening levers: `UPDATE_ETA`,
`NOTIFY_CUSTOMER`, `OFFER_CREDIT`) are deliberately kept separate — a lever
either changes what happens or changes how much it costs when it does,
never a fuzzy mix of both, which is what keeps the "why" in
`InterventionDecision.rationale` legible.

**Feedback loop**: `SimulationEngine.apply_intervention_effect` feeds a
chosen intervention's `probability_reduction` back into the *actual* hazard
rolls for that order (and proportionally extends its driver-wait patience).
Without this, the experiment framework would compute different "decisions"
per strategy but identical ground-truth outcomes — this is what makes
Milestone 5's comparison real rather than cosmetic.

**Alternatives considered**: a bandit/RL-learned policy. Explicitly out of
scope — there's no reward signal from a real marketplace to learn from yet,
and an expected-value model over documented cost/effect assumptions is more
defensible in a portfolio context than an opaque learned policy with made-up
training data.

**Likely interview questions**: "How would you tune the cost/effect
numbers?" (currently documented assumptions — a real deployment would learn
them from measured intervention outcomes; this project doesn't have that
data, so it's explicit rather than hidden). "Why can `REASSIGN_DRIVER` never
apply before a driver is assigned?" (`requires_driver_assigned` — you can't
reassign a driver that doesn't exist yet; the applicable case for
"unassigned too long" is `NOTIFY_MERCHANT`/escalation instead).

## Experiment framework

**What/why**: `experiments/runner.py` runs the *same* `SimulationConfig`
through three strategies — `NO_INTERVENTION` (bare engine), `THRESHOLD_BASED`
(`ThresholdInterventionPolicy`: one fixed action, fixed cost, fixed effect
size, triggered purely by a risk-score threshold, no cause-awareness — the
"naive ops team" baseline), and `EXPECTED_VALUE` (the real
risk+intervention engine stack) — and computes comparable metrics for each.

**Why "identical seeded conditions" doesn't mean "identical outcomes"**: all
three runs re-seed from `config.seed` via a fresh `SimulationEngine`, so they
start identically. But once a strategy actually prevents a hazard, that
order keeps consuming RNG draws in later ticks that it wouldn't have under a
different strategy — this shifts alignment for *every subsequent* draw, not
just that order's. This is the correct, expected counterfactual divergence,
not a bug; it's documented in the runner's module docstring and confirmed by
test (`test_reproducible_given_same_config` checks reproducibility of a
*given* strategy, not equality *across* strategies).

**Measured, not fabricated**: a specific seed/config combination in
`tests/test_experiments.py` demonstrates a real, measured effect — the
threshold policy's extended driver-wait patience reduces
`no_driver_available` cancellations relative to the no-intervention
baseline in that scenario. It does **not** universally prove "intervening is
always better" — a supply-constrained scenario tested manually during
development showed extending patience can *shift* which orders fail rather
than reduce the total, since drivers are the actual bottleneck. Both
findings are real and worth having in the README's honest-limitations
section: interventions help when they address the actual constraint, and
can be neutral or counterproductive when they don't.

**Known limitation**: single-seed comparisons are one sample path, not a
distribution. A rigorous version would run many seeds per configuration and
report distributions/confidence intervals, not point estimates. Deferred for
scope; noted so it's never mistaken for more rigorous than it is.

## Persistence (PostgreSQL + SQLAlchemy)

**What/why**: `persistence/models.py` is a normalized schema (10 tables,
real foreign keys) mapped from — but not shared with — the `domain/`
dataclasses; conversion lives in `persistence/repository.py`, the only
module allowed to import SQLAlchemy. Migrations via Alembic
(`alembic/versions/`), connection string via `ORDERGUARD_DATABASE_URL`.

**A real bug found and fixed here**: enum columns (`domain/enums.py`'s
`StrEnum`s) default, in SQLAlchemy's `Enum` type, to storing the Python
`.name` (upper-case) rather than `.value` (lower-case) — which would have
silently broken every string-based API filter (`?status=delivered`) since
the rest of the codebase serializes on `.value`. Fixed with a
`values_callable` helper (`_str_enum`) applied to every enum column.

**A second real bug**: a cross-table foreign key (`intervention_decisions.
risk_assessment_id → risk_assessments.id`) failed on insert even though
Postgres's schema-level FK ordering should, in principle, handle unrelated
mapped classes correctly. In practice, a single `session.commit()` adding
both in one flush hit an ordering issue; fixed with an explicit
`session.flush()` between the two loops in `save_simulation_run` rather than
trusting automatic dependency sorting across classes with no `relationship()`
configured between them. Worth digging into further if it recurs elsewhere.

**Alternatives considered**: SQLite for simplicity. Rejected — the stack
decision is Postgres from the start (real FK relationships, JSONB, and this
is meant to demonstrate production-shaped decisions, not the easiest local
setup).

## API (FastAPI)

**What/why**: Thin routers (`api/routers/`) — no business logic, just
validate input (`api/schemas.py`'s Pydantic models), call into
`experiments`/`persistence`, shape the response. `POST /simulations` runs
the full three-strategy experiment, persists the expected-value run's full
detail (orders, deliveries, events, risk assessments, intervention
decisions) plus every strategy's aggregate metrics, and returns the
comparison. `GET /orders/{id}` is the Order Inspector's data source:
timeline + risk history + every intervention decision's full cost-comparison
math.

**Tested against a real database**: `tests/test_api.py` uses FastAPI's
`TestClient` against a real Postgres test database (`orderguard_test`), not
mocks — every assertion is checking data that actually round-tripped through
the simulation → persistence → HTTP response path.

## Dashboard (Next.js)
_Not yet built._

## Benchmarks
_Not yet built._
