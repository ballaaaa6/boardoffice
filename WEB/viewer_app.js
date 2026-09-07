import { BrowserRuntimeCore } from "./runtime_simulation_core.js";
import { RuntimeCanvasRenderer } from "./runtime_canvas_renderer.js";

// DOM Elements
const canvas = document.getElementById("livingCanvas");
const stageWrapper = document.getElementById("stageWrapper");
const viewport = document.getElementById("viewport");
const loadingOverlay = document.getElementById("loadingOverlay");

// HUD Elements
const floorSelect = document.getElementById("floorSelect");
const currentFloorLabel = document.getElementById("currentFloorLabel");
const brandFloorBadge = document.getElementById("brandFloorBadge");
const virtualClockEl = document.getElementById("virtualClock");
const activeWorkersCountEl = document.getElementById("activeWorkersCount");
const playPauseBtn = document.getElementById("playPauseBtn");
const playPauseIcon = document.getElementById("playPauseIcon");
const playPauseText = document.getElementById("playPauseText");
const localeSelect = document.getElementById("localeSelect");
const speedBtns = document.querySelectorAll("[data-speed]");

// Inspector Elements
const inspectorPanel = document.getElementById("inspectorPanel");
const inspectorCloseBtn = document.getElementById("inspectorCloseBtn");
const inspectorActorName = document.getElementById("inspectorActorName");
const inspectorActorRole = document.getElementById("inspectorActorRole");
const inspectorActivity = document.getElementById("inspectorActivity");
const inspectorWorkstation = document.getElementById("inspectorWorkstation");
const inspectorStaminaVal = document.getElementById("inspectorStaminaVal");
const inspectorStaminaFill = document.getElementById("inspectorStaminaFill");
const inspectorThought = document.getElementById("inspectorThought");
const followActorBtn = document.getElementById("followActorBtn");
const avatarCanvas = document.getElementById("avatarCanvas");
const avatarCtx = avatarCanvas ? avatarCanvas.getContext("2d") : null;

// Quick Actions
const btnDemoTalk = document.getElementById("btnDemoTalk");
const btnDemoEffects = document.getElementById("btnDemoEffects");
const btnDemoCritical = document.getElementById("btnDemoCritical");
const btnReset = document.getElementById("btnReset");

// Zoom Tools
const zoomInBtn = document.getElementById("zoomInBtn");
const zoomOutBtn = document.getElementById("zoomOutBtn");
const zoomResetBtn = document.getElementById("zoomResetBtn");

// Simulation Engine State
let core = null;
let renderer = null;
let bootstrapData = null;
let manifestData = null;
let currentFloorId = "floor02";
let isSwitchingFloor = false;
let isPaused = false;
let speedMultiplier = 1;
let currentLocale = "th"; // default to Thai
let selectedActorId = null;
let isFollowingActor = false;
let lastRenderState = null;

// Canonical Speech Bubble Sprite Sheet & Presets (from CHARACTER/ASSETS/dialogue/fukidashi_base.png & bubble_presets.json)
const FUKIDASHI_BASE64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAMAAAAAoBAMAAABa5ejbAAAABGdBTUEAALGPC/xhBQAAAAFzUkdCAK7OHOkAAAAhUExURf///+Lt4vX39bO8s+ry6u707vj4+HuOfPL/8uzz7fD08H2BqFwAAAABdFJOUwBA5thmAAAACXBIWXMAAA7DAAAOwwHHb6hkAAABpElEQVRIx82VsWrDMBiEDzx4dlVK1iQvIEVJlGQr6RuEPkAolIwGDZ5NoHTP1Dlbn7JuCrWkSr8iFUNu+zlOJw36P6CQEQEIehyePGyJKiKOIugxX55b5xcPrxExiKC3554865/cdYlJTGN5FzaZJz/mhfnCIQpE/0LMogUTSXhTX964EcPqPSpJeEdf3irYfEYlCe/syxtPnmLxHJUkvJ0vb9zoPEyB4WP9EZUkvNOaDpwwf4pKEt52Tge2ENHzH+V92GSCDjDo2CqqWEOsK6XpgEIxipw/6nZRGzJb/jdvBlqOUjrbqnJmpqBFwN/L+je/r4zA8mfufKBxtvnhxZ5VjVKH/KbPL9/swGVuvhd2Y2ul7Lm7A8qQb3j6aAcuMzzSNUiF/FLRc2/Q54f9OjAXV0OYI0viagizrPO9TBUBAGc9IIGR7CYLZgkQnuYUrBIgfMwp2CRA+JxTsEhg5O4mC9YJED7lFMwTILzN+gcJEM76BzoBwiprF42uhnCbtYv8TBUeBF8AmyGXyQ6EDQQ3eTwoHSY7EDYQjEGkawyr8p/5LxspvhDRdGCxAAAAAElFTkSuQmCC";

const BUBBLE_PRESETS = {
  BB1: { crop: [0, 0, 71, 20], tail: [35, 19], safe: [4, 3, 67, 17] },
  BB2: { crop: [71, 0, 57, 20], tail: [28, 19], safe: [4, 3, 53, 17] },
  BB3: { crop: [128, 0, 41, 20], tail: [20, 19], safe: [4, 3, 37, 17] },
  BB4: { crop: [169, 2, 23, 18], tail: [11, 17], safe: [4, 3, 19, 15] },
  BB6: { crop: [41, 20, 49, 20], tail: [24, 19], safe: [4, 3, 45, 17] },
};

let fukidashiImg = null;

// Live Lifecycle Scheduling State (Matches Python live_start)
let actorIds = [];
let liveSpawnDueMs = {};
let liveBehaviorArmed = new Set();

// Viewport Transform State
let scale = 1.35;
let panX = 0;
let panY = 0;
let isDragging = false;
let dragStartX = 0;
let dragStartY = 0;

function updateTransform() {
  stageWrapper.style.transform = `translate(calc(-50% + ${panX}px), calc(-50% + ${panY}px)) scale(${scale})`;
}

// Fixed-Step Loop Parameters
const STEP_MS = 60;
const MAX_ACCUMULATOR_MS = 1000;
let lastWallTime = performance.now();
let accumulatorMs = 0;

