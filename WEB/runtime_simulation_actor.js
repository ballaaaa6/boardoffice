import { stableHash64 } from "./runtime_simulation_prng.js";

const TICK_MS = 60;
const WORK_LOOP_MS = 720;
const WORK_CHARACTER_FRAME_MS = 360;
const MAX_STAMINA_MILLI = 100000;
const LOW_THRESHOLD_MILLI = 30000;
const CRITICAL_THRESHOLD_MILLI = 10000;
const PORTAL_FADE_STEPS = 4;
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

function thresholdBand(current) {
  if (current <= CRITICAL_THRESHOLD_MILLI) return "critical";
  if (current <= LOW_THRESHOLD_MILLI) return "low";
  return "normal";
}

function quantizeMs(milliseconds) {
  return Math.max(TICK_MS, Math.round(Number(milliseconds) / TICK_MS) * TICK_MS);
}

export class BrowserActorReducer {
  constructor({ employees = {}, navigation, workSeat } = {}) {
    if (!navigation || !workSeat) throw new TypeError("BrowserActorReducer needs navigation and WorkSeat reducers");
    this.employees = employees;
    this.navigation = navigation;
    this.workSeat = workSeat;
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
          delete actor.position.seat_transition;
          if (completion === "to_workseat") this.finishSeatEntry(context, actor, employee, nowMs, events);
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
      actor.position.uv = transition.phase === "seat_entry"
        ? actor.position.uv
        : null;
      if (transition.elapsed_ms >= duration) {
        if (transition.phase === "seat_entry") {
          const completion = transition.completion;
          delete actor.position.seat_transition;
          if (completion === "to_workseat") this.finishSeatEntry(context, actor, employee, nowMs, events);
        } else delete actor.position.seat_transition;
      }
    }
    return nowMs;
  }

  finishRoute(context, actor, employee, timestampMs, events) {
    const route = actor.position.route;
    if (!isObject(route)) throw new TypeError(`${actor.employee_id}: route segment is missing`);
    const floorId = actor.assignment.floor_id;
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
        : this.navigation.pathPose(route.path_cells_uv, route.elapsed_ms, profile.speed_multiplier);
      actor.position.floor_id = actor.assignment.floor_id;
      actor.position.ground_xy = [...pose.ground_xy];
      actor.position.uv = pose.current_uv ? [...pose.current_uv] : null;
      route.direction = pose.direction;
      route.raw_direction = pose.raw_direction;
      route.visibility_alpha = pose.visibility_alpha ?? 1;
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
    const total = Number(behavior.work_loop_elapsed_ms || 0) + Number(elapsedMs);
    const completed = Math.floor(total / WORK_LOOP_MS);
    behavior.work_loop_elapsed_ms = total % WORK_LOOP_MS;
    behavior.work_loop_count = Number(behavior.work_loop_count || 0) + completed;
    stamina.threshold_band = thresholdBand(stamina.current_milli);
    actor.last_event = "work_tick";
  }

  requestHome(context, actor, employee, timestampMs, events) {
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
    actor.last_event = "home_requested";
    this.startRoute(actor, employee, {
      phase: "to_portal",
      startUv: gate,
      targetUv: inside,
      path,
    });
    this.beginSeatExit(actor, employee);
    this.appendEvent(context, events, actor, timestampMs, "home_requested", {
      assignment_retained: true,
    });
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
        || (actor.activity === "talking" && route.phase === "talk_outbound")
      );
      if (routeActive) {
        const advanced = this.advanceRoute(context, actor, employee, nowMs, targetMs, events);
        if (advanced <= nowMs) break;
        nowMs = advanced;
        continue;
      }
      if (actor.activity === "working") {
        this.drainWork(actor, employee, targetMs - nowMs);
        nowMs = targetMs;
        continue;
      }
      break;
    }
  }

  step(actor, context, elapsedMs, commands = []) {
    if (!isObject(actor)) throw new TypeError("actor must be an object");
    if (!Number.isInteger(elapsedMs) || elapsedMs < 0) throw new TypeError("elapsedMs must be a non-negative integer");
    const employee = this.employeeFor(actor);
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
