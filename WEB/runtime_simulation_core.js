import {
  cloneJsonValue,
  cloneRuntimeSnapshot,
  RENDER_STATE_SCHEMA,
  RENDER_STATE_VERSION,
  validateRuntimeSnapshot,
} from "./runtime_simulation_state.js";
import { FixedStepClock } from "./runtime_simulation_clock.js";

const BROWSER_BUNDLE_SCHEMA = "gds.browser_runtime_bundle.v1";
const BROWSER_BUNDLE_VERSION = "1.0.0";
const DEFAULT_STEP_MS = 60;
const DEFAULT_MAX_CATCHUP_MS = 1000;
const DEFAULT_ANCHOR = [16, 31];
const DEFAULT_CHARACTER_FRAME_MS = 360;
const DEFAULT_PC_FRAME_MS = 720;
const COMMAND_HISTORY_LIMIT = 2048;

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function requireBundle(bundle, floorId = null) {
  if (!isObject(bundle)) throw new TypeError("browser runtime bundle must be an object");
  if (bundle.schema !== BROWSER_BUNDLE_SCHEMA) {
    throw new TypeError("browser runtime bundle schema is unsupported");
  }
  if (bundle.version !== BROWSER_BUNDLE_VERSION) {
    throw new TypeError("browser runtime bundle version is unsupported");
  }
  if (floorId !== null && bundle.floor_id !== floorId) {
    throw new TypeError("browser runtime bundle floor does not match requested floor");
  }
  if (!isObject(bundle.simulation) || bundle.simulation.step_ms !== DEFAULT_STEP_MS) {
    throw new TypeError("browser runtime bundle must use a 60ms simulation step");
  }
  if (!isObject(bundle.world)) throw new TypeError("browser runtime bundle world is required");
  validateRuntimeSnapshot(bundle.initial_snapshot);
  return bundle;
}

function numeric(value, fallback = 0) {
  return Number.isFinite(Number(value)) ? Number(value) : fallback;
}

function integer(value, fallback = 0) {
  return Math.trunc(numeric(value, fallback));
}

function actorAssignment(actor) {
  return isObject(actor.assignment) ? actor.assignment : {};
}

function frameReference(bundle, actor) {
  const characterId = actor.character_id;
  const character = bundle.characters?.[characterId];
  const refs = Array.isArray(character?.frame_refs) ? character.frame_refs : [];
  const assignment = actorAssignment(actor);
  const action = actor.action || (actor.activity === "working" ? "work" : "idle");
  const direction = actor.direction || assignment.facing || "SE";
  const subaction = actor.subaction || (action === "work" ? "normal_work" : null);
  return refs.find((ref) => (
    ref.action === action
    && (ref.direction === direction || ref.direction === null || ref.direction === undefined)
    && (ref.subaction || null) === subaction
  )) || refs.find((ref) => ref.action === action) || refs[0] || null;
}

function hiddenDialogue(speakerId) {
  return {
    bubble_id: null,
    dialogue_id: null,
    line_index: null,
    locale: null,
    offset_xy: [0, 0],
    opacity: 0,
    phase: "hidden",
    speaker_id: speakerId,
    text: null,
    turn_index: 0,
    visible: false,
  };
}

export class BrowserRuntimeCore {
  static async create({ bundleUrl, bundle, floorId, seed, fetchImpl } = {}) {
    let loadedBundle = bundle;
    if (loadedBundle === undefined) {
      if (typeof bundleUrl !== "string" || bundleUrl.length === 0) {
        throw new TypeError("bundleUrl is required when bundle is not provided");
      }
      const fetcher = fetchImpl || globalThis.fetch?.bind(globalThis);
      if (typeof fetcher !== "function") throw new TypeError("browser runtime requires fetch");
      const response = await fetcher(bundleUrl);
      if (response?.ok === false) {
        throw new Error(`browser runtime bundle request failed: ${response.status}`);
      }
      if (typeof response?.json !== "function") {
        throw new TypeError("browser runtime bundle response must provide json()");
      }
      loadedBundle = await response.json();
    }
    return new BrowserRuntimeCore({ bundle: loadedBundle, floorId, seed });
  }

