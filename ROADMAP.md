# GDS Central Game Core — Living Roadmap

**Project root:** `D:\antigravity\board office`
**Source of truth:** unpacked project root
**Updated:** 2026-09-11 (Asia/Bangkok)

Legacy API review host `8765` is retired. Author browser review now uses the
zero-API static viewer at `http://127.0.0.1:8000/viewer.html`.

## Active milestone — Cloudflare browser runtime / zero simulation API

The browser runtime implementation is active. The first slice is
the existing `floor02` nine-actor browser bundle. The target is a static
Cloudflare deployment where the browser advances `BrowserRuntimeCore` locally
after bootstrap; Python remains the offline oracle, generated-bundle builder
and local raster fallback.

- [x] Survey the current Python-hosted page, existing browser JS core,
  generated bundle/manifest boundary and missing Cloudflare configuration.
- [x] Record the scoped design and implementation plan in
  `docs/superpowers/specs/2026-09-04-cloudflare-browser-runtime-design.md` and
  `docs/superpowers/plans/2026-09-04-cloudflare-browser-runtime-zero-api.md`.
- [x] Build reproducible all-floor static bundles and manifests (`WEB/floors/`, `TOOLS/build_all_floors.py`)
  covering all 25 floors with zero Python required in the client runtime.
- [x] Implement browser fixed-step simulation controller (`WEB/viewer_app.js`, `FixedStepClock 60ms`)
  and proven zero recurring `/api/*`/`/api/tick` requests after bootstrap.
- [x] Implement 25-floor dynamic switcher with zero page reloads and instant simulation reset.
- [x] Complete dialogue bubble fitting enforcement (<= 63px safe rect, fixed 9px font, no clipping)
  and dynamic conversational animation frames (M28/M45, M8/M9, happy/sad emotions).
- [x] Diagnose the reported walking jitter at the presentation boundary: live
  RAF pacing is stable (~145Hz, no >20ms gaps or long tasks); the remaining
  perceived unevenness is attributable to fixed 60ms state timing, integer
  walker placement after interpolation, a two-pose walk cycle and fractional
  pixel-art CSS scaling. No implementation change was made in this diagnostic.
- [x] Survey the design for a smoother walking presentation without changing
  gameplay simulation: keep the 60ms deterministic core, introduce an explicit
  render-time pose/timeline, preserve one coherent depth resolver from the
  interpolated pose, and evaluate a higher-resolution logical-coordinate Canvas
  surface before considering a separate layer or WebGL rewrite. The first
  implementation is isolated on `codex/walking-presentation-smooth`; it keeps
  gameplay, canonical assets and the Python fallback unchanged and remains
  author-acceptance pending.
- [x] Make Zero-API browser mode (`WEB/viewer.html`) the primary production architecture while
  retaining Python as offline data oracle, bundle compiler, and review fallback.
- [x] Remove the PC animation frame-swap flash by preloading workstation PC
  frames and retaining the last ready frame during slow image loads; add
  browser regression coverage and verify the live floor00 canvas.
- [x] Merge `prototype_living_character_web` into `main` and push to remote.

### Smooth walking presentation experiment — 2026-09-11

- [x] Add a render-time timeline that interpolates only walking poses between
  accepted 60ms simulation states, with a legacy pixel-mode fallback.
- [x] Resolve character paint order and walking occluders from the same sampled
  pose so interpolation does not desynchronize depth metadata.
- [x] Add a logical-coordinate Canvas backing surface with configurable 1x/2x/4x
  resolution, fractional walker placement in smooth mode, and nearest-neighbor
  pixel-art settings.
- [x] Keep Follow Camera and Canvas hit-testing on logical/render coordinates;
  remove the second CSS camera transition.
- [x] Add Browser regression coverage; `node TESTS/browser_runtime_test.mjs`
  passes **26/26**, syntax checks pass, and `python -m pytest -q` passes
  **388 tests**.
- [x] Author selected the Smooth 4x presentation after live branch-preview
  review of the walking scene, with the deterministic simulation unchanged.
- [x] Compare against the pixel fallback and merge the approved Smooth 4x
  presentation to `main`; retain 2x as an optional lower-cost fallback and
  leave the Python raster fallback unchanged.

### Walking occluder source-alpha correction — 2026-09-11

- [x] Trace the transparency and disappearing-edge defect to RGB-based dark
  pixel removal in the destination-out occluder masks.
- [x] Preserve canonical source alpha, including dark opaque desk, PC and
  chair contours, and add focused regression coverage.
- [x] Rebuild all 25 floor bundles and audit 845 exported occluder masks with
  0 source-alpha mismatches.
- [ ] Author visual confirmation of walking occlusion in the live viewer.

### Standing-pair workstation occlusion hotfix — 2026-09-11

- [x] Trace the standing-pair overlap to the render-time workstation alpha
  mask, without changing table/chair assets, authored depth anchors, talk
  spacing or navigation geometry.
- [x] Add a render-only `standing_pair_hold` policy that filters only `desk`,
  `pc`, `chair` and `chair_sub` occluders for both standing speakers while
  retaining reception/foreground overlays and the normal depth rule elsewhere.
- [x] Mirror the policy in the Python raster renderer, lean metadata projector
  and browser Canvas resolver; cover hold, outbound, return and other talk
  modes with regression tests.
- [x] Validate on `codex/standing-pair-occlusion-hotfix`: focused Python
  **40 passed**, browser **27 passed**, full pytest **392 passed**, and the
  relevant navigation/WorkSeat/conversation/depth audits pass. The existing
  Phase 6/Central reference mismatches remain unrelated.
