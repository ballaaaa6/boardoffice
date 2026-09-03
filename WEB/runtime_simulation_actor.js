import { stableHash64 } from "./runtime_simulation_prng.js";

const TICK_MS = 60;
const WORK_LOOP_MS = 720;
const WORK_CHARACTER_FRAME_MS = 360;
const MAX_STAMINA_MILLI = 100000;
const LOW_THRESHOLD_MILLI = 30000;
const CRITICAL_THRESHOLD_MILLI = 10000;
const PORTAL_FADE_STEPS = 4;
const EVENT_ACTIVITY = Object.freeze({
  talk: "talking",
  background_effect: "popup_event",
  popup: "popup_event",
  wander: "wandering",
});
const EVENT_LAST_EVENT = Object.freeze({
  talk: "talk_recovery",
  background_effect: "background_effect_recovery",
  popup: "popup_recovery",
  wander: "wander_recovery",
});
const WEIGHTED_EVENTS = Object.freeze(["talk", "background_effect", "popup", "wander"]);
const ROUTE_PHASES = new Set([
  "to_portal",
  "portal_exit",
  "portal_entry",
  "to_workseat",
  "wander_out",
  "wander_back",
  "talk_outbound",
  "talk_hold",
  "talk_return",
]);
const ROUTE_ACTIVITIES = new Set(["going_home", "returning_to_work"]);
const ROUTE_PATH_PHASES = new Set([
  "to_portal",
  "to_workseat",
  "wander_out",
  "wander_back",
  "talk_outbound",
  "talk_return",
]);

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function clone(value) {
  if (typeof globalThis.structuredClone === "function") return globalThis.structuredClone(value);
  return JSON.parse(JSON.stringify(value));
}

function round4(value) {
  return Math.round(Number(value) * 10000) / 10000;
}

function integer(value, fallback = 0) {
  return Number.isFinite(Number(value)) ? Math.trunc(Number(value)) : fallback;
}

function thresholdBand(current) {
  if (current <= CRITICAL_THRESHOLD_MILLI) return "critical";
  if (current <= LOW_THRESHOLD_MILLI) return "low";
  return "normal";
}

function quantizeMs(milliseconds) {
  const value = Math.max(TICK_MS, Number(milliseconds));
  const quotient = value / TICK_MS;
  const lower = Math.floor(quotient);
  const fraction = quotient - lower;
  const rounded = fraction < 0.5
    ? lower
    : fraction > 0.5 || lower % 2 === 1
      ? lower + 1
      : lower;
  return Math.max(TICK_MS, rounded * TICK_MS);
}

export class BrowserActorReducer {
  constructor({ employees = {}, navigation, workSeat, visualSelection } = {}) {
    if (!navigation || !workSeat) throw new TypeError("BrowserActorReducer needs navigation and WorkSeat reducers");
    if (!visualSelection) throw new TypeError("BrowserActorReducer needs visual selection");
    this.employees = employees;
    this.navigation = navigation;
    this.workSeat = workSeat;
    this.visualSelection = visualSelection;
  }

  employeeFor(actor) {
    const employee = this.employees?.[actor.employee_id];
    if (!isObject(employee)) throw new TypeError(`Unknown employee: ${actor.employee_id}`);
    return employee;
  }

  movementProfile(employee) {
    const profile = employee.movement_profile;
    if (!isObject(profile) || !(Number(profile.speed_multiplier) > 0)) {
      throw new TypeError(`${employee.employee_id}: movement profile is invalid`);
    }
    return profile;
  }

  staminaProfile(employee) {
    const profile = employee.stamina_profile?.stamina_profile;
    if (!isObject(profile) || !Number.isInteger(profile.work_drain_milli_per_second)) {
      throw new TypeError(`${employee.employee_id}: stamina profile is invalid`);
    }
    return profile;
  }

  staminaPolicy(employee) {
    const policy = employee.stamina_profile?.stamina_policy;
    if (!isObject(policy)) throw new TypeError(`${employee.employee_id}: stamina policy is invalid`);
    return policy;
  }

  nextIntervalMs(employee, { counter, nowMs, event = null } = {}) {
    const profile = this.staminaProfile(employee);
    const policy = this.staminaPolicy(employee);
    const values = event
      ? policy.recovery_events?.[event]?.interval_seconds_range
      : policy.target_work_cycle_seconds_range;
    if (!Array.isArray(values) || values.length !== 2) {
      throw new TypeError(`${employee.employee_id}: interval range is invalid`);
    }
    const lower = Number(values[0]);
    const upper = Number(values[1]);
    const ticket = stableHash64(
      employee.employee_id,
      profile.profile_seed,
      "interval",
      event || "schedule",
      Number(counter),
      Number(nowMs),
    );
    const seconds = lower + Number(ticket % BigInt(upper - lower + 1));
    const milliseconds = Math.floor(
      seconds * 1000 * Number(profile.event_timing_multiplier_percent) / 100,
    );
    return quantizeMs(milliseconds);
  }

  scheduleNextEvent(actor, employee, nowMs) {
    return Number(nowMs) + this.nextIntervalMs(employee, {
      counter: Number(actor.behavior.event_counter || 0),
      nowMs,
    });
  }

  chooseBehaviorEvent(actor, employee, nowMs) {
    const policy = this.staminaPolicy(employee);
    const recoveryEvents = policy.recovery_events;
    const eligible = [];
    for (const event of WEIGHTED_EVENTS) {
      const weight = Number(recoveryEvents?.[event]?.selection_weight || 0);
      const cooldownUntil = Number(actor.behavior.cooldowns?.[event] || 0);
      if (weight > 0 && Number(nowMs) >= cooldownUntil) eligible.push([event, weight]);
    }
    if (eligible.length === 0) throw new TypeError("No eligible weighted recovery event");
    const total = eligible.reduce((sum, [, weight]) => sum + weight, 0);
    let ticket = Number(stableHash64(
      employee.employee_id,
      this.staminaProfile(employee).profile_seed,
      Number(actor.behavior.event_counter || 0),
      Number(nowMs),
    ) % BigInt(total));
    for (const [event, weight] of eligible) {
      if (ticket < weight) return event;
      ticket -= weight;
    }
    return eligible.at(-1)[0];
  }

