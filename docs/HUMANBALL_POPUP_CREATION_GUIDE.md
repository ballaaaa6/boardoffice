# HumanBall Popup Pixel-Art Drawing Guide

This is the direct workflow for drawing a HumanBall popup. Every popup starts
on a transparent native `18x18 px` canvas and is authored pixel by pixel.
The sprite must be readable at native `1x`, use hard pixel edges, and carry its
`#FFFBF0` and `#000000` border in the exported PNG.

**Author-approved method: 2026-09-09.** The entertainment v6 sheet is the
accepted example for construction, line treatment and material shading.
The author accepted the v5 construction language, then required a distinct
modern controller instead of a duplicate of the original controller. The
complete v6 set was subsequently accepted. Earlier rejected entertainment
versions are not drawing specifications.

The reproducible source is
[humanball_entertainment_approved.py](examples/humanball_entertainment_approved.py).
Section 9 documents how each of the twenty objects was actually built.
The workflow starts directly on the native grid; no generated concept image
or large-image downsampling stage is required.

## 1. The locked HumanBall look

- Compact, readable game pixel art.
- One recognizable silhouette before small decoration.
- Stepped diagonals and intentional pixel clusters.
- Hard color tiers instead of smooth digital gradients.
- A complete `#FFFBF0` outer cream edge exactly `1 px` wide.
- A complete `#000000` inner contour exactly `1 px` wide.
- At least `1 px` of transparent moat outside the `#FFFBF0` edge whenever the
  shape fits.
- No renderer-added outline, glow, blur or smoothing.

The border is part of the artwork. It must exist in the final PNG, not in the
browser, canvas or game renderer.

## 2. Direct drawing workflow

Follow these steps for every popup.

### Step 1 — Start the native canvas

1. Create a new `18x18 px` RGBA sprite.
2. Keep the background fully transparent.
3. Leave room for the outer `#FFFBF0` edge and a transparent moat. Do not let the
   final border touch the canvas edge unless the shape absolutely requires it.
4. Place every final pixel explicitly on the native grid.

Coordinates are zero-based: `x=0..17`, `y=0..17`. Reserve both outline
layers **before** drawing: the fill must stay inside `x=2..15, y=2..15`
for complete unclipped rings. Use `3..14` if a one-pixel transparent moat
is also required. The approved set uses both layouts; a complete cream
edge may touch the canvas boundary. Never clip the dilation to the canvas
and then declare its border complete.

Suggested working files:

```text
LOCAL_REVIEW/humanball_popups/<popup_id>_18x18.aseprite
LOCAL_REVIEW/humanball_popups/<popup_id>_18x18.png
LOCAL_REVIEW/humanball_popups/<popup_id>_18x18_review.png
```

### Step 2 — Draw the recognizable colored-fill silhouette

Create the colored subject as a closed pixel mask named `F`. `F` contains only
the subject's colored pixels before the `#000000` and `#FFFBF0` rings are added.

At this stage, decide only the main shape:

- overall mass and proportions;
- top, bottom, left and right extents;
- main axis or tilt;
- stepped corners and diagonals;
- holes, gaps and detached parts;
- the landmark that makes the subject identifiable.

Keep the silhouette large enough to read at `1x`, but small enough to leave the
transparent moat after both rings are added.

### Step 3 — Pass the readability check before decorating

Look at the filled `F` at native `1x`. If the subject is not immediately
recognizable, fix the silhouette now. Do not try to rescue an unclear shape
with highlights, shadows or extra pixels.

Inspect both the solid silhouette and a grayscale structural drawing.
The latter includes identity-bearing internal divisions: a cube needs its
three face boundaries, a record needs its label and spindle hole, and a
controller needs controls. A solid silhouette alone cannot distinguish
every object. Structural marks must work before material highlights are added.

Choose the view that fits the pixel budget: the accepted guitar is upright,
the controller is front-facing, the arcade cabinet is side-facing, and the
dice is a projected three-face cube. Build meaningful parts in that view.
Do not begin every item with a rounded rectangle and decorate it afterward.

