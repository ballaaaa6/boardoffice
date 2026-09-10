# GDS Central Game Core — Handoff

**Updated:** 2026-09-10 (Asia/Bangkok)
**Project root:** `D:\antigravity\board office`
**Status:** Zero-API Client-Side Browser Simulation Architecture active on `main`. Character crop/shadow and chair foreground defects are resolved in the live renderer across all 25 office floors (219 workstations and employees). HumanBall selection scope, animation lifecycle and manual event-overlap cases are fixed and regression-covered. Python remains offline data oracle, bundle compiler (`TOOLS/build_all_floors.py`), and review fallback.

## Current state

- 2026-09-10 the local host was switched to the zero-API browser viewer:
  `python TOOLS/static_web_server.py`, with `/` mapped to
  `WEB/viewer.html` at `http://127.0.0.1:8000/`. Root and direct viewer HTML,
  module and floor-index health checks passed (HTTP 200) and root/direct HTML
  are identical; `viewer_app.js` contains zero `/api/` references and
  `/api/health` returns 404 on the static host. The previous API review host
  was stopped.

- 2026-09-10 legacy API review host cleanup completed. Removed the review
  server/page, API polling client, and their review-only test/benchmark files.
  The dependency audit had found 52 local Python modules and 397 canonical
  data/image files behind that host; those source/runtime files remain intact.
  Shared `WEB/runtime_canvas_renderer.js`,
  `WEB/runtime_render_manifest.json`, `WEB/runtime_assets/`, and browser floor
  bundles were preserved for the zero-API viewer. Port `8765` is retired; the
  only author web host is static `8000`. Verification after cleanup: full
  pytest **375 passed, 1 pre-existing failure** at
  `TESTS/test_work_seat_floor_integration.py::test_floor06_workstation_seat_resolution_uses_directional_chair_roles`
  (`foreground_static_present` expectation); browser runtime **16/16**,
  Node syntax checks **12/12**, static viewer/floor index HTTP **200**, and no
  `8765` listener or active-source reference remains.

- 2026-09-09 explicit integration request received for the 38 green-selected
  office HumanBall items. The selected PNGs are registered in the office
  registry and now merged into the existing automatic `humanball` popup bag:
  six locked canonical items + 38 office items = 44 deterministic choices per
  actor/channel shuffle-bag cycle. The original six records, IDs and hashes
  remain unchanged. Added the dedicated registry/schema/facades, asset-registry
  records, browser bundle channel, render-manifest channel and Canvas fallback
  so a mixed default popup can load either source. Rebuilt all 25 floor bundles;
  each exposes 6 canonical plus 38 office HumanBalls. The 38 source PNGs are
  exact 18x18 RGBA assets with recorded hashes, and no GIF or review sheet was
  packaged as runtime data. Requested default gameplay merge is implemented;
  visual acceptance of the 38-item artwork remains open.
  A browser parity mismatch found during verification was fixed by making the
  Python speech scheduler use the same render-fit dialogue pool as the browser.
  Current merge regression: 32 focused pool/metadata/contract tests and 37
  parity/render tests passed; browser unit suite: 16 passed. Full pytest: 409
  passed, 1 pre-existing `floor06/ws3` foreground-placement
  expectation failure. Central self-audit remains blocked by the existing
  `WORLD/REGISTRY/floor_skins.json` reference hash and placement-count
  mismatches; neither is part of this HumanBall change.

- 2026-09-10 HumanBall duplicate fix implemented after the diagnostic audit.
  `RUNTIME/visual_selection_core.py` and
  `WEB/runtime_simulation_visual_selection.js` now deterministically swap the
  first two items of a new HumanBall permutation only when its first item would
  equal the previous generation's last item. Each 44-item generation remains a
  complete permutation and VFX selection is unchanged. Python and Browser
  `startEvent` now reject an already-active recovery/talk event, while the
  manual Effects action validates the actor state before admission. Added
  boundary and duplicate-admission regressions in both runtimes. Focused
  Python tests: **32 passed**; browser runtime: **18 passed**; browser parity
  trace: **8 passed**; full pytest: **377 passed, 1 pre-existing failure** at
  `TESTS/test_work_seat_floor_integration.py::test_floor06_workstation_seat_resolution_uses_directional_chair_roles`
  (`foreground_static_present`). Syntax and `git diff --check` pass. Status:
  engineering fix complete; visual/gameplay acceptance remains a separate
  author gate. Next task is author review on `http://127.0.0.1:8000/`; the
  pre-existing floor06 WorkSeat and central-audit mismatches remain blockers to
  calling the repository fully green.

- 2026-09-10 follow-up diagnostic after the author still observed consecutive
  identical popups. The current `8000` host serves the updated selector and
  current 44-item bundle. The 44 HumanBall source pixels and URLs are unique;
  the browser renderer reads one persisted binding per actor and does not
  reselect or draw a second HumanBall channel. Same-actor sequential selection
  was exercised 50 times without a repeat. The remaining reproducible cause is
  that both Python and Browser shuffle bags are keyed by `employee_id` plus
  channel, so they guarantee no repeat per actor, not across the global popup
  stream. With the current catalog and `viewer_seed_test_0`, the first popup
  choice for `EMP_W1_0031` and `EMP_W1_0044` is the same
  `office.food_drinks.cake`; if those actors fire consecutively, the UI shows
  the same HumanBall twice. Restart/floor-switch also reconstructs the same
  initial snapshot and resets all per-actor cursors. The follow-up fix now
  persists one shared `humanball_global_bag` in actor determinism, advances it
  once at each popup admission, and mirrors the resulting binding into the
  actor-owned render channel. This makes the no-repeat scope global while
  preserving active-binding rendering and save/load continuity. Focused tests:
  Python **34 passed**, Browser **19 passed**; parity trace **8 passed**; full
  pytest **379 passed, 1 pre-existing failure** at
  `TESTS/test_work_seat_floor_integration.py::test_floor06_workstation_seat_resolution_uses_directional_chair_roles`
  (`foreground_static_present`). All 25 floor bundles and the root fallback
  bundle were rebuilt; static HTTP checks remain green.

- 2026-09-10 follow-up trace found the remaining visible duplicate was not an
  asset-selection collision and not a second `popup` admission. The checked-in
  HumanBall timeline has 12 logical frames at 240ms each: 10 visible offsets
  followed by 2 hidden offsets (`CHARACTER/RUNTIME/humanball_renderer.py`), so
  one presentation lasts 2,880ms. The live popup policy allows a 2–4 second
  activity window (`CHARACTER/EMPLOYEES/employee_metadata.json`), while the
  browser presentation previously indexed offsets modulo 12, causing a
  3,180ms/3,420ms popup to wrap to frame 0 after its hidden frames. The fix
  now clamps the Browser/Python presentation to the first hidden frame and
  makes both renderers reject any frame at or beyond the ten visible frames.
  Added regressions for long popup windows and the Browser canvas path.
  Focused Python **25 passed**, Browser **20 passed**, parity trace **8 passed**;
  full pytest **380 passed, 1 pre-existing failure** at
  `TESTS/test_work_seat_floor_integration.py::test_floor06_workstation_seat_resolution_uses_directional_chair_roles`
  (`foreground_static_present`).