  activityDurationMs(employee, event, counter) {
    const values = this.staminaPolicy(employee).recovery_events?.[event]?.activity_duration_seconds_range;
    if (!Array.isArray(values) || values.length !== 2) {
      throw new TypeError(`${employee.employee_id}: activity duration range is invalid`);
    }
    const lower = Number(values[0]);
    const upper = Number(values[1]);
    if (!Number.isInteger(lower) || !Number.isInteger(upper) || lower < 1 || upper < lower) {
      throw new TypeError(`${employee.employee_id}: activity duration range is invalid`);
    }
    const ticket = stableHash64(
      employee.employee_id,
      this.staminaProfile(employee).profile_seed,
      "duration",
      event,
      Number(counter),
    );
    return quantizeMs(
      (lower + Number(ticket % BigInt(upper - lower + 1)))
      * 1000
      * Number(this.staminaProfile(employee).event_timing_multiplier_percent)
      / 100,
    );
  }

  ensureVisualChannels(actor) {
    if (!isObject(actor.behavior)) throw new TypeError(`${actor.employee_id}: behavior is required`);
    if (!isObject(actor.behavior.visual_channels)) actor.behavior.visual_channels = {};
    for (const channel of ["vfx", "humanball"]) {
      if (!isObject(actor.behavior.visual_channels[channel])) {
        actor.behavior.visual_channels[channel] = this.visualSelection.initialChannelState(channel);
      }
      this.visualSelection.validateChannelState(actor.behavior.visual_channels[channel], channel);
    }
    return actor.behavior.visual_channels;
  }

  visualChannelForEvent(event) {
    if (event === "background_effect") return "vfx";
    if (event === "popup") return "humanball";
    return null;
  }

  visualEventId(actor, event, counter, timestampMs) {
    return `visual:${actor.employee_id}:${event}:${counter}:${timestampMs}`;
  }

  presentationForBehavior(actor, event) {
    if (event === "talk") {
      return { channel: "conversation", behavior: "talk", binding: "speech_scheduler_behavior_request" };
    }
    const channel = this.visualChannelForEvent(event);
    if (channel) {
      const binding = this.ensureVisualChannels(actor)[channel].active_binding;
      const payload = {
        channel,
        asset_id: binding?.asset_id ?? null,
        selection_source: binding?.selection_source || "shuffle_bag",
        render_owner: "work_seat",
        action: "work",
        subaction: "normal_work",
        character_frame_ms: 360,
      };
      payload[channel === "vfx" ? "effect_frame_ms" : "humanball_frame_ms"] = 240;
      if (binding) {
        payload.visual_event_id = binding.event_id;
        payload.visual_generation = binding.generation;
        payload.visual_cursor_after = binding.cursor_after;
      }
      return payload;
    }
    return { channel: "movement", render_owner: "walking_depth", action: "move", subaction: "idle" };
  }

  startEvent(context, actor, employee, event, timestampMs, events) {
    if (!WEIGHTED_EVENTS.includes(event)) throw new TypeError(`Unknown weighted recovery event: ${event}`);
    const counter = Number(actor.behavior.event_counter || 0) + 1;
    actor.behavior.event_counter = counter;
    actor.behavior.active_event = event;
    actor.behavior.activity_started_ms = Number(timestampMs);
    actor.behavior.activity_until_ms = event === "talk"
      ? null
      : Number(timestampMs) + this.activityDurationMs(employee, event, counter);
    actor.behavior.next_event_due_ms = null;
    actor.behavior.talk = null;
    actor.behavior.cooldowns = actor.behavior.cooldowns || {};
    actor.behavior.cooldowns[event] = Number(timestampMs) + this.nextIntervalMs(employee, {
      counter,
      nowMs: Number(timestampMs),
      event,
    });
    actor.presence = "present";
    actor.activity = EVENT_ACTIVITY[event];
    actor.conversation_phase = event === "talk" ? "talk_pending" : null;
    const channel = this.visualChannelForEvent(event);
    if (channel) {
      const visualChannels = this.ensureVisualChannels(actor);
      const visualEventId = this.visualEventId(actor, event, counter, timestampMs);
      const selected = this.visualSelection.select(visualChannels[channel], {
        channel,
        simulationSeed: String(context.snapshot.determinism.simulation_seed),
        employeeId: actor.employee_id,
        eventId: visualEventId,
        startedAtMs: Number(timestampMs),
        endsAtMs: Number(actor.behavior.activity_until_ms),
      });
      visualChannels[channel] = selected.state;
    }
    this.appendEvent(context, events, actor, timestampMs, "behavior_started", {
      behavior: event,
      activity: actor.activity,
      activity_until_ms: actor.behavior.activity_until_ms,
      presentation: this.presentationForBehavior(actor, event),
    });
  }

  appendEvent(context, events, actor, timestampMs, type, payload = {}) {
    const determinism = context.snapshot.determinism;
    const eventIndex = Number(determinism.root_event_counter || 0);
    determinism.root_event_counter = eventIndex + 1;
    const event = {
      event_index: eventIndex,
      timestamp_ms: Number(timestampMs),
      employee_id: actor.employee_id,
      type,
      ...clone(payload),
    };
    events.push(event);
    return event;
  }

  routeRecord({ phase, startUv, targetUv, path, durationMs, action = "move", subaction = "idle", direction = null }) {
    if (!ROUTE_PHASES.has(phase)) throw new TypeError(`Unknown actor route phase: ${phase}`);
    return {
      phase,
      start_uv: [...startUv],
      target_uv: [...targetUv],
      path_cells_uv: path.map((value) => [...value]),
      elapsed_ms: 0,
      duration_ms: Number(durationMs),
      render_owner: "walking_depth",
      action,
      subaction,
      direction,
      raw_direction: direction,
      visibility_alpha: 1,
    };
  }

  startRoute(actor, employee, { phase, startUv, targetUv, path, durationMs = null, action = "move", subaction = "idle", updateWindow = true }) {
    const profile = this.movementProfile(employee);
    const duration = durationMs ?? this.navigation.routeDurationMs(path, profile.speed_multiplier);
    let direction = null;
    if (startUv[0] !== targetUv[0] || startUv[1] !== targetUv[1]) {
      try {
        direction = this.navigation.directionForStep(startUv, targetUv);
      } catch {
        direction = null;
      }
    }
    actor.position.route = this.routeRecord({
      phase,
      startUv,
      targetUv,
      path,
      durationMs: duration,
      action,
      subaction,
      direction,
    });
    actor.position.floor_id = actor.assignment.floor_id;
    actor.position.uv = [...startUv];
    actor.position.ground_xy = this.navigation.uvCellCenterToPixel(startUv);
    if (updateWindow) {
      actor.behavior.activity_until_ms = Number(actor.behavior.activity_started_ms) + Number(duration);
    }
  }

