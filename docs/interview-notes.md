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

**A third real bug, more serious — found via benchmarking, not inspection**:
the initial schema used the simulation's own generated IDs
("merchant-0003", "order-000042", ...) as bare primary keys. Those IDs are
only unique *within a single run* — every `SimulationEngine` restarts its
counters from zero (`simulation/generators.py`) — so persisting a *second*
run ever crashed with `UniqueViolation` on `customers_pkey`. Every test
passed because each test's `db_session` fixture truncates tables between
tests, so only one run's rows ever coexisted at a time; the bug only
surfaced when the API latency benchmark hit `POST /simulations` repeatedly
against the same, un-truncated database — exactly the kind of thing "run it
under realistic conditions" catches that unit tests, by construction,
don't. Fixed by making `merchants`, `drivers`, `customers`, `orders`, and
`deliveries` use composite primary keys — `(simulation_run_id, id)` — and
composite foreign keys everywhere they're referenced (`risk_assessments`
and `intervention_decisions` keep simple UUID keys; those IDs were already
globally unique). This is a genuinely instructive example of a bug class
worth naming: **generated IDs that are only unique within a scope will
eventually collide once more than one instance of that scope exists** — the
kind of thing that's invisible until you deliberately create two of
whatever the scope is.

That fix immediately exposed a **fourth bug**, one layer up: `GET
/orders/{order_id}` had been written as if order IDs were globally unique.
Once two runs could coexist in the database, the same lookup started
raising `MultipleResultsFound` instead of quietly returning the wrong run's
order (arguably worse — a silent wrong answer — but SQLAlchemy's
`scalar_one_or_none()` correctly refuses to guess). Fixed by moving the
route to `GET /simulations/{run_id}/orders/{order_id}` — the fix belonged
in the API contract, not the query — and updating `repository.get_order_
detail` to require `run_id`, with no unscoped fallback. The frontend's
order links already had `run_id` in scope wherever they're constructed
(every order ID reaches the UI from a run-scoped list to begin with), so
updating the route was mechanical, not a design change.

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
comparison. `GET /simulations/{run_id}/orders/{order_id}` is the Order
Inspector's data source: timeline + risk history + every intervention
decision's full cost-comparison math — scoped by run, not a flat
`/orders/{id}`, because order IDs are only unique within a run (see the
Persistence section's third/fourth bugs above for why that isn't optional).

**Tested against a real database**: `tests/test_api.py` uses FastAPI's
`TestClient` against a real Postgres test database (`orderguard_test`), not
mocks — every assertion is checking data that actually round-tripped through
the simulation → persistence → HTTP response path.

## Dashboard (Next.js)

**What/why**: App Router, all data pages are Client Components (`"use
client"`) that fetch directly from the FastAPI backend — no server-side
proxy layer, since there's no auth or secret to hide yet and it keeps the
stack simpler. Three pages: Overview (`/`, an explanation banner + stat
tiles + map + high-risk feed, polling every 20s), Simulation Lab
(`/simulation-lab`, configure and run an experiment, see the three-strategy
comparison as both a table and a bar chart), Order Inspector
(`/simulations/[runId]/orders/[orderId]`, timeline + risk-over-time chart +
factor breakdown + intervention cost-comparison table).

**No mock data, anywhere**: every value rendered comes from a `fetch` to a
real endpoint on the FastAPI backend, backed by real Postgres rows. There is
no fixture/demo-data fallback path — if the backend is down, the page shows
an API error, not a plausible-looking fake number.

**Map** (`components/MarketplaceMap.tsx`): plain SVG, not MapLibre GL —
switched after the first pass, deliberately, once it became clear there was
no real geography to project onto and a general-purpose mapping library was
pure overhead for a synthetic coordinate plane. Bounds are computed from
the actual returned merchant/driver/customer positions (no hardcoded
map-size assumption); delivery routes are drawn only for orders that
actually got a driver assigned (`driver_id is not null`), colored by
status — active + above the current risk threshold gets a distinct color
and a highlighted driver marker, terminal orders render dim and desaturated
by outcome. Backed by a new endpoint, `GET /simulations/{run_id}/map`'s
`deliveries` array (`persistence/repository.py`'s `get_delivery_map_for_run`
— one query, joining orders to merchants/customers/drivers/latest-risk,
every join condition scoped by `simulation_run_id` for the same reason
composite keys exist at all: none of those IDs are unique across runs).

**Empty states, handled honestly**: the high-risk feed fetches every scored
order once (`min_score=0`) and applies the threshold client-side, so
raising/lowering it never needs a round trip. When *nothing* clears the
threshold — which happens on plenty of real runs, not a hypothetical: a
seed-77 run with deliberately elevated hazard rates still topped out at a
9.1 risk score — the panel says so explicitly and shows the top-10 highest-
risk orders anyway, labeled as below-threshold. This was a deliberate
answer to "the dashboard can show 0 high-risk orders" rather than either
lying about it or leaving a blank panel.

