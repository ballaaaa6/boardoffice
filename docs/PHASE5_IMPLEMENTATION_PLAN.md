# GDS Phase 5 Lean Central Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the validated Character/Action/VFX, Character Identity, and World Direction cores into one lean central runtime package while preserving each domain byte-for-byte and adding a single integrated facade.

**Architecture:** The release has two isolated domains: `CHARACTER/` and `WORLD/`. Human-facing identity metadata lives under `CHARACTER/IDENTITY/`. `RUNTIME/central_core.py` composes the existing CharacterSystem, CharacterIdentityResolver, FloorRenderer, LayoutCore, and DirectionCore without coupling their internal registries. World RAW floor audit images are intentionally omitted because canonical world blobs are sufficient for runtime floor assembly; recipe provenance remains in registries and raw recipe revalidation stays available in the Phase 3 source package.

**Tech Stack:** Python 3, Pillow, JSON, pytest, deterministic ZIP packaging.

**Spec:** `/mnt/data/docs/superpowers/specs/2026-08-28-gds-central-core-design.md`

## Global Constraints

- Character runtime payload must remain byte-identical to `GDS_CHARACTER_ACTION_SYSTEM_FINAL_CENTRAL_VFX_v1.3.1` for canonical registries, runtime modules, and assets.
- Character identity cards and aliases must remain byte-identical to `GDS_CHARACTER_IDENTITY_CORE_v1.0.0`.
- World canonical assets and runtime registries must remain byte-identical to `GDS_WORLD_DIRECTION_CORE_v1.0.0` except development/audit-only files omitted from the central release.
- Do not include world `RAW/` floor sources in the central runtime release.
- Do not include materialized character action frames, materialized final-floor renders, cache directories, `.pyc`, or `.pytest_cache`.
- Do not add collision, navigation, seat anchors, or Phase 6/7 metadata.
- Workstation directions continue to resolve from layout profiles; Floor03+ inherits `layout.floor02.large`.
- Character `work` direction bridge remains three-way `SE/SW/NW`, with `NE` unsupported and no fallback.
- The integrated facade must accept character number, `CHAR_xxx`, full name, nickname, or canonical character ID.
- Build and ZIP output must be deterministic.

---

### Task 1: Freeze source payload contracts

**Files:**
- Create: `/mnt/data/_phase5_work/tests/test_phase5_source_contracts.py`
- Create: `/mnt/data/_phase5_work/build_phase5.py`

**Interfaces:**
- Consumes: the three Phase 3/4/Character source package roots.
- Produces: deterministic file-selection manifests for `CHARACTER/`, `CHARACTER/IDENTITY/`, and `WORLD/`.

- [ ] Write failing tests requiring the central package skeleton, exact source payload hashes, no RAW world sources, and no caches.
- [ ] Run tests and verify RED because the Phase 5 package does not exist.
- [ ] Implement deterministic copy/build logic selecting only runtime-canonical payload.
- [ ] Run tests and verify GREEN.

### Task 2: Add integrated central facade

**Files:**
- Create: `GDS_CENTRAL_GAME_CORE_v1.0.0/RUNTIME/central_core.py`
- Create: `GDS_CENTRAL_GAME_CORE_v1.0.0/RUNTIME/__init__.py`
- Create: `/mnt/data/_phase5_work/tests/test_phase5_central_runtime.py`

**Interfaces:**
- Produces: `CentralGameCore` with `resolve_character`, `render_character`, `render_floor`, `resolve_workstation_direction`, `resolve_workstation`, and `render_character_at_workstation`.

- [ ] Write failing runtime tests for identity aliases, floor assembly, direction resolution, and integrated work rendering.
- [ ] Verify RED because the facade does not exist.
- [ ] Implement minimal composition-only facade with no duplicated domain logic.
- [ ] Verify GREEN and compare outputs with original domain runtimes.

### Task 3: Central contracts and manifest

**Files:**
- Create: `GDS_CENTRAL_GAME_CORE_v1.0.0/CONTRACTS/central_contract.json`
- Create: `GDS_CENTRAL_GAME_CORE_v1.0.0/CENTRAL_MANIFEST.json`
- Create: `GDS_CENTRAL_GAME_CORE_v1.0.0/SCHEMA/central_manifest.schema.json`
- Create: `/mnt/data/_phase5_work/tests/test_phase5_manifest.py`

**Interfaces:**
- Central manifest records source ZIP hashes, counts, domain boundaries, omitted audit-only RAW payload, and runtime entry point.

- [ ] Write failing manifest/schema tests.
- [ ] Verify RED.
- [ ] Implement contracts/manifest/schema.
- [ ] Verify GREEN.

### Task 4: Release validation and regression

**Files:**
- Create: `GDS_CENTRAL_GAME_CORE_v1.0.0/VALIDATION/self_audit_central.py`
- Create: `GDS_CENTRAL_GAME_CORE_v1.0.0/REPORTS/PHASE5_CENTRAL_AUDIT.json`
- Create: `/mnt/data/_phase5_work/tests/test_phase5_release.py`

**Interfaces:**
- Validates 302 identities, character source fidelity, 25 floor renders, 219 workstation directions, 766 placements, integrated render smoke, and release cleanliness.

- [ ] Write failing release-audit tests.
- [ ] Verify RED.
- [ ] Implement standalone self-audit.
- [ ] Run full regression against the three source packages.

### Task 5: Deterministic packaging

**Files:**
- Create: `GDS_CENTRAL_GAME_CORE_v1.0.0/checksums.sha256`
- Create: `/mnt/data/GDS_CENTRAL_GAME_CORE_v1.0.0.zip`

**Interfaces:**
- Produces final deterministic Phase 5 release.

- [ ] Rebuild central tree twice and compare canonical tree hashes.
- [ ] Remove all cache/generated output files.
- [ ] Generate checksums over release files.
- [ ] Create deterministic ZIP.
- [ ] Fresh-extract ZIP and rerun checksum, tests, self-audit, 25-floor regression, identity resolver smoke, workstation rendering smoke.
- [ ] Repack fresh tree and require byte-identical ZIP.