For symmetric manufactured bodies, mirror the **shape mask**, not the colors:
`(x,y) -> (17-x,y)` on this canvas. The controls and illumination can differ
between sides. The v6 controller checks this equality programmatically.

For simple symbols, use the simplest familiar structure first. A music note,
for example, starts as a clear oval note head plus a straight stem. Add a flag,
beam or accent only if the plain symbol already reads correctly; remove any
part that makes it look like a hook or an abstract blob.

### Step 4 — Choose a compact palette

Use approximately `4-10` opaque colors, depending on the subject:

```text
#000000 contour
deep shadow
shadow or side-plane midtone
base color
light midtone
highlight
one or two small accents when necessary
```

The border colors are locked and must not be substituted:

```text
black contour = #000000
cream edge    = #FFFBF0
```

### Step 5 — Fill the base plane

Fill the largest, clearest color planes inside `F`. Keep all color pixels
inside the silhouette. The base fill must still make the subject readable
before shading is added.

### Step 6 — Add hard-edged shading

Use stepped clusters to give the subject volume:

1. Add a readable shadow cluster, usually toward the lower-right unless the
   object's light direction says otherwise.
2. Add a midtone or side plane when the shape has enough area for it.
3. Add a few selective highlights, usually toward the upper-left.
4. Preserve rims, folds, holes, faces, panels, handles and overlaps with the
   value changes rather than with smooth gradients.

Shading rules:

- Use small deliberate clusters, commonly `1-4 px`.
- Use discrete tonal steps, not a continuous gradient.
- Keep the deepest values near overlaps and the contour.
- Avoid noisy isolated pixels.
- Do not paint a continuous white shine around the subject.
- A flat symbol may use fewer colors, but a solid object needs visible
  base/shadow/highlight separation.

## 3. Build the one-pixel border

Derive both rings from the final colored-fill mask `F`. This keeps the border
continuous and prevents gaps or accidental thick sections.

`dilate8(X)` means adding the eight neighboring pixels around every pixel in
set `X`, one native pixel outward.

```text
F  = cleaned colored-fill silhouette
B  = dilate8(F) - F                       (#000000 ring, 1 px)
U  = F ∪ B
C  = dilate8(U) - U                       (#FFFBF0 ring, 1 px)
```

Render from back to front:

```text
transparent background
#FFFBF0 cream ring C
#000000 black ring B
colored artwork F
```

The three masks must be disjoint. The `#FFFBF0` ring must never overwrite the
`#000000` ring or the colored artwork. Do not draw a global outline around the
finished multicolor image and do not use a two-pixel cream dilation.

### Border rules

- `#000000` contour: exactly `1` native pixel between the colored fill and the
  `#FFFBF0` edge.
- `#FFFBF0` edge: exactly `1` native pixel outside the `#000000` contour.
- Both rings must follow every exposed side of the silhouette.
- Every stepped corner and diagonal endpoint must be checked individually.
- Apparent extra thickness at a diagonal is staircase geometry, not permission
  to add another ring.
- The `#FFFBF0` edge must be complete around the entire connected subject.
- A detached part gets its own complete `#000000` and `#FFFBF0` rings.
- A deliberate hole stays transparent; keep its inner dark rim and do not let
  `#FFFBF0` pixels flood into the hole.
- Never create a rectangular `#FFFBF0` frame around the `18x18` canvas.
- Never share a border with another sprite.

For detached parts or tight holes, inspect the final composite as well as F.
Two expansions consume two pixels on each side of a gap; leave at least five
empty columns between facing fill edges to retain one transparent column.
If an essential opening closes, widen or reposition the fill geometry and
recompute both rings. Do not erase arbitrary ring pixels afterward: that
would invalidate the complete-ring construction and its audit.

## 4. Native pixel-art rules

