import {
  nextD6FromState,
  stableHash64,
} from "./runtime_simulation_prng.js";

const TICK_MS = 60;
const BUBBLE_VISIBLE_MS = 4000;
const BUBBLE_FADE_MS = 300;
const SESSION_HOLD_MS = 4300;
const EMOTION_HOLD_MS = 1200;
const PAIR_CATEGORIES = ["conversation_open", "conversation_reply"];

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function clone(value) {
  if (typeof globalThis.structuredClone === "function") return globalThis.structuredClone(value);
  return JSON.parse(JSON.stringify(value));
}

function integer(value, fallback = 0) {
  return Number.isFinite(Number(value)) ? Math.trunc(Number(value)) : fallback;
}

function localeKey(value) {
  return String(value || "en").trim().toLowerCase().split("-", 1)[0] || "en";
}

function floorOf(actor) {
  return actor?.assignment?.floor_id || actor?.floor_id || null;
}

function roleOf(actor) {
  return actor?.assignment?.workstation_id === "ceo" ? "ceo" : "employee";
}

function lineKey(line) {
  // SpeechSchedulerCore's dialogue bag keys are dialogue_id|line_index;
  // locale is already part of the bag namespace.
  return `${line?.dialogue_id}|${integer(line?.line_index)}`;
}

function bubbleKey(line) {
  return `${localeKey(line?.locale)}|${lineKey(line)}`;
}

function compactLine(line) {
  return line ? clone(line) : null;
}

export class BrowserSpeechReducer {
  constructor({
    employees = {},
    dialogue = {},
    conversation = {},
    navigation,
    workSeat,
    seed = "gds-browser-runtime-v1",
  } = {}) {
    if (!navigation || !workSeat) {
      throw new TypeError("BrowserSpeechReducer needs navigation and WorkSeat reducers");
    }
    this.employees = employees;
    this.dialogue = dialogue;
    this.conversation = conversation;
    this.navigation = navigation;
    this.workSeat = workSeat;
    this.seed = seed;
  }

  employee(employeeId) {
    const value = this.employees?.[employeeId];
    if (!isObject(value)) throw new TypeError(`Unknown employee: ${employeeId}`);
    return value;
  }

  appendEvent(snapshot, events, timestampMs, type, payload = {}) {
    const determinism = snapshot.determinism || (snapshot.determinism = {});
    const eventIndex = integer(determinism.root_event_counter, 0);
    determinism.root_event_counter = eventIndex + 1;
    const event = {
      event_index: eventIndex,
      timestamp_ms: integer(timestampMs),
      type,
      ...clone(payload),
    };
    events.push(event);
    return event;
  }

  syncActorState(snapshot, actorSnapshot, nowMs) {
    if (!isObject(actorSnapshot?.actors)) return;
    for (const [employeeId, speechActor] of Object.entries(snapshot.actors || {})) {
      const actor = actorSnapshot.actors[employeeId];
      if (!isObject(actor)) continue;
      speechActor.last_activity = String(actor.activity || speechActor.last_activity || "working");
      speechActor.stamina_band = String(
        actor.stamina?.threshold_band || speechActor.stamina_band || "normal",
      );
      const presence = String(actor.presence || "present");
      if (presence === "home") {
        speechActor.speech_phase = speechActor.speech_phase === "emotion"
          ? speechActor.speech_phase
          : "idle";
        speechActor.external_talk_pending = false;
        speechActor.external_talk_due_ms = null;
      }
      if (actor.activity === "going_home" || presence === "leaving") {
        if (actor.last_event === "home_requested") {
          speechActor.fatigue_pending = true;
          speechActor.fatigue_emitted = false;
        } else {
          speechActor.fatigue_pending = false;
          speechActor.fatigue_emitted = true;
        }
        speechActor.leaving_emitted = false;
        speechActor.leaving_due_ms = null;
      }
      if (
        actor.activity === "working"
        && speechActor.last_activity !== "working"
        && speechActor.speech_phase === "idle"
        && speechActor.work_start_due_ms === null
      ) {
        speechActor.work_start_due_ms = integer(nowMs);
        speechActor.work_start_emitted = false;
      }
    }
  }

