function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function clone(value) {
  if (typeof globalThis.structuredClone === "function") return globalThis.structuredClone(value);
  return JSON.parse(JSON.stringify(value));
}

export class BrowserEffectsReducer {
  constructor({ employees = {}, effects = {}, visualSelection = null } = {}) {
    this.employees = employees;
    this.effects = effects;
    this.visualSelection = visualSelection;
  }

  presentation(actor, sampleMs) {
    const event = actor?.behavior?.active_event;
    if (event !== "background_effect" && event !== "popup") return null;
    if (actor.presence === "home") return null;
    const channel = event === "background_effect" ? "vfx" : "humanball";
    const binding = actor.behavior?.visual_channels?.[channel]?.active_binding;
    const assetId = isObject(binding) ? binding.asset_id : null;
    const selectionSource = isObject(binding) && binding.selection_source
      ? binding.selection_source
      : "shuffle_bag";
    const elapsed = Math.max(
      0,
      Number(sampleMs) - Number(actor.behavior?.activity_started_ms || sampleMs),
    );
    if (event === "background_effect") {
      return {
        channel: "vfx",
        asset_id: assetId,
        selection_source: selectionSource,
        visual_event_id: binding?.event_id ?? null,
        visual_generation: binding?.generation ?? null,
        visual_cursor_after: binding?.cursor_after ?? null,
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
      selection_source: selectionSource,
      visual_event_id: binding?.event_id ?? null,
      visual_generation: binding?.generation ?? null,
      visual_cursor_after: binding?.cursor_after ?? null,
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
