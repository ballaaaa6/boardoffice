# TypeScript/JavaScript Runtime Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task with review checkpoints. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Port the single-user live simulation to a strict TypeScript browser runtime that produces the existing Python contract outputs, has no recurring simulation request after bootstrap, and can be packaged as Cloudflare static assets without changing gameplay, canonical data or authored artwork.

**Architecture:** Keep WORLD/, CHARACTER/ and CONTRACTS/ as canonical inputs. Keep Python as the deterministic bundle builder, behavior oracle, validation toolchain and raster fallback while a typed runtime is built in staged behavior families. The typed runtime remains DOM/Canvas/network independent and emits gds.runtime_snapshot.v1 plus gds.runtime_render_state.v1; browser/controller and Cloudflare adapters are added only after parity is green.

**Tech Stack:** TypeScript strict mode, Node ESM, json-schema-to-typescript, Ajv 2020 validation, Vitest, existing Node built-in browser tests, Python pytest/Ruff/audits, Playwright for browser/network checks, Wrangler and the Cloudflare Vitest integration for the deployment slice. The fixed simulation step is 60ms; the first target is the existing floor02 nine-actor bundle.

**Spec:** docs/superpowers/specs/2026-09-03-tsjs-runtime-migration-design.md

## Global Constraints

- Do not edit 00_STARTING_POINT/, canonical PNGs, authored geometry, WorkSeat placement, reference hashes or gameplay timing/policy.
- Canonical data remains in WORLD/, CHARACTER/ and CONTRACTS/; WEB/runtime_simulation_bootstrap.json, WEB/runtime_render_manifest.json and WEB/runtime_assets/ are generated outputs.
- Complete the lean-first source-profile, frame, facade, legacy-caller and contract-freeze prerequisites before switching the live review page to the typed runtime.
- Keep the public BrowserRuntimeCore behavior compatible with create, step, snapshot, renderState, command, serialize, load, replay and destroy.
- Use integer millisecond simulation time and the existing 60ms fixed step; do not add a request-driven tick loop.
- Use the current browser JavaScript as the first reference where it already matches the Python oracle; use python2ts only for isolated pure-code scaffolding.
- Never accept converter output, a successful compile, a generated manifest or a benchmark as proof of behavior parity.
- Compare IDs, labels, clocks, events, frame indices, ownership, dialogue and replay output exactly; allow position tolerance only where documented, with an absolute limit of 1e-6.
- Keep Python, Pillow, raster fallback and the existing browser source mode until all parity, persistence, zero-request, endurance, author-acceptance and release-clean gates pass.
- Each task ends with focused tests, the relevant full tests and a separate commit; no task deletes the old implementation merely because the new code compiles.

## Scope decomposition

The approved spec contains several coupled subsystems. This plan keeps them in one dependency-ordered migration but treats each block as an independently testable subproject:

1. contract/toolchain foundation;
2. deterministic primitives and world services;
3. actor, effects and visual selection;
4. speech, conversation, persistence and runtime orchestration;
5. browser source mode, Cloudflare packaging and release verification.

Do not run a later block before the previous block exit gate is recorded.

## Current boundary to preserve

| Current file | Typed target | Existing public symbols |
| --- | --- | --- |
| WEB/runtime_simulation_prng.js | WEB/src/runtime/prng.ts | stableHash64, splitmix64Next, nextD6FromState, deriveEmotionRngState, DeterministicRng |
| WEB/runtime_simulation_clock.js | WEB/src/runtime/clock.ts | FixedStepClock |
| WEB/runtime_simulation_state.js | WEB/src/runtime/state.ts | snapshot constants, validateRuntimeSnapshot, cloneJsonValue, cloneRuntimeSnapshot |
| WEB/runtime_simulation_navigation.js | WEB/src/runtime/navigation.ts | BrowserNavigation, BrowserNavigationError, normalizeUv, uvKey |
| WEB/runtime_simulation_work_seat.js | WEB/src/runtime/work-seat.ts | BrowserWorkSeatReducer, SEAT_TRANSITION_MS |
| WEB/runtime_simulation_visual_selection.js | WEB/src/runtime/visual-selection.ts | BrowserVisualSelection |
| WEB/runtime_simulation_effects.js | WEB/src/runtime/effects.ts | BrowserEffectsReducer |
| WEB/runtime_simulation_actor.js | WEB/src/runtime/actor.ts | BrowserActorReducer, timing constants |
| WEB/runtime_simulation_speech.js | WEB/src/runtime/speech.ts | BrowserSpeechReducer |
| WEB/runtime_simulation_core.js | WEB/src/runtime/core.ts | BrowserRuntimeCore |
| WEB/runtime_canvas_renderer.js | WEB/src/renderer/canvas.ts | RuntimeCanvasRenderer |
| WEB/runtime_render_client.js | WEB/src/browser/python-client.ts | RuntimeRenderClient compatibility path |

The typed targets start as parallel modules so the current ES modules remain a rollback path. Import switches happen only in the integration task.

---

### Task 1: Add the TypeScript toolchain and a compiling contract boundary

**Files:**

- Modify: WEB/package.json
- Create: WEB/package-lock.json through the package manager, WEB/tsconfig.json, WEB/tsconfig.build.json, WEB/vitest.config.ts
- Create: WEB/src/contracts/constants.ts, WEB/tests/toolchain_smoke.test.ts

**Interfaces:**

- Produces npm --prefix WEB run typecheck, npm --prefix WEB run test:ts, npm --prefix WEB run generate:contracts and npm --prefix WEB run build:web script names for later tasks.
- Produces RUNTIME_SNAPSHOT_SCHEMA, RUNTIME_SNAPSHOT_VERSION, RENDER_STATE_SCHEMA, RENDER_STATE_VERSION, BROWSER_BUNDLE_SCHEMA and BROWSER_BUNDLE_VERSION constants with literal string types.

