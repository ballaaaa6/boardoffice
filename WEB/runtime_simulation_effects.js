import { stableHash64 } from "./runtime_simulation_prng.js";

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function clone(value) {
  if (typeof globalThis.structuredClone === "function") return globalThis.structuredClone(value);
  return JSON.parse(JSON.stringify(value));
}

export class BrowserEffectsReducer {
  constructor({ employees = {}, effects = {}, seed = "gds-browser-runtime-v1" } = {}) {
    this.employees = employees;
    this.effects = effects;
    this.seed = seed;
  }

  presentation(actor, sampleMs) {
    const event = actor?.behavior?.active_event;
    if (event !== "background_effect" && event !== "popup") return null;
    if (actor.presence === "home") return null;
    const employee = this.employees?.[actor.employee_id] || {};
    const profile = employee.stamina_profile?.stamina_policy?.visual_recovery_references || {};
    const ids = event === "background_effect"
      ? (Array.isArray(profile.effect_ids) ? profile.effect_ids : [])
      : (Array.isArray(profile.humanball_ids) ? profile.humanball_ids : []);
    const counter = Number(actor.behavior?.event_counter || 0);
    const index = ids.length
      ? Number(stableHash64(actor.employee_id, event, counter) % BigInt(ids.length))
      : null;
    const assetId = index === null ? null : ids[index];
    const elapsed = Math.max(
      0,
      Number(sampleMs) - Number(actor.behavior?.activity_started_ms || sampleMs),
    );
    if (event === "background_effect") {
      return {
        channel: "vfx",
        asset_id: assetId,
        render_owner: "work_seat",
        action: "work",
        subaction: "normal_work",
        character_frame_ms: 360,
        effect_frame_ms: 240,
        effect_frame_index: Math.floor(elapsed / 240),
      };
    }
    return {
      channel: "humanball",
      asset_id: assetId,
      render_owner: "work_seat",
      action: "work",
      subaction: "normal_work",
      character_frame_ms: 360,
      humanball_frame_ms: 240,
      humanball_frame_index: Math.floor(elapsed / 240),
    };
  }

  channels(actor, sampleMs) {
    const binding = this.presentation(actor, sampleMs);
    if (!binding) return {};
    return { [binding.channel]: clone(binding) };
  }
}

export { isObject };
