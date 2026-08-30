# GDS Central Core Architecture Design

## Goal
Build a lean central core that combines the verified Character + Action + Central VFX system with a normalized Floor/World system, while preserving strict domain boundaries and allowing future spatial metadata, collision, navigation, and behavior to be added without rewriting the core.

## Architecture principles

1. Character and World remain separate domains inside one central package.
2. Canonical assets are stored once; materialized PNG/GIF/final floor renders remain derived outputs or regression artifacts, not source-of-truth.
3. Floor 0, Floor 1, and Floor 2 define the canonical layout families. Floor 3+ inherit the Floor 2 large-layout template and swap only floor-specific asset skins/variants.
4. Workstation direction is metadata on workstation usage/layout, not on raw desk/chair/PC PNG assets.
5. Existing pixel X/Y/layer remain authoritative until a verified isometric grid is derived.
6. Character machine identity remains stable; user-facing serial, full name, and nickname are aliases that resolve back to the canonical character_id.
7. Unknown spatial facts remain null/unset. Collision, grid, navigation, and seat anchors are never guessed.
8. All randomized character serial/name assignments are generated once with a recorded seed and then frozen.

## Final domains

- Character Domain: identity, composition, action registry, frame rules, VFX, render/export.
- World Domain: world assets, visual variants, floor skins, layout templates, placements, workstations, coordinate frames.
- Shared Contracts: direction enum, canonical IDs, resolver interfaces, future interaction/spatial contracts.
- Runtime: character resolver, world resolver, floor assembler, later scene/interaction/navigation runtimes.

## Direction contract

`interaction_direction` means the character action direction to use when interacting with a workstation. Canonical enum: NE, SE, SW, NW.

Verified authored directions:

- floor00: ceo=SE, ws1=SE, ws2=SE, ws3=NW, ws4=NW
- floor01: ceo=SE, ws1=SE, ws2=SE, ws3=NW, ws4=NW, ws5=SE, ws6=SE
- floor02 template: ceo=SW, ws1=SE, ws2=SE, ws3=NW, ws4=NW, ws5=SE, ws6=SE, ws7=NW, ws8=NW
- floor03+ inherit the floor02 layout-direction pattern.

## Spatial contract

Pixel space is authoritative initially:

- origin: top-left of the floor render canvas
- +X: right
- +Y: down
- `layer`: existing draw-order scalar

Isometric axis metadata is descriptive until measured grid units are verified:

- +U direction: SE
- +V direction: SW
- grid/tile dimensions: unset until verified

## Character identity-card contract

Canonical machine identity remains `character_id` (e.g. TP_000, RND_M_081). Add:

- `character_no`: stable integer 0..301
- `character_code`: CHAR_000..CHAR_301
- `first_name`
- `last_name`
- `full_name`
- `nickname`

Original characters retain canonical source order 0..63. Custom characters occupy 64..301 using one deterministic shuffle whose seed is stored in the registry build metadata. Names are generated once and frozen. Gender-specific names may be used only where source metadata explicitly establishes gender; otherwise use a neutral English name pool. Full names and nicknames must be case-insensitively unique for unambiguous lookup.

## Non-goals until later phases

- no guessed collision polygons
- no guessed walkability grid
- no guessed seat/snap anchors
- no AI behavior implementation before navigation contracts exist
- no duplication of floor02 layout metadata into floor03+