  beginSeatExit(actor, employee) {
    if (actor.position.seat_transition) throw new TypeError(`${actor.employee_id}: seat transition already active`);
    const gate = this.workSeat.navigationAccess(actor.assignment.workstation_id).transition_gate_uv;
    const seatGround = this.workSeat.visualCharacterAnchor(
      actor.assignment.floor_id,
      actor.assignment.workstation_id,
      actor.character_id,
    );
    const gateGround = this.navigation.uvCellCenterToPixel(gate);
    const route = actor.position.route;
    const direction = route?.direction || actor.assignment.facing || "SE";
    actor.position.seat_transition = this.workSeat.seatTransitionRecord({
      phase: "seat_exit",
      fromGround: seatGround,
      toGround: gateGround,
      direction,
    });
    actor.position.ground_xy = [...seatGround];
    actor.position.uv = null;
    return gate;
  }

  beginSeatEntry(actor, employee, gate, completion, timestampMs) {
    const fromGround = Array.isArray(actor.position.ground_xy)
      ? actor.position.ground_xy
      : this.navigation.uvCellCenterToPixel(gate);
    const seatGround = this.workSeat.visualCharacterAnchor(
      actor.assignment.floor_id,
      actor.assignment.workstation_id,
      actor.character_id,
    );
    actor.position.seat_transition = this.workSeat.seatTransitionRecord({
      phase: "seat_entry",
      fromGround,
      toGround: seatGround,
      direction: actor.assignment.facing || "SE",
      completion,
    });
    actor.position.ground_xy = fromGround.map(round4);
    actor.position.uv = [...gate];
    actor.position.route = null;
    actor.behavior.activity_until_ms = Number(timestampMs) + 240;
  }

  finishSeatEntry(context, actor, employee, timestampMs, events) {
    const completion = actor.position.seat_transition?.completion;
    if (completion === "talk_return") {
      this.finishTalkActor(context, actor, employee, timestampMs, events);
      return;
    }
    actor.position = {
      floor_id: actor.assignment.floor_id,
      uv: null,
      ground_xy: null,
      route: null,
    };
    actor.presence = "present";
    actor.activity = "working";
    actor.conversation_phase = null;
    actor.behavior.next_event_due_ms = this.scheduleNextEvent(actor, employee, timestampMs);
    actor.behavior.active_event = null;
    actor.behavior.activity_started_ms = Number(timestampMs);
    actor.behavior.activity_until_ms = null;
    actor.behavior.work_loop_elapsed_ms = 0;
    actor.behavior.work_loop_count = 0;
    actor.behavior.pending_home = false;
    actor.behavior.pending_home_due_ms = null;
    actor.last_event = "return_requested";
    this.appendEvent(context, events, actor, timestampMs, "workseat_reentered", {
      assignment_retained: true,
      slot_id: actor.assignment.slot_id,
      render_owner: "work_seat",
      action: "work",
      subaction: "normal_work",
    });
  }

  advanceSeatTransition(context, actor, employee, startMs, targetMs, events) {
    let nowMs = Number(startMs);
    while (nowMs < targetMs) {
      const transition = actor.position.seat_transition;
      if (!isObject(transition)) break;
      const duration = Math.max(TICK_MS, Number(transition.duration_ms));
      const elapsed = Number(transition.elapsed_ms || 0);
      const remaining = duration - elapsed;
      if (remaining <= 0) {
        if (transition.phase === "seat_entry") {
          const completion = transition.completion;
          if (completion === "to_workseat" || completion === "talk_return") {
            this.finishSeatEntry(context, actor, employee, nowMs, events);
          } else {
            delete actor.position.seat_transition;
          }
        } else delete actor.position.seat_transition;
        continue;
      }
      const untilTick = TICK_MS - (elapsed % TICK_MS);
      const step = Math.min(targetMs - nowMs, remaining, untilTick);
      transition.elapsed_ms = elapsed + step;
      nowMs += step;
      const progress = Math.min(1, Math.max(0, transition.elapsed_ms / duration));
      const from = transition.from_ground_xy;
      const to = transition.to_ground_xy;
      actor.position.ground_xy = [
        round4(Number(from[0]) + (Number(to[0]) - Number(from[0])) * progress),
        round4(Number(from[1]) + (Number(to[1]) - Number(from[1])) * progress),
      ];
      // The WorkSeat entry transition owns the visual interpolation; the
      // navigation UV is no longer a walk pose once the actor reaches the
      // gate, matching Central's seat-entry boundary.
      actor.position.uv = null;
      if (transition.elapsed_ms >= duration) {
        if (transition.phase === "seat_entry") {
          const completion = transition.completion;
          if (completion === "to_workseat" || completion === "talk_return") {
            this.finishSeatEntry(context, actor, employee, nowMs, events);
          } else {
            delete actor.position.seat_transition;
          }
        } else delete actor.position.seat_transition;
      }
    }
    return nowMs;
  }

