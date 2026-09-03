from __future__ import annotations

import argparse
import json
from collections import deque
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

try:
    from TOOLS._bootstrap import ensure_project_root
except ModuleNotFoundError:
    from _bootstrap import ensure_project_root

ROOT = ensure_project_root(__file__)

from WORLD.RUNTIME.floor_renderer import FloorRenderer
from WORLD.RUNTIME.navigation_occupancy_core import NavigationOccupancyCore
from WORLD.RUNTIME.room_navigation_core import RoomNavigationCore


class Phase8ANavigationQA:
    """Deterministic Phase 8A navigation review renderer.

    Review images are derived from canonical world data at runtime.  The QA
    path intentionally calls ``compile_floor`` rather than loading the optional
    materialized occupancy cache.
    """

    WALKABLE = (34, 197, 94, 88)
    OCCUPIED = (224, 66, 66, 142)
    PORTAL = (255, 214, 0, 210)
    ROOM_BOUNDARY = (24, 120, 255, 255)
    GRID = (22, 24, 29, 120)

    MAP_OUTSIDE = (0, 0, 0, 255)
    MAP_WALKABLE = (34, 197, 94, 255)
    MAP_OCCUPIED = (224, 66, 66, 255)
    MAP_PORTAL = (255, 214, 0, 255)

    def __init__(self, core_root: str | Path):
        self.core_root = Path(core_root).resolve()
        self.world_root = self.core_root / 'WORLD'
        self.navigation = RoomNavigationCore(self.world_root)
        self.occupancy = NavigationOccupancyCore(self.world_root)
        # Phase 8A must prove the lean runtime fallback. Point the optional
        # occupancy-cache root at a deliberately absent location so every
        # QA result is derived from canonical registries/masks.
        self.occupancy.compiled_root = self.core_root / '__PHASE8A_RUNTIME_ONLY_NO_DISK_CACHE__'
        self.renderer = FloorRenderer(self.world_root)

    def _pixel(self, u: int, v: int) -> tuple[int, int]:
        return self.navigation.uv_vertex_to_pixel(int(u), int(v))

    def _cell_polygon(self, u: int, v: int) -> list[tuple[int, int]]:
        return [
            self._pixel(u, v),
            self._pixel(u + 1, v),
            self._pixel(u + 1, v + 1),
            self._pixel(u, v + 1),
        ]

    def render_floor_overlay(self, floor_id: str) -> Image.Image:
        compiled = self.occupancy.compile_floor(floor_id)
        base = self.renderer.render(floor_id).convert('RGBA')
        overlay = Image.new('RGBA', base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay, 'RGBA')

        portal_cells = {tuple(cell) for cell in compiled['portal_inside_cells_uv']}
        walkable = {tuple(cell) for cell in compiled['walkable_cells_uv']}
        occupied = {tuple(cell) for cell in compiled['occupied_cells_uv']}
        room = {tuple(cell) for cell in compiled['room_cells_uv']}

        for u, v in sorted(walkable, key=lambda cell: (cell[1], cell[0])):
            draw.polygon(self._cell_polygon(u, v), fill=self.WALKABLE)
        for u, v in sorted(occupied, key=lambda cell: (cell[1], cell[0])):
            draw.polygon(self._cell_polygon(u, v), fill=self.OCCUPIED)
        for u, v in sorted(portal_cells, key=lambda cell: (cell[1], cell[0])):
            draw.polygon(self._cell_polygon(u, v), fill=self.PORTAL)

        # Dark fine grid: draw once after fills so the permanent lattice remains readable.
        for u, v in sorted(room, key=lambda cell: (cell[1], cell[0])):
            poly = self._cell_polygon(u, v)
            draw.line(poly + [poly[0]], fill=self.GRID, width=1)

        domain = self.navigation.domain(floor_id)['polygon_uv']
        domain_px = [self._pixel(u, v) for u, v in domain]
        draw.line(domain_px + [domain_px[0]], fill=self.ROOM_BOUNDARY, width=2)

        portal_edge = self.navigation.portal(floor_id)['edge_uv']
        draw.line(
            [self._pixel(*portal_edge[0]), self._pixel(*portal_edge[1])],
            fill=self.PORTAL,
            width=4,
        )
        return Image.alpha_composite(base, overlay)

    def render_cell_map(self, floor_id: str, *, cell_px: int = 5, padding: int = 3) -> Image.Image:
        if cell_px < 1:
            raise ValueError('cell_px must be >= 1')
        compiled = self.occupancy.compile_floor(floor_id)
        room = {tuple(cell) for cell in compiled['room_cells_uv']}
        walkable = {tuple(cell) for cell in compiled['walkable_cells_uv']}
        occupied = {tuple(cell) for cell in compiled['occupied_cells_uv']}
        portal = {tuple(cell) for cell in compiled['portal_inside_cells_uv']}

        if not room:
            raise ValueError(f'Room domain has no cells: {floor_id}')
        min_u = min(u for u, _ in room) - padding
        max_u = max(u for u, _ in room) + padding
        min_v = min(v for _, v in room) - padding
        max_v = max(v for _, v in room) + padding
        width = (max_u - min_u + 1) * cell_px
        height = (max_v - min_v + 1) * cell_px
        image = Image.new('RGBA', (width, height), self.MAP_OUTSIDE)
        draw = ImageDraw.Draw(image, 'RGBA')

        def rect_for(u: int, v: int) -> tuple[int, int, int, int]:
            x = (u - min_u) * cell_px
            y = (v - min_v) * cell_px
            return (x, y, x + cell_px - 1, y + cell_px - 1)

        for u, v in walkable:
            draw.rectangle(rect_for(u, v), fill=self.MAP_WALKABLE)
        for u, v in occupied:
            draw.rectangle(rect_for(u, v), fill=self.MAP_OCCUPIED)
        for u, v in portal:
            draw.rectangle(rect_for(u, v), fill=self.MAP_PORTAL)
        return image

    @staticmethod
    def _reachable_from_portal(compiled: dict[str, Any]) -> set[tuple[int, int]]:
        walkable = {tuple(cell) for cell in compiled['walkable_cells_uv']}
        starts = {tuple(cell) for cell in compiled['portal_inside_cells_uv']} & walkable
        seen = set(starts)
        queue = deque(sorted(starts, key=lambda cell: (cell[1], cell[0])))
        while queue:
            u, v = queue.popleft()
            for nxt in ((u + 1, v), (u - 1, v), (u, v + 1), (u, v - 1)):
                if nxt in walkable and nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return seen

    def build_floor_metrics(self, floor_id: str) -> dict[str, Any]:
        compiled = self.occupancy.compile_floor(floor_id)
        # Seed the in-memory cache with the just-derived structure so related
        # workstation queries are guaranteed to inspect the same runtime data.
        self.occupancy._compiled_cache[floor_id] = compiled
        self.occupancy._reachable_cache.pop(floor_id, None)

        walkable = {tuple(cell) for cell in compiled['walkable_cells_uv']}
        reachable = self._reachable_from_portal(compiled)
        workstation_ids = list(
            self.occupancy.layout.floor_layout(floor_id).get('workstation_groups', {})
        )
        unreachable = 0
        for workstation_id in workstation_ids:
            access = self.occupancy.workstation_access(floor_id, workstation_id)
            if access['reachable_approach_cell_count'] <= 0:
                unreachable += 1

        outside_count = int(compiled['outside_room_instance_count'])
        outside_closure_count = int(compiled.get('outside_room_closure_count', 0))
        portal_overlap_count = int(compiled['portal_overlap_cell_count'])
        isolated_count = len(walkable - reachable)
        valid = (
            outside_count == 0
            and outside_closure_count == 0
            and portal_overlap_count == 0
            and isolated_count == 0
            and unreachable == 0
        )
        return {
            'floor_id': floor_id,
            'canonical_room_floor_id': compiled['canonical_room_floor_id'],
            'room_cell_count': int(compiled['room_cell_count']),
            'base_occupied_cell_count': int(compiled.get('base_occupied_cell_count', compiled['occupied_cell_count'])),
            'closure_cell_count': int(compiled.get('closure_cell_count', 0)),
            'occupied_cell_count': int(compiled['occupied_cell_count']),
            'walkable_cell_count': int(compiled['walkable_cell_count']),
            'portal_inside_cell_count': int(compiled['portal_inside_cell_count']),
            'outside_room_instance_count': outside_count,
            'outside_room_closure_count': outside_closure_count,
            'portal_overlap_cell_count': portal_overlap_count,
            'reachable_walkable_cell_count': len(reachable),
            'isolated_walkable_cell_count': isolated_count,
            'workstation_count': len(workstation_ids),
            'unreachable_workstation_count': unreachable,
            'valid': valid,
        }

    def resolve_review_floors(self) -> list[str]:
        floors = self.occupancy.layout.floors
        large = [
            floor_id
            for floor_id, rec in floors.items()
            if rec['layout_id'] == 'layout.floor02.large'
        ]
        if not large:
            raise ValueError('No floor uses layout.floor02.large')
        candidates = ['floor00', 'floor01', 'floor02', 'floor03', 'floor06', large[-1]]
        out: list[str] = []
        for floor_id in candidates:
            if floor_id in floors and floor_id not in out:
                out.append(floor_id)
        return out

    @staticmethod
    def _contact_sheet(items: list[tuple[str, Image.Image]], *, thumb_size: int = 600) -> Image.Image:
        if not items:
            raise ValueError('Contact sheet requires at least one image')
        columns = 2
        label_h = 28
        gap = 16
        prepared: list[tuple[str, Image.Image]] = []
        for label, image in items:
            thumb = image.convert('RGBA').copy()
            thumb.thumbnail((thumb_size, thumb_size), Image.Resampling.NEAREST)
            prepared.append((label, thumb))
        cell_w = max(im.width for _, im in prepared)
        cell_h = max(im.height for _, im in prepared) + label_h
        rows = (len(prepared) + columns - 1) // columns
        sheet = Image.new(
            'RGBA',
            (columns * cell_w + (columns + 1) * gap, rows * cell_h + (rows + 1) * gap),
            (20, 22, 28, 255),
        )
        draw = ImageDraw.Draw(sheet)
        for idx, (label, thumb) in enumerate(prepared):
            row, col = divmod(idx, columns)
            x = gap + col * (cell_w + gap)
            y = gap + row * (cell_h + gap)
            draw.text((x, y + 5), label.upper(), fill=(245, 247, 250, 255))
            image_x = x + (cell_w - thumb.width) // 2
            sheet.alpha_composite(thumb, (image_x, y + label_h))
        return sheet

    def generate_review_bundle(self, output_root: str | Path) -> dict[str, Any]:
        output_root = Path(output_root).resolve()
        overlay_dir = output_root / 'OVERLAY'
        cell_dir = output_root / 'CELL_MAP'
        contact_dir = output_root / 'CONTACT_SHEETS'
        for directory in (overlay_dir, cell_dir, contact_dir):
            directory.mkdir(parents=True, exist_ok=True)

        floors = self.resolve_review_floors()
        overlay_items: list[tuple[str, Image.Image]] = []
        cell_items: list[tuple[str, Image.Image]] = []
        floor_reports: list[dict[str, Any]] = []

        for floor_id in floors:
            overlay = self.render_floor_overlay(floor_id)
            cell_map = self.render_cell_map(floor_id)
            overlay.save(overlay_dir / f'{floor_id}_navigation_overlay.png')
            cell_map.save(cell_dir / f'{floor_id}_navigation_cellmap.png')
            overlay_items.append((floor_id, overlay))
            cell_items.append((floor_id, cell_map))
            floor_reports.append(self.build_floor_metrics(floor_id))

        self._contact_sheet(overlay_items).save(
            contact_dir / 'phase8a_overlay_contact.png'
        )
        self._contact_sheet(cell_items).save(
            contact_dir / 'phase8a_cellmap_contact.png'
        )

        machine_pass = all(item['valid'] for item in floor_reports)
        report = {
            'schema': 'gds_phase8a_navigation_qa_v1',
            'status': 'PASS' if machine_pass else 'FAIL',
            'visual_review_status': 'PENDING_USER_APPROVAL',
            'runtime_derived_occupancy_only': True,
            'output_root': str(output_root),
            'floors': floor_reports,
        }
        (output_root / 'PHASE8A_NAVIGATION_QA.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8',
        )
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description='Render Phase 8A navigation QA artifacts')
    parser.add_argument('--output', required=True, help='External review output directory')
    args = parser.parse_args()
    report = Phase8ANavigationQA(ROOT).generate_review_bundle(args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
