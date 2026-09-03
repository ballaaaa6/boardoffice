import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import { DeterministicRng } from "../WEB/runtime_simulation_prng.js";
import {
  cloneRuntimeSnapshot,
  validateRuntimeSnapshot,
} from "../WEB/runtime_simulation_state.js";
import { FixedStepClock } from "../WEB/runtime_simulation_clock.js";
import { BrowserNavigation } from "../WEB/runtime_simulation_navigation.js";
import { BrowserWorkSeatReducer } from "../WEB/runtime_simulation_work_seat.js";
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

async function checkedInBundle() {
  const path = new URL("../WEB/runtime_simulation_bootstrap.json", import.meta.url);
  return JSON.parse(await readFile(path, "utf8"));
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

test("bundle-backed navigation matches the authored floor02 A* path", async () => {
  const bundle = await checkedInBundle();
  const navigation = new BrowserNavigation({ world: bundle.world });
  assert.equal(navigation.isWalkable(189, 103), true);
  assert.equal(navigation.isWalkable(202, 47), false);
  assert.deepEqual(navigation.portal("floor02").inside_cells_uv[0], [240, 182]);

  const path = navigation.findPath([189, 103], [253, 182]);
  assert.equal(path.path_cell_count, 144);
  assert.deepEqual(path.path_cells_uv.slice(0, 3), [
    [189, 103],
    [189, 104],
    [189, 105],
  ]);
  assert.deepEqual(path.path_cells_uv.at(-1), [253, 182]);
});

test("workseat reducer exposes a non-image visual anchor", async () => {
  const bundle = await checkedInBundle();
  const workSeat = new BrowserWorkSeatReducer({
    workSeats: bundle.work_seats,
    employees: bundle.employees,
  });
  assert.deepEqual(workSeat.visualCharacterAnchor("floor02", "ws2", "TP_009"), [213, 304]);
  assert.equal(workSeat.pcFrameCount("ws2"), 1);
});

test("browser actor slice advances work stamina and frame clocks", async () => {
  const bundle = await checkedInBundle();
  const core = await BrowserRuntimeCore.create({
    bundle,
    floorId: "floor02",
    seed: "browser-test-seed",
  });
  const result = core.step(60);
  const actor = result.snapshot.actor_snapshot.actors.EMP_W1_0010;
  const row = result.renderState.actors.find((item) => item.employee_id === "EMP_W1_0010");
  assert.equal(actor.behavior.work_loop_elapsed_ms, 60);
  assert.equal(actor.stamina.current_milli, 99957);
  assert.equal(actor.stamina.drain_remainder, 440);
  assert.equal(row.workstation_id, "ws2");
  assert.equal(row.render_owner, "work_seat");
  assert.equal(row.action, "work");
  assert.equal(row.character_frame_count, 2);
  assert.equal(row.character_frame_index, 0);
  assert.equal(row.pc_frame_count, 1);
  core.destroy();
});

test("request_home leaves the owned workseat through the authored gate route", async () => {
  const bundle = await checkedInBundle();
  const core = await BrowserRuntimeCore.create({
    bundle,
    floorId: "floor02",
    seed: "browser-test-seed",
  });
  const result = core.step(60, {
    actorCommands: [{ type: "request_home", employee_id: "EMP_W1_0010" }],
  });
  const actor = result.snapshot.actor_snapshot.actors.EMP_W1_0010;
  const row = result.renderState.actors.find((item) => item.employee_id === "EMP_W1_0010");
  assert.equal(actor.presence, "leaving");
  assert.equal(actor.activity, "going_home");
  assert.equal(actor.position.route.phase, "to_portal");
  assert.deepEqual(actor.position.route.start_uv, [189, 103]);
  assert.deepEqual(actor.position.route.target_uv, [253, 182]);
  assert.equal(actor.position.route.elapsed_ms, 60);
  assert.equal(actor.position.route.duration_ms, 14220);
  assert.equal(actor.position.seat_transition.phase, "seat_exit");
  assert.deepEqual(actor.position.seat_transition.from_ground_xy, [213, 304]);
  assert.equal(row.render_owner, "walking_depth");
  assert.equal(row.action, "move");
  assert.equal(row.route_phase, "to_portal");
  assert.equal(row.route_elapsed_ms, 60);
  core.destroy();
});

test("browser effects expose metadata channels without image payloads", async () => {
  const bundle = await checkedInBundle();
  const core = await BrowserRuntimeCore.create({
    bundle,
    floorId: "floor02",
    seed: "browser-test-seed",
  });
  const snapshot = core.snapshot();
  const employeeId = "EMP_W1_0031";
  const actor = snapshot.actor_snapshot.actors[employeeId];
  actor.activity = "popup_event";
  actor.behavior.event_counter = 1;
  actor.behavior.active_event = "popup";
  actor.behavior.activity_started_ms = 0;
  actor.behavior.activity_until_ms = 600;
  actor.behavior.next_event_due_ms = null;
  for (const speechActor of Object.values(snapshot.speech_snapshot.actors)) {
    speechActor.greeting_due_ms = 999999;
    speechActor.greeting_emitted = true;
    speechActor.work_start_due_ms = 999999;
    speechActor.work_start_emitted = true;
    speechActor.solo_next_due_ms = 999999;
    speechActor.pair_next_due_ms = 999999;
    speechActor.solo_pending = false;
    speechActor.pair_pending = false;
  }
  core.load({
    floor_id: "floor02",
    bundle_revision: bundle.bundle_revision,
    snapshot,
    sequence: 0,
    command_history: [],
  });
  const result = core.step(60);
  const row = result.renderState.actors.find((item) => item.employee_id === employeeId);
  assert.equal(row.channels.humanball.asset_id, "purple_bot");
  assert.equal(row.channels.humanball.humanball_frame_index, 0);
  assert.equal("image_data_url" in result.renderState, false);
  assert.equal(JSON.stringify(result.renderState).includes("data:image"), false);
  core.destroy();
});