  finishRoute(context, actor, employee, timestampMs, events) {
    const route = actor.position.route;
    if (!isObject(route)) throw new TypeError(`${actor.employee_id}: route segment is missing`);
    const floorId = actor.assignment.floor_id;
    if (route.phase === "talk_outbound") {
      const talk = actor.behavior.talk;
      if (!isObject(talk)) throw new TypeError(`${actor.employee_id}: talk outbound metadata is missing`);
      const endpoint = [...talk.endpoint_uv];
      actor.position.floor_id = floorId;
      actor.position.uv = [...endpoint];
      actor.position.ground_xy = this.navigation.uvCellCenterToPixel(endpoint);
      actor.position.route = this.routeRecord({
        phase: "talk_hold",
        startUv: endpoint,
        targetUv: endpoint,
        path: [endpoint],
        durationMs: Math.max(TICK_MS, integer(talk.return_start_at_ms, timestampMs) - Number(timestampMs)),
        action: "idle",
        subaction: "idle",
        direction: String(talk.endpoint_facing || route.direction || actor.assignment.facing || "SE").toUpperCase(),
      });
      actor.conversation_phase = "talk_arrival";
      actor.behavior.activity_started_ms = Number(timestampMs);
      actor.behavior.activity_until_ms = integer(talk.return_start_at_ms, timestampMs);
      this.appendEvent(context, events, actor, timestampMs, "talk_arrived", {
        session_id: talk.session_id,
        mode: talk.mode,
        partner_id: talk.partner_id,
        endpoint_uv: [...endpoint],
      });
      if (integer(talk.return_start_at_ms, timestampMs) <= Number(timestampMs)) {
        this.beginTalkReturn(context, actor, employee, Number(timestampMs), events);
      }
      return;
    }
    if (route.phase === "talk_hold") {
      this.beginTalkReturn(context, actor, employee, Number(timestampMs), events);
      return;
    }
    if (route.phase === "talk_return") {
      this.beginSeatEntry(actor, employee, route.target_uv, "talk_return", Number(timestampMs));
      return;
    }
    if (route.phase === "to_portal") {
      const { inside, outside } = this.navigation.portalPair(floorId);
      actor.behavior.activity_started_ms = Number(timestampMs);
      this.startRoute(actor, employee, {
        phase: "portal_exit",
        startUv: inside,
        targetUv: outside,
        path: [inside, outside],
        durationMs: PORTAL_FADE_STEPS * TICK_MS,
      });
      this.appendEvent(context, events, actor, timestampMs, "portal_exit_started", {
        inside_uv: [...inside],
        outside_uv: [...outside],
        fade_ms: PORTAL_FADE_STEPS * TICK_MS,
      });
      return;
    }
    if (route.phase === "portal_exit") {
      const profile = this.staminaProfile(employee);
      const range = profile.home_delay_seconds_range || [8, 20];
      const ticket = stableHash64(
        actor.employee_id,
        profile.profile_seed,
        "home-recovery",
        Number(actor.behavior.event_counter || 0),
      );
      const seconds = Number(range[0]) + Number(ticket % BigInt(Number(range[1]) - Number(range[0]) + 1));
      actor.position = { floor_id: null, uv: null, ground_xy: null, route: null };
      actor.presence = "home";
      actor.activity = "home_recovery";
      actor.conversation_phase = null;
      actor.stamina.current_milli = MAX_STAMINA_MILLI;
      actor.stamina.threshold_band = "normal";
      actor.stamina.drain_remainder = 0;
      actor.behavior.next_event_due_ms = null;
      actor.behavior.active_event = null;
      actor.behavior.activity_started_ms = Number(timestampMs);
      actor.behavior.activity_until_ms = quantizeMs(seconds * 1000) + Number(timestampMs);
      actor.behavior.work_loop_elapsed_ms = 0;
      actor.behavior.work_loop_count = 0;
      actor.behavior.pending_home = false;
      actor.behavior.pending_home_due_ms = null;
      actor.last_event = "home_recovered";
      this.appendEvent(context, events, actor, timestampMs, "portal_exited", {
        assignment_retained: true,
        render_owner: "walking_depth",
      });
      this.appendEvent(context, events, actor, timestampMs, "home_recovery_started", {
        ready_at_ms: actor.behavior.activity_until_ms,
        stamina_restored_milli: MAX_STAMINA_MILLI,
        assignment_retained: true,
      });
      return;
    }
    if (route.phase === "portal_entry") {
      const { inside } = this.navigation.portalPair(floorId);
      const gate = this.workSeat.navigationAccess(actor.assignment.workstation_id).transition_gate_uv;
      const path = this.navigation.findPath(inside, gate).path_cells_uv;
      actor.behavior.activity_started_ms = Number(timestampMs);
      this.startRoute(actor, employee, {
        phase: "to_workseat",
        startUv: inside,
        targetUv: gate,
        path,
      });
      this.appendEvent(context, events, actor, timestampMs, "portal_entered", {
        inside_uv: [...inside],
        assignment_retained: true,
      });
      return;
    }
    if (route.phase === "to_workseat") {
      const gate = route.target_uv;
      this.beginSeatEntry(actor, employee, gate, "to_workseat", timestampMs);
      return;
    }
    throw new TypeError(`${actor.employee_id}: unsupported route completion: ${route.phase}`);
  }

  advanceRoute(context, actor, employee, startMs, targetMs, events) {
    let nowMs = Number(startMs);
    while (nowMs < targetMs) {
      const route = actor.position.route;
      if (!isObject(route)) break;
      const duration = Math.max(TICK_MS, Number(route.duration_ms));
      const elapsed = Number(route.elapsed_ms || 0);
      const remaining = duration - elapsed;
      if (remaining <= 0) {
        this.finishRoute(context, actor, employee, nowMs, events);
        continue;
      }
      const untilTick = TICK_MS - (elapsed % TICK_MS);
      const step = Math.min(targetMs - nowMs, remaining, untilTick);
      route.elapsed_ms = elapsed + step;
      nowMs += step;
      const profile = this.movementProfile(employee);
      const pose = route.phase === "portal_entry" || route.phase === "portal_exit"
        ? this.navigation.portalPose(route, route.elapsed_ms)
        : route.phase === "talk_hold"
          ? {
            ground_xy: this.navigation.uvCellCenterToPixel(route.target_uv),
            current_uv: [...route.target_uv],
            direction: route.direction || actor.assignment.facing || "SE",
            raw_direction: route.raw_direction || route.direction || actor.assignment.facing || "SE",
            cumulative_distance_px: 0,
          }
          : this.navigation.pathPose(route.path_cells_uv, route.elapsed_ms, profile.speed_multiplier);
      actor.position.floor_id = actor.assignment.floor_id;
      actor.position.ground_xy = [...pose.ground_xy];
      actor.position.uv = pose.current_uv ? [...pose.current_uv] : null;
      route.direction = pose.direction;
      route.raw_direction = pose.raw_direction;
      route.visibility_alpha = pose.visibility_alpha ?? 1;
      if (route.phase === "talk_outbound") actor.conversation_phase = "walking_to_talk";
      if (route.phase === "talk_hold") {
        const talk = actor.behavior.talk || {};
        const talkStart = integer(talk.talk_start_at_ms, nowMs);
        const talkEnd = integer(talk.talk_end_at_ms, talkStart);
        const returnStart = integer(talk.return_start_at_ms, talkEnd);
        if (nowMs < talkStart) {
          actor.conversation_phase = "talk_arrival";
          route.action = "idle";
          route.subaction = "idle";
        } else if (nowMs < talkEnd) {
          actor.conversation_phase = "talking";
          route.action = "idle";
          route.subaction = "idle";
        } else if (["happy", "sad"].includes(talk.emotion) && nowMs < returnStart) {
          actor.conversation_phase = "talk_complete";
          route.action = talk.emotion;
          route.subaction = talk.emotion;
        } else {
          actor.conversation_phase = "talk_complete";
          route.action = "idle";
          route.subaction = "idle";
        }
      }
      if (actor.position.seat_transition?.phase === "seat_exit") {
        const transition = actor.position.seat_transition;
        transition.elapsed_ms = Math.min(
          Number(transition.duration_ms),
          Number(transition.elapsed_ms || 0) + step,
        );
        transition.to_ground_xy = pose.ground_xy.map(round4);
        if (transition.elapsed_ms >= Number(transition.duration_ms)) {
          delete actor.position.seat_transition;
        }
      }
      if (route.elapsed_ms >= duration) {
        this.finishRoute(context, actor, employee, nowMs, events);
      }
    }
    return nowMs;
  }