- No anti-aliasing.
- No semi-transparent pixels.
- No blur or soft glow.
- No bilinear, bicubic, Lanczos or other blended scaling.
- Preview enlargement uses nearest-neighbor only.
- Use stepped diagonals, not smooth vector curves.
- Use asymmetry for an intentional view or pose; keep symmetric object bodies
  symmetric. Uneven construction is not a substitute for a handmade feel.
- Simplify by importance; do not squeeze every tiny detail into `18x18`.
- Remove any pixel that does not improve recognition, volume or structure.

For browser or canvas previews, use:

```javascript
ctx.imageSmoothingEnabled = false;
```

The enlarged preview is only for inspection. The native `18x18` PNG remains
the source asset.

## 5. Review order

Review in this order so a large preview cannot hide a bad native shape:

1. Native `1x`: confirm that the subject is recognizable in actual use.
2. Native grid: inspect every `#000000` and `#FFFBF0` border pixel.
3. Nearest-neighbor `10x`: inspect clusters, stepped corners and accidental
   holes.
4. Return to native `1x`: remove details that reduce readability.

Do not approve an unclear sprite because it looks attractive at `10x`. The
native view is the deciding view.

## 6. Technical checklist

- [ ] Canvas is exactly `18x18 px`.
- [ ] File is RGBA PNG.
- [ ] Alpha contains only `0` and `255`.
- [ ] Background is transparent.
- [ ] A transparent moat remains outside the `#FFFBF0` edge wherever possible.
- [ ] The colored silhouette `F` is closed and recognizable at native `1x`.
- [ ] `B = dilate8(F) - F` is the only `#000000` ring.
- [ ] `C = dilate8(F ∪ B) - (F ∪ B)` is the only `#FFFBF0` ring.
- [ ] `#000000` and `#FFFBF0` are each exactly one native pixel wide on
      straight runs.
- [ ] `#FFFBF0` and `#000000` do not overwrite each other or the colored fill.
- [ ] Every exposed side, staircase corner and detached part is bordered.
- [ ] Deliberate holes remain transparent and have the intended dark inner rim.
- [ ] No anti-aliasing, semi-transparency, blur or smoothing is present.
- [ ] No floating pixels, accidental holes or stray colors remain.
- [ ] The sprite reads correctly at native `1x`.
- [ ] The `10x` preview uses nearest-neighbor enlargement only.

## 7. File and approval flow

Keep the working Aseprite file, native PNG and enlarged review PNG together in
`LOCAL_REVIEW` until the visual result is approved.

After approval only:

Visual acceptance approves the artwork. Perform the following integration
steps when production integration is also requested; updating this guide
does not itself authorize registry or runtime changes.

1. Copy the standalone PNG to:

   ```text
   CHARACTER/ASSETS/effects/humanball/<popup_id>.png
   ```

2. Update the HumanBall registry or metadata only when the popup is being
   formally added.
3. Regenerate bundles when required.
4. Run the relevant project validation checks.
5. Review the popup in the live runtime.

## 8. Definition of done

A popup is ready for production consideration when:

1. Its main silhouette is recognizable at native `1x`.
2. Its `18x18` canvas and transparent moat are correct.
3. Its base, shadow, midtone and highlight clusters have clear separate jobs.
4. Its `#000000` contour is exactly one pixel.
5. Its `#FFFBF0` edge is exactly one pixel and completely surrounds the
   subject.
6. Its `F`, `B` and `C` masks are disjoint and border gaps are closed.
7. Its holes and detached parts have the intended negative space and contour.
8. Its alpha and hard-edge technical checks pass.
9. It reads correctly at native `1x` and survives the `10x` inspection.
10. The author has approved the visual result.
11. Production integration and runtime validation have passed.

## 9. How the accepted twenty objects were drawn

### Construction tools and drawing order