/**
 * Prepares the authentic live-start snapshot matching Python live_start():
 * All actors begin off-map at home with home_recovery, waiting for staggered portal entry.
 */
function createLiveBundle(rawBootstrap) {
  const bundle = JSON.parse(JSON.stringify(rawBootstrap));
  const snapshot = bundle.initial_snapshot;
  const ids = Object.keys(snapshot.actor_snapshot.actors).sort();

  for (const actor of Object.values(snapshot.actor_snapshot.actors)) {
    actor.presence = "home";
    actor.activity = "home_recovery";
    actor.position = {
      floor_id: null,
      uv: null,
      ground_xy: null,
      route: null,
    };
    actor.conversation_phase = null;
    actor.behavior = {
      ...actor.behavior,
      next_event_due_ms: null,
      active_event: null,
      activity_started_ms: 0,
      activity_until_ms: 0,
      work_loop_elapsed_ms: 0,
      work_loop_count: 0,
      pending_home: false,
      pending_home_due_ms: null,
    };
    actor.stamina = {
      ...actor.stamina,
      current_milli: 100000,
      threshold_band: "normal",
      drain_remainder: 0,
    };
  }

  // Reset speech actors so greeting and work-start trigger naturally on portal entry
  for (const actor of Object.values(snapshot.speech_snapshot.actors)) {
    actor.greeting_due_ms = null;
    actor.greeting_emitted = false;
    actor.work_start_due_ms = null;
    actor.work_start_emitted = false;
    actor.solo_next_due_ms = null;
    actor.pair_next_due_ms = null;
    actor.speech_phase = "idle";
  }

  return { bundle, ids };
}