  advanceWorkLoop(actor, elapsedMs) {
    if (elapsedMs <= 0) return 0;
    const behavior = actor.behavior;
    const total = integer(behavior.work_loop_elapsed_ms, 0) + Number(elapsedMs);
    const completed = Math.floor(total / WORK_LOOP_MS);
    behavior.work_loop_elapsed_ms = total % WORK_LOOP_MS;
    behavior.work_loop_count = integer(behavior.work_loop_count, 0) + completed;
    return completed;
  }

  talkPath(value, label) {
    if (!Array.isArray(value) || value.length === 0) throw new TypeError(`${label} must be a non-empty path`);
    return value.map((item, index) => {
      if (!Array.isArray(item) || item.length !== 2 || !Number.isInteger(item[0]) || !Number.isInteger(item[1])) {
        throw new TypeError(`${label}[${index}] must contain integer coordinates`);
      }
      return [item[0], item[1]];
    });
  }

  startTalkSession(context, actor, employee, command, timestampMs, events) {
    const sessionId = command.session_id;
    if (typeof sessionId !== "string" || !sessionId) throw new TypeError("start_talk_session.session_id is required");
    const mode = String(command.mode || "standing_pair");
    const role = String(command.role || "initiator");
    if (!["self_talk", "ceo_front", "seated_host", "standing_pair"].includes(mode)) {
      throw new TypeError(`Unknown talk mode: ${mode}`);
    }
    if (!["initiator", "participant", "visitor"].includes(role)) {
      throw new TypeError(`Unknown talk role: ${role}`);
    }
    if (actor.presence !== "present") throw new TypeError(`${actor.employee_id}: talk session requires a present actor`);
    if (actor.activity === "talking" && !["talk_pending", "self_talk"].includes(actor.conversation_phase)) {
      throw new TypeError(`${actor.employee_id}: actor is already in a talk session`);
    }
    if (actor.activity === "working" && actor.behavior.active_event !== null) {
      throw new TypeError(`${actor.employee_id}: working actor has another active event`);
    }
    if (actor.activity === "working" && (actor.behavior.pending_home || actor.stamina.threshold_band === "critical")) {
      throw new TypeError(`${actor.employee_id}: critical actor cannot enter a talk session`);
    }
    const effectiveAt = integer(command.effective_at_ms, timestampMs);
    const talkStart = integer(command.talk_start_at_ms, timestampMs);
    const talkEnd = integer(command.talk_end_at_ms, talkStart);
    const returnStart = integer(command.return_start_at_ms, talkEnd);
    if (!(effectiveAt <= talkStart && talkStart <= talkEnd && talkEnd <= returnStart)) {
      throw new TypeError(`${actor.employee_id}: talk session timing is not monotonic`);
    }
    const routeInfo = command.route_info || null;
    let outbound = null;
    let inbound = null;
    let gate = null;
    let endpoint = null;
    let outboundDuration = 0;
    let returnDuration = 0;
    if (routeInfo) {
      if (!isObject(routeInfo)) throw new TypeError("start_talk_session.route_info must be an object");
      outbound = this.talkPath(routeInfo.outbound_path_cells_uv, "route_info.outbound_path_cells_uv");
      inbound = this.talkPath(routeInfo.inbound_path_cells_uv, "route_info.inbound_path_cells_uv");
      gate = routeInfo.gate_uv;
      endpoint = command.endpoint_uv;
      if (!Array.isArray(gate) || gate.length !== 2 || !Array.isArray(endpoint) || endpoint.length !== 2) {
        throw new TypeError(`${actor.employee_id}: talk route endpoints are invalid`);
      }
      if (outbound[0][0] !== gate[0] || outbound[0][1] !== gate[1] || outbound.at(-1)[0] !== endpoint[0] || outbound.at(-1)[1] !== endpoint[1]) {
        throw new TypeError(`${actor.employee_id}: talk outbound path endpoints are invalid`);
      }
      if (inbound[0][0] !== endpoint[0] || inbound[0][1] !== endpoint[1] || inbound.at(-1)[0] !== gate[0] || inbound.at(-1)[1] !== gate[1]) {
        throw new TypeError(`${actor.employee_id}: talk inbound path endpoints are invalid`);
      }
      outboundDuration = integer(routeInfo.arrival_ms, this.navigation.routeDurationMs(outbound, this.movementProfile(employee).speed_multiplier));
      returnDuration = integer(routeInfo.return_ms, 0) - integer(routeInfo.return_start_ms, talkEnd);
      if (returnDuration <= 0) returnDuration = this.navigation.routeDurationMs(inbound, this.movementProfile(employee).speed_multiplier);
      if (talkStart < effectiveAt + outboundDuration) throw new TypeError(`${actor.employee_id}: talk starts before route arrival`);
    }
    const routeCommitted = Boolean(outbound);
    if (command.route_committed !== undefined && Boolean(command.route_committed) !== routeCommitted) {
      throw new TypeError(`${actor.employee_id}: talk route marker does not match route_info`);
    }
    const recoveryOwner = command.recovery_owner === undefined ? role === "initiator" : Boolean(command.recovery_owner);
    if (actor.activity === "working" && recoveryOwner) {
      actor.behavior.event_counter = integer(actor.behavior.event_counter, 0) + 1;
      actor.behavior.active_event = "talk";
      actor.behavior.cooldowns = actor.behavior.cooldowns || {};
      actor.behavior.cooldowns.talk = Number(timestampMs) + this.nextIntervalMs(employee, {
        counter: actor.behavior.event_counter,
        nowMs: Number(timestampMs),
        event: "talk",
      });
    }
    actor.presence = "present";
    actor.activity = "talking";
    actor.behavior.next_event_due_ms = null;
    actor.behavior.activity_started_ms = effectiveAt;
    actor.behavior.activity_until_ms = returnStart + returnDuration;
    actor.behavior.talk = {
      session_id: sessionId,
      mode,
      role,
      partner_id: command.partner_id ?? null,
      recovery_owner: recoveryOwner,
      route_committed: routeCommitted,
      effective_at_ms: effectiveAt,
      talk_start_at_ms: talkStart,
      talk_end_at_ms: talkEnd,
      return_start_at_ms: returnStart,
      emotion: command.emotion ?? null,
      emotion_until_at_ms: command.emotion_until_at_ms ?? null,
      endpoint_uv: endpoint ? [...endpoint] : null,
      endpoint_facing: command.endpoint_facing || null,
      gate_uv: gate ? [...gate] : null,
      outbound_path_cells_uv: outbound ? outbound.map((cell) => [...cell]) : [],
      inbound_path_cells_uv: inbound ? inbound.map((cell) => [...cell]) : [],
      outbound_duration_ms: outboundDuration,
      return_duration_ms: returnDuration,
    };
    if (!routeCommitted) {
      actor.activity = "working";
      actor.conversation_phase = null;
      actor.behavior.activity_until_ms = null;
      actor.position.route = null;
    } else {
      actor.conversation_phase = "walking_to_talk";
      this.startRoute(actor, employee, {
        phase: "talk_outbound",
        startUv: gate,
        targetUv: endpoint,
        path: outbound,
        durationMs: outboundDuration,
        updateWindow: false,
      });
      this.beginSeatExit(actor, employee);
    }
    this.appendEvent(context, events, actor, effectiveAt, "talk_session_accepted", {
      session_id: sessionId,
      mode,
      role,
      partner_id: command.partner_id ?? null,
      route_committed: routeCommitted,
      talk_start_at_ms: talkStart,
      talk_end_at_ms: talkEnd,
      return_start_at_ms: returnStart,
    });
    const elapsedSinceAccept = Math.max(0, Number(timestampMs) - effectiveAt);
    if (routeCommitted && elapsedSinceAccept > 0) {
      const route = actor.position.route;
      if (route) {
        route.elapsed_ms = Math.min(route.duration_ms, elapsedSinceAccept);
        const pose = this.navigation.pathPose(route.path_cells_uv, route.elapsed_ms, this.movementProfile(employee).speed_multiplier);
        actor.position.floor_id = actor.assignment.floor_id;
        actor.position.ground_xy = [...pose.ground_xy];
        actor.position.uv = pose.current_uv ? [...pose.current_uv] : null;
        route.direction = pose.direction;
        route.raw_direction = pose.raw_direction;
        const transition = actor.position.seat_transition;
        if (transition?.phase === "seat_exit") {
          transition.elapsed_ms = Math.min(transition.duration_ms, elapsedSinceAccept);
          transition.to_ground_xy = pose.ground_xy.map(round4);
          actor.position.ground_xy = [...pose.ground_xy];
          if (transition.elapsed_ms >= transition.duration_ms) delete actor.position.seat_transition;
        }
        if (route.elapsed_ms >= route.duration_ms) this.finishRoute(context, actor, employee, Number(timestampMs), events);
      }
    }
  }

