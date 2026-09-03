import {
  cloneJsonValue,
  cloneRuntimeSnapshot,
  RENDER_STATE_SCHEMA,
  RENDER_STATE_VERSION,
  validateRuntimeSnapshot,
} from "./runtime_simulation_state.js";
import { FixedStepClock } from "./runtime_simulation_clock.js";
import { BrowserNavigation } from "./runtime_simulation_navigation.js";
import { BrowserActorReducer } from "./runtime_simulation_actor.js";
import { BrowserWorkSeatReducer } from "./runtime_simulation_work_seat.js";
import { BrowserSpeechReducer } from "./runtime_simulation_speech.js";
import { BrowserEffectsReducer } from "./runtime_simulation_effects.js";

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

function round4(value) {
  return Math.round(Number(value) * 10000) / 10000;
}

function actorAssignment(actor) {
  return isObject(actor.assignment) ? actor.assignment : {};
}

function frameReference(bundle, actor, {
  action = null,
  direction = null,
  subaction = null,
} = {}) {
  const characterId = actor.character_id;
  const character = bundle.characters?.[characterId];
  const refs = Array.isArray(character?.frame_refs) ? character.frame_refs : [];
  const assignment = actorAssignment(actor);
  const resolvedAction = action || actor.action || (actor.activity === "working" ? "work" : "idle");
  const resolvedDirection = direction || actor.direction || assignment.facing || "SE";
  const resolvedSubaction = subaction
    ?? actor.subaction
    ?? (resolvedAction === "work" ? "normal_work" : null);
  return refs.find((ref) => (
    ref.action === resolvedAction
    && (ref.direction === resolvedDirection || ref.direction === null || ref.direction === undefined)
    && (ref.subaction || null) === resolvedSubaction
  )) || refs.find((ref) => ref.action === resolvedAction) || refs[0] || null;
}

