from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from RUNTIME.central_core import CentralGameCore
from TOOLS.render_floor06_work_effects import build_global_palette, to_palette


def build_review_assignments(core: CentralGameCore) -> tuple[list[dict], list[dict]]:
    workstations = ['ceo', 'ws1', 'ws2', 'ws3', 'ws4', 'ws5', 'ws6', 'ws7', 'ws8']
    humanballs = core.characters.list_humanballs()
    primary = [
        {
            'workstation_id': ws,
            'character': idx,
            'subaction': 'normal_work',
            'humanball_id': humanballs[idx % len(humanballs)],
        }
        for idx, ws in enumerate(workstations)
    ]
    combined = [
        {
            'workstation_id': 'ceo',
            'character': 0,
            'subaction': 'normal_work',
            'effect_id': 'fire_original',
            'humanball_id': 'controller',
        },
        {
            'workstation_id': 'ws1',
            'character': 1,
            'subaction': 'normal_work',
            'effect_id': 'coffee_energy',
            'humanball_id': 'coin',
        },
        {
            'workstation_id': 'ws3',
            'character': 2,
            'subaction': 'normal_work',
            'effect_id': 'thunder_cloud',
            'humanball_id': 'horse',
        },
    ]
    return primary, combined


def save_global_palette_gif(frames: list[Image.Image], out_path: Path, *, frame_ms: int = 240) -> None:
    palette = build_global_palette(frames)
    source = frames if len(frames) > 1 else [frames[0], frames[0].copy()]
    pal_frames = [to_palette(frame, palette) for frame in source]
    pal_frames[0].save(
        out_path,
        save_all=True,
        append_images=pal_frames[1:],
        duration=[frame_ms] * len(pal_frames),
        loop=0,
        disposal=2,
        transparency=255,
    )


def make_strip(frames: list[Image.Image], out_path: Path, indices: tuple[int, ...]) -> None:
    selected = [frames[i] for i in indices]
    canvas = Image.new('RGBA', (600 * len(selected), 622), (210, 220, 240, 255))
    draw = ImageDraw.Draw(canvas)
    for col, (frame_index, frame) in enumerate(zip(indices, selected)):
        canvas.alpha_composite(frame.convert('RGBA'), (col * 600, 22))
        draw.text((col * 600 + 8, 4), f'frame {frame_index:02d}', fill=(0, 0, 0, 255))
    canvas.save(out_path)


def describe_assignments(core: CentralGameCore, assignments: list[dict]) -> list[dict]:
    rows = []
    for item in assignments:
        seat = core.resolve_work_seat('floor06', item['workstation_id'])
        char = core.resolve_character(item['character'])
        rows.append({
            'workstation_id': item['workstation_id'],
            'direction': seat['direction'],
            'character_no': item['character'],
            'character_id': char['character_id'],
            'character_code': char['character_code'],
            'humanball_id': item['humanball_id'],
            'effect_id': item.get('effect_id'),
        })
    return rows


def main() -> int:
    core = CentralGameCore(ROOT)
    primary, combined = build_review_assignments(core)
    out = ROOT / 'PREVIEW' / 'humanball' / 'floor06'
    out.mkdir(parents=True, exist_ok=True)

    frame_count = 12
    frame_ms = core.work_seat_lifecycle.humanball_frame_ms
    primary_frames = [
        core.render_floor_with_work_effects('floor06', primary, frame_index=i)
        for i in range(frame_count)
    ]
    combined_frames = [
        core.render_floor_with_work_effects('floor06', combined, frame_index=i)
        for i in range(frame_count)
    ]

    primary_dir = out / 'humanball_only_frames'
    combined_dir = out / 'vfx_plus_humanball_frames'
    primary_dir.mkdir(exist_ok=True)
    combined_dir.mkdir(exist_ok=True)
    for idx, frame in enumerate(primary_frames):
        frame.save(primary_dir / f'frame_{idx:02d}.png')
    for idx, frame in enumerate(combined_frames):
        frame.save(combined_dir / f'frame_{idx:02d}.png')

    primary_gif = out / 'floor06_humanball_only.gif'
    combined_gif = out / 'floor06_vfx_plus_humanball.gif'
    save_global_palette_gif(primary_frames, primary_gif, frame_ms=frame_ms)
    save_global_palette_gif(combined_frames, combined_gif, frame_ms=frame_ms)

    primary_strip = out / 'floor06_humanball_motion_review.png'
    combined_strip = out / 'floor06_vfx_plus_humanball_review.png'
    make_strip(primary_frames, primary_strip, (0, 3, 6, 9, 10))
    make_strip(combined_frames, combined_strip, (0, 3, 6, 9, 10))

    report = {
        'schema': 'gds.floor06_humanball_review.v1',
        'floor_id': 'floor06',
        'source_core_version': '1.6.1',
        'candidate_feature': 'humanball_popup_channel',
        'artwork_policy': 'project_assets_only_no_generative_image',
        'visual_approval': 'author_requested_merge_2026_08_30',
        'frame_count': frame_count,
        'frame_duration_ms': frame_ms,
        'humanball_contract': {
            'channel': 'work_popup_overlay',
            'cell_px': [18, 18],
            'visible_frames': 10,
            'hidden_frames': 2,
            'directions': ['NW', 'SE', 'SW'],
            'sw_policy': 'derive relation from SE; do not mirror authored furniture or HumanBall art',
        },
        'primary_assignments': describe_assignments(core, primary),
        'combined_assignments': describe_assignments(core, combined),
        'outputs': {
            'humanball_only_gif': primary_gif.relative_to(ROOT).as_posix(),
            'humanball_only_review': primary_strip.relative_to(ROOT).as_posix(),
            'vfx_plus_humanball_gif': combined_gif.relative_to(ROOT).as_posix(),
            'vfx_plus_humanball_review': combined_strip.relative_to(ROOT).as_posix(),
            'humanball_only_frames': [
                (primary_dir / f'frame_{i:02d}.png').relative_to(ROOT).as_posix()
                for i in range(frame_count)
            ],
            'vfx_plus_humanball_frames': [
                (combined_dir / f'frame_{i:02d}.png').relative_to(ROOT).as_posix()
                for i in range(frame_count)
            ],
        },
        'notes': [
            'HumanBall is composited after completed work-scene static/human/foreground events.',
            'Existing Work VFX remains an underlay before authored chair/workstation geometry.',
            'Frames 10 and 11 intentionally contain no HumanBall popup.',
            'GIFs use one global palette per complete animation.',
        ],
    }
    report_path = ROOT / 'REPORTS' / 'FLOOR06_HUMANBALL_REVIEW.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