  beginTalkReturn(context, actor, employee, timestampMs, events) {
    const talk = actor.behavior.talk;
    if (!isObject(talk)) throw new TypeError(`${actor.employee_id}: talk return metadata is missing`);
    const inbound = this.talkPath(talk.inbound_path_cells_uv, "talk.inbound_path_cells_uv");
    const endpoint = talk.endpoint_uv;
    const gate = talk.gate_uv;
    const duration = Math.max(TICK_MS, integer(talk.return_duration_ms, this.navigation.routeDurationMs(inbound, this.movementProfile(employee).speed_multiplier)));
    actor.conversation_phase = "returning_to_work";
    actor.behavior.activity_started_ms = Number(timestampMs);
    actor.behavior.activity_until_ms = Number(timestampMs) + duration;
    this.startRoute(actor, employee, {
      phase: "talk_return",
      startUv: endpoint,
      targetUv: gate,
      path: inbound,
      durationMs: duration,
      updateWindow: false,
    });
    this.appendEvent(context, events, actor, timestampMs, "talk_return_started", {
      session_id: talk.session_id,
      mode: talk.mode,
      partner_id: talk.partner_id,
      return_duration_ms: duration,
    });
  }

  finishTalkActor(context, actor, employee, timestampMs, events) {
    const talk = actor.behavior.talk;
    if (!isObject(talk)) throw new TypeError(`${actor.employee_id}: talk completion metadata is missing`);
    actor.position = { floor_id: actor.assignment.floor_id, uv: null, ground_xy: null, route: null };
    actor.presence = "present";
    actor.conversation_phase = null;
    this.appendEvent(context, events, actor, timestampMs, "talk_returned", {
      session_id: talk.session_id,
      mode: talk.mode,
      partner_id: talk.partner_id,
      gate_uv: talk.gate_uv ? [...talk.gate_uv] : null,
      assignment_retained: true,
      route_committed: Boolean(talk.route_committed),
    });
    const recoveryOwner = Boolean(talk.recovery_owner);
    actor.behavior.talk = null;
    if (recoveryOwner && actor.behavior.active_event === "talk") {
      this.completeEvent(context, actor, employee, timestampMs, events);
      return;
    }
    actor.activity = "working";
    actor.behavior.active_event = null;
    actor.behavior.activity_started_ms = Number(timestampMs);
    actor.behavior.activity_until_ms = null;
    actor.behavior.next_event_due_ms = this.scheduleNextEvent(actor, employee, Number(timestampMs));
  }

  completeEvent(context, actor, employee, timestampMs, events) {
    const event = actor.behavior.active_event;
    if (!WEIGHTED_EVENTS.includes(event)) throw new TypeError(`${actor.employee_id}: missing active recovery event`);
    const channel = this.visualChannelForEvent(event);
    if (channel) {
      const visualChannels = this.ensureVisualChannels(actor);
      const active = visualChannels[channel].active_binding;
      if (active) {
        visualChannels[channel] = this.visualSelection.clearActive(
          visualChannels[channel],
          { channel, eventId: active.event_id },
        );
      }
    }
    const policy = this.staminaPolicy(employee).recovery_events?.[event] || {};
    const range = policy.recovery_amount_range || [0, 0];
    const counter = integer(actor.behavior.event_counter, 0);
    const ticket = stableHash64(
      employee.employee_id,
      this.staminaProfile(employee).profile_seed,
      "recovery",
      event,
      counter,
    );
    const amount = (Number(range[0]) + Number(ticket % BigInt(Number(range[1]) - Number(range[0]) + 1))) * 1000;
    const before = integer(actor.stamina.current_milli, 0);
    actor.stamina.current_milli = Math.min(MAX_STAMINA_MILLI, before + amount);
    actor.stamina.threshold_band = thresholdBand(actor.stamina.current_milli);
    actor.last_event = EVENT_LAST_EVENT[event];
    actor.activity = "working";
    actor.presence = "present";
    actor.conversation_phase = null;
    actor.behavior.active_event = null;
    const preserveDeskLoop = ["talk", "popup", "background_effect"].includes(event) && actor.position.route === null;
    if (!preserveDeskLoop) {
      actor.behavior.work_loop_elapsed_ms = 0;
      actor.behavior.work_loop_count = 0;
    }
    actor.behavior.activity_started_ms = Number(timestampMs);
    actor.behavior.activity_until_ms = null;
    actor.behavior.next_event_due_ms = this.scheduleNextEvent(actor, employee, Number(timestampMs));
    this.appendEvent(context, events, actor, timestampMs, "stamina_recovery", {
      behavior: event,
      recovery_milli: amount,
      stamina_before_milli: before,
      stamina_after_milli: actor.stamina.current_milli,
      presentation_ended: true,
    });
  }

