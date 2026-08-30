from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from TOOLS.render_phase8b_crowd_portal_qa import CrowdPortalRenderer


class Floor02SpeedProfileQA:
    """Render the production movement-profile rules on the canonical F2 map."""

    FLOOR_ID = 'floor02'
    AGENT_COUNT = 8
    ROUTE_DISTANCE_CELLS = 40
    TARGET_HOLD_TICKS = 8
    ENTRY_EXIT_TICKS = 4
    EMPTY_TAIL_TICKS = 8
    SIDEBAR_WIDTH = 220
    COLORS = [
        (255, 92, 92),
        (85, 220, 255),
        (255, 200, 90),
        (189, 137, 255),
        (92, 255, 170),
        (255, 115, 196),
        (212, 255, 119),
        (125, 167, 255),
    ]

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.renderer = CrowdPortalRenderer(self.root)
        self.core = self.renderer.core
        self.movement = self.renderer.move

    def _transition(
        self,
        start_uv: tuple[int, int],
        end_uv: tuple[int, int],
        direction: str,
        alphas: list[float],
        phase: str,
        distance_offset_px: float,
    ) -> tuple[list[dict[str, Any]], float]:
        start_xy = self.renderer.uvxy(start_uv)
        end_xy = self.renderer.uvxy(end_uv)
        segment_distance = self.renderer._distance(start_xy, end_xy)
        states = []
        for index, alpha in enumerate(alphas, start=1):
            progress = index / len(alphas)
            states.append({
                'ground_xy': (
                    start_xy[0] + (end_xy[0] - start_xy[0]) * progress,
                    start_xy[1] + (end_xy[1] - start_xy[1]) * progress,
                ),
                'direction': direction,
                'raw_direction': direction,
                'action': 'move',
                'alpha': alpha,
                'phase': phase,
                'cumulative_distance_px': distance_offset_px + segment_distance * progress,
            })
        return states, distance_offset_px + segment_distance

    def _path(
        self,
        path: list[tuple[int, int]],
        profile: dict[str, Any],
        phase: str,
        distance_offset_px: float,
    ) -> tuple[list[dict[str, Any]], float]:
        samples = self.movement.sample_path_timeline(
            path,
            speed_multiplier=profile['speed_multiplier'],
            tick_ms=profile['playback_tick_ms'],
        )
        states = [{
            'ground_xy': tuple(sample['ground_xy']),
            'direction': sample['direction'],
            'raw_direction': sample['raw_direction'],
            'action': 'move',
            'alpha': 1.0,
            'phase': phase,
            'cumulative_distance_px': distance_offset_px + sample['cumulative_distance_px'],
        } for sample in samples]
        if samples:
            distance_offset_px += samples[-1]['cumulative_distance_px']
        return states, distance_offset_px

    def _hold(
        self,
        uv: tuple[int, int],
        direction: str,
        distance_px: float,
    ) -> list[dict[str, Any]]:
        xy = self.renderer.uvxy(uv)
        return [{
            'ground_xy': xy,
            'direction': direction,
            'raw_direction': direction,
            'action': 'idle',
            'idle_frame_index': index,
            'alpha': 1.0,
            'phase': 'target_hold',
            'cumulative_distance_px': distance_px,
        } for index in range(self.TARGET_HOLD_TICKS)]

    def _agent(self, query: int, start_uv: tuple[int, int]) -> dict[str, Any]:
        profile = self.core.resolve_character_movement_profile(query)
        target_uv = self.core.pathfinding.resolve_near_target(
            self.FLOOR_ID,
            start_uv,
            min_distance=self.ROUTE_DISTANCE_CELLS,
        )
        outward = [
            tuple(cell)
            for cell in self.core.find_navigation_path(
                self.FLOOR_ID,
                start_uv,
                target_uv,
            )['path_cells_uv']
        ]
        returning = list(reversed(outward))
        outside_uv = self.renderer.adjacent_outside(self.FLOOR_ID, start_uv)
        entry_direction = self.movement.direction_for_step(outside_uv, start_uv)
        exit_direction = self.movement.direction_for_step(start_uv, outside_uv)

        states: list[dict[str, Any]] = []
        entry, cumulative = self._transition(
            outside_uv,
            start_uv,
            entry_direction,
            [0.25, 0.5, 0.75, 1.0],
            'entry',
            0.0,
        )
        states.extend(entry)
        outward_states, cumulative = self._path(
            outward,
            profile,
            'outward',
            cumulative,
        )
        states.extend(outward_states)
        target_direction = outward_states[-1]['direction'] if outward_states else entry_direction
        states.extend(self._hold(target_uv, target_direction, cumulative))
        return_states, cumulative = self._path(
            returning,
            profile,
            'return',
            cumulative,
        )
        states.extend(return_states)
        exit_states, cumulative = self._transition(
            start_uv,
            outside_uv,
            exit_direction,
            [1.0, 0.75, 0.5, 0.25],
            'exit',
            cumulative,
        )
        states.extend(exit_states)

        moving = [state for state in states if state['phase'] in {'outward', 'return'}]
        raw_changes = sum(
            current['raw_direction'] != previous['raw_direction']
            for previous, current in zip(moving, moving[1:])
        )
        visual_changes = sum(
            current['direction'] != previous['direction']
            for previous, current in zip(moving, moving[1:])
        )
        return {
            'query': query,
            'character_id': profile['character_id'],
            'profile': profile,
            'start_uv': start_uv,
            'outside_uv': outside_uv,
            'target_uv': target_uv,
            'path_cells_uv': outward,
            'states': states,
            'route_cell_count': len(outward),
            'raw_direction_changes': raw_changes,
            'visual_direction_changes': visual_changes,
        }

    @staticmethod
    def _phase_label(agent: dict[str, Any], frame_index: int) -> str:
        if frame_index >= len(agent['states']):
            return 'done'
        phase = agent['states'][frame_index]['phase']
        if phase in {'outward', 'return'}:
            return 'walking'
        return phase

    def _sidebar(self, frame_index: int, total_frames: int, agents: list[dict[str, Any]]) -> Image.Image:
        panel = Image.new('RGBA', (self.SIDEBAR_WIDTH, 600), (12, 20, 32, 255))
        draw = ImageDraw.Draw(panel)
        draw.text((14, 14), 'F2 MOVEMENT PROFILE', fill=(240, 246, 255, 255))
        draw.text((14, 34), 'stable random 225-250%', fill=(151, 177, 207, 255))
        draw.text((14, 54), 'shared tick: 60 ms', fill=(151, 177, 207, 255))
        draw.text((14, 74), f'frame {frame_index + 1}/{total_frames}', fill=(151, 177, 207, 255))
        y = 112
        for index, agent in enumerate(agents):
            color = self.COLORS[index % len(self.COLORS)]
            draw.rectangle((14, y + 2, 23, y + 11), fill=color + (255,))
            draw.text(
                (31, y),
                f"{agent['character_id']}  {agent['profile']['speed_percent']}%",
                fill=(240, 246, 255, 255),
            )
            draw.text(
                (31, y + 17),
                self._phase_label(agent, frame_index),
                fill=(151, 177, 207, 255),
            )
            y += 48
        draw.text((14, 516), 'Stride scales with speed', fill=(151, 177, 207, 255))
        draw.text((14, 536), 'Facing uses path lookahead', fill=(151, 177, 207, 255))
        draw.text((14, 566), 'GDS runtime QA', fill=(94, 220, 170, 255))
        return panel

    def _render_frame(
        self,
        frame_index: int,
        total_frames: int,
        agents: list[dict[str, Any]],
    ) -> Image.Image:
        actors = []
        for agent in agents:
            if frame_index >= len(agent['states']):
                continue
            state = agent['states'][frame_index]
            if state['action'] == 'move':
                sprite_index = self.renderer.move_sprite_index(
                    agent['query'],
                    state['direction'],
                    state['cumulative_distance_px'],
                    agent['profile'],
                )
            else:
                sprite_index = int(state.get('idle_frame_index', 0))
            sprite = self.renderer.sprite(
                agent['query'],
                state['action'],
                state['direction'],
                sprite_index,
            )
            sprite = self.renderer.with_alpha(sprite, state['alpha'])
            actors.append({
                'sprite': sprite,
                'ground_xy': tuple(state['ground_xy']),
                'ground_anchor_px': tuple(self.movement.GROUND_ANCHOR_PX),
            })
        floor = self.renderer.depth.composite_characters(self.FLOOR_ID, actors).convert('RGBA')
        canvas = Image.new(
            'RGBA',
            (floor.width + self.SIDEBAR_WIDTH, floor.height),
            (12, 20, 32, 255),
        )
        canvas.alpha_composite(floor, (0, 0))
        canvas.alpha_composite(self._sidebar(frame_index, total_frames, agents), (floor.width, 0))
        return canvas

    def _route_overlay(self, agents: list[dict[str, Any]]) -> Image.Image:
        overlay = self.core.render_floor(self.FLOOR_ID).convert('RGBA')
        draw = ImageDraw.Draw(overlay, 'RGBA')
        for index, agent in enumerate(agents):
            color = self.COLORS[index % len(self.COLORS)]
            points = [self.renderer.uvxy(cell) for cell in agent['path_cells_uv']]
            draw.line(points, fill=color + (210,), width=2)
            sx, sy = self.renderer.uvxy(agent['start_uv'])
            tx, ty = self.renderer.uvxy(agent['target_uv'])
            draw.ellipse((sx - 3, sy - 3, sx + 3, sy + 3), fill=(255, 255, 255, 255))
            draw.ellipse((tx - 4, ty - 4, tx + 4, ty + 4), fill=color + (255,))
        return overlay

    def generate(self, output_root: str | Path) -> dict[str, Any]:
        output_root = Path(output_root).resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        starts = self.renderer.portal_starts(self.FLOOR_ID, self.AGENT_COUNT)
        agents = [self._agent(query, start) for query, start in enumerate(starts)]
        total_frames = max(len(agent['states']) for agent in agents) + self.EMPTY_TAIL_TICKS

        palette_reference: Image.Image | None = None
        frames: list[Image.Image] = []
        midpoint: Image.Image | None = None
        midpoint_index = total_frames // 2
        for frame_index in range(total_frames):
            frame = self._render_frame(frame_index, total_frames, agents)
            if frame_index == midpoint_index:
                midpoint = frame.copy()
            if palette_reference is None:
                paletted = frame.convert('P', palette=Image.Palette.ADAPTIVE, colors=256)
                palette_reference = paletted
            else:
                paletted = frame.convert('RGB').quantize(
                    palette=palette_reference,
                    dither=Image.Dither.NONE,
                )
            frames.append(paletted)

        gif_path = output_root / 'floor02_random_speed_225_250.gif'
        frames[0].save(
            gif_path,
            save_all=True,
            append_images=frames[1:],
            duration=self.renderer.FRAME_MS,
            loop=0,
            disposal=2,
        )
        midpoint_path = output_root / 'floor02_random_speed_midpoint.png'
        if midpoint is not None:
            midpoint.save(midpoint_path)
        overlay_path = output_root / 'floor02_random_speed_routes.png'
        self._route_overlay(agents).save(overlay_path)

        agent_rows = [{
            'character_id': agent['character_id'],
            'speed_percent': agent['profile']['speed_percent'],
            'speed_multiplier': agent['profile']['speed_multiplier'],
            'walk_frame_distance_cells': agent['profile']['walk_frame_distance_cells'],
            'start_uv': list(agent['start_uv']),
            'target_uv': list(agent['target_uv']),
            'route_cell_count': agent['route_cell_count'],
            'state_count': len(agent['states']),
            'raw_direction_changes': agent['raw_direction_changes'],
            'visual_direction_changes': agent['visual_direction_changes'],
        } for agent in agents]
        status = 'PASS'
        if not all(225 <= row['speed_percent'] <= 250 for row in agent_rows):
            status = 'FAIL'
        if not all(row['visual_direction_changes'] <= row['raw_direction_changes'] for row in agent_rows):
            status = 'FAIL'
        report = {
            'schema': 'gds_floor02_movement_profile_qa_v3',
            'status': status,
            'floor_id': self.FLOOR_ID,
            'frame_ms': self.renderer.FRAME_MS,
            'frame_count': total_frames,
            'duration_ms': total_frames * self.renderer.FRAME_MS,
            'speed_range_percent': [225, 250],
            'assignment_policy': 'stable_sha256_per_character',
            'route_distance_cells': self.ROUTE_DISTANCE_CELLS,
            'agents': agent_rows,
            'gif': str(gif_path),
            'midpoint_png': str(midpoint_path),
            'routes_png': str(overlay_path),
            'generated_artifact_policy': 'project_local_review_only_not_canonical_release_payload',
        }
        report_path = output_root / 'floor02_random_speed_report.json'
        report['report_json'] = str(report_path)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8',
        )
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Render the F2 stable random 225-250% movement profile QA.',
    )
    parser.add_argument(
        '--output',
        default=str(PROJECT_ROOT / 'LOCAL_REVIEW' / 'F2_WALK_SPEED_V2'),
        help='Output directory; defaults to the project-local review folder.',
    )
    args = parser.parse_args(argv)
    result = Floor02SpeedProfileQA(PROJECT_ROOT).generate(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
