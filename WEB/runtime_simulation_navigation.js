const NEIGHBOR_DELTAS = Object.freeze([[1, 0], [0, 1], [-1, 0], [0, -1]]);
const DIRECTION_SCREEN_VECTORS = Object.freeze({
  SE: [2, 1],
  SW: [-2, 1],
  NW: [-2, -1],
  NE: [2, -1],
});
const OPPOSITE_DIRECTIONS = Object.freeze({ SE: "NW", NW: "SE", SW: "NE", NE: "SW" });
const STEP_MS = 60;
const SUBSTEPS_PER_CELL = 4;
const BASE_MOVE_SPEED_CELLS_PER_SECOND = 1000 / (STEP_MS * SUBSTEPS_PER_CELL);
const FINE_STEP_DISTANCE_PX = Math.sqrt(5);

export class BrowserNavigationError extends Error {}

function cell(value, v = undefined, label = "uv") {
  const result = Array.isArray(value) ? value : [value, v];
  if (
    result.length !== 2
    || !Number.isInteger(result[0])
    || !Number.isInteger(result[1])
  ) {
    throw new TypeError(`${label} must contain two integer coordinates`);
  }
  return [result[0], result[1]];
}

function key(value) {
  return `${value[0]},${value[1]}`;
}

function round4(value) {
  return Math.round(Number(value) * 10000) / 10000;
}

function manhattan(left, right) {
  return Math.abs(left[0] - right[0]) + Math.abs(left[1] - right[1]);
}

class MinHeap {
  constructor(compare) {
    this.compare = compare;
    this.items = [];
  }

  push(item) {
    this.items.push(item);
    let index = this.items.length - 1;
    while (index > 0) {
      const parent = Math.floor((index - 1) / 2);
      if (this.compare(this.items[parent], item) <= 0) break;
      this.items[index] = this.items[parent];
      index = parent;
    }
    this.items[index] = item;
  }

  pop() {
    if (this.items.length === 0) return undefined;
    const first = this.items[0];
    const last = this.items.pop();
    if (this.items.length > 0) {
      let index = 0;
      while (true) {
        const left = index * 2 + 1;
        if (left >= this.items.length) break;
        const right = left + 1;
        let child = left;
        if (
          right < this.items.length
          && this.compare(this.items[right], this.items[left]) < 0
        ) child = right;
        if (this.compare(this.items[child], last) >= 0) break;
        this.items[index] = this.items[child];
        index = child;
      }
      this.items[index] = last;
    }
    return first;
  }

  get length() {
    return this.items.length;
  }
}

export class BrowserNavigation {
  constructor({ world, workSeats = null } = {}) {
    if (!world || typeof world !== "object") {
      throw new TypeError("BrowserNavigation requires world runtime inputs");
    }
    this.world = world;
    this.navigation = world.navigation || {};
    this.roomNavigation = world.room_navigation || {};
    this.workSeats = workSeats || {};
    this.floorId = this.navigation.floor_id || world.floor?.floor_id || null;
    this.grid = this.roomNavigation.grid || {
      grid_origin_px: [28, 0],
      u_step_px: [2, 1],
      v_step_px: [-2, 1],
    };
    this.walkable = new Set(
      (this.navigation.walkable_cells_uv || []).map((value) => key(cell(value))),
    );
  }

  isWalkable(u, v = undefined) {
    return this.walkable.has(key(cell(u, v)));
  }

  portal(floorId = this.floorId) {
    if (floorId !== this.floorId) {
      throw new BrowserNavigationError(`Unknown floor: ${floorId}`);
    }
    return this.roomNavigation.portal || {
      floor_id: floorId,
      inside_cells_uv: this.navigation.portal_inside_cells_uv || [],
      outside_cells_uv: this.navigation.portal_outside_cells_uv || [],
    };
  }

  workstationAccess(workstationId) {
    const record = this.workSeats?.[workstationId];
    if (!record?.navigation_access) {
      throw new BrowserNavigationError(`Unknown workstation: ${workstationId}`);
    }
    return record.navigation_access;
  }

  uvCellCenterToPixel(u, v = undefined) {
    const [cellU, cellV] = cell(u, v);
    const origin = this.grid.grid_origin_px || [28, 0];
    const uStep = this.grid.u_step_px || [2, 1];
    const vStep = this.grid.v_step_px || [-2, 1];
    const x = origin[0] + (cellU + 0.5) * uStep[0] + (cellV + 0.5) * vStep[0];
    const y = origin[1] + (cellU + 0.5) * uStep[1] + (cellV + 0.5) * vStep[1];
    return [Math.round(x), Math.round(y)];
  }