  applyCommand(snapshot, command, timestampMs) {
    if (!isObject(command)) throw new TypeError("speech commands must contain objects");
    const employeeId = command.employee_id;
    const actor = snapshot.actors?.[employeeId];
    if (!isObject(actor)) throw new TypeError("speech command.employee_id must name an active actor");
    const type = command.type;
    if (type === "behavior_started") {
      if (command.behavior !== "talk") {
        throw new TypeError("behavior_started speech bridge only accepts behavior=talk");
      }
      actor.external_talk_pending = true;
      actor.external_talk_due_ms = integer(command.effective_at_ms, timestampMs);
      return;
    }
    if (type === "cancel_talk") {
      actor.external_talk_pending = false;
      actor.external_talk_due_ms = null;
      actor.pair_pending = false;
      actor.pair_next_due_ms = timestampMs + this.delayMs(snapshot, employeeId, "retry", integer(actor.departure_token, 0) + 1);
      return;
    }
    if (type === "spawned") {
      const effectiveAt = integer(command.effective_at_ms, timestampMs);
      actor.spawned_at_ms = effectiveAt;
      actor.greeting_due_ms = effectiveAt + this.delayMs(snapshot, employeeId, "greeting", integer(actor.departure_token, 0) + 1);
      actor.greeting_emitted = false;
      return;
    }
    if (type === "workseat_entered") {
      actor.work_start_due_ms = integer(command.effective_at_ms, timestampMs);
      actor.work_start_emitted = false;
      return;
    }
    if (type === "going_home") {
      actor.fatigue_pending = true;
      actor.fatigue_emitted = false;
      actor.leaving_emitted = false;
      actor.leaving_due_ms = null;
      actor.departure_token = integer(actor.departure_token, 0) + 1;
      return;
    }
    if (type === "returned_to_work") {
      const effectiveAt = integer(command.effective_at_ms, timestampMs);
      const token = integer(actor.departure_token, 0) + 1;
      actor.speech_phase = "idle";
      actor.emotion = null;
      actor.emotion_until_ms = null;
      actor.greeting_due_ms = effectiveAt + this.delayMs(snapshot, employeeId, "greeting", token);
      actor.greeting_emitted = false;
      actor.work_start_due_ms = effectiveAt;
      actor.work_start_emitted = false;
      actor.solo_next_due_ms = effectiveAt + this.delayMs(snapshot, employeeId, "solo", token);
      actor.pair_next_due_ms = actor.role === "ceo"
        ? null
        : effectiveAt + this.delayMs(snapshot, employeeId, "pair", token);
      actor.solo_pending = false;
      actor.pair_pending = false;
      actor.leaving_pending = false;
      actor.leaving_due_ms = null;
      return;
    }
    if (type === "reception_depth_crossed") {
      if (!command.draws_over_reception && !command.render_over_reception) {
        throw new TypeError("reception_depth_crossed requires draws_over_reception=true");
      }
      actor.leaving_pending = true;
      actor.leaving_emitted = false;
      actor.leaving_due_ms = integer(command.effective_at_ms, timestampMs);
      return;
    }
    throw new TypeError(`Unknown speech command type: ${type}`);
  }

  delayMs(snapshot, employeeId, kind, counter) {
    const ranges = {
      greeting: [2, 3],
      solo: [30, 60],
      pair: [45, 75],
      retry: [15, 30],
    };
    const [lower, upper] = ranges[kind] || ranges.solo;
    const ticket = stableHash64(
      snapshot.determinism?.simulation_seed || this.seed,
      employeeId,
      kind,
      Number(counter),
    );
    const seconds = lower + Number(ticket % BigInt(upper - lower + 1));
    return Math.max(TICK_MS, Math.ceil((seconds * 1000) / TICK_MS) * TICK_MS);
  }

  actorAvailable(speechActor, actor, conversationActor, allowNonWorking = false) {
    if (!isObject(actor) || !isObject(speechActor)) return false;
    if (!["present", "entering"].includes(String(actor.presence || "present"))) return false;
    if (!allowNonWorking && String(actor.activity || "working") !== "working") return false;
    if (conversationActor?.locked) return false;
    if (speechActor.stamina_band === "critical") return false;
    return speechActor.speech_phase === "idle";
  }

  partnerIds(snapshot, actorSnapshot, conversationSnapshot, initiatorId) {
    const initiator = actorSnapshot.actors[initiatorId];
    const floor = floorOf(initiator);
    return Object.keys(snapshot.actors || {})
      .filter((employeeId) => employeeId !== initiatorId)
      .filter((employeeId) => {
        const actor = actorSnapshot.actors[employeeId];
        const speechActor = snapshot.actors[employeeId];
        const convActor = conversationSnapshot?.actors?.[employeeId];
        return floorOf(actor) === floor
          && roleOf(actor) === "employee"
          && this.actorAvailable(speechActor, actor, convActor);
      })
      .sort((left, right) => (
        integer(actorSnapshot.actors[left]?.assignment?.assignment_order, 0)
        - integer(actorSnapshot.actors[right]?.assignment?.assignment_order, 0)
        || left.localeCompare(right)
      ));
  }

  modeRequests(snapshot, actorSnapshot, conversationSnapshot, initiatorId) {
    const initiator = actorSnapshot.actors[initiatorId];
    const speechActor = snapshot.actors[initiatorId];
    const conversationActor = conversationSnapshot?.actors?.[initiatorId];
    const external = Boolean(speechActor?.external_talk_pending);
    if (!this.actorAvailable(speechActor, initiator, conversationActor, external)) return [];
    if (roleOf(initiator) === "ceo") return [];
    const ceos = Object.keys(snapshot.actors || {}).filter((employeeId) => {
      const actor = actorSnapshot.actors[employeeId];
      return floorOf(actor) === floorOf(initiator)
        && roleOf(actor) === "ceo"
        && this.actorAvailable(
          snapshot.actors[employeeId],
          actor,
          conversationSnapshot?.actors?.[employeeId],
        );
    });
    const employees = this.partnerIds(snapshot, actorSnapshot, conversationSnapshot, initiatorId);
    const groups = [];
    if (ceos.length) groups.push(["ceo_front", ceos]);
    if (employees.length) {
      groups.push(["seated_host", employees]);
      groups.push(["standing_pair", employees]);
    }
    if (!groups.length) return [];
    const counter = integer(speechActor.speech_event_counter, 0) + 1;
    const seed = snapshot.determinism?.simulation_seed || this.seed;
    const selected = Number(stableHash64(seed, initiatorId, "mode", counter) % BigInt(groups.length));
    const rotated = groups.slice(selected).concat(groups.slice(0, selected));
    const availableModes = groups.map(([mode]) => mode);
    const result = [];
    for (const [mode, partners] of rotated) {
      const ordered = [...partners].sort((left, right) => (
        stableHash64(seed, initiatorId, mode, counter, left) < stableHash64(seed, initiatorId, mode, counter, right)
          ? -1
          : stableHash64(seed, initiatorId, mode, counter, left) > stableHash64(seed, initiatorId, mode, counter, right)
            ? 1
            : left.localeCompare(right)
      ));
      for (const partnerId of ordered) {
        result.push({
          kind: "pair",
          category: "conversation_open",
          mode,
          initiator_id: initiatorId,
          partner_id: partnerId,
          participants: [initiatorId, partnerId],
          dialogue_categories: [...PAIR_CATEGORIES],
          available_modes: [...availableModes],
          external,
        });
      }
    }
    return result;
  }

