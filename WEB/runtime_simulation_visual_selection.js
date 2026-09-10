import { stableHash64 } from "./runtime_simulation_prng.js";

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function clone(value) {
  if (typeof globalThis.structuredClone === "function") return globalThis.structuredClone(value);
  return JSON.parse(JSON.stringify(value));
}

function integer(value, name) {
  if (!Number.isSafeInteger(Number(value)) || Number(value) < 0) {
    throw new TypeError(`${name} must be a non-negative integer`);
  }
  return Number(value);
}

export class BrowserVisualSelection {
  constructor({ catalog } = {}) {
    if (!isObject(catalog)) throw new TypeError("visual catalog is required");
    if (catalog.profile_id !== "gds.visual_catalog.v1") {
      throw new TypeError("visual catalog profile is unsupported");
    }
    if (typeof catalog.catalog_profile !== "string" || !catalog.catalog_profile) {
      throw new TypeError("visual catalog profile hash is required");
    }
    this._catalog = clone(catalog);
    this._ids = {};
    const channelSchemas = [
      ["vfx", "gds_effect_registry_v1", true],
      ["humanball", "gds_humanball_registry_v1", true],
      ["office_humanball", "gds_office_humanball_registry_v1", false],
    ];
    for (const [channel, schema, required] of channelSchemas) {
      const record = catalog[channel];
      if (!record && !required) continue;
      if (!isObject(record) || record.registry_schema !== schema || !Array.isArray(record.ids) || record.ids.length === 0) {
        throw new TypeError(`${channel} visual catalog is invalid`);
      }
      if (record.ids.some((assetId) => typeof assetId !== "string" || assetId.length === 0)) {
        throw new TypeError(`${channel} visual catalog IDs must be non-empty strings`);
      }
      if (new Set(record.ids).size !== record.ids.length) {
        throw new TypeError(`${channel} visual catalog IDs must be unique`);
      }
      this._ids[channel] = Object.freeze([...record.ids]);
    }
    this._catalog = Object.freeze(this._catalog);
    this.catalogProfile = catalog.catalog_profile;
  }

  catalog() {
    return clone(this._catalog);
  }

  requireChannel(channel) {
    if (!Object.prototype.hasOwnProperty.call(this._ids, channel)) {
      throw new TypeError(`unknown visual channel: ${channel}`);
    }
    return channel;
  }

  initialChannelState(channel) {
    this.requireChannel(channel);
    return {
      catalog_profile: this.catalogProfile,
      generation: 0,
      cursor: 0,
      active_binding: null,
    };
  }

  validateChannelState(state, channel) {
    this.requireChannel(channel);
    if (!isObject(state)) throw new TypeError("visual channel state must be an object");
    if (state.catalog_profile !== this.catalogProfile) {
      throw new TypeError("visual channel catalog profile mismatch");
    }
    const generation = integer(state.generation, "visual channel generation");
    const cursor = integer(state.cursor, "visual channel cursor");
    if (cursor > this._ids[channel].length) {
      throw new RangeError("visual channel cursor exceeds bag length");
    }
    if (state.active_binding !== null) {
      const binding = state.active_binding;
      if (!isObject(binding) || binding.channel !== channel || typeof binding.event_id !== "string" || !binding.event_id) {
        throw new TypeError("visual channel active binding is invalid");
      }
      if (!this._ids[channel].includes(binding.asset_id)) {
        throw new TypeError("visual channel active binding asset is invalid");
      }
    }
    return { ...clone(state), generation, cursor };
  }

  permutation({ channel, simulationSeed, employeeId, generation }) {
    this.requireChannel(channel);
    if (typeof simulationSeed !== "string" || simulationSeed.length === 0) {
      throw new TypeError("simulationSeed must be a non-empty string");
    }
    if (typeof employeeId !== "string" || employeeId.length === 0) {
      throw new TypeError("employeeId must be a non-empty string");
    }
    const generationNumber = integer(generation, "generation");
    const permutation = [...this._ids[channel]].sort((left, right) => {
      const leftHash = stableHash64(
        simulationSeed,
        "visual-bag",
        employeeId,
        channel,
        generationNumber,
        left,
      );
      const rightHash = stableHash64(
        simulationSeed,
        "visual-bag",
        employeeId,
        channel,
        generationNumber,
        right,
      );
      if (leftHash < rightHash) return -1;
      if (leftHash > rightHash) return 1;
      return left.localeCompare(right);
    });
    if (channel === "humanball" && generationNumber > 0 && permutation.length > 1) {
      const previousPermutation = [...this._ids[channel]].sort((left, right) => {
        const leftHash = stableHash64(
          simulationSeed,
          "visual-bag",
          employeeId,
          channel,
          generationNumber - 1,
          left,
        );
        const rightHash = stableHash64(
          simulationSeed,
          "visual-bag",
          employeeId,
          channel,
          generationNumber - 1,
          right,
        );
        if (leftHash < rightHash) return -1;
        if (leftHash > rightHash) return 1;
        return left.localeCompare(right);
      });
      if (permutation[0] === previousPermutation[previousPermutation.length - 1]) {
        // Keep the next generation a full permutation while preventing
        // an identical HumanBall at the boundary between bag cycles.
        [permutation[0], permutation[1]] = [permutation[1], permutation[0]];
      }
    }
    return permutation;
  }

  select(state, {
    channel,
    simulationSeed,
    employeeId,
    eventId,
    startedAtMs,
    endsAtMs,
    bagEmployeeId = null,
  } = {}) {
    this.requireChannel(channel);
    const current = this.validateChannelState(state, channel);
    if (typeof eventId !== "string" || eventId.length === 0) throw new TypeError("eventId must be a non-empty string");
    if (typeof employeeId !== "string" || employeeId.length === 0) {
      throw new TypeError("employeeId must be a non-empty string");
    }
    const start = integer(startedAtMs, "startedAtMs");
    const end = integer(endsAtMs, "endsAtMs");
    if (end < start) throw new RangeError("endsAtMs must not precede startedAtMs");
    const bagOwner = bagEmployeeId === null ? employeeId : bagEmployeeId;
    if (typeof bagOwner !== "string" || bagOwner.length === 0) {
      throw new TypeError("bagEmployeeId must be a non-empty string");
    }
    let generation = current.generation;
    let cursor = current.cursor;
    if (cursor === this._ids[channel].length) {
      generation += 1;
      cursor = 0;
    }
    const permutation = this.permutation({
      channel,
      simulationSeed,
      employeeId: bagOwner,
      generation,
    });
    const assetId = permutation[cursor];
    const cursorAfter = cursor + 1;
    const binding = {
      channel,
      asset_id: assetId,
      event_id: eventId,
      employee_id: employeeId,
      started_at_ms: start,
      ends_at_ms: end,
      generation,
      cursor_after: cursorAfter,
    };
    return {
      state: {
        ...current,
        generation,
        cursor: cursorAfter,
        active_binding: binding,
      },
      binding: clone(binding),
    };
  }

  clearActive(state, { channel, eventId = null } = {}) {
    this.requireChannel(channel);
    const current = this.validateChannelState(state, channel);
    if (current.active_binding && eventId !== null && current.active_binding.event_id !== eventId) {
      throw new TypeError(`active binding belongs to event ${current.active_binding.event_id}`);
    }
    return { ...current, active_binding: null };
  }
}

export { isObject };