The accepted implementation uses Pillow as a native pixel drawing tool.
`ImageDraw.line`, `rectangle`, `polygon` and `point` use integer coordinates;
there is no smoothing or high-resolution source reduction. Rectangle and
line endpoints are inclusive. `rows()` draws explicit horizontal spans
`(y, x_start, x_end)` for stepped curves and narrow parts. Polygons are used
for intentionally angular parts and projected planes, not as a shared template.

For each item:

1. Choose its view, main axis, proportions and essential opening/overlap.
2. Draw the body and appendages inside the reserved fill area.
3. Add structural divisions, such as neck/body, three cube faces or page spine.
4. Paint material planes, then compact highlights and contact shadows.
5. Add the few identity-bearing controls, holes, pips or symbols that fit.
6. Extract F from all nontransparent subject pixels and derive B and C.
7. Render C, B, F, inspect at native size, then at nearest-neighbor 10x.
8. Pack the exact native PNG pixels into the sheet only after individual review.

The final alpha mask includes every subject part and structural mark.
A detail outside the intended body changes F, so inspect geometry again
after adding details. Only the two border colors are globally locked;
material palettes below document this approved set and may vary in new objects.

### Per-object construction and color recipes

Coordinates below describe the subject before its two outline rings.
Color roles refer to actual painted regions, not automatic gradients.

