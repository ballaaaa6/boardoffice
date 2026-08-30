from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path


class RoomNavigationCore:
    """Resolve author-approved room domains/portals on the permanent fine lattice.

    Floor00 owns its geometry, Floor01 owns its geometry, and every floor using
    layout.floor02.large reuses Floor02 canonical geometry without duplication.
    """

    def __init__(self, world_root: str | Path):
        self.root = Path(world_root)
        reg = self.root / 'REGISTRY'
        self.floors = self._load(reg / 'floors.json')['floors']
        self.grid = self._load(reg / 'fine_grid_profiles.json')['profiles']['grid.iso.occupancy_fine.v1']
        self.domain_registry = self._load(reg / 'room_domains.json')
        self.portal_registry = self._load(reg / 'portals.json')
        self.bindings = self._load(reg / 'room_navigation_bindings.json')
        self.compiled_root = self.root / 'COMPILED_NAV'

    @staticmethod
    def _load(path: Path) -> dict:
        with path.open('r', encoding='utf-8') as f:
            return json.load(f)

    def grid_profile(self) -> dict:
        return deepcopy(self.grid)

    def family(self, floor_id: str) -> dict:
        if floor_id not in self.floors:
            raise KeyError(f'Unknown floor: {floor_id}')
        layout_id = self.floors[floor_id]['layout_id']
        try:
            canonical = self.bindings['layout_bindings'][layout_id]
        except KeyError as exc:
            raise KeyError(f'No room-navigation family binding for layout {layout_id}') from exc
        return {
            'floor_id': floor_id,
            'layout_id': layout_id,
            'canonical_floor_id': canonical,
            'grid_profile_id': self.grid['profile_id'],
        }

    def domain(self, floor_id: str) -> dict:
        fam = self.family(floor_id)
        rec = deepcopy(self.domain_registry['domains'][fam['canonical_floor_id']])
        rec['floor_id'] = floor_id
        rec['canonical_floor_id'] = fam['canonical_floor_id']
        rec['derived_from_canonical'] = floor_id != fam['canonical_floor_id']
        return rec

    def portal(self, floor_id: str) -> dict:
        fam = self.family(floor_id)
        canonical_floor = fam['canonical_floor_id']
        canonical_id = f'{canonical_floor}.main_exit'
        rec = deepcopy(self.portal_registry['portals'][canonical_id])
        rec['floor_id'] = floor_id
        rec['canonical_floor_id'] = canonical_floor
        rec['canonical_portal_id'] = canonical_id
        rec['portal_id'] = f'{floor_id}.main_exit'
        rec['derived_from_canonical'] = floor_id != canonical_floor
        return rec

    def room_cells(self, floor_id: str) -> dict:
        fam = self.family(floor_id)
        canonical = fam['canonical_floor_id']
        rec = self._load(self.compiled_root / f'{canonical}_room_cells.json')
        out = deepcopy(rec)
        out['floor_id'] = floor_id
        out['canonical_floor_id'] = canonical
        out['derived_from_canonical'] = floor_id != canonical
        return out

    def room_cell_set(self, floor_id: str) -> set[tuple[int,int]]:
        rec = self.room_cells(floor_id)
        rows = rec.get('row_runs', rec.get('rows', []))
        out=set()
        for row in rows:
            v=int(row['v'])
            for lo,hi in row['u_runs_inclusive']:
                out.update((u,v) for u in range(int(lo),int(hi)+1))
        return out

    def is_room_cell(self, floor_id: str, u: int, v: int) -> bool:
        return (int(u),int(v)) in self.room_cell_set(floor_id)

    def uv_vertex_to_pixel(self, u: int, v: int) -> tuple[int,int]:
        ox,oy=self.grid['grid_origin_px']; ux,uy=self.grid['u_step_px']; vx,vy=self.grid['v_step_px']
        return (ox+int(u)*ux+int(v)*vx, oy+int(u)*uy+int(v)*vy)

    def pixel_to_uv_vertex(self, x: int, y: int) -> tuple[int,int]:
        ox,oy=self.grid['grid_origin_px']; dx,dy=int(x)-ox,int(y)-oy
        ux,uy=self.grid['u_step_px']; vx,vy=self.grid['v_step_px']; det=ux*vy-uy*vx
        un=dx*vy-dy*vx; vn=ux*dy-uy*dx
        if un % det or vn % det:
            raise ValueError(f'Pixel is not on a fine-grid vertex: {(x,y)}')
        return (un//det,vn//det)
