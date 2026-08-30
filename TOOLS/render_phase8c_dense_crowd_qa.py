from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from TOOLS.render_phase8b_crowd_portal_qa import CrowdPortalRenderer


class DenseCrowdPortalRenderer(CrowdPortalRenderer):
    """Render a reproducible, deliberately dense Phase 8C visual sample.

    This is a QA-only wrapper. It reuses the production renderer and crowd
    scheduler, but samples goals across the full reachable room instead of the
    older mid-radius sample. Runtime navigation and actor lifecycle code are
    not changed by this tool.
    """

    AGENT_COUNT = 10

    @staticmethod
    def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def distributed_targets(self, floor_id: str, count: int) -> list[tuple[int, int]]:
        """Choose farthest-point goals over the reachable room footprint."""
        nav = self.core.resolve_navigation_cells(floor_id)
        walkable = sorted({tuple(cell) for cell in nav['walkable_cells_uv']}, key=lambda cell: (cell[1], cell[0]))
        portal_start = tuple(self.core.resolve_portal_navigation_start(floor_id))
        if not walkable:
            return []

        distances = {cell: self._manhattan(cell, portal_start) for cell in walkable}
        max_distance = max(distances.values())
        # Keep targets away from the portal while still allowing the sample to
        # occupy the whole room, including near and far edges.
        minimum_distance = max(8, int(round(max_distance * 0.16)))
        candidates = [cell for cell in walkable if distances[cell] >= minimum_distance]
        if len(candidates) < count:
            candidates = walkable

        selected: list[tuple[int, int]] = []
        first = max(candidates, key=lambda cell: (distances[cell], -cell[1], -cell[0]))
        selected.append(first)
        while len(selected) < count:
            remaining = [cell for cell in candidates if cell not in selected]
            if not remaining:
                break
            choice = max(
                remaining,
                key=lambda cell: (
                    min(self._manhattan(cell, chosen) for chosen in selected),
                    distances[cell],
                    -cell[1],
                    -cell[0],
                ),
            )
            selected.append(choice)
        return selected[:count]


def choose_floors(renderer: DenseCrowdPortalRenderer, seed: int) -> tuple[list[str], list[str]]:
    required = ['floor00', 'floor01', 'floor02']
    remaining = [floor_id for floor_id in renderer.list_floor_ids() if floor_id not in required]
    extras = random.Random(seed).sample(remaining, 2)
    return required + extras, extras


def write_keyframe_sheet(gif_path: Path, output_path: Path) -> dict[str, Any]:
    """Create a small review sheet without altering the source GIF."""
    with Image.open(gif_path) as gif:
        frame_count = int(getattr(gif, 'n_frames', 1))
        indices = sorted({0, 1, frame_count // 4, frame_count // 2, (3 * frame_count) // 4, max(0, frame_count - 9), frame_count - 1})
        tile_w, tile_h = 300, 330
        columns = 2
        rows = (len(indices) + columns - 1) // columns
        sheet = Image.new('RGBA', (columns * tile_w, rows * tile_h), (248, 248, 248, 255))
        draw = ImageDraw.Draw(sheet)
        for slot, frame_index in enumerate(indices):
            gif.seek(frame_index)
            frame = gif.convert('RGBA').resize((tile_w, tile_w), Image.Resampling.NEAREST)
            x = (slot % columns) * tile_w
            y = (slot // columns) * tile_h
            sheet.alpha_composite(frame, (x, y))
            draw.rectangle((x, y + tile_w, x + tile_w, y + tile_h), fill=(248, 248, 248, 255))
            draw.text((x + 8, y + tile_w + 7), f'frame {frame_index}/{frame_count - 1}', fill=(20, 20, 20, 255))
        sheet.save(output_path)
    return {'path': str(output_path), 'frame_count': frame_count, 'sampled_frames': indices}


def main() -> int:
    seed = 8042
    output_root = PROJECT_ROOT / 'LOCAL_REVIEW' / 'PHASE8C_DENSE_10_ACTOR_QA_20260831'
    output_root.mkdir(parents=True, exist_ok=True)
    renderer = DenseCrowdPortalRenderer(PROJECT_ROOT)
    floor_ids, random_floor_ids = choose_floors(renderer, seed)
    floors: list[dict[str, Any]] = []
    for floor_id in floor_ids:
        row = renderer.render_floor(floor_id, renderer.AGENT_COUNT, output_root)
        gif_path = Path(row['gif'])
        keyframe_path = output_root / f'{floor_id}_dense_keyframes.png'
        row['keyframes'] = write_keyframe_sheet(gif_path, keyframe_path)
        row['timeline_frame_count'] = row['frame_count']
        row['gif_frame_count'] = row['keyframes']['frame_count']
        row['gif_encoder_coalesced_frames'] = row['gif_frame_count'] < row['timeline_frame_count']
        row['target_sampling'] = 'deterministic_farthest_point_over_walkable_room'
        row['requested_agent_count'] = renderer.AGENT_COUNT
        floors.append(row)

    report = {
        'schema': 'gds.phase8c.dense_crowd_qa.v1',
        'status': 'PASS',
        'seed': seed,
        'floor_order': floor_ids,
        'required_floors': ['floor00', 'floor01', 'floor02'],
        'random_floors': random_floor_ids,
        'agent_count_per_floor': renderer.AGENT_COUNT,
        'target_sampling': 'deterministic_farthest_point_over_walkable_room',
        'source_renderer': 'TOOLS/render_phase8b_crowd_portal_qa.py',
        'floors': floors,
    }
    for row in floors:
        if (
            row.get('requested_agent_count') != renderer.AGENT_COUNT
            or row.get('agent_count') != renderer.AGENT_COUNT
            or row.get('gif_frame_count', 0) < 1
            or row.get('static_world_changed_pixels_outside_actor_bounds') != 0
            or not row.get('portal_entry_exit_adjacent')
            or not row.get('collision_free')
            or row.get('active_wait_ticks_total') != 0
        ):
            report['status'] = 'FAIL'
    report_path = output_root / 'PHASE8C_DENSE_10_ACTOR_QA.json'
    report['report_json'] = str(report_path)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
