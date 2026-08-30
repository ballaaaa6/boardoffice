from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path


class GroundFootprintCore:
    """Resolve author-approved ground-occupancy footprints independently of visual alpha."""

    def __init__(self, world_root: str | Path):
        self.root = Path(world_root)
        reg = self.root / 'REGISTRY'
        self._registry_dir = reg
        self.fine_grid = self._load(reg / 'fine_grid_profiles.json')['profiles']['grid.iso.occupancy_fine.v1']
        self.profiles = self._load(reg / 'footprint_profiles.json')['profiles']
        self.bindings = self._load(reg / 'footprint_bindings.json')['rules']
        self.world_assets = self._load(reg / 'world_assets.json')['assets']
        self.visual_variants = self._load(reg / 'visual_variants.json')['variants']
        spatial_path = reg / 'spatial_profiles.json'
        self.spatial_profiles = self._load(spatial_path).get('profiles', {}) if spatial_path.exists() else {}
        self._normal_visual_bounds_by_asset = {
            rec['asset_id']: deepcopy(rec['visual_bounds_px'])
            for rec in self.spatial_profiles.values()
            if rec.get('transform') == 'NORMAL' and rec.get('visual_bounds_px') is not None
        }

    @staticmethod
    def _load(path: Path):
        with path.open('r', encoding='utf-8') as f:
            return json.load(f)

    def profile(self, profile_id: str) -> dict:
        return deepcopy(self.profiles[profile_id])

    def fine_grid_profile(self) -> dict:
        return deepcopy(self.fine_grid)

    def _asset_record(self, asset_id: str) -> dict:
        if asset_id in self.world_assets:
            return self.world_assets[asset_id]
        raise KeyError(f'Unknown world asset for ground footprint: {asset_id}')

    def _canvas_size(self, asset_id: str) -> list[int]:
        rec = self._asset_record(asset_id)
        return [int(rec['width']), int(rec['height'])]

    def _match_rule(self, asset_id: str):
        for rule in self.bindings:
            match = rule['match']
            if 'asset_id_exact' in match and asset_id == match['asset_id_exact']:
                return rule
            if 'asset_id_regex' in match and re.match(match['asset_id_regex'], asset_id):
                return rule
        return None

    def _profile_outer_corners(self, profile: dict, asset_id: str) -> tuple[list[list[int]], list[int]]:
        x, y = profile['origin_asset_edge_px']
        origin_basis = profile.get('origin_basis', 'asset_canvas')
        visual_offset = [0, 0]
        if origin_basis == 'visual_bounds_top_left':
            bounds = self._normal_visual_bounds_by_asset.get(asset_id)
            if bounds is None:
                raise KeyError(f'Missing NORMAL visual bounds for ground-footprint origin: {asset_id}')
            visual_offset = [int(bounds['left']), int(bounds['top'])]
            x += visual_offset[0]
            y += visual_offset[1]
        elif origin_basis != 'asset_canvas':
            raise ValueError(f'Unsupported ground-footprint origin basis: {origin_basis}')
        u = int(profile['axes']['u_cells'])
        v = int(profile['axes']['v_cells'])
        ux, uy = self.fine_grid['u_step_px']
        vx, vy = self.fine_grid['v_step_px']
        p0 = [x, y]
        p1 = [x + u * ux, y + u * uy]
        p2 = [p1[0] + v * vx, p1[1] + v * vy]
        p3 = [x + v * vx, y + v * vy]
        return [p0, p1, p2, p3], visual_offset

    def resolve_asset(self, asset_id: str, *, transform: str | None = None) -> dict | None:
        rule = self._match_rule(asset_id)
        if rule is None or rule.get('profile_id') is None:
            return None
        profile = self.profiles[rule['profile_id']]
        canvas = self._canvas_size(asset_id)
        applied = transform or rule.get('default_transform', 'NORMAL')
        corners, visual_offset = self._profile_outer_corners(profile, asset_id)
        if applied == 'FLIP_X':
            width = canvas[0]
            corners = [[width - x, y] for x, y in corners]
        elif applied != 'NORMAL':
            raise ValueError(f'Unsupported ground-footprint transform: {applied}')
        return {
            'asset_id': asset_id,
            'profile_id': profile['profile_id'],
            'approval_status': profile['approval_status'],
            'grid_profile_id': 'grid.iso.occupancy_fine.v1',
            'canvas_size_px': canvas,
            'author_size_fine_cells': list(profile['author_size_fine_cells']),
            'axes': deepcopy(profile['axes']),
            'derived_transform': applied,
            'origin_basis': profile.get('origin_basis', 'asset_canvas'),
            'visual_bounds_offset_px': visual_offset,
            'outer_corners_asset_px': corners,
        }

    def resolve_variant(self, variant_id: str) -> dict | None:
        rec = self.visual_variants.get(variant_id)
        if rec is None:
            raise KeyError(f'Unknown world visual variant for ground footprint: {variant_id}')
        visual_transform = rec.get('transform', 'NORMAL')
        transform = 'FLIP_X' if visual_transform == 'FLIP_X' else None
        return self.resolve_asset(rec['asset_id'], transform=transform)

    def project_asset(self, asset_id: str, asset_top_left_px, *, transform: str | None = None) -> dict | None:
        resolved = self.resolve_asset(asset_id, transform=transform)
        if resolved is None:
            return None
        ax, ay = map(int, asset_top_left_px)
        out = deepcopy(resolved)
        out['asset_top_left_px'] = [ax, ay]
        out['outer_corners_world_px'] = [[ax + x, ay + y] for x, y in resolved['outer_corners_asset_px']]
        return out

    def local_occupied_cells(self, profile_id: str) -> list[list[int]]:
        p = self.profiles[profile_id]
        return [[u, v] for u in range(p['axes']['u_cells']) for v in range(p['axes']['v_cells'])]