function startLiveSimulation() {
  const { bundle, ids } = createLiveBundle(bootstrapData);
  actorIds = ids;

  // Staggered spawn: each employee enters through the portal every 1200ms
  liveSpawnDueMs = {};
  actorIds.forEach((id, index) => {
    liveSpawnDueMs[id] = index * 1200;
  });
  liveBehaviorArmed.clear();

  core = new BrowserRuntimeCore({
    bundle,
    floorId: currentFloorId,
    seed: `viewer_seed_${Date.now()}`,
  });

  // Inject locale into speech reducer step
  const originalSpeechStep = core.speechReducer.step.bind(core.speechReducer);
  core.speechReducer.step = function (snapshot, options = {}) {
    options.dialogueLocale = currentLocale;
    return originalSpeechStep(snapshot, options);
  };

  // Wrap startSession to emit non-blocking start_talk_session command for solo/self_talk
  // Matching Python CentralGameCore speech overlay behavior (prevents employee freeze)
  const originalStartSession = core.speechReducer.startSession.bind(core.speechReducer);
  core.speechReducer.startSession = function (snapshot, actorSnapshot, request, plan, timestampMs, events, dialogueLocale) {
    const result = originalStartSession(snapshot, actorSnapshot, request, plan, timestampMs, events, dialogueLocale);
    if (result && result.session && result.session.kind === "solo") {
      const session = result.session;
      for (const employeeId of session.participants) {
        result.talkCommands.push({
          type: "start_talk_session",
          employee_id: employeeId,
          session_id: session.session_id,
          mode: session.mode,
          role: "initiator",
          partner_id: null,
          recovery_owner: true,
          effective_at_ms: session.movement_started_ms,
          talk_start_at_ms: session.movement_arrival_ms,
          talk_end_at_ms: session.fade_end_ms,
          return_start_at_ms: session.fade_end_ms + (session.emotion_hold_ms || 0),
          emotion: session.emotion_outcome,
          emotion_until_at_ms: session.emotion_outcome ? session.fade_end_ms + (session.emotion_hold_ms || 0) : null,
          endpoint_uv: null,
          endpoint_facing: null,
          route_committed: false,
        });
      }
    }
    return result;
  };

  // Canonical walking-depth front-edge profiles across floors (from walking_depth_profiles.json)
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

  function frontEdgeYAtX(frontEdge, worldX) {
    const points = [...frontEdge].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    const x = Math.min(Math.max(worldX, points[0][0]), points[points.length - 1][0]);
    for (let i = 0; i < points.length - 1; i++) {
      const [x0, y0] = points[i];
      const [x1, y1] = points[i + 1];
      if (x0 <= x && x <= x1) {
        if (x1 === x0) return Math.max(y0, y1);
        const progress = (x - x0) / (x1 - x0);
        return y0 + (y1 - y0) * progress;
      }
    }
    return points[points.length - 1][1];
  }

  function resolveActorOccluderIds(actor, occluders) {
    if (actor.render_owner !== "walking_depth") return [];
    if (!actor.ground_xy || actor.ground_xy.length !== 2) return [];
    const [gx, gy] = actor.ground_xy;
    const ax0 = Math.round(gx - 16);
    const ay0 = Math.round(gy - 31);
    const ax1 = ax0 + 32;
    const ay1 = ay0 + 42;

    const depthFrontEdges = DEPTH_PROFILES_BY_FLOOR[currentFloorId] || DEPTH_PROFILES_DEFAULT;

    const ids = [];
    for (const occ of occluders) {
      // 1. Exact depth test matching Python WalkingDepthCore.occluders_in_front
      let inFront = false;
      if (occ.always_foreground) {
        inFront = true;
      } else {
        const edge = depthFrontEdges[occ.placement_id];
        const anchorY = edge ? frontEdgeYAtX(edge, gx) : occ.depth_anchor_y_px;
        if (anchorY != null && anchorY > gy) {
          inFront = true;
        }
      }
      if (!inFront) continue;

      // 2. Bounding box overlap test matching Python WalkingDepthCore._mask_character_by_world_occluders
      const ox0 = occ.x_px;
      const oy0 = occ.y_px;
      const ox1 = ox0 + occ.width;
      const oy1 = oy0 + occ.height;
      const ix0 = Math.max(ax0, ox0);
      const iy0 = Math.max(ay0, oy0);
      const ix1 = Math.min(ax1, ox1);
      const iy1 = Math.min(ay1, oy1);
      if (ix0 < ix1 && iy0 < iy1) {
        ids.push(occ.placement_id);
      }
    }
    return ids;
  }

  // Wrap renderState to compute dynamic occluder IDs and ground-Y paint_order
  // Matching Python CentralGameCore and WalkingDepthCore exactly
  const originalRenderState = core.renderState.bind(core);
  core.renderState = function (atMs = core.clockMs) {
    const state = originalRenderState(atMs);
    const occluders = manifestData?.occluders || [];

    for (const actor of state.actors || []) {
      actor.occluder_placement_ids = resolveActorOccluderIds(actor, occluders);
    }

    // Exact Python CentralGameCore paint_order (sorts walking actors by ground Y)
    const actorsList = state.actors || [];
    state.paint_order = {
      characters: [...actorsList]
        .sort((a, b) => {
          const aGround = a.ground_xy;
          const bGround = b.ground_xy;
          const aHas = aGround ? 0 : 1;
          const bHas = bGround ? 0 : 1;
          if (aHas !== bHas) return aHas - bHas;
          const ay = aGround ? aGround[1] : 0;
          const by = bGround ? bGround[1] : 0;
          if (ay !== by) return ay - by;
          const aOrder = a.assignment_order ?? 0;
          const bOrder = b.assignment_order ?? 0;
          if (aOrder !== bOrder) return aOrder - bOrder;
          return String(a.employee_id).localeCompare(String(b.employee_id));
        })
        .map((a) => a.employee_id),
      dialogue_bubbles: [...actorsList]
        .filter((a) => a.dialogue?.visible)
        .sort((a, b) => (
          (a.dialogue?.turn_index ?? 0) - (b.dialogue?.turn_index ?? 0)
          || String(a.employee_id).localeCompare(String(b.employee_id))
        ))
        .map((a) => a.employee_id),
    };

    // Conversational Facing & Seated Host Turn-Side Poses (Matching Python conversation presentation)
    const activeSessions = Object.values(core.state.speech_snapshot?.active_sessions || {});
    for (const session of activeSessions) {
      const bubbleStart = session.bubble_start_ms || 0;
      const fadeEnd = session.fade_end_ms || (bubbleStart + 4300);
      const inTalkWindow = atMs >= bubbleStart && atMs < fadeEnd;

      if (session.mode === "seated_host") {
        // 1. Host turns toward visitor
        const hostId = session.partner_id || session.conversation_plan?.host_employee_id;
        const hostActor = state.actors.find((a) => a.employee_id === hostId);
        const hostTurn = session.conversation_plan?.spot?.selected_side?.side
          || session.spot?.selected_side?.side
          || "turn_side_ne";

        if (hostActor && hostActor.action === "work" && inTalkWindow) {
          hostActor.subaction = hostTurn;
          hostActor.resolved_subaction = hostTurn;
          const char = core.bundle.characters?.[hostActor.character_id];
          const ref = char?.frame_refs?.find((r) => (
            r.action === "work"
            && r.direction === hostActor.direction
            && r.subaction === hostTurn
          ));
          if (ref && ref.frame_ids?.length) {
            const sourceActor = core.state.actor_snapshot?.actors?.[hostId];
            const workLoopElapsed = Number(sourceActor?.behavior?.work_loop_elapsed_ms ?? (atMs % 720));
            const frameIndex = Math.floor(workLoopElapsed / 360) % ref.frame_ids.length;
            hostActor.character_frame_count = ref.frame_ids.length;
            hostActor.character_frame_index = frameIndex;
            hostActor.frame_index = frameIndex;
            hostActor.frame_id = ref.frame_ids[frameIndex];
            hostActor.animation_clock_ms = frameIndex * 360;
          }
        }

        // 2. Visitor stands at talk spot and faces host
        const visitorId = session.initiator_id || session.conversation_plan?.visitor_employee_id;
        const visitorActor = state.actors.find((a) => a.employee_id === visitorId);
        const visitorFacing = session.conversation_plan?.facing_by_actor?.[visitorId]
          || session.conversation_plan?.spot?.selected_side?.visitor_idle_direction
          || session.spot?.selected_side?.visitor_idle_direction
          || "SW";

        if (visitorActor && visitorFacing && visitorActor.route_phase === "talk_hold") {
          visitorActor.direction = visitorFacing;
          visitorActor.resolved_direction = visitorFacing;
          if (visitorActor.action !== "happy" && visitorActor.action !== "sad") {
            const char = core.bundle.characters?.[visitorActor.character_id];
            const ref = char?.frame_refs?.find((r) => (
              r.action === "idle"
              && r.direction === visitorFacing
            )) || char?.frame_refs?.find((r) => (
              r.action === visitorActor.action
              && r.direction === visitorFacing
            ));
            if (ref && ref.frame_ids?.length) {
              const visitorRoute = core.state.actor_snapshot?.actors?.[visitorId]?.position?.route;
              const routeElapsed = Number(visitorRoute?.elapsed_ms ?? Math.max(0, atMs - bubbleStart));
              const frameIndex = Math.floor(Math.max(0, routeElapsed) / 360) % ref.frame_ids.length;
              visitorActor.character_frame_count = ref.frame_ids.length;
              visitorActor.character_frame_index = frameIndex;
              visitorActor.frame_index = frameIndex;
              visitorActor.frame_id = ref.frame_ids[frameIndex];
              visitorActor.animation_clock_ms = frameIndex * 360;
            }
          }
        }
      } else if (session.mode === "standing_pair") {
        // Both participants face each other
        for (const empId of session.participants || []) {
          const actor = state.actors.find((a) => a.employee_id === empId);
          const facing = session.conversation_plan?.facing_by_actor?.[empId];
          if (actor && facing && actor.route_phase === "talk_hold") {
            actor.direction = facing;
            actor.resolved_direction = facing;
            if (actor.action !== "happy" && actor.action !== "sad") {
              const char = core.bundle.characters?.[actor.character_id];
              const ref = char?.frame_refs?.find((r) => (
                r.action === "idle"
                && r.direction === facing
              )) || char?.frame_refs?.find((r) => (
                r.action === actor.action
                && r.direction === facing
              ));
              if (ref && ref.frame_ids?.length) {
                const actorRoute = core.state.actor_snapshot?.actors?.[empId]?.position?.route;
                const routeElapsed = Number(actorRoute?.elapsed_ms ?? Math.max(0, atMs - bubbleStart));
                const frameIndex = Math.floor(Math.max(0, routeElapsed) / 360) % ref.frame_ids.length;
                actor.character_frame_count = ref.frame_ids.length;
                actor.character_frame_index = frameIndex;
                actor.frame_index = frameIndex;
                actor.frame_id = ref.frame_ids[frameIndex];
                actor.animation_clock_ms = frameIndex * 360;
              }
            }
          }
        }
      } else if (session.mode === "ceo_front") {
        // Visitor stands in front of CEO desk and faces CEO
        const visitorId = session.initiator_id || session.participants?.[0];
        const visitorActor = state.actors.find((a) => a.employee_id === visitorId);
        const visitorFacing = session.conversation_plan?.facing_by_actor?.[visitorId]
          || session.spot?.endpoint_facing
          || "NW";
        if (visitorActor && visitorFacing && visitorActor.route_phase === "talk_hold") {
          visitorActor.direction = visitorFacing;
          visitorActor.resolved_direction = visitorFacing;
          if (visitorActor.action !== "happy" && visitorActor.action !== "sad") {
            const char = core.bundle.characters?.[visitorActor.character_id];
            const ref = char?.frame_refs?.find((r) => (
              r.action === "idle"
              && r.direction === visitorFacing
            ));
            if (ref && ref.frame_ids?.length) {
              const visitorRoute = core.state.actor_snapshot?.actors?.[visitorId]?.position?.route;
              const routeElapsed = Number(visitorRoute?.elapsed_ms ?? Math.max(0, atMs - bubbleStart));
              const frameIndex = Math.floor(Math.max(0, routeElapsed) / 360) % ref.frame_ids.length;
              visitorActor.character_frame_count = ref.frame_ids.length;
              visitorActor.character_frame_index = frameIndex;
              visitorActor.frame_index = frameIndex;
              visitorActor.frame_id = ref.frame_ids[frameIndex];
              visitorActor.animation_clock_ms = frameIndex * 360;
            }
          }
        }
      }
    }

    return state;
  };

  accumulatorMs = 0;
  lastWallTime = performance.now();
}