- [ ] **Step 1: Write the failing toolchain smoke test**

~~~
import { describe, expect, it } from "vitest";
import {
  BROWSER_BUNDLE_SCHEMA,
  RENDER_STATE_SCHEMA,
  RUNTIME_SNAPSHOT_SCHEMA,
} from "../src/contracts/constants.js";

describe("TypeScript contract toolchain", () => {
  it("exposes the frozen runtime contract identifiers", () => {
    expect(RUNTIME_SNAPSHOT_SCHEMA).toBe("gds.runtime_snapshot.v1");
    expect(RENDER_STATE_SCHEMA).toBe("gds.runtime_render_state.v1");
    expect(BROWSER_BUNDLE_SCHEMA).toBe("gds.browser_runtime_bundle.v1");
  });
});
~~~

- [ ] **Step 2: Run the test to verify the missing toolchain fails**

Run: npm --prefix WEB run test:ts -- --run tests/toolchain_smoke.test.ts

Expected: FAIL because the test:ts script, Vitest configuration and imported module do not exist.

- [ ] **Step 3: Install the toolchain dependencies**

Run: npm --prefix WEB install --save-dev typescript json-schema-to-typescript vitest @types/node

Run: npm --prefix WEB install ajv

Commit the generated WEB/package-lock.json so CI and local builds resolve the same dependency tree.

- [ ] **Step 4: Add strict ESM TypeScript configuration**

Create WEB/tsconfig.json with target ES2022, NodeNext modules, strict mode, noUncheckedIndexedAccess, exactOptionalPropertyTypes, verbatimModuleSyntax, resolveJsonModule, rootDir ., and includes for src, tests and vitest.config.ts. Create WEB/tsconfig.build.json extending it with rootDir src, outDir dist and include src/**/*.ts only. Create WEB/vitest.config.ts with a Node environment and tests/**/*.test.ts include pattern. Retain type module in WEB/package.json.

Extend WEB/package.json with:

~~~
"scripts": {
  "generate:contracts": "node scripts/generate_contract_types.mjs",
  "check:contracts": "npm run generate:contracts && git -C .. diff --exit-code -- WEB/src/contracts/generated WEB/src/contracts/schema-catalog.ts",
  "typecheck": "tsc --noEmit",
  "test:ts": "vitest run",
  "build:web": "tsc -p tsconfig.build.json"
}
~~~

- [ ] **Step 5: Add constants and run the focused test**

Create WEB/src/contracts/constants.ts:

~~~
export const RUNTIME_SNAPSHOT_SCHEMA = "gds.runtime_snapshot.v1" as const;
export const RUNTIME_SNAPSHOT_VERSION = "1.0.0" as const;
export const RENDER_STATE_SCHEMA = "gds.runtime_render_state.v1" as const;
export const RENDER_STATE_VERSION = "1.0.0" as const;
export const BROWSER_BUNDLE_SCHEMA = "gds.browser_runtime_bundle.v1" as const;
export const BROWSER_BUNDLE_VERSION = "1.0.0" as const;
~~~

Run: npm --prefix WEB run typecheck

Run: npm --prefix WEB run test:ts -- --run tests/toolchain_smoke.test.ts

Expected: PASS.

- [ ] **Step 6: Commit the compiling foundation**

~~~
git add WEB/package.json WEB/package-lock.json WEB/tsconfig.json WEB/vitest.config.ts WEB/src/contracts/constants.ts WEB/tests/toolchain_smoke.test.ts
git commit -m "build: add strict TypeScript runtime toolchain"
~~~

**Exit gate:** TypeScript and Vitest run in WEB, the constants compile as literal types, the existing node --test TESTS/browser_runtime_test.mjs remains green, and no runtime/browser file has been switched.

### Task 2: Generate schema types and add runtime JSON validation

**Files:**

- Create: SCHEMA/browser_runtime_bundle.schema.json
- Modify: RUNTIME/browser_bundle_contract.py, TESTS/test_browser_bundle_contract.py
- Create: WEB/scripts/generate_contract_types.mjs
- Create: WEB/src/contracts/generated/ outputs, WEB/src/contracts/schema-catalog.ts, WEB/src/contracts/validation.ts, WEB/src/contracts/types.ts
- Create: WEB/tests/contracts_generation.test.ts, WEB/tests/contracts_validation.test.ts
- Modify: WEB/package.json

**Interfaces:**

- generate_contract_types.mjs reads every SCHEMA/**/*.schema.json, emits one type module preserving relative schema names, emits a schema catalog and exits nonzero when a schema cannot compile.
- BrowserRuntimeBundle is the typed top-level bundle with required keys schema, version, builder, bundle_revision, source_hashes, floor_id, world, work_seats, employees, characters, assets, actions, frame_profile, frame_rules, dialogue, effects, visual_catalog, conversation, simulation and initial_snapshot.
- validateContract<T>(schemaId: ContractSchemaId, value: unknown): T returns the validated value or throws ContractValidationError containing schemaId and Ajv error details.
- assertBrowserRuntimeBundle(value: unknown): asserts value is BrowserRuntimeBundle rejects unknown schema/version and unresolved required top-level fields.
- WEB/src/contracts/types.ts re-exports generated schema types and defines the cross-channel aliases used by later tasks: Uv = readonly [number, number], Direction = "NW" | "SE" | "SW" | "NE", WorldInputs = BrowserRuntimeBundle["world"], WorkSeatInputs = BrowserRuntimeBundle["work_seats"], EmployeeInputs = BrowserRuntimeBundle["employees"], AssetInputs = BrowserRuntimeBundle["assets"], CharacterInputs = BrowserRuntimeBundle["characters"], and RuntimeSnapshot = { schema: "gds.runtime_snapshot.v1"; version: "1.0.0"; actor_snapshot: ActorSnapshot; speech_snapshot: SpeechSnapshot; conversation_snapshot: ConversationSnapshot }.