- [ ] Extend the render-only policy to the actual live-preview reproduction:
  the walking visitor in `seated_host`/`talk_hold` (and explicitly decide
  whether the analogous `ceo_front` visitor is in scope). The current
  `#btnDemoTalk` handler prefers `seated_host`, so the existing
  `standing_pair_hold` patch does not affect the observed visitor.
- [ ] Author visual acceptance from the branch preview and decide whether to
  merge into `main`.

### VFX charging-aura visual review — 2026-09-09

- [x] Produce a fresh curved-volume ten-frame native 33x65 review in
  `LOCAL_REVIEW/core_charge_flow_v2/` after rejection of the angular v1.
- [x] Verify native pixels, unique frames, alpha, nearest-neighbor exports
  and GIF timing (240ms/frame); inspect the enlarged sheet.
- [x] After author rejected smooth v2 as too simple, inspect all 11 effects
  (104 frames), emphasizing fire, and draw the fiercer ten-frame candidate
  `LOCAL_REVIEW/core_charge_inferno_v3/`; verify pixels/timing and unchanged
  reference hashes. Previous v1/v2 are rejected visual history.
- [x] Author rejected the red v3 direction; inspect a blue charging-aura
  reference and redraw the native ten-frame `LOCAL_REVIEW/core_charge_blue_v4/`
  with a luminous inner envelope and curved layered blue perimeter.
  Verify exact pixels, transparent moat, unique frames and GIF timing.
- [x] Composite blue v4 onto the first character on `floor00` and export a
  character-only cropped ten-frame GIF plus 6x nearest-neighbor sheet for
  scene-placement review.
- [x] Compose the actual `floor00` scene and inject blue v4 for every assigned
  actor; export and inspect the ten-frame full-scene GIF at 240ms/frame.
- [x] Record the reusable native-pixel VFX creation, QA, scene-review and
  integration workflow in `docs/VFX_CREATION_GUIDE.md` and link it from
  `docs/INDEX.md`.
- [x] Author visual acceptance of blue v4 and actual floor00 scene placement
  (accepted before requesting the reusable creation guide).
- [ ] Separate production integration request and runtime verification.

### Aggressive Energy ten-effect review — 2026-09-09

- [x] Author requested creation of the planned ten distinct effects with
  cartoon-style color depth and clearly visible ten-frame motion.
- [x] Draw all 100 native 33x65 frames with hue-shifted cel shading, three
  editable Aseprite layers per effect and reproducible Lua source under
  `LOCAL_REVIEW/aggressive_energy_v1/`.
- [x] Verify native dimensions, binary alpha, border, uniqueness, Aseprite
  reopen equality and exact GIF pixels/timing; inspect the 100-frame sheet.
- [x] Produce an animated ten-effect overview and two actual floor00 scene
  reviews covering all ten effects; inspect both scene PNGs.
- [x] Author rejected v1 as overly geometric rods/helices; retain as history.
- [x] Generate and visually inspect a ten-design organic painted concept board
  at `LOCAL_REVIEW/organic_aura_v2/concept_board.png` with saved prompt.
- [x] Author accepted moving from organic concepts to native drawing.
- [x] Reinterpret ten concepts as 100 native frames in
  `LOCAL_REVIEW/organic_aura_native_v2/`; pixel/timing/Aseprite QA passes,
  overview and both actual floor00 scene previews inspected.
- [x] Author rejected native v2 as small clumps; measure fire's occupied
  pixels and redraw all 100 frames as connected fire-scale native v3 masses.
  `LOCAL_REVIEW/organic_aura_native_v3/`: pixel/timing/roundtrip and connected
  mass QA pass; same-scale comparison and actual floor00 previews inspected.
- [x] Author rejected v3's jelly-like appearance; redraw 100 frames in
  `LOCAL_REVIEW/organic_aura_native_v4/` with inward-light color bands and
  asymmetric pixel-dab rims. Pixel/timing/roundtrip/connectivity QA pass;
  comparison, full-frame sheet and both scene PNGs inspected.
- [x] Research the author's Dragon Ball-style charging-aura reference before
  another redraw. The proposed construction is two coordinated layers: a
  contained diffuse aura volume plus contained hard-edged shards/lightning/
  particles, with each 33x65 frame treated as its own clipping domain.
- [x] Redraw the next blue candidate with strict per-cell bounds, a safe
  interior edge treatment, non-repeating shard silhouettes and separate
  fog/shard motion; then re-run native/GIF/scene QA. Layered v5 is at
  `LOCAL_REVIEW/core_charge_layered_v5/`: ten frames, transparent border,
  Aseprite sheet roundtrip and exact preview GIF checks pass; floor00 reviewed.
- [x] Author rejected layered v5; draw a unified single-layer blue v6 with
  larger shape changes, no separate fog, and safe-cell overscan assertions.
  Native/GIF/reopened-sheet QA passes; ten-frame sheet and floor00 inspected.
- [x] Author accepted v6's approximate shape; revise size, on-floor brightness
  and lightning/motes as radiant v7. Ten-frame native/border/GIF QA passes;
  comparison and floor00 inspected, with a 3x scene crop for review.
- [x] Revise v7 into flow v8: +26.2% occupied area in the same safe cell,
  periodic main tips and persistent branch-following filaments/motes.
  Ten-frame native/border/reopened-sheet/exact GIF QA passes; actual floor00
  crop and comparison inspected. No production changes.
- [x] Author requested expansion in the v8 direction with more gradient
  shading; produce ten variants / 100 frames in `LOCAL_REVIEW/flow_aura_ten_v9/`.
  Native/border/Aseprite/exact GIF QA passes, with overview and ten floor00
  scene previews. No production edits.
- [x] Author rejected v9 as recolor-led; draw ten different construction and
  motion styles in `LOCAL_REVIEW/aura_styles_v10/`. All 100 native frames,
  borders, Aseprite roundtrips and exact GIF QA pass; final overview and
  tidal/nebula actual floor00 stills inspected. Review-only, no integration.
