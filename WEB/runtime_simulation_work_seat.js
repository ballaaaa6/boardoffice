const DEFAULT_CHARACTER_ANCHOR = [16, 31];
const SEAT_TRANSITION_MS = 240;
const DIRECTIONS = new Set(["NW", "SE", "SW", "NE"]);

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function round4(value) {
  return Math.round(Number(value) * 10000) / 10000;
}

function profileOffset(seat, characterId, assets, characters) {
  const profile = seat.visual_profile || {};
  if (profile.mode === "native_verified") {
    const offset = profile.visual_character_offset_from_chair_px;
    if (Array.isArray(offset) && offset.length === 2) return [Number(offset[0]), Number(offset[1])];
  }
  const sourceDirection = String(profile.derived_from || "").toUpperCase();
  const sourceProfile = profile.mode === "derived"
    ? (seat.visual_profile_source || {})
    : profile;
  const sourceOffset = sourceProfile.visual_character_offset_from_chair_px
    || (sourceDirection === "SE" ? [2, 2] : [-10, -6]);
  const chairDimensions = assets?.[seat.chair_asset_id]?.dimensions || [32, 32];
  const characterDimensions = characters?.[characterId]?.render_canvas || [32, 42];
  return [
    Number(chairDimensions[0]) - Number(sourceOffset[0]) - Number(characterDimensions[0]),
    Number(sourceOffset[1]),
  ];
}

export class BrowserWorkSeatReducer {
  constructor({ workSeats = {}, employees = {}, assets = {}, characters = {} } = {}) {
    this.workSeats = workSeats;
    this.employees = employees;
    this.assets = assets;
    this.characters = characters;
  }

  seat(floorId, workstationId) {
    const seat = this.workSeats?.[workstationId]?.seat;
    if (!isObject(seat) || (floorId && seat.floor_id !== floorId)) {
      throw new TypeError(`Unknown WorkSeat: ${floorId}.${workstationId}`);
    }
    return seat;
  }

  navigationAccess(workstationId) {
    const access = this.workSeats?.[workstationId]?.navigation_access;
    if (!isObject(access)) throw new TypeError(`Unknown WorkSeat access: ${workstationId}`);
    return access;
  }

  visualCharacterAnchor(floorId, workstationId, characterId) {
    const seat = this.seat(floorId, workstationId);
    const [offsetX, offsetY] = profileOffset(seat, characterId, this.assets, this.characters);
    return [
      round4(Number(seat.chair_x_px) + offsetX + DEFAULT_CHARACTER_ANCHOR[0]),
      round4(Number(seat.chair_y_px) + offsetY + DEFAULT_CHARACTER_ANCHOR[1]),
    ];
  }

  pcFrameCount(workstationId) {
    const seat = this.workSeats?.[workstationId]?.seat;
    if (!seat) throw new TypeError(`Unknown WorkSeat: ${workstationId}`);
    const direction = String(seat.direction || "SE").toUpperCase();
    if (!DIRECTIONS.has(direction)) throw new TypeError(`Unsupported WorkSeat direction: ${direction}`);
    return direction === "NW" || direction === "NE" ? 5 : 1;
  }

  seatTransitionRecord({
    phase,
    fromGround,
    toGround,
    direction,
    completion = null,
  }) {
    if (phase !== "seat_exit" && phase !== "seat_entry") {
      throw new TypeError(`Unknown seat transition phase: ${phase}`);
    }
    if (phase === "seat_exit" && completion !== null) {
      throw new TypeError("seat_exit cannot have a completion route");
    }
    if (phase === "seat_entry" && !completion) {
      throw new TypeError("seat_entry needs a completion route");
    }
    const normalizedDirection = DIRECTIONS.has(String(direction || "").toUpperCase())
      ? String(direction).toUpperCase()
      : "SE";
    return {
      phase,
      anchor_source: "WorkSeatCore",
      from_ground_xy: fromGround.map(round4),
      to_ground_xy: toGround.map(round4),
      elapsed_ms: 0,
      duration_ms: SEAT_TRANSITION_MS,
      render_owner: "walking_depth",
      action: "move",
      subaction: "idle",
      direction: normalizedDirection,
      raw_direction: normalizedDirection,
      visibility_alpha: 1,
      completion,
    };
  }

  step(actor, seatState = {}, context = {}, elapsedMs = 0) {
    if (!isObject(actor) || !isObject(actor.position)) throw new TypeError("actor position is required");
    const transition = actor.position.seat_transition;
    if (!isObject(transition)) return { actor, seatState, events: [] };
    if (!Number.isInteger(elapsedMs) || elapsedMs < 0) throw new TypeError("elapsedMs must be a non-negative integer");
    const duration = Math.max(60, Number(transition.duration_ms));
    transition.elapsed_ms = Math.min(duration, Number(transition.elapsed_ms || 0) + elapsedMs);
    const progress = Math.min(1, Math.max(0, transition.elapsed_ms / duration));
    const from = transition.from_ground_xy;
    const to = transition.to_ground_xy;
    actor.position.ground_xy = [
      round4(Number(from[0]) + (Number(to[0]) - Number(from[0])) * progress),
      round4(Number(from[1]) + (Number(to[1]) - Number(from[1])) * progress),
    ];
    actor.position.uv = null;
    const events = [];
    if (transition.elapsed_ms >= duration && transition.phase === "seat_exit") {
      delete actor.position.seat_transition;
    }
    return { actor, seatState, events };
  }
}

export { SEAT_TRANSITION_MS };
