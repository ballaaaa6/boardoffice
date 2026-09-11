const DEPTH_PROFILES_BY_FLOOR = {
  floor00: {
    ceo_desk_cell2: [
      [226, 306],
      [240, 313],
      [276, 295],
    ],
    ceo_pc: [
      [226, 306],
      [240, 313],
      [276, 295],
    ],
  },
  floor01: {
    reception: [
      [215, 382],
      [241, 395],
      [269, 381],
    ],
    ceo_desk_cell2: [
      [261, 282],
      [275, 289],
      [311, 271],
    ],
    ceo_pc: [
      [261, 282],
      [275, 289],
      [311, 271],
    ],
  },
};

const DEPTH_PROFILES_DEFAULT = {
  reception: [
    [209, 381],
    [267, 410],
    [297, 395],
  ],
  ceo_desk_cell2: [
    [293, 263],
    [329, 281],
    [343, 274],
  ],
  ceo_pc: [
    [293, 263],
    [329, 281],
    [343, 274],
  ],
};

function numberOr(value, fallback = 0) {
  const result = Number(value);
  return Number.isFinite(result) ? result : fallback;
}

function validGround(value) {
  return Array.isArray(value)
    && value.length === 2
    && Number.isFinite(Number(value[0]))
    && Number.isFinite(Number(value[1]));
}

const WORKSTATION_OCCLUDER_TYPES = new Set(["desk", "pc", "chair", "chair_sub"]);
const TALK_HOLD_MODES = new Set(["standing_pair", "seated_host", "ceo_front"]);

export function resolveWalkingOcclusionContext(actor) {
  if (TALK_HOLD_MODES.has(actor?.speech_mode) && actor?.route_phase === "talk_hold") {
    return "walking_talk_hold";
  }
  return "normal";
}

export function frontEdgeYAtX(frontEdge, worldX) {
  if (!Array.isArray(frontEdge) || !frontEdge.length) return null;
  const points = [...frontEdge].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const x = Math.min(Math.max(worldX, points[0][0]), points[points.length - 1][0]);
  for (let index = 0; index < points.length - 1; index += 1) {
    const [x0, y0] = points[index];
    const [x1, y1] = points[index + 1];
    if (x0 <= x && x <= x1) {
      if (x1 === x0) return Math.max(y0, y1);
      const progress = (x - x0) / (x1 - x0);
      return y0 + (y1 - y0) * progress;
    }
  }
  return points[points.length - 1][1];
}

/**
 * Resolve the authored walking occluders for a visual pose. The default uses
 * the legacy integer actor box for parity; smooth Canvas mode can opt into a
 * float actor box without changing gameplay state.
 */
export function resolveActorOccluderIds(
  actor,
  occluders,
  floorId,
  {
    anchor = [16, 31],
    width = 32,
    height = 42,
    snapActorBox = true,
  } = {},
) {
  if (actor?.render_owner !== "walking_depth" || !validGround(actor?.ground_xy)) return [];
  const [gx, gy] = actor.ground_xy.map(Number);
  const left = snapActorBox ? Math.round(gx - anchor[0]) : gx - anchor[0];
  const top = snapActorBox ? Math.round(gy - anchor[1]) : gy - anchor[1];
  const right = left + width;
  const bottom = top + height;
  const depthFrontEdges = DEPTH_PROFILES_BY_FLOOR[floorId] || DEPTH_PROFILES_DEFAULT;
  const walkingTalkHold = resolveWalkingOcclusionContext(actor) === "walking_talk_hold";
  const ids = [];

  for (const occluder of occluders || []) {
    if (walkingTalkHold && WORKSTATION_OCCLUDER_TYPES.has(occluder?.object_type)) {
      continue;
    }
    let inFront = false;
    if (occluder.always_foreground) {
      inFront = true;
    } else {
      const edge = occluder.depth_front_edge_world_px || depthFrontEdges[occluder.placement_id];
      const anchorY = edge
        ? frontEdgeYAtX(edge, gx)
        : occluder.depth_anchor_y_px;
      if (anchorY != null && anchorY > gy) inFront = true;
    }
    if (!inFront) continue;

    const ox0 = numberOr(occluder.x_px);
    const oy0 = numberOr(occluder.y_px);
    const ox1 = ox0 + numberOr(occluder.width);
    const oy1 = oy0 + numberOr(occluder.height);
    const ix0 = Math.max(left, ox0);
    const iy0 = Math.max(top, oy0);
    const ix1 = Math.min(right, ox1);
    const iy1 = Math.min(bottom, oy1);
    if (ix0 < ix1 && iy0 < iy1) ids.push(occluder.placement_id);
  }
  return ids;
}

export function sortCharacterPaintOrder(actors) {
  return [...(actors || [])].sort((left, right) => {
    const aGround = left?.ground_xy;
    const bGround = right?.ground_xy;
    const aHas = aGround ? 0 : 1;
    const bHas = bGround ? 0 : 1;
    if (aHas !== bHas) return aHas - bHas;
    const ay = aGround ? Number(aGround[1]) : 0;
    const by = bGround ? Number(bGround[1]) : 0;
    if (ay !== by) return ay - by;
    const aOrder = left?.assignment_order ?? 0;
    const bOrder = right?.assignment_order ?? 0;
    if (aOrder !== bOrder) return aOrder - bOrder;
    return String(left?.employee_id).localeCompare(String(right?.employee_id));
  }).map((actor) => actor?.employee_id);
}