- [x] Author rejected v10's thin/worm-like forms and approved a three-style
  mass-first pilot. Created `LOCAL_REVIEW/aura_mass_pilot_v11/` with 30
  native frames, >=1000 occupied pixels per frame, safe borders, reopened
  Aseprite and exact GIF QA. Final overview and blue floor00 crop inspected.
- [x] Revise all three v11 candidates with visible lateral lightning/forks
  as `LOCAL_REVIEW/aura_lateral_pilot_v12/`. Thirty-frame native/border/
  reopened-sheet/exact GIF QA passes; overview and blue floor00 crop inspected.
  Side lanes replace some central fill; total native canvas/anchor unchanged.
- [x] Author accepted v12's general direction; revise as v13 with filled
  side flames and flashing/expanding faceted half-arcs plus outward forks.
  Thirty-frame native/border/Aseprite/exact GIF QA passes; overview and blue
  actual floor00 closeup inspected. No production changes.
- [x] Clarified rear/front halves wrap the fire only; produce v14 with one
  faceted expanding ellipse, rear/fire/front sprite-internal occlusion and
  unchanged actor ordering. All 30 frames pass native/border/Aseprite/exact
  GIF and render-plane composition QA; overview and blue floor00 inspected.
- [x] Redraw v14's rejected geometric fire body as `aura_wildfire_v15` using
  unequal curled tongue landmarks and torn contour shading informed by
  canonical fire; preserve wrapping lightning. Thirty-frame native/border/
  Aseprite/exact GIF/composition QA passes; comparison and floor00 inspected.
- [ ] Author visual/motion acceptance of v15's fire-body redraw
  before expanding to ten styles.
  Native v4 and layered v5 remain rejected history.
- [ ] Separate production integration request and runtime verification.

### Model-generated atlas review — 2026-09-10

- [x] Produce the combined v22 model atlas and isolate its geometry/extraction
  issues; keep it review-only.
- [x] Retire the v23 row-level workaround; use the accepted v22 geometry and
  rows 01-09 as the frozen reference for a fresh 20-type x 10-frame /
  200-cell atlas.
- [x] Generate one combined model source and reject its wrong 22x22 final
  geometry after finding that later-row artwork spans paired columns.
- [x] Rebuild rows 10-20 in complete locked per-frame blocks by reassembling
  paired model columns before extraction; reject the v24 single-column crop.
- [x] Verify all 200 native cells, exact 330x1300 RGBA atlas dimensions,
  90/90 frozen reference frames, complete-pose gate, bottom anchoring and zero
  out-of-bounds cells. Packing containment alone remains insufficient for the
  separate author visual gate.
- [x] Replace the rejected mixed-artwork v25 with v26: generate all 20 rows
  anew, use only the accepted block geometry, correct measured source frame
  edges, and verify 200 complete new poses with no cross-row fragments.
- [x] Render all 20 v26 effects in the actual floor00 compositor, producing
  one named 600x600 / 10-frame / 240ms GIF per effect plus closeup review
  GIFs, with non-VFX channels frozen to prevent background flicker.
- [x] Record v26 visual rejection: source artwork can touch the top/side
  boundary and alpha-bbox normalization turns that into a flat clipped edge.
- [x] Rebuild once as v27 and once as two independent v28 ten-row batches with
  explicit final guard bands, 200-cell technical audits and frozen-channel
  floor00 GIF checks. Both candidates failed the visual gate: the model-owned
  framed source geometry was not stable, and v28's cleanup/fit made the aura
  scale and silhouette inconsistent.
- [ ] Rebuild again with the v22 native-canvas block geometry locked outside
  the image model; validate one complete 10-row batch against the accepted
  reference before generating the second batch. Do not use model-drawn frames
  as geometry and do not normalize an edge-touching alpha bbox.
- [x] Produce v29 sheet 01-10 using a fixed outer block plus fixed inner-safe
  envelope and one identical extraction rectangle per cell. Technical audit:
  100 native cells, ten 10-frame GIFs, 27x58 artwork envelope and zero
  out-of-bounds cells.
- [ ] Author visual acceptance of v29 sheet 01-10 before making sheet 11-20.
- [x] Render v29 sheet 01-10 on floor00 as ten named 600x600 / 10-frame /
  240ms GIFs with non-VFX channels frozen; add closeup review GIFs.
- [x] Start v30 replacement plan with one Crimson Inferno 10-frame pilot,
  fixed row template, fixed safe-area extraction, native review and one
  floor00 pilot GIF. Pilot technical gate passes; author visual review is
  pending before making the rest of sheet 01-10.
- [x] Replace the v30 framed-template pilot with a standalone v31 horizontal
  10-frame strip, source-edge rejection and contain-fit extraction. Crimson
  base clipping is absent in the native and floor00 pilot review.
- [x] Expand the standalone-strip method to one batch of ten effects: 100
  native 33x65 cells, ten individual effect GIFs and ten floor00 scene GIFs.
  Each source is edge-gated independently; RGB/black-backed sources are keyed
  transparent before extraction. Review output is under
  `LOCAL_REVIEW/aura_model_atlas_v32/`.
- [x] Update `docs/VFX_CREATION_GUIDE.md` with the approved standalone-strip
  workflow, edge-gate rules, black-backdrop handling and batch/floor00 QA.
- [ ] Author visual acceptance of the v32 ten-effect batch.
- [x] Decide to expand v32 additively from 11 to 21; the original eleven
  records/assets remain unchanged and review PNGs are not copied directly into
  runtime.
- [x] Resolve the v32 alpha policy as binary native alpha using threshold 32;
  register only the validated canonical 33x65 PNG frames.
