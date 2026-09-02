import test from "node:test";
import assert from "node:assert/strict";

import { DeterministicRng } from "../WEB/runtime_simulation_prng.js";
import {
  cloneRuntimeSnapshot,
  validateRuntimeSnapshot,
} from "../WEB/runtime_simulation_state.js";
import { FixedStepClock } from "../WEB/runtime_simulation_clock.js";
import { BrowserRuntimeCore } from "../WEB/runtime_simulation_core.js";

function fixtureSnapshot() {
  const actorId = "EMP_TEST_001";
  return {
    schema: "gds.runtime_snapshot.v1",
    version: "1.0.0",
    actor_snapshot: {
      schema: "gds.actor_snapshot.v1",
      version: "1.0.0",
      clock: { simulation_time_ms: 0, tick_ms: 60 },
      determinism: { root_event_counter: 0, simulation_seed: "test" },
      actors: { [actorId]: { employee_id: actorId, activity: "working" } },
    },
    speech_snapshot: {
      schema: "gds.speech_scheduler_snapshot.v1",
      version: "1.0.0",
      clock: { simulation_time_ms: 0, tick_ms: 60 },
      determinism: { root_event_counter: 0, simulation_seed: "test" },
      active_sessions: {},
      dialogue_bags: {},
      lanes: {},
      actors: { [actorId]: { employee_id: actorId, speech_phase: "idle" } },
    },
    conversation_snapshot: {
      schema: "gds.conversation_actor_snapshot.v1",
      version: 1,
      clock_ms: 0,
      active_conversation: null,
      conversation_id: null,
      locks: { participant_lock: [], talk_slot_lock: [] },
      actors: { [actorId]: { employee_id: actorId, phase: "working" } },
    },
  };
}

function fixtureBundle() {
  return {
    schema: "gds.browser_runtime_bundle.v1",
    version: "1.0.0",
    floor_id: "floor02",
    bundle_revision: "fixture-revision",
    simulation: {
      step_ms: 60,
      seed_namespace: "gds-browser-runtime-v1",
      constants: {},
    },
    world: { floor: { floor_id: "floor02" }, navigation: {} },
    initial_snapshot: fixtureSnapshot(),
  };
}

test("seeded random sequence is deterministic and never uses Math.random", () => {
  const rng = new DeterministicRng("gds-browser-runtime-v1");
  const values = Array.from({ length: 5 }, () => rng.nextUint32());
  assert.deepEqual(values, [
    2382527216,
    871612171,
    941754517,
    3825408319,
    900664123,
  ]);
  assert.equal(rng.d6(), 3);
  assert.equal(["a", "b", "c"].includes(rng.choice(["a", "b", "c"])), true);
});

test("runtime snapshot validation checks all synchronized actor channels", () => {
  const snapshot = fixtureSnapshot();
  assert.equal(validateRuntimeSnapshot(snapshot), snapshot);
  const cloned = cloneRuntimeSnapshot(snapshot);
  cloned.actor_snapshot.actors.EMP_TEST_001.activity = "changed";
  assert.equal(snapshot.actor_snapshot.actors.EMP_TEST_001.activity, "working");

  assert.throws(
    () => validateRuntimeSnapshot({ ...snapshot, schema: "wrong" }),
    /runtime snapshot schema/,
  );
  assert.throws(
    () => validateRuntimeSnapshot({ ...snapshot, speech_snapshot: undefined }),
    /speech_snapshot channel/,
  );
  assert.throws(
    () => validateRuntimeSnapshot({
      ...snapshot,
      conversation_snapshot: {
        ...snapshot.conversation_snapshot,
        actors: {},
      },
    }),
    /actor ids must match/,
  );
});

test("fixed clock returns bounded fixed slices", () => {
  const clock = new FixedStepClock({ stepMs: 60, maxCatchupMs: 180 });
  assert.deepEqual(clock.pushElapsed(200), [60, 60, 60]);
  assert.deepEqual(clock.pushElapsed(5000), [60, 60, 60]);
  assert.equal(clock.simulationClockMs, 360);
});

test("browser core starts from the canonical snapshot without network", async () => {
  const core = await BrowserRuntimeCore.create({
    bundle: fixtureBundle(),
    floorId: "floor02",
    seed: "test",
  });
  const result = core.step(60);
  assert.equal(result.snapshot.schema, "gds.runtime_snapshot.v1");
  assert.equal(result.renderState.schema, "gds.runtime_render_state.v1");
  assert.equal(result.snapshot.actor_snapshot.clock.simulation_time_ms, 60);
  assert.equal(result.renderState.clock_ms, 60);
  core.destroy();
});

test("browser core fetches the bootstrap exactly once and never polls while stepping", async () => {
  let calls = 0;
  const core = await BrowserRuntimeCore.create({
    bundleUrl: "/runtime_simulation_bootstrap.json",
    floorId: "floor02",
    seed: "test",
    fetchImpl: async () => {
      calls += 1;
      return { ok: true, json: async () => fixtureBundle() };
    },
  });
  core.step(600);
  core.step(60);
  assert.equal(calls, 1);
  core.destroy();
});
