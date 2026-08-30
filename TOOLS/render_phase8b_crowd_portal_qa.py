from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any
import sys

from PIL import Image, ImageChops, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from RUNTIME.central_core import CentralGameCore


class CrowdPortalRenderer:
    """Render crowd portal QA loops.

    Movement-profile changes:
    - assigns a stable 125-175% travel speed to each character
    - samples every actor independently on one shared 60 ms playback tick
    - stabilizes visual facing across A* staircase paths
    - scales walk-frame distance with travel speed to avoid fast leg pedalling
    - reduces peak memory during GIF rendering by quantizing frames eagerly,
      allowing full multi-floor crowd QA exports in one pass
    """

    FRAME_MS = 60
    EMPTY_TAIL_FRAMES = 8

    def __init__(self, root: Path):
        self.root = Path(root)
        self.core = CentralGameCore(self.root)
        self.depth = self.core.walking_depth
        self.move = self.core.character_movement
        self._sprite_cache: dict[tuple[int, str, str], list[Image.Image]] = {}

    def uvxy(self, cell: tuple[int, int]) -> tuple[float, float]:
        return self.move.uv_cell_center_to_pixel(*cell)

    def adjacent_outside(self, floor_id: str, inside_uv: tuple[int, int]) -> tuple[int, int]:
        portal = self.core.resolve_portal(floor_id)
        outside = [tuple(cell) for cell in portal['outside_cells_uv']]
        adjacent = [cell for cell in outside if abs(cell[0] - inside_uv[0]) + abs(cell[1] - inside_uv[1]) == 1]
        if adjacent:
            return sorted(adjacent, key=lambda c: (c[1], c[0]))[0]
        return min(outside, key=lambda c: (abs(c[0] - inside_uv[0]) + abs(c[1] - inside_uv[1]), c[1], c[0]))

    def portal_starts(self, floor_id: str, count: int) -> list[tuple[int, int]]:
        inside = [tuple(cell) for cell in self.core.resolve_portal(floor_id)['inside_cells_uv']]
        if count == 1:
            return [inside[len(inside) // 2]]
        return [inside[round(i * (len(inside) - 1) / max(1, count - 1))] for i in range(count)]

    def list_floor_ids(self) -> list[str]:
        registry_path = self.root / 'WORLD' / 'REGISTRY' / 'floors.json'
        payload = json.loads(registry_path.read_text(encoding='utf-8'))
        floors = payload.get('floors', {})
        return sorted(floors.keys(), key=lambda floor_id: int(floor_id.replace('floor', '')))

    def distributed_targets(self, floor_id: str, count: int) -> list[tuple[int, int]]:
        nav = self.core.resolve_navigation_cells(floor_id)
        walkable = [tuple(cell) for cell in nav['walkable_cells_uv']]
        portal_start = tuple(self.core.resolve_portal_navigation_start(floor_id))
        candidates = walkable[::11]

        def md(a: tuple[int, int], b: tuple[int, int]) -> int:
            return abs(a[0] - b[0]) + abs(a[1] - b[1])

        candidate_distances = {cell: md(cell, portal_start) for cell in candidates}
        max_distance = max(candidate_distances.values())
        low = max(12, int(round(max_distance * 0.28)))
        high = max(low + 1, int(round(max_distance * 0.68)))
        filtered = [cell for cell in candidates if low <= candidate_distances[cell] <= high]
        if len(filtered) < count:
            filtered = [cell for cell in candidates if candidate_distances[cell] >= low]
        if len(filtered) < count:
            filtered = candidates

        target_radii = []
        if count == 1:
            target_radii = [max_distance * 0.52]
        else:
            for idx in range(count):
                t = idx / max(1, count - 1)
                target_radii.append(max_distance * (0.38 + 0.24 * t))

        selected: list[tuple[int, int]] = []
        for radius in target_radii:
            remaining = [cell for cell in filtered if cell not in selected]
            if not remaining:
                break
            if not selected:
                choice = min(remaining, key=lambda c: (abs(candidate_distances[c] - radius), c[1], c[0]))
            else:
                choice = max(
                    remaining,
                    key=lambda c: (
                        min(md(c, s) for s in selected),
                        -abs(candidate_distances[c] - radius),
                        candidate_distances[c],
                        c[1],
                        c[0],
                    ),
                )
            selected.append(choice)

        remaining = [cell for cell in filtered if cell not in selected]
        while len(selected) < count and remaining:
            choice = max(
                remaining,
                key=lambda c: (
                    min(md(c, s) for s in selected) if selected else candidate_distances[c],
                    candidate_distances[c],
                    c[1],
                    c[0],
                ),
            )
            selected.append(choice)
            remaining = [cell for cell in filtered if cell not in selected]
        return selected[:count]

    def sprite_frames(self, query: int, action: str, direction: str) -> list[Image.Image]:
        key = (query, action, direction)
        if key not in self._sprite_cache:
            self._sprite_cache[key] = self.core.render_character(query, action, direction).frames
        return self._sprite_cache[key]

    def sprite(self, query: int, action: str, direction: str, frame_idx: int) -> Image.Image:
        frames = self.sprite_frames(query, action, direction)
        return frames[frame_idx % len(frames)]

    @staticmethod
    def with_alpha(image: Image.Image, alpha: float) -> Image.Image:
        if alpha >= 0.999:
            return image
        rgba = image.convert('RGBA').copy()
        channel = rgba.getchannel('A').point(lambda v: int(v * alpha))
        rgba.putalpha(channel)
        return rgba

    def move_sprite_index(
        self,
        query: int,
        direction: str,
        cumulative_distance_px: float,
        movement_profile: dict[str, Any],
    ) -> int:
        frames = self.sprite_frames(query, 'move', direction)
        return self.move.walk_cycle_frame_index(
            cumulative_distance_px,
            len(frames),
            frame_distance_cells=float(movement_profile['walk_frame_distance_cells']),
        )

    @staticmethod
    def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
        return math.hypot(b[0] - a[0], b[1] - a[1])

    def _transition_states(
        self,
        start_xy: tuple[float, float],
        end_xy: tuple[float, float],
        direction: str,
        phase: str,
        alphas: list[float],
        *,
        distance_offset_px: float,
        movement_profile: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], float]:
        states: list[dict[str, Any]] = []
        segment_distance = self._distance(start_xy, end_xy)
        count = len(alphas)
        for idx, alpha in enumerate(alphas, start=1):
            t = idx / count
            xy = (
                start_xy[0] + (end_xy[0] - start_xy[0]) * t,
                start_xy[1] + (end_xy[1] - start_xy[1]) * t,
            )
            cumulative = distance_offset_px + segment_distance * t
            states.append({
                'ground_xy': xy,
                'direction': direction,
                'raw_direction': direction,
                'action': 'move',
                'cumulative_distance_px': cumulative,
                'alpha': alpha,
                'phase': phase,
                'speed_percent': movement_profile['speed_percent'],
                'speed_multiplier': movement_profile['speed_multiplier'],
            })
        return states, distance_offset_px + segment_distance

    def _path_states(
        self,
        path: list[tuple[int, int]],
        phase: str,
        *,
        distance_offset_px: float,
        movement_profile: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], float]:
        raw = self.move.sample_path_timeline(
            path,
            speed_multiplier=float(movement_profile['speed_multiplier']),
            tick_ms=int(movement_profile['playback_tick_ms']),
        )
        states = []
        last_distance = distance_offset_px
        for sample in raw:
            xy = tuple(map(float, sample['ground_xy']))
            cumulative = distance_offset_px + float(sample['cumulative_distance_px'])
            states.append({
                'ground_xy': xy,
                'direction': sample['direction'],
                'raw_direction': sample['raw_direction'],
                'action': 'move',
                'cumulative_distance_px': cumulative,
                'alpha': 1.0,
                'phase': phase,
                'step_index': sample['step_index'],
                'tick_index': sample['tick_index'],
                'speed_percent': movement_profile['speed_percent'],
                'speed_multiplier': movement_profile['speed_multiplier'],
            })
            last_distance = cumulative
        return states, last_distance

    def states_for(
        self,
        floor_id: str,
        query: int,
        start_uv: tuple[int, int],
        target_uv: tuple[int, int],
    ) -> tuple[list[dict[str, Any]], tuple[int, int], dict[str, Any]]:
        movement_profile = self.core.resolve_character_movement_profile(query)
        outside_uv = self.adjacent_outside(floor_id, start_uv)
        entry_dir = self.move.direction_for_step(outside_uv, start_uv)
        exit_dir = self.move.direction_for_step(start_uv, outside_uv)
        out_path = [tuple(cell) for cell in self.core.find_navigation_path(floor_id, start_uv, target_uv)['path_cells_uv']]
        back_path = [tuple(cell) for cell in self.core.find_navigation_path(floor_id, target_uv, start_uv)['path_cells_uv']]

        states: list[dict[str, Any]] = []
        cumulative = 0.0
        outside_xy = self.uvxy(outside_uv)
        start_xy = self.uvxy(start_uv)
        goal_xy = self.uvxy(target_uv)

        entry_states, cumulative = self._transition_states(
            outside_xy,
            start_xy,
            entry_dir,
            'entry',
            [0.25, 0.5, 0.75, 1.0],
            distance_offset_px=cumulative,
            movement_profile=movement_profile,
        )
        states.extend(entry_states)

        outward_states, cumulative = self._path_states(
            out_path,
            'outward',
            distance_offset_px=cumulative,
            movement_profile=movement_profile,
        )
        states.extend(outward_states)

        goal_dir = outward_states[-1]['direction'] if outward_states else entry_dir
        idle_frames = len(self.sprite_frames(query, 'idle', goal_dir))
        for i in range(4):
            states.append({
                'ground_xy': goal_xy,
                'direction': goal_dir,
                'action': 'idle',
                'idle_frame_index': i % idle_frames,
                'alpha': 1.0,
                'phase': 'goal_hold',
                'speed_percent': movement_profile['speed_percent'],
                'speed_multiplier': movement_profile['speed_multiplier'],
            })

        return_states, cumulative = self._path_states(
            back_path,
            'return',
            distance_offset_px=cumulative,
            movement_profile=movement_profile,
        )
        states.extend(return_states)

        arrival_dir = return_states[-1]['direction'] if return_states else goal_dir
        arrival_idle_frames = len(self.sprite_frames(query, 'idle', arrival_dir))
        for i in range(3):
            states.append({
                'ground_xy': start_xy,
                'direction': arrival_dir,
                'action': 'idle',
                'idle_frame_index': i % arrival_idle_frames,
                'alpha': 1.0,
                'phase': 'portal_hold',
                'speed_percent': movement_profile['speed_percent'],
                'speed_multiplier': movement_profile['speed_multiplier'],
            })

        exit_states, cumulative = self._transition_states(
            start_xy,
            outside_xy,
            exit_dir,
            'exit',
            [1.0, 0.75, 0.5, 0.25],
            distance_offset_px=cumulative,
            movement_profile=movement_profile,
        )
        states.extend(exit_states)

        return states, outside_uv, movement_profile

    def changed_outside_actor_bboxes(self, base: Image.Image, frame: Image.Image, bboxes: list[tuple[int, int, int, int]]) -> int:
        diff = ImageChops.difference(base, frame).convert('RGBA')
        draw = ImageDraw.Draw(diff)
        for bbox in bboxes:
            draw.rectangle(bbox, fill=(0, 0, 0, 0))
        return 0 if diff.getbbox() is None else 1

    def render_floor(self, floor_id: str, agent_count: int, output_root: Path) -> dict[str, Any]:
        starts = self.portal_starts(floor_id, agent_count)
        targets = self.distributed_targets(floor_id, agent_count)
        agent_specs = []
        for query, (start_uv, target_uv) in enumerate(zip(starts, targets)):
            states, outside_uv, movement_profile = self.states_for(floor_id, query, start_uv, target_uv)
            start_delay = query * 8
            agent_specs.append((query, start_uv, target_uv, outside_uv, start_delay, movement_profile, states))

        total_frames = max(start_delay + len(states) for *_head, start_delay, _profile, states in agent_specs) + self.EMPTY_TAIL_FRAMES
        base = self.core.render_floor(floor_id).convert('RGBA')

        sampled_checks = {0, total_frames // 3, (2 * total_frames) // 3, total_frames - 1}
        sampled_checks = sorted(sampled_checks)
        max_static = 0

        palette = None
        paletted_frames: list[Image.Image] = []

        for frame_idx in range(total_frames):
            actors = []
            bboxes = []
            for query, start_uv, target_uv, outside_uv, start_delay, movement_profile, states in agent_specs:
                local = frame_idx - start_delay
                if local < 0 or local >= len(states):
                    continue
                state = states[local]
                if state['action'] == 'move':
                    sprite_idx = self.move_sprite_index(
                        query,
                        state['direction'],
                        state['cumulative_distance_px'],
                        movement_profile,
                    )
                else:
                    sprite_idx = int(state.get('idle_frame_index', 0))
                sprite = self.with_alpha(self.sprite(query, state['action'], state['direction'], sprite_idx), state['alpha'])
                xy = tuple(map(float, state['ground_xy']))
                actors.append({
                    'sprite': sprite,
                    'ground_xy': xy,
                    'ground_anchor_px': tuple(self.move.GROUND_ANCHOR_PX),
                })
                bboxes.append(self.depth._actor_bbox(sprite, xy, tuple(self.move.GROUND_ANCHOR_PX)))
            frame = self.depth.composite_characters(floor_id, actors)
            if frame_idx in sampled_checks:
                max_static = max(max_static, self.changed_outside_actor_bboxes(base, frame, bboxes))
            if palette is None:
                paletted = frame.convert('P', palette=Image.Palette.ADAPTIVE, colors=256)
                palette = paletted.getpalette()
            else:
                paletted = frame.convert('RGB').quantize(palette=paletted_frames[0], dither=Image.Dither.NONE)
            paletted_frames.append(paletted)

        gif_path = output_root / f'{floor_id}_crowd_portal_v184.gif'
        paletted_frames[0].save(gif_path, save_all=True, append_images=paletted_frames[1:], duration=self.FRAME_MS, loop=0, disposal=2)

        overlay = base.copy()
        draw = ImageDraw.Draw(overlay, 'RGBA')
        colors = [
            (255, 92, 92, 180), (85, 220, 255, 180), (255, 200, 90, 180), (189, 137, 255, 180),
            (92, 255, 170, 180), (255, 115, 196, 180), (212, 255, 119, 180), (125, 167, 255, 180),
        ]
        summary_agents = []
        for idx, (query, start_uv, target_uv, outside_uv, start_delay, movement_profile, states) in enumerate(agent_specs):
            color = colors[idx % len(colors)]
            pts = [state['ground_xy'] for state in states if state['phase'] in {'outward', 'return'}]
            if len(pts) >= 2:
                draw.line(pts, fill=color, width=2)
            sx, sy = self.uvxy(start_uv)
            gx, gy = self.uvxy(target_uv)
            draw.ellipse((sx - 3, sy - 3, sx + 3, sy + 3), fill=(255, 255, 255, 255), outline=(0, 0, 0, 255))
            draw.ellipse((gx - 4, gy - 4, gx + 4, gy + 4), fill=color[:3] + (255,), outline=(0, 0, 0, 255))
            summary_agents.append({
                'character_id': self.core.resolve_character_id(query),
                'start_uv': list(start_uv),
                'outside_uv': list(outside_uv),
                'target_uv': list(target_uv),
                'start_delay': start_delay,
                'state_count': len(states),
                'speed_percent': movement_profile['speed_percent'],
                'walk_frame_distance_cells': movement_profile['walk_frame_distance_cells'],
            })
        overlay_path = output_root / f'{floor_id}_crowd_routes_overlay_v184.png'
        overlay.save(overlay_path)

        return {
            'floor_id': floor_id,
            'gif': str(gif_path),
            'overlay': str(overlay_path),
            'agent_count': agent_count,
            'frame_count': total_frames,
            'frame_ms': self.FRAME_MS,
            'baseline_substeps_per_cell': self.move.DEFAULT_SUBSTEPS_PER_CELL,
            'speed_range_percent': [
                self.move.MIN_MOVE_SPEED_PERCENT,
                self.move.MAX_MOVE_SPEED_PERCENT,
            ],
            'walk_frame_distance_policy': '0.65 cells multiplied by actor speed',
            'static_world_changed_pixels_outside_actor_bounds': max_static,
            'portal_entry_exit_adjacent': all(abs(outside_uv[0] - start_uv[0]) + abs(outside_uv[1] - start_uv[1]) == 1 for _, start_uv, _, outside_uv, _, _, _ in agent_specs),
            'empty_tail_frames': self.EMPTY_TAIL_FRAMES,
            'agents': summary_agents,
        }

    def render_all(self, output_root: Path) -> dict[str, Any]:
        output_root.mkdir(parents=True, exist_ok=True)
        results = [
            self.render_floor('floor00', 6, output_root),
            self.render_floor('floor01', 7, output_root),
            self.render_floor('floor02', 8, output_root),
        ]
        report = {
            'schema': 'gds_phase8b_v184_crowd_portal_qa_v1',
            'status': 'PASS',
            'notes': [
                'Each character gets one deterministic movement speed from 125-175%.',
                'All actors use one 60ms playback tick and advance by their own speed.',
                'Walk cadence is distance-driven with a speed-scaled stride distance.',
                'Visual direction uses path lookahead and hysteresis to suppress A* staircase flicker.',
                'Actors despawn completely after exit fade-out.',
            ],
            'floors': results,
        }
        for row in results:
            if row['static_world_changed_pixels_outside_actor_bounds'] != 0 or not row['portal_entry_exit_adjacent']:
                report['status'] = 'FAIL'
        report_path = output_root / 'PHASE8B_V184_CROWD_PORTAL_QA.json'
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        report['report_json'] = str(report_path)
        return report

    def render_all_registered_floors(self, output_root: Path, *, default_agent_count: int = 6) -> dict[str, Any]:
        output_root.mkdir(parents=True, exist_ok=True)
        results = []
        family_large = {'floor02', 'floor03', 'floor04', 'floor05', 'floor06', 'floor07', 'floor08', 'floor09', 'floor11', 'floor12', 'floor13', 'floor14', 'floor15', 'floor16', 'floor17', 'floor18', 'floor19', 'floor21', 'floor31', 'floor33', 'floor34', 'floor35', 'floor36'}
        for floor_id in self.list_floor_ids():
            agent_count = default_agent_count
            if floor_id == 'floor00':
                agent_count = 4
            elif floor_id == 'floor01':
                agent_count = 4
            elif floor_id in family_large:
                agent_count = 5
            results.append(self.render_floor(floor_id, agent_count, output_root))
        report = {
            'schema': 'gds_phase8c_v184_all_floor_crowd_qa_v1',
            'status': 'PASS',
            'notes': [
                'All registered floors rendered with stable per-character 125-175% movement profiles.',
                'Each actor advances independently on a shared 60ms playback tick.',
                'Walk stride and stabilized facing are sourced from CharacterMovementCore.',
                'GIF rendering quantizes frames eagerly to lower peak memory during full-bundle export.',
            ],
            'floor_count': len(results),
            'floors': results,
        }
        for row in results:
            if row['static_world_changed_pixels_outside_actor_bounds'] != 0 or not row['portal_entry_exit_adjacent']:
                report['status'] = 'FAIL'
        report_path = output_root / 'PHASE8C_V184_ALL_FLOOR_CROWD_QA.json'
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        report['report_json'] = str(report_path)
        return report


if __name__ == '__main__':
    project_root = Path(__file__).resolve().parents[1]
    out = project_root / 'LOCAL_REVIEW' / 'PHASE8B_CROWD_PORTAL_QA'
    renderer = CrowdPortalRenderer(project_root)
    result = renderer.render_all(out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['status'] == 'PASS' else 1)
