# Project Working Rules

These rules apply to the project rooted at `D:\antigravity\board office`.

## Source of truth

- The unpacked files at the project root are the active source of truth.
- `00_STARTING_POINT/` is an immutable archive of the four received starting files. Do not edit it or use its status as the current status.
- Do not create a second nested project root.
- There is exactly one active handoff: `/HANDOFF.md`. Update it in place; never create dated or versioned handoff copies.
- Historical context belongs in Git history or a clearly named `docs/history/*_STATE_SNAPSHOT_*.md`, never in another active-looking handoff.
- There is exactly one active milestone plan: `/ROADMAP.md`.

## Every session

At the start of every session:

1. Read `HANDOFF.md` and `ROADMAP.md`.
2. Check the root tree and current Git status.
3. Confirm the current phase, open gate and next concrete task before changing code.

During the session, keep changes scoped to the stated task and preserve static world/character assets and their reference hashes unless an explicit asset change is part of the approved task.

Before ending every session, replace the current information in `HANDOFF.md` even when no source code changed. Keep it as a concise current-state snapshot rather than an accumulating session diary. Record the date, completed work, tests/audits and their results, current status, next task and blockers/approval still needed. Update `ROADMAP.md` whenever milestone scope or acceptance status changes.

## Phase and acceptance rules

- Do not mark a phase closed from a generated manifest or report alone.
- A phase requires working implementation, regression coverage, required audits, clean packaging and explicit author acceptance where visual or gameplay behavior is involved.
- Keep acceptance-pending and author-approved states distinct in handoff text.

## Validation

Use the project root as the working directory. At minimum, run `python -m pytest -q` after runtime changes. For navigation/world changes, also run the relevant validation scripts, including Room Navigation, Navigation Occupancy, WorkSeat, Phase 6 Spatial, Central integrity and F2 gameplay-metadata family audits.

## Release hygiene

Release archives must be freshly created from the root and freshly extracted for verification. Do not ship `__pycache__/`, `.pytest_cache/`, `LOCAL_REVIEW/`, preview/debug artifacts or materialized occupancy caches. Require `release_clean=true` before promoting a canonical package.

## File and process safety

- Prefer reversible, narrowly scoped file operations and verify exact paths before moving or removing anything.
- Use `apply_patch` for text/code edits.
- Inspect existing listeners before starting a development server; reuse a healthy project server and clean up only processes started for this task.
- Do not rewrite or delete historical starting-point files.
