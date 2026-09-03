from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


try:
    from TOOLS._bootstrap import ensure_project_root
except ModuleNotFoundError:
    from _bootstrap import ensure_project_root

PROJECT_ROOT = ensure_project_root(__file__)

from TOOLS.render_phase8b_crowd_portal_qa import CrowdPortalRenderer
from TOOLS.render_phase8c_dense_crowd_qa import write_keyframe_sheet


class CeoDeskDepthRenderer(CrowdPortalRenderer):
    """Render dense routes that deliberately finish in front of the CEO desk.

    This is a QA-only renderer. It reuses the production crowd scheduler and
    walking-depth compositor while choosing reachable targets from the local
    CEO front envelope. No runtime navigation or actor lifecycle behavior is
    changed by this tool.
    """

    AGENT_COUNT = 10
    SEED = 8042

    def __init__(self, root: Path):
        super().__init__(root)
        self._target_metadata: dict[str, list[dict[str, Any]]] = {}

    @staticmethod
    def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    @staticmethod
    def _spread_targets(
        candidates: list[dict[str, Any]], count: int
    ) -> list[dict[str, Any]]:
        if not candidates or count <= 0:
            return []
        remaining = list(candidates)
        selected = [
            min(
                remaining,
                key=lambda row: (
                    abs(float(row['front_margin']) - 10.0),
                    row['ground_xy'][1],
                    row['ground_xy'][0],
                    row['uv'][1],
                    row['uv'][0],
                ),
            )
        ]
        remaining.remove(selected[0])
        while remaining and len(selected) < count:
            choice = max(
                remaining,
                key=lambda row: (
                    min(
                        CeoDeskDepthRenderer._manhattan(
                            tuple(row['uv']), tuple(chosen['uv'])
                        )
                        for chosen in selected
                    ),
                    abs(float(row['front_margin']) - 10.0),
                    -row['ground_xy'][1],
                    -row['ground_xy'][0],
                    -row['uv'][1],
                    -row['uv'][0],
                ),
            )
            selected.append(choice)
            remaining.remove(choice)
        return selected

    def _ceo_target_candidates(self, floor_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        rows = {
            row['placement_id']: row
            for row in self.depth.resolve_occluders(floor_id)
        }
        desk = rows['ceo_desk_cell2']
        corners = desk['depth_footprint_corners_world_px']
        front_edge = desk['depth_front_edge_world_px']
        if front_edge is None:
            raise RuntimeError(f'{floor_id}: CEO desk is missing a front-edge profile')
        min_x = min(x for x, _ in corners)
        max_x = max(x for x, _ in corners)
        scalar_anchor = float(desk['depth_anchor_y_px'])
        compiled = self.core.resolve_navigation_cells(floor_id)

        front_candidates: list[dict[str, Any]] = []
        nearby_candidates: list[dict[str, Any]] = []
        for cell in compiled['walkable_cells_uv']:
            uv = tuple(cell)
            x, y = self.uvxy(uv)
            local_front_y = self.depth._front_edge_y_at_x(front_edge, x)
            front_margin = float(y) - float(local_front_y)
            base = {
                'uv': list(uv),
                'ground_xy': [int(x), int(y)],
                'front_y': round(float(local_front_y), 4),
                'front_margin': round(front_margin, 4),
                'scalar_anchor_y': int(scalar_anchor),
            }
            # These targets deliberately occupy the band that used to be
            # misclassified by the scalar max-Y fallback, while remaining
            # visibly in front of the CEO desk's local envelope.
            if min_x <= x <= max_x and 4.0 <= front_margin <= 24.0 and y < scalar_anchor:
                front_candidates.append(base)
            if (
                min_x - 32 <= x <= max_x + 32
                and -2.0 <= front_margin <= 36.0
                and y <= scalar_anchor + 36
            ):
                nearby_candidates.append(base)

        front_candidates.sort(key=lambda row: (row['uv'][1], row['uv'][0]))
        nearby_candidates.sort(key=lambda row: (row['uv'][1], row['uv'][0]))
        return front_candidates, {
            'profile_id': desk['depth_profile_id'],
            'front_edge_world_px': front_edge,
            'depth_anchor_y_px': int(scalar_anchor),
            'front_candidate_count': len(front_candidates),
            'nearby_candidate_count': len(nearby_candidates),
        }

    def distributed_targets(self, floor_id: str, count: int) -> list[tuple[int, int]]:
        front_candidates, metadata = self._ceo_target_candidates(floor_id)
        if len(front_candidates) < count:
            raise RuntimeError(
                f'{floor_id}: only {len(front_candidates)} CEO front targets for {count} actors'
            )
        selected = self._spread_targets(front_candidates, count)
        self._target_metadata[floor_id] = [
            {**row, 'target_role': 'ceo_front_envelope'}
            for row in selected
        ]
        self._target_metadata[f'{floor_id}:meta'] = metadata
        return [tuple(row['uv']) for row in selected]

    def _rename_and_annotate_outputs(
        self,
        floor_id: str,
        output_root: Path,
        row: dict[str, Any],
    ) -> dict[str, Any]:
        old_gif = Path(row['gif'])
        old_overlay = Path(row['overlay'])
        gif_path = output_root / f'{floor_id}_ceo_desk_depth_10_actor.gif'
        overlay_path = output_root / f'{floor_id}_ceo_desk_depth_routes.png'
        if old_gif != gif_path:
            old_gif.replace(gif_path)

        overlay = Image.open(old_overlay).convert('RGBA')
        draw = ImageDraw.Draw(overlay, 'RGBA')
        metadata = self._target_metadata[f'{floor_id}:meta']
        edge = [tuple(point) for point in metadata['front_edge_world_px']]
        draw.line(edge, fill=(255, 232, 64, 255), width=3, joint='curve')
        target_rows = self._target_metadata[floor_id]
        for target in target_rows:
            x, y = target['ground_xy']
            draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=(255, 232, 64, 220), outline=(40, 40, 40, 255))
        if old_overlay != overlay_path:
            old_overlay.unlink(missing_ok=True)
        overlay.save(overlay_path)

        row.update({
            'gif': str(gif_path),
            'overlay': str(overlay_path),
            'target_sampling': 'deterministic_reachable_ceo_front_envelope',
            'target_role': 'ceo_front_envelope',
            'target_count': len(target_rows),
            'front_candidate_count': metadata['front_candidate_count'],
            'ceo_depth_profile_id': metadata['profile_id'],
            'ceo_front_edge_world_px': metadata['front_edge_world_px'],
            'target_ground_xy': [row['ground_xy'] for row in target_rows],
        })
        return row

    def render_floor(self, floor_id: str, agent_count: int, output_root: Path) -> dict[str, Any]:
        if agent_count != self.AGENT_COUNT:
            raise ValueError(f'CEO depth QA requires exactly {self.AGENT_COUNT} actors')
        row = super().render_floor(floor_id, agent_count, output_root)
        return self._rename_and_annotate_outputs(floor_id, output_root, row)