  constructor({ bundle, floorId, seed } = {}) {
    const requestedFloor = floorId ?? bundle?.floor_id ?? null;
    requireBundle(bundle, requestedFloor);
    const initialSnapshot = cloneRuntimeSnapshot(bundle.initial_snapshot);
    const initialClock = initialSnapshot.actor_snapshot.clock.simulation_time_ms;
    this.bundle = cloneJsonValue(bundle);
    this.floorId = requestedFloor;
    this.seed = seed ?? bundle.simulation.seed_namespace;
    if (typeof this.seed !== "string" || this.seed.length === 0) {
      throw new TypeError("seed must be a non-empty string");
    }
    this.state = initialSnapshot;
    this.clock = new FixedStepClock({
      stepMs: bundle.simulation.step_ms,
      maxCatchupMs: DEFAULT_MAX_CATCHUP_MS,
    });
    this.clock.reset({ simulationClockMs: initialClock });
    this.clockMs = initialClock;
    this.sequence = 0;
    this.lastEvents = [];
    this.commandHistory = [];
    this.destroyed = false;
  }

  _assertAlive() {
    if (this.destroyed || !this.state) throw new Error("browser runtime has been destroyed");
  }

  _applyClock(clockMs) {
    this.state.actor_snapshot.clock.simulation_time_ms = clockMs;
    this.state.speech_snapshot.clock.simulation_time_ms = clockMs;
    this.state.conversation_snapshot.clock_ms = clockMs;
    this.clockMs = clockMs;
  }

  _renderActor(employeeId, actor) {
    const assignment = actorAssignment(actor);
    const frameRef = frameReference(this.bundle, actor);
    const frameIds = Array.isArray(frameRef?.frame_ids) ? frameRef.frame_ids : [];
    const frameId = frameIds[0] ?? null;
    const workstationId = actor.workstation_id ?? assignment.workstation_id ?? null;
    const action = actor.action || (actor.activity === "working" ? "work" : "idle");
    const direction = actor.direction || assignment.facing || "SE";
    const subaction = actor.subaction || (action === "work" ? "normal_work" : null);
    const position = isObject(actor.position) ? actor.position.ground_xy : null;
    const characterId = actor.character_id ?? null;
    const frameRule = frameId ? this.bundle.frame_rules?.[frameId] : null;
    const workstation = workstationId ? this.bundle.work_seats?.[workstationId] : null;
    const pcFrameCount = integer(
      workstation?.seat?.pc_frame_count ?? workstation?.pc?.frame_count,
      1,
    );
    return {
      employee_id: employeeId,
      character_id: characterId,
      floor_id: actor.floor_id ?? assignment.floor_id ?? this.floorId,
      activity: actor.activity ?? "working",
      presence: actor.presence ?? "present",
      action,
      resolved_action: action,
      direction,
      resolved_direction: direction,
      subaction,
      resolved_subaction: subaction,
      assignment_order: assignment.assignment_order ?? null,
      workstation_id: workstationId,
      render_owner: actor.render_owner ?? "work_seat",
      anchor_xy: Array.isArray(position) ? position : [...DEFAULT_ANCHOR],
      ground_xy: Array.isArray(position) ? position : null,
      route_phase: actor.route?.phase ?? null,
      route_elapsed_ms: actor.route?.elapsed_ms ?? null,
      route_duration_ms: actor.route?.duration_ms ?? null,
      cumulative_distance_px: numeric(actor.route?.distance_px, 0),
      animation_clock_ms: integer(actor.animation_clock_ms, 0),
      frame_id: frameId,
      frame_index: integer(actor.frame_index, 0),
      character_frame_index: integer(actor.character_frame_index, 0),
      character_frame_count: frameIds.length || 1,
      character_frame_ms: integer(actor.character_frame_ms, DEFAULT_CHARACTER_FRAME_MS),
      pc_frame_index: integer(actor.pc_frame_index, 0),
      pc_frame_count: pcFrameCount,
      pc_frame_ms: integer(actor.pc_frame_ms, DEFAULT_PC_FRAME_MS),
      channels: {
        pc: {
          frame_count: pcFrameCount,
          frame_index: integer(actor.pc_frame_index, 0),
          frame_ms: integer(actor.pc_frame_ms, DEFAULT_PC_FRAME_MS),
        },
      },
      stamina: actor.stamina ? cloneJsonValue(actor.stamina) : null,
      dialogue: hiddenDialogue(employeeId),
      occluder_placement_ids: [],
      visibility_alpha: numeric(actor.visibility_alpha, 1),
      visible: actor.presence !== "home",
    };
  }

  step(elapsedMs, { actorCommands = [], speechCommands = [] } = {}) {
    this._assertAlive();
    if (!Array.isArray(actorCommands) || !Array.isArray(speechCommands)) {
      throw new TypeError("actorCommands and speechCommands must be arrays");
    }
    for (const command of actorCommands) this.command(command);
    for (const command of speechCommands) this.command(command);

    const slices = this.clock.pushElapsed(elapsedMs);
    const firstClock = this.clock.simulationClockMs - slices.length * this.clock.stepMs;
    const events = [];
    slices.forEach((_slice, index) => {
      this._applyClock(firstClock + (index + 1) * this.clock.stepMs);
      this.sequence += 1;
    });
    this.lastEvents = events;
    return {
      snapshot: this.snapshot(),
      renderState: this.renderState(),
      events: cloneJsonValue(events),
    };
  }