- [x] Build a non-destructive replace-10 test candidate that preserves the
  11-effect contract, validates the real effect loader in four directions and
  renders ten floor00 GIFs without modifying canonical/runtime files.
- [ ] Author visual review of the replace-10 test candidate before any
  canonical asset or registry change.
- [x] Diagnose the candidate's frozen employee frames: the floor00 test
  intentionally freezes character/HumanBall/PC channels to isolate VFX; this
  is not evidence of live-runtime animation failure.
- [x] Additive integration approved and completed: migrate the contract and
  catalog from 11 to 21, register 100 new 33x65 PNG frames, rebuild all
  browser bundles/manifests, add save/replay catalog-profile migration, and
  verify a full moving-character floor00 playback before release packaging.
- [x] Complete the read-only dependency audit for the additive 11-to-21 route:
  preserve the existing vfx channel, renderer, anchors, timings, direction
  transforms and old eleven assets; update only the coordinated registry,
  count contracts, asset/hash manifests, derived bundles, selection tests and
  save/replay compatibility policy when implementation is approved.
- [ ] Keep author visual acceptance of the earlier corrected 20-type candidate
  separate; it is review-only and is not a prerequisite for the approved v32
  additive route.
- [x] Complete the separate v32 production integration request and runtime
  verification; leave final visual/gameplay acceptance as an author gate.

### Current HumanBall popup review gate

- [x] Create a new text-specified 100-item office popup batch: five categories,
  20 items each, with no reuse of prior popup images.
- [x] Produce independent native 18x18 Aseprite/PNG sources, ordered 5x4
  review sheets, nearest-neighbor 10x reviews and a batch manifest under
  `LOCAL_REVIEW/humanball_popups_new_from_scratch_v1/`.
- [x] Pass native QA for all 100 sprites: exact dimensions, binary alpha,
  transparent moat/no edge pixels and no identical hashes with prior review
  PNGs.
- [x] Rework the complete 100-item batch into a new shaded review revision
  under `LOCAL_REVIEW/humanball_popups_new_shaded_v2/`, with hard-edged
  highlight/midtone/shadow clusters and no legacy image inputs.
- [x] Pass shaded native QA: 100/100 exact 18x18 RGBA sprites, binary alpha,
  no edge pixels, at least four opaque object colors per sprite, all changed
  from the flat v1 batch and no identical hashes with prior review PNGs.
- [x] Complete the prior fresh redraw for silhouette/readability under
  `LOCAL_REVIEW/humanball_popups_redraw_v3/`; retain it as rejected legacy
  review history only because it is not the current Gate A-derived batch.
- [x] Replace that rejected legacy batch with the active Gate B candidate under
  `LOCAL_REVIEW/humanball_popups_gateb_from_gatea_v1/`, drawn only from the
  five latest author-approved Gate A sheets, with 100 independent native
  18x18 Aseprite/PNG sprites, ordered 5x4 sheets and nearest-neighbor 10x
  reviews.
- [x] Pass active Gate B candidate QA: 100/100 exact 18x18 RGBA sprites,
  binary alpha, transparent moat/no edge pixels, complete dark-inner-contour
  adjacency, at least four opaque colors per sprite, 100 unique hashes and no
  hash overlap with prior review PNGs.
- [x] Author approved the five 180x180 concept sheets (Gate A) and authorized
  the complete native 18x18 redraw for Gate B review.
- [ ] Author visual approval of the active Gate A-derived native redraw (Gate B).
- [ ] Production integration, registry/bundle regeneration and runtime review
  (Gate C).

### Entertainment 20-item visual follow-up — 2026-09-09

- [x] Re-audit the six canonical HumanBall sprites for silhouette families,
  object landmarks and hard-edged value-cluster behavior.
- [x] Create the review-only v3 entertainment redraw under
  `LOCAL_REVIEW/humanball_entertainment_20_v3/` without reusing v1/v2 pixel
  maps; technical export dimensions and locked border colors are present.
- [x] Redraw a representative silhouette pilot first: wide hardware, open
  negative-space audio, radial media, side-profile object and stepped
  geometric piece, under
  `LOCAL_REVIEW/humanball_entertainment_pilot_v4/`; author visual review is
  rejected the construction, so this pilot is review history only.
- [x] Rebuild the representative pilot as silhouette and grayscale structural
  studies in `LOCAL_REVIEW/humanball_construction_v5/` with mirrored controller
  geometry, upright guitar, standalone record and three-face dice.
- [x] Author accepted v5 construction language on 2026-09-09, requiring a
  distinct controller design; the canonical-like v5 controller is not selected.
- [x] Draw and shade all twenty entertainment items in
  `LOCAL_REVIEW/humanball_entertainment_v6/`, including the redesigned
  symmetric twin-stick controller; export PNG/Aseprite and verify pixel QA.
- [x] Author visual acceptance of the full v6 entertainment sheet, 2026-09-09.
- [x] Document all twenty approved construction and shading recipes; preserve
  executable source in `docs/examples/humanball_entertainment_approved.py` and
  verify pixel-identical reproduction of all sprites and both clean sheets.
- [x] Add object-specific highlight/midtone/contact-shadow/deep-shadow
  clusters using a consistent upper-left light direction; avoid decorative
  full-width color bands.
- [x] Rebuild all twenty from the approved pilot language, then obtain author
  visual approval before any production integration.

### Office 200-item batch — 2026-09-09

- [x] Draw ten categories of twenty native sprites using the accepted method;
  create one 5x4 sheet per category under `LOCAL_REVIEW/humanball_office_200_v1/`.
- [x] Provide individual PNGs, transparent native/10x sheets, Thai-labeled
  reviews, overview, manifests and reproducible drawing source.
