# Phase 6 Spatial Object Metadata Foundation

Phase 6 covers only `chair`, `desk`, `pc`, and `reception` as primary spatial objects.

The release stores 224 visual-variant spatial profiles and derives 681 floor object instances at runtime. It does not materialize one spatial JSON record per floor placement.

## Evidence-backed data

For each used primary visual variant the registry stores the rendered canvas size, alpha-channel visual bounds, transparent padding, transform, and usage provenance. Runtime combines that profile with the already verified layout placement to produce render coordinates and world-space visual bounds.

Workstation component roles and direction are reused from the Phase 2/3 layout and direction registries. Reception on the large layout preserves the Phase 2 semantic anchor (`sprite_left x=221`, visible `alpha_top y=355`). Floor 1 reception keeps only its explicit placement because no shared semantic anchor was proven for that layout.

`chair_sub` is not promoted to a primary spatial object. When present, it is surfaced only as the existing `chair_foreground` / `foreground_fragment` render relationship.

## Explicitly unknown in Phase 6

The following are present as `null` and must not be inferred by consumers:

- object footprint
- solid flag
- collision shape
- interaction anchor
- interaction radius
- workstation seat anchor

Grid, navigation, pathfinding and behavior remain Phase 7 work.
