# OrderGuard

Real-time delivery failure prediction and intervention system, built as a
portfolio project against a synthetic on-demand delivery marketplace
simulation. No real company or customer data is used anywhere in this
project.

**Core question:** Can we identify deliveries likely to fail before they
fail, determine the probable cause, and select a cost-effective intervention?

## Current status

Early scaffolding. This README will grow into a full engineering case study
(problem, architecture, methodology, measured results, benchmarks,
engineering-decisions, limitations) as the system is built — see
[`ROADMAP.md`](ROADMAP.md) for what exists today versus what's planned, and
[`docs/architecture.md`](docs/architecture.md) for the design.

No functionality is claimed here beyond what's implemented and tested. If a
milestone in the roadmap is unchecked, that feature does not exist yet.

## Stack
Python 3.12 / FastAPI / Pydantic / SQLAlchemy / PostgreSQL (backend) ·
Next.js / React / TypeScript / MapLibre GL (frontend) · pytest · Docker
Compose · GitHub Actions.

## Docs
- [`ROADMAP.md`](ROADMAP.md) — build order and current progress
- [`docs/architecture.md`](docs/architecture.md) — module boundaries, domain
  model, and the reasoning behind key technical decisions
- [`docs/interview-notes.md`](docs/interview-notes.md) — component-by-component
  deep dive, maintained as the system is built
