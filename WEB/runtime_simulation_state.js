export const RUNTIME_SNAPSHOT_SCHEMA = "gds.runtime_snapshot.v1";
export const RUNTIME_SNAPSHOT_VERSION = "1.0.0";
export const RENDER_STATE_SCHEMA = "gds.runtime_render_state.v1";
export const RENDER_STATE_VERSION = "1.0.0";

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function requireObject(value, label) {
  if (!isObject(value)) throw new TypeError(`${label} must be an object`);
  return value;
}

function requireNonNegativeInteger(value, label) {
  if (!Number.isInteger(value) || value < 0) {
    throw new TypeError(`${label} must be a non-negative integer`);
  }
  return value;
}

function requireChannel(snapshot, key) {
  if (!isObject(snapshot[key])) {
    throw new TypeError(`${key} channel is required`);
  }
  return snapshot[key];
}

function validateActorChannel(channel, key) {
  if (key === "actor_snapshot" && channel.schema !== "gds.actor_snapshot.v1") {
    throw new TypeError("actor_snapshot schema is unsupported");
  }
  if (key === "speech_snapshot" && channel.schema !== "gds.speech_scheduler_snapshot.v1") {
    throw new TypeError("speech_snapshot schema is unsupported");
  }
  const actors = requireObject(channel.actors, `${key}.actors`);
  const clock = requireObject(channel.clock, `${key}.clock`);
  requireNonNegativeInteger(clock.simulation_time_ms, `${key}.clock.simulation_time_ms`);
  if (!Number.isInteger(clock.tick_ms) || clock.tick_ms <= 0) {
    throw new TypeError(`${key}.clock.tick_ms must be a positive integer`);
  }
  return actors;
}

export function validateRuntimeSnapshot(snapshot) {
  requireObject(snapshot, "runtime snapshot");
  if (snapshot.schema !== RUNTIME_SNAPSHOT_SCHEMA) {
    throw new TypeError("runtime snapshot schema is unsupported");
  }
  if (snapshot.version !== RUNTIME_SNAPSHOT_VERSION) {
    throw new TypeError("runtime snapshot version is unsupported");
  }

  const actorSnapshot = requireChannel(snapshot, "actor_snapshot");
  const speechSnapshot = requireChannel(snapshot, "speech_snapshot");
  const conversationSnapshot = requireChannel(snapshot, "conversation_snapshot");
  const actorIds = Object.keys(validateActorChannel(actorSnapshot, "actor_snapshot")).sort();
  const speechIds = Object.keys(validateActorChannel(speechSnapshot, "speech_snapshot")).sort();
  const conversationActors = requireObject(
    conversationSnapshot.actors,
    "conversation_snapshot.actors",
  );
  requireNonNegativeInteger(conversationSnapshot.clock_ms, "conversation_snapshot.clock_ms");

  if (conversationSnapshot.schema !== "gds.conversation_actor_snapshot.v1") {
    throw new TypeError("conversation_snapshot schema is unsupported");
  }
  const conversationIds = Object.keys(conversationActors).sort();
  const expected = JSON.stringify(actorIds);
  if (JSON.stringify(speechIds) !== expected || JSON.stringify(conversationIds) !== expected) {
    throw new TypeError("runtime snapshot actor ids must match across channels");
  }

  const actorClock = actorSnapshot.clock.simulation_time_ms;
  if (
    speechSnapshot.clock.simulation_time_ms !== actorClock
    || conversationSnapshot.clock_ms !== actorClock
  ) {
    throw new TypeError("runtime snapshot channel clocks must match");
  }
  return snapshot;
}

export function cloneJsonValue(value) {
  if (typeof globalThis.structuredClone === "function") {
    return globalThis.structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value));
}

export function cloneRuntimeSnapshot(snapshot) {
  validateRuntimeSnapshot(snapshot);
  return cloneJsonValue(snapshot);
}