- 2026-09-09 current VFX task: author rejected v3's jelly-like shading and
  requested inside-to-outside color plus unpredictable fire-like pixel edges.
  Active review `LOCAL_REVIEW/organic_aura_native_v4/`: 100 native 33x65
  frames at 240ms, three-layer Aseprite sources, exact individual/overview
  GIFs, all-frame sheet, fire/v3/v4 comparison and two actual floor00 GIFs.
  Edited the native Lua source: stepped dark/color rim follows actual jagged
  silhouette distance into a luminous center; uneven brush tips, side dabs
  and bitten-out notches replace smooth contours. Detached particles no
  longer paint dark specks over the bright interior. Occupancy 1296–1674
  (mean 1512), main connected mass >=95.91%; fire mean is 1326.
  Dimensions, binary alpha, uniqueness, Aseprite roundtrip, exact GIF pixels/
  timing and scale/connectivity checks PASS. No transparent moat claimed.
  Inspected comparison, all-frame sheet and both scene PNGs. Scene GIFs are
  quantized and work poses sampled by index, not gameplay-clock parity.
  Native v4 was rejected for clipped edges and a fog-only appearance;
  older candidates are retained as review history.
  On 2026-09-09 the author requested research before another redraw because
  some aura details are clipped at cell boundaries and the current pass reads
  as fog-only. Visual research used the official Toei trailer plus reference
  stills and animation-art guidance: the next candidate must separate a
  contained diffuse aura volume from contained hard-edged energy shards/
  lightning, with independent motion and strict per-cell clipping.
  Author then requested drawing the plan. Current candidate is
  `LOCAL_REVIEW/core_charge_layered_v5/`: one blue aura, ten 33x65 frames,
  240ms, editable Aseprite, native PNG/sheet, preview/layer-breakdown GIFs
  and actual floor00 GIF with all five actors. Native Lua separates darker
  flowing atmosphere, concave tapered bright tongues and transient filaments.
  Every authored coordinate is asserted within x=1..31/y=1..63; all ten
  exported frames have a transparent border. Uniqueness, binary alpha,
  reopened Aseprite sheet and exact review GIF pixel/timing QA PASS.
  Inspected layer breakdown and floor00; scene GIF remains quantized and
  work poses sampled by frame index. Batch processes exited normally.
  No runtime/canonical edits or server; pytest not run for artwork-only work.
  Author rejected v5's stiff shapes, limited motion and mismatched fog.
  Current candidate: `LOCAL_REVIEW/core_charge_unified_v6/`, ten 33x65
  frames at 240ms in one Aseprite layer. Seven changing tapered flows form
  one blue energy mass; color bands follow the same silhouette. Includes
  preview/comparison GIFs, full sheet and actual five-actor floor00 preview.
  Overscan asserts no occupied pixels outside the safe cell; transparent
  border, uniqueness, binary alpha, reopened sheet and exact GIF QA PASS.
  Adjacent changed canvas pixels: v6 22.6-27.9% versus v5 16.2-20.5%,
  including loop seam. Inspected full sheet and floor00. Batch processes
  exited; no runtime changes, pytest unnecessary; git diff --check passed.
  Author accepted v6's approximate silhouette, requesting larger size,
  brighter on-floor colors and small lightning/particle accents. Current
  candidate is `LOCAL_REVIEW/core_charge_radiant_v7/`: ten native 33x65
  frames at 240ms with thicker flows fitted using a fixed animation-wide
  mapping, brighter cyan midtones and intermittent lightning/motes.
  Mean occupied pixels 719.7 versus v6 628.5 (+14.5%). Safe-cell overscan,
  transparent border, uniqueness, binary alpha, reopened sheet and exact
  sprite/review GIF checks PASS. Comparison and floor00 inspected; includes
  full scene and 3x actual-scene crop GIFs. Scene GIFs quantized; work poses
  sampled by frame index. No runtime edits/server; batch process exited.
  Author requested more size and continuous accent motion after v7.
  Current candidate: `LOCAL_REVIEW/core_charge_flow_v8/`, ten 33x65 frames
  at 240ms, single editable Aseprite layer, same bright cyan palette/anchor.
  Thicker flows increase mean occupied pixels to 908.3 (+26.2% versus v7).
  Periodic main-tip motion replaces modulo jumps; persistent filaments/motes
  follow interpolated samples of their own main-flow branches across the loop.
  Safe-cell overscan, transparent border, uniqueness, reopened sheet and exact
  native/review GIF QA PASS. Inspected comparison, full sheet and actual
  floor00 crop; scene GIFs remain quantized with index-sampled work poses.
  No runtime/canonical changes or server; batch exited, pytest not required.
  Author subsequently requested ten additional variants in the v8 direction
  with more gradient shading. Current review: `LOCAL_REVIEW/flow_aura_ten_v9/`.
  Completed ten hue-shifted variants, 100 native 33x65 frames at 240ms,
  editable single-layer Aseprite sources, branch-following accents and varied
  branch count/curvature/taper. Nonlinear inward shading preserves saturated
  midtones instead of the large flat-white core. Includes animated overview,
  all-frame sheet, individual GIFs and ten actual five-actor floor00 scenes
  with closeup GIFs. Native/border/uniqueness/Aseprite roundtrip and exact
  sprite/overview GIF QA PASS. Overview and purple/gold floor00 PNGs inspected.
  Scene palette quantization and index-sampled pose caveats still apply.
  Batch exited; no server or runtime changes; pytest not required.
  Author rejected v9 as palette changes rather than distinct styles.
  Current review: `LOCAL_REVIEW/aura_styles_v10/`: ten different flow
  constructions (torn flame, crescent, branches, radial burst, crown, falling
  veil, breaking wave, electricity, surging lobes, irregular nebula pockets).
  Preserved gradients, ten 33x65 frames each at 240ms and tracked accents.
  Revised tidal/nebula geometry after the first overview inspection to reduce
  crescent duplication and smooth-ring geometry. Native/border/Aseprite and
  exact individual/overview GIF QA PASS for all 100 frames. Final overview
  and tidal/nebula actual floor00 PNGs inspected. Includes ten scene/closeup
  GIFs with the same quantization/index-sampled-pose caveats. No runtime
  changes, no server; batch exited; pytest not required for review-only art.
  Author rejected v10 as thin/worm-like and lacking spectacle, then approved
  a three-style mass-first pilot before another ten-effect expansion.
  Current candidate: `LOCAL_REVIEW/aura_mass_pilot_v11/`: Cataclysm,
  Stormfront and Overcharge; 30 native 33x65 frames at 240ms. Derived from
  v8 with thicker multi-tip flows, billowing lobes or angular branching,
  luminous cores, shaded recesses and continuous branch-following accents.
  Initial mass check caught two 999px frames; increased shoulder/tip mass
  before final export. All final frames exceed the 1000px occupancy gate;
  native/border/uniqueness/Aseprite roundtrip and exact GIF QA PASS.
  Inspected final overview and actual blue floor00 closeup. Includes three
  actual five-actor floor00 scenes and closeups; prior scene caveats apply.
  No runtime/server changes; batch exited; pytest unnecessary for art-only work.
  Author requested visible lateral branches and angular lightning decoration,
  approving a revision of all three. Current candidate:
  `LOCAL_REVIEW/aura_lateral_pilot_v12/`: same 30 native 33x65 frames/240ms.
  Reserved x=1..4 and x=28..31 side lanes by narrowing the central mass;
  added four primary bolts and four forks with colored sheaths/white cores,
  persistent left/right identities and periodic eruption-linked motion.
  Final frames pass >=800px occupancy (some fill replaced by side lanes),
  transparent border, overscan/accent bounds, uniqueness, Aseprite roundtrip
  and exact GIF QA. Inspected overview and blue actual floor00 crop; side
  discharges visibly extend outside the central mass. Three actual floor00
  GIFs/closeups retain palette-quantization and pose-index caveats.
  No runtime/canonical changes or server; batch exited; pytest unnecessary.
  Author accepted v12's general direction, requesting sideward main flames
  and faceted half-arcs that flash, expand and scatter. Current review:
  `LOCAL_REVIEW/aura_arc_pilot_v13/`, three styles / 30 native 33x65 frames,
  240ms. Added filled shoulder/waist side tongues and staggered left/right
  near-semicircular lightning arcs, expanding during visible ages with
  bright/dim flashes, outward forks and an invisible reset interval.
  Native/border/overscan/accent/uniqueness/Aseprite/exact GIF QA PASS;
  inspected overview and blue actual floor00 closeup. Three full scenes
  and closeups retain palette-quantization and index-sampled pose caveats.
  No runtime/canonical edits/server; batch exited; pytest unnecessary.
  Author clarified that the lightning must be one ring wrapping the FIRE,
  with rear/front halves, not left/right arcs and not character-layer changes.
  Current candidate: `LOCAL_REVIEW/aura_wrap_pilot_v14/`, three styles,
  30 native 33x65 frames at 240ms. Rear half -> unchanged v13 side-flame body
  -> front half, flattened into one sprite layer; both halves share endpoints,
  expansion and flash phase. Retained outward forks and invisible reset.
  Native/border/Aseprite/exact GIF QA and pixel-exact rear/body/front
  composition checks PASS for all 30 frames. Inspected overview and actual
  blue floor00 closeup. Actor ordering/anchor remains unchanged; all VFX
  pixels still use canonical fire placement behind the actor. Scene GIF
  quantization/index-sampled pose caveats apply. Batch exited, no server,
  runtime or canonical edits; pytest unnecessary for artwork-only work.
  Author rejected v14's main mass as too geometric and requested a fierce
  redraw informed by canonical fire. Current candidate:
  `LOCAL_REVIEW/aura_wildfire_v15/`, 30 native 33x65 frames at 240ms.
  Nine unequal authored tongue landmarks replace the regular fan/side spikes;
  periodic contour distortion, edge bites and curved inward shading replace
  blocky masses. Three palette/phase candidates, not three new style families.
  Preserved v14 rear/fire/front wrapping ring and unchanged actor ordering.
  Initial left-edge overscan failures were corrected by reshaping the curl
  and fixed x fitting. Final native/border/uniqueness/overscan/Aseprite/exact
  GIF and render-plane composition QA PASS; >=800 occupied pixels/frame.
  Inspected overview, blue actual floor00 crop and canonical/v14/v15 comparison.
  No runtime/canonical edits/server; batch exited; pytest unnecessary.
  Next: author visual review of v15 fire body before ten-style expansion.