- [ ] **Step 1: Write the failing bundle-schema regression**

Add a Python test that loads WEB/runtime_simulation_bootstrap.json, validates it through the updated RUNTIME.browser_bundle_contract, and rejects a copy with schema, version or initial_snapshot removed. Add the matching TypeScript shape:

~~~
import { readFile } from "node:fs/promises";

async function readCheckedInBundle(): Promise<unknown> {
  const text = await readFile(new URL("../runtime_simulation_bootstrap.json", import.meta.url), "utf8");
  return JSON.parse(text) as unknown;
}

it("accepts the checked-in floor02 bundle and rejects a missing required field", async () => {
  const bundle = await readCheckedInBundle();
  expect(() => assertBrowserRuntimeBundle(bundle)).not.toThrow();
  const broken = structuredClone(bundle) as Record<string, unknown>;
  delete broken.initial_snapshot;
  expect(() => assertBrowserRuntimeBundle(broken)).toThrow(/initial_snapshot/);
});
~~~

- [ ] **Step 2: Run the tests to identify the missing schema and validator**

Run: python -m pytest -q TESTS/test_browser_bundle_contract.py

Run: npm --prefix WEB run test:ts -- --run tests/contracts_validation.test.ts

Expected: the Python test reports the missing bundle-schema integration and the TypeScript test cannot import the validator.

- [ ] **Step 3: Freeze the bundle schema from the existing checked-in output**

Create SCHEMA/browser_runtime_bundle.schema.json with id gds.browser_runtime_bundle.v1, version 1.0.0, additionalProperties false and the required top-level keys from the Interfaces block. Reuse existing actor, persistence and render contract identifiers for nested channels; do not invent fields or change the checked-in bundle. Update the Python contract validator to validate the same required keys before its existing source/hash checks.

- [ ] **Step 4: Implement deterministic type and schema generation**

Create WEB/scripts/generate_contract_types.mjs using fs/promises, path and json-schema-to-typescript with stable sorted traversal. Resolve the repository root from import.meta.url, write only under WEB/src/contracts/generated, write the schema catalog from sorted id values, and fail if an id is duplicated.

The generated output is checked in as derived code. Add check:contracts so a second generation fails if it changes the generated tree.

- [ ] **Step 5: Add Ajv 2020 validation**

Create WEB/src/contracts/validation.ts with Ajv2020({ allErrors: true, strict: true }), register the generated schema catalog once, map schema IDs to compiled validators, and throw ContractValidationError with a stable instancePath/keyword summary. Export validateContract, assertBrowserRuntimeBundle and isContractValidationError.

- [ ] **Step 6: Add generation and invalid-input tests**

The tests must assert that the number of generated schema modules equals the number of schema files, a second generation leaves no diff, invalid schema/version/required fields fail, and the checked-in bundle passes. Use the real bundle reader only in Node/Vitest tests; browser runtime modules receive already loaded JSON.

Run: npm --prefix WEB run generate:contracts

Run: npm --prefix WEB run typecheck

Run: npm --prefix WEB run test:ts -- --run tests/contracts_generation.test.ts tests/contracts_validation.test.ts

Run: python -m pytest -q TESTS/test_browser_bundle_contract.py

- [ ] **Step 7: Commit the contract boundary**

~~~
git add SCHEMA/browser_runtime_bundle.schema.json RUNTIME/browser_bundle_contract.py TESTS/test_browser_bundle_contract.py WEB/package.json WEB/scripts/generate_contract_types.mjs WEB/src/contracts WEB/tests/contracts_generation.test.ts WEB/tests/contracts_validation.test.ts
git commit -m "feat: generate and validate browser runtime contracts"
~~~

**Exit gate:** the current generated bundle validates in Python and TypeScript, generation is deterministic, generated files are clearly derived, and all existing Python/browser tests remain green.

### Task 3: Add a shared parity comparator and migration fixtures

**Files:**

- Create: WEB/src/contracts/parity.ts, WEB/tests/parity_comparator.test.ts
- Modify: TESTS/browser_runtime_parity_runner.mjs, TESTS/test_browser_parity_trace.py
- Create: TESTS/fixtures/tsjs_parity_cases/README.md and one small checked-in fixture per required behavior family as that family is migrated

**Interfaces:**

~~~
export type JsonValue =
  | null | boolean | number | string | JsonValue[]
  | { [key: string]: JsonValue };

export interface JsonMismatch {
  path: string;
  expected: JsonValue | undefined;
  actual: JsonValue | undefined;
  reason: "missing" | "unexpected" | "value" | "type" | "number_tolerance";
}

export interface ParityCompareOptions {
  positionTolerance: number;
  exactPaths: readonly string[];
}

export function firstJsonMismatch(
  expected: JsonValue,
  actual: JsonValue,
  options: ParityCompareOptions,
): JsonMismatch | null;

export function compareParityCheckpoint(
  expected: JsonValue,
  actual: JsonValue,
): JsonMismatch | null;
~~~

- [ ] **Step 1: Write comparator tests for exact and tolerant fields**