| # / object | Geometry and identifying marks | Material, light and shadow used |
|---|---|---|
| 01 Game controller | Front-facing modern body with narrow bridge and two angled handles. Top shoulders at `y=4`; bridge `x=4..13, y=5..6`; wide middle `x=3..14, y=7..8`; handles separate from `y=9` and slope outward through `y=12`. Mirror the fill about `x=8.5`. Two `2x2` analog pads at `(5,7)` and `(11,7)`, D-pad above left, small buttons above right. | Shell `#46677B`, upper shoulders `#A3D8DA`, undersides/handles `#294454`, analog recesses `#172A39`. Tiny orange `#FFB34C` and coral `#E87150` controls. This is deliberately different from the original broad, short controller. |
| 02 Handheld console | Wide shell `x=3..14, y=6..11`, with shorter top and bottom rows. Inset screen `x=6..11, y=6..10`; D-pad on left, two buttons on right. | Shell `#936CC4`, top `#C6A5E6`, bottom `#5E418B`; screen `#263B57` with cyan `#69B8BF` and `#397387` reflections. Yellow/pink buttons distinguish the controls. |
| 03 Arcade machine | Tall side-view polygon: marquee overhang, screen sloping inward, control deck projecting at `y=10`, tall base to `y=14`. Draw screen and deck as separate polygons. | Cabinet `#BE475A`, right base `#6D2C49`, control deck `#EC8290`; marquee `#FFC677`/`#FFE4A2`; recessed screen `#20394B` with `#84D6CE` reflection. Bright rows represent actual ledges, not decoration across the whole cabinet. |
| 04 Joystick | Stepped ball at `y=3..6`, two-pixel shaft `x=8..9, y=7..10`, trapezoid base from `(5,11)` to `(14,13)` and lower edge at `y=14`. | Ball `#E75A52`, upper-left `#FFAD83`, underside `#972F45`; shaft `#53667D`/`#BAC6D6`; base `#357EAD`, lip `#80C7D5`, bottom `#214762`, one yellow button. |
| 05 Headphones | Preserve the accepted open arch: top `x=6..11, y=3`, wider row at `y=4`, side arms down to `y=7`. Cups `x=3..5` and `12..14`, `y=8..12`. The central gap remains visibly open after outlining. | Band `#8067BC` with `#CCB6F1` upper-left light; cups `#7452A4`, brighter outside faces, inner pads `#352B57`, small teal lower accents `#58B5AD`. |
| 06 Earbuds | Two independent buds based at `(3,4)` and `(11,6)`. Each has a `3x3` head, then a two-pixel stem extending down six pixels from its origin. Stagger their height and preserve separation. | Head `#C8E5DE`, upper edge `#EFF5DD`, speaker edge `#396B7D`; stem `#7AB5B9`, right side `#3D7688`. |
| 07 Speaker | Upright rectangular cabinet `x=5..12, y=3..14`. Inset front panel `x=6..10`; small upper driver and larger stepped lower driver. The two drivers, not cabinet rounding, establish identity. | Wood `#A76B3C`, top `#EAB36D`, left `#CB9054`, right `#644630`; front `#344650`, drivers `#141E2B`/`#172A34`, small cone reflections `#688A96`/`#A1C5C3`. |
| 08 Microphone | Vertical capsule `x=7..10, y=2..7`, short grille marks at `y=4,6`, U-shaped cradle around it, stem at `x=8..9`, and narrow base at `y=14`. | Capsule `#91B5C9`, top light `#E4EFE8`, lower side `#49677F`; dark grille `#31465E`; cradle `#66849C`, stem has a light left side and dark right side. |
| 09 Music note | Upright two-pixel stem `x=10..11, y=3..11`; stepped oval head widens leftward at `y=11..14`. Keep the plain quarter-note form. | Stem `#A957B7`, head `#B663BD`, left stem `#E0A3DF`, small head highlight `#E8B4E5`, lower-right head `#743378`. |
| 10 Vinyl record | Standalone circular disc using row spans: narrow top/bottom `x=7..10`, widest middle `x=3..14`. Small central stepped label and one dark spindle pixel, plus two short groove/reflection arcs. The accepted design has no tonearm. | Disc `#26334D`, lower-right `#151F34`; grooves `#687899`, `#596A8D`, `#425474`; label `#D3647B`, light `#F8B093`, shadow `#9A405E`, spindle `#141D31`. |
| 11 Guitar | Upright acoustic construction: headstock `x=8..9, y=2..4`, narrow neck to `y=8`; upper bout `x=6..11`, waist narrows to `x=7..10` at `y=10`, lower bout reaches `x=5..12` at `y=12..13`. Sound hole `2x2` at `(8,9)` and horizontal bridge at `y=13`. | Wood body `#CC8C48`, upper-left bout `#F0C378`, lower-right and bottom `#85512E`; neck `#D6A265`, headstock `#AD713C`, sound hole `#3D2B25`, bridge `#513726`. |
| 12 Movie ticket | Horizontal ticket `x=3..14, y=6..11`. Inset both sides to `x=5..12` at `y=8..9` to create actual edge notches. Three separated perforation dots at `x=11`; a small red cross-like emblem. | Paper `#E6B856`, top `#FFE0A0`, bottom `#B37B3B`, perforations `#815038`, emblem `#B94C52`. Do not describe the tiny emblem as detailed lettering. |
| 13 Popcorn | Tapered carton from `x=4..13, y=8` to `x=6..11, y=14`. Five small kernel clusters above and overlapping the rim; carton stripes follow its taper. | Carton `#C64F50`, bottom `#873345`; stripes `#F1C684`/`#FFE3A0`; kernels `#F6D48B`, top-left pixels `#FFF0BB`, bottom-right `#CE9F51`. |
| 14 Film reel | Small stepped disc ending near `y=11`; four `2x2` dark reel openings around a tiny hub. A short bent film tail extends down-right to `y=14`. The holes and tail distinguish it from vinyl. | Metal `#93A7AE`, upper-left `#D9E6DC`, lower-right `#546878`; openings `#2E3C4C`, hub `#E0B16D`, tail `#798C99`/`#CEDAD4`. |
| 15 Projector | Side-view box `x=4..11, y=7..11`; two small reels above at `x=5` and `10`; lens extends right to `x=14`; two short feet below. | Body `#579495`, top `#A0D3BE`, bottom `#345D70`, dark vent `#2D5261`; reels `#AAB9B8` with dark hubs, lens `#59758A` and bright rim `#9FC5D0`. |
| 16 Playing cards | Draw the tilted blue rear card first, then the cream front card `x=7..14, y=5..14`. A small red heart and corner marks sit on the front card. Keep the visible rear edge and overlap. | Back `#B4C7D8`/`#426E94`, front `#E5D8B6`, top `#FFF0CA`, right edge `#AC987B`, bottom `#BBA689`, suit `#BD4D58`. |
| 17 Dice | Three polygons share `(8,8)`: top `[(8,2),(14,5),(8,8),(3,5)]`, left `[(3,5),(8,8),(8,15),(3,11)]`, right `[(8,8),(14,5),(14,11),(8,15)]`. Draw the Y-shaped face divisions, then 1/2/3 pips on the visible faces. | Top `#F1D591`, left `#CE9D55`, right `#93633C`; shared edges `#735135`/`#65452E`, left reflection `#E5BD75`, pips `#45352C`. The face values and shared edges establish the cube. |
| 18 Chess pawn | Stepped head `y=2..5`, wider collar `y=6`, narrow shaft `y=7..8`, body gradually widening through `y=12`, flat plinth `x=4..13, y=13..14`. | Body `#8C9BAC`, upper-left head/collar/plinth `#D1DCE0`, lower-right body and base `#4B5B76`. Highlights on collar and plinth are actual horizontal ledges. |
| 19 Puzzle piece | Main rectangle `x=6..11, y=6..13`; top tab `x=8..10, y=3..5`, right tab `x=12..14, y=8..10`; left upper/lower blocks surround a deep socket. Preserve the socket after both rings. | Base `#58AA87`, top/left `#A4DCA1`, tab light `#ACE0AB`, interior light `#82C79C`, underside and right edges `#2E725F`. |
| 20 Comic book | Two angular page polygons meet at a central valley around `x=8..9`, descending to `y=14`. Left page contains a red panel; right page a blue speech balloon with a one-pixel tail. Spine and page overlap establish the open book. | Left page `#E7C584`, right `#EDE2BC`, top edges `#FFF0C5`/`#FFF3D5`; spine `#865D48`/`#BD9E77`; panel `#B45159`, balloon `#82B3BE`. |