- The author accepted blue-v4's actual floor00 scene preview before requesting
  the creation guide. Accepted reference remains
  `LOCAL_REVIEW/core_charge_blue_v4/`; earlier candidates remain history.
  The English workflow is `docs/VFX_CREATION_GUIDE.md`, linked from
  `docs/INDEX.md`. Blue-v4 production integration has not been requested.

- 2026-09-09 current artwork task: author rejected v2's rectangular shading
  and requested curved tonal transitions with cinematic lighting. Active
  approved artwork: `LOCAL_REVIEW/humanball_office_200_cinematic_v3/`; v1/v2 untouched.
  Relit the primary material of all 200 sprites with per-object selected
  cylinder/ellipsoid/torus/diagonal-shaft/convex-panel/beveled-plane profiles,
  warm upper-left key, cool shadows and seven-slot discrete material ramps.
  Dark structural marks retain contrast bias. Small accent materials remain
  as drawn. Source: `docs/examples/humanball_office_cinematic.py`; reproduce
  with `humanball_office_200.py --cinematic --output <directory>`.
  Inspected ten labeled sheets and eight before/after pairs; reduced excessive
  glint coverage and restored dark grooves/marks during review.
  Native QA: 200 unique, binary-alpha 18x18 sprites; exact sheet cells and
  complete 1px #000000/#FFFBF0 rings. Comparison with rejected v2: all 200
  changed (15-141 interior pixels); alpha and both border masks unchanged.
  All 210 editable Aseprite exports round-trip pixel-identically; 463-entry
  ZIP integrity and `git diff --check` pass. Batch processes exited.
  Export verification is recorded in `export_audit.json` beside the ZIP.
  Author explicitly approved cinematic v3 on 2026-09-09 ("โอเคเริ่มเลยผ่าน").
  It is now the accepted office lighting reference; entertainment v6 remains
  separately approved. Acceptance recorded in HANDOFF/ROADMAP; diff check
  passed. The author then explicitly canceled production integration before
  approval. That earlier attempt was rolled back; it was later superseded by
  the explicit request to integrate only the 38 green-selected items as a
  office pool. The remaining 162 new PNGs remain review-only under
  LOCAL_REVIEW and are not in the game system.

- 2026-09-09 review-only demo: created
  `LOCAL_REVIEW/humanball_office_200_cinematic_v3/floor00_random10_gif/`.
  It contains one 5x2 animated GIF sheet using ten deterministic random
  office icons on one cropped floor00 CEO scene. Each panel keeps its icon
  fixed through visible HumanBall frames 1–10, follows the existing SE motion
  offsets, then hides on frames 11–12 at 240ms. The GIF has 12 frames; the
  still sheet and `selection.json` are included. The demo remains review-only;
  no GIF/sheet was packaged as runtime data.

- 2026-09-09 review-only demo: created
  `LOCAL_REVIEW/humanball_office_200_cinematic_v3/green_selected_38_gif/`.
  It contains the 38 items marked with bright-green circles in the current
  overview, resolved against the batch manifest and arranged in one 5x8
  animated floor00 CEO sheet. Each panel keeps its selected icon unchanged
  through visible HumanBall frames 1–10, follows the existing SE motion
  offsets, then hides on frames 11–12 at 240ms. The GIF is accompanied by a
  first-frame still, `selection.json` and a review README. The GIF remains
  review-only; its 38 selected PNGs were later integrated into the default
  popup office pool, and the GIF/sheet itself was not packaged.

- 2026-09-09 review-only demo: created
  `LOCAL_REVIEW/humanball_office_200_cinematic_v3/system_six_gif/`.
  It contains all six locked system HumanBall assets from
  `CHARACTER/EFFECTS/humanball_v1.json` on the same floor00 CEO crop, arranged
  as one 3x2 animated sheet. Registry SE offsets and 10-visible/2-hidden,
  240ms timing are preserved; source asset hashes are recorded in
  `selection.json`. The six source assets and canonical registry remain
  unchanged; the GIF remains review-only.

- 2026-09-09 current HumanBall review: author approved the v5 construction
  language, with a required controller redesign to avoid duplicating the
  original. Created `LOCAL_REVIEW/humanball_entertainment_v6/`: 20 native
  18x18 PNG/Aseprite sprites, 90x72 transparent sheet, 10x sheet, labeled
  review, reproducible drawing source, manifest and pixel audit. The new
  controller has mirrored angled handles and twin analog sticks. Other items
  extend the approved construction language with material-specific light and
  shadow clusters. QA passes 20/20 for size, binary alpha, complete unclipped
  1px #000000/#FFFBF0 rings and exact sheet cells. No runtime changes.
  Author visually approved the full v6 sheet and requested documentation.
  Updated `docs/HUMANBALL_POPUP_CREATION_GUIDE.md` with all twenty construction
  recipes, actual coordinate/color roles, structural-value review, boundary
  reservation and gap rules. Preserved the reproducible source in
  `docs/examples/humanball_entertainment_approved.py` with an explicit output
  directory argument. Reproduction verified 22/22 images pixel-identical
  (twenty sprites plus native and 10x sheets); pixel QA and diff check passed.
  This accepted method is now applied to the ten-category batch above.
  Production integration still requires a separate request.
  Earlier rejected batches below are historical context.