- [x] Verify all 200: unique RGBA hashes, binary alpha, complete unclipped
  1px #000000/#FFFBF0 borders, and pixel-identical sheet cells.
- [x] Export 200 editable sprites plus ten editable sheets; verify all 210
  Aseprite round trips and ZIP integrity (457 explicitly selected files).
- [x] Respond to the author's flat-shading feedback with explicit material
  highlight/shadow patches on all 200 in `humanball_office_200_shaded_v2/`;
  retain v1 and verify unchanged silhouettes and exact border pixels.
- [x] Verify shaded v2's 210 editable-source round trips and 462-entry ZIP.
- [x] Record author rejection of v2's block-shaped shadows; create cinematic
  v3 with curved surface-driven tonal transitions and warm/cool lighting.
  Verify all 200 changed with identical alpha and black/cream border masks.
- [x] Verify v3's 210 editable-source round trips and 463-entry ZIP integrity.
- [x] Author visual acceptance of the cinematic v3 ten-category batch —
  2026-09-09. Accepted reference for curved cinematic office lighting.
- [x] Roll back the canceled integration attempt; retain all 200 new sprites
  as review-only artwork and leave the six original HumanBall assets/system
  records unchanged.
- [x] Create a review-only floor00 GIF contact sheet with ten random new
  icons, using the original 12-frame HumanBall timing and no integration.
- [x] Receive an explicit request to integrate only the 38 green-selected
  items as an office HumanBall pool.

### Authorized 38-item office pool integration — 2026-09-09

- [x] Resolve the exact 38 green-selected items from
  `green_selected_38_gif/selection.json` without importing the remaining 162
  review-only sprites.
- [x] Copy and hash-register the 38 exact 18x18 RGBA PNGs under the separate
  `CHARACTER/ASSETS/effects/humanball/office/` namespace.
- [x] Add the dedicated office registry/schema and CharacterSystem/Central
  facades while preserving the six canonical HumanBall IDs and hashes.
- [x] Add the office browser visual channel and render-manifest channel;
  rebuild all 25 floor bundles with 38 office IDs plus the unchanged six
  canonical IDs.
- [x] Merge the 38 office IDs into the existing automatic `humanball` popup
  shuffle bag, producing one deterministic 44-item pool while preserving the
  six canonical records and their hashes.
- [x] Verify the office renderer's 12-frame timing, 10 visible / 2 hidden
  frames, 240ms frame timing, NW/SE offsets, binary alpha and asset hashes.
- [x] Keep the review GIFs/sheets out of runtime packaging.
- [x] Default-merge regression: 32 focused pool/metadata/contract tests and
  37 parity/render tests passed; browser unit suite: 16 passed; all 25 floor
  bundle checks passed.
- [x] Prevent consecutive HumanBall reuse at the 44-item shuffle-bag
  generation boundary per actor in Python and Browser JS; guard
  manual/automatic event admission against overlapping recovery events and add
  regressions.
- [x] Enforce no-repeat scope across the global popup stream when different
  actors fire consecutive HumanBalls, with a persisted shared bag mirrored to
  the actor-owned render binding and covered by Python/Browser regressions.
- [x] Prevent a HumanBall presentation from wrapping back to frame 0 when its
  2–4 second recovery window exceeds the 12-frame / 2,880ms visual timeline;
  cover the one-shot/termination boundary with Python and Browser regressions.
- [x] Define the cross-channel depth rule: VFX, canonical HumanBall and office
  HumanBall inherit their work-seat owner's ground depth; larger ground Y is
  closer/front, the rear walker cannot erase a closer channel, and equal-depth
  behavior keeps the existing tie rule.
- [x] Implement browser/Python parity by resolving active channel layers as
  alpha descriptors and applying destination-out/alpha subtraction only to a
  walking actor buffer when the channel owner is closer. Retain authored
  workstation layers and avoid comparing raw ground Y with component layers.
- [x] Add floor02 front-owner/rear-walker regressions for VFX, canonical and
  office HumanBall, hidden frames, reverse depth and mirrored/transparent VFX;
  browser coverage is 23/23 and the full Python suite is 388 passed.
- [ ] Complete the all-floor visual scan and author visual acceptance of the
  cross-depth correction alongside the existing occluder/VFX/HumanBall review.
- [ ] Author visual acceptance of the 38-item artwork remains open; the
  requested 44-item default gameplay merge is now implemented.
- [x] Align the `floor06/ws3` WorkSeat expectation with its authored static
  foreground placement.
- [ ] Resolve the remaining central-audit `floor_skins`/placement-reference
  mismatches.

## Completed milestone — Phase 8E runtime review

The implementation slice, required verification and original browser review were completed, and the baseline author acceptance remains recorded. Static floor geometry, workstation ownership, character artwork and reference assets remain unchanged. Phase 8E baseline is closed; a later live multi-actor follow-up blocker is recorded below. The rejected host-first realtime experiment was deleted and is not part of this milestone.

### Engineering scope complete

- [x] Restrict out-of-seat behavior to authored Talk or Home; retire automatic idle/wander and migrate stale snapshots.
- [x] Preserve the WorkSeat exit/entry presentation boundary and finish-current-work-loop behavior for Critical/Home.
- [x] Keep popup/background/HumanBall effects seated and preserve Work/PC animation clocks.
- [x] Rotate all 11 in-work dialogue categories through persisted locale/category shuffle bags with no visible repetition until refill.
- [x] Treat `encouragement`, `praise`, `celebration`, `disappointment` and `fatigue` as ordinary work dialogue; do not attach them to conversation result status.
- [x] Keep lifecycle speech score/stamina-safe; retain only Talk recovery and standing-pair `sad`/`happy` numeric effects.
- [x] Use every enabled office line through the bag; enabled catalog rows are render-fit and observable in telemetry.
- [x] Select the smallest fitting allowed bubble from BB1/BB2/BB3/BB4/BB6; exclude BB5 and reject overflow.
- [x] Expose dialogue id/category/locale/bubble/bag coverage in API v2 and the web review panel.
- [x] Add focused regression, persistence/replay, catalog-fit and no-wander coverage plus the all-floor audit matrix.