  dialogueFromBag(snapshot, category, locale, seed) {
    const normalizedLocale = localeKey(locale);
    const pool = (this.dialogue.lines || []).filter((line) => (
      isObject(line)
      && line.enabled !== false
      && localeKey(line.locale) === normalizedLocale
      && String(line.category || "") === String(category)
    ));
    if (!pool.length) return { line: null, state: snapshot.dialogue_bags || {} };
    const byKey = new Map(pool.map((line) => [lineKey(line), line]));
    const bagKey = `${normalizedLocale}|${category}`;
    const bags = snapshot.dialogue_bags || (snapshot.dialogue_bags = {});
    const source = bags[bagKey] || {};
    let generation = integer(source.generation, 0);
    let usedCount = integer(source.used_count, 0);
    let remaining = Array.isArray(source.remaining)
      ? source.remaining.filter((key) => byKey.has(key))
      : [];
    const recent = Array.isArray(source.recent_texts) ? source.recent_texts.map(String) : [];
    if (!remaining.length) {
      generation += 1;
      remaining = [...byKey.keys()].sort((left, right) => {
        const leftHash = stableHash64(seed, "dialogue-bag", normalizedLocale, category, generation, left);
        const rightHash = stableHash64(seed, "dialogue-bag", normalizedLocale, category, generation, right);
        return leftHash < rightHash ? -1 : leftHash > rightHash ? 1 : left.localeCompare(right);
      });
    }
    const chosenKey = remaining.find((key) => !recent.includes(String(byKey.get(key)?.text || ""))) || remaining[0];
    remaining = remaining.filter((key) => key !== chosenKey);
    const line = byKey.get(chosenKey);
    usedCount += 1;
    bags[bagKey] = {
      locale: normalizedLocale,
      category: String(category),
      generation,
      used_count: usedCount,
      remaining,
      recent_texts: [...recent, String(line?.text || "")].slice(-4),
    };
    return { line: compactLine(line), state: bags };
  }

  bubbleId(line) {
    if (!line) return null;
    const key = bubbleKey(line);
    return this.dialogue.bubble_by_line?.[key] || "BB1";
  }

  buildRouteInfo(actorSnapshot, plan) {
    const result = {};
    const endpoints = plan.endpoint_by_actor || {};
    for (const employeeId of Object.keys(endpoints)) {
      const actor = actorSnapshot.actors[employeeId];
      if (!actor) continue;
      const gate = this.workSeat.navigationAccess(actor.assignment.workstation_id).transition_gate_uv;
      const endpoint = endpoints[employeeId];
      const outbound = this.navigation.findPath(gate, endpoint).path_cells_uv;
      const inbound = this.navigation.findPath(endpoint, gate).path_cells_uv;
      const speed = Number(this.employees[employeeId]?.movement_profile?.speed_multiplier || 1);
      // Central's authored talk route includes the one 60ms WorkSeat exit
      // boundary before the outbound movement clock becomes visible.
      const arrival = this.navigation.routeDurationMs(outbound, speed) + TICK_MS;
      const returnDuration = this.navigation.routeDurationMs(inbound, speed);
      const returnStart = integer(plan.talk_end_ms, 0) + integer(plan.emotion_hold_ms, 0);
      result[employeeId] = {
        gate_uv: [...gate],
        endpoint_uv: [...endpoint],
        outbound_path_cells_uv: outbound.map((cell) => [...cell]),
        inbound_path_cells_uv: inbound.map((cell) => [...cell]),
        arrival_ms: arrival,
        return_start_ms: returnStart,
        return_ms: returnStart + returnDuration,
      };
    }
    return result;
  }