async function switchFloor(floorId) {
  if (!floorId || (floorId === currentFloorId && core && !isSwitchingFloor)) return;
  isSwitchingFloor = true;
  currentFloorId = floorId;

  // Update UI indicators
  if (floorSelect && floorSelect.value !== floorId) {
    floorSelect.value = floorId;
  }
  if (currentFloorLabel) {
    const opt = floorSelect?.selectedOptions?.[0];
    const labelText = opt ? opt.textContent.replace(/ \(.*\)/, '') : `Floor ${floorId.replace('floor', '')}`;
    currentFloorLabel.textContent = labelText;
    if (brandFloorBadge) brandFloorBadge.textContent = labelText;
  }

  // Show loading overlay
  loadingOverlay.classList.remove("hidden");
  const loadingText = document.querySelector(".loading-text");
  if (loadingText) loadingText.textContent = `Loading ${floorId.toUpperCase()}...`;

  try {
    deselectActor();

    const bootstrapUrl = `./floors/${floorId}/bootstrap.json`;
    const manifestUrl = `./floors/${floorId}/manifest.json`;

    const [bootstrap, manifest] = await Promise.all([
      fetch(bootstrapUrl).then((r) => {
        if (!r.ok) {
          if (floorId === "floor02") return fetch("./runtime_simulation_bootstrap.json").then((res) => res.json());
          throw new Error(`Bootstrap HTTP ${r.status}`);
        }
        return r.json();
      }),
      fetch(manifestUrl).then((r) => {
        if (!r.ok) {
          if (floorId === "floor02") return fetch("./runtime_render_manifest.json").then((res) => res.json());
          throw new Error(`Manifest HTTP ${r.status}`);
        }
        return r.json();
      }),
    ]);

    bootstrapData = bootstrap;
    manifestData = manifest;

    // Reload renderer manifest
    renderer.manifest = null;
    renderer.manifestPromise = null;
    renderer.manifestUrl = manifestUrl;
    renderer.previousState = null;
    renderer.state = null;
    await renderer.loadManifest();

    // Update URL query parameter
    const url = new URL(window.location.href);
    url.searchParams.set("floor", floorId);
    window.history.replaceState({}, "", url.toString());

    // Restart simulation on new floor
    startLiveSimulation();

    // Initial frame
    const initialResult = core.step(STEP_MS);
    lastRenderState = core.renderState();
    renderer.setState(lastRenderState);
    renderer.render(performance.now());

    // Reset pan/zoom and update HUD
    panX = 0;
    panY = 0;
    scale = 1.35;
    updateTransform();
    updateHUD();

    loadingOverlay.classList.add("hidden");
    isSwitchingFloor = false;
  } catch (err) {
    isSwitchingFloor = false;
    console.error(`Failed to switch to ${floorId}:`, err);
    if (loadingText) loadingText.textContent = `Error loading ${floorId}: ${err.message}`;
  }
}