### Verification evidence

- `python -m pytest -q` → **326 passed**.
- Required Room Navigation, Navigation Occupancy, WorkSeat, WorkSeat lifecycle, Phase 6 Spatial, Central, gameplay-metadata family and conversation audits → **PASS**.
- All-floor probe → **25 floors / 219 actors**, zero automatic wander choices.
- Dialogue reload → **2,009 rows / 1,873 enabled rows**; all enabled office rows render; BB1/2/3/4/6 all observed.
- Browser review → static `http://127.0.0.1:8000/viewer.html`, browser-owned simulation with Talk/Effects/Exhaustion controls and no recurring API requests.

### Closeout

1. Author visual/gameplay acceptance: **APPROVED — 2026-09-02**.
2. Final stamina/Thai-content tuning: **APPROVED — 2026-09-02**.
3. Phase 8E implementation and verification gate: **CLOSED**.

The original Phase 8E gate is closed. The rejected host-first realtime experiment and its non-active design documents have been removed; the active browser-owned simulation work remains tracked separately below.

## Post-close conversation-runtime correction — 2026-09-02

The previously approved correction is implemented and verified; visual/gameplay acceptance is **acceptance-pending** until the author reviews the live page.

- [x] Carry planned standing-pair endpoint facings through Central into the actor `talk_hold` pose: the original 2026-09-02 U-axis mapping was later superseded by the V-axis orientation correction below.
- [x] Keep the opener bubble at the explicit extra `[0, -20]` offset and the reply at `[0, 0]`.
- [x] Use one persisted replayable d6 per standing pair with even → `happy` and odd → `sad`.
- [x] Make the review demo completion gate wait for every participant to finish `seat_entry` and expose `work_seat/work/normal_work`.
- [x] Fix the newly diagnosed seated in-work BB frame stall: keep the normal-work clock advancing while the bubble is an overlay, preserve routed talk behavior, and add active/post-return frame regression coverage. Engineering verification completed with the actor-clock, stationary-host and routed-return regressions.
- [x] Verify with `337 passed`, the required navigation/WorkSeat/Phase 6/Central/F2/conversation audits, runtime-presentation QA, and a fresh browser run before retiring the legacy review host.
- [ ] Author visual/gameplay acceptance at `http://127.0.0.1:8000/viewer.html`.

The engineering gate for the non-blocking speech overlay is closed. The page was rechecked on 2026-09-02: active BB frames continue to change while stamina/work time advances, routed talks retain their movement/facing contract, and both participants return to `work/normal_work`. Author acceptance remains a separate pending gate.

## Live multi-actor follow-up correction — 2026-09-02

The long-running full live trace exposed a pending-talk/lifecycle ownership seam. The correction is now implemented, regression-covered and stress-verified. Engineering follow-up is closed; visual/gameplay acceptance remains a separate author gate.

- [x] Prevent actor-side `talk_pending` from freezing the normal-work frame/stamina when the floor speech lane is occupied; define explicit accept, cancel and timeout ownership.
- [x] Keep the queued speech request's category and identity, and prevent an unrelated lifecycle session completion from clearing a still-valid actor talk request.
- [x] Arm greeting and start-work timers at the intended spawn/work-session boundaries instead of initializing the review runtime with both already emitted and relying only on later return events.
- [x] Prevent `_arm_live_behavior_timers()` from scheduling a new weighted event while a stationary talk overlay owns the actor.
- [x] Add multi-actor long-run and noncompact runtime regressions, queue telemetry, and a fresh API/browser stress run; rerun `python -m pytest -q` plus the required navigation/WorkSeat/Phase 6/Central/F2/conversation audits.

Engineering verification result: **348 tests passed**, all required audits and runtime presentation QA passed, and the fresh `floor02` API run reached `137400ms` with 9 work-start bubbles and 0 lifecycle-boundary violations. Author visual/gameplay acceptance is now directed to `http://127.0.0.1:8000/viewer.html` after legacy host retirement.

## Standing-pair orientation correction — 2026-09-03

The attached reference requires the standing pair to occupy the V axis: equal `u`, four-cell `v` separation, with the upper-right/lower-`v` actor facing `SW` and the lower-left/higher-`v` actor facing `NE`. Engineering verification is complete; visual/gameplay acceptance remains a separate author gate.

- [x] Change the conversation contract/schema to prefer V, fall back to U, and order endpoints by ascending `v`.
- [x] Make the resolver default read the contract instead of hardcoding U; keep the authored `SW`/`NE` endpoint-facing order.
- [x] Regenerate the deterministic browser bundle and add core/live-route/browser geometry assertions.
- [x] Align browser transition rounding and persistent-bubble fade sampling with the Python parity oracle exposed by the V-axis route.
- [x] Verify with full pytest **377 passed**, browser unit tests **10 passed**, focused conversation/browser regression **38 passed**, required navigation/occupancy/WorkSeat/Phase 6/Central/F2/conversation audits **PASS**, and conversation visual QA **PASS**.
- [ ] Author visual/gameplay acceptance at `http://127.0.0.1:8000/viewer.html`.

## Lean component-renderer prototype — 2026-09-03

The merged `main` history now contains the engineering-verified headless JSON + browser Canvas prototype. The raster compatibility path remains available until the author accepts the Canvas behavior.