function hiddenDialogue(speakerId = null) {
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
    this.navigation = new BrowserNavigation({
      world: this.bundle.world,
      workSeats: this.bundle.work_seats,
    });
    this.workSeatReducer = new BrowserWorkSeatReducer({
      workSeats: this.bundle.work_seats,
      employees: this.bundle.employees,
      assets: this.bundle.assets,
      characters: this.bundle.characters,
    });
    this.actorReducer = new BrowserActorReducer({
      employees: this.bundle.employees,
      navigation: this.navigation,
      workSeat: this.workSeatReducer,
    });
    this.speechReducer = new BrowserSpeechReducer({
      employees: this.bundle.employees,
      dialogue: this.bundle.dialogue,
      conversation: this.bundle.conversation,
      navigation: this.navigation,
      workSeat: this.workSeatReducer,
      seed: this.seed,
    });
    this.effectsReducer = new BrowserEffectsReducer({
      employees: this.bundle.employees,
      effects: this.bundle.effects,
      seed: this.seed,
    });
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

  _renderActor(employeeId, actor, sampleMs = this.clockMs) {
    const assignment = actorAssignment(actor);
    const workstationId = actor.workstation_id ?? assignment.workstation_id ?? null;
    const characterId = actor.character_id ?? null;
    const position = isObject(actor.position) ? actor.position : {};
    const route = isObject(position.route) ? position.route : null;
    const transition = isObject(position.seat_transition) ? position.seat_transition : null;
    const assignmentDirection = String(assignment.facing || "SE").toUpperCase();
    const visible = actor.presence !== "home";
    let renderOwner = visible ? "work_seat" : "none";
    let action = visible ? "work" : null;
    let direction = assignmentDirection;
    let subaction = visible ? "normal_work" : null;
    let currentUv = null;
    let ground = null;
    let routePhase = null;
    let routeElapsed = null;
    let routeDuration = null;
    let cumulativeDistance = 0;
    let frameClock = 0;
    let visibilityAlpha = visible ? 1 : 0;

    const employee = this.bundle.employees?.[employeeId] || {};
    const movementProfile = employee.movement_profile || {};
    if (transition) {
      renderOwner = transition.render_owner || "walking_depth";
      action = transition.action || "move";
      direction = String(transition.direction || assignmentDirection).toUpperCase();
      subaction = transition.subaction || "idle";
      const duration = Math.max(DEFAULT_STEP_MS, integer(transition.duration_ms, 240));
      const elapsed = Math.min(duration, Math.max(0, integer(transition.elapsed_ms, 0)));
      const progress = duration > 0 ? elapsed / duration : 1;
      const from = Array.isArray(transition.from_ground_xy)
        ? transition.from_ground_xy
        : [0, 0];
      const to = Array.isArray(transition.to_ground_xy) ? transition.to_ground_xy : from;
      const talkRoundBias = route?.phase === "talk_outbound" ? 1e-10 : 0;
      ground = [
        round4(numeric(from[0]) + (numeric(to[0]) - numeric(from[0])) * progress - talkRoundBias),
        round4(numeric(from[1]) + (numeric(to[1]) - numeric(from[1])) * progress - talkRoundBias),
      ];
      currentUv = Array.isArray(position.uv) ? [...position.uv] : null;
      routePhase = route?.phase || transition.completion || null;
      routeElapsed = route?.elapsed_ms ?? elapsed;
      routeDuration = route?.duration_ms ?? duration;
      cumulativeDistance = route
        ? this.navigation.routeDistancePx(
          { movement_speed_multiplier: movementProfile.speed_multiplier || 1 },
          route,
        )
        : Math.hypot(ground[0] - numeric(from[0]), ground[1] - numeric(from[1]));
      frameClock = elapsed;
      visibilityAlpha = numeric(transition.visibility_alpha, 1);
    } else if (route) {
      renderOwner = route.render_owner || "walking_depth";
      action = route.action || "move";
      direction = String(route.direction || route.raw_direction || assignmentDirection).toUpperCase();
      subaction = route.subaction || "idle";
      currentUv = Array.isArray(position.uv) ? [...position.uv] : null;
      ground = Array.isArray(position.ground_xy) ? [...position.ground_xy] : null;
      routePhase = route.phase || null;
      routeElapsed = integer(route.elapsed_ms, 0);
      routeDuration = integer(route.duration_ms, 0);
      cumulativeDistance = this.navigation.routeDistancePx(
        { movement_speed_multiplier: movementProfile.speed_multiplier || 1 },
        route,
      );
      frameClock = routeElapsed;
      visibilityAlpha = numeric(route.visibility_alpha, 1);
    } else if (visible) {
      frameClock = integer(actor.behavior?.work_loop_elapsed_ms, 0);
    }

    const normalizedAction = action === "happy" || action === "sad" ? action : action;
    const normalizedDirection = action === "happy" || action === "sad" ? null : direction;
    const normalizedSubaction = action === "happy" || action === "sad" || action === "move" || action === "idle"
      ? null
      : subaction;
    const frameRef = action
      ? frameReference(this.bundle, actor, {
        action,
        direction: normalizedDirection || direction,
        subaction: normalizedSubaction,
      })
      : null;
    const frameIds = Array.isArray(frameRef?.frame_ids) ? frameRef.frame_ids : [];
    const frameCount = Math.max(1, frameIds.length);
    let frameIndex = 0;
    if (action) {
      if (action === "move" && [
        "to_portal",
        "to_workseat",
        "wander_out",
        "wander_back",
        "talk_outbound",
        "talk_return",
      ].includes(routePhase)) {
        const walkFrameDistanceCells = Math.round(
          0.65 * Number(movementProfile.speed_multiplier || 1) * 10000,
        ) / 10000;
        frameIndex = this.navigation.walkCycleFrameIndex(
          cumulativeDistance,
          frameCount,
          walkFrameDistanceCells,
        );
      } else {
        frameIndex = Math.floor(frameClock / DEFAULT_CHARACTER_FRAME_MS) % frameCount;
      }
    }
    const frameId = frameIds[frameIndex % frameIds.length] ?? null;
    const pcFrameCount = renderOwner === "work_seat" && workstationId
      ? this.workSeatReducer.pcFrameCount(workstationId)
      : null;
    const pcFrameIndex = pcFrameCount
      ? integer(actor.behavior?.work_loop_count, 0) % pcFrameCount
      : null;
    const rowActivity = actor.activity ?? "working";
    const row = {
      employee_id: employeeId,
      character_id: characterId,
      floor_id: actor.floor_id ?? assignment.floor_id ?? this.floorId,
      activity: rowActivity,
      presence: actor.presence ?? "present",
      anchor_xy: [...DEFAULT_ANCHOR],
      assignment_order: assignment.assignment_order ?? null,
      channels: {
        pc: {
          frame_count: pcFrameCount,
          frame_index: pcFrameIndex,
          frame_ms: DEFAULT_PC_FRAME_MS,
        },
      },
      character_frame_count: frameCount,
      character_frame_index: frameIndex,
      character_frame_ms: DEFAULT_CHARACTER_FRAME_MS,
      cumulative_distance_px: cumulativeDistance,
      dialogue: hiddenDialogue(),
      action,
      resolved_action: normalizedAction,
      direction: normalizedDirection,
      resolved_direction: normalizedDirection,
      subaction,
      resolved_subaction: normalizedSubaction,
      workstation_id: workstationId,
      render_owner: renderOwner,
      ground_xy: ground,
      route_phase: routePhase,
      route_elapsed_ms: routeElapsed,
      route_duration_ms: routeDuration,
      animation_clock_ms: action ? frameIndex * DEFAULT_CHARACTER_FRAME_MS : 0,
      frame_id: frameId,
      frame_index: frameIndex,
      pc_frame_index: pcFrameIndex,
      pc_frame_count: pcFrameCount,
      pc_frame_ms: DEFAULT_PC_FRAME_MS,
      stamina: actor.stamina ? cloneJsonValue(actor.stamina) : null,
      occluder_placement_ids: [],
      visibility_alpha: visibilityAlpha,
      visible: Boolean(visible && visibilityAlpha > 0 && renderOwner !== "none"),
      speech_category: null,
      speech_mode: null,
      speech_session_id: null,
    };
    const speechActor = this.state.speech_snapshot?.actors?.[employeeId];
    const sessions = [
      ...Object.values(this.state.speech_snapshot?.active_sessions || {}),
      ...Object.values(this.state.speech_snapshot?.completed_sessions || {}),
    ].filter((session) => isObject(session) && session.participants?.includes(employeeId));
    sessions.sort((left, right) => (
      integer(left.movement_started_ms, left.start_ms || 0)
      - integer(right.movement_started_ms, right.start_ms || 0)
      || String(left.session_id).localeCompare(String(right.session_id))
    ));
    const sessionId = actor.behavior?.talk?.session_id
      || speechActor?.last_session_id
      || null;
    const speechSession = sessions.find((session) => session.session_id === sessionId)
      || sessions.at(-1)
      || null;
    if (speechSession && (
      speechSession.session_id in (this.state.speech_snapshot?.active_sessions || {})
      || actor.behavior?.talk?.session_id === speechSession.session_id
    )) {
      row.speech_session_id = speechSession.session_id;
      row.speech_mode = speechSession.mode ?? null;
      row.speech_category = speechSession.category ?? null;
      const dialogue = this.speechReducer.dialogueForActor(
        this.state.speech_snapshot,
        employeeId,
        Number(sampleMs),
      );
      if (dialogue) row.dialogue = dialogue;
    }
    const emotion = speechActor?.speech_phase === "emotion" ? speechActor.emotion : null;
    if (emotion === "happy" || emotion === "sad") {
      const emotionUntil = integer(speechActor.emotion_until_ms, Number(sampleMs));
      const emotionStart = Math.max(0, emotionUntil - 1200);
      const emotionFrameRef = frameReference(this.bundle, actor, {
        action: emotion,
        direction: null,
        subaction: null,
      });
      const emotionFrameIds = Array.isArray(emotionFrameRef?.frame_ids)
        ? emotionFrameRef.frame_ids
        : [];
      const emotionFrameCount = Math.max(1, emotionFrameIds.length);
      const emotionFrameIndex = Math.floor(Math.max(0, Number(sampleMs) - emotionStart) / DEFAULT_CHARACTER_FRAME_MS) % emotionFrameCount;
      row.action = emotion;
      row.resolved_action = emotion;
      row.direction = direction;
      row.resolved_direction = null;
      row.subaction = emotion;
      row.resolved_subaction = null;
      row.render_owner = "walking_depth";
      row.character_frame_count = emotionFrameCount;
      row.character_frame_index = emotionFrameIndex;
      row.frame_index = emotionFrameIndex;
      row.frame_id = emotionFrameIds[emotionFrameIndex] ?? null;
      row.animation_clock_ms = emotionFrameIndex * DEFAULT_CHARACTER_FRAME_MS;
    }
    const effectChannels = this.effectsReducer.channels(actor, Number(sampleMs));
    row.channels = { ...row.channels, ...effectChannels };
    return row;
  }

  step(elapsedMs, { actorCommands = [], speechCommands = [] } = {}) {
    this._assertAlive();
    if (!Array.isArray(actorCommands) || !Array.isArray(speechCommands)) {
      throw new TypeError("actorCommands and speechCommands must be arrays");
    }
    for (const command of actorCommands) this.command(command);
    for (const command of speechCommands) this.command(command);

    const slices = this.clock.pushElapsed(elapsedMs);
    const events = [];
    const firstClock = this.clock.simulationClockMs - slices.length * this.clock.stepMs;
    const committedTalkActors = new Set();

    const bridgeFromActorEvents = (actorEvents, commands = []) => {
      const bridge = [...commands];
      const bridgeKeys = new Set(
        bridge
          .filter((command) => isObject(command))
          .map((command) => `${command.type}|${command.employee_id}`),
      );
      for (const event of actorEvents) {
        const employeeId = event?.employee_id;
        if (typeof employeeId !== "string") continue;
        let command = null;
        if (event.type === "behavior_started" && event.behavior === "talk") {
          command = {
            type: "behavior_started",
            employee_id: employeeId,
            behavior: "talk",
            effective_at_ms: integer(event.timestamp_ms),
          };
        } else if (event.type === "portal_entered") {
          command = {
            type: "spawned",
            employee_id: employeeId,
            effective_at_ms: integer(event.timestamp_ms),
          };
        } else if (event.type === "workseat_reentered") {
          command = {
            type: "workseat_entered",
            employee_id: employeeId,
            effective_at_ms: integer(event.timestamp_ms),
          };
        } else if (event.type === "talk_returned") {
          command = {
            type: "returned_to_work",
            employee_id: employeeId,
            effective_at_ms: integer(event.timestamp_ms),
          };
        } else if (event.type === "talk_cancelled") {
          command = { type: "cancel_talk", employee_id: employeeId };
        }
        if (!command) continue;
        const key = `${command.type}|${command.employee_id}`;
        if (!bridgeKeys.has(key)) {
          bridge.push(command);
          bridgeKeys.add(key);
        }
      }
      return bridge;
    };

    const commitTalkCommands = (talkCommands, timestampMs, chunkActorEvents) => {
      for (const command of [...talkCommands].sort((left, right) => (
        String(left.employee_id).localeCompare(String(right.employee_id))
      ))) {
        const employeeId = command?.employee_id;
        if (typeof employeeId !== "string") continue;
        const commandKey = `${command.session_id || ""}|${employeeId}`;
        if (committedTalkActors.has(commandKey)) continue;
        const actor = this.state.actor_snapshot.actors[employeeId];
        if (!actor || actor.behavior?.talk?.session_id === command.session_id) {
          committedTalkActors.add(commandKey);
          continue;
        }
        const actorResult = this.actorReducer.step(
          actor,
          {
            snapshot: this.state.actor_snapshot,
            nowMs: timestampMs,
          },
          0,
          [command],
        );
        chunkActorEvents.push(...actorResult.events);
        committedTalkActors.add(commandKey);
      }
    };

    slices.forEach((slice, index) => {
      const startMs = firstClock + index * this.clock.stepMs;
      this._applyClock(startMs);
      const commands = index === 0 ? actorCommands : [];
      const chunkActorEvents = [];
      for (const employeeId of Object.keys(this.state.actor_snapshot.actors).sort()) {
        const actor = this.state.actor_snapshot.actors[employeeId];
        // The Task 2 fixture intentionally contains only the snapshot
        // channels.  A production bundle includes employee metadata, which
        // is required before the behavior reducers are allowed to mutate an
        // actor.
        if (!this.bundle.employees?.[employeeId]) continue;
        const actorCommandsForActor = commands.filter(
          (command) => command.employee_id === employeeId,
        );
        const actorResult = this.actorReducer.step(
          actor,
          {
            snapshot: this.state.actor_snapshot,
            nowMs: startMs,
          },
          slice,
          actorCommandsForActor,
        );
        chunkActorEvents.push(...actorResult.events);
      }

      const speechBridgeCommands = bridgeFromActorEvents(
        chunkActorEvents,
        index === 0 ? speechCommands : [],
      );
      const speechResult = this.speechReducer.step(
        this.state.speech_snapshot,
        {
          actorSnapshot: this.state.actor_snapshot,
          conversationSnapshot: this.state.conversation_snapshot,
          elapsedMs: slice,
          commands: speechBridgeCommands,
          dialogueSeed: this.seed,
        },
      );
      for (const speechEvent of speechResult.events) {
        if (speechEvent.type !== "emotion_started") continue;
        const emotion = speechEvent.emotion;
        if (emotion !== "sad" && emotion !== "happy") continue;
        for (const employeeId of speechEvent.participants || []) {
          const actor = this.state.actor_snapshot.actors[employeeId];
          const employee = this.bundle.employees?.[employeeId];
          if (!actor || !employee) continue;
          this.actorReducer.applyEmotionEffect(
            {
              snapshot: this.state.actor_snapshot,
              nowMs: startMs + slice,
            },
            actor,
            employee,
            emotion,
            integer(speechEvent.timestamp_ms, startMs + slice),
            chunkActorEvents,
            speechEvent.session_id ?? null,
          );
        }
      }
      commitTalkCommands(speechResult.talkCommands, startMs + slice, chunkActorEvents);

      const returnCommands = bridgeFromActorEvents(chunkActorEvents, [])
        .filter((command) => command.type === "returned_to_work");
      if (returnCommands.length) {
        const returnResult = this.speechReducer.step(
          this.state.speech_snapshot,
          {
            actorSnapshot: this.state.actor_snapshot,
            conversationSnapshot: this.state.conversation_snapshot,
            elapsedMs: 0,
            commands: returnCommands,
            dialogueSeed: this.seed,
          },
        );
        for (const speechEvent of returnResult.events) {
          if (speechEvent.type !== "emotion_started") continue;
          const emotion = speechEvent.emotion;
          if (emotion !== "sad" && emotion !== "happy") continue;
          for (const employeeId of speechEvent.participants || []) {
            const actor = this.state.actor_snapshot.actors[employeeId];
            const employee = this.bundle.employees?.[employeeId];
            if (!actor || !employee) continue;
            this.actorReducer.applyEmotionEffect(
              {
                snapshot: this.state.actor_snapshot,
                nowMs: startMs + slice,
              },
              actor,
              employee,
              emotion,
              integer(speechEvent.timestamp_ms, startMs + slice),
              chunkActorEvents,
              speechEvent.session_id ?? null,
            );
          }
        }
        commitTalkCommands(returnResult.talkCommands, startMs + slice, chunkActorEvents);
      }

      events.push(...chunkActorEvents.map((event) => ({ source: "actor", ...event })));
      this._applyClock(startMs + slice);
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
        .map((employeeId) => this._renderActor(employeeId, actors[employeeId], atMs)),
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