### Why these value clusters work

Light is generally above-left, with darker lower/right-facing areas. Different
materials need different arrangements: dice uses large flat face values;
the guitar uses a curved lower-right body cluster; the record stays dark with
short reflections; cards use bright paper faces and narrow edge shadows.
Accent colors identify controls or printed marks and do not replace shading.

Do not impose a fixed number of shades or a generic coordinate-based ramp on
every item. Place each cluster where a surface turns, an object overlaps,
a cavity recedes or a recognizable marking exists. A single pixel is valid
for a pip, control or spindle hole when it has a specific job.

### Reproduce, export and verify

From the project root, use a dedicated output directory:

```powershell
python docs/examples/humanball_entertainment_approved.py --output LOCAL_REVIEW/humanball_entertainment_reproduction
```

This redraws all twenty PNGs, the 90x72 transparent 5x4 sheet, a nearest-neighbor
10x sheet, a spaced/labeled review, manifest and audit. It overwrites matching
generated files in the specified output directory; use a new directory for
experiments. The labeled review's background and spacing are presentation
only and are never inserted into native assets.

Export individual PNGs to editable Aseprite documents with the installed
Aseprite batch CLI (`-b input.png --save-as output.aseprite`). Pixel coordinates
remain zero-based; Aseprite MCP frame/layer indices are **1** for the first
frame/layer, as verified from document metadata. Check tool results before
exporting; a file existing on disk does not prove it contains painted pixels.

The source asserts controller mask symmetry, complete unbounded dilation
fitting inside the canvas, exact native dimensions, binary alpha, exact ring
colors and exact sheet-cell equality. Border checks run on actual exported
PNGs. They do not judge recognition or replace author visual acceptance.

The approved source is preserved in `docs/examples/` so the method survives
cleanup of `LOCAL_REVIEW`. New categories should reuse its construction and
verification helpers while defining their own object geometry and palettes.