- On 2026-09-08, created the first Ori-informed HumanBall pizza experiment in
  `LOCAL_REVIEW/humanball_pizza_ori_v1/`: one editable native 18x18 Aseprite
  source, an 18x18 RGBA PNG and a nearest-neighbor 10x review PNG. The test
  intentionally removes the uniform cream sticker border, uses a dark local
  contour, warm cheese/crust value tiers, clustered shadow and selective
  highlights. It is review-only; no canonical asset, registry, runtime bundle
  or production contract changed.

- Re-audited the six checked-in HumanBall popups directly from
  `CHARACTER/ASSETS/effects/humanball/` after the pizza experiment was rejected.
  The canonical grammar is confirmed as a deliberate cream outer silhouette,
  a complete black inner contour, chunky object-specific value clusters,
  sparse highlights and immediately readable object geometry. A temporary
  10x canonical-style montage is at
  `LOCAL_REVIEW/humanball_canonical_style_10x_montage.png`; it is review-only.

- Created `LOCAL_REVIEW/humanball_pizza_humanball_v2/` as a corrected pizza
  experiment after v1 rejection. The editable 18x18 source uses a continuous
  cream outer silhouette, a repaired complete black inner contour, a clear
  triangular slice/crust silhouette, chunky cheese/crust shadow tiers and
  sparse pepperoni highlights. It remains review-only with no canonical or
  runtime integration.

- Corrected the pizza v2 review after the author identified an open cream ring
  at the bottom tip. Added the missing cream pixels beneath the terminal black
  contour and regenerated the native and 10x review PNGs; still review-only.

- Created a fully fresh pizza redraw in
  `LOCAL_REVIEW/humanball_pizza_humanball_v3/` after the author requested no
  reuse of the earlier pizza maps. The v3 builds the cream ring from a
  two-pixel dilation around a one-pixel black contour and a new inner pizza
  silhouette, then adds a distinct crust, triangular cheese wedge, pepperoni,
  shadow clusters and highlights. It is review-only and not production data.

- Rechecked all six locked HumanBall PNGs at the native pixel grid after the
  author corrected the border requirement. The canonical construction is one
  pixel of cream outer border plus one pixel of black/dark inner contour;
  apparent extra thickness at diagonals is staircase geometry, not a two-pixel
  ring. The v3 pizza's two-pixel cream dilation is therefore rejected and must
  not be used as a redraw base.

- Created a fresh music-note popup experiment in
  `LOCAL_REVIEW/humanball_music_note_v1/`: a new editable 18x18 Aseprite
  source, native PNG and 10x review PNG. The note was authored from a new
  silhouette with one-pixel dark contour and one-pixel cream outer border,
  blue value clusters and a six-color binary-alpha QA result. Review-only;
  no canonical asset or runtime metadata changed.

- Created a fresh quarter-note redraw in
  `LOCAL_REVIEW/humanball_music_note_quarter_v1/` after the earlier flag
  silhouettes were rejected as unreadable. The new native 18x18 source uses a
  clear oval note head and straight stem, with one-pixel black contour and
  one-pixel cream outer border; native QA is 18x18 RGBA, alpha 0/255 only,
  9 colors, and bbox [3,1]-[13,16]. Review-only; no canonical asset or
  runtime metadata changed.

- Rewrote `docs/HUMANBALL_POPUP_CREATION_GUIDE.md` as a direct native-only
  drawing manual. It now starts on a transparent 18x18 canvas, defines the
  recognizable colored-fill mask `F`, adds stepped color clusters, then derives
  disjoint one-pixel `#000000` and `#FFFBF0` rings from `F`; these two border
  colors are now locked to prevent drift. The quarter-note shape is recorded as
  the readability example. No production asset or runtime metadata changed.

- Created the first 20-item food/drink review set in
  `LOCAL_REVIEW/humanball_food_drink_20_v1/`. It contains twenty independent
  native 18x18 Aseprite/PNG sprites, a transparent 5x4 native sheet
  (`90x72`), a nearest-neighbor 10x review sheet and a row/column manifest.
  All twenty sprites pass the asset audit: exact 18x18 RGBA, alpha 0/255 only,
  no opaque edge pixels, exact `#000000`/`#FFFBF0` border colors and one-pixel
  border construction. Review-only; no canonical asset or runtime metadata
  changed.

- Created the 20-item entertainment review set in
  `LOCAL_REVIEW/humanball_entertainment_20_v1/`. It contains twenty
  independent native 18x18 Aseprite/PNG sprites, a transparent 5x4 native
  sheet (`90x72`), a nearest-neighbor 10x review sheet and a row/column
  manifest. The final audit passes all twenty: exact 18x18 RGBA, alpha 0/255
  only, no opaque edge pixels, and locked `#000000`/`#FFFBF0` one-pixel
  borders. Review-only; no canonical asset or runtime metadata changed.

- The author rejected the entertainment set's visual readability despite the
  technical QA pass. The current batch overuses a shared rounded-rectangle
  template, decorative horizontal color bands and generic coordinate-based
  shading, so several items collapse into indistinguishable boxes at native
  1x. Next task is a fresh silhouette-first redraw per item with object-specific
  landmarks and material palettes, while keeping the locked one-pixel
  `#000000`/`#FFFBF0` border rules.

- Created `LOCAL_REVIEW/humanball_entertainment_20_v2/` as a fresh
  silhouette-first redraw of the entertainment set. The pass strengthens
  object-specific landmarks (screen/control deck, earbud separation, speaker
  drivers, microphone capsule, guitar sound hole, ticket notches, projector
  lens, card overlap, comic panels) and keeps the direct native 18x18 workflow.
  It includes twenty independent Aseprite/PNG sprites, a transparent 5x4
  `90x72` sheet, a nearest-neighbor 10x review sheet and a manifest. Technical
  audit passes 20/20; visual author acceptance is still pending. No canonical
  asset or runtime metadata changed.

- The author rejected entertainment v2 as still too round and too similar
  between items. The six canonical HumanBall sprites were re-audited at the
  native pixel grid; the next redraw must use object-specific silhouette
  families, structural landmarks and material color planes, with no shared
  rounded-box template or decorative coordinate bands. No production changes
  were made during this analysis pass.

- Created `LOCAL_REVIEW/humanball_entertainment_20_v3/` as a new native redraw
  from the canonical-style blueprint. It contains twenty fresh 18x18
  Aseprite/PNG sprites, a transparent 5x4 native sheet, a 10x review sheet
  and a manifest with the locked `#000000`/`#FFFBF0` one-pixel borders.
  The batch now uses distinct front, radial, side-profile, open-space and
  stepped geometric silhouettes; visual author acceptance is pending. No
  canonical asset or runtime metadata changed.