  buildPlan(snapshot, actorSnapshot, request, dialogueLocale, dialogueSeed) {
    const initiatorId = request.initiator_id;
    const mode = request.mode || (request.kind === "pair" ? "standing_pair" : "self_talk");
    const counter = integer(snapshot.determinism?.root_event_counter, 0);
    const selectedLines = {};
    if (request.kind === "pair") {
      for (let index = 0; index < request.participants.length; index += 1) {
        const employeeId = request.participants[index];
        const category = PAIR_CATEGORIES[index] || PAIR_CATEGORIES[0];
        const selected = this.dialogueFromBag(
          snapshot,
          category,
          dialogueLocale,
          `${dialogueSeed}|${counter}|${initiatorId}`,
        );
        if (selected.line) selectedLines[employeeId] = selected.line;
      }
    } else {
      const category = request.category || "idle_flavor";
      const selected = this.dialogueFromBag(
        snapshot,
        category,
        dialogueLocale,
        `${dialogueSeed}|${counter}|${initiatorId}`,
      );
      if (selected.line) selectedLines[initiatorId] = selected.line;
    }

    const catalog = request.kind === "pair"
      ? this.conversation.plans?.[`${initiatorId}|${request.partner_id}|${mode}`]
      : null;
    const plan = catalog ? clone(catalog) : {
      ready: true,
      schema: "gds.browser_conversation_plan.v1",
      mode: "self_talk",
      floor_id: floorOf(actorSnapshot.actors[initiatorId]),
      initiator_id: initiatorId,
      participants: [initiatorId],
      endpoint_by_actor: {},
      facing_by_actor: {},
      bubble_offset_by_actor: { [initiatorId]: [0, 0] },
      talk_duration_ms: SESSION_HOLD_MS,
      bubble_visible_ms: BUBBLE_VISIBLE_MS,
      bubble_fade_ms: BUBBLE_FADE_MS,
      speaker_gap_ms: 0,
      emotion_hold_ms: 0,
      pose_bindings: {
        [initiatorId]: {
          render_owner: "work_seat",
          action: "work",
          subaction: "normal_work",
          role: "seated_speaker",
        },
      },
    };
    if (request.kind === "pair" && !catalog) return null;
    plan.talk_start_ms = request.kind === "pair"
      ? Math.max(TICK_MS, ...Object.values(this.buildRouteInfo(actorSnapshot, plan)).map((info) => integer(info.arrival_ms, TICK_MS)))
      : 0;
    plan.talk_end_ms = plan.talk_start_ms + integer(plan.talk_duration_ms, SESSION_HOLD_MS);
    plan.talk_frames = Math.ceil((integer(plan.talk_duration_ms, SESSION_HOLD_MS) + BUBBLE_FADE_MS) / TICK_MS);
    plan.route_info = request.kind === "pair" ? this.buildRouteInfo(actorSnapshot, plan) : {};
    plan.dialogue_by_actor = selectedLines;
    plan.dialogue_selection = {
      policy: request.kind === "pair" ? "pair_open_reply_bags" : "in_work_category_bag",
      overrides: Object.fromEntries(
        Object.entries(selectedLines).map(([employeeId, line]) => [employeeId, {
          dialogue_id: line.dialogue_id,
          line_index: integer(line.line_index),
        }]),
      ),
    };
    plan.emotion = {
      outcome: null,
      roll: null,
      hold_ms: mode === "standing_pair" ? integer(plan.emotion_hold_ms, EMOTION_HOLD_MS) : 0,
      stamina_effect_hook: "actor_snapshot_numeric_delta",
      stamina_effect_milli_by_emotion: { sad: -1000, happy: 2000 },
      starts_after: "bubble_fade_end",
      return_after: true,
    };
    if (!isObject(plan.pose_bindings)) {
      plan.pose_bindings = Object.fromEntries(
        request.participants.map((employeeId) => [employeeId, {
          render_owner: "walking_depth",
          action: "idle",
          subaction: "idle",
          role: "standing_pair_participant",
        }]),
      );
    }
    return plan;
  }

  requestForActor(snapshot, actorSnapshot, conversationSnapshot, employeeId, nowMs) {
    const speechActor = snapshot.actors[employeeId];
    const actor = actorSnapshot.actors[employeeId];
    if (!speechActor || !actor || speechActor.speech_phase !== "idle") return null;
    if (speechActor.leaving_pending && !speechActor.leaving_emitted && (
      speechActor.leaving_due_ms === null || integer(speechActor.leaving_due_ms) <= nowMs
    )) {
      return { kind: "lifecycle", category: "leaving", mode: "self_talk", participants: [employeeId], initiator_id: employeeId };
    }
    if (speechActor.fatigue_pending && !speechActor.fatigue_emitted) {
      return { kind: "lifecycle", category: "fatigue", mode: "self_talk", participants: [employeeId], initiator_id: employeeId };
    }
    const available = this.actorAvailable(
      speechActor,
      actor,
      conversationSnapshot?.actors?.[employeeId],
    );
    if (available && !speechActor.greeting_emitted && speechActor.greeting_due_ms !== null && integer(speechActor.greeting_due_ms) <= nowMs) {
      return { kind: "lifecycle", category: "greeting", mode: "self_talk", participants: [employeeId], initiator_id: employeeId };
    }
    if (available && !speechActor.work_start_emitted && speechActor.work_start_due_ms !== null && integer(speechActor.work_start_due_ms) <= nowMs) {
      return { kind: "lifecycle", category: "work_start", mode: "self_talk", participants: [employeeId], initiator_id: employeeId };
    }
    if (speechActor.external_talk_pending && (
      speechActor.external_talk_due_ms === null || integer(speechActor.external_talk_due_ms) <= nowMs
    )) {
      if (roleOf(actor) === "ceo") {
        return { kind: "solo", category: "idle_flavor", mode: "self_talk", participants: [employeeId], initiator_id: employeeId, external: true };
      }
      const request = this.modeRequests(snapshot, actorSnapshot, conversationSnapshot, employeeId)[0];
      return request || { kind: "solo", category: "idle_flavor", mode: "self_talk", participants: [employeeId], initiator_id: employeeId, external: true };
    }
    if (!available) return null;
    if (roleOf(actor) !== "ceo" && (
      speechActor.pair_pending
      || (speechActor.pair_next_due_ms !== null && integer(speechActor.pair_next_due_ms) <= nowMs)
    )) {
      const request = this.modeRequests(snapshot, actorSnapshot, conversationSnapshot, employeeId)[0];
      if (request) return request;
      speechActor.pair_pending = true;
      speechActor.pair_next_due_ms = null;
    }
    if (speechActor.solo_pending || (speechActor.solo_next_due_ms !== null && integer(speechActor.solo_next_due_ms) <= nowMs)) {
      const categories = [
        "anticipation", "work_progress", "work_complete", "encouragement", "praise",
        "celebration", "disappointment", "fatigue", "surprise", "uncertainty", "idle_flavor",
      ];
      const category = categories[integer(speechActor.work_dialogue_cursor, 0) % categories.length];
      return { kind: "solo", category, mode: "self_talk", participants: [employeeId], initiator_id: employeeId };
    }
    return null;
  }