~~~
it("reports the first stable JSON path and only tolerates position floats", () => {
  const expected = { actors: [{ id: "A", position: { x: 1, y: 2 } }], events: [] };
  const actual = { actors: [{ id: "A", position: { x: 1.0000005, y: 2 } }], events: [] };
  expect(firstJsonMismatch(expected, actual, { positionTolerance: 1e-6, exactPaths: ["events"] })).toBeNull();
  expect(firstJsonMismatch(expected, { ...actual, events: [{ type: "wrong" }] }, { positionTolerance: 1e-6, exactPaths: ["events"] })?.path).toBe("events[0].type");
});
~~~

- [ ] **Step 2: Run the comparator test and confirm it fails**

Run: npm --prefix WEB run test:ts -- --run tests/parity_comparator.test.ts

Expected: FAIL because the comparator module is absent.

- [ ] **Step 3: Implement deterministic recursive comparison**

Sort object keys before comparison, preserve array order, report the first mismatch, and apply 1e-6 only to documented position coordinate paths. Do not ignore IDs, event ordering, clocks, frame indices, ownership, dialogue, bubble offsets or replay fields.

- [ ] **Step 4: Make the existing parity runner selectable without changing its JSON output**

Add an environment-selected entry point while retaining the current default:

~~~
const entry = process.env.GDS_BROWSER_RUNTIME_ENTRY ?? "../WEB/runtime_simulation_core.js";
const { BrowserRuntimeCore } = await import(entry);
~~~

The Python test continues to invoke the same runner and compares the same gds.browser_runtime_parity_result.v1 fields. Add a test that reports the first mismatch path when a deliberately changed checkpoint is supplied.

- [ ] **Step 5: Run the baseline parity suite and commit the harness**

Run: python -m pytest -q TESTS/test_browser_parity_trace.py

Run: node --test TESTS/browser_runtime_test.mjs

~~~
git add WEB/src/contracts/parity.ts WEB/tests/parity_comparator.test.ts TESTS/browser_runtime_parity_runner.mjs TESTS/test_browser_parity_trace.py TESTS/fixtures/tsjs_parity_cases
git commit -m "test: add deterministic TypeScript parity comparison"
~~~

**Exit gate:** the old JavaScript remains the passing reference implementation and every future typed checkpoint can identify the first contract mismatch without weakening comparison rules.

### Task 4: Port deterministic primitives and state codecs

**Files:**

- Create: WEB/src/runtime/prng.ts, WEB/src/runtime/clock.ts, WEB/src/runtime/state.ts, WEB/tests/runtime_prng.test.ts, WEB/tests/runtime_clock.test.ts, WEB/tests/runtime_state.test.ts
- Modify: WEB/src/contracts/types.ts
- Reference only: WEB/runtime_simulation_prng.js, WEB/runtime_simulation_clock.js, WEB/runtime_simulation_state.js

**Interfaces:**

~~~
export function stableHash64(...parts: readonly unknown[]): bigint;
export function splitmix64Next(state: bigint): { state: bigint; value: bigint };
export function nextD6FromState(state: bigint): { state: bigint; roll: number };
export function deriveEmotionRngState(simulationSeed: string, rootEventCounter?: number): bigint;

export class DeterministicRng {
  constructor(seed: string, options?: { state?: bigint | null });
  nextUint64(): bigint;
  nextUint32(): number;
  nextFloat(): number;
  choice<T>(items: readonly T[]): T;
  d6(): number;
}

export class FixedStepClock {
  constructor(options?: { stepMs?: number; maxCatchupMs?: number });
  readonly simulationClockMs: number;
  pushElapsed(elapsedMs: number): number[];
  reset(options?: { simulationClockMs?: number }): void;
}
~~~

- [ ] **Step 1: Copy the known-answer tests into Vitest**

Use the current expected PRNG sequence [2382527216, 871612171, 941754517, 3825408319, 900664123], d6() === 3, and clock behavior pushElapsed(200) === [60, 60, 60], followed by bounded catch-up at simulationClockMs === 360.

- [ ] **Step 2: Run the primitive tests and confirm they fail**

Run: npm --prefix WEB run test:ts -- --run tests/runtime_prng.test.ts tests/runtime_clock.test.ts

Expected: FAIL because typed modules do not exist.

- [ ] **Step 3: Port the PRNG without changing integer widths**

Use bigint for the uint64 state, retain the exact splitmix constants and rejection-sampled d6 logic, reject an empty seed, and return the current JavaScript error categories for invalid choice input. Do not replace the PRNG with Math.random.

- [ ] **Step 4: Port the fixed-step clock and JSON state helpers**

Keep the accumulator remainder and max-catchup policy identical. validateRuntimeSnapshot must retain the current v1/v2 speech migration and synchronized actor IDs/clocks. cloneRuntimeSnapshot must validate before cloning and return an independent JSON-safe value.

- [ ] **Step 5: Add direct parity vectors and run the gate**

Compare the typed functions with the existing JavaScript for seeds, boundary elapsed values, d6 state, malformed snapshots and speech-v1 migration. Run npm --prefix WEB run typecheck and all focused tests.

- [ ] **Step 6: Commit the primitive port**

~~~
git add WEB/src/contracts/types.ts WEB/src/runtime/prng.ts WEB/src/runtime/clock.ts WEB/src/runtime/state.ts WEB/tests/runtime_prng.test.ts WEB/tests/runtime_clock.test.ts WEB/tests/runtime_state.test.ts
git commit -m "feat: port deterministic runtime primitives to TypeScript"
~~~

**Exit gate:** primitive outputs and state migration match the current JavaScript and Python fixtures; no browser integration switch occurs.

### Task 5: Port navigation, occupancy and WorkSeat services

**Files:**

- Create: WEB/src/runtime/navigation.ts, WEB/src/runtime/work-seat.ts, WEB/tests/runtime_navigation.test.ts, WEB/tests/runtime_work_seat.test.ts
- Modify: WEB/src/contracts/types.ts
- Reference: WEB/runtime_simulation_navigation.js, WEB/runtime_simulation_work_seat.js, TESTS/browser_runtime_test.mjs