async function init() {
  try {
    // Populate floor select from ./floors/index.json
    try {
      const floorsIndexRes = await fetch("./floors/index.json");
      if (floorsIndexRes.ok) {
        const floorsList = await floorsIndexRes.json();
        if (floorSelect && Array.isArray(floorsList) && floorsList.length > 0) {
          floorSelect.innerHTML = "";
          for (const f of floorsList) {
            const opt = document.createElement("option");
            opt.value = f.floor_id;
            opt.textContent = `${f.name} (${f.employee_count} workers)`;
            floorSelect.appendChild(opt);
          }
        }
      }
    } catch (e) {
      console.warn("Could not load floors/index.json:", e);
    }

    // Check URL param ?floor=floorXX
    const urlParams = new URLSearchParams(window.location.search);
    const requestedFloor = urlParams.get("floor");
    if (requestedFloor) {
      currentFloorId = requestedFloor;
    }
    if (floorSelect) {
      floorSelect.value = currentFloorId;
    }
    if (currentFloorLabel) {
      const selectedOpt = floorSelect?.selectedOptions?.[0];
      const labelText = selectedOpt ? selectedOpt.textContent.replace(/ \(.*\)/, '') : `Floor ${currentFloorId.replace('floor', '')}`;
      currentFloorLabel.textContent = labelText;
      if (brandFloorBadge) brandFloorBadge.textContent = labelText;
    }

    const bootstrapUrl = `./floors/${currentFloorId}/bootstrap.json`;
    const manifestUrl = `./floors/${currentFloorId}/manifest.json`;

    const [bootstrap, manifest] = await Promise.all([
      fetch(bootstrapUrl).then((r) => {
        if (!r.ok) {
          if (currentFloorId === "floor02") return fetch("./runtime_simulation_bootstrap.json").then((res) => res.json());
          throw new Error(`Bootstrap HTTP ${r.status}`);
        }
        return r.json();
      }),
      fetch(manifestUrl).then((r) => {
        if (!r.ok) {
          if (currentFloorId === "floor02") return fetch("./runtime_render_manifest.json").then((res) => res.json());
          throw new Error(`Manifest HTTP ${r.status}`);
        }
        return r.json();
      }),
    ]);

    bootstrapData = bootstrap;
    manifestData = manifest;

    // Preload authentic speech bubble sprite sheet (CHARACTER/ASSETS/dialogue/fukidashi_base.png)
    fukidashiImg = new Image();
    fukidashiImg.src = FUKIDASHI_BASE64;
    await new Promise((resolve) => {
      if (fukidashiImg.complete) resolve();
      else fukidashiImg.onload = () => resolve();
    });

    // Instantiate Renderer
    renderer = new RuntimeCanvasRenderer({
      canvas,
      manifestUrl,
    });
    await renderer.loadManifest();

    // Attach floor selection listener
    if (floorSelect) {
      floorSelect.addEventListener("change", (e) => {
        switchFloor(e.target.value);
      });
    }

    // Override _drawDialogue to render authentic fukidashi_base pixel sprites and #0c45fb text
    renderer._drawDialogue = function (context, rows) {
      const byId = new Map(rows.map((row) => [row.employee_id, row]));
      const order = this.state?.paint_order?.dialogue_bubbles || [];
      const ordered = [...order, ...rows.map((row) => row.employee_id)]
        .filter((id, index, source) => source.indexOf(id) === index)
        .map((id) => byId.get(id))
        .filter((row) => row?.dialogue?.visible && row.dialogue.text);

      const BUBBLE_ORDER = ["BB4", "BB3", "BB6", "BB2", "BB1"];

      for (const row of ordered) {
        const topLeft = this._characterTopLeft(row);
        if (!topLeft) continue;
        const dialogue = row.dialogue;
        const text = String(dialogue.text || "").trim();
        if (!text) continue;

        context.font = '9px system-ui, -apple-system, "Segoe UI", sans-serif';
        const textMetrics = context.measureText(text);
        const textW = Math.ceil(textMetrics.width);

        // Find the smallest allowed bubble that fits the actual measured width
        let assignedBubbleId = dialogue.bubble_id;
        let preset = BUBBLE_PRESETS[assignedBubbleId] || BUBBLE_PRESETS.BB1;
        let safeW = preset.safe[2] - preset.safe[0];

        // If text exceeds currently assigned bubble, upgrade to the smallest allowed bubble that fits
        if (textW > safeW) {
          assignedBubbleId = null;
          for (const bid of BUBBLE_ORDER) {
            const p = BUBBLE_PRESETS[bid];
            const sw = p.safe[2] - p.safe[0];
            if (textW <= sw) {
              assignedBubbleId = bid;
              preset = p;
              safeW = sw;
              break;
            }
          }
        }

        // If text exceeds all allowed bubbles (maximum safe width is 63px in BB1),
        // reject it: never draw clipped/overflowing text!
        if (!assignedBubbleId || textW > safeW) {
          continue;
        }

        const [cropX, cropY, width, height] = preset.crop;
        const [tailX, tailY] = preset.tail;
        const [safeX0, safeY0, safeX1, safeY1] = preset.safe;
        const offset = dialogue.offset_xy || [0, 0];
        const anchorX = topLeft[0] + 16 + Math.trunc(Number(offset[0]) || 0);
        const bubbleX = anchorX - tailX;
        const bubbleY = topLeft[1] - 20 + Math.trunc(Number(offset[1]) || 0);
        const opacity = Math.max(0, Math.min(1, dialogue.opacity != null ? Number(dialogue.opacity) : 1));

        context.save();
        context.globalAlpha = opacity;
        context.imageSmoothingEnabled = false;

        if (fukidashiImg && fukidashiImg.complete) {
          context.drawImage(fukidashiImg, cropX, cropY, width, height, bubbleX, bubbleY, width, height);
        } else {
          context.fillStyle = "#f7f9ff";
          context.strokeStyle = "#2449bb";
          context.lineWidth = 1;
          context.fillRect(bubbleX, bubbleY, width, height);
          context.strokeRect(bubbleX, bubbleY, width, height);
        }

        const safeBoxW = Math.max(8, safeX1 - safeX0);
        const safeBoxH = Math.max(8, safeY1 - safeY0);
        const centerX = bubbleX + (safeX0 + safeX1) / 2;
        const centerY = bubbleY + (safeY0 + safeY1) / 2;

        context.save();
        context.beginPath();
        context.rect(bubbleX + safeX0, bubbleY + safeY0, safeBoxW, safeBoxH);
        context.clip();
        context.fillStyle = "#0c45fb";
        context.textAlign = "center";
        context.textBaseline = "middle";
        context.fillText(text, centerX, centerY);
        context.restore();

        context.restore();
      }
    };

    // Start Live Simulation with authentic Home -> Portal -> Desk lifecycle
    startLiveSimulation();

    // Step first tick to populate initial frame
    const initialResult = core.step(STEP_MS);
    lastRenderState = core.renderState();
    renderer.setState(lastRenderState);
    renderer.render(performance.now());

    // Hide Loading Screen
    loadingOverlay.classList.add("hidden");

    // Launch Fixed-step Animation Loop
    lastWallTime = performance.now();
    requestAnimationFrame(simulationLoop);
  } catch (err) {
    console.error("Initialization error:", err);
    document.querySelector(".loading-text").textContent = `Error: ${err.message}`;
  }
}

