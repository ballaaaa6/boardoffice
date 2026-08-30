# Canonical Room Navigation

Source of truth for room geometry: `fine_grid_profiles.json` + `room_domains.json` + `portals.json` + `room_navigation_bindings.json`.

F0 and F1 have unique geometry. F2 is the canonical Room Domain and Portal geometry for every floor using `layout.floor02.large`, including F3+. No duplicated F2+ room polygons or room masks are stored.

Approved room counts:
- F0: 3939 cells; portal width 12.
- F1: 6380 cells; portal width 26.
- F2/F2+: 7774 cells; portal width 28.

Object occupancy is a separate layer. Per-floor compiled occupancy/walkability lives under `WORLD/COMPILED_NAV/OCCUPANCY/`, because floor skins may project the shared footprint families differently even when they share F2 room geometry.

Static floor-crop solids do not participate in navigation. They remain external archived rollback material.
