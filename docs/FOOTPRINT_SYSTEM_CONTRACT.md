# Ground Footprint System Contract v1

## Purpose

Separate visual sprites from ground occupancy. Navigation must consume footprint occupancy, not the full visual alpha silhouette.

## Canonical fine grid

`grid.iso.occupancy_fine.v1` is the permanent canonical navigation/occupancy lattice (4×2 px; U=(2,1), V=(-2,1), origin=(28,0)).

- fine tile: 4 x 2 px
- +U: (+2,+1)
- +V: (-2,+1)
- 9 fine steps = one approved 36 x 18 movement-grid step

This fine grid is for occupancy authoring/projection. It does not force character animation to move one fine cell at a time.

## Source of truth

JSON profile data is canonical. PNG footprint images are derived debug/review outputs only.

Each profile stores:

- approved dimensions in fine cells
- U/V cell extents
- footprint origin relative to the visual asset's top-left edge-coordinate frame
- transform policy

## Transform policy

Desk mirrored/reversed occupancy MUST NOT be stored as a second profile. A visual FLIP_X must derive the footprint by the same FLIP_X transform. In asset edge coordinates the mirror rule is `x' = canvas_width - x`.

## Visual-only pieces

- PC/monitor assets: no ground footprint
- Chair `part_03`: no ground footprint

These pieces remain available to rendering/depth/occlusion logic later.

## Approved profiles

- `footprint.desk.standard`: 18 x 7 author dimensions
- `footprint.chair.standard`: 4 x 4
- `footprint.reception.f0`: 15 x 19
- `footprint.reception.f1`: 14 x 18
- `footprint.reception.f2_plus`: 15 x 25

Reception F2+ is shared by Floor02 and later reception families unless a future author-approved override replaces it.