function simulationLoop(now) {
  requestAnimationFrame(simulationLoop);

  const deltaWallMs = (now - lastWallTime) * speedMultiplier;
  lastWallTime = now;

  if (!isPaused && core && !isSwitchingFloor) {
    accumulatorMs = Math.min(accumulatorMs + deltaWallMs, MAX_ACCUMULATOR_MS);
    while (accumulatorMs >= STEP_MS) {
      const nowMs = core.clockMs;
      const actorCommands = [];
      const returnRequestedThisTick = new Set();

      // 1. Ready return commands (staggered initial spawn from portal)
      for (const employeeId of actorIds) {
        const initialDue = liveSpawnDueMs[employeeId];
        if (initialDue !== undefined && nowMs >= initialDue) {
          actorCommands.push({ type: "request_return", employee_id: employeeId });
          returnRequestedThisTick.add(employeeId);
          delete liveSpawnDueMs[employeeId];
        }
      }

      // 2. Return from home recovery when fatigue rest completes
      for (const [employeeId, actor] of Object.entries(core.state.actor_snapshot.actors)) {
        if (actor.presence === "home" && actor.activity === "home_recovery") {
          if (liveSpawnDueMs[employeeId] === undefined && !returnRequestedThisTick.has(employeeId)) {
            const readyAt = actor.behavior?.activity_until_ms;
            if (readyAt != null && readyAt <= nowMs) {
              actorCommands.push({ type: "request_return", employee_id: employeeId });
              returnRequestedThisTick.add(employeeId);
            }
          }
        }
      }

      // 3. Talk Queue Timeout Safeguard (matching Python CentralGameCore TALK_QUEUE_TIMEOUT_MS = 30000)
      // If actor was queued for talk but no talk route was assigned within 30000ms, cancel talk and resume work
      for (const actor of Object.values(core.state.actor_snapshot.actors)) {
        if (
          actor.presence === "present"
          && actor.activity === "talking"
          && actor.conversation_phase === "talk_pending"
          && !actor.behavior?.talk
        ) {
          const started = actor.behavior?.activity_started_ms || nowMs;
          if (nowMs - started >= 30000) {
            actor.activity = "working";
            actor.conversation_phase = null;
            if (actor.behavior) {
              actor.behavior.active_event = null;
              actor.behavior.talk = null;
              actor.behavior.activity_started_ms = nowMs;
              actor.behavior.activity_until_ms = null;
              actor.behavior.next_event_due_ms = nowMs + 4000;
            }
            core.speechReducer.applyCommand(core.state.speech_snapshot, { type: "cancel_talk", employee_id: actor.employee_id }, nowMs);
          }
        }
      }

      // 4. Arm live behavior timers for seated working actors (triggers talk & events)
      for (let index = 0; index < actorIds.length; index++) {
        const employeeId = actorIds[index];
        const actor = core.state.actor_snapshot.actors[employeeId];
        if (
          actor.presence === "present"
          && actor.activity === "working"
          && actor.stamina?.threshold_band !== "critical"
        ) {
          const behavior = actor.behavior;
          if (!behavior.active_event && !behavior.talk) {
            const due = behavior.next_event_due_ms;
            if (!liveBehaviorArmed.has(employeeId)) {
              behavior.next_event_due_ms = nowMs + 3600 + (index % 5) * 1200;
              liveBehaviorArmed.add(employeeId);
            } else if (due == null || due - nowMs > 12000) {
              behavior.next_event_due_ms = nowMs + 6000 + (index % 5) * 1200;
            }
          }
        }
      }

      core.step(STEP_MS, { actorCommands });
      accumulatorMs -= STEP_MS;
    }

    lastRenderState = core.renderState();
    if (lastRenderState) {
      renderer.setState(lastRenderState);
    }
  }

  if (renderer) {
    renderer.render(now);
  }

  updateHUD();
  updateInspector();
  updateFollowCamera();
}

// Virtual Clock & HUD updates
function updateHUD() {
  if (!lastRenderState || !core) return;

  const clockMs = core.clockMs || 0;
  // Office hours start at 09:00:00 AM
  const totalSeconds = Math.floor(clockMs / 1000);
  const startHour = 9;
  const currentHour = (startHour + Math.floor(totalSeconds / 3600)) % 24;
  const currentMin = Math.floor((totalSeconds % 3600) / 60);
  const currentSec = totalSeconds % 60;
  const pad = (n) => String(n).padStart(2, "0");
  const ampm = currentHour >= 12 ? "PM" : "AM";
  const displayHour = currentHour % 12 || 12;

  virtualClockEl.textContent = `${pad(displayHour)}:${pad(currentMin)}:${pad(currentSec)} ${ampm}`;

  // Count active workers in office
  const actors = lastRenderState.actors || [];
  const activeCount = actors.filter((a) => a.visible && a.presence !== "home").length;
  activeWorkersCountEl.textContent = `${activeCount} / ${actors.length}`;
}

// Character Hit-detection on Canvas
function getCanvasCoords(event) {
  const rect = canvas.getBoundingClientRect();
  const scaleX = canvas.width / rect.width;
  const scaleY = canvas.height / rect.height;
  return {
    x: (event.clientX - rect.left) * scaleX,
    y: (event.clientY - rect.top) * scaleY,
  };
}

function selectActor(employeeId) {
  selectedActorId = employeeId;
  inspectorPanel.classList.add("open");
  updateInspector(true);
}

function deselectActor() {
  selectedActorId = null;
  isFollowingActor = false;
  followActorBtn.classList.remove("active");
  inspectorPanel.classList.remove("open");
}

