# Documentation Index

This directory contains the technical contracts, implementation plans and historical records for the GDS Central Game Core. The active project root is `D:\antigravity\board office`.

## Read this first

Use these files in this order when starting or resuming work:

1. [`../AGENTS.md`](../AGENTS.md) — project working rules and safety gates.
2. [`../HANDOFF.md`](../HANDOFF.md) — the single current project state.
3. [`../ROADMAP.md`](../ROADMAP.md) — milestone order and acceptance gates.
4. [`../README.md`](../README.md) or [`../README_TH.md`](../README_TH.md) — project overview and usage.

## Authority order

When documents disagree, use this order:

1. Executable code, registries, schemas and passing tests define what the current package actually does.
2. The contract documents below define protected behavior and invariants.
3. `HANDOFF.md` defines the current session/project status.
4. `ROADMAP.md` defines intended milestone order, not implementation proof.
5. `docs/history/` and `00_STARTING_POINT/` are historical context only and must not override current status.

Generated manifests and reports are evidence for a check; their phase labels do not replace explicit author acceptance.

## Canonical technical contracts

- [`CENTRAL_CORE_ARCHITECTURE_DESIGN.md`](CENTRAL_CORE_ARCHITECTURE_DESIGN.md) — central runtime composition and boundaries.
- [`ROOM_NAVIGATION_CANONICAL.md`](ROOM_NAVIGATION_CANONICAL.md) — room/portal geometry and canonical navigation families.
- [`NAVIGATION_OCCUPANCY_CONTRACT.md`](NAVIGATION_OCCUPANCY_CONTRACT.md) — footprints, closures, clearance and WorkSeat transition gates.
- [`FOOTPRINT_SYSTEM_CONTRACT.md`](FOOTPRINT_SYSTEM_CONTRACT.md) — ground footprint rules.
- [`PHASE6_SPATIAL_METADATA.md`](PHASE6_SPATIAL_METADATA.md) — spatial metadata contract.
- [`LEAN_RELEASE_POLICY.md`](LEAN_RELEASE_POLICY.md) — package contents and lean-release policy.

The JSON schemas under `SCHEMA/`, registry files under `WORLD/REGISTRY/` and `CHARACTER/`, and validation scripts under `VALIDATION/` are the machine-readable/runtime companions to these contracts.

## Plans and specifications

- [`PHASE5_IMPLEMENTATION_PLAN.md`](PHASE5_IMPLEMENTATION_PLAN.md) — Phase 5 central integration history.
- [`PHASE6_IMPLEMENTATION_PLAN.md`](PHASE6_IMPLEMENTATION_PLAN.md) — Phase 6 spatial metadata implementation history.
- `superpowers/specs/` — dated design specifications.
- `superpowers/plans/` — dated implementation plans and closeout notes.

Plans and specifications explain decisions; they do not supersede the current handoff or executable behavior.

## Release and verification

- [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md) — repeatable release gate for tests, audits, visual review and fresh extraction.
- `VALIDATION/` — executable audits and reference hashes.
- `REPORTS/` — generated audit and acceptance reports.
- `releases/` — release archives; do not treat an archive as current source until it has been freshly verified.

## History and starting point

- `../00_STARTING_POINT/` — immutable copies of the four files received at project start.
- `history/` — renamed historical state snapshots. These are read-only context, not active handoffs.

Do not add another `HANDOFF*.md`, `STATUS.md`, `TODO.md` or competing roadmap. Update the root `HANDOFF.md` and `ROADMAP.md` instead.