  queuedMetadata(snapshot, request, nowMs) {
    const employeeId = String(request.initiator_id);
    const actor = snapshot.actors[employeeId] || {};
    const category = String(request.category || request.kind || "solo");
    const dueKey = {
      greeting: "greeting_due_ms",
      work_start: "work_start_due_ms",
      pair: "pair_next_due_ms",
      conversation_open: "pair_next_due_ms",
      solo: "solo_next_due_ms",
      leaving: "leaving_due_ms",
      fatigue: "external_talk_due_ms",
    }[category];
    const due = dueKey && actor[dueKey] !== null && actor[dueKey] !== undefined
      ? integer(actor[dueKey])
      : integer(nowMs);
    const token = [
      integer(actor.departure_token, 0),
      integer(actor.speech_event_counter, 0),
      category,
      request.partner_id || "",
    ].join(":");
    return {
      request_id: `speech-request:${employeeId}:${token}`,
      initiator_id: employeeId,
      kind: String(request.kind || "solo"),
      category,
      mode: String(request.mode || "self_talk"),
      participants: [...(request.participants || [employeeId])],
      due_ms: due,
      external: Boolean(request.external),
    };
  }

  startSession(snapshot, actorSnapshot, request, plan, timestampMs, events, dialogueLocale) {
    const participants = [...request.participants];
    const kind = String(request.kind);
    const mode = String(request.mode || (kind === "pair" ? "standing_pair" : "self_talk"));
    const category = String(request.category || "idle_flavor");
    const sessionCounter = integer(snapshot.determinism.root_event_counter, 0);
    const floorId = snapshot.actors[participants[0]].floor_id;
    const sessionId = `speech:${floorId}:${kind}:${participants[0]}:${sessionCounter}`;
    const movementStartedMs = integer(timestampMs);
    const movementArrivalMs = movementStartedMs + (kind === "pair" ? integer(plan.talk_start_ms, 0) : 0);
    const bubbleStartMs = movementArrivalMs;
    const fadeEndMs = bubbleStartMs + SESSION_HOLD_MS;
    const session = {
      session_id: sessionId,
      floor_id: floorId,
      kind,
      mode,
      category,
      pair_categories: kind === "pair" ? [...PAIR_CATEGORIES] : [],
      participants,
      initiator_id: request.initiator_id || participants[0],
      partner_id: request.partner_id || null,
      available_modes: [...(request.available_modes || [])],
      selection_policy: "uniform_valid_mode_then_seeded_partner",
      start_ms: bubbleStartMs,
      movement_started_ms: movementStartedMs,
      movement_arrival_ms: movementArrivalMs,
      bubble_start_ms: bubbleStartMs,
      bubble_visible_end_ms: bubbleStartMs + BUBBLE_VISIBLE_MS,
      fade_start_ms: bubbleStartMs + BUBBLE_VISIBLE_MS,
      fade_end_ms: fadeEndMs,
      return_after_bubble: true,
      bubble_schedule: [],
      pose_bindings: clone(plan.pose_bindings || {}),
      conversation_plan: clone(plan),
      emotion_roll: null,
      emotion_outcome: null,
      emotion_hold_ms: 0,
      numeric_effect_policy: "none",
      stamina_effect_milli: 0,
      score_delta: 0,
      stamina_effect_hook: "none",
      stamina_effect_milli_by_emotion: { sad: -1000, happy: 2000 },
      bubble_selection_policy: "smallest_allowed_fit",
      bubble_started: false,
      bubble_start_event_emitted: false,
    };
    if (kind === "pair") {
      for (let index = 0; index < participants.length; index += 1) {
        const employeeId = participants[index];
        const line = plan.dialogue_by_actor?.[employeeId];
        const start = bubbleStartMs + (index === 1 ? 500 : 0);
        session.bubble_schedule.push({
          employee_id: employeeId,
          category: PAIR_CATEGORIES[index] || PAIR_CATEGORIES[0],
          start_ms: start,
          visible_end_ms: bubbleStartMs + BUBBLE_VISIBLE_MS,
          fade_end_ms: fadeEndMs,
          turn_index: index,
          preferred_bubble_id: this.bubbleId(line),
        });
      }
      if (mode === "standing_pair") {
        const next = nextD6FromState(snapshot.determinism.emotion_rng_state);
        // JSON cannot represent an exact uint64 as a JavaScript Number.
        // Keep the persisted SplitMix64 state decimal-encoded so save/load
        // and parity traces do not lose the low bits before the next roll.
        snapshot.determinism.emotion_rng_state = next.state.toString();
        const emotion = next.roll % 2 === 0 ? "happy" : "sad";
        session.emotion_roll = next.roll;
        session.emotion_outcome = emotion;
        session.emotion_hold_ms = EMOTION_HOLD_MS;
        session.conversation_plan.emotion = {
          ...(session.conversation_plan.emotion || {}),
          outcome: emotion,
          roll: next.roll,
          hold_ms: EMOTION_HOLD_MS,
        };
      }
    } else {
      const line = plan.dialogue_by_actor?.[participants[0]];
      session.bubble_schedule.push({
        employee_id: participants[0],
        category,
        start_ms: bubbleStartMs,
        visible_end_ms: bubbleStartMs + BUBBLE_VISIBLE_MS,
        fade_end_ms: fadeEndMs,
        turn_index: 0,
        preferred_bubble_id: this.bubbleId(line),
      });
    }
    snapshot.active_sessions[sessionId] = session;
    const lane = snapshot.lanes[floorId] || (snapshot.lanes[floorId] = {
      floor_id: floorId,
      active_session_id: null,
      active_until_ms: null,
      queued_session_ids: [],
      queued_requests: [],
      last_completed_session_id: null,
    });
    lane.active_session_id = sessionId;
    lane.active_until_ms = fadeEndMs;
    for (const employeeId of participants) {
      const speechActor = snapshot.actors[employeeId];
      speechActor.speech_event_counter = integer(speechActor.speech_event_counter, 0) + 1;
      speechActor.speech_phase = "active";
      speechActor.external_talk_pending = request.external ? false : speechActor.external_talk_pending;
      speechActor.external_talk_due_ms = request.external ? null : speechActor.external_talk_due_ms;
      speechActor.last_session_id = sessionId;
      speechActor.last_partner_id = request.partner_id || null;
      if (kind === "solo") {
        speechActor.work_dialogue_cursor = integer(speechActor.work_dialogue_cursor, 0) + 1;
        speechActor.work_dialogue_emitted = integer(speechActor.work_dialogue_emitted, 0) + 1;
      }
      if (category === "greeting") speechActor.greeting_emitted = true;
      if (category === "work_start") speechActor.work_start_emitted = true;
      if (category === "fatigue") {
        speechActor.fatigue_emitted = true;
        speechActor.fatigue_pending = false;
      }
      if (category === "leaving") {
        speechActor.leaving_emitted = true;
        speechActor.leaving_pending = false;
        speechActor.leaving_due_ms = null;
      }
      if (kind === "solo") {
        speechActor.solo_pending = false;
        speechActor.solo_next_due_ms = null;
      }
      if (kind === "pair") {
        speechActor.pair_pending = false;
        speechActor.pair_next_due_ms = null;
      }
    }
    this.appendEvent(snapshot, events, timestampMs, "speech_session_started", {
      employee_id: participants[0],
      session_id: sessionId,
      floor_id: floorId,
      kind,
      mode,
      category,
      participants,
      bubble_visible_end_ms: session.bubble_visible_end_ms,
      fade_end_ms: fadeEndMs,
      bubble_start_ms: bubbleStartMs,
      movement_started_ms: movementStartedMs,
      movement_arrival_ms: movementArrivalMs,
      pose_bindings: session.pose_bindings,
      bubble_schedule: session.bubble_schedule,
      conversation_plan: session.conversation_plan,
      emotion_roll: session.emotion_roll,
      emotion_outcome: session.emotion_outcome,
    });
    const talkCommands = [];
    if (kind === "pair") {
      for (const employeeId of participants) {
        const routeInfo = session.conversation_plan.route_info?.[employeeId];
        talkCommands.push({
          type: "start_talk_session",
          employee_id: employeeId,
          session_id: sessionId,
          mode,
          role: employeeId === session.initiator_id ? "initiator" : "participant",
          partner_id: session.partner_id,
          recovery_owner: employeeId === session.initiator_id,
          effective_at_ms: movementStartedMs,
          talk_start_at_ms: movementArrivalMs,
          talk_end_at_ms: fadeEndMs,
          return_start_at_ms: fadeEndMs + session.emotion_hold_ms,
          emotion: session.emotion_outcome,
          emotion_until_at_ms: session.emotion_outcome ? fadeEndMs + session.emotion_hold_ms : null,
          endpoint_uv: session.conversation_plan.endpoint_by_actor?.[employeeId] || null,
          endpoint_facing: session.conversation_plan.facing_by_actor?.[employeeId] || null,
          route_committed: Boolean(routeInfo),
          ...(routeInfo ? { route_info: routeInfo } : {}),
        });
      }
    }
    return { session, talkCommands };
  }