  directionForStep(startUv, targetUv) {
    const start = cell(startUv, undefined, "start_uv");
    const target = cell(targetUv, undefined, "target_uv");
    const delta = `${target[0] - start[0]},${target[1] - start[1]}`;
    const directions = {
      "1,0": "SE",
      "-1,0": "NW",
      "0,1": "SW",
      "0,-1": "NE",
    };
    if (!directions[delta]) {
      throw new BrowserNavigationError(`Unsupported movement step: ${start} -> ${target}`);
    }
    return directions[delta];
  }

  findPath(startUv, goalUv, { blockedCells = [] } = {}) {
    const start = cell(startUv, undefined, "start_uv");
    const goal = cell(goalUv, undefined, "goal_uv");
    const blocked = new Set(blockedCells.map((value) => key(cell(value, undefined, "blocked cell"))));
    blocked.delete(key(start));
    blocked.delete(key(goal));
    if (!this.walkable.has(key(start))) {
      throw new BrowserNavigationError(`start is not a walkable cell: ${start}`);
    }
    if (!this.walkable.has(key(goal))) {
      throw new BrowserNavigationError(`goal is not a walkable cell: ${goal}`);
    }
    if (start[0] === goal[0] && start[1] === goal[1]) {
      return {
        floor_id: this.floorId,
        start_uv: [...start],
        goal_uv: [...goal],
        path_cells_uv: [[...start]],
        path_cell_count: 1,
        compressed_waypoints_uv: [[...start]],
        reachable: true,
      };
    }

    const frontier = new MinHeap((left, right) => (
      left.f - right.f
      || left.g - right.g
      || left.cell[1] - right.cell[1]
      || left.cell[0] - right.cell[0]
      || left.sequence - right.sequence
    ));
    let sequence = 0;
    frontier.push({
      f: manhattan(start, goal),
      g: 0,
      cell: start,
      sequence,
    });
    const cameFrom = new Map([[key(start), null]]);
    const bestG = new Map([[key(start), 0]]);
    while (frontier.length > 0) {
      const current = frontier.pop();
      const currentKey = key(current.cell);
      if (current.g !== bestG.get(currentKey)) continue;
      if (current.cell[0] === goal[0] && current.cell[1] === goal[1]) break;
      for (const [du, dv] of NEIGHBOR_DELTAS) {
        const next = [current.cell[0] + du, current.cell[1] + dv];
        const nextKey = key(next);
        if (!this.walkable.has(nextKey) || blocked.has(nextKey)) continue;
        const candidateG = current.g + 1;
        if (candidateG >= (bestG.get(nextKey) ?? Number.MAX_SAFE_INTEGER)) continue;
        bestG.set(nextKey, candidateG);
        cameFrom.set(nextKey, current.cell);
        sequence += 1;
        frontier.push({
          f: candidateG + manhattan(next, goal),
          g: candidateG,
          cell: next,
          sequence,
        });
      }
    }
    if (!cameFrom.has(key(goal))) {
      throw new BrowserNavigationError(`no route from ${start} to ${goal}`);
    }
    const path = [];
    let current = goal;
    while (current) {
      path.push([...current]);
      current = cameFrom.get(key(current));
    }
    path.reverse();
    return {
      floor_id: this.floorId,
      start_uv: [...start],
      goal_uv: [...goal],
      path_cells_uv: path,
      path_cell_count: path.length,
      compressed_waypoints_uv: this.compressPath(path),
      reachable: true,
    };
  }

  compressPath(pathCellsUv) {
    const path = pathCellsUv.map((value) => cell(value));
    if (path.length <= 2) return path.map((value) => [...value]);
    const result = [[...path[0]]];
    let previousDelta = [path[1][0] - path[0][0], path[1][1] - path[0][1]];
    for (let index = 1; index < path.length - 1; index += 1) {
      const current = path[index];
      const next = path[index + 1];
      const delta = [next[0] - current[0], next[1] - current[1]];
      if (delta[0] !== previousDelta[0] || delta[1] !== previousDelta[1]) {
        result.push([...current]);
        previousDelta = delta;
      }
    }
    result.push([...path.at(-1)]);
    return result;
  }