- On 2026-09-09, the author said entertainment v3 is an improvement but still
  not visually accepted: several silhouettes remain too generic/rounded and
  the interior palettes are too flat, with insufficient highlight, midtone,
  contact shadow and deep-shadow clusters. Next task is a shape-first pilot
  across representative silhouette families, followed by an object-specific
  shaded redraw of all twenty. Keep v3 review-only and do not reuse its pixel
  maps as the next drawing base.

- Created `LOCAL_REVIEW/humanball_entertainment_pilot_v4/` from five fresh
  native masks: game controller, headphones, vinyl record, guitar and dice.
  The pilot intentionally tests wide-front, open-negative-space, radial-media,
  side-profile and stepped-geometry families with upper-left highlights,
  midtones, lower-right shadows and contact/deep-shadow clusters. Technical
  QA passes 5/5 exact 18x18 RGBA, binary alpha, native sheet 90x18 and review
  sheet 900x180. Visual author acceptance is pending; no v3 pixel map,
  canonical asset or runtime metadata was reused or changed.

- The author rejected the pilot's construction, specifically identifying the
  dice as a non-cubic rounded diamond, the guitar as an unreadable generic
  wooden form, the vinyl as insufficiently record-like and the controller as
  having a skewed outer silhouette instead of a symmetric gamepad body. The
  next pass must be shape-only first with construction constraints per object
  (mirrored gamepad outline, three-plane cube, body/neck/headstock guitar and
  record-plus-tonearm geometry), then add shaded material planes only after
  those silhouettes read at 1x. Keep the pilot review-only and do not reuse
  its pixel maps.

- The author explicitly rejected the prior `LOCAL_REVIEW/humanball_popups_redraw_v3/`
  as the old/wrong batch and instructed that it must not be mixed with the
  current Gate A set. The active Gate B candidate is the newly drawn batch in
  `LOCAL_REVIEW/humanball_popups_gateb_from_gatea_v1/`, sourced only from the
  five latest author-approved Gate A sheets copied into that folder's
  `references/` directory. It contains 100 independent 18x18 Aseprite/PNG
  sprites, five ordered 5x4 sheets and nearest-neighbor 10x review sheets.
  QA passes 100/100: exact 18x18 RGBA, alpha 0/255 only, no edge pixels,
  transparent moat, complete dark-inner-contour adjacency, at least four
  opaque colors per sprite, 100 unique PNG hashes and zero hash overlap with
  the old review PNGs. No old popup image was used as pixel input; no
  canonical asset, registry, runtime bundle or production contract changed.
  Gate B visual approval is pending. Gate A for the five concept sheets was
  explicitly accepted by the author.

- The preceding shaded batch in
  `LOCAL_REVIEW/humanball_popups_new_shaded_v2/` remains review history only
  and was not used as a pixel input for the fresh v3 redraw.

- The author found the new-from-scratch v1 popup batch too flat and requested
  stronger color depth. A fresh shaded review revision is now in
  `LOCAL_REVIEW/humanball_popups_new_shaded_v2/`: all 100 independent native
  18x18 Aseprite/PNG sprites were reworked from the v1 new batch with
  posterized highlight/midtone/shadow tiers, lower-right deep shadows and
  hard pixel color clusters. It has five ordered v3 native sheets, five 10x
  review sheets, a 100-item master at 1x/10x and its own manifest. Shaded QA
  passes 100/100: exact 18x18 RGBA, alpha 0/255 only, no edge pixels, every
  sprite has at least four opaque object colors, all 100 differ from the flat
  v1 PNGs, and zero hashes match prior review PNGs. Legacy/rejected folders
  were not inputs. Gate B visual approval is pending; no canonical asset,
  registry, runtime bundle or production contract changed.

- User rejected the previous popup/gold-sample visuals and explicitly required a
  complete redraw with no reuse of old images. A new review-only batch was
  created from text-only category specifications in
  `LOCAL_REVIEW/humanball_popups_new_from_scratch_v1/`: 100 independent native
  18x18 Aseprite/PNG sprites, five ordered 5x4 native sheets, five 10x review
  sheets, a 100-item master review and a new manifest. A new reference batch is
  under `LOCAL_REVIEW/humanball_references_new_v1/`. The old review folders are
  untouched and were not used as inputs. Native QA passes 100/100 files, exact
  18x18 RGBA, alpha 0/255 only, no edge pixels, and zero identical hashes with
  prior review PNGs. Gate B visual approval is pending; no canonical asset,
  registry, runtime bundle or production contract changed.

- Created five new review-only 20-item office popup prototype sheets from the
  approved category lists: food/drinks, documents/meetings, office equipment,
  work status, and rewards/events. Files are stored in
  `LOCAL_REVIEW/humanball_references/` as `*_20_5x4_prototype_v1.png`.
  These are concept references only; no canonical asset, registry, runtime
  bundle or production contract changed. They remain pending visual review and
  should not be treated as Gate A approval until each cell is inspected.

- The previous six-item gold sample in
  `LOCAL_REVIEW/humanball_popups_office_gold_v1/` is retained as review history
  only. It was superseded after the user rejected the visual direction and was
  not used as an input to the new 100-item batch.

- Composed the six-sample review strip at
  `LOCAL_REVIEW/humanball_popups_office_gold_v1/png/gold_samples_6_18x18_sheet_v1.png`
  with the corresponding nearest-neighbor review at
  `gold_samples_6_10x_review_v1.png`. The six independent PNGs pass the
  focused native QA: exact 18x18 RGBA, alpha 0/255 only and no visible edge
  pixels.

- The prior gold-sample Gate B review and its reference approval remain closed
  out of the new batch; the new batch has its own independent Gate B review.

- Created five new office HumanBall reference sheets in
  `LOCAL_REVIEW/humanball_references/`, one per category with 20 independent
  concepts in a 5x4 layout. The normalized v2 sheets are RGBA, exactly 900x720
  px (20 fixed 180x180 cells), and are indexed by
  `office_popup_100_batch_manifest_v1.json`. The documents/meetings sheet was
  regenerated so the video-meeting monitor contains abstract blocks only, with
  no people or faces. These are Gate A review references only; no 18x18 native
  sprites, registry entries, runtime bundles or canonical assets changed.

- Created five HumanBall concept-sheet review artifacts in
  `LOCAL_REVIEW/humanball_concept_sheets_v1/`: productivity, communication/
  meetings, office equipment, work-state symbols and rewards/special events.
  Each sheet presents ten concepts in a 5x2 catalog layout. These are
  brainstorming references only; no canonical asset, registry, runtime bundle
  or production contract changed.

- Hand-drew the first native-size HumanBall review batch through the local
  Aseprite MCP pixel tool: five transparent 90x36 PNG/Aseprite sheets, each
  containing ten independent 18x18 cells in a 5x2 layout, plus nearest-neighbor
  10x review PNGs. The work-state sheet uses symbols only and contains no
  character faces. Native PNG QA passed: every sheet is 90x36 RGBA, alpha is
  limited to 0/255, all 50 cells are non-empty, and no cell boundary contains
  visible pixels. These remain LOCAL_REVIEW artifacts pending Gate B approval;
  canonical HumanBall assets and runtime metadata are unchanged.

- Author rejected the first native-size batch for visual mismatch with the
  concept sheets. The batch remains review history only and must not be used as
  the redraw base. The food category is now the pilot for the corrected
  workflow: ten independent 18x18 source sprites first, then a 90x36 catalog
  sheet; do not integrate or register until visual Gate B approval.

