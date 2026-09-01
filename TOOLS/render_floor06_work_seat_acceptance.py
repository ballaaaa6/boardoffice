from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from RUNTIME.central_core import CentralGameCore


def build_global_palette(frames: list[Image.Image]) -> list[int]:
    strip = Image.new('RGBA', (frames[0].width * len(frames), frames[0].height), (0, 0, 0, 0))
    for idx, frame in enumerate(frames):
        strip.alpha_composite(frame.convert('RGBA'), (idx * frame.width, 0))
    alpha = strip.getchannel('A')
    rgb = Image.new('RGB', strip.size, (0, 0, 0))
    rgb.paste(strip, mask=alpha)
    pal = rgb.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    palette = pal.getpalette() or []
    if len(palette) < 768:
        palette += [0] * (768 - len(palette))
    return palette[:768]


def to_palette(im: Image.Image, palette: list[int]) -> Image.Image:
    rgba = im.convert('RGBA')
    alpha = rgba.getchannel('A')
    rgb = Image.new('RGB', rgba.size, (0, 0, 0))
    rgb.paste(rgba, mask=alpha)
    palette_image = Image.new('P', (1, 1))
    palette_image.putpalette(palette)
    pal = rgb.quantize(colors=255, palette=palette_image, dither=Image.Dither.NONE)
    transparent_mask = alpha.point(lambda a: 255 if a == 0 else 0)
    pal.paste(255, mask=transparent_mask)
    pal.putpalette(palette)
    pal.info['transparency'] = 255
    return pal


def main() -> int:
    core = CentralGameCore(ROOT)
    timing = core.work_seat_lifecycle
    out = ROOT / 'PREVIEW' / 'work_seat' / 'floor06'
    out.mkdir(parents=True, exist_ok=True)

    workstations = ['ceo', 'ws1', 'ws2', 'ws3', 'ws4', 'ws5', 'ws6', 'ws7', 'ws8']
    character_queries = [0, 1, 2, 3, 4, 5, 6, 7, 8]
    base_assignments = [
        {'workstation_id': ws, 'character': q}
        for ws, q in zip(workstations, character_queries)
    ]
    subactions = ['normal_work', 'turn_side_sw', 'turn_side_ne', 'turn_side_se', 'turn_side_nw', 'happy']
    report = {
        'schema': 'gds.floor06_work_seat_acceptance.v1',
        'floor_id': 'floor06',
        'source_core_version': '1.4.1',
        'artwork_policy': 'project_assets_only_no_generative_image',
        'timing_policy': {
            'playback_tick_ms': timing.tick_ms,
            'character_frame_ms': timing.character_frame_ms,
            'effect_frame_ms': timing.effect_frame_ms,
            'humanball_frame_ms': timing.humanball_frame_ms,
            'pc_frame_loop_source': 'character_frame_ms multiplied by resolved_work_action_frame_count',
        },
        'assignments': [],
        'subactions': {},
        'visual_approval': 'pending_author_review',
    }

    for ws, q in zip(workstations, character_queries):
        char = core.resolve_character(q)
        seat = core.resolve_work_seat('floor06', ws)
        action = core.render_character(q, 'work', seat['direction'], 'normal_work')
        chair = core.world.load_asset(seat['chair_asset_id'])
        offset = core.work_seats.resolve_world_offset(
            seat['direction'], chair_size=chair.size, human_size=action.frames[0].size
        )
        report['assignments'].append({
            'workstation_id': ws,
            'character_no': q,
            'character_code': char['character_code'],
            'character_id': char['character_id'],
            'full_name': char['full_name'],
            'direction': seat['direction'],
            'chair_family_id': seat['chair_family_id'],
            'chair_asset_id': seat['chair_asset_id'],
            'visual_character_offset_from_chair_px': list(offset),
            'foreground_asset_id': seat['foreground_asset_id'],
            'foreground_static_present': seat['foreground_static_present'],
            'foreground_layer': seat['foreground_layer'],
        })

    for subaction in subactions:
        assignments = []
        resolved_subactions = {}
        for a in base_assignments:
            seat = core.resolve_work_seat('floor06', a['workstation_id'])
            supported = core.work_seats.TURN_SIDE_SUBACTIONS_BY_WORK_DIRECTION[seat['direction']]
            resolved = (
                subaction
                if subaction in {'normal_work', 'happy'} or subaction in supported
                else 'normal_work'
            )
            assignments.append({**a, 'subaction': resolved})
            resolved_subactions[a['workstation_id']] = resolved
        frame_counts = []
        for a in assignments:
            seat = core.resolve_work_seat('floor06', a['workstation_id'])
            r = core.render_character(a['character'], 'work', seat['direction'], a['subaction'])
            frame_counts.append(len(r.frames))
        frame_count = max(frame_counts)
        frames = [core.render_floor_with_work('floor06', assignments, frame_index=i) for i in range(frame_count)]
        png_path = out / f'{subaction}_frame00.png'
        frames[0].save(png_path)
        gif_path = out / f'{subaction}.gif'
        gif_frames = frames if len(frames) > 1 else [frames[0], frames[0].copy()]
        palette = build_global_palette(gif_frames)
        pframes = [to_palette(im, palette) for im in gif_frames]
        pframes[0].save(
            gif_path,
            save_all=True,
            append_images=pframes[1:],
            duration=[timing.character_frame_ms] * len(pframes),
            loop=0,
            disposal=2,
        )
        sheet = Image.new('RGBA', (600 * len(frames), 600), (0, 0, 0, 0))
        for i, frame in enumerate(frames):
            sheet.alpha_composite(frame, (600 * i, 0))
        sheet_path = out / f'{subaction}_sheet.png'
        sheet.save(sheet_path)
        report['subactions'][subaction] = {
            'frame_count': frame_count,
            'resolved_subactions': resolved_subactions,
            'png': png_path.relative_to(ROOT).as_posix(),
            'gif': gif_path.relative_to(ROOT).as_posix(),
            'sheet': sheet_path.relative_to(ROOT).as_posix(),
        }

    report_path = ROOT / 'REPORTS' / 'FLOOR06_WORK_SEAT_ACCEPTANCE.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