  appendBubbleStarted(snapshot, session, events, timestampMs) {
    if (session.bubble_start_event_emitted) return;
    session.bubble_started = true;
    session.bubble_start_event_emitted = true;
    this.appendEvent(snapshot, events, timestampMs, "speech_bubble_started", {
      employee_id: session.participants[0],
      session_id: session.session_id,
      floor_id: session.floor_id,
      kind: session.kind,
      mode: session.mode,
      category: session.category,
      participants: session.participants,
      bubble_visible_end_ms: session.bubble_visible_end_ms,
      fade_start_ms: session.fade_start_ms,
      fade_end_ms: session.fade_end_ms,
      bubble_schedule: session.bubble_schedule,
    });
  }

  finishParticipants(snapshot, participants, timestampMs, sessionId = null, events = []) {
    for (const employeeId of participants) {
      const actor = snapshot.actors[employeeId];
      if (!actor) continue;
      actor.speech_phase = "idle";
      actor.emotion = null;
      actor.emotion_until_ms = null;
      const counter = integer(actor.speech_event_counter, 0);
      actor.solo_next_due_ms = timestampMs + this.delayMs(snapshot, employeeId, "solo", counter);
      actor.pair_next_due_ms = actor.role === "ceo"
        ? null
        : timestampMs + this.delayMs(snapshot, employeeId, "pair", counter);
      actor.solo_pending = false;
      actor.pair_pending = false;
    }
    if (sessionId) {
      this.appendEvent(snapshot, events, timestampMs, "emotion_completed", {
        employee_id: participants[0],
        session_id: sessionId,
        participants: [...participants],
        return_requested: true,
      });
    }
  }