function updateInspector(forceUpdateAvatar = false) {
  if (!selectedActorId || !lastRenderState) return;

  const actor = (lastRenderState.actors || []).find((a) => a.employee_id === selectedActorId);
  if (!actor) return;

  const empMetadata = bootstrapData?.employees?.[selectedActorId] || {};
  const isCeo = actor.workstation_id === "ceo";

  inspectorActorName.textContent = isCeo
    ? "CEO (Executive)"
    : `${selectedActorId.replace("EMP_W1_", "Worker #")}`;
  inspectorActorRole.textContent = isCeo
    ? "Chief Executive Officer"
    : (empMetadata.role || "Office Employee");
  inspectorWorkstation.textContent = actor.workstation_id
    ? `Station: ${actor.workstation_id.toUpperCase()}`
    : "No Assigned Desk";

  // Activity presentation
  let activityLabel = "Normal Work";
  if (actor.presence === "home") {
    activityLabel = "At Home (Resting)";
  } else if (actor.channels?.vfx?.asset_id) {
    activityLabel = `Effect (VFX): ${actor.channels.vfx.asset_id}`;
  } else if (actor.channels?.humanball?.asset_id) {
    activityLabel = `Popup (HumanBall): ${actor.channels.humanball.asset_id}`;
  } else if (actor.action === "move") {
    if (actor.route_phase === "to_portal" || actor.route_phase === "portal_exit") {
      activityLabel = "Leaving to go Home";
    } else if (actor.route_phase === "talk_outbound") {
      activityLabel = "Walking to Colleague (Talk)";
    } else if (actor.route_phase === "talk_return") {
      activityLabel = "Returning to Desk";
    } else {
      activityLabel = "Walking to Desk";
    }
  } else if (actor.speech_mode && actor.speech_mode !== "idle") {
    activityLabel = `Talking (${actor.speech_mode})`;
  } else if (actor.action === "happy") {
    activityLabel = "Happy / Motivated";
  } else if (actor.action === "sad") {
    activityLabel = "Disappointed / Tired";
  }
  inspectorActivity.textContent = activityLabel;

  // Stamina Gauge
  const rawStamina = actor.stamina?.stamina_milli ?? 100000;
  const staminaPercent = Math.max(0, Math.min(100, Math.round(rawStamina / 1000)));
  inspectorStaminaVal.textContent = `${staminaPercent}%`;
  inspectorStaminaFill.style.width = `${staminaPercent}%`;

  inspectorStaminaFill.className = "stamina-fill";
  if (staminaPercent <= 20) {
    inspectorStaminaFill.classList.add("danger");
  } else if (staminaPercent <= 50) {
    inspectorStaminaFill.classList.add("warning");
  }

  // Thought / Bubble status (Authentic dialogue emitted by simulation)
  if (actor.dialogue?.visible && actor.dialogue?.text) {
    inspectorThought.textContent = `[${actor.dialogue.bubble_id || "BB"}] "${actor.dialogue.text}"`;
  } else {
    inspectorThought.textContent = currentLocale === "th"
      ? "— ไม่มีบทสนทนาขณะนี้ —"
      : "— No active dialogue —";
  }

  // Render character mini-avatar on preview canvas
  if (avatarCtx && renderer) {
    avatarCtx.clearRect(0, 0, avatarCanvas.width, avatarCanvas.height);
    avatarCtx.imageSmoothingEnabled = false;
    renderer._drawCharacter(
      avatarCtx,
      { character_id: actor.character_id, frame_id: actor.frame_id || "M1" },
      2,
      2,
    );
  }
}

// Camera Follow Mode
function updateFollowCamera() {
  if (!isFollowingActor || !selectedActorId || !lastRenderState) return;

  const actor = (lastRenderState.actors || []).find((a) => a.employee_id === selectedActorId);
  if (!actor || !actor.ground_xy) return;

  // Target center in canvas pixels: center of stage is (300, 300)
  const targetX = (300 - actor.ground_xy[0]) * scale;
  const targetY = (300 - actor.ground_xy[1]) * scale;

  // Smooth lerp
  panX += (targetX - panX) * 0.08;
  panY += (targetY - panY) * 0.08;
  updateTransform();
}

// Event Listeners: Pan and Zoom
viewport.addEventListener("mousedown", (e) => {
  if (e.target.closest(".inspector-panel") || e.target.closest(".stage-tools")) {
    return;
  }
  isDragging = true;
  dragStartX = e.clientX - panX;
  dragStartY = e.clientY - panY;
});

window.addEventListener("mousemove", (e) => {
  if (!isDragging) return;
  isFollowingActor = false;
  followActorBtn.classList.remove("active");
  panX = e.clientX - dragStartX;
  panY = e.clientY - dragStartY;
  updateTransform();
});

window.addEventListener("mouseup", () => {
  isDragging = false;
});

viewport.addEventListener("wheel", (e) => {
  e.preventDefault();
  const zoomFactor = e.deltaY < 0 ? 1.12 : 0.88;
  scale = Math.max(0.7, Math.min(3.5, scale * zoomFactor));
  updateTransform();
}, { passive: false });

// Canvas Click for Actor Selection
canvas.addEventListener("click", (e) => {
  const coords = getCanvasCoords(e);
  const actors = lastRenderState?.actors || [];

  // Hit test actors from top to bottom
  for (let i = actors.length - 1; i >= 0; i--) {
    const actor = actors[i];
    if (!actor.visible || !actor.ground_xy) continue;
    const ax = actor.ground_xy[0] - actor.anchor_xy[0];
    const ay = actor.ground_xy[1] - actor.anchor_xy[1];

    if (coords.x >= ax - 4 && coords.x <= ax + 36 && coords.y >= ay - 6 && coords.y <= ay + 46) {
      selectActor(actor.employee_id);
      return;
    }
  }

  // Clicked empty area
  deselectActor();
});

// Follow Button
followActorBtn.addEventListener("click", () => {
  isFollowingActor = !isFollowingActor;
  followActorBtn.classList.toggle("active", isFollowingActor);
});

inspectorCloseBtn.addEventListener("click", deselectActor);

// Play / Pause Toggle
function togglePlayPause() {
  isPaused = !isPaused;
  playPauseBtn.classList.toggle("active", isPaused);
  playPauseIcon.textContent = isPaused ? "▶" : "⏸";
  playPauseText.textContent = isPaused ? "Resume" : "Pause";
}