  snapshot() {
    this._assertAlive();
    return cloneRuntimeSnapshot(this.state);
  }

  renderState(atMs = this.clockMs) {
    this._assertAlive();
    if (!Number.isFinite(Number(atMs)) || Number(atMs) < 0) {
      throw new TypeError("atMs must be a non-negative number");
    }
    const actors = this.state.actor_snapshot.actors;
    const activeSessions = this.state.speech_snapshot.active_sessions;
    return {
      schema: RENDER_STATE_SCHEMA,
      version: RENDER_STATE_VERSION,
      floor_id: this.floorId,
      clock_ms: Math.trunc(Number(atMs)),
      sequence: this.sequence,
      static_scene_id: this.floorId,
      manifest_revision: this.bundle.render_manifest_revision
        ?? "floor02-component-manifest-v1",
      full: true,
      actors: Object.keys(actors)
        .sort()
        .map((employeeId) => this._renderActor(employeeId, actors[employeeId])),
      active_speech_sessions: Object.values(activeSessions || {}).map((session) => (
        isObject(session) ? cloneJsonValue(session) : session
      )),
      events: cloneJsonValue(this.lastEvents),
      paint_order: ["characters", "dialogue_bubbles"],
    };
  }

  command(command) {
    this._assertAlive();
    if (!isObject(command)) throw new TypeError("runtime command must be an object");
    const copy = cloneJsonValue(command);
    this.commandHistory.push(copy);
    if (this.commandHistory.length > COMMAND_HISTORY_LIMIT) this.commandHistory.shift();
    return cloneJsonValue(copy);
  }

  serialize() {
    this._assertAlive();
    return JSON.stringify({
      schema: "gds.browser_runtime_save.v1",
      version: "1.0.0",
      floor_id: this.floorId,
      bundle_revision: this.bundle.bundle_revision,
      seed: this.seed,
      sequence: this.sequence,
      snapshot: this.snapshot(),
      command_history: cloneJsonValue(this.commandHistory),
    });
  }

  load(payload) {
    this._assertAlive();
    const parsed = typeof payload === "string" ? JSON.parse(payload) : payload;
    if (!isObject(parsed)) throw new TypeError("runtime save package must be an object");
    if (parsed.floor_id !== this.floorId) throw new TypeError("runtime save floor does not match");
    if (
      parsed.bundle_revision !== undefined
      && parsed.bundle_revision !== this.bundle.bundle_revision
    ) {
      throw new TypeError("runtime save bundle revision does not match");
    }
    const snapshot = cloneRuntimeSnapshot(parsed.snapshot);
    const clockMs = snapshot.actor_snapshot.clock.simulation_time_ms;
    const nextClock = new FixedStepClock({
      stepMs: this.bundle.simulation.step_ms,
      maxCatchupMs: DEFAULT_MAX_CATCHUP_MS,
    });
    nextClock.reset({ simulationClockMs: clockMs });
    this.state = snapshot;
    this.clock = nextClock;
    this.clockMs = clockMs;
    this.sequence = Number.isInteger(parsed.sequence) ? parsed.sequence : 0;
    this.commandHistory = Array.isArray(parsed.command_history)
      ? cloneJsonValue(parsed.command_history).slice(-COMMAND_HISTORY_LIMIT)
      : [];
    this.lastEvents = [];
    return this.snapshot();
  }

  replay(packagePayload) {
    this._assertAlive();
    const parsed = typeof packagePayload === "string"
      ? JSON.parse(packagePayload)
      : packagePayload;
    if (!isObject(parsed) || !Array.isArray(parsed.steps)) {
      throw new TypeError("runtime replay package must contain steps");
    }
    if (parsed.initial_snapshot) {
      this.load({
        floor_id: this.floorId,
        bundle_revision: this.bundle.bundle_revision,
        snapshot: parsed.initial_snapshot,
        sequence: 0,
        command_history: [],
      });
    }
    const checkpoints = parsed.steps.map((step) => this.step(
      step.elapsed_ms,
      {
        actorCommands: step.actor_commands || [],
        speechCommands: step.speech_commands || [],
      },
    ));
    return { snapshot: this.snapshot(), checkpoints };
  }

  destroy() {
    if (this.destroyed) return;
    this.destroyed = true;
    this.state = null;
    this.bundle = null;
    this.commandHistory = [];
    this.lastEvents = [];
  }
}