  resolvePortalStart(floorId = this.floorId) {
    const portalCells = (this.portal(floorId).inside_cells_uv || [])
      .map((value) => cell(value))
      .filter((value) => this.walkable.has(key(value)));
    if (portalCells.length === 0) throw new BrowserNavigationError("no walkable portal-inside cells");
    const meanU = portalCells.reduce((sum, value) => sum + value[0], 0) / portalCells.length;
    const meanV = portalCells.reduce((sum, value) => sum + value[1], 0) / portalCells.length;
    return [...portalCells].sort((left, right) => (
      (Math.abs(left[0] - meanU) + Math.abs(left[1] - meanV))
      - (Math.abs(right[0] - meanU) + Math.abs(right[1] - meanV))
      || left[1] - right[1]
      || left[0] - right[0]
    ))[0];
  }

  portalPair(floorId = this.floorId) {
    const inside = this.resolvePortalStart(floorId);
    const outsideCells = (this.portal(floorId).outside_cells_uv || []).map((value) => cell(value));
    if (outsideCells.length === 0) throw new BrowserNavigationError("portal has no outside cells");
    const adjacent = outsideCells.filter((value) => manhattan(value, inside) === 1);
    const candidates = adjacent.length ? adjacent : outsideCells;
    const outside = [...candidates].sort((left, right) => (
      manhattan(left, inside) - manhattan(right, inside)
      || left[1] - right[1]
      || left[0] - right[0]
    ))[0];
    return { inside, outside };
  }

  routeDurationMs(pathCellsUv, speedMultiplier) {
    const path = pathCellsUv.map((value) => cell(value));
    if (path.length < 2) return STEP_MS;
    const multiplier = Number(speedMultiplier);
    if (!(multiplier > 0)) throw new TypeError("speedMultiplier must be positive");
    const cellsPerTick = BASE_MOVE_SPEED_CELLS_PER_SECOND * multiplier * STEP_MS / 1000;
    return Math.max(STEP_MS, Math.ceil((path.length - 1) / cellsPerTick) * STEP_MS);
  }

  visualDirectionsForPath(pathCellsUv, {
    lookaheadCells = 3,
    confirmSteps = 2,
    minHoldCells = 0.75,
  } = {}) {
    const path = pathCellsUv.map((value) => cell(value));
    if (path.length < 2) return [];
    const raw = path.slice(0, -1).map((value, index) => (
      this.directionForStep(value, path[index + 1])
    ));
    let stable = raw[0];
    let pending = null;
    let pendingCount = 0;
    let lastChangeStep = 0;
    const result = [];
    for (let stepIndex = 0; stepIndex < raw.length; stepIndex += 1) {
      const endIndex = Math.min(path.length - 1, stepIndex + lookaheadCells);
      const [sx, sy] = this.uvCellCenterToPixel(path[stepIndex]);
      const [ex, ey] = this.uvCellCenterToPixel(path[endIndex]);
      const scores = Object.fromEntries(
        Object.entries(DIRECTION_SCREEN_VECTORS).map(([direction, vector]) => [
          direction,
          (ex - sx) * vector[0] + (ey - sy) * vector[1],
        ]),
      );
      const best = Math.max(...Object.values(scores));
      const tied = Object.keys(DIRECTION_SCREEN_VECTORS).filter(
        (direction) => Math.abs(scores[direction] - best) <= 1e-9,
      );
      const candidate = tied.includes(stable) ? stable : tied[0];
      if (candidate === stable) {
        pending = null;
        pendingCount = 0;
      } else if (candidate === OPPOSITE_DIRECTIONS[stable]) {
        stable = candidate;
        lastChangeStep = stepIndex;
        pending = null;
        pendingCount = 0;
      } else {
        if (pending === candidate) pendingCount += 1;
        else {
          pending = candidate;
          pendingCount = 1;
        }
        const heldCells = stepIndex - lastChangeStep;
        if (heldCells >= minHoldCells && pendingCount >= confirmSteps) {
          stable = candidate;
          lastChangeStep = stepIndex;
          pending = null;
          pendingCount = 0;
        }
      }
      result.push(DIRECTION_SCREEN_VECTORS[stable] ? stable : raw[stepIndex]);
    }
    return result;
  }