playPauseBtn.addEventListener("click", togglePlayPause);

window.addEventListener("keydown", (e) => {
  if (e.code === "Space" && e.target === document.body) {
    e.preventDefault();
    togglePlayPause();
  }
});

// Speed Controls
speedBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
    speedBtns.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    speedMultiplier = parseFloat(btn.dataset.speed) || 1;
  });
});

// Language Switcher
localeSelect.addEventListener("change", () => {
  currentLocale = localeSelect.value;
  updateInspector();
});

// Zoom Toolbar Buttons
zoomInBtn.addEventListener("click", () => {
  scale = Math.min(3.5, scale * 1.2);
  updateTransform();
});

zoomOutBtn.addEventListener("click", () => {
  scale = Math.max(0.7, scale * 0.83);
  updateTransform();
});

zoomResetBtn.addEventListener("click", () => {
  scale = 1.35;
  panX = 0;
  panY = 0;
  isFollowingActor = false;
  followActorBtn.classList.remove("active");
  updateTransform();
});

// Quick Action: Spontaneous Talk
btnDemoTalk.addEventListener("click", () => {
  if (!core || !lastRenderState) return;
  const seatedActors = (lastRenderState.actors || []).filter(
    (a) => a.visible && a.presence === "present" && a.activity === "working" && !a.behavior?.talk,
  );
  if (seatedActors.length < 2) return;

  const initiatorId = selectedActorId && seatedActors.some((a) => a.employee_id === selectedActorId)
    ? selectedActorId
    : seatedActors[0].employee_id;
  const partnerId = seatedActors.find((a) => a.employee_id !== initiatorId)?.employee_id;
  if (!partnerId) return;

  const nowMs = core.clockMs;
  const seatedPlanKey = `${initiatorId}|${partnerId}|seated_host`;
  const standingPlanKey = `${initiatorId}|${partnerId}|standing_pair`;
  const plan = core.bundle.conversation?.plans?.[seatedPlanKey] || core.bundle.conversation?.plans?.[standingPlanKey];
  const mode = plan?.mode || "seated_host";

  const request = {
    kind: "pair",
    category: "conversation_open",
    mode,
    initiator_id: initiatorId,
    partner_id: partnerId,
    participants: [initiatorId, partnerId],
    external: true,
  };

  const builtPlan = core.speechReducer.buildPlan(
    core.state.speech_snapshot,
    core.state.actor_snapshot,
    request,
    currentLocale,
    `demo_talk_${nowMs}`,
  );
  if (plan) {
    builtPlan.spot = plan.spot;
    builtPlan.facing_by_actor = plan.facing_by_actor;
    if (plan.route_info) builtPlan.route_info = plan.route_info;
  }

  for (const id of [initiatorId, partnerId]) {
    const slot = core.state.speech_snapshot.actor_slots?.[id];
    if (slot && slot.active_session_id) {
      core.speechReducer.completeSession(core.state.speech_snapshot, slot.active_session_id, nowMs, []);
    }
  }

  const result = core.speechReducer.startSession(
    core.state.speech_snapshot,
    core.state.actor_snapshot,
    request,
    builtPlan,
    nowMs,
    [],
    currentLocale,
  );

  if (result && result.talkCommands) {
    for (const cmd of result.talkCommands) {
      const actor = core.state.actor_snapshot.actors[cmd.employee_id];
      if (actor) {
        actor.behavior.active_event = null;
        core.actorReducer.applyCommand(
          { snapshot: core.state.actor_snapshot },
          actor,
          core.bundle.employees[cmd.employee_id],
          cmd,
          nowMs,
          [],
        );
      }
    }
  }
});

// Quick Action: Trigger Visual Effects (VFX & HumanBall)
if (btnDemoEffects) {
  btnDemoEffects.addEventListener("click", () => {
    if (!core || !lastRenderState) return;
    const seatedActors = (lastRenderState.actors || []).filter(
      (a) => a.visible && a.presence === "present" && a.activity === "working" && a.workstation_id !== "ceo",
    );
    if (seatedActors.length === 0) return;

    const nowMs = core.clockMs;
    const actor1Id = selectedActorId && seatedActors.some((a) => a.employee_id === selectedActorId)
      ? selectedActorId
      : seatedActors[0].employee_id;
    const remaining = seatedActors.filter((a) => a.employee_id !== actor1Id);
    const actor2Id = remaining.length > 0 ? remaining[0].employee_id : null;

    const actor1 = core.state.actor_snapshot.actors[actor1Id];
    if (actor1 && actor1.behavior) {
      actor1.behavior.next_event_due_ms = null;
      core.actorReducer.startEvent(
        { snapshot: core.state.actor_snapshot },
        actor1,
        core.bundle.employees[actor1Id],
        "background_effect",
        nowMs,
        [],
      );
    }

    if (actor2Id) {
      const actor2 = core.state.actor_snapshot.actors[actor2Id];
      if (actor2 && actor2.behavior) {
        actor2.behavior.next_event_due_ms = null;
        core.actorReducer.startEvent(
          { snapshot: core.state.actor_snapshot },
          actor2,
          core.bundle.employees[actor2Id],
          "popup",
          nowMs,
          [],
        );
      }
    }
  });
}

// Quick Action: Simulate Fatigue / Going Home
btnDemoCritical.addEventListener("click", () => {
  if (!core || !lastRenderState) return;
  const seatedActors = (lastRenderState.actors || []).filter(
    (a) => a.visible && a.presence === "present" && a.activity === "working",
  );
  if (seatedActors.length === 0) return;

  const targetId = selectedActorId || seatedActors[0].employee_id;
  const targetActor = core.state.actor_snapshot.actors[targetId];
  if (targetActor && targetActor.stamina) {
    targetActor.stamina.stamina_milli = 5000;
    targetActor.stamina.threshold_band = "critical";
  }
  selectActor(targetId);
});

// Restart Simulation from time zero
btnReset.addEventListener("click", () => {
  startLiveSimulation();
  deselectActor();
});

// Initialize on Load
updateTransform();
window.addEventListener("DOMContentLoaded", init);