- [x] Add a metadata-only `gds.runtime_render_state.v1` projection and headless loop without materializing Pillow frames.
- [x] Preserve the Python/Pillow raster path as the explicit compatibility fallback.
- [x] Build the deterministic `floor02` static/component manifest and Canvas renderer with 100ms polling plus RAF composition/interpolation.
- [x] Verify parity across spawn/work, Talk, Effects/HumanBall and Critical traces, plus no-Pillow Canvas requests.
- [x] Measure Canvas p50 request `1.13ms` versus raster `10.63ms`, payload `23.7KB` versus `136.4KB`, and `82.63%` payload reduction.
- [ ] Author visual/gameplay acceptance for Canvas/Raster parity, pixel sharpness, dialogue bubbles, walking depth and perceived smoothness.
- [x] Merge the derived lean renderer history into `main` while retaining raster fallback and canonical asset/hash contracts.
- [ ] After acceptance, trim duplicate canvas telemetry/projection work, publish the derived bundle, and choose the Cloudflare authority model.

The prototype is intentionally not yet a closed production milestone: it is limited to `floor02`, retains two presentation implementations for fallback/parity, and carries generated derived browser assets that should be treated as build/deployment output rather than new gameplay source.

## Browser-owned simulation slice — 2026-09-03

The latest browser-owned simulation work is now merged into `main` at `18f0436`. After one bootstrap load, a single-user browser can advance deterministic runtime state locally and use the existing Canvas component renderer. The Python runtime remains the canonical oracle and local fallback. Tasks 1–4 are engineering-complete; persistence/replay hardening, UI source-mode integration and endurance/Cloudflare gates remain open.

- [x] Export and validate the deterministic `floor02` browser bootstrap bundle and Python parity traces.
- [x] Add deterministic browser PRNG/state/clock primitives, a no-DOM core shell and stdin parity checkpoint.
- [x] Port bundle-backed navigation, actor movement/action clocks and WorkSeat ownership with spawn/work and home-route parity.
- [x] Port speech/dialogue, standing-pair conversation, effects, HumanBall, stamina/lifecycle and critical-home boundaries with focused parity traces.
- [ ] Harden browser save/load/replay behavior with an explicit versioned package and exact replay parity.
- [ ] Integrate Browser source mode with zero periodic `/api/tick` calls while preserving Python Canvas/Raster fallback.
- [ ] Pass simulated 24-hour, real browser soak, author visual/gameplay and release-clean gates.
- [ ] Decide the separate Cloudflare static deployment/persistence or shared Durable Object/WebSocket slice.

## Lean-first cleanup prerequisite — 2026-09-03

Before starting the production TypeScript/JavaScript migration, the current runtime must be made lean and contract-stable. The detailed migration plan was removed during the author's cleanup after the non-accepted migration direction was discarded. This prerequisite does not change the current Python oracle, canonical assets or raster fallback.

- [x] Establish a reproducible lean audit and clear the reviewed Ruff unused-import/unused-local findings.
- [ ] Consolidate repeated QA/build/validation helpers and centralize source-hash profiles without changing output hashes.
- [ ] Reduce the duplicate runtime presentation/projection path to one neutral frame per simulation slice.
- [ ] Split high-responsibility runtime façades behind compatibility-preserving interfaces.
- [ ] Retire legacy crowd/action/wander/depth seams only after caller inventories and replay migration tests prove they are unused.
- [ ] Freeze the browser bundle/snapshot/render-state contracts and verify one bootstrap request with zero periodic `/api/tick` calls before handing off to the TS/JS migration.

The standing-pair visual/gameplay acceptance, Canvas/Raster acceptance, browser persistence/replay, endurance and Cloudflare gates remain separate and must not be marked closed by the lean audit alone.

## TypeScript/JavaScript runtime migration design — 2026-09-03

The staged Browser-owned runtime direction is historical only; its design and
task-by-task migration plan were removed during the author's cleanup. The
accepted production default on `main` remains Python + Raster. No migration
worktree or non-accepted TypeScript candidate is currently active.

- [x] Survey the current Python/browser/data boundaries and migration-tool options.
- [x] Select contract-first TypeScript porting with Python retained as oracle,
  builder, QA and fallback.
- [x] Define the target module boundaries, bundle rules, parity strategy,
  browser zero-request behavior, Cloudflare packaging and rollback gates.
- [x] Author review of the migration specification.
- [ ] Select the execution mode and begin the Task 1 toolchain checkpoint.
- [ ] Complete lean-first source-profile, neutral-frame, facade-boundary,
  legacy-caller and contract-freeze prerequisites before implementation.
- [ ] Add the TypeScript toolchain and begin the production runtime port only
  after the design and prerequisite gates are accepted.

Track A engineering checkpoint (2026-09-03): the audit/hygiene gate is green, proven preview/POC debris and generated workspace output were removed, and the canonical duplicate manifest was collapsed to `CHARACTER/FINAL_MANIFEST.json`. Remaining duplicate function-body groups are retained as domain/test candidates until a semantics-preserving boundary is approved; source-hash profiles and the later runtime tracks remain open.

## Full TypeScript/JavaScript scope clarification — 2026-09-04

The requested end state was broader than the first Browser-owned production
slice: every active Python runtime, renderer, ReviewRuntime/server adapter,
builder/export/QA tool, validator and pytest family would have required a
behavior-preserving TypeScript/JavaScript replacement. The full-cutover plan
was removed during the author's cleanup; no production cutover is active.

- [x] Record the explicit rule that this is a port, not new gameplay or a
  feature expansion.
- [x] Map the remaining responsibilities to authoritative Python sources and
  typed boundaries: occupancy, clearance, pathfinding, actor lifecycle,
  speech/conversation, renderer/pixel parity, ReviewRuntime, tools and
  Python removal.