  completeSession(snapshot, sessionId, timestampMs, events) {
    const session = snapshot.active_sessions[sessionId];
    if (!session) return;
    delete snapshot.active_sessions[sessionId];
    const lane = snapshot.lanes[session.floor_id];
    if (lane) {
      lane.active_session_id = null;
      lane.active_until_ms = null;
      lane.last_completed_session_id = sessionId;
    }
    const emotion = session.emotion_outcome;
    this.appendEvent(snapshot, events, timestampMs, "speech_session_completed", {
      employee_id: session.participants[0],
      session_id: sessionId,
      floor_id: session.floor_id,
      participants: session.participants,
      return_requested: !(emotion && session.emotion_hold_ms > 0),
    });
    if (emotion && session.emotion_hold_ms > 0) {
      const emotionUntil = timestampMs + session.emotion_hold_ms;
      session.emotion_until_ms = emotionUntil;
      session.numeric_effect_policy = "standing_pair_emotion_only";
      session.stamina_effect_hook = "actor_snapshot_numeric_delta";
      for (const employeeId of session.participants) {
        const actor = snapshot.actors[employeeId];
        actor.speech_phase = "emotion";
        actor.emotion = emotion;
        actor.emotion_until_ms = emotionUntil;
      }
      this.appendEvent(snapshot, events, timestampMs, "emotion_started", {
        employee_id: session.participants[0],
        session_id: sessionId,
        emotion,
        emotion_roll: session.emotion_roll,
        participants: session.participants,
        stamina_effect_hook: "actor_snapshot_numeric_delta",
      });
    } else {
      this.finishParticipants(snapshot, session.participants, timestampMs, null, events);
    }
    snapshot.completed_sessions = snapshot.completed_sessions || {};
    snapshot.completed_sessions[sessionId] = session;
  }

  finishEmotions(snapshot, timestampMs, events) {
    const grouped = new Set();
    for (const [employeeId, actor] of Object.entries(snapshot.actors || {})) {
      if (actor.speech_phase !== "emotion" || actor.emotion_until_ms === null || integer(actor.emotion_until_ms) > timestampMs) continue;
      const sessionId = actor.last_session_id;
      if (grouped.has(sessionId)) continue;
      const session = snapshot.completed_sessions?.[sessionId];
      const participants = session?.participants || [employeeId];
      this.finishParticipants(snapshot, participants, timestampMs, sessionId, events);
      grouped.add(sessionId);
    }
  }

  processAt(snapshot, actorSnapshot, conversationSnapshot, nowMs, events, dialogueLocale, dialogueSeed) {
    this.finishEmotions(snapshot, nowMs, events);
    for (const session of Object.values(snapshot.active_sessions || {})) {
      if (!session.bubble_start_event_emitted && integer(session.bubble_start_ms) <= nowMs) {
        this.appendBubbleStarted(snapshot, session, events, integer(session.bubble_start_ms));
      }
    }
    for (const sessionId of Object.keys(snapshot.active_sessions || {}).sort()) {
      if (integer(snapshot.active_sessions[sessionId].fade_end_ms) <= nowMs) {
        this.completeSession(snapshot, sessionId, nowMs, events);
      }
    }
    this.syncActorState(snapshot, actorSnapshot, nowMs);
    for (const lane of Object.values(snapshot.lanes || {})) {
      lane.queued_session_ids = [];
      lane.queued_requests = [];
    }
    const byFloor = {};
    for (const employeeId of Object.keys(snapshot.actors || {}).sort()) {
      const request = this.requestForActor(
        snapshot,
        actorSnapshot,
        conversationSnapshot,
        employeeId,
        nowMs,
      );
      if (request) {
        const floor = snapshot.actors[employeeId].floor_id;
        (byFloor[floor] ||= []).push(request);
      }
    }
    const started = [];
    for (const floor of Object.keys(byFloor).sort()) {
      const lane = snapshot.lanes[floor] || (snapshot.lanes[floor] = {
        floor_id: floor,
        active_session_id: null,
        active_until_ms: null,
        queued_session_ids: [],
        queued_requests: [],
        last_completed_session_id: null,
      });
      const records = byFloor[floor]
        .map((request) => ({ request, metadata: this.queuedMetadata(snapshot, request, nowMs) }))
        .sort((left, right) => (
          (left.metadata.category === "leaving" ? 0 : left.metadata.category === "fatigue" ? 1 : left.metadata.category === "greeting" ? 2 : left.metadata.category === "work_start" ? 3 : left.metadata.category === "conversation_open" ? 4 : 5)
          - (right.metadata.category === "leaving" ? 0 : right.metadata.category === "fatigue" ? 1 : right.metadata.category === "greeting" ? 2 : right.metadata.category === "work_start" ? 3 : right.metadata.category === "conversation_open" ? 4 : 5)
          || integer(left.metadata.due_ms) - integer(right.metadata.due_ms)
          || left.metadata.initiator_id.localeCompare(right.metadata.initiator_id)
        ));
      if (lane.active_session_id) {
        lane.queued_session_ids = records.map((record) => record.metadata.initiator_id);
        lane.queued_requests = records.map((record) => record.metadata);
        continue;
      }
      for (const { request } of records) {
        const plan = this.buildPlan(snapshot, actorSnapshot, request, dialogueLocale, dialogueSeed);
        if (!plan) continue;
        const startedSession = this.startSession(snapshot, actorSnapshot, request, plan, nowMs, events, dialogueLocale);
        started.push(...startedSession.talkCommands);
        break;
      }
    }
    return started;
  }