  pathPose(pathCellsUv, elapsedMs, speedMultiplier) {
    const path = pathCellsUv.map((value) => cell(value));
    if (path.length < 2) {
      const ground = this.uvCellCenterToPixel(path[0]);
      return {
        ground_xy: ground,
        current_uv: [...path[0]],
        from_uv: [...path[0]],
        to_uv: [...path[0]],
        progress_t: 1,
        direction: "SE",
        raw_direction: "SE",
        cumulative_distance_px: 0,
      };
    }
    const cellsPerSecond = BASE_MOVE_SPEED_CELLS_PER_SECOND * Number(speedMultiplier);
    const totalCells = path.length - 1;
    const distanceCells = Math.min(totalCells, Math.max(0, Number(elapsedMs)) / 1000 * cellsPerSecond);
    const nearestCell = Math.round(distanceCells);
    let stepIndex;
    let progress;
    if (distanceCells > 0 && Math.abs(distanceCells - nearestCell) <= 1e-9) {
      stepIndex = Math.min(nearestCell - 1, path.length - 2);
      progress = 1;
    } else {
      stepIndex = Math.min(Math.floor(distanceCells), path.length - 2);
      progress = distanceCells - stepIndex;
    }
    const current = path[stepIndex];
    const target = path[stepIndex + 1];
    const [sx, sy] = this.uvCellCenterToPixel(current);
    const [ex, ey] = this.uvCellCenterToPixel(target);
    const rawDirection = this.directionForStep(current, target);
    const visual = this.visualDirectionsForPath(path);
    return {
      ground_xy: [round4(sx + (ex - sx) * progress), round4(sy + (ey - sy) * progress)],
      current_uv: Math.abs(progress - 1) <= 1e-9 ? [...target] : null,
      from_uv: [...current],
      to_uv: [...target],
      progress_t: round4(progress),
      direction: visual[stepIndex],
      raw_direction: rawDirection,
      cumulative_distance_px: round4(distanceCells * FINE_STEP_DISTANCE_PX),
    };
  }

  portalPose(route, elapsedMs) {
    const start = cell(route.start_uv);
    const target = cell(route.target_uv);
    const duration = Math.max(STEP_MS, Number(route.duration_ms));
    const progress = Math.min(1, Math.max(0, Number(elapsedMs) / duration));
    const [sx, sy] = this.uvCellCenterToPixel(start);
    const [ex, ey] = this.uvCellCenterToPixel(target);
    const direction = this.directionForStep(start, target);
    const alpha = route.phase === "portal_entry" ? progress : 1 - progress;
    return {
      ground_xy: [round4(sx + (ex - sx) * progress), round4(sy + (ey - sy) * progress)],
      current_uv: Math.abs(progress - 1) <= 1e-9 ? [...target] : null,
      from_uv: [...start],
      to_uv: [...target],
      progress_t: round4(progress),
      direction,
      raw_direction: direction,
      cumulative_distance_px: round4(Math.hypot(ex - sx, ey - sy) * progress),
      visibility_alpha: round4(Math.max(0, Math.min(1, alpha))),
    };
  }

  routeDistancePx(actor, route) {
    if (!route) return 0;
    const phase = String(route.phase || "");
    const elapsed = Math.max(0, Number(route.elapsed_ms || 0));
    if (phase === "talk_hold") return 0;
    if (phase === "portal_entry" || phase === "portal_exit") {
      return this.portalPose(route, elapsed).cumulative_distance_px;
    }
    if (!["to_portal", "to_workseat", "wander_out", "wander_back", "talk_outbound", "talk_return"].includes(phase)) {
      return 0;
    }
    return this.pathPose(route.path_cells_uv || [], elapsed, actor.movement_speed_multiplier || 1)
      .cumulative_distance_px;
  }

  walkCycleFrameIndex(cumulativeDistancePx, frameCount, frameDistanceCells) {
    if (!Number.isInteger(frameCount) || frameCount <= 0) {
      throw new TypeError("frameCount must be positive");
    }
    const phaseDistancePx = FINE_STEP_DISTANCE_PX * Number(frameDistanceCells);
    if (!(phaseDistancePx > 0)) throw new TypeError("frameDistanceCells must be positive");
    return Math.floor(Number(cumulativeDistancePx) / phaseDistancePx) % frameCount;
  }
}

export { cell as normalizeUv, key as uvKey, FINE_STEP_DISTANCE_PX };
