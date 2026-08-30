from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from RUNTIME.central_core import CentralGameCore


class Phase8BEdgeReliefQA:
    """Render F0/F1/F2 real-floor fine-grid overlays for clearance relief QA."""

    FLOOR_IDS = ['floor00', 'floor01', 'floor02']

    BASE = (220, 45, 45, 105)
    CLEARANCE = (45, 135, 255, 115)
    DESK_CHAIR = (255, 150, 20, 185)
    DESK_DESK = (170, 70, 255, 195)
    BOUNDARY_RELIEF = (255, 70, 180, 230)
    PAIR_RELIEF = (255, 235, 70, 235)
    GATE = (35, 235, 105, 235)
    PORTAL = (255, 205, 0, 245)
    GRID = (18, 20, 24, 150)
    ROOM_BOUNDARY = (15, 85, 235, 255)

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.core = CentralGameCore(self.root)

    def _cell_polygon(self, cell: tuple[int, int] | list[int]) -> list[tuple[int, int]]:
        u, v = int(cell[0]), int(cell[1])
        nav = self.core.room_navigation
        return [
            nav.uv_vertex_to_pixel(u, v),
            nav.uv_vertex_to_pixel(u + 1, v),
            nav.uv_vertex_to_pixel(u + 1, v + 1),
            nav.uv_vertex_to_pixel(u, v + 1),
        ]

    @staticmethod
    def _cells(rows: list[list[int]] | None) -> set[tuple[int, int]]:
        return {tuple(cell) for cell in (rows or [])}

    def render_floor_overlay(self, floor_id: str) -> Image.Image:
        compiled = self.core.navigation_occupancy.compile_floor(floor_id)
        image = self.core.render_floor(floor_id).convert('RGBA')
        overlay = Image.new('RGBA', image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay, 'RGBA')

        # Physical authored occupancy.
        for cell in compiled['base_occupied_cells_uv']:
            draw.polygon(self._cell_polygon(cell), fill=self.BASE)

        # Final navigation-only clearance after all relief rules.
        for cell in compiled.get('clearance_cells_uv', []):
            draw.polygon(self._cell_polygon(cell), fill=self.CLEARANCE)

        # Semantic closures stay solid and are never carved by relief.
        by_type: dict[str, set[tuple[int, int]]] = {
            'workstation_desk_chair': set(),
            'desk_desk_seam': set(),
        }
        for row in compiled.get('closures', []):
            by_type.setdefault(row['closure_type'], set()).update(
                tuple(cell) for cell in row['occupied_cells_uv']
            )
        for cell in sorted(by_type['workstation_desk_chair'], key=lambda uv: (uv[1], uv[0])):
            draw.polygon(self._cell_polygon(cell), fill=self.DESK_CHAIR)
        for cell in sorted(by_type['desk_desk_seam'], key=lambda uv: (uv[1], uv[0])):
            draw.polygon(self._cell_polygon(cell), fill=self.DESK_DESK)

        # Restored navigation space from edge-aware chair rules.
        for cell in compiled.get('boundary_relief_cells_uv', []):
            draw.polygon(self._cell_polygon(cell), fill=self.BOUNDARY_RELIEF)
        for cell in compiled.get('chair_pair_relief_cells_uv', []):
            draw.polygon(self._cell_polygon(cell), fill=self.PAIR_RELIEF)

        # WorkSeat transition gates and portal remain visibly distinct.
        for cell in compiled.get('protected_ingress_cells_uv', []):
            draw.polygon(self._cell_polygon(cell), fill=self.GATE)
        for cell in compiled.get('portal_inside_cells_uv', []):
            draw.polygon(self._cell_polygon(cell), fill=(255, 205, 0, 95))

        # Permanent fine grid is drawn last so buffer-vs-room relationships are readable.
        for cell in compiled['room_cells_uv']:
            poly = self._cell_polygon(cell)
            draw.line(poly + [poly[0]], fill=self.GRID, width=1)

        domain = self.core.resolve_room_domain(floor_id)['polygon_uv']
        domain_px = [self.core.room_navigation.uv_vertex_to_pixel(u, v) for u, v in domain]
        draw.line(domain_px + [domain_px[0]], fill=self.ROOM_BOUNDARY, width=2)
        portal = self.core.resolve_portal(floor_id)['edge_uv']
        draw.line(
            [
                self.core.room_navigation.uv_vertex_to_pixel(*portal[0]),
                self.core.room_navigation.uv_vertex_to_pixel(*portal[1]),
            ],
            fill=self.PORTAL,
            width=4,
        )
        return Image.alpha_composite(image, overlay)

    def _metrics(self, floor_id: str) -> dict[str, Any]:
        compiled = self.core.navigation_occupancy.compile_floor(floor_id)
        # Keep related runtime queries on exactly this derived structure.
        self.core.navigation_occupancy._compiled_cache[floor_id] = compiled
        self.core.navigation_occupancy._reachable_cache.pop(floor_id, None)
        audit = self.core.validate_navigation_floor(floor_id)
        workstation_ids = list(self.core.world.floor_layout(floor_id)['workstation_groups'])
        unreachable = 0
        for workstation_id in workstation_ids:
            access = self.core.resolve_workstation_navigation_access(floor_id, workstation_id)
            if access['reachable_approach_cell_count'] <= 0:
                unreachable += 1
        return {
            'floor_id': floor_id,
            'room_cell_count': compiled['room_cell_count'],
            'base_occupied_cell_count': compiled['base_occupied_cell_count'],
            'closure_cell_count': compiled['closure_cell_count'],
            'clearance_cell_count': compiled['clearance_cell_count'],
            'boundary_relief_cell_count': compiled.get('boundary_relief_cell_count', 0),
            'boundary_relief_count': len(compiled.get('boundary_relief_records', [])),
            'chair_pair_relief_cell_count': compiled.get('chair_pair_relief_cell_count', 0),
            'chair_pair_relief_count': len(compiled.get('chair_pair_relief_records', [])),
            'sealed_pocket_cell_count': compiled.get('sealed_pocket_cell_count', 0),
            'occupied_cell_count': compiled['occupied_cell_count'],
            'walkable_cell_count': compiled['walkable_cell_count'],
            'protected_ingress_cell_count': compiled.get('protected_ingress_cell_count', 0),
            'isolated_walkable_cell_count': audit['isolated_walkable_cell_count'],
            'portal_overlap_cell_count': audit['portal_overlap_cell_count'],
            'unreachable_workstation_count': unreachable,
            'workstation_count': len(workstation_ids),
            'boundary_relief_records': compiled.get('boundary_relief_records', []),
            'chair_pair_relief_records': compiled.get('chair_pair_relief_records', []),
            'valid': bool(audit['valid'] and unreachable == 0),
        }

    @staticmethod
    def _contact_sheet(items: list[tuple[str, Image.Image]]) -> Image.Image:
        label_h = 30
        gap = 12
        cell_w = 600
        cell_h = 600 + label_h
        sheet = Image.new(
            'RGBA',
            (gap * 4 + cell_w * len(items), cell_h + gap * 2),
            (18, 20, 24, 255),
        )
        draw = ImageDraw.Draw(sheet)
        for idx, (label, image) in enumerate(items):
            x = gap + idx * (cell_w + gap)
            y = gap
            draw.text((x + 6, y + 6), label.upper(), fill=(245, 247, 250, 255))
            sheet.alpha_composite(image.convert('RGBA'), (x, y + label_h))
        return sheet

    def generate_bundle(self, output_root: str | Path) -> dict[str, Any]:
        output_root = Path(output_root).resolve()
        floor_dir = output_root / 'FLOORS'
        contact_dir = output_root / 'CONTACT_SHEETS'
        floor_dir.mkdir(parents=True, exist_ok=True)
        contact_dir.mkdir(parents=True, exist_ok=True)

        items: list[tuple[str, Image.Image]] = []
        metrics: list[dict[str, Any]] = []
        for floor_id in self.FLOOR_IDS:
            image = self.render_floor_overlay(floor_id)
            image.save(floor_dir / f'{floor_id}_edge_relief_grid_overlay.png')
            items.append((floor_id, image))
            metrics.append(self._metrics(floor_id))

        self._contact_sheet(items).save(
            contact_dir / 'f0_f1_f2_edge_relief_grid_contact.png'
        )
        status = 'PASS' if all(row['valid'] for row in metrics) else 'FAIL'
        report = {
            'schema': 'gds_phase8b_edge_relief_grid_qa_v1',
            'status': status,
            'visual_review_status': 'PENDING_USER_APPROVAL',
            'floors': list(self.FLOOR_IDS),
            'metrics': metrics,
            'legend': {
                'base_footprint': 'red',
                'navigation_clearance': 'blue',
                'desk_chair_closure': 'orange',
                'desk_desk_seam': 'purple',
                'chair_boundary_relief_restored': 'magenta',
                'chair_pair_relief_restored': 'yellow',
                'workseat_transition_gate': 'green',
                'room_boundary': 'blue_line',
                'portal': 'yellow_line',
                'fine_grid': 'dark_lines',
            },
            'artifact_policy': 'external_review_only_not_canonical_release_payload',
        }
        report_path = output_root / 'PHASE8B_EDGE_RELIEF_GRID_QA.json'
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Render F0/F1/F2 edge-relief occupancy over the real fine grid.')
    parser.add_argument('--output', required=True, help='External QA output directory')
    args = parser.parse_args(argv)
    report = Phase8BEdgeReliefQA(ROOT).generate_bundle(args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
