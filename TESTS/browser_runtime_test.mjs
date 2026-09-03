import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import { DeterministicRng } from "../WEB/runtime_simulation_prng.js";
import {
  cloneRuntimeSnapshot,
  validateRuntimeSnapshot,
} from "../WEB/runtime_simulation_state.js";
import { BrowserVisualSelection } from "../WEB/runtime_simulation_visual_selection.js";
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
    visual_catalog: visualCatalogFixture(),
    initial_snapshot: fixtureSnapshot(),
  };
}

async function checkedInBundle() {
  const path = new URL("../WEB/runtime_simulation_bootstrap.json", import.meta.url);
  return JSON.parse(await readFile(path, "utf8"));
}

function visualCatalogFixture() {
  return {
    profile_id: "gds.visual_catalog.v1",
    catalog_profile: "gds.visual_catalog.v1:test-profile",
    vfx: {
      ids: [
        "fire_original", "speed_wind", "idea_overclock", "coffee_energy",
        "sunshine_bloom", "heart_burst", "cherry_blossom_swirl", "thunder_cloud",
        "stock_crash", "low_battery_drain", "static_noise_field",
      ],
      registry_schema: "gds_effect_registry_v1",
      registry_hash: "0".repeat(64),
    },
    humanball: {
      ids: ["controller", "coin", "horse", "bench", "purple_bot", "purple_bot_body"],
      registry_schema: "gds_humanball_registry_v1",
      registry_hash: "1".repeat(64),
    },
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

test("browser visual shuffle bags cover every catalog item before repeating", () => {
  const selection = new BrowserVisualSelection({ catalog: visualCatalogFixture() });
  let state = selection.initialChannelState("vfx");
  const selected = [];
  for (let index = 0; index < 23; index += 1) {
    const result = selection.select(state, {
      channel: "vfx",
      simulationSeed: "browser-bag-seed",
      employeeId: "EMP_W1_0010",
      eventId: `event-${index}`,
      startedAtMs: index * 60,
      endsAtMs: (index + 1) * 60,
    });
    state = selection.clearActive(result.state, { channel: "vfx", eventId: `event-${index}` });
    selected.push(result.binding.asset_id);
  }
  assert.equal(new Set(selected.slice(0, 11)).size, 11);
  assert.equal(new Set(selected.slice(11, 22)).size, 11);
});

test("browser visual rendering reads an active binding without reselection", async () => {
  const selection = new BrowserVisualSelection({ catalog: visualCatalogFixture() });
  const selected = selection.select(selection.initialChannelState("humanball"), {
    channel: "humanball",
    simulationSeed: "browser-binding-seed",
    employeeId: "EMP_W1_0010",
    eventId: "event-a",
    startedAtMs: 0,
    endsAtMs: 600,
  });
  const actor = {
    employee_id: "EMP_W1_0010",
    presence: "present",
    behavior: {
      active_event: "popup",
      activity_started_ms: 0,
      visual_channels: { vfx: selection.initialChannelState("vfx"), humanball: selected.state },
    },
  };
  const { BrowserEffectsReducer } = await import("../WEB/runtime_simulation_effects.js");
  const effects = new BrowserEffectsReducer({ catalog: visualCatalogFixture() });
  assert.equal(effects.presentation(actor, 0).asset_id, selected.binding.asset_id);
  assert.equal(effects.presentation(actor, 240).asset_id, selected.binding.asset_id);
  const legacyActor = structuredClone(actor);
  legacyActor.behavior.visual_channels.humanball.active_binding = null;
  const legacyPresentation = effects.presentation(legacyActor, 0);
  assert.equal(legacyPresentation.asset_id, null);
  assert.equal(legacyPresentation.selection_source, "shuffle_bag");
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
  const selected = core.visualSelection.select(actor.behavior.visual_channels.humanball, {
    channel: "humanball",
    simulationSeed: "browser-test-seed",
    employeeId,
    eventId: `visual:${employeeId}:popup:1:0`,
    startedAtMs: 0,
    endsAtMs: 600,
  });
  actor.behavior.visual_channels.humanball = selected.state;
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
  assert.equal(row.channels.humanball.asset_id, selected.binding.asset_id);
  assert.equal(bundle.visual_catalog.humanball.ids.includes(row.channels.humanball.asset_id), true);
  assert.equal(row.channels.humanball.humanball_frame_index, 0);
  assert.equal("image_data_url" in result.renderState, false);
  assert.equal(JSON.stringify(result.renderState).includes("data:image"), false);
  core.destroy();
});

test("browser actor selects visuals at event admission and clears them at completion", async () => {
  const bundle = await checkedInBundle();
  const core = await BrowserRuntimeCore.create({
    bundle,
    floorId: "floor02",
    seed: "browser-visual-event-seed",
  });
  const snapshot = core.snapshot();
  const employeeId = "EMP_W1_0010";
  const actor = snapshot.actor_snapshot.actors[employeeId];
  actor.behavior.next_event_due_ms = 0;
  actor.behavior.cooldowns = {
    talk: 999999,
    background_effect: 0,
    popup: 999999,
    wander: 999999,
  };
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
  const started = core.step(60);
  const startedActor = started.snapshot.actor_snapshot.actors[employeeId];
  const binding = startedActor.behavior.visual_channels.vfx.active_binding;
  assert.equal(startedActor.behavior.active_event, "background_effect");
  assert.equal(bundle.visual_catalog.vfx.ids.includes(binding.asset_id), true);
  assert.equal(started.renderState.actors.find((row) => row.employee_id === employeeId).channels.vfx.asset_id, binding.asset_id);

  for (let index = 0; index < 80; index += 1) core.step(60);
  const completed = core.snapshot().actor_snapshot.actors[employeeId];
  assert.equal(completed.behavior.active_event, null);
  assert.equal(completed.behavior.visual_channels.vfx.active_binding, null);
  core.destroy();
});

test("browser speech admits independent actor bubbles on the same floor", async () => {
  const bundle = await checkedInBundle();
  const core = await BrowserRuntimeCore.create({
    bundle,
    floorId: "floor02",
    seed: "browser-speech-slot-seed",
  });
  const runtimeSnapshot = core.snapshot();
  const employeeIds = Object.keys(runtimeSnapshot.speech_snapshot.actors)
    .filter((employeeId) => runtimeSnapshot.speech_snapshot.actors[employeeId].role === "employee")
    .sort()
    .slice(0, 2);
  for (const actor of Object.values(runtimeSnapshot.speech_snapshot.actors)) {
    actor.greeting_due_ms = null;
    actor.greeting_emitted = true;
    actor.work_start_due_ms = null;
    actor.work_start_emitted = true;
    actor.solo_next_due_ms = null;
    actor.pair_next_due_ms = null;
    actor.solo_pending = false;
    actor.pair_pending = false;
  }
  for (const employeeId of employeeIds) runtimeSnapshot.speech_snapshot.actors[employeeId].solo_pending = true;
  const result = core.speechReducer.step(runtimeSnapshot.speech_snapshot, {
    actorSnapshot: runtimeSnapshot.actor_snapshot,
    conversationSnapshot: runtimeSnapshot.conversation_snapshot,
    elapsedMs: 60,
    dialogueSeed: "browser-speech-slot-seed",
  });
  const started = result.events.filter((event) => event.type === "speech_session_started");
  assert.equal(started.length, 2);
  assert.equal(Object.keys(result.snapshot.active_sessions).length, 2);
  assert.deepEqual(
    employeeIds.map((employeeId) => Boolean(result.snapshot.actor_slots[employeeId].active_session_id)),
    [true, true],
  );
  core.destroy();
});