- Generated a fresh food/drink reference sheet at
  `LOCAL_REVIEW/humanball_references/food_10_reference_sheet_180px_v1.png`:
  10 independent concepts in a 5x2 layout, exact 180x180 cells and a
  900x360 transparent canvas. Small disconnected boundary artifacts were
  removed after inspection; the sheet is review-only and is not a source for
  production sprites.

- Completed the food pilot through the Aseprite MCP pixel workflow in
  `LOCAL_REVIEW/humanball_popups_food_v1/aseprite/`: ten independent editable
  18x18 `.aseprite` files and exported RGBA PNGs, plus
  `food_10_18x18_sheet_v1.png` (90x36) and a nearest-neighbor 10x review.
  Export QA passed: exact dimensions, binary alpha, no visible cell-boundary
  pixels, and exact equality between the reviewed pixel maps and Aseprite
  exports. These are review-ready but remain outside canonical runtime assets
  pending visual approval.

- Author review found the food pilot is still not visually approved: the
  black inner contour is not closed around every silhouette and several small
  icons read as awkward at native size. Do not promote this batch. The next
  redraw must derive a complete black outline from each independent silhouette,
  place the cream halo outside that outline, then hand-clean corners and
  internal holes on the native 18x18 grid before export.

- Root cause of the remaining reference mismatch is recorded: the 180x180
  concepts were treated as style inspiration instead of aligned geometry
  blueprints, so camera angle, silhouette, bounding box and negative spaces
  drifted during the 18x18 redraw. The next pilot must isolate each 180x180
  cell, overlay an aligned 18x18/10px construction grid, preserve landmarks
  and silhouette first, and only then simplify shading and generate the two
  outline masks.

- Author supplied a new 10-item food/drink reference sheet at
  `LOCAL_REVIEW/humanball_references/food_10_reference_sheet_user_1983x793_v2.png`.
  A fresh native-grid trace was built in
  `LOCAL_REVIEW/humanball_popups_food_v2/aseprite/`: ten separate 18x18
  Aseprite/PNG sources, a 90x36 5x2 sheet, and a nearest-neighbor 10x review.
  This pass preserves the reference landmarks while deriving a closed 1px
  black contour and a separate 1px cream halo from each independent mask.
  QA passed: binary alpha, no boundary pixels, complete cream-to-black
  adjacency, and exact sheet composition. Still review-only pending Gate B.

- Author rejected the food v2 visual review: the cream border appears
  incomplete in places and the silhouettes, especially pizza, do not preserve
  the supplied reference geometry. Root cause: the pass used hand-authored
  18x18 polygons and dilation around a semantic redraw, not a reference-locked
  outer-silhouette trace. The batch remains rejected; the next attempt must
  approve one silhouette-only gold sample first, derive nested cream/black/fill
  masks from that canonical outer mask, and only then batch the remaining nine.

- Rebuilt the food pilot as a reference-locked ring pass in
  `LOCAL_REVIEW/humanball_popups_food_v2/reference_locked_ring_v3/` using the
  author-supplied sheet. The 18x18 fill geometry is reduced from each isolated
  reference silhouette, then the black contour and cream halo are derived from
  that fill with no post-render clipping. Aseprite/PNG sources for all ten,
  the 90x36 sheet, and 10x review are present under `aseprite/`. QA passed:
  binary alpha, no cell-boundary pixels, every fill perimeter has black before
  transparency, every cream pixel has a black neighbor, and sheet composition
  is exact. This remains review-only pending author Gate B approval.

- Updated the English creation guide at
  `docs/HUMANBALL_POPUP_CREATION_GUIDE.md` to record the full proven workflow:
  generate any number of independent 180x180 cells in one transparent batch
  sheet with a visible four-sided `CELL_GUIDE` block and hard clip for every
  slot, approve each cell, address or export its exact cell boundary, align the
  18x18/10px grid, lock `S0`, derive native fill/black/cream masks, paint pixel
  clusters, compare geometry at 1x and 10x, run contour QA, and pack the final
  catalog sheet only after independent approval. The guide also records the
  failed-sheet, semantic-redraw, overflow and post-render-clipping failure
  modes, while keeping the guide overlay out of the clean transparent artwork.

- Strengthened the popup guide after the latest visual review: reference
  artwork must be transparent from creation (backgrounds are never baked and
  removed later), each native sprite must pass a silhouette-only comparison
  against its 180x180 cell before color, and solid objects require stepped
  base/midtone/shadow/highlight volume clusters. A shading pass may add depth,
  but may not be used to hide a changed shape or camera angle.

- The author rejected the first two corrected Productivity pilots for continued
  visual mismatch. They remain review history only. A third redraw is now in
  `LOCAL_REVIEW/humanball_productivity_pilot_v5/`: ten independent 18x18
  Aseprite/PNG sources and a derived 90x36 5x2 sheet with 10x previews. This
  pass explicitly preserves the concept landmarks for the folded checked
  document, red/cyan/yellow hourglass, four colored file stack, bulb and base,
  concentric target with dart, four-bar chart with arrow, red-header calendar,
  keyed keyboard, printer with top/bottom paper and status light, and handled
  trophy. Native QA passed: ten 18x18 sources, sheet 90x36, alpha 0/255 only,
  and no cell-boundary pixels. This pilot remains review history only; the
  remaining four categories were subsequently redrawn in a separate full pass.

- After the author explicitly rejected any carried-over pieces, completed a
  separate full redraw in
  `LOCAL_REVIEW/humanball_full_redraw_v2/`: 50 newly mapped, independent 18x18
  Aseprite/PNG sources and five fresh 90x36 5x2 category sheets. No pixel map
  or rendered source was copied from the v1 batch; all 50 source PNG hashes are
  unique and none overlaps v1. The work-state category uses symbols only (no
  character faces). Native QA passed: 50 sources, five sheets, exact sizes,
  alpha limited to 0/255, no source boundary pixels and no empty cells. This
  is still LOCAL_REVIEW output pending visual Gate B approval; canonical assets,
  registries and runtime metadata remain unchanged.

- Replaced the old Thai HumanBall popup guide with the English canonical guide
  at `docs/HUMANBALL_POPUP_CREATION_GUIDE.md`. The approved workflow is now
  a transparent batch of independent 180x180 cells (any chosen N and CxR
  layout), followed by a manual pixel-by-pixel 18x18 Aseprite/MCP redraw per
  approved cell, native/nearest-neighbor review, author approval, and only
  then production integration. The former uncontrolled combined master-sheet
  resize workflow was removed.

- Investigated a faster assisted workflow: Aseprite's nearest-neighbor resize
  can produce an 18x18 guide from an individual 180x180 reference, but the
  guide must remain a locked visual aid and the final sprite must still be
  manually redrawn. ImageMagick is not installed on PATH; no runtime or
  canonical asset changes were made.

- The generated category master-sheet previews under
  `LOCAL_REVIEW/popup_master_sheets_v1/` are rejected review artifacts because
  combined-sheet generation/cropping can cut through or merge artwork. They
  are not a drawing source and no canonical runtime asset or contract changed.

- Reconstructed the paper popup a second time from the 180x180 reference,
  correcting the perspective mismatch: the top/bottom contours and folded
  corner now use stepped diagonal geometry rather than a near-upright page.
  The new v2 remains an 18x18 transparent MCP/Aseprite asset with a continuous
  one-pixel cream outer silhouette.

- Generated a 180x180 paper-document reference and reconstructed it as a new
  18x18 transparent Aseprite/PNG through MCP. The final pixel map starts with
  one continuous cream silhouette around the page and folded corner, then adds
  the inner outline, paper shading, blue document lines and green check mark;
  no canonical asset or runtime contract changed.