  applyEmotionEffect(context, actor, employee, emotion, timestampMs, events, sourceSessionId = null) {
    if (!isObject(actor) || !isObject(employee)) {
      throw new TypeError("emotion effect requires an actor and employee");
    }
    if (emotion !== "sad" && emotion !== "happy") {
      throw new TypeError(`Unknown emotion stamina effect: ${emotion}`);
    }
    const delta = emotion === "happy" ? 2000 : -1000;
    const stamina = actor.stamina;
    const before = integer(stamina.current_milli, 0);
    const after = Math.max(0, Math.min(MAX_STAMINA_MILLI, before + delta));
    stamina.current_milli = after;
    stamina.threshold_band = thresholdBand(after);
    actor.last_event = `emotion_${emotion}_${delta > 0 ? "bonus" : "penalty"}`;
    const payload = {
      emotion,
      effect_milli: delta,
      effect_display: delta / 1000,
      stamina_before_milli: before,
      stamina_after_milli: after,
      source: "speech_scheduler",
    };
    if (sourceSessionId !== null && sourceSessionId !== undefined) {
      payload.session_id = String(sourceSessionId);
    }
    this.appendEvent(context, events, actor, timestampMs, "stamina_emotion_effect", payload);

    const rank = { normal: 2, low: 1, critical: 0 };
    const previousBand = thresholdBand(before);
    const currentBand = thresholdBand(after);
    if (rank[currentBand] < rank[previousBand]) {
      for (const [band, threshold] of [["low", 30000], ["critical", 10000]]) {
        if (rank[previousBand] > rank[band] && rank[band] >= rank[currentBand]) {
          this.appendEvent(context, events, actor, timestampMs, "threshold_crossed", {
            threshold_band: band,
            stamina_milli: threshold,
            source: "emotion_effect",
          });
        }
      }
    }
    if (
      currentBand === "critical"
      && actor.activity === "working"
      && !actor.behavior.pending_home
    ) {
      const queueTimestamp = Math.max(
        Number(timestampMs),
        Number(context.snapshot.clock?.simulation_time_ms || 0),
      );
      const loopElapsed = integer(actor.behavior.work_loop_elapsed_ms, 0);
      const offset = WORK_LOOP_MS - loopElapsed;
      const due = queueTimestamp + (offset === WORK_LOOP_MS ? 0 : offset);
      actor.behavior.pending_home = true;
      actor.behavior.pending_home_due_ms = due;
      this.appendEvent(context, events, actor, queueTimestamp, "home_queued", {
        reason: "stamina_critical",
        stamina_milli: after,
        finish_work_loop_at_ms: due,
        work_loop_ms: WORK_LOOP_MS,
      });
    }
  }

  drainWork(actor, employee, elapsedMs) {
    if (elapsedMs <= 0) return;
    const profile = this.staminaProfile(employee);
    const stamina = actor.stamina;
    const numerator = Number(profile.work_drain_milli_per_second) * Number(elapsedMs)
      + Number(stamina.drain_remainder || 0);
    const drain = Math.floor(numerator / 1000);
    stamina.current_milli = Math.max(0, Number(stamina.current_milli) - drain);
    stamina.drain_remainder = numerator % 1000;
    const behavior = actor.behavior;
    this.advanceWorkLoop(actor, elapsedMs);
    stamina.threshold_band = thresholdBand(stamina.current_milli);
    actor.last_event = "work_tick";
  }

  requestHome(context, actor, employee, timestampMs, events, {
    reason = "explicit",
    workLoopCompleted = false,
  } = {}) {
    if (actor.presence !== "present" || actor.activity === "talking") {
      throw new TypeError(`${actor.employee_id}: actor cannot begin home route in current state`);
    }
    if (actor.behavior.active_event !== null) {
      throw new TypeError(`${actor.employee_id}: active recovery event must finish before home`);
    }
    const floorId = actor.assignment.floor_id;
    const gate = this.workSeat.navigationAccess(actor.assignment.workstation_id).transition_gate_uv;
    const { inside } = this.navigation.portalPair(floorId);
    const path = this.navigation.findPath(gate, inside).path_cells_uv;
    actor.presence = "leaving";
    actor.activity = "going_home";
    actor.conversation_phase = null;
    actor.behavior.next_event_due_ms = null;
    actor.behavior.active_event = null;
    actor.behavior.pending_home = false;
    actor.behavior.pending_home_due_ms = null;
    actor.behavior.work_loop_elapsed_ms = 0;
    actor.behavior.work_loop_count = 0;
    actor.behavior.activity_started_ms = Number(timestampMs);
    actor.behavior.activity_until_ms = null;
    actor.last_event = reason === "stamina_critical" ? "critical_home_requested" : "home_requested";
    this.startRoute(actor, employee, {
      phase: "to_portal",
      startUv: gate,
      targetUv: inside,
      path,
    });
    this.beginSeatExit(actor, employee);
    const payload = { assignment_retained: true };
    if (reason !== "explicit" || workLoopCompleted) {
      payload.reason = reason;
      payload.work_loop_completed = Boolean(workLoopCompleted);
    }
    this.appendEvent(context, events, actor, timestampMs, "home_requested", payload);
  }