def choose_floors(renderer: CeoDeskDepthRenderer, seed: int) -> tuple[list[str], list[str]]:
    required = ['floor00', 'floor01', 'floor02']
    remaining = [floor_id for floor_id in renderer.list_floor_ids() if floor_id not in required]
    extras = random.Random(seed).sample(remaining, 2)
    return required + extras, extras


def main() -> int:
    output_root = PROJECT_ROOT / 'LOCAL_REVIEW' / 'CEO_DESK_DEPTH_QA_20260831'
    output_root.mkdir(parents=True, exist_ok=True)
    renderer = CeoDeskDepthRenderer(PROJECT_ROOT)
    floor_ids, random_floor_ids = choose_floors(renderer, renderer.SEED)
    floors: list[dict[str, Any]] = []
    for floor_id in floor_ids:
        row = renderer.render_floor(floor_id, renderer.AGENT_COUNT, output_root)
        keyframe_path = output_root / f'{floor_id}_ceo_desk_depth_keyframes.png'
        row['keyframes'] = write_keyframe_sheet(Path(row['gif']), keyframe_path)
        row['timeline_frame_count'] = row['frame_count']
        row['gif_frame_count'] = row['keyframes']['frame_count']
        row['gif_encoder_coalesced_frames'] = row['gif_frame_count'] < row['timeline_frame_count']
        row['requested_agent_count'] = renderer.AGENT_COUNT
        floors.append(row)

    report: dict[str, Any] = {
        'schema': 'gds.ceo_desk_depth_qa.v1',
        'status': 'PASS',
        'seed': renderer.SEED,
        'floor_order': floor_ids,
        'required_floors': ['floor00', 'floor01', 'floor02'],
        'random_floors': random_floor_ids,
        'agent_count_per_floor': renderer.AGENT_COUNT,
        'target_sampling': 'deterministic_reachable_ceo_front_envelope',
        'target_role': 'ceo_front_envelope',
        'source_renderer': 'TOOLS/render_phase8b_crowd_portal_qa.py',
        'floors': floors,
    }
    for row in floors:
        if (
            row.get('requested_agent_count') != renderer.AGENT_COUNT
            or row.get('agent_count') != renderer.AGENT_COUNT
            or row.get('target_count') != renderer.AGENT_COUNT
            or row.get('front_candidate_count', 0) < renderer.AGENT_COUNT
            or row.get('gif_frame_count', 0) < 1
            or row.get('static_world_changed_pixels_outside_actor_bounds') != 0
            or not row.get('portal_entry_exit_adjacent')
            or not row.get('collision_free')
            or row.get('active_wait_ticks_total') != 0
        ):
            report['status'] = 'FAIL'
    report_path = output_root / 'CEO_DESK_DEPTH_QA.json'
    report['report_json'] = str(report_path)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