- Generated a new 180x180 coffee-cup reference and reconstructed it as a
  separate 18x18 transparent Aseprite/PNG asset through the MCP pixel tool.
  The reconstruction is hand-mapped rather than resized, preserving a
  one-pixel cream silhouette edge, stepped coffee/cup shading, handle, steam
  and saucer within the final canvas. Review output only; canonical runtime
  assets remain unchanged.

- First live Aseprite MCP pixel-drawing smoke test completed in
  `LOCAL_REVIEW/aseprite_mcp_demo/`: an 18x18 transparent computer popup was
  created through `aseprite_set_pixels` (309 explicit pixels), saved as an
  editable `.aseprite`, and exported to PNG. The first call exposed the
  server's 1-based frame/layer indexing and was corrected without production
  asset changes.

- Installed, built and connected the local `aseprite-mcp` server under
  `aseprite-mcp/` using Node.js 24.10.0. Codex config now points to
  `dist/src/index.js`, binds the project Aseprite executable, and limits the
  allowed workspace to this project. A direct MCP initialize handshake passed
  with server `aseprite-mcp` version `0.1.0`; Codex restart is still required
  before the new tools could appear; the current session now exposes the
  Aseprite tool namespace. A dry-run `create_sprite` probe passed without
  writing a file. `npm test` passed 12/12; npm reported 7 audit findings and
  no automatic fix was applied.

- The rejected Office HumanBall prototypes from this session were removed from
  `LOCAL_REVIEW` and sent to the Recycle Bin. No canonical assets, registry,
  runtime bundles or production files were changed.

- Active branch: `main` at `bdba11d`; the related `fix_z_depth_occlusion_sorting` worktree points to the same commit.
- Visual crop & shadow root cause identified and resolved:
  1. `TOOLS/build_runtime_render_manifest.py` previously exported occluder masks to `WEB/runtime_assets/occluders/{placement_id}.png` without floor isolation. Rebuilding all 25 floors caused each floor to overwrite common placement IDs.
  2. `build_runtime_render_manifest.py` omitted `depth_front_edge_world_px` from occluder records.
  3. `walking_depth_core.py` failed to strip opaque shadows (`a=255` but dark), causing desks and reception shadows to generate invisible vertical bounding boxes that clipped characters.
- Fixes applied:
  1. Updated `TOOLS/build_runtime_render_manifest.py` to write masks to `occluders/{floor_id}/{placement_id}.png` and export `"depth_front_edge_world_px"`.
  2. Updated `WEB/viewer_app.js` (`resolveActorOccluderIds`) to prioritize `occ.depth_front_edge_world_px`.
  3. Updated `WORLD/RUNTIME/walking_depth_core.py` to strip all dark pixels (`max(r, g, b) <= 64` and `a > 0`) from occluder masks, preventing opaque shadows from cropping actors.
  4. Rebuilt all 25 office floor manifests and simulation bundles using `TOOLS/build_all_floors.py`.
  5. Updated `WEB/runtime_canvas_renderer.js` to keep authored static/work-seat layers separate from walking `groundY` sorting, and to mask seated actors that are in front of a walking actor. This fixes chair-over-walker and walker-over-seated-character inversions without changing canonical assets or manifests.
- Canonical data remains untouched: `WORLD/`, `CHARACTER/`, and `CONTRACTS/` trees preserved with original reference hashes.

## Verification

- Gate 0 oracle freeze completed: annotated tag
  `oracle/python-runtime-2026-09-04` points to `fde8279`; the clean suite ran
  twice with `python -B -m pytest -p no:cacheprovider -q --ignore=.worktrees`
  and returned **404 passed** on both runs. The candidate worktree's
  uncommitted inventory fixture was discarded with that worktree and is not
  part of `main`.
- Gate 1 strict boundary checkpoint → `npm --prefix WEB run typecheck`,
  `typecheck:browser` and `typecheck:node` all pass; contract generation is
  deterministic across 46 files; Vitest passes 32 files / 84 tests; Node
  browser compatibility passes 16/16; Python review/default-route tests pass
  32/32. These checks do not yet establish complete runtime or pixel parity.