**Interfaces:**

~~~
export class BrowserNavigation {
  constructor(input: { world: WorldInputs; workSeats?: WorkSeatInputs | null });
  isWalkable(u: number, v?: number): boolean;
  portal(floorId?: string): PortalInput;
  workstationAccess(workstationId: string): NavigationAccess;
  uvCellCenterToPixel(u: number, v?: number): [number, number];
  directionForStep(startUv: Uv, targetUv: Uv): Direction;
  findPath(startUv: Uv, goalUv: Uv, options?: { blockedCells?: readonly Uv[] }): PathResult;
  compressPath(pathCellsUv: readonly Uv[]): Uv[];
  routeDurationMs(pathCellsUv: readonly Uv[], speedMultiplier: number): number;
  pathPose(pathCellsUv: readonly Uv[], elapsedMs: number, speedMultiplier: number): PathPose;
  portalPose(route: RouteRecord, elapsedMs: number): PortalPose;
}

export class BrowserWorkSeatReducer {
  constructor(input: { workSeats: WorkSeatInputs; employees: EmployeeInputs; assets: AssetInputs; characters: CharacterInputs });
  seat(floorId: string, workstationId: string): WorkSeatInput;
  navigationAccess(workstationId: string): NavigationAccess;
  visualCharacterAnchor(floorId: string, workstationId: string, characterId: string): [number, number];
  pcFrameCount(workstationId: string): number;
  seatTransitionRecord(input: SeatTransitionInput): SeatTransitionRecord;
  step(actor: ActorSnapshot, seatState?: SeatState, context?: SeatContext, elapsedMs?: number): SeatStepResult;
}
~~~

- [ ] **Step 1: Add authored floor02 known-answer tests**

Assert isWalkable(189, 103), rejection of (202, 47), portal inside cell [240, 182], authored A* path length 144, target [253, 182], WorkSeat anchor [213, 304] for ws2/TP_009, and PC frame count 1.

- [ ] **Step 2: Run the tests and confirm the typed services are absent**

Run: npm --prefix WEB run test:ts -- --run tests/runtime_navigation.test.ts tests/runtime_work_seat.test.ts

Expected: FAIL at module import.

- [ ] **Step 3: Port navigation with stable cell/path ordering**

Port the min-heap tie-break order, cardinal neighbor order, UV normalization, route compression, portal fade/pose and cumulative distance calculations exactly. Keep BrowserNavigationError for invalid or unreachable routes.

- [ ] **Step 4: Port WorkSeat as a metadata/state service**

Keep image-free anchors, PC frame metadata, seat transition duration 240ms and the existing ownership/transition boundary. The service must not load PNGs or mutate assignment ownership.

- [ ] **Step 5: Run Python/browser module checkpoints**

Run the existing Python navigation/occupancy/WorkSeat audits, the new Vitest tests and node --test TESTS/browser_runtime_test.mjs. Compare typed and old-JS path/pose JSON for the known route.

- [ ] **Step 6: Commit world services**

~~~
git add WEB/src/contracts/types.ts WEB/src/runtime/navigation.ts WEB/src/runtime/work-seat.ts WEB/tests/runtime_navigation.test.ts WEB/tests/runtime_work_seat.test.ts
git commit -m "feat: port browser navigation and WorkSeat services"
~~~

**Exit gate:** floor02 path, portal, occupancy-facing metadata and WorkSeat anchors match exactly; no actor reducer or UI switch occurs.

### Task 6: Port actor, effects and visual-selection behavior

**Files:**

- Create: WEB/src/runtime/visual-selection.ts, WEB/src/runtime/effects.ts, WEB/src/runtime/actor.ts, WEB/tests/runtime_visual_selection.test.ts, WEB/tests/runtime_effects.test.ts, WEB/tests/runtime_actor.test.ts
- Modify: WEB/src/contracts/types.ts
- Reference: WEB/runtime_simulation_visual_selection.js, WEB/runtime_simulation_effects.js, WEB/runtime_simulation_actor.js

**Interfaces:**

~~~
export class BrowserVisualSelection {
  constructor(input: { catalog: VisualCatalog });
  catalog(): VisualCatalog;
  initialChannelState(channel: VisualChannel): VisualChannelState;
  select(state: VisualChannelState, input: VisualSelectionRequest): VisualSelectionResult;
  clearActive(state: VisualChannelState, input: { channel: VisualChannel; eventId?: string | null }): VisualChannelState;
}

export class BrowserEffectsReducer {
  constructor(input: { employees: EmployeeInputs; effects: EffectInputs; visualSelection?: BrowserVisualSelection | null });
  presentation(actor: ActorSnapshot, sampleMs: number): EffectPresentation;
  channels(actor: ActorSnapshot, sampleMs: number): EffectChannels;
}

export class BrowserActorReducer {
  constructor(input: { employees: EmployeeInputs; navigation: BrowserNavigation; workSeat: BrowserWorkSeatReducer; visualSelection?: BrowserVisualSelection | null });
  step(actor: ActorSnapshot, context: ActorStepContext, elapsedMs: number, commands?: readonly RuntimeCommand[]): ActorStepResult;
}
~~~

- [ ] **Step 1: Add behavior-family failing tests**

Cover deterministic visual bags, active-binding persistence, 11 VFX/6 HumanBall catalog coverage, no image/base64 output, normal work stamina (99957 milli-stamina and remainder 440 after the known 60ms step), frame clocks, request_home, seat exit and the Critical boundary.

- [ ] **Step 2: Run the focused tests before the typed implementation**

