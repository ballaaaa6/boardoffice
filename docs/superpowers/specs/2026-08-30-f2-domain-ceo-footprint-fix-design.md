# F2 Domain + CEO Desk Footprint Fix Design

## Goal
Patch the canonical navigation/footprint data after author review: Floor00/Floor01 CEO desks use the normal canonical desk footprint, while Floor02 and all F2+ floors continue to use the mirrored CEO desk footprint; Floor02 canonical Room Domain is reshaped from the author markup and its portal narrows with the corridor.

## Approved behavior
- `floor00.ceo_desk` -> `footprint.desk.standard`, transform `NORMAL`.
- `floor01.ceo_desk` -> `footprint.desk.standard`, transform `NORMAL`.
- `floor02.ceo_desk` and later CEO desk assets remain derived mirrors (`FLIP_X`) unless a later author review overrides them.
- Floor02 domain removes the author-red right strip from the lower corridor and adds the author-green rectangular notch extension on the lower-left transition.
- The snapped canonical Floor02 polygon is:
  `[[188,45],[188,117],[217,117],[217,134],[240,134],[240,189],[268,189],[268,128],[279,128],[279,71],[217,71],[217,45]]`.
- Floor02 portal becomes `[[240,189],[268,189]]`; its inside/outside strips are regenerated from this edge.
- Every floor bound to `layout.floor02.large` inherits the updated Floor02 domain, portal, and compiled room cells; no duplicate F3+ geometry is created.
- Floor00/Floor01 room domains and portals remain unchanged.

## Storage and runtime
`WORLD/REGISTRY/footprint_bindings.json` is the binding source of truth. `WORLD/REGISTRY/room_domains.json`, `WORLD/REGISTRY/portals.json`, and `WORLD/COMPILED_NAV/floor02_room_cells.json` are the navigation source/compiled artifacts. F2+ reuse remains controlled by `room_navigation_bindings.json`.

## Validation
Tests must prove CEO desk transforms, exact Floor02 canonical polygon/portal, F2+ derivation, compiled-mask consistency, and portal-strip width. Navigation/footprint audits and the full active test suite must pass. Review previews must be regenerated from metadata, not hand-painted.
