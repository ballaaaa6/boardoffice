from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw

if __package__ is None or __package__ == '':
    ROOT = Path(__file__).resolve().parents[1]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
else:
    ROOT = Path(__file__).resolve().parents[1]

from RUNTIME.central_core import CentralGameCore
from TOOLS.render_phase8b_floor00_movement import Phase8BFloor00MovementQA


class Phase8BClosureQA:
    """Review supplemental navigation closures and the resulting F0 distant route."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.core = CentralGameCore(self.root)
        self.movement_qa = Phase8BFloor00MovementQA(self.root)

    def _cell_polygon(self, cell: tuple[int, int] | list[int]) -> list[tuple[int, int]]:
        u, v = int(cell[0]), int(cell[1])
        nav = self.core.room_navigation
        return [
            nav.uv_vertex_to_pixel(u, v),
            nav.uv_vertex_to_pixel(u + 1, v),
            nav.uv_vertex_to_pixel(u + 1, v + 1),
            nav.uv_vertex_to_pixel(u, v + 1),
        ]

    def _render_overlay(self, floor_id: str, path_cells: list[list[int]]) -> Image.Image:
        compiled = self.core.resolve_navigation_cells(floor_id)
        image = self.core.render_floor(floor_id).convert('RGBA')
        draw = ImageDraw.Draw(image, 'RGBA')

        # Base object occupancy: muted red. Supplemental semantic closures are
        # drawn afterward with distinct colors so they remain visually legible.
        for cell in compiled['base_occupied_cells_uv']:
            draw.polygon(self._cell_polygon(cell), fill=(220, 45, 45, 80))

        # Navigation-only clearance: blue. It deliberately does not alter the
        # authored footprint/depth geometry; it only keeps walking paths from
        # grazing visual furniture edges.
        for cell in compiled.get('clearance_cells_uv', []):
            draw.polygon(
                self._cell_polygon(cell),
                fill=(45, 135, 255, 125),
                outline=(155, 210, 255, 210),
            )

        by_type: dict[str, set[tuple[int, int]]] = {
            'workstation_desk_chair': set(),
            'desk_desk_seam': set(),
        }
        for closure in compiled['closures']:
            by_type.setdefault(closure['closure_type'], set()).update(
                tuple(cell) for cell in closure['occupied_cells_uv']
            )

        for cell in sorted(by_type.get('workstation_desk_chair', set()), key=lambda uv: (uv[1], uv[0])):
            draw.polygon(self._cell_polygon(cell), fill=(255, 150, 20, 190), outline=(255, 215, 80, 245))
        for cell in sorted(by_type.get('desk_desk_seam', set()), key=lambda uv: (uv[1], uv[0])):
            draw.polygon(self._cell_polygon(cell), fill=(170, 70, 255, 215), outline=(235, 190, 255, 255))

        # Protected WorkSeat ingress gates remain walkable even when desk/chair
        # clearance would otherwise cover them.
        for cell in compiled.get('protected_ingress_cells_uv', []):
            draw.polygon(
                self._cell_polygon(cell),
                fill=(35, 235, 105, 230),
                outline=(210, 255, 220, 255),
            )

        centers = [self.core.character_movement.uv_cell_center_to_pixel(*cell) for cell in path_cells]
        if len(centers) >= 2:
            draw.line(centers, fill=(255, 255, 255, 245), width=3)
        if centers:
            sx, sy = centers[0]
            gx, gy = centers[-1]
            draw.ellipse((sx - 5, sy - 5, sx + 5, sy + 5), fill=(255, 220, 0, 255), outline=(0, 0, 0, 255))
            draw.ellipse((gx - 5, gy - 5, gx + 5, gy + 5), fill=(0, 230, 255, 255), outline=(0, 0, 0, 255))
        return image


    def _render_approach_detail(self, overlay: Image.Image, floor_id: str) -> Image.Image:
        image = overlay.copy().convert('RGBA')
        draw = ImageDraw.Draw(image, 'RGBA')
        for workstation_id in self.core.world.floor_layout(floor_id)['workstation_groups']:
            access = self.core.resolve_workstation_navigation_access(floor_id, workstation_id)
            for cell in access['reachable_approach_cells_uv']:
                draw.polygon(
                    self._cell_polygon(cell),
                    fill=(35, 220, 105, 155),
                    outline=(180, 255, 205, 240),
                )
        return self._detail_crop(image)

    @staticmethod
    def _detail_crop(image: Image.Image) -> Image.Image:
        # F0 workstation cluster, enlarged with nearest-neighbor to keep grid/pixels crisp.
        crop = image.crop((210, 250, 390, 390))
        return crop.resize((720, 560), Image.Resampling.NEAREST)

    def generate_bundle(self, output_root: str | Path) -> dict:
        output_root = Path(output_root).resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        floor_id = 'floor00'

        routes = {row['route_id']: row for row in self.movement_qa.resolve_routes()}
        distant = routes['distant_target']
        start = tuple(distant['start_uv'])
        goal = tuple(distant['goal_uv'])
        movement = self.core.resolve_character_movement(0, floor_id, start, goal)
        compiled = self.core.resolve_navigation_cells(floor_id)
        closure_cells = {tuple(cell) for cell in compiled['closure_cells_uv']}
        path_cells = {tuple(cell) for cell in movement['path_cells_uv']}
        if path_cells & closure_cells:
            raise ValueError('Distant route intersects supplemental closure occupancy')

        overlay = self._render_overlay(floor_id, movement['path_cells_uv'])
        overlay_path = output_root / 'floor00_closure_route_overlay.png'
        overlay.save(overlay_path)
        detail = self._detail_crop(overlay)
        detail_path = output_root / 'floor00_closure_detail_x4.png'
        detail.save(detail_path)
        clearance_detail = self._detail_crop(self._render_overlay(floor_id, []))
        clearance_detail_path = output_root / 'floor00_clearance_detail_x4.png'
        clearance_detail.save(clearance_detail_path)
        approach_detail = self._render_approach_detail(overlay, floor_id)
        approach_detail_path = output_root / 'floor00_closure_approach_detail_x4.png'
        approach_detail.save(approach_detail_path)

        frames = self.movement_qa._movement_frames(0, movement)
        gif_path = output_root / 'floor00_distant_target_closure_fixed.gif'
        self.movement_qa._save_gif(frames, gif_path)

        type_counts = Counter(row['closure_type'] for row in compiled['closures'])
        report = {
            'schema': 'gds_phase8b_occupancy_closure_qa_v1',
            'status': 'PASS',
            'floor_id': floor_id,
            'base_occupied_cell_count': compiled['base_occupied_cell_count'],
            'closure_cell_count': compiled['closure_cell_count'],
            'clearance_cell_count': compiled.get('clearance_cell_count', 0),
            'protected_ingress_cell_count': compiled.get('protected_ingress_cell_count', 0),
            'final_occupied_cell_count': compiled['occupied_cell_count'],
            'walkable_cell_count': compiled['walkable_cell_count'],
            'workstation_desk_chair_closure_count': type_counts.get('workstation_desk_chair', 0),
            'desk_desk_closure_count': type_counts.get('desk_desk_seam', 0),
            'path_cell_count': movement['path_cell_count'],
            'path_intersects_closure': False,
            'overlay_png': str(overlay_path),
            'detail_png': str(detail_path),
            'clearance_detail_png': str(clearance_detail_path),
            'approach_detail_png': str(approach_detail_path),
            'distant_motion_gif': str(gif_path),
            'closure_records': compiled['closures'],
            'artifact_policy': 'external_review_only_not_canonical_release_payload',
        }
        report_path = output_root / 'PHASE8B_CLOSURE_QA.json'
        report['report_json'] = str(report_path)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Render Phase 8B occupancy-closure QA artifacts.')
    parser.add_argument('--output', required=True, help='External review output directory')
    args = parser.parse_args(argv)
    report = Phase8BClosureQA(ROOT).generate_bundle(args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