Run: npm --prefix WEB run test:ts -- --run tests/runtime_visual_selection.test.ts tests/runtime_effects.test.ts tests/runtime_actor.test.ts

Expected: FAIL because the typed reducers are absent.

- [ ] **Step 3: Port visual selection and effects as metadata-only reducers**

Preserve per-actor/per-channel shuffle-bag generation, event-admission selection, active binding persistence and catalog profile checks. Reject per-frame reselection and never attach image data to state.

- [ ] **Step 4: Port actor transitions from the existing browser implementation**

Keep route phases, seat transitions, action/frame clocks, work-loop clock, stamina remainder, event counters, talk overlay ownership and explicit command behavior. Do not add automatic wander behavior or alter the existing zero-weight legacy metadata.

- [ ] **Step 5: Run parity at every 60ms checkpoint**

Use TOOLS/export_browser_parity_trace.py for spawn_work, critical_home, effects_humanball and home_route; run the typed reducer through a small test adapter and compare snapshots/render metadata with firstJsonMismatch.

- [ ] **Step 6: Commit actor/effects behavior**

~~~
git add WEB/src/contracts/types.ts WEB/src/runtime/visual-selection.ts WEB/src/runtime/effects.ts WEB/src/runtime/actor.ts WEB/tests/runtime_visual_selection.test.ts WEB/tests/runtime_effects.test.ts WEB/tests/runtime_actor.test.ts
git commit -m "feat: port typed actor and visual runtime reducers"
~~~

**Exit gate:** actor state, stamina, movement, frame clocks, effect bindings and visual catalog behavior match the existing browser/Python checkpoints.

### Task 7: Port speech, conversation and social event timing

**Files:**

- Create: WEB/src/runtime/speech.ts, WEB/tests/runtime_speech.test.ts
- Modify: WEB/src/runtime/actor.ts, WEB/src/contracts/types.ts
- Reference: WEB/runtime_simulation_speech.js, CONTRACTS/speech_scheduler.json, CONTRACTS/conversation_behavior.json, TESTS/test_browser_parity_trace.py

**Interfaces:**

~~~
export class BrowserSpeechReducer {
  constructor(input: {
    employees: EmployeeInputs;
    conversation: ConversationInputs;
    dialogue: DialogueInputs;
  });
  ensureSnapshotShape(snapshot: RuntimeSnapshot): RuntimeSnapshot;
  applyCommand(snapshot: RuntimeSnapshot, command: SpeechCommand, timestampMs: number): SpeechCommandResult;
  processAt(snapshot: RuntimeSnapshot, actorSnapshot: ActorSnapshot, conversationSnapshot: ConversationSnapshot, nowMs: number, events: RuntimeEvent[], locale: string, seed: string): void;
  step(snapshot: RuntimeSnapshot, input: SpeechStepInput): SpeechStepResult;
  dialogueForActor(snapshot: RuntimeSnapshot, employeeId: string, sampleMs: number): DialoguePresentation;
}
~~~

- [ ] **Step 1: Add failing speech/conversation tests**

Cover one actor slot per actor, atomic pair claims, queue contention, v-axis endpoint order, SW/NE facings, bubble schedules, speech-v1 migration, d6 emotion parity and return-to-work cleanup.

- [ ] **Step 2: Run the tests before the typed speech reducer exists**

Run: npm --prefix WEB run test:ts -- --run tests/runtime_speech.test.ts

Expected: FAIL at module import.

- [ ] **Step 3: Port snapshot shape and resource-claim migration**

Keep actor_slots, pending_requests, resource_claims, legacy lane projection and actor/speech/conversation clock synchronization exactly as the current v2 browser state contract requires.

- [ ] **Step 4: Port request admission, planning and timing**

Preserve partner selection, reserved physical cells, queue timeout, category/locale bags, bubble fit metadata, session timing, emotion seed namespace and explicit cancel/failure behavior. Speech owns timing; actor owns route movement.

- [ ] **Step 5: Run full social parity traces**

Run the talk_pair trace and compare every actor, active session, schedule, bubble, event and render row. A difference in event order, time, participant ownership or dialogue ID blocks the task.

- [ ] **Step 6: Commit social behavior**

~~~
git add WEB/src/contracts/types.ts WEB/src/runtime/actor.ts WEB/src/runtime/speech.ts WEB/tests/runtime_speech.test.ts
git commit -m "feat: port speech and conversation runtime behavior"
~~~

**Exit gate:** social traces match the Python oracle and existing browser implementation, including V-axis geometry and per-actor bubble ownership.

### Task 8: Compose the typed core and implement exact persistence/replay

**Files:**

- Create: WEB/src/runtime/core.ts, WEB/src/runtime/persistence.ts, WEB/tests/runtime_core.test.ts, WEB/tests/runtime_persistence.test.ts
- Modify: TESTS/browser_runtime_parity_runner.mjs, TESTS/test_browser_parity_trace.py, WEB/package.json
- Reference: WEB/runtime_simulation_core.js, SCHEMA/runtime_persistence.schema.json, SCHEMA/runtime_replay.schema.json

**Interfaces:**

~~~
export interface BrowserRuntimeCoreOptions {
  bundle?: BrowserRuntimeBundle;
  bundleUrl?: string;
  floorId?: string;
  seed?: string;
  fetchImpl?: typeof fetch;
}

export class BrowserRuntimeCore {
  static create(options?: BrowserRuntimeCoreOptions): Promise<BrowserRuntimeCore>;
  step(elapsedMs: number, commands?: RuntimeCommandSet): StepResult;
  snapshot(): RuntimeSnapshot;
  renderState(atMs?: number): RuntimeRenderState;
  command(command: RuntimeCommand): void;
  serialize(): RuntimeSavePackage;
  load(payload: RuntimeSavePackage): void;
  replay(payload: ReplayPackage): ReplayResult;
  destroy(): void;
}
~~~