- [x] Establish strict browser/Node TypeScript checks and deterministic contract
  generation in the former migration worktree: root, browser and node typechecks pass;
  46 generated contract files are deterministic; Vitest is 32 files / 84 tests.
- [x] Freeze the reviewed Python oracle as annotated tag
  `oracle/python-runtime-2026-09-04` at `fde8279`; run the clean Python suite
  twice with **404 passed** on both runs; and freeze the 169-file / 46,039-line
  inventory with exact path, line-count and SHA-256 fixture coverage.
- [ ] Port complete World/Character domains and runtime behavior against full
  snapshots/events/plans, not compact browser projections.
- [ ] Port authored presentation, ReviewRuntime, persistence/replay, all tools,
  validators and all pytest coverage; keep Python as oracle/fallback meanwhile.
- [ ] Pass all-floor differential, pixel/hash, browser zero-request, endurance,
  Cloudflare, release-clean and explicit author-acceptance gates.
- [ ] Remove Python only as the final mechanical commit after every replacement
  and gate is green; preserve accurate history.

The former `codex/tsjs-runtime-migration` worktree had typed foundations and a
Browser source candidate, but direct full comparison reported known
differences in long lifecycle conversation state, dynamic depth/occluders,
effect clocks, Talk/Wander metadata and cross-runtime persistence. At the
author's request on 2026-09-04, that branch, worktree, uncommitted candidate,
design and plan documents were discarded. Reopening requires explicit approval
and a new isolated branch/worktree.

## Combined visual selection and per-actor bubble correction — 2026-09-03 (engineering complete)

The asset/rendering inventory and BB root-cause audit are complete. The written design spec is `docs/superpowers/specs/2026-09-03-visual-selection-bubble-concurrency-design.md` (committed as `b7d03b9`) and is author-approved. The execution plan is `docs/superpowers/plans/2026-09-03-visual-selection-bubble-concurrency.md` (committed as `9c11ef0`). Implementation and engineering verification are complete; author visual/gameplay acceptance remains a separate gate.

- [x] Replace hash-modulo VFX selection with deterministic per-actor/per-channel shuffle bags covering all 11 canonical VFX IDs.
- [x] Keep all 6 canonical HumanBall popup IDs in a deterministic per-actor popup shuffle bag with no repeat before refill.
- [x] Replace floor-wide bubble serialization with one bubble slot per actor; allow different actors on the same floor to show bubbles concurrently.
- [x] Keep same-actor exclusion, atomic participant locks for pair sessions and physical talk-spot/path/crowd collision protection.
- [x] Mirror the scheduler and visual-bag algorithms in Browser JS with exact Python parity, compact save/load state and one-bootstrap/no-per-event-request behavior.
- [x] Add same-floor concurrency, VFX/popup coverage, legacy migration, replay/parity and full regression gates before TS/JS migration.
- [ ] Author visual/gameplay acceptance at `http://127.0.0.1:8000/viewer.html`.

Engineering evidence: full Python suite **403 passed**, browser unit suite **14 passed**, focused conversation/browser regression suite **48 passed**, compile/Ruff/diff checks passed, required runtime audits passed, and the live page showed simultaneous VFX/HumanBall channels plus two actor-owned BBs. This section does not close the existing Canvas/Raster, browser persistence, endurance or Cloudflare gates.

## Walking visitor bubble lift follow-up — 2026-09-03

The original behavior correction remains implemented and regenerated for `seated_host`; the shared `ceo_front` visitor lift was corrected by the combined slice below. Engineering verification is complete; visual/gameplay acceptance remains a separate pending gate.

- [x] Add the contract/schema field for the visitor extra `[0, -20]` offset.
- [x] Apply the extra offset to the walking visitor in `seated_host`, producing actual `-40px` total height while leaving its host at normal `-20px`.
- [x] Regenerate the `floor02` browser bundle and verify all **11 VFX** and
  the current **44-item HumanBall popup** pool remain present.
- [x] Add Python/browser bundle regressions; full Python suite **403 passed**, focused conversation/browser suite **48 passed**, browser unit suite **14 passed**.
- [ ] Author visual/gameplay acceptance at `http://127.0.0.1:8000/viewer.html`.

## Combined startup stamina + CEO bubble correction — 2026-09-03

Two author-requested behavior corrections were implemented and verified together. The scope stayed limited to the review-host startup default and the `ceo_front` conversation branch.

- [x] Make normal `/api/live-start` begin every actor at `100` stamina and retain the low-energy actor only in the explicit Critical demo path.
- [x] Keep `seated_host` visitor extra `[0, -20]` and its actual `-40px` result unchanged.
- [x] Make `ceo_front` use explicit `[0, 0]` bubble extras for both visitor and CEO, producing actual `-20px` for both.
- [x] Leave `standing_pair`, self-talk, effects, assets, metadata and all unrelated modes unchanged.
- [x] Update the targeted Python/review/bundle regressions and regenerate the embedded `floor02` browser bundle; no global contract/schema change was needed.
- [x] Run the full Python/browser, compile/lint and focused runtime checks; author visual/gameplay acceptance remains pending.

## Integration checkpoint — 2026-09-03

- [x] Fast-forward merge of the latest browser-owned simulation work into `main` at `18f0436`.
- [x] Remove the merged local feature worktrees and branches; retain only `main` locally and leave `origin/main` unchanged.
- [x] Run merged verification: full Python suite **377 passed**, browser runtime **10 passed**, browser parity **8 passed**, focused renderer/server/web/benchmark/bundle suite **62 passed**.
- [ ] Author visual/gameplay acceptance and complete browser persistence/replay, zero-request UI source mode, soak and Cloudflare gates.