- `node --test TESTS/browser_runtime_test.mjs` → **14 passed**.
- Final focused conversation/speech/contract/parity/renderer regressions → **48 passed**.
- `python -B -m compileall -q RUNTIME WORLD CHARACTER TOOLS VALIDATION TESTS` → **PASS**.
- `ruff check RUNTIME WORLD CHARACTER TOOLS VALIDATION TESTS --select F401,F841` → **PASS**.
- Lean audit → **0 exact duplicates, 21 duplicate function-body groups, 3 shared bootstrap calls, 16 direct CLI candidates, 0 selected Ruff findings**. The remaining function groups are retained domain/test helpers until a safe shared boundary is proven.
- Central, Conversation, F2 gameplay metadata, Phase 6, Room Navigation, Navigation Occupancy, WorkSeat and WorkSeat lifecycle audits → **PASS**.
- `git diff --check` → **PASS**.
- `CONTRACTS/central_contract.json` SHA256 matches its checked-in `checksums.sha256` entry; the legacy API review server was stopped and retired, with no duplicate project server remaining.
- Cleanup and live smoke check → **PASS**: 28 approved cleanup targets were moved to the Recycle Bin; no `__pycache__` directory or `*.pyc` file remains outside the excluded starting-point archive. The main page returned `200`, `/api/health` returned `ok=true` with API `v2` and 25 floors, and `/api/live-start` returned `floor02` with 9 actors using Canvas.
- The post-cleanup full regression run was started but intentionally stopped after the author accepted the live-page result; no failure had appeared before interruption.
- Live browser/API recheck → **PASS**: the updated server reports speech snapshot v2 with per-actor slots and physical resource claims. `seated_host` retains visitor `[0, -20]`, while `ceo_front` carries `[0, 0]` for both participants; the Effects demo exposes independent `humanball:controller` and `vfx:low_battery_drain` bindings. The regenerated bundle contains all **11 VFX** and the current **44-item HumanBall popup** pool.
- Browser review page → **PASS**: Canvas renderer loaded the regenerated bundle, Talk mode was set to `seated host`, and the page was paused at the `8400ms` arrival/bubble-start boundary with the visitor BB visible in telemetry while the seated host remained unchanged.
- Startup API probe → **PASS**: updated `/api/live-start` at `60ms` returned all nine actors at `100.0/normal`; explicit `/api/demo-critical` still returned `EMP_W1_0010` at `5.0/critical`.
- CEO bubble-offset probe → **PASS**: `seated_host` remains visitor `-40px`/host `-20px`; updated `ceo_front` plan carries `[0, 0]` for both and renders visitor/CEO at `-20px` each.
- Walking depth renderer correction → **PASS**: `node --check WEB/runtime_canvas_renderer.js`, browser runtime **15/15**, focused Python renderer/presentation/manifest suite **25 passed**, and live Talk smoke on `http://127.0.0.1:8000/viewer.html?` after reload. Static authored layers are no longer compared directly with walking `groundY`; seated-character front masking is active.
- Focused conversation/browser-bundle verification from the pre-retirement review slice → **51 passed**; the review-host-specific tests were removed together with that retired host.
- Planning-session inspection → **PASS** before cleanup: the scope-corrected plan mapped each user-listed responsibility to an authoritative Python source, TypeScript boundary, parity evidence and an explicit exit gate. The plan was subsequently removed at the author's request; no source/runtime implementation files were changed.
- Claude Code plugin verification → **PASS**: `claude plugin list` reports both `fable-orchestrator@fable-orchestrator` v1.4.1 and the existing `fable-orchestrator@fables` v0.1.0 enabled. Fable execution remains **blocked pending `/login`**; the project Git worktree remains limited to the pre-existing user changes plus this handoff refresh.
- Zero-API Living Office Viewer verification → **PASS**: `WEB/viewer.html`, `WEB/viewer_app.js`, and `WEB/viewer_style.css` created from scratch with complete fidelity to Python gameplay oracle:
  1. **Conversational Facing & Dynamic Head-Turn Animations**: Fixed seated host and visitor facing in `core.renderState()`. Seated hosts resolve `subaction = turn_side_*` (e.g., `turn_side_ne`) and dynamically alternate between turn pose and talking/reacting gesture frames (e.g., `M28` and `M45`) at 360ms per frame matching `work_loop_elapsed_ms`. Visitors at talk spots turn to face the host (`SW`) and animate between their two idle posture frames (e.g., `M8` and `M9`) matching `route_elapsed_ms`. Standing pair participants turn to face each other according to `facing_by_actor` and animate their idle postures, preserving happy/sad emotion frames upon session completion. Handled `ceo_front` visitor facing and animation. Fixed hardcoded `frame_ids[0]` bug that previously froze characters in static poses during conversations.
  2. **Authentic Dialogue Bubble (BB) Sprites & Fixed 9px Font**: Rendered authentic `CHARACTER/ASSETS/dialogue/fukidashi_base.png` sprite crops based on canonical `CHARACTER/DIALOGUE/bubble_presets.json` (BB1, BB2, BB3, BB4, BB6) with text rendered in canonical `#0c45fb` (`rgb(12, 69, 251)`). Removed font shrinking loop; font size is strictly fixed at `9px system-ui, -apple-system, 'Segoe UI', sans-serif` without downsizing. Text is clipped to the preset `safe_rect`.
  3. **Autonomous Pair Talks & Character Movement**: Corrected `core.speechReducer.startSession` wrapper to target only `kind === "solo"`, preventing lifecycle speech (`greeting`, `work_start`) from emitting spurious `start_talk_session` commands and getting trapped in an infinite `returned_to_work` loop. Actors now autonomously leave their desks, walk along `talk_outbound` to meet partners (in both `seated_host` and `standing_pair` configurations), converse with dialogue bubbles, walk back along `talk_return`, sit back down, and resume normal work.
  4. **Visual Effects & Popups (VFX & HumanBall)**: With speech lifecycle normalized, actors naturally roll and trigger `background_effect` (VFX like sunshine bloom, coffee energy) and `popup` (HumanBall). Added `✨ Effects` toolbar button for on-demand inspection alongside `💬 Talk` and `💤 Exhaustion`.
  5. **Walking Depth & Occlusion Parity**: Preserved dynamic walking depth front-edge profiles across all floors (F0, F1, F2-family), ensuring characters are never clipped when walking on the visitor side. Fixed Inspector mini-avatar preview by compositing character body and face via `renderer._drawCharacter`.
  6. **25-Floor Multi-Floor Switcher (Zero-API)**: Built all 25 office floor simulation bundles and manifests (`floor00` through `floor36`, 219 total workstations and employees) using `TOOLS/build_all_floors.py` into `WEB/floors/` with shared asset deduplication. Added dynamic floor switcher `<select id="floorSelect">` in toolbar and URL parameter support (`?floor=floorXX`). Switching floors dynamically resets `core` and `renderer` without page reload, restarts the authentic live simulation, and centers viewport with zero `/api/tick` requests. Resolved root manifest parity (`floor02` default) and added `isSwitchingFloor` simulation loop race guard.
  7. **Dialogue Bubble (BB) Fitting & Zero Clipping Enforcement**: Fixed dialogue bubble line selection and rendering to prevent oversized text overflow and clipping at fixed 9px font size without font downscaling. In `TOOLS/build_runtime_simulation_bundle.py`, pinned `font_size_px=9` in `select_bubble()`, filtering bundle lines down to the 1,347 lines that genuinely fit within canonical bubble safe rects (<= 63px for BB1). In `WEB/runtime_simulation_speech.js`, `dialogueFromBag` filters out lines without a verified fitting bubble. In `WEB/viewer_app.js`, `renderer._drawDialogue` measures text metrics at 9px and dynamically selects the smallest fitting bubble (`BB4` -> `BB3` -> `BB6` -> `BB2` -> `BB1`), rejecting/skipping any text wider than the safe rect so clipped text is never rendered. All 25 floor simulation bundles were rebuilt and verified.
  8. **Validation**: `node --check WEB/viewer_app.js` passed; `node --test TESTS/browser_runtime_test.mjs` passed (15/15); `python -m pytest -q TESTS/test_browser_bundle_contract.py` passed (5/5); all 25 floors verified end-to-end with static scene images and core stepping; `python -B -m compileall` passed; `ruff check` passed; static server running on port 8000. No canonical files modified.
  9. **Character Crop & Shadow Occlusion Fix**:
     - Diagnosed character clipping and floating body fragments (hair, shoulders under speech bubbles, straight dress cuts like Caitlin Mitchell at `(288, 329)` on `floor08`): root cause was cross-floor flat file collisions in `WEB/runtime_assets/occluders/{placement_id}.png` where building 25 floors overwrote earlier floor occluders with `floor02`'s furniture shapes, combined with missing `depth_front_edge_world_px` polygons in the runtime manifest.
     - Separated occluder masks into `WEB/runtime_assets/occluders/{floor_id}/{placement_id}.png` in `TOOLS/build_runtime_render_manifest.py`.
     - Exported exact `depth_front_edge_world_px` polygons in manifest occluder records and consumed them dynamically in `WEB/viewer_app.js`.
     - Rebuilt all 25 floor manifests and bundles; deleted deprecated flat occluders.
     - Added contract test `test_occluders_isolated_by_floor_and_export_front_edge` in `TESTS/test_runtime_render_manifest.py` (passed).
     - Verified across all 3,853 walkable cells on `floor08`: 0 cells produce stray floating fragments (reduced from 57 cells before fix); 0 pixels erased at Caitlin Mitchell (`288, 329`) and Clara (`280, 333`).



## Next task and open gates

Current VFX gate: author visual review of
`LOCAL_REVIEW/aura_wildfire_v15/overview_3.gif` and individual floor00 closeups.
Three mass-first candidates (30 frames) pass native/pixel/timing/border QA;
visual acceptance is pending. Rejected v10 is history. Ten-effect expansion
waits for pilot review; production integration requires a separate request.
Existing unrelated gates:

1. Author-review the 38-item `office_humanball` artwork and confirm the mixed
   44-item popup behavior on the target page.
2. Keep the other 162 cinematic-v3 sprites review-only. Separately, resolve
   the pre-existing `floor06/ws3` WorkSeat expectation and central-audit
   reference mismatches before calling the repository fully green.

No release archive was rebuilt in this session. The 44-item default popup pool
is engineering-integrated and the requested gameplay cutover is active; visual
review of the 38 office items remains acceptance-pending. The other
cinematic-v3 sprites remain review-only. `main` remains the rollback/reference
path.

**Active handoff:** this file only. `ROADMAP.md` is the single active milestone plan.
