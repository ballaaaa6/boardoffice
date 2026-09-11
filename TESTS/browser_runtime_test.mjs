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
        "crimson_inferno", "tangerine_cyclone", "lemon_crown", "acid_bramble",
        "emerald_serpent", "turquoise_glacier", "cobalt_volt", "violet_rift",
        "fuchsia_shockwave", "rose_nebula",
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
  const effectCount = selection.catalog().vfx.ids.length;
  let state = selection.initialChannelState("vfx");
  const selected = [];
  for (let index = 0; index < effectCount * 2 + 1; index += 1) {
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
  assert.equal(new Set(selected.slice(0, effectCount)).size, effectCount);
  assert.equal(new Set(selected.slice(effectCount, effectCount * 2)).size, effectCount);
});

test("browser HumanBall bags avoid immediate repeat at generation boundaries", async () => {
  const bundle = await checkedInBundle();
  const selection = new BrowserVisualSelection({ catalog: bundle.visual_catalog });
  for (let seedIndex = 0; seedIndex < 16; seedIndex += 1) {
    for (const employeeId of ["EMP_W1_0010", "EMP_W1_0031", "EMP_W1_0044"]) {
      let state = selection.initialChannelState("humanball");
      const selected = [];
      for (let index = 0; index < 89; index += 1) {
        const eventId = `boundary-${seedIndex}-${employeeId}-${index}`;
        const result = selection.select(state, {
          channel: "humanball",
          simulationSeed: `seed-${seedIndex}`,
          employeeId,
          eventId,
          startedAtMs: index * 60,
          endsAtMs: index * 60 + 1,
        });
        selected.push(result.binding.asset_id);
        state = selection.clearActive(result.state, {
          channel: "humanball",
          eventId,
        });
      }
      for (let index = 1; index < selected.length; index += 1) {
        assert.notEqual(
          selected[index],
          selected[index - 1],
          `${employeeId} seed-${seedIndex} index ${index}`,
        );
      }
    }
  }
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
  assert.equal(effects.presentation(actor, 2880).humanball_frame_index, 10);
  assert.equal(effects.presentation(actor, 3600).humanball_frame_index, 10);
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

test("browser runtime migrates an old 11-item VFX save atomically", async () => {
  const bundle = await checkedInBundle();
  const core = await BrowserRuntimeCore.create({
    bundle,
    floorId: "floor02",
    seed: "browser-vfx-migration-seed",
  });
  const snapshot = core.snapshot();
  for (const actor of Object.values(snapshot.actor_snapshot.actors)) {
    const employeeId = actor.employee_id;
    actor.behavior.visual_channels.vfx = {
      catalog_profile: "gds.visual_catalog.v1:legacy-vfx-profile",
      generation: 2,
      cursor: 11,
      active_binding: {
        channel: "vfx",
        asset_id: "speed_wind",
        event_id: `legacy-vfx:${employeeId}`,
        employee_id: employeeId,
        started_at_ms: 0,
        ends_at_ms: 600,
        generation: 2,
        cursor_after: 11,
      },
    };
  }

  core.load({
    floor_id: "floor02",
    bundle_revision: "legacy-11-item-bundle-revision",
    snapshot,
    sequence: 7,
    command_history: [],
  });

  for (const actor of Object.values(core.snapshot().actor_snapshot.actors)) {
    const state = actor.behavior.visual_channels.vfx;
    assert.equal(state.catalog_profile, bundle.visual_catalog.catalog_profile);
    assert.equal(state.generation, 0);
    assert.equal(state.cursor, 0);
    assert.equal(state.active_binding.asset_id, "speed_wind");
  }
  const stepped = core.step(60);
  assert.equal(stepped.snapshot.actor_snapshot.clock.simulation_time_ms, 60);
  core.destroy();
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

test("browser actor rejects a second recovery event while one is active", async () => {
  const bundle = await checkedInBundle();
  const core = await BrowserRuntimeCore.create({
    bundle,
    floorId: "floor02",
    seed: "browser-active-event-guard-seed",
  });
  const employeeId = "EMP_W1_0031";
  const actor = core.state.actor_snapshot.actors[employeeId];
  const employee = core.bundle.employees[employeeId];
  core.actorReducer.startEvent(
    { snapshot: core.state.actor_snapshot },
    actor,
    employee,
    "popup",
    0,
    [],
  );

  assert.throws(
    () => core.actorReducer.startEvent(
      { snapshot: core.state.actor_snapshot },
      actor,
      employee,
      "popup",
      60,
      [],
    ),
    /active recovery event/,
  );
  assert.equal(actor.behavior.event_counter, 1);
  assert.equal(actor.behavior.visual_channels.humanball.cursor, 1);
  core.destroy();
});

test("browser popup events share one global HumanBall bag across actors", async () => {
  const bundle = await checkedInBundle();
  const core = await BrowserRuntimeCore.create({
    bundle,
    floorId: "floor02",
    seed: "browser-global-popup-seed",
  });
  const firstId = "EMP_W1_0011";
  const secondId = "EMP_W1_0030";
  const firstActor = core.state.actor_snapshot.actors[firstId];
  const secondActor = core.state.actor_snapshot.actors[secondId];
  const firstEmployee = core.bundle.employees[firstId];
  const secondEmployee = core.bundle.employees[secondId];

  core.actorReducer.startEvent(
    { snapshot: core.state.actor_snapshot },
    firstActor,
    firstEmployee,
    "popup",
    0,
    [],
  );
  const firstAsset = firstActor.behavior.visual_channels.humanball.active_binding.asset_id;
  core.actorReducer.completeEvent(
    { snapshot: core.state.actor_snapshot },
    firstActor,
    firstEmployee,
    firstActor.behavior.activity_until_ms,
    [],
  );
  core.actorReducer.startEvent(
    { snapshot: core.state.actor_snapshot },
    secondActor,
    secondEmployee,
    "popup",
    6000,
    [],
  );
  const secondAsset = secondActor.behavior.visual_channels.humanball.active_binding.asset_id;

  assert.notEqual(firstAsset, secondAsset);
  assert.equal(core.state.actor_snapshot.determinism.humanball_global_bag.cursor, 2);
  assert.equal(core.state.actor_snapshot.determinism.humanball_global_bag.active_binding, null);
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

test("multi-floor browser index loads and advances all 25 floor bundles cleanly", async () => {
  const indexPath = new URL("../WEB/floors/index.json", import.meta.url);
  const rawIndex = await readFile(indexPath, "utf8");
  const floorList = JSON.parse(rawIndex);

  assert.equal(floorList.length, 25, "Expected 25 floors in index.json");

  // Verify key milestone floors
  const f00 = floorList.find((f) => f.floor_id === "floor00");
  const f01 = floorList.find((f) => f.floor_id === "floor01");
  const f02 = floorList.find((f) => f.floor_id === "floor02");
  const f36 = floorList.find((f) => f.floor_id === "floor36");

  assert.ok(f00 && f01 && f02 && f36);
  assert.equal(f00.employee_count, 5);
  assert.equal(f01.employee_count, 7);
  assert.equal(f02.employee_count, 9);
  assert.equal(f36.employee_count, 9);

  // Spot-check simulation execution on floor00 (Lobby), floor01, and floor36
  for (const floorId of ["floor00", "floor01", "floor36"]) {
    const bundleUrl = new URL(`../WEB/floors/${floorId}/bootstrap.json`, import.meta.url);
    const bundle = JSON.parse(await readFile(bundleUrl, "utf8"));
    const core = await BrowserRuntimeCore.create({
      bundle,
      floorId,
      seed: `test_floor_${floorId}`,
    });

    core.step(60);
    const state = core.renderState();
    assert.equal(state.floor_id, floorId);
    assert.equal(state.actors.length, Object.keys(bundle.employees).length);
    core.destroy();
  }
});

test("canvas renderer preloads PC frames and keeps the last ready frame during a slow swap", async () => {
  const { RuntimeCanvasRenderer } = await import("../WEB/runtime_canvas_renderer.js");
  const requested = [];
  const fakeContext = {
    imageSmoothingEnabled: false,
    clearRect: () => {},
    drawImage: () => {},
  };
  const fakeCanvas = {
    width: 600,
    height: 600,
    getContext: () => fakeContext,
  };
  const imageFactory = () => {
    const image = {
      complete: false,
      naturalWidth: 0,
      width: 0,
      height: 32,
      onload: null,
      onerror: null,
    };
    Object.defineProperty(image, "src", {
      set(value) {
        requested.push(value);
        queueMicrotask(() => {
          image.complete = true;
          image.naturalWidth = 50;
          image.width = 50;
          image.onload?.();
        });
      },
    });
    return image;
  };
  const manifest = {
    schema: "gds.runtime_render_manifest.v1",
    canvas: { width: 600, height: 600 },
    static_scene: { url: "/static.png" },
    overlays: [{ url: "/overlay.png" }],
    workstations: {
      ws1: {
        components: [
          { role: "pc", url: "/pc0.png", x_px: 10, y_px: 20, layer: 10 },
        ],
        pc_frames: [
          { frame_index: 0, url: "/pc0.png" },
          { frame_index: 1, url: "/pc1.png" },
        ],
      },
    },
  };
  const renderer = new RuntimeCanvasRenderer({
    canvas: fakeCanvas,
    manifestUrl: "http://127.0.0.1/floor00/manifest.json",
    imageFactory,
    fetchImpl: async () => ({ ok: true, json: async () => manifest }),
  });

  await renderer.loadManifest();
  assert.deepEqual(new Set(requested), new Set([
    "http://127.0.0.1/static.png",
    "http://127.0.0.1/overlay.png",
    "http://127.0.0.1/pc0.png",
    "http://127.0.0.1/pc1.png",
  ]));
  assert.equal(renderer.imageCache.get("http://127.0.0.1/pc0.png").ready, true);
  assert.equal(renderer.imageCache.get("http://127.0.0.1/pc1.png").ready, true);

  const row = {
    employee_id: "EMP_TEST_001",
    visible: true,
    render_owner: "work_seat",
    workstation_id: "ws1",
    channels: { pc: { frame_index: 0 } },
  };
  const pcEntry = () => renderer._dynamicEntries([row])
    .find((entry) => entry.key === "ws1:component:pc");

  assert.equal(pcEntry().record.url, "/pc0.png");
  renderer.imageCache.get("http://127.0.0.1/pc1.png").ready = false;
  row.channels.pc.frame_index = 1;
  assert.equal(pcEntry().record.url, "/pc0.png");

  renderer.imageCache.get("http://127.0.0.1/pc1.png").ready = true;
  assert.equal(pcEntry().record.url, "/pc1.png");
  renderer.destroy();
});

test("canvas renderer occludes walking actors behind seated characters and workstations", async () => {
  const { RuntimeCanvasRenderer } = await import("../WEB/runtime_canvas_renderer.js");
  const fakeContext = {
    clearRect: () => {},
    drawImage: () => {},
    save: () => {},
    restore: () => {},
  };
  const fakeCanvas = {
    width: 600,
    height: 600,
    getContext: () => fakeContext,
    ownerDocument: {
      createElement: () => ({
        width: 32,
        height: 42,
        getContext: () => ({
          imageSmoothingEnabled: false,
          clearRect: () => {},
          save: () => {},
          restore: () => {},
          drawImage: () => {},
        }),
      }),
    },
  };
  const renderer = new RuntimeCanvasRenderer({
    canvas: fakeCanvas,
    manifestUrl: "data:application/json,{}",
  });

  const maskedSeated = [];
  renderer._readyImage = () => ({ width: 32, height: 42 });
  renderer._drawRecord = () => {};
  renderer._drawEffect = () => {};
  renderer._drawHumanballs = () => {};
  renderer._drawDialogue = () => {};
  renderer._drawCharacter = (ctx, row) => {
    if (ctx === renderer.actorCtx && row.render_owner === "work_seat") {
      maskedSeated.push(row.employee_id);
    }
    return true;
  };

  renderer.manifest = {
    canvas: { width: 600, height: 600 },
    static_scene: { url: "static.png" },
    overlays: [],
    workstations: {
      ws_front: {
        character_layer: 400,
        character_top_left: [100, 300],
        components: [
          { role: "chair_main", layer: 399, x_px: 100, y_px: 300 },
          { role: "chair_foreground", layer: 500, x_px: 100, y_px: 300 },
        ],
      },
    },
  };
  renderer.state = {
    schema: "gds.runtime_render_state.v1",
    floor_id: "floor_test",
    sequence: 1,
    clock_ms: 60,
    actors: [
      { employee_id: "EMP_SEATED", visible: true, render_owner: "work_seat", workstation_id: "ws_front" },
      { employee_id: "EMP_WALKER_BEHIND", visible: true, render_owner: "walking_depth", ground_xy: [100, 310] },
      { employee_id: "EMP_WALKER_IN_FRONT", visible: true, render_owner: "walking_depth", ground_xy: [100, 350] },
    ],
    paint_order: { characters: ["EMP_WALKER_BEHIND", "EMP_WALKER_IN_FRONT"] },
  };

  renderer.render();
  assert.deepEqual(maskedSeated, ["EMP_SEATED"]);
});

test("canvas renderer masks rear walkers behind active seated VFX and HumanBall channels", async () => {
  const { RuntimeCanvasRenderer } = await import("../WEB/runtime_canvas_renderer.js");
  const calls = [];
  const makeContext = (name) => {
    const state = { globalCompositeOperation: "source-over", globalAlpha: 1 };
    const stack = [];
    return {
      get globalCompositeOperation() {
        return state.globalCompositeOperation;
      },
      set globalCompositeOperation(value) {
        state.globalCompositeOperation = value;
      },
      get globalAlpha() {
        return state.globalAlpha;
      },
      set globalAlpha(value) {
        state.globalAlpha = value;
      },
      imageSmoothingEnabled: false,
      clearRect: () => {},
      drawImage: (image, ...args) => calls.push({
        target: name,
        source: image?.name,
        operation: state.globalCompositeOperation,
        args,
      }),
      save: () => stack.push({ ...state }),
      restore: () => {
        const previous = stack.pop();
        if (previous) Object.assign(state, previous);
      },
      translate: () => {},
      scale: () => {},
    };
  };
  const mainContext = makeContext("main");
  const actorContext = makeContext("actor");
  const fakeCanvas = {
    width: 600,
    height: 600,
    getContext: () => mainContext,
    ownerDocument: {
      createElement: () => ({
        width: 32,
        height: 42,
        getContext: () => actorContext,
      }),
    },
  };
  const renderer = new RuntimeCanvasRenderer({
    canvas: fakeCanvas,
    manifestUrl: "http://127.0.0.1/render.json",
    imageFactory: () => ({ complete: true, naturalWidth: 1, width: 1, height: 1 }),
  });
  renderer._readyImage = (url) => ({
    name: url,
    width: url === "vfx.png" ? 33 : url.endsWith("humanball.png") ? 18 : 600,
    height: url === "vfx.png" ? 65 : url.endsWith("humanball.png") ? 18 : 600,
  });
  renderer._drawCharacter = () => true;
  renderer._drawDialogue = () => {};
  renderer.manifest = {
    frame_profile: { canvas: [32, 42] },
    static_scene: { url: "static.png" },
    overlays: [],
    workstations: {
      ws_front: {
        direction: "NW",
        character_layer: 400,
        effect_layer: 399,
        character_top_left: [100, 300],
        effect_world_offset: [0, 0],
        humanball_offsets: { NW: [[5, 5]] },
        components: [],
      },
    },
    effects: {
      test_effect: { frames: { NW: [{ url: "vfx.png", mirror_x: false }] } },
    },
    humanballs: {
      test_popup: { url: "humanball.png", visible_frame_count: 1 },
    },
    office_humanballs: {
      test_office_popup: { url: "office-humanball.png", visible_frame_count: 1 },
    },
  };
  const seated = {
    employee_id: "EMP_SEATED_FRONT",
    visible: true,
    render_owner: "work_seat",
    workstation_id: "ws_front",
    character_id: "TP_SEATED",
    frame_id: "M1",
    anchor_xy: [16, 31],
    channels: {
      vfx: { asset_id: "test_effect", effect_frame_index: 0 },
      humanball: { asset_id: "test_popup", humanball_frame_index: 0 },
      office_humanball: { asset_id: "test_office_popup", humanball_frame_index: 0 },
    },
  };
  const walker = {
    employee_id: "EMP_WALKER_REAR",
    visible: true,
    render_owner: "walking_depth",
    character_id: "TP_WALKER",
    frame_id: "M1",
    action: "idle",
    direction: "NW",
    ground_xy: [100, 310],
    anchor_xy: [16, 31],
  };
  renderer.state = {
    schema: "gds.runtime_render_state.v1",
    floor_id: "floor_test",
    sequence: 1,
    clock_ms: 60,
    actors: [seated, walker],
    paint_order: { characters: [walker.employee_id] },
  };

  renderer.render();
  const rearMaskSources = calls
    .filter((call) => call.target === "actor" && call.operation === "destination-out")
    .map((call) => call.source);
  assert.deepEqual(rearMaskSources, ["vfx.png", "humanball.png", "office-humanball.png"]);

  calls.length = 0;
  renderer.state.actors[1] = { ...walker, ground_xy: [100, 350] };
  renderer.render();
  const frontMaskSources = calls
    .filter((call) => call.target === "actor" && call.operation === "destination-out")
    .map((call) => call.source);
  assert.deepEqual(frontMaskSources, []);
});

test("canvas renderer keeps HumanBall hidden after its one-shot timeline", async () => {
  const { RuntimeCanvasRenderer } = await import("../WEB/runtime_canvas_renderer.js");
  const drawn = [];
  const fakeContext = {
    drawImage: (...args) => drawn.push(args),
    clearRect: () => {},
    save: () => {},
    restore: () => {},
  };
  const fakeCanvas = {
    width: 600,
    height: 600,
    getContext: () => fakeContext,
  };
  const renderer = new RuntimeCanvasRenderer({
    canvas: fakeCanvas,
    manifestUrl: "data:application/json,{}",
  });
  const offsets = Array.from({ length: 10 }, () => [5, -13]).concat([null, null]);
  renderer.manifest = {
    workstations: {
      ws1: {
        direction: "SE",
        character_top_left: [100, 100],
        humanball_offsets: { SE: offsets },
      },
    },
    humanballs: {
      controller: { url: "humanball.png", visible_frame_count: 10 },
    },
    office_humanballs: {},
  };
  renderer._readyImage = () => ({ width: 18, height: 18 });
  const row = {
    employee_id: "EMP_TEST_001",
    visible: true,
    render_owner: "work_seat",
    workstation_id: "ws1",
    channels: {
      humanball: { asset_id: "controller", humanball_frame_index: 12 },
    },
  };

  renderer._drawHumanballChannel(fakeContext, [row], "humanball", "humanballs");
  assert.equal(drawn.length, 0);

  row.channels.humanball.humanball_frame_index = 9;
  renderer._drawHumanballChannel(fakeContext, [row], "humanball", "humanballs");
  assert.equal(drawn.length, 1);
});

test("talk hold leaves workstation components behind walking speakers", async () => {
  const { resolveActorOccluderIds, resolveWalkingOcclusionContext } = await import(
    "../WEB/runtime_render_depth.js"
  );
  const occluders = [
    {
      placement_id: "desk",
      object_type: "desk",
      x_px: 84,
      y_px: 100,
      width: 32,
      height: 42,
      depth_anchor_y_px: 150,
      depth_front_edge_world_px: null,
      always_foreground: false,
    },
    {
      placement_id: "chair_sub",
      object_type: "chair_sub",
      x_px: 84,
      y_px: 100,
      width: 32,
      height: 42,
      depth_anchor_y_px: 150,
      depth_front_edge_world_px: null,
      always_foreground: false,
    },
    {
      placement_id: "overlay",
      object_type: "foreground_overlay",
      x_px: 84,
      y_px: 100,
      width: 32,
      height: 42,
      depth_anchor_y_px: null,
      depth_front_edge_world_px: null,
      always_foreground: true,
    },
  ];
  const actor = {
    render_owner: "walking_depth",
    ground_xy: [100, 140],
    speech_mode: "standing_pair",
    route_phase: "talk_hold",
  };

  assert.equal(resolveWalkingOcclusionContext(actor), "walking_talk_hold");
  assert.deepEqual(resolveActorOccluderIds(actor, occluders, "floor_test"), ["chair_sub", "overlay"]);
  for (const [speech_mode, route_phase] of [
    ["standing_pair", "talk_outbound"],
    ["standing_pair", "talk_return"],
  ]) {
    assert.equal(resolveWalkingOcclusionContext({ speech_mode, route_phase }), "normal");
    assert.deepEqual(
      resolveActorOccluderIds(
        { ...actor, speech_mode, route_phase },
        occluders,
        "floor_test",
      ),
      ["desk", "chair_sub", "overlay"],
    );
  }
  for (const speech_mode of ["seated_host", "ceo_front"]) {
    assert.equal(
      resolveWalkingOcclusionContext({ ...actor, speech_mode, route_phase: "talk_hold" }),
      "walking_talk_hold",
    );
    assert.deepEqual(
      resolveActorOccluderIds(
        { ...actor, speech_mode, route_phase: "talk_hold" },
        occluders,
        "floor_test",
      ),
      ["chair_sub", "overlay"],
    );
  }
});

test("render timeline interpolates walking poses without mutating source states", async () => {
  const { RenderTimeline } = await import("../WEB/runtime_render_timeline.js");
  const previous = {
    schema: "gds.runtime_render_state.v1",
    floor_id: "floor_test",
    sequence: 1,
    clock_ms: 60,
    actors: [{
      employee_id: "EMP_TEST_001",
      visible: true,
      render_owner: "walking_depth",
      ground_xy: [100, 310],
    }],
  };
  const current = {
    ...previous,
    sequence: 2,
    clock_ms: 120,
    actors: [{
      ...previous.actors[0],
      ground_xy: [101, 311],
    }],
  };
  const timeline = new RenderTimeline({ now: () => 0 });
  assert.equal(timeline.push(previous, { receivedAtMs: 0 }), true);
  assert.equal(timeline.push(current, { receivedAtMs: 60 }), true);
  const sampled = timeline.rows(90);
  assert.deepEqual(sampled[0].ground_xy, [100.5, 310.5]);
  assert.deepEqual(previous.actors[0].ground_xy, [100, 310]);
  assert.deepEqual(current.actors[0].ground_xy, [101, 311]);
});

test("smooth canvas mode preserves fractional walker placement on a high-resolution backing surface", async () => {
  const { RuntimeCanvasRenderer } = await import("../WEB/runtime_canvas_renderer.js");
  const calls = [];
  const makeContext = (name) => ({
    imageSmoothingEnabled: false,
    setTransform: (...args) => calls.push({ target: name, type: "transform", args }),
    clearRect: (...args) => calls.push({ target: name, type: "clear", args }),
    drawImage: (image, ...args) => calls.push({ target: name, type: "draw", image, args }),
    save: () => {},
    restore: () => {},
  });
  const mainContext = makeContext("main");
  const actorContext = makeContext("actor");
  const fakeCanvas = {
    width: 600,
    height: 600,
    style: {},
    getContext: () => mainContext,
    ownerDocument: {
      createElement: () => ({
        width: 32,
        height: 42,
        getContext: () => actorContext,
      }),
    },
  };
  const renderer = new RuntimeCanvasRenderer({
    canvas: fakeCanvas,
    manifestUrl: "http://127.0.0.1/render.json",
    motionMode: "smooth",
    renderResolutionScale: 4,
    now: () => 0,
  });
  renderer.manifest = {
    schema: "gds.runtime_render_manifest.v1",
    floor_id: "floor_test",
    canvas: { width: 600, height: 600 },
    frame_profile: { canvas: [32, 42] },
    static_scene: { url: "static.png" },
    overlays: [],
    occluders: [],
    workstations: {},
  };
  renderer._readyImage = (url) => ({ name: url, width: 600, height: 600 });
  renderer._drawCharacter = () => true;
  const row = {
    employee_id: "EMP_TEST_001",
    visible: true,
    render_owner: "walking_depth",
    character_id: "TP_TEST",
    frame_id: "M1",
    ground_xy: [100, 310],
    anchor_xy: [16, 31],
  };
  renderer.setState({
    schema: "gds.runtime_render_state.v1",
    floor_id: "floor_test",
    sequence: 1,
    clock_ms: 60,
    actors: [row],
    paint_order: { characters: [row.employee_id] },
  }, { receivedAtMs: 0 });
  renderer.setState({
    schema: "gds.runtime_render_state.v1",
    floor_id: "floor_test",
    sequence: 2,
    clock_ms: 120,
    actors: [{ ...row, ground_xy: [101, 311] }],
    paint_order: { characters: [row.employee_id] },
  }, { receivedAtMs: 60 });

  renderer.render(90);
  assert.equal(fakeCanvas.width, 2400);
  assert.equal(fakeCanvas.height, 2400);
  assert.equal(fakeCanvas.style.width, "600px");
  const actorDraw = calls.find((call) => (
    call.target === "main" && call.type === "draw" && call.image === renderer.actorCanvas
  ));
  assert.ok(actorDraw);
  assert.deepEqual(actorDraw.args, [0, 0, 128, 168, 84.5, 279.5, 32, 42]);
});

test("smooth canvas mode resolves walking occluders from the interpolated pose", async () => {
  const { RuntimeCanvasRenderer } = await import("../WEB/runtime_canvas_renderer.js");
  const fakeContext = {
    imageSmoothingEnabled: false,
    clearRect: () => {},
    drawImage: () => {},
  };
  const renderer = new RuntimeCanvasRenderer({
    canvas: { width: 600, height: 600, getContext: () => fakeContext },
    manifestUrl: "data:application/json,{}",
    motionMode: "smooth",
    now: () => 0,
  });
  renderer.manifest = {
    floor_id: "floor_test",
    occluders: [{
      placement_id: "front_object",
      x_px: 84,
      y_px: 100,
      width: 32,
      height: 42,
      depth_anchor_y_px: 150,
      depth_front_edge_world_px: null,
      always_foreground: false,
    }],
  };
  const baseActor = {
    employee_id: "EMP_TEST_001",
    visible: true,
    render_owner: "walking_depth",
    ground_xy: [100, 160],
    anchor_xy: [16, 31],
    occluder_placement_ids: [],
  };
  renderer.setState({
    schema: "gds.runtime_render_state.v1",
    floor_id: "floor_test",
    sequence: 1,
    clock_ms: 60,
    actors: [baseActor],
  }, { receivedAtMs: 0 });
  renderer.setState({
    schema: "gds.runtime_render_state.v1",
    floor_id: "floor_test",
    sequence: 2,
    clock_ms: 120,
    actors: [{
      ...baseActor,
      ground_xy: [100, 140],
      occluder_placement_ids: ["front_object"],
    }],
  }, { receivedAtMs: 60 });

  const sampled = renderer.getRenderRows(90);
  assert.deepEqual(sampled[0].ground_xy, [100, 150]);
  assert.deepEqual(sampled[0].occluder_placement_ids, []);
});