**Live stats without WebSockets**: polling (`setInterval`, 20s) rather than
push, consistent with WebSockets being explicitly deferred in the roadmap.
This is a real, known limitation — if the user is watching for a change
that happens more often than the poll interval, they'll miss the
intermediate states. Acceptable for a portfolio-scale demo; the roadmap
already names WebSocket live updates as the next highest-value addition
after the MVP ships.

**Not yet verified**: no browser/screenshot tool has been available in any
session that's worked on this — verification has been `tsc --noEmit`
(clean), `eslint` (clean), `next build` (clean), confirming every route
returns HTTP 200 against a live backend with real data (via `curl`,
checking the server-rendered HTML shell, including grepping for specific
content that only renders once client-side data fetches resolve), and
independently querying the same API endpoints the frontend calls to confirm
the data shape and values it will receive are sane (e.g. confirmed a real
run with 22 active high-risk deliveries, one at a 72.5 score with a
genuine `notify_customer` intervention and a $0.33 expected net value, and
separately confirmed a run where nothing clears the default 50-point
threshold, to exercise the fallback path). What's still unverified is
purely visual/interactive: does the SVG map actually look right, are chart
labels legible, does the layout hold at narrow widths. Spot-check in an
actual browser before treating this as fully done.

**Likely interview questions**: "Why Client Components instead of Server
Components fetching in `page.tsx`?" (the data needs to poll/refresh and
respond to user-driven config changes — Server Components render once per
request, which doesn't fit a "live" dashboard without either polling from
the client anyway or a more complex revalidation setup; simplest correct
choice given the requirement). "Why SVG for the map instead of a mapping
library?" (see the Map section above — no real geography, so a
general-purpose mapping library bought nothing but bundle size and
complexity; a first pass actually used MapLibre GL before being replaced).
"Why recharts and not something lighter for two small charts?" (already
needed a real charting library for the Simulation Lab comparison and the
per-order risk-history view — one dependency serving two call sites beat
hand-rolling SVG charts a second time in the same codebase that already
hand-rolls the map).

## Benchmarks

Scripts: `backend/benchmarks/benchmark_simulation.py` (throughput at 1K/10K/
100K orders, bare engine vs. full risk+intervention stack) and
`backend/benchmarks/benchmark_api_latency.py` (p50/p95 latency for every
endpoint against a real running server + real Postgres). Not pytest tests —
they print measurements, on this dev machine (Apple Silicon, local
Postgres), not portable performance guarantees. Re-run them yourself before
citing a number anywhere.

### Simulation throughput: baseline → bottleneck → fix → result

**Baseline** (bare engine, no risk/intervention wiring), 1440-simulated-
minute runs, entity counts scaled proportionally to the target order count:

| target orders | actual | wall time | orders/sec |
|---|---|---|---|
| 1,000 | 993 | 0.042s | 23,905 |
| 10,000 | 9,857 | 0.777s | 12,679 |
| 100,000 | 100,156 | 49.088s | 2,040 |

Throughput *fell* more than 10x going from 1K to 100K — not the flat/near-
linear scaling a tick-based simulation should show. That's a red flag worth
chasing before ever citing a "handles 100K deliveries" number.

**Bottleneck, found by profiling (`cProfile`) the 100K run**: 92% of total
runtime (118s of 129s) was `_nearest_available_driver` — on every driver
assignment attempt, it filtered *every* driver in the marketplace
(`[d for d in self.drivers.values() if d.is_available]`) to find the
available ones, then took the nearest. At 100K scale with ~830 drivers and
~1.48M assignment attempts across the run, that's ~1.2 **billion** calls to
`Driver.is_available`. Classic O(pending_orders × total_drivers) hiding
inside what looked like a simple list comprehension.

**Fix**: maintain `self._available_driver_ids` incrementally (a dict-as-
ordered-set, updated at the handful of places a driver's availability
actually changes — assigned, freed after delivery/failure/spoilage) instead
of re-deriving it from scratch on every call. `_nearest_available_driver`
now only ever iterates over drivers that are actually available.

**Result**, same benchmark, same three targets:

| target orders | actual | wall time | orders/sec | speedup |
|---|---|---|---|---|
| 1,000 | 1,009 | 0.037s | 27,629 | 1.1x |
| 10,000 | 9,936 | 0.346s | 28,738 | 2.2x |
| 100,000 | 99,923 | 3.936s | 25,388 | **12.5x** |

