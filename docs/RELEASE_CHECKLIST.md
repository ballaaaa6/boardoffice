# Release Checklist

Use this checklist before promoting any package as a canonical GDS Central Game Core release. Run commands from the project root `D:\antigravity\board office`.

This checklist is a release gate, not a runtime design document. A report that says `PASS` is necessary but does not replace explicit author acceptance for visual or gameplay behavior.

## 1. Preflight

- [ ] Read `AGENTS.md`, `HANDOFF.md` and `ROADMAP.md`.
- [ ] Confirm the project root is the intended checkout and no nested project root exists.
- [ ] Confirm the target version and release scope in `CENTRAL_MANIFEST.json`.
- [ ] Inspect `git status --short --branch` and identify every intentional change.
- [ ] Preserve static world/character assets and reference hashes unless the release explicitly includes an approved asset change.
- [ ] Do not use files under `00_STARTING_POINT/` as current source or modify them.

## 2. Automated regression

Run the full suite:

```text
python -m pytest -q
```

- [ ] All collected tests pass.
- [ ] Any focused tests added for the current milestone pass.
- [ ] No failure is hidden by a stale cache or an alternate working directory.

## 3. Required audits

Run each audit from the root and retain the generated report:

```text
python VALIDATION/self_audit_room_navigation.py
python VALIDATION/self_audit_ground_footprints.py
python VALIDATION/self_audit_navigation_occupancy.py
python VALIDATION/self_audit_work_seat.py
python VALIDATION/self_audit_phase6.py
python VALIDATION/self_audit_gameplay_metadata_family.py
python VALIDATION/self_audit_central.py
```

- [ ] Room Navigation: PASS.
- [ ] Ground Footprints: PASS.
- [ ] Navigation Occupancy: PASS for all registered floors and workstations.
- [ ] WorkSeat: PASS.
- [ ] Phase 6 Spatial: PASS.
- [ ] F2 gameplay-metadata family synchronization: PASS.
- [ ] Central integrity: `pass=true`.

## 4. Visual/gameplay acceptance

For movement, portal, crowd or WorkSeat changes:

- [ ] Render representative samples for F0, F1 and the F2-family floor.
- [ ] Inspect portal entry/exit, fade order, actor facing, movement speed and walking depth.
- [ ] Confirm no ghost/translucent actor remains after despawn.
- [ ] Confirm crowd trajectories preserve ground-anchor clearance and actor identity.
- [ ] For WorkSeat, confirm the actor stops at the reachable exterior gate, takes over the authored seat placement, renders the correct work pose and exits back to navigation without entering chair clearance.
- [ ] Record the author's acceptance or rejection in `HANDOFF.md`.

## 5. Clean package

Create the archive from the project root using the release tooling for the current milestone. The archive must exclude:

- `__pycache__/` and `*.pyc`;
- `.pytest_cache/`, `.mypy_cache/` and `.ruff_cache/`;
- `LOCAL_REVIEW/`, `PREVIEW/` and debug/preview exports;
- `WORLD/COMPILED_NAV/OCCUPANCY/` materialized caches;
- `releases/.staging/` and temporary extraction directories.

- [ ] The archive contains the intended root payload and no nested project root.
- [ ] The archive contains the matching manifest, schemas, registries, runtime, tests, tools and validation assets.
- [ ] The archive is freshly extracted into a clean temporary directory.
- [ ] Tests and required audits pass from the fresh extraction.
- [ ] Central integrity reports `release_clean=true` from the fresh extraction.

## 6. Closeout

- [ ] Update `CENTRAL_MANIFEST.json` only after the implementation and acceptance gates agree.
- [ ] Update `HANDOFF.md` with the final status, verification results, artifact path and next task.
- [ ] Update `ROADMAP.md` if the accepted milestone or next milestone changed.
- [ ] Confirm the release archive path and checksum in the handoff.
- [ ] Leave the working tree understandable; do not silently discard unrelated user changes.

If any required gate is incomplete, keep the status as acceptance-pending or release-pending and do not promote the package as canonical.