- [ ] **Step 1: Write core and persistence failing tests**

Assert one bootstrap fetch, fixed-step clock behavior, snapshot/render-state schemas, command history limit 2048, load rejection before mutation for wrong schema/floor/bundle revision, save/load round trip and replay equality.

- [ ] **Step 2: Run the failing core tests**

Run: npm --prefix WEB run test:ts -- --run tests/runtime_core.test.ts tests/runtime_persistence.test.ts

Expected: FAIL because the typed core and persistence modules are absent.

- [ ] **Step 3: Compose reducers behind a DOM-free core**

Load and validate the bundle exactly once, create fixed clock/PRNG/world/actor/speech/effects services, advance only 60ms slices, build one snapshot and one metadata-only render state per slice, and return ordered events without consulting the network.

- [ ] **Step 4: Implement versioned save/load/replay**

Store schema, version, floor, bundle revision, initial snapshot, current snapshot and explicit step/command trace. Validate the whole package before mutating live state; replay from the stored initial snapshot through step() and bound live diagnostic history.

- [ ] **Step 5: Switch the parity runner to the typed build output**

Add build:runtime to emit WEB/dist, make the runner import WEB/dist/runtime/core.js when GDS_BROWSER_RUNTIME_ENTRY=typed, and make the Python parity test run the build before typed checkpoints. Keep the default old-JS entry until the typed gate is green.

- [ ] **Step 6: Run the full typed parity matrix**

Run typed traces for spawn/work, home route, talk pair, effects/HumanBall, critical/home, speech contention, save/load and replay. Compare every checkpoint with Python using the shared comparator, then run the old Node tests and the complete Python suite.

- [ ] **Step 7: Commit the typed core**

~~~
git add WEB/src/runtime/core.ts WEB/src/runtime/persistence.ts WEB/tests/runtime_core.test.ts WEB/tests/runtime_persistence.test.ts TESTS/browser_runtime_parity_runner.mjs TESTS/test_browser_parity_trace.py WEB/package.json
git commit -m "feat: compose typed browser runtime with replay"
~~~

**Exit gate:** typed core and Python oracle produce identical accepted traces, persistence is versioned and deterministic, and the old browser path is still available.

### Task 9: Integrate typed browser source mode and the Canvas boundary

**Files:**

- Create: WEB/src/browser/controller.ts, WEB/src/browser/network-instrumentation.ts, WEB/src/renderer/canvas.ts
- Modify: WEB/runtime_review.html, WEB/runtime_canvas_renderer.js, WEB/runtime_render_client.js
- Create: TESTS/test_browser_source_mode.py, WEB/tests/browser_controller.test.ts

**Interfaces:**

~~~
export type RuntimeSourceMode = "browser" | "python";
export type RendererMode = "canvas" | "raster";

export class BrowserRuntimeController {
  constructor(input: {
    source: RuntimeSourceMode;
    renderer: RendererMode;
    bundleUrl: string;
    coreFactory: typeof BrowserRuntimeCore.create;
  });
  start(): Promise<void>;
  command(command: RuntimeCommand): void;
  save(): RuntimeSavePackage;
  load(payload: RuntimeSavePackage): void;
  stop(): void;
}
~~~

- [ ] **Step 1: Add failing UI/network tests**

Instrument fetch and assert Browser mode loads the bootstrap once, advances locally, performs zero /api/tick requests and zero image/base64 requests during stepping. Assert Python mode still constructs RuntimeRenderClient and retains the existing fallback behavior.

- [ ] **Step 2: Run the tests against the current page**

Run: python -m pytest -q TESTS/test_browser_source_mode.py

Expected: the new Browser-mode assertions fail because the review page has no typed controller/source selector.

- [ ] **Step 3: Add the explicit source/renderer controller**

Browser mode owns requestAnimationFrame, an accumulator and fixed 60ms core.step() calls. It passes core.renderState() to Canvas and never creates the Python render client. Python mode remains explicit and owns its current polling/raster lifecycle.

- [ ] **Step 4: Type the Canvas consumer without moving gameplay into rendering**

Make RuntimeCanvasRenderer accept RuntimeRenderState, use generated manifest policy for bubble sizes/anchors, retain interpolation at display time and keep all image loading in the renderer. Remove hard-coded policy only after manifest and screenshot parity tests pass.

- [ ] **Step 5: Add local persistence and explicit fallback UI**

Use a namespaced local-storage key containing the bundle revision and save package. On bundle validation failure, show an explicit error and a Python-source option; do not silently fetch /api/tick as recovery.

- [ ] **Step 6: Run browser source-mode verification**

Run the existing runtime web tests, the network-counter test, all typed parity traces, Canvas/Raster presentation QA and the required navigation/occupancy/WorkSeat/Phase 6/Central/F2/conversation audits.

- [ ] **Step 7: Commit browser integration**

~~~
git add WEB/src/browser WEB/src/renderer/canvas.ts WEB/runtime_review.html WEB/runtime_canvas_renderer.js WEB/runtime_render_client.js TESTS/test_browser_source_mode.py WEB/tests/browser_controller.test.ts
git commit -m "feat: add typed browser-owned runtime source mode"
~~~

**Exit gate:** Browser mode is the default candidate, performs no recurring simulation request after bootstrap, Canvas consumes typed metadata, Python/raster remains selectable, and the author can compare both modes.

### Task 10: Package for Cloudflare and run release gates

**Files:**

