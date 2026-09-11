function numberOr(value, fallback = 0) {
  const result = Number(value);
  return Number.isFinite(result) ? result : fallback;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function sameFloor(left, right) {
  return Boolean(left && right && left.floor_id && left.floor_id === right.floor_id);
}

function sequential(left, right) {
  return sameFloor(left, right)
    && Math.trunc(numberOr(right.sequence, -1)) === Math.trunc(numberOr(left.sequence, -2)) + 1;
}

function validPoint(value) {
  return Array.isArray(value)
    && value.length === 2
    && Number.isFinite(Number(value[0]))
    && Number.isFinite(Number(value[1]));
}

function interpolatePoint(previous, current, progress) {
  return [
    numberOr(previous[0]) + (numberOr(current[0]) - numberOr(previous[0])) * progress,
    numberOr(previous[1]) + (numberOr(current[1]) - numberOr(previous[1])) * progress,
  ];
}

/**
 * Samples two accepted render states at the time the Canvas is painted.
 * The simulation remains fixed-step; this class owns presentation timing only.
 */
export class RenderTimeline {
  constructor({ now = () => globalThis.performance?.now?.() ?? Date.now() } = {}) {
    this.now = now;
    this.state = null;
    this.previousState = null;
    this.stateReceivedAt = 0;
    this.interpolationDurationMs = 1;
  }

  reset() {
    this.state = null;
    this.previousState = null;
    this.stateReceivedAt = 0;
    this.interpolationDurationMs = 1;
  }

  push(nextState, { receivedAtMs = this.now() } = {}) {
    if (!nextState || nextState.schema !== "gds.runtime_render_state.v1") {
      throw new TypeError("unsupported runtime render state");
    }
    const nextSequence = Math.trunc(numberOr(nextState.sequence, -1));
    if (this.state && nextSequence <= Math.trunc(numberOr(this.state.sequence, -1))) {
      return false;
    }

    const previous = this.state;
    const canInterpolate = sequential(previous, nextState);
    this.previousState = canInterpolate ? previous : null;
    this.state = nextState;
    this.stateReceivedAt = numberOr(receivedAtMs, this.now());
    this.interpolationDurationMs = canInterpolate
      ? Math.max(1, Math.trunc(numberOr(nextState.clock_ms, 0)) - Math.trunc(numberOr(previous.clock_ms, 0)))
      : 1;
    return true;
  }

  rows(nowMs = this.now()) {
    return sampleRenderRows(
      this.state,
      this.previousState,
      nowMs,
      this.stateReceivedAt,
      this.interpolationDurationMs,
    );
  }
}

/**
 * Pure row sampler kept separate so the renderer remains compatible with
 * existing tests and callers that assign a state directly.
 */
export function sampleRenderRows(
  state,
  previousState,
  nowMs,
  stateReceivedAt,
  interpolationDurationMs,
) {
  if (!state) return [];
  const currentRows = Array.isArray(state.actors) ? state.actors : [];
  const previousById = new Map(
    (previousState?.actors || []).map((row) => [row.employee_id, row]),
  );
  const progress = previousState
    ? clamp(
      (numberOr(nowMs) - numberOr(stateReceivedAt)) / Math.max(1, numberOr(interpolationDurationMs, 1)),
      0,
      1,
    )
    : 1;

  return currentRows.map((row) => {
    const previous = previousById.get(row.employee_id);
    if (!previous || !validPoint(previous.ground_xy) || !validPoint(row.ground_xy)) return row;
    if (row.render_owner !== "walking_depth" || previous.render_owner !== "walking_depth") return row;
    return { ...row, ground_xy: interpolatePoint(previous.ground_xy, row.ground_xy, progress) };
  });
}
