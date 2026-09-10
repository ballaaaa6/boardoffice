# Pixel VFX Creation Guide

This guide documents the repeatable native-pixel workflow used for the
`core_charge_blue_v4` review asset and its `floor00` scene preview. It is the
recommended process for creating future VFX without breaking pixel scale,
runtime contracts or scene composition.

## 1. Current VFX architecture

VFX are authored RGBA animation frames. They are not procedurally regenerated
at runtime. The registry identifies the effect, its frames and placement; the
runtime loads those frames and advances them by time.

Key files:

- `CHARACTER/EFFECTS/gds_effects_v1.json` — effect IDs, canvas, frame order,
  timing, anchor and layer rules.
- `CHARACTER/ASSETS/effects/<effect_id>/` — canonical native PNG frames.
- `CHARACTER/RUNTIME/effect_renderer.py` — frame loading, looping and derived
  direction transforms.
- `CHARACTER/RUNTIME/presentation_renderer.py` — character/VFX composition.
- `RUNTIME/work_seat_core.py` — work-scene composition.
- `WEB/runtime_canvas_renderer.js` — browser rendering path.

The current VFX canvas is `33x65` native pixels. The standard placement uses
`character_work_origin` and renders the effect behind the character.

## 2. Standard workflow

### A. Study the existing language first

1. Read the effect registry and inspect `effect_order`.
2. Inspect all four source frames of `fire_original`; it is the main reference
   for mass, silhouette and frame-to-frame flame motion.
3. Inspect the other effects to understand the existing visual vocabulary:
   wind uses flowing ribbons, thunder uses a dark mass and bright cracks, and
   bloom uses a concentrated luminous volume.
4. Review the effect in a real scene, not only in an isolated sheet.

Lock these values before drawing:

| Item | Standard |
|---|---|
| Canvas | `33x65` native pixels |
| New-loop length | 10 frames |
| Timing | `240ms/frame`, `2400ms` loop |
| Alpha | Only `0` or `255` |
| Anchor | `character_work_origin` |
| Layer | Behind the character |
| Directions | Draw primary sources; derive supported directions by mirroring |

### B. Design motion before color

A readable charging aura should contain at least three layers:

1. **Core/envelope** — a bright inner volume that communicates energy around
   the character.
2. **Primary silhouette** — the main shape that defines the effect, such as
   rising curved flames or a pressure shell.
3. **Secondary currents** — offset ribbons, tongues, sparks or arcs that add
   depth and prevent the loop from feeling mechanically predictable.

Useful motion rules:

- Do not scale the entire image up and down as one object. Move the crown,
  sides and core on different phases.
- Preserve part of the main mass so the character remains readable.
- Vary the height and bend of each flame tip.
- Use glints and cracks only in selected frames.
- Keep the last frame close enough to the first frame for a clean loop.
- Avoid repeating identical triangular edge shapes.

For a blue charging aura, the proven direction is a pale cyan/white inner
volume, several cobalt/blue outer tiers, unequal rising crowns, offset side
currents and short-lived white glints.

### C. Draw on the native grid

Always draw at `33x65`. Enlarged images are review outputs only.

- Keep a transparent moat around the silhouette where possible.
- Avoid vector rasterization or anti-aliasing.
- Use a deliberate deep-blue → blue → cyan → pale-cyan/white palette.
- Use dark palette colors for recesses; do not use partial alpha.
- Make every frame change intentionally, rather than adding independent random
  noise.
- Keep the drawing source and exact pixel payload so the asset can be rebuilt.

Recommended review directory:

```text
LOCAL_REVIEW/<effect_name>/
  drawing.js
  pixels.json
  core_charge.aseprite
  frame_00.png ... frame_09.png
  sheet_native.png
  sheet_4x.png
  charge_native.gif
  charge_6x.gif
  verify_exports.py
  README.md
```

### D. Write the artwork into Aseprite

Create a `33x65`, 10-frame, `240ms` RGB sprite with Aseprite MCP, then write
the native pixels frame by frame. MCP frame and layer indices are 1-based:

```text
frameIndex = 1..10
layerIndex = 1
```

On Windows, split large pixel payloads into chunks of roughly 65 pixels to
avoid command-line length failures. Explicitly write transparent pixels when
removing old artwork.

Export the native sheet without Aseprite scaling:

```powershell
& '.\aseprite\portable-v1.3.7\aseprite.exe' -b `
  'LOCAL_REVIEW\<effect>\core_charge.aseprite' `
  --sheet-columns 5 `
  --sheet 'LOCAL_REVIEW\<effect>\sheet_native.png' `
  --data 'LOCAL_REVIEW\<effect>\frames.json'
```

Aseprite `--scale` may smooth the image. Generate enlarged reviews with
Pillow `Image.Resampling.NEAREST` only.

### E. Validate before scene placement

Every candidate must pass:

- All frames are exactly `33x65`.
- There are 10 frames and all are unique.
- Alpha values are limited to `0/255`.
- The GIF has 10 frames at `240ms/frame` and loops after `2400ms`.
- Decoded GIF pixels exactly match the exported PNG pixels.
- The silhouette does not overflow the canvas.
- Every native sheet cell matches `pixels.json`.
- The native 1x and enlarged nearest-neighbor sheet have been visually checked.

`LOCAL_REVIEW/core_charge_blue_v4/verify_exports.py` is the reference QA
script. Passing automated QA does not replace visual review.

### F. Review with a character and a real scene

Use two review levels:

1. **Character-only crop** — verify anchor, scale, occlusion and readability.
2. **Full scene** — use `CentralGameCore.render_floor_with_work_effects` and
   apply the candidate to every assigned character on at least one floor.

The completed examples are:

```text
LOCAL_REVIEW/core_charge_blue_v4/floor00_first_character_gif/
LOCAL_REVIEW/core_charge_blue_v4/floor00_full_scene_gif/
```

Check that:

- The effect stays behind the character.
- The anchor does not float above the head or below the feet.
- The scale works for multiple characters and directions.
- Desk, chair and foreground draw order remains unchanged.
- Every actor receives the effect without incorrect overlap.
- The effect color does not reduce scene readability.

For unapproved previews, inject the candidate in memory as the full-scene
review script does. Do not modify the registry just to make a GIF.

## 3. Direction handling

The renderer supports `NW`, `SE`, `SW` and `NE`. Usually, author source frames
for the primary directions and declare derived directions in the registry:

```json
"SW": {
  "source": "derived",
  "derived_from": "SE",
  "transform": "mirror_y"
}
```

Use the renderer's established transform rather than inventing a new mirror
operation in production. Check every direction with a real character because
asymmetric effects may not mirror cleanly.

## 4. Production integration after approval

Only integrate after explicit visual approval and a separate integration
request:

1. Copy source PNGs into `CHARACTER/ASSETS/effects/<effect_id>/`.
2. Add the asset records and hashes to the asset registry.
3. Add the effect record to `CHARACTER/EFFECTS/gds_effects_v1.json`, including
   canvas, animation, frame asset IDs and render placement.
4. Decide whether `effect_order` and the automatic VFX bag should change.
5. Regenerate manifests and browser bundles.
6. Run renderer tests, the full Python suite and relevant validation audits.
7. Rebuild the full-scene GIF through the runtime path and request final review.

Do not treat a good-looking GIF or a passing manifest audit as author approval.
Visual acceptance and production integration are separate gates.

## 5. Do not do these things

- Do not edit canonical `fire_original` while experimenting.
- Do not package GIFs or review sheets as runtime assets.
- Do not use an enlarged preview as the source for native drawing.
- Do not use smooth resizing or anti-aliasing.
- Do not use partial alpha to hide bad edges.
- Do not make every frame identical and translate the whole group.
- Do not change runtime placement to compensate for an incorrectly anchored asset.
- Do not close the milestone before explicit visual acceptance.

## 6. Submission checklist

- [ ] Existing effects and reference grammar were inspected.
- [ ] Canvas, frame count and timing are locked.
- [ ] Artwork is native-pixel with binary alpha.
- [ ] Core, primary silhouette and secondary currents are present.
- [ ] Frames change intentionally and loop cleanly.
- [ ] Aseprite source, pixel payload and drawing source are saved.
- [ ] Size, alpha, uniqueness, timing and exact-pixel QA passes.
- [ ] Native and nearest-neighbor enlarged reviews were inspected.
- [ ] Character-only crop was reviewed.
- [ ] Full-scene compositor review was completed.
- [ ] Runtime integration waits for explicit approval.
