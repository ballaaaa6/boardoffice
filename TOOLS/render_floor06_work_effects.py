from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from RUNTIME.central_core import CentralGameCore


def build_global_palette(frames: list[Image.Image]) -> list[int]:
    if not frames:
        raise ValueError('frames required')
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
    out = ROOT / 'PREVIEW' / 'work_effects' / 'floor06'
    out.mkdir(parents=True, exist_ok=True)

    workstations = ['ceo', 'ws1', 'ws2', 'ws3', 'ws4', 'ws5', 'ws6', 'ws7', 'ws8']
    character_queries = [0, 1, 2, 3, 4, 5, 6, 7, 8]
    seed = 606406
    rng = random.Random(seed)
    effect_ids = rng.sample(core.characters.list_effects(), k=len(workstations))

    base_assignments = []
    report = {
        'schema': 'gds.floor06_work_effects_acceptance.v1',
        'floor_id': 'floor06',
        'source_core_version': '1.4.2',
        'artwork_policy': 'project_assets_only_no_generative_image',
        'random_seed': seed,
        'assignments': [],
        'frame_count': 0,
        'frame_duration_ms': 140,
        'outputs': {},
        'visual_approval': 'pending_author_review',
        'notes': [
            'Effect is inserted as underlay before authored chair layer.',
            'GIF export uses one global palette across all frames to avoid static-floor flicker.',
        ],
    }

    for ws, q, effect_id in zip(workstations, character_queries, effect_ids):
        seat = core.resolve_work_seat('floor06', ws)
        char = core.resolve_character(q)
        base_assignments.append({'workstation_id': ws, 'character': q, 'subaction': 'normal_work', 'effect_id': effect_id})
        report['assignments'].append({
            'workstation_id': ws,
            'character_no': q,
            'character_code': char['character_code'],
            'character_id': char['character_id'],
            'full_name': char['full_name'],
            'direction': seat['direction'],
            'chair_family_id': seat['chair_family_id'],
            'chair_asset_id': seat['chair_asset_id'],
            'effect_id': effect_id,
        })

    frame_count = 1
    frame_ms = 140
    for a in base_assignments:
        seat = core.resolve_work_seat('floor06', a['workstation_id'])
        human = core.render_character(a['character'], 'work', seat['direction'], 'normal_work')
        effect = core.characters.render_effect(a['effect_id'], seat['direction'])
        frame_count = max(frame_count, len(human.frames), len(effect.frames))
        frame_ms = effect.frame_ms
    report['frame_count'] = frame_count
    report['frame_duration_ms'] = frame_ms

    frames = [core.render_floor_with_work_effects('floor06', base_assignments, frame_index=i) for i in range(frame_count)]
    for idx, frame in enumerate(frames):
        frame.save(out / f'frame_{idx:02d}.png')

    palette = build_global_palette(frames)
    pal_frames = [to_palette(f, palette) for f in (frames if len(frames) > 1 else [frames[0], frames[0].copy()])]
    gif_path = out / 'floor06_random_work_effects.gif'
    pal_frames[0].save(
        gif_path,
        save_all=True,
        append_images=pal_frames[1:],
        duration=[frame_ms] * len(pal_frames),
        loop=0,
        disposal=2,
        transparency=255,
    )

    preview_count = min(4, len(frames))
    preview = Image.new('RGBA', (600 * preview_count, 622), (210, 220, 240, 255))
    draw = ImageDraw.Draw(preview)
    for idx in range(preview_count):
        preview.alpha_composite(frames[idx], (idx * 600, 22))
        draw.text((idx * 600 + 8, 4), f'frame {idx:02d}', fill=(0, 0, 0, 255))
    preview_path = out / 'floor06_random_work_effects_preview.png'
    preview.save(preview_path)

    assign_path = out / 'effect_assignments.png'
    assign = Image.new('RGBA', (980, 28 + 18 * (len(report['assignments']) + 1)), (255, 255, 255, 255))
    draw = ImageDraw.Draw(assign)
    draw.text((10, 6), 'Floor06 random work effects assignments', fill=(0, 0, 0, 255))
    for idx, item in enumerate(report['assignments']):
        y = 28 + idx * 18
        draw.text((10, y), f"{item['workstation_id']:>3}  {item['character_code']}  {item['direction']:>2}  effect={item['effect_id']}", fill=(0, 0, 0, 255))
    assign.save(assign_path)

    report['outputs'] = {
        'gif': gif_path.relative_to(ROOT).as_posix(),
        'preview': preview_path.relative_to(ROOT).as_posix(),
        'assignments': assign_path.relative_to(ROOT).as_posix(),
        'frames': [f'PREVIEW/work_effects/floor06/frame_{i:02d}.png' for i in range(frame_count)],
    }

    report_path = ROOT / 'REPORTS' / 'FLOOR06_WORK_EFFECTS_ACCEPTANCE.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