Throughput is now roughly flat (~25-29K orders/sec) across two orders of
magnitude — the engine scales the way a tick-based design should. The full
stack (risk + intervention services attached) went from 57.6s → 12.7s at
100K (4.5x) — smaller speedup than the bare engine because, once the driver-
lookup bottleneck was removed, a re-profile showed the remaining time is
mostly *proportional* work (risk assessment + intervention selection firing
once per event, ~410K times at 100K scale) rather than a second hidden
superlinear bottleneck. That remaining cost is inherent to the event-
reactive design, not a bug — reducing it further would mean changing what
gets computed (e.g. cheaper risk scoring), not how it's looked up.

### API latency: baseline → bottleneck → fix → result

Against a real running server + real Postgres (not the in-process
TestClient, which skips actual socket I/O):

| endpoint | before | after |
|---|---|---|
| `GET /simulations` | 1.1ms (p50) | — (unchanged) |
| `GET /simulations/{id}/orders` | 2.5ms | — (unchanged) |
| `GET /simulations/{id}/metrics` | 1.3ms | — (unchanged) |
| `GET /simulations/{id}/map` | 17.2ms | — (unchanged) |
| `GET /simulations/{id}/orders/{id}` | 33.9ms | — (unchanged) |
| `GET /simulations/{id}/high-risk` | **1782.8ms** | **218.2ms (8.2x)** |
| `POST /simulations` (~1K orders, 3 strategies + full persistence) | ~1.6s | ~1.6s (not optimized — see below) |

**Bottleneck**: `get_latest_risk_assessments_for_run` (backing the
high-risk feed) eager-loaded *every* historical risk assessment for *every*
order in the run via `selectinload`, then picked the newest per order in a
Python loop — on a 5K-order run with risk reassessed on every event, that's
~30K assessment rows (each carrying a JSONB factors list) pulled over the
wire and mostly discarded.

**Fix**: a `ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY computed_at
DESC)` window-function query, so Postgres picks the latest row per order
server-side and only that row crosses the wire. Verified independently
(direct query timing: 0.16s server-side for the same run) before rewriting
`persistence/repository.py`.

**`POST /simulations` was not optimized** — ~1.6s for a full three-strategy
comparison (each strategy runs an independent simulation) plus persisting
one run's full detail is a reasonable cost for a synchronous request at
this scale, and profiling would be the next step *if* this needs to get
faster (candidate suspects: running the three strategies concurrently
instead of sequentially, or batching the persistence inserts) — not
optimized here because nothing measured points at it being disproportionate
yet. Consistent with "measure before optimizing": absence of a finding is
also a finding.

**Likely interview questions**: "How did you find the driver-lookup
bottleneck?" (`cProfile`, sorted by cumulative time — 92% in one function is
impossible to miss once you look). "Why a window function instead of just
caching?" (caching risk assessments would go stale the moment a new event
fires; the window function reads current data, it just reads *less* of
it). "What would you profile next if this needed to scale further?"
(honest answer: `POST /simulations`'s per-row `session.add()` pattern in
`repository.py` — SQLAlchemy's ORM-level bulk insert is not the fastest way
to write tens of thousands of rows; `bulk_insert_mappings` or raw
`COPY`-based loading would be the next thing to measure, not assume).

## Docker & CI

**What/why**: `docker-compose.yml` at the repo root wires up Postgres, the
backend (migrations run automatically via the container's `CMD` before
`uvicorn` starts — `sh -c "alembic upgrade head && uvicorn ..."`), and the
frontend (`next build` with `output: "standalone"`, so the runtime image
only ships the resolved dependency subset, not the full workspace).

**Actually verified, not just written**: neither Docker nor any container
runtime was present on the machine this was built on. Installed Colima
(a lightweight Linux VM) + the Docker CLI via Homebrew, then genuinely ran
`docker compose build` and `docker compose up`, confirmed migrations
executed in the backend container's logs, hit `/health`, ran a full
`POST /simulations` experiment against the dockerized API, and tore the
stack down — the same bar as everything else in this project: don't claim
something works without running it.

**CI**: `.github/workflows/ci.yml` runs backend lint (`ruff`) + migrations +
`pytest` against a real `postgres:16` service container, and frontend
`eslint` + `tsc --noEmit` + `next build`. Every individual command in the
workflow has been run successfully in this repo's own local development;
the workflow file itself has not executed on GitHub Actions, since this
repository has no GitHub remote configured. That's a meaningful caveat, not
a technicality — a YAML file that's never actually run on the target
platform can still have a wrong working-directory path or a missing env var
that only shows up there. Push to a real GitHub remote and watch the first
run before treating this as "CI passes," not just "CI is configured."

**Likely interview questions**: "Why Colima instead of Docker Desktop?"
(Docker Desktop needs a GUI installer and manual first-run steps that don't
work in a non-interactive environment; Colima is scriptable end-to-end via
Homebrew + CLI, which is what let this actually get verified instead of
just written). "What would you add to CI next?" (a step that actually spins
up `docker compose` and smoke-tests it, so a broken Dockerfile fails CI
before it fails a real deploy — not present yet).
