const DEFAULT_MANIFEST_URL = "/runtime_render_manifest.json";
const DEFAULT_ANCHOR = [16, 31];
const DEFAULT_CHARACTER_SIZE = [32, 42];
const DEFAULT_CANVAS_SIZE = [600, 600];
const BUBBLE_SIZES = {
  BB1: [71, 20, 35, 19],
  BB2: [57, 20, 28, 19],
  BB3: [41, 20, 20, 19],
  BB4: [23, 18, 11, 17],
  BB6: [49, 20, 24, 19],
};

function numberOr(value, fallback = 0) {
  const result = Number(value);
  return Number.isFinite(result) ? result : fallback;
}
function integerOr(value, fallback = 0) {
  return Math.trunc(numberOr(value, fallback));
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function sameFloor(left, right) {
  return Boolean(left && right && left.floor_id === right.floor_id);
}

function sequential(left, right) {
  return sameFloor(left, right)
    && integerOr(right.sequence, -1) === integerOr(left.sequence, -2) + 1;
}

function validPoint(value) {
  return Array.isArray(value)
    && value.length === 2
    && Number.isFinite(Number(value[0]))
    && Number.isFinite(Number(value[1]));
}

function interpolatePoint(previous, current, progress) {
  if (!validPoint(previous) || !validPoint(current)) return current;
  return [
    numberOr(previous[0]) + (numberOr(current[0]) - numberOr(previous[0])) * progress,
    numberOr(previous[1]) + (numberOr(current[1]) - numberOr(previous[1])) * progress,
  ];
}

function imageIsReady(image) {
  return Boolean(image && image.complete && (image.naturalWidth || image.width));
}

export class RuntimeCanvasRenderer {
  constructor({
    canvas,
    manifestUrl = DEFAULT_MANIFEST_URL,
    imageFactory = () => new Image(),
    fetchImpl = globalThis.fetch?.bind(globalThis),
    now = () => globalThis.performance?.now?.() ?? Date.now(),
  } = {}) {
    if (!canvas || typeof canvas.getContext !== "function") {
      throw new TypeError("RuntimeCanvasRenderer requires a canvas element");
    }
    if (typeof fetchImpl !== "function") {
      throw new TypeError("RuntimeCanvasRenderer requires fetch");
    }
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    if (!this.ctx) throw new Error("Canvas 2D context is unavailable");
    this.ctx.imageSmoothingEnabled = false;
    this.manifestUrl = manifestUrl;
    this.imageFactory = imageFactory;
    this.fetchImpl = fetchImpl;
    this.now = now;
    this.manifest = null;
    this.manifestPromise = null;
    this.imageCache = new Map();
    this.lastReadyPcFrames = new Map();
    this.state = null;
    this.previousState = null;
    this.stateReceivedAt = 0;
    this.interpolationDurationMs = 1;
    this.destroyed = false;
    this.lastError = null;
    this.actorCanvas = null;
    this.actorCtx = null;
    this._setCanvasSize(...DEFAULT_CANVAS_SIZE);
  }

  _setCanvasSize(width, height) {
    const targetWidth = integerOr(width, DEFAULT_CANVAS_SIZE[0]);
    const targetHeight = integerOr(height, DEFAULT_CANVAS_SIZE[1]);
    if (this.canvas.width !== targetWidth) this.canvas.width = targetWidth;
    if (this.canvas.height !== targetHeight) this.canvas.height = targetHeight;
    this.ctx.imageSmoothingEnabled = false;
  }

  _absoluteUrl(url) {
    return new URL(String(url), new URL(this.manifestUrl, globalThis.location?.href || "http://127.0.0.1/")).href;
  }

  _loadImage(url) {
    if (!url) return null;
    const absoluteUrl = this._absoluteUrl(url);
    const cached = this.imageCache.get(absoluteUrl);
    if (cached) return cached;
    const image = this.imageFactory();
    const entry = { image, ready: false, error: null, promise: null };
    entry.promise = new Promise((resolve, reject) => {
      image.onload = () => {
        entry.ready = true;
        resolve(image);
      };
      image.onerror = (error) => {
        entry.error = error || new Error(`Unable to load ${absoluteUrl}`);
        reject(entry.error);
      };
      image.decoding = "async";
      image.src = absoluteUrl;
      if (imageIsReady(image)) {
        entry.ready = true;
        resolve(image);
      }
    }).catch((error) => {
      this.lastError = error;
      return null;
    });
    this.imageCache.set(absoluteUrl, entry);
    return entry;
  }

  _readyImage(url) {
    const entry = this._loadImage(url);
    return entry?.ready ? entry.image : null;
  }

  _queueImagePreload(pending, url) {
    const entry = this._loadImage(url);
    if (entry?.promise) pending.push(entry.promise);
  }

  async loadManifest() {
    if (this.manifest) return this.manifest;
    if (this.manifestPromise) return this.manifestPromise;
    this.manifestPromise = this.fetchImpl(this.manifestUrl, { cache: "force-cache" })
      .then(async (response) => {
        if (!response.ok) throw new Error(`manifest HTTP ${response.status}`);
        const manifest = await response.json();
        if (manifest?.schema !== "gds.runtime_render_manifest.v1") {
          throw new Error("unsupported runtime render manifest");
        }
        if (!manifest.canvas || !manifest.static_scene || !manifest.workstations) {
          throw new Error("runtime render manifest is incomplete");
        }
        this.manifest = manifest;
        this.lastReadyPcFrames.clear();
        this._setCanvasSize(manifest.canvas.width, manifest.canvas.height);
        const pending = [];
        this._queueImagePreload(pending, manifest.static_scene.url);
        for (const overlay of manifest.overlays || []) {
          if (overlay?.url) this._queueImagePreload(pending, overlay.url);
        }
        for (const workstation of Object.values(manifest.workstations || {})) {
          for (const component of workstation.components || []) {
            if (component?.url) this._queueImagePreload(pending, component.url);
          }
          for (const frame of workstation.pc_frames || []) {
            if (frame?.url) this._queueImagePreload(pending, frame.url);
          }
        }
        await Promise.all(pending);
        return manifest;
      })
      .catch((error) => {
        this.lastError = error;
        this.manifestPromise = null;
        throw error;
      });
    return this.manifestPromise;
  }

  setState(nextState) {
    if (this.destroyed) return false;
    if (!nextState || nextState.schema !== "gds.runtime_render_state.v1") {
      throw new TypeError("unsupported runtime render state");
    }
    if (this.manifest && nextState.floor_id !== this.manifest.floor_id) {
      throw new Error(`render state floor mismatch: ${nextState.floor_id}`);
    }
    const nextSequence = integerOr(nextState.sequence, -1);
    if (this.state && nextSequence <= integerOr(this.state.sequence, -1)) return false;
    const previous = this.state;
    const canInterpolate = sequential(previous, nextState);
    this.previousState = canInterpolate ? previous : null;
    this.state = nextState;
    this.stateReceivedAt = this.now();
    this.interpolationDurationMs = canInterpolate
      ? Math.max(1, integerOr(nextState.clock_ms, 0) - integerOr(previous.clock_ms, 0))
      : 1;
    for (const actor of nextState.actors || []) {
      if (actor?.character_id && actor?.frame_id) this._primeCharacter(actor);
      const workstation = this.manifest?.workstations?.[actor.workstation_id];
      const effect = actor?.channels?.vfx;
      if (workstation && effect?.asset_id) this._primeEffect(workstation, effect, actor);
      const humanball = actor?.channels?.humanball;
      if (workstation && humanball?.asset_id) this._primeHumanball(humanball);
      const officeHumanball = actor?.channels?.office_humanball;
      if (workstation && officeHumanball?.asset_id) this._primeOfficeHumanball(officeHumanball);
      for (const placementId of actor.occluder_placement_ids || []) {
        const occluder = this._occluder(placementId);
        if (occluder) this._loadImage(occluder.url);
      }
    }
    return true;
  }

  _stateRows(nowMs) {
    if (!this.state) return [];
    const currentRows = Array.isArray(this.state.actors) ? this.state.actors : [];
    const previousById = new Map(
      (this.previousState?.actors || []).map((row) => [row.employee_id, row]),
    );
    const progress = this.previousState
      ? clamp((numberOr(nowMs) - numberOr(this.stateReceivedAt)) / this.interpolationDurationMs, 0, 1)
      : 1;
    return currentRows.map((row) => {
      const previous = previousById.get(row.employee_id);
      if (!previous || !validPoint(previous.ground_xy) || !validPoint(row.ground_xy)) return row;
      if (row.render_owner !== "walking_depth" || previous.render_owner !== "walking_depth") return row;
      return { ...row, ground_xy: interpolatePoint(previous.ground_xy, row.ground_xy, progress) };
    });
  }

  _characterRecord(row) {
    return this.manifest?.characters?.[row.character_id] || null;
  }

  _frameRule(frameId) {
    return this.manifest?.frame_rules?.[frameId] || null;
  }

  _primeCharacter(row) {
    const character = this._characterRecord(row);
    if (!character) return;
    this._loadImage(character.body_url);
    this._loadImage(character.face_url);
  }

  _drawNativeFrame(context, character, frameId, x, y) {
    const rule = this._frameRule(frameId);
    if (!rule || rule.kind !== "native") return false;
    const body = this._readyImage(character.body_url);
    const face = this._readyImage(character.face_url);
    if (!body || !face) return false;
    const origin = this.manifest.frame_profile?.origin || [5, 2];
    const bodyRule = rule.body;
    const faceRule = rule.face;
    const bodyX = x + integerOr(origin[0]) + integerOr(bodyRule.dst?.[0]);
    const bodyY = y + integerOr(origin[1]) + integerOr(bodyRule.dst?.[1]);
    const faceX = x + integerOr(origin[0]) + integerOr(faceRule.dst?.[0]);
    const faceY = y + integerOr(origin[1]) + integerOr(faceRule.dst?.[1]);
    if (!rule.special_split_body) {
      const [sx, sy, sw, sh] = bodyRule.src;
      const [fx, fy, fw, fh] = faceRule.src;
      context.drawImage(body, sx, sy, sw, sh, bodyX, bodyY, sw, sh);
      context.drawImage(face, fx, fy, fw, fh, faceX, faceY, fw, fh);
      return true;
    }
    const split = rule.split_body;
    if (!split) return false;
    const [sx, sy, sw] = bodyRule.src;
    const topHeight = integerOr(split.top_height);
    const fullHeight = integerOr(split.full_body_height);
    const shiftY = integerOr(split.shift_y);
    const [fx, fy, fw, fh] = faceRule.src;
    context.drawImage(body, sx, sy, sw, topHeight, bodyX, bodyY + shiftY, sw, topHeight);
    context.drawImage(face, fx, fy, fw, fh, faceX, faceY + shiftY, fw, fh);
    context.drawImage(
      body,
      sx,
      sy + topHeight,
      sw,
      fullHeight - topHeight,
      bodyX,
      bodyY + topHeight,
      sw,
      fullHeight - topHeight,
    );
    return true;
  }

  _drawCharacter(context, row, x, y) {
    const character = this._characterRecord(row);
    const frameId = row.frame_id;
    if (!character || !frameId) return false;
    this._primeCharacter(row);
    const rule = this._frameRule(frameId);
    if (!rule) return false;
    const [width, height] = this.manifest.frame_profile?.canvas || DEFAULT_CHARACTER_SIZE;
    const drawNative = (target, targetX, targetY, nativeFrameId) => this._drawNativeFrame(
      target,
      character,
      nativeFrameId,
      targetX,
      targetY,
    );
    if (rule.kind === "derived") {
      if (rule.transform !== "mirror_y") return false;
      context.save();
      context.translate(x + width, y);
      context.scale(-1, 1);
      const result = drawNative(context, 0, 0, rule.source_frame_id);
      context.restore();
      return result;
    }
    return drawNative(context, x, y, frameId);
  }

  _occluder(placementId) {
    return (this.manifest?.occluders || []).find(
      (row) => row.placement_id === placementId,
    ) || null;
  }

  _workstationRows(rows) {
    const result = new Map();
    for (const row of rows) {
      if (row?.render_owner === "work_seat" && row.visible && row.workstation_id) {
        result.set(row.workstation_id, row);
      }
    }
    return result;
  }

  _pcFrame(workstation, row) {
    const frames = workstation.pc_frames || [];
    if (!frames.length) return null;
    const channel = row?.channels?.pc;
    const index = integerOr(channel?.frame_index ?? row?.pc_frame_index, 0);
    return frames[((index % frames.length) + frames.length) % frames.length];
  }

  _pcFrameForRender(workstationId, workstation, row, component) {
    const selected = this._pcFrame(workstation, row);
    if (!selected) return component;

    // A seated actor changes the PC record at the animation boundary. Keep
    // the previous ready frame visible until the requested image is ready so
    // the canvas clear in render() cannot expose the desk/background for one
    // or more browser frames.
    if (row?.render_owner === "work_seat" && row.visible) {
      if (this._readyImage(selected.url)) {
        this.lastReadyPcFrames.set(workstationId, selected);
        return selected;
      }
      return this.lastReadyPcFrames.get(workstationId) || component;
    }
    return selected;
  }

  _primeEffect(workstation, channel, row) {
    const effect = this.manifest?.effects?.[channel.asset_id];
    if (!effect) return;
    const direction = String(row?.resolved_direction || workstation.direction || "NW").toUpperCase();
    const frames = effect.frames?.[direction] || effect.frames?.NW || [];
    const index = integerOr(channel.effect_frame_index, 0);
    const frame = frames.length ? frames[((index % frames.length) + frames.length) % frames.length] : null;
    if (frame) this._loadImage(frame.url);
  }

  _primeHumanball(channel) {
    const humanball = this.manifest?.humanballs?.[channel.asset_id]
      || this.manifest?.office_humanballs?.[channel.asset_id];
    if (humanball) this._loadImage(humanball.url);
  }

  _primeOfficeHumanball(channel) {
    const humanball = this.manifest?.office_humanballs?.[channel.asset_id];
    if (humanball) this._loadImage(humanball.url);
  }

  _dynamicEntries(rows) {
    const byWorkstation = this._workstationRows(rows);
    const entries = [];
    for (const workstationId of Object.keys(this.manifest?.workstations || {}).sort()) {
      const workstation = this.manifest.workstations[workstationId];
      const row = byWorkstation.get(workstationId);
      for (const component of workstation.components || []) {
        const record = component.role === "pc"
          ? this._pcFrameForRender(workstationId, workstation, row, component)
          : component;
        entries.push({
          layer: integerOr(component.layer),
          priority: component.role === "chair_foreground" ? 3 : 1,
          key: `${workstationId}:component:${component.role}`,
          kind: "component",
          record,
          x: integerOr(component.x_px),
          y: integerOr(component.y_px),
        });
      }
      if (!row || !row.visible) continue;
      const effect = row.channels?.vfx;
      if (effect?.asset_id) {
        this._primeEffect(workstation, effect, row);
        entries.push({
          layer: integerOr(workstation.effect_layer, 369),
          priority: 0,
          key: `${workstationId}:effect`,
          kind: "effect",
          workstation,
          row,
          channel: effect,
        });
      }
      entries.push({
        layer: integerOr(workstation.character_layer, 371),
        priority: 2,
        key: `${workstationId}:character:${row.employee_id}`,
        kind: "character",
        row,
        workstation,
      });
    }
    return entries.sort((left, right) => (
      left.layer - right.layer
      || left.priority - right.priority
      || left.key.localeCompare(right.key)
    ));
  }

  _drawRecord(context, record, x, y) {
    const image = this._readyImage(record?.url);
    if (!image) return false;
    context.drawImage(image, x, y);
    return true;
  }

  _drawEffect(context, entry) {
    const effect = this.manifest?.effects?.[entry.channel?.asset_id];
    if (!effect) return false;
    const direction = String(entry.row?.resolved_direction || entry.workstation.direction || "NW").toUpperCase();
    const frames = effect.frames?.[direction] || effect.frames?.NW || [];
    if (!frames.length) return false;
    const index = integerOr(entry.channel?.effect_frame_index, 0);
    const frame = frames[((index % frames.length) + frames.length) % frames.length];
    const image = this._readyImage(frame.url);
    if (!image) return false;
    const topLeft = this._characterTopLeft(entry.row, entry.workstation);
    const offset = entry.workstation.effect_world_offset || [0, 0];
    const x = topLeft[0] + integerOr(offset[0]);
    const y = topLeft[1] + integerOr(offset[1]);
    if (!frame.mirror_x) {
      context.drawImage(image, x, y);
      return true;
    }
    context.save();
    context.translate(x + image.width, y);
    context.scale(-1, 1);
    context.drawImage(image, 0, 0);
    context.restore();
    return true;
  }

  _characterTopLeft(row, workstation = null) {
    if (row?.render_owner === "work_seat") {
      const seat = workstation || this.manifest?.workstations?.[row.workstation_id];
      return seat?.character_top_left ? seat.character_top_left.map(numberOr) : null;
    }
    if (row?.render_owner === "walking_depth" && validPoint(row.ground_xy)) {
      const anchor = row.anchor_xy || DEFAULT_ANCHOR;
      return [numberOr(row.ground_xy[0]) - numberOr(anchor[0]), numberOr(row.ground_xy[1]) - numberOr(anchor[1])];
    }
    return null;
  }

  _ensureActorCanvas() {
    if (this.actorCanvas) return;
    const documentRef = this.canvas.ownerDocument || globalThis.document;
    if (!documentRef?.createElement) throw new Error("Canvas document is unavailable");
    this.actorCanvas = documentRef.createElement("canvas");
    this.actorCanvas.width = DEFAULT_CHARACTER_SIZE[0];
    this.actorCanvas.height = DEFAULT_CHARACTER_SIZE[1];
    this.actorCtx = this.actorCanvas.getContext("2d");
    if (!this.actorCtx) throw new Error("Actor canvas 2D context is unavailable");
    this.actorCtx.imageSmoothingEnabled = false;
  }

  _drawWalkingActor(context, row, seatedRows = []) {
    if (!row?.visible || row.render_owner !== "walking_depth") return false;
    const topLeft = this._characterTopLeft(row);
    if (!topLeft) return false;
    this._ensureActorCanvas();
    const [width, height] = this.manifest.frame_profile?.canvas || DEFAULT_CHARACTER_SIZE;
    if (this.actorCanvas.width !== width) this.actorCanvas.width = width;
    if (this.actorCanvas.height !== height) this.actorCanvas.height = height;
    this.actorCtx.imageSmoothingEnabled = false;
    this.actorCtx.clearRect(0, 0, width, height);
    if (!this._drawCharacter(this.actorCtx, row, 0, 0)) return false;
    this.actorCtx.save();
    this.actorCtx.globalCompositeOperation = "destination-out";
    for (const placementId of row.occluder_placement_ids || []) {
      const occluder = this._occluder(placementId);
      const image = this._readyImage(occluder?.url);
      if (!occluder || !image) continue;
      this.actorCtx.drawImage(
        image,
        integerOr(occluder.x_px) - topLeft[0],
        integerOr(occluder.y_px) - topLeft[1],
      );
    }

    // Work-seat characters are part of the static/work-seat pass, so a walker
    // must be masked by any seated character whose ground depth is closer to
    // the camera. Do this in the actor buffer instead of mixing groundY with
    // authored component layers; those are different depth systems.
    const walkingGroundY = validPoint(row.ground_xy)
      ? numberOr(row.ground_xy[1])
      : topLeft[1] + 31;
    const walkingBox = [topLeft[0], topLeft[1], topLeft[0] + width, topLeft[1] + height];
    for (const seated of seatedRows) {
      if (!seated?.visible || seated.render_owner !== "work_seat") continue;
      const seatedTopLeft = this._characterTopLeft(seated);
      if (!seatedTopLeft) continue;
      const seatedGroundY = seatedTopLeft[1] + 31;
      if (seatedGroundY <= walkingGroundY) continue;
      const seatedBox = [
        seatedTopLeft[0], seatedTopLeft[1],
        seatedTopLeft[0] + width, seatedTopLeft[1] + height,
      ];
      const overlaps = !(
        walkingBox[2] <= seatedBox[0]
        || walkingBox[0] >= seatedBox[2]
        || walkingBox[3] <= seatedBox[1]
        || walkingBox[1] >= seatedBox[3]
      );
      if (overlaps) {
        this._drawCharacter(
          this.actorCtx,
          seated,
          Math.round(seatedTopLeft[0] - topLeft[0]),
          Math.round(seatedTopLeft[1] - topLeft[1]),
        );
      }
    }

    this.actorCtx.restore();
    context.save();
    context.globalAlpha = clamp(numberOr(row.visibility_alpha, 1), 0, 1);
    context.drawImage(this.actorCanvas, Math.round(topLeft[0]), Math.round(topLeft[1]));
    context.restore();
    return true;
  }

  _drawHumanballs(context, rows) {
    this._drawHumanballChannel(context, rows, "humanball", "humanballs");
  }

  _drawOfficeHumanballs(context, rows) {
    this._drawHumanballChannel(context, rows, "office_humanball", "office_humanballs");
  }

  _drawHumanballChannel(context, rows, channelName, manifestKey) {
    for (const row of rows) {
      if (!row?.visible || row.render_owner !== "work_seat") continue;
      const channel = row.channels?.[channelName];
      const workstation = this.manifest?.workstations?.[row.workstation_id];
      const humanball = this.manifest?.[manifestKey]?.[channel?.asset_id]
        || (channelName === "humanball"
          ? this.manifest?.office_humanballs?.[channel?.asset_id]
          : null);
      if (!channel || !workstation || !humanball) continue;
      const frameIndex = integerOr(channel.humanball_frame_index, 0);
      const visibleFrameCount = Math.max(
        0,
        integerOr(humanball.visible_frame_count, 10),
      );
      // A recovery event can outlive the 12-frame HumanBall timeline. The
      // visual must remain hidden after its ten visible frames, never wrap to
      // the first icon frame while the same event is still active.
      if (frameIndex >= visibleFrameCount) continue;
      const offsets = workstation.humanball_offsets?.[workstation.direction] || [];
      const offset = offsets[((frameIndex % offsets.length) + offsets.length) % offsets.length];
      if (!offset) continue;
      const image = this._readyImage(humanball.url);
      if (!image) continue;
      const topLeft = this._characterTopLeft(row, workstation);
      if (!topLeft) continue;
      context.drawImage(image, topLeft[0] + integerOr(offset[0]), topLeft[1] + integerOr(offset[1]));
    }
  }

  _bubbleSpec(dialogue) {
    const bubbleId = BUBBLE_SIZES[dialogue?.bubble_id] ? dialogue.bubble_id : "BB3";
    return { id: bubbleId, values: BUBBLE_SIZES[bubbleId] };
  }

  _drawDialogue(context, rows) {
    const byId = new Map(rows.map((row) => [row.employee_id, row]));
    const order = this.state?.paint_order?.dialogue_bubbles || [];
    const ordered = [...order, ...rows.map((row) => row.employee_id)]
      .filter((id, index, source) => source.indexOf(id) === index)
      .map((id) => byId.get(id))
      .filter((row) => row?.dialogue?.visible && row.dialogue.text);
    for (const row of ordered) {
      const topLeft = this._characterTopLeft(row);
      if (!topLeft) continue;
      const dialogue = row.dialogue;
      const spec = this._bubbleSpec(dialogue);
      const [width, height, tailX, tailY] = spec.values;
      const offset = dialogue.offset_xy || [0, 0];
      const anchorX = topLeft[0] + 16 + integerOr(offset[0]);
      const bubbleX = anchorX - tailX;
      const bubbleY = topLeft[1] - 20 + integerOr(offset[1]);
      const opacity = clamp(numberOr(dialogue.opacity, 1), 0, 1);
      context.save();
      context.globalAlpha = opacity;
      context.fillStyle = "#f7f9ff";
      context.strokeStyle = "#2449bb";
      context.lineWidth = 1;
      if (typeof context.roundRect === "function") {
        context.beginPath();
        context.roundRect(bubbleX, bubbleY, width, height, 3);
        context.fill();
        context.stroke();
      } else {
        context.fillRect(bubbleX, bubbleY, width, height);
        context.strokeRect(bubbleX, bubbleY, width, height);
      }
      context.fillStyle = "#0c45fb";
      context.beginPath();
      context.moveTo(anchorX - 3, bubbleY + height - 1);
      context.lineTo(anchorX, bubbleY + height + 3);
      context.lineTo(anchorX + 3, bubbleY + height - 1);
      context.closePath();
      context.fill();
      context.font = "9px system-ui, sans-serif";
      context.textAlign = "center";
      context.textBaseline = "middle";
      const text = String(dialogue.text);
      const safeWidth = Math.max(8, width - 8);
      let fontSize = 9;
      while (fontSize > 4) {
        context.font = `${fontSize}px system-ui, sans-serif`;
        if (context.measureText(text).width <= safeWidth) break;
        fontSize -= 1;
      }
      context.save();
      context.beginPath();
      context.rect(bubbleX + 4, bubbleY + 2, safeWidth, Math.max(1, height - 4));
      context.clip();
      context.fillText(text, bubbleX + width / 2, bubbleY + height / 2);
      context.restore();
      context.restore();
    }
  }

  render(nowMs = this.now()) {
    if (this.destroyed || !this.manifest || !this.state) return false;
    const staticImage = this._readyImage(this.manifest.static_scene.url);
    if (!staticImage) return false;
    const context = this.ctx;
    const width = this.canvas.width;
    const height = this.canvas.height;
    context.imageSmoothingEnabled = false;
    context.clearRect(0, 0, width, height);
    context.drawImage(staticImage, 0, 0);
    const rows = this._stateRows(nowMs);
    const dynamicEntries = this._dynamicEntries(rows);
    const seatedRows = rows.filter((row) => row?.visible && row.render_owner === "work_seat");
    const byId = new Map(rows.map((row) => [row.employee_id, row]));
    const orderedIds = [
      ...(this.state.paint_order?.characters || []),
      ...rows.map((row) => row.employee_id),
    ].filter((id, index, source) => source.indexOf(id) === index);

    for (const entry of dynamicEntries) {
      if (entry.kind === "component") this._drawRecord(context, entry.record, entry.x, entry.y);
      else if (entry.kind === "effect") this._drawEffect(context, entry);
      else if (entry.kind === "character") {
        const topLeft = this._characterTopLeft(entry.row, entry.workstation);
        if (topLeft) this._drawCharacter(context, entry.row, topLeft[0], topLeft[1]);
      }
    }
    this._drawHumanballs(context, rows);
    this._drawOfficeHumanballs(context, rows);
    // Paint walking actors as a separate depth pass. paint_order.characters is
    // ground-Y ordered by the browser core, while static entries above retain
    // their authored manifest layers.
    for (const employeeId of orderedIds) {
      this._drawWalkingActor(context, byId.get(employeeId), seatedRows);
    }
    for (const overlay of this.manifest.overlays || []) {
      this._drawRecord(context, overlay, overlay.x_px, overlay.y_px);
    }
    this._drawDialogue(context, rows);
    return true;
  }

  destroy() {
    this.destroyed = true;
    this.state = null;
    this.previousState = null;
    this.imageCache.clear();
    this.lastReadyPcFrames.clear();
    this.manifest = null;
    this.manifestPromise = null;
    this.actorCanvas = null;
    this.actorCtx = null;
  }
}