- Create: WEB/wrangler.jsonc, WEB/tests/worker_smoke.test.ts, WEB/scripts/check_runtime_bundle.mjs, WEB/README_DEPLOY.md
- Modify: WEB/package.json, .gitignore, HANDOFF.md, ROADMAP.md
- Use existing: WEB/dist, generated bootstrap/render manifest/assets, docs/RELEASE_CHECKLIST.md

**Interfaces:**

- npm --prefix WEB run build:web produces only deployable HTML/ES modules/generated data under WEB/dist.
- npm --prefix WEB run check:deploy rejects Node-only imports, Python/Pillow references, missing asset references, stale source hashes, base64 image data in simulation state and nondeterministic bundle output.
- Worker smoke test imports the static asset handler and verifies a known HTML, bootstrap JSON and asset response without starting a persistent simulation server.

- [ ] **Step 1: Add failing packaging checks**

Create tests that fail if WEB/dist is absent, if a compiled runtime file contains fs, path, Pillow, python or api/tick, if the bundle revision/source hash does not match generated inputs, or if runtime_render_state contains image_data_url.

- [ ] **Step 2: Run the checks before Wrangler configuration**

Run: npm --prefix WEB run build:web

Run: npm --prefix WEB run check:deploy

Expected: FAIL because static packaging and Worker configuration do not exist.

- [ ] **Step 3: Add static Cloudflare packaging**

Configure wrangler.jsonc for the WEB/dist assets directory and a minimal fetch handler only if the selected static deployment requires one. Do not add Durable Objects, WebSockets or a server tick endpoint in this single-user migration.

- [ ] **Step 4: Add Workers Vitest integration**

Install the current Cloudflare Vitest integration, configure the Worker test pool and test asset responses plus the absence of Node-only APIs. Keep normal runtime tests in the Node/Vitest environment; use the Worker pool only for Worker-specific behavior.

- [ ] **Step 5: Add deterministic build and fresh-extraction checks**

Build twice from the same canonical inputs and compare hashes. Create a fresh release archive from the root, extract it into a fresh directory, run release_clean=true validation and verify no __pycache__, .pytest_cache, LOCAL_REVIEW, debug artifacts or materialized occupancy caches are included.

- [ ] **Step 6: Run endurance and author gates**

Run a deterministic simulated 24-hour trace, a real-browser soak with heap/FPS/request metrics, Canvas/Raster review and explicit author visual/gameplay acceptance. Record typed runtime step p95, FPS, payload size, heap checkpoints and request counts in HANDOFF.md.

- [ ] **Step 7: Cut over only after all gates are recorded**

Change the production source default only after G0–G9 from the spec are green. Keep the Python source mode, oracle and raster fallback in the repository. Do not delete old modules or Python services in this task.

- [ ] **Step 8: Commit deployment packaging and status**

~~~
git add WEB/wrangler.jsonc WEB/tests/worker_smoke.test.ts WEB/scripts/check_runtime_bundle.mjs WEB/README_DEPLOY.md WEB/package.json .gitignore HANDOFF.md ROADMAP.md
git commit -m "feat: package typed runtime for Cloudflare static assets"
~~~

**Exit gate:** Cloudflare preview/static smoke passes, Worker-specific tests pass, deterministic release extraction is clean, endurance and author acceptance are recorded, and rollback to Python remains one explicit source-mode choice.

## Validation matrix

Run the narrowest relevant command after each task and the complete matrix before any completion claim:

~~~
npm --prefix WEB run typecheck
npm --prefix WEB run test:ts
npm --prefix WEB run check:contracts
python -B -m compileall -q RUNTIME WORLD CHARACTER TOOLS VALIDATION TESTS
ruff check RUNTIME WORLD CHARACTER TOOLS VALIDATION TESTS
python -B -m pytest -p no:cacheprovider -q
node --test TESTS/browser_runtime_test.mjs
python VALIDATION/self_audit_room_navigation.py
python VALIDATION/self_audit_navigation_occupancy.py
python VALIDATION/self_audit_work_seat.py
python VALIDATION/self_audit_work_seat_lifecycle.py
python VALIDATION/self_audit_phase6_spatial.py
python VALIDATION/self_audit_central.py
python VALIDATION/self_audit_gameplay_metadata_family.py
python VALIDATION/self_audit_conversation.py
python TOOLS/render_runtime_presentation_qa.py
python TOOLS/benchmark_runtime_renderers.py
git diff --check
~~~

Cloudflare/Playwright checks are added in Task 10 and are required before release, not a replacement for the Python and parity suites.

## Rollback and commit policy

- Keep the old JavaScript entry and Python source mode until the final cutover.
- Use one commit per task and keep parity fixtures in the same commit as the behavior family they protect.
- If a typed task changes a trace, leave the old path as the reference, inspect the first mismatch path and revert only the typed task if the owning rule is not understood.
- Do not use git reset --hard, broad deletion or generated-output edits to hide a mismatch.
- Do not touch immutable starting-point files or untracked user assets.

## Plan self-review

The plan covers every section of the approved design:

- canonical data/source hashes and deterministic bundle: Tasks 2 and 10;
- strict TypeScript types and runtime validation: Tasks 1–2;
- pure runtime module order: Tasks 4–8;
- one neutral render state and Canvas boundary: Tasks 8–9;
- save/load/replay: Task 8;
- browser one-bootstrap/zero-periodic-request behavior: Task 9;
- property/differential/browser/performance tests: Tasks 3, 6–10;
- Cloudflare static packaging and Worker-specific checks: Task 10;
- Python oracle/fallback and rollback: global constraints and Tasks 8–10;
- author acceptance and release-clean package: Task 10.

No task relies on a converter as a correctness proof, no task changes authored gameplay data, and every typed module has a focused test checkpoint before it can be used by a later task.
