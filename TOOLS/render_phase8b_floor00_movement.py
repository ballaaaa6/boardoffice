from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

if __package__ is None or __package__ == '':
    ROOT = Path(__file__).resolve().parents[1]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
else:
    ROOT = Path(__file__).resolve().parents[1]

from RUNTIME.central_core import CentralGameCore
from WORLD.RUNTIME.pathfinding_core import PathfindingCore


class Phase8BFloor00MovementQA:
    """Deterministic Floor00 movement proof bundle using real project assets only."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.core = CentralGameCore(self.root)
        self.pathfinding = PathfindingCore(self.root / 'WORLD')
        self.movement = self.core.character_movement

    def _resolve_workstation_approach(self, floor_id: str, workstation_id: str, start: tuple[int, int]) -> tuple[int, int]:
        access = self.core.resolve_workstation_navigation_access(floor_id, workstation_id)
        candidates = [tuple(cell) for cell in access['reachable_approach_cells_uv']]
        ranked = []
        for cell in candidates:
            path = self.core.find_navigation_path(floor_id, start, cell)
            ranked.append((path['path_cell_count'], cell[1], cell[0], cell))
        if not ranked:
            raise ValueError(f'No reachable approach cell for {floor_id}.{workstation_id}')
        return min(ranked)[-1]

    def resolve_routes(self) -> list[dict]:
        floor_id = 'floor00'
        start = self.pathfinding.resolve_portal_start(floor_id)
        near = self.pathfinding.resolve_near_target(floor_id, start, min_distance=6)
        distant = self.pathfinding.resolve_distant_target(floor_id, start)
        workstation_id = 'ws4'
        approach = self._resolve_workstation_approach(floor_id, workstation_id, start)
        return [
            {
                'route_id': 'near_open_target',
                'floor_id': floor_id,
                'start_uv': list(start),
                'goal_uv': list(near),
            },
            {
                'route_id': 'distant_target',
                'floor_id': floor_id,
                'start_uv': list(start),
                'goal_uv': list(distant),
            },
            {
                'route_id': 'workstation_approach',
                'floor_id': floor_id,
                'start_uv': list(start),
                'goal_uv': list(approach),
                'workstation_id': workstation_id,
            },
        ]

    def _cell_polygon(self, cell: tuple[int, int] | list[int]) -> list[tuple[int, int]]:
        u, v = int(cell[0]), int(cell[1])
        rn = self.core.room_navigation
        return [
            rn.uv_vertex_to_pixel(u, v),
            rn.uv_vertex_to_pixel(u + 1, v),
            rn.uv_vertex_to_pixel(u + 1, v + 1),
            rn.uv_vertex_to_pixel(u, v + 1),
        ]

    def _draw_debug_overlay(self, record: dict) -> Image.Image:
        base = self.core.render_floor(record['floor_id']).convert('RGBA')
        draw = ImageDraw.Draw(base, 'RGBA')
        for cell in record['path_cells_uv']:
            draw.polygon(
                self._cell_polygon(cell),
                fill=(255, 64, 64, 88),
                outline=(255, 64, 64, 180),
            )
        centers = [self.movement.uv_cell_center_to_pixel(*cell) for cell in record['path_cells_uv']]
        if len(centers) >= 2:
            draw.line(centers, fill=(255, 255, 255, 225), width=2)
        sx, sy = centers[0]
        gx, gy = centers[-1]
        draw.ellipse((sx - 5, sy - 5, sx + 5, sy + 5), fill=(255, 220, 0, 255), outline=(0, 0, 0, 255))
        draw.ellipse((gx - 5, gy - 5, gx + 5, gy + 5), fill=(0, 220, 255, 255), outline=(0, 0, 0, 255))
        return base

    def _composite_character(self, floor_id: str, sprite: Image.Image, center_xy: tuple[float, float]) -> Image.Image:
        return self.core.walking_depth.composite_character(
            floor_id,
            sprite,
            center_xy,
            ground_anchor_px=self.movement.GROUND_ANCHOR_PX,
        )

    def _movement_frames(self, character_query: int | str, record: dict, *, max_step_samples: int = 80) -> list[Image.Image]:
        path = [tuple(cell) for cell in record['path_cells_uv']]
        step_count = max(0, len(path) - 1)
        stride = max(1, math.ceil(step_count / max_step_samples)) if step_count else 1
        frames: list[Image.Image] = []

        for idx in range(0, step_count, stride):
            cur = path[idx]
            nxt = path[idx + 1]
            direction = self.movement.direction_for_step(cur, nxt)
            action = self.core.render_character(character_query, 'move', direction)
            start_xy = self.movement.uv_cell_center_to_pixel(*cur)
            end_xy = self.movement.uv_cell_center_to_pixel(*nxt)
            sprite = action.frames[(idx // stride) % len(action.frames)]
            fx = start_xy[0] + (end_xy[0] - start_xy[0]) * 0.5
            fy = start_xy[1] + (end_xy[1] - start_xy[1]) * 0.5
            frames.append(self._composite_character(record['floor_id'], sprite, (fx, fy)))

        arrival_dir = record['arrival_action']['direction']
        idle = self.core.render_character(character_query, 'idle', arrival_dir)
        goal_xy = self.movement.uv_cell_center_to_pixel(*path[-1])
        for sprite in idle.frames[:2]:
            frames.append(self._composite_character(record['floor_id'], sprite, goal_xy))
        return frames

    @staticmethod
    def _save_gif(frames: list[Image.Image], path: Path, *, frame_ms: int = 120) -> None:
        paletted = [frame.convert('P', palette=Image.Palette.ADAPTIVE) for frame in frames]
        paletted[0].save(
            path,
            save_all=True,
            append_images=paletted[1:],
            duration=[frame_ms] * len(paletted),
            loop=0,
            disposal=2,
        )

    @staticmethod
    def _make_contact(images: list[tuple[str, Image.Image]]) -> Image.Image:
        cell_w = 600
        cell_h = 624
        sheet = Image.new('RGBA', (cell_w * len(images), cell_h), (18, 20, 24, 255))
        draw = ImageDraw.Draw(sheet)
        for idx, (label, image) in enumerate(images):
            x = idx * cell_w
            sheet.alpha_composite(image.convert('RGBA'), (x, 24))
            draw.text((x + 8, 5), label, fill=(255, 255, 255, 255))
        return sheet

    def _cross_floor_smoke(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for floor_id in ('floor00', 'floor01', 'floor02', 'floor36'):
            start = tuple(self.core.resolve_portal_navigation_start(floor_id))
            goal = tuple(self.core.resolve_distant_navigation_target(floor_id, start))
            path = self.core.find_navigation_path(floor_id, start, goal)
            movement = self.core.resolve_character_movement(0, floor_id, start, goal)
            valid = (
                path['reachable'] is True
                and movement['path_cells_uv'] == path['path_cells_uv']
                and movement['arrival_action']['action'] == 'idle'
            )
            out[floor_id] = {
                'status': 'PASS' if valid else 'FAIL',
                'start_uv': list(start),
                'goal_uv': list(goal),
                'path_cell_count': path['path_cell_count'],
                'segment_count': len(movement['segments']),
                'arrival_direction': movement['arrival_action']['direction'],
            }
        return out

    def generate_bundle(self, output_root: str | Path) -> dict:
        output_root = Path(output_root).resolve()
        debug_dir = output_root / 'DEBUG'
        gif_dir = output_root / 'GIF'
        contact_dir = output_root / 'CONTACT_SHEETS'
        for directory in (debug_dir, gif_dir, contact_dir):
            directory.mkdir(parents=True, exist_ok=True)

        character_query = 0
        route_rows = []
        contact_images: list[tuple[str, Image.Image]] = []
        for route in self.resolve_routes():
            start = tuple(route['start_uv'])
            goal = tuple(route['goal_uv'])
            record = self.core.resolve_character_movement(character_query, route['floor_id'], start, goal)
            debug = self._draw_debug_overlay(record)
            debug_path = debug_dir / f"floor00_{route['route_id']}_debug.png"
            debug.save(debug_path)
            contact_images.append((route['route_id'], debug))

            frames = self._movement_frames(character_query, record)
            gif_path = gif_dir / f"floor00_{route['route_id']}_motion.gif"
            self._save_gif(frames, gif_path)

            row = {
                **route,
                'character_id': record['character_id'],
                'path_cell_count': record['path_cell_count'],
                'segment_count': len(record['segments']),
                'compressed_waypoint_count': len(record['compressed_waypoints_uv']),
                'arrival_direction': record['arrival_action']['direction'],
                'ground_anchor_px': record['ground_anchor_px'],
                'debug_png': str(debug_path),
                'motion_gif': str(gif_path),
            }
            route_rows.append(row)

        contact_path = contact_dir / 'floor00_phase8b_route_contact.png'
        self._make_contact(contact_images).save(contact_path)
        smoke = self._cross_floor_smoke()
        status = 'PASS' if all(row['status'] == 'PASS' for row in smoke.values()) else 'FAIL'
        report = {
            'schema': 'gds_phase8b_single_character_movement_qa_v1',
            'status': status,
            'character_query': character_query,
            'routes': route_rows,
            'cross_floor_smoke': smoke,
            'contact_sheet': str(contact_path),
            'generated_artifact_policy': 'external_review_only_not_canonical_release_payload',
        }
        report_path = output_root / 'PHASE8B_MOVEMENT_QA.json'
        report['report_json'] = str(report_path)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Generate Phase 8B Floor00 movement QA bundle.')
    parser.add_argument('--output', required=True, help='External output directory for QA artifacts')
    args = parser.parse_args(argv)
    result = Phase8BFloor00MovementQA(ROOT).generate_bundle(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