  requestReturn(context, actor, employee, timestampMs, events) {
    if (actor.presence !== "home" || actor.activity !== "home_recovery") {
      throw new TypeError(`${actor.employee_id}: actor cannot return in current state`);
    }
    if (Number(actor.behavior.activity_until_ms) > Number(timestampMs)) {
      throw new TypeError(`${actor.employee_id}: home recovery is not ready`);
    }
    const { inside, outside } = this.navigation.portalPair(actor.assignment.floor_id);
    actor.presence = "entering";
    actor.activity = "returning_to_work";
    actor.conversation_phase = null;
    actor.behavior.next_event_due_ms = null;
    actor.behavior.active_event = null;
    actor.behavior.activity_started_ms = Number(timestampMs);
    actor.behavior.activity_until_ms = null;
    actor.last_event = "return_requested";
    this.startRoute(actor, employee, {
      phase: "portal_entry",
      startUv: outside,
      targetUv: inside,
      path: [outside, inside],
      durationMs: PORTAL_FADE_STEPS * TICK_MS,
    });
    this.appendEvent(context, events, actor, timestampMs, "return_requested", {
      assignment_retained: true,
    });
  }

  applyCommand(context, actor, employee, command, timestampMs, events) {
    if (!isObject(command)) throw new TypeError("actor commands must contain objects");
    if (command.employee_id !== actor.employee_id) return;
    if (command.type === "start_talk_session") {
      this.startTalkSession(context, actor, employee, command, timestampMs, events);
      return;
    }
    if (command.type === "request_home") {
      this.requestHome(context, actor, employee, timestampMs, events);
      return;
    }
    if (command.type === "request_return") {
      this.requestReturn(context, actor, employee, timestampMs, events);
      return;
    }
    throw new TypeError(`Unknown actor command: ${command.type}`);
  }

  advanceActor(context, actor, employee, startMs, targetMs, events) {
    let nowMs = Number(startMs);
    while (nowMs < targetMs) {
      if (actor.position.seat_transition?.phase === "seat_entry") {
        const advanced = this.advanceSeatTransition(context, actor, employee, nowMs, targetMs, events);
        if (advanced <= nowMs) break;
        nowMs = advanced;
        continue;
      }
      const route = actor.position.route;
      const routeActive = isObject(route) && (
        ROUTE_ACTIVITIES.has(actor.activity)
        || (actor.activity === "talking" && ["talk_outbound", "talk_hold", "talk_return"].includes(route.phase))
      );
      if (routeActive) {
        const advanced = this.advanceRoute(context, actor, employee, nowMs, targetMs, events);
        if (advanced <= nowMs) break;
        nowMs = advanced;
        continue;
      }
      if (actor.activity === "working") {
        const behavior = actor.behavior;
        const talk = behavior.talk;
        const stationaryTalk = isObject(talk) && !Boolean(
          talk.route_committed ?? Boolean(talk.outbound_path_cells_uv?.length),
        );
        if (stationaryTalk) {
          const overlayEnd = integer(talk.return_start_at_ms, nowMs);
          if (overlayEnd > nowMs) {
            const stepTarget = Math.min(targetMs, overlayEnd);
            this.drainWork(actor, employee, stepTarget - nowMs);
            nowMs = stepTarget;
            if (nowMs < overlayEnd) break;
          }
          this.finishTalkActor(context, actor, employee, nowMs, events);
          continue;
        }
        if (actor.stamina.threshold_band === "critical" && !behavior.pending_home) {
          const loopElapsed = integer(behavior.work_loop_elapsed_ms, 0);
          const offset = WORK_LOOP_MS - loopElapsed;
          behavior.pending_home = true;
          behavior.pending_home_due_ms = nowMs + (offset === WORK_LOOP_MS ? 0 : offset);
          this.appendEvent(context, events, actor, nowMs, "home_queued", {
            reason: "stamina_critical",
            stamina_milli: actor.stamina.current_milli,
            finish_work_loop_at_ms: behavior.pending_home_due_ms,
            work_loop_ms: WORK_LOOP_MS,
          });
        }
        if (behavior.pending_home) {
          const due = integer(behavior.pending_home_due_ms, nowMs);
          if (due <= nowMs) {
            this.requestHome(context, actor, employee, nowMs, events, {
              reason: "stamina_critical",
              workLoopCompleted: true,
            });
            continue;
          }
          const stepTarget = Math.min(targetMs, due);
          this.advanceWorkLoop(actor, stepTarget - nowMs);
          nowMs = stepTarget;
          if (nowMs >= due) {
            this.requestHome(context, actor, employee, nowMs, events, {
              reason: "stamina_critical",
              workLoopCompleted: true,
            });
            continue;
          }
          break;
        }
        let due = behavior.next_event_due_ms;
        if (due === null || due === undefined) {
          due = this.scheduleNextEvent(actor, employee, nowMs);
          behavior.next_event_due_ms = due;
        }
        const stepTarget = Math.min(targetMs, Number(due));
        this.drainWork(actor, employee, stepTarget - nowMs);
        nowMs = stepTarget;
        if (nowMs >= targetMs) continue;
        let event;
        try {
          event = this.chooseBehaviorEvent(actor, employee, nowMs);
        } catch (error) {
          if (!(error instanceof TypeError) || error.message !== "No eligible weighted recovery event") throw error;
          const futureCooldowns = Object.values(behavior.cooldowns || {})
            .map((value) => Number(value))
            .filter((value) => value > nowMs);
          if (futureCooldowns.length === 0) throw error;
          behavior.next_event_due_ms = Math.min(...futureCooldowns);
          continue;
        }
        this.startEvent(context, actor, employee, event, nowMs, events);
        continue;
      }
      if (actor.activity === "popup_event") {
        const until = actor.behavior.activity_until_ms;
        if (until === null || until === undefined) break;
        if (Number(until) > targetMs) {
          this.advanceWorkLoop(actor, targetMs - nowMs);
          nowMs = targetMs;
          break;
        }
        this.advanceWorkLoop(actor, Number(until) - nowMs);
        nowMs = Number(until);
        this.completeEvent(context, actor, employee, nowMs, events);
        continue;
      }
      break;
    }
  }

  step(actor, context, elapsedMs, commands = []) {
    if (!isObject(actor)) throw new TypeError("actor must be an object");
    if (!Number.isInteger(elapsedMs) || elapsedMs < 0) throw new TypeError("elapsedMs must be a non-negative integer");
    const employee = this.employeeFor(actor);
    this.ensureVisualChannels(actor);
    const events = [];
    const nowMs = Number(context.nowMs);
    const targetMs = nowMs + elapsedMs;
    for (const command of [...commands].sort((left, right) => String(left.employee_id).localeCompare(String(right.employee_id)))) {
      this.applyCommand(context, actor, employee, command, nowMs, events);
    }
    this.advanceActor(context, actor, employee, nowMs, targetMs, events);
    return { actor, events };
  }
}

export { TICK_MS, WORK_LOOP_MS, WORK_CHARACTER_FRAME_MS, thresholdBand };