  step(snapshot, {
    actorSnapshot,
    conversationSnapshot,
    elapsedMs,
    commands = [],
    dialogueLocale = "en",
    dialogueSeed = this.seed,
  } = {}) {
    if (!isObject(snapshot)) throw new TypeError("speech snapshot is required");
    const startMs = integer(snapshot.clock?.simulation_time_ms, 0);
    const targetMs = startMs + integer(elapsedMs, 0);
    const events = [];
    this.syncActorState(snapshot, actorSnapshot, startMs);
    for (const command of [...commands].sort((left, right) => String(left.employee_id).localeCompare(String(right.employee_id)))) {
      this.applyCommand(snapshot, command, startMs);
    }
    const talkCommands = [];
    const processBoundary = (timestampMs) => {
      const boundaryTalkCommands = this.processAt(
        snapshot,
        actorSnapshot,
        conversationSnapshot,
        timestampMs,
        events,
        dialogueLocale,
        dialogueSeed,
      );
      talkCommands.push(...boundaryTalkCommands);
    };
    processBoundary(startMs);
    let nowMs = startMs;
    while (nowMs < targetMs) {
      const boundaries = [targetMs];
      for (const session of Object.values(snapshot.active_sessions || {})) {
        for (const key of ["bubble_start_ms", "fade_end_ms"]) {
          const boundary = integer(session?.[key], targetMs);
          if (boundary > nowMs && boundary <= targetMs) boundaries.push(boundary);
        }
      }
      for (const actor of Object.values(snapshot.actors || {})) {
        for (const key of [
          "greeting_due_ms",
          "work_start_due_ms",
          "solo_next_due_ms",
          "pair_next_due_ms",
          "leaving_due_ms",
          "external_talk_due_ms",
          "emotion_until_ms",
        ]) {
          const boundary = actor?.[key];
          if (boundary !== null && boundary !== undefined) {
            const value = integer(boundary, targetMs);
            if (value > nowMs && value <= targetMs) boundaries.push(value);
          }
        }
      }
      let nextMs = Math.min(...boundaries);
      if (nextMs <= nowMs) nextMs = Math.min(targetMs, nowMs + TICK_MS);
      processBoundary(nextMs);
      nowMs = nextMs;
    }
    snapshot.clock.simulation_time_ms = targetMs;
    return { snapshot, events, talkCommands };
  }

  dialogueForActor(snapshot, employeeId, sampleMs) {
    const candidates = [
      ...(Object.values(snapshot.active_sessions || {})),
      ...(Object.values(snapshot.completed_sessions || {})),
    ].filter((session) => (
      isObject(session)
      && Array.isArray(session.participants)
      && session.participants.includes(employeeId)
    ));
    candidates.sort((left, right) => (
      integer(left.movement_started_ms, 0) - integer(right.movement_started_ms, 0)
      || String(left.session_id).localeCompare(String(right.session_id))
    ));
    const session = candidates.at(-1);
    if (!session) return null;
    const actor = snapshot.actors[employeeId];
    const authoritativeTalk = actor?.last_session_id === session.session_id || session.session_id in (snapshot.active_sessions || {});
    if (!authoritativeTalk) return null;
    const relative = integer(sampleMs) - integer(session.movement_started_ms, session.start_ms);
    if (relative < 0) return null;
    const schedule = session.bubble_schedule || [];
    let own = schedule.find((item) => item.employee_id === employeeId && sampleMs >= integer(item.start_ms) && sampleMs < integer(item.fade_end_ms));
    if (own) {
      const visibleEnd = integer(own.visible_end_ms, integer(own.start_ms) + BUBBLE_VISIBLE_MS);
      const fadeEnd = integer(own.fade_end_ms, visibleEnd + BUBBLE_FADE_MS);
      let opacity = 0;
      let phase = "hidden";
      if (sampleMs <= visibleEnd) {
        opacity = 1;
        phase = "visible";
      } else {
        opacity = Math.max(0, Math.min(1, 1 - ((sampleMs - visibleEnd) / Math.max(1, fadeEnd - visibleEnd))));
        phase = opacity > 0 ? "fading" : "hidden";
      }
      const line = session.conversation_plan?.dialogue_by_actor?.[employeeId] || null;
      return {
        visible: opacity > 0,
        opacity: Math.round(opacity * 10000) / 10000,
        phase,
        dialogue_id: line?.dialogue_id ?? null,
        line_index: line ? integer(line.line_index) : null,
        text: line?.text ?? null,
        locale: line?.locale ?? null,
        bubble_id: own.preferred_bubble_id ?? null,
        offset_xy: session.conversation_plan?.bubble_offset_by_actor?.[employeeId] || [0, 0],
        turn_index: integer(own.turn_index, 0),
        speaker_id: employeeId,
      };
    }
    if (session.kind === "pair" && sampleMs >= integer(session.bubble_start_ms, 0) && sampleMs < integer(session.fade_end_ms, 0)) {
      const first = schedule[0];
      if (first && sampleMs >= integer(first.start_ms) && sampleMs < integer(first.fade_end_ms)) {
        return {
          visible: false,
          opacity: 0,
          phase: "talking",
          dialogue_id: null,
          line_index: null,
          text: null,
          locale: null,
          bubble_id: null,
          offset_xy: [0, 0],
          turn_index: 0,
          speaker_id: first.employee_id,
        };
      }
    }
    return null;
  }
}

export {
  BUBBLE_FADE_MS,
  BUBBLE_VISIBLE_MS,
  EMOTION_HOLD_MS,
  SESSION_HOLD_MS,
  TICK_MS,
};
