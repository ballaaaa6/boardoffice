from pathlib import Path

from PIL import Image

from WORLD.RUNTIME.walking_depth_core import WalkingDepthCore

ROOT = Path(__file__).resolve().parents[1]


def _outside_bbox_changed(base, rendered, bbox):
    x0, y0, x1, y1 = bbox
    changed = 0
    for y in range(base.height):
        for x in range(base.width):
            if x0 <= x < x1 and y0 <= y < y1:
                continue
            if base.getpixel((x, y)) != rendered.getpixel((x, y)):
                changed += 1
    return changed


def test_no_redraw_keeps_static_world_pixels_exact_outside_actor_bbox():
    depth = WalkingDepthCore(ROOT / 'WORLD')
    desk = {r['placement_id']: r for r in depth.resolve_occluders('floor02')}['ws1_desk']
    placement = desk['placement']
    human = Image.new('RGBA', (32, 42), (255, 0, 255, 255))
    anchor = (16, 31)
    ground_xy = (int(placement['x_px']) + 24, desk['depth_anchor_y_px'] - 1)
    base = depth.floor_renderer.render('floor02').convert('RGBA')
    rendered = depth.composite_character('floor02', human, ground_xy, ground_anchor_px=anchor)
    bbox = depth._actor_bbox(human, ground_xy, anchor)
    assert _outside_bbox_changed(base, rendered, bbox) == 0


def test_transparent_actor_is_byte_exact_floor_even_when_behind_furniture():
    depth = WalkingDepthCore(ROOT / 'WORLD')
    desk = {r['placement_id']: r for r in depth.resolve_occluders('floor02')}['ws1_desk']
    human = Image.new('RGBA', (32, 42), (0, 0, 0, 0))
    ground_xy = (300, desk['depth_anchor_y_px'] - 1)
    base = depth.floor_renderer.render('floor02').convert('RGBA')
    rendered = depth.composite_character('floor02', human, ground_xy, ground_anchor_px=(16, 31))
    assert rendered.tobytes() == base.tobytes()


def test_single_actor_and_crowd_api_one_actor_match_exactly():
    depth = WalkingDepthCore(ROOT / 'WORLD')
    human = Image.new('RGBA', (32, 42), (255, 0, 255, 255))
    ground_xy = (300, 350)
    single = depth.composite_character('floor02', human, ground_xy, ground_anchor_px=(16, 31))
    crowd = depth.composite_characters('floor02', [{
        'sprite': human,
        'ground_xy': ground_xy,
        'ground_anchor_px': (16, 31),
    }])
    assert crowd.tobytes() == single.tobytes()


def test_crowd_no_redraw_keeps_static_world_exact_outside_actor_union():
    depth = WalkingDepthCore(ROOT / 'WORLD')
    human_a = Image.new('RGBA', (32, 42), (255, 0, 255, 255))
    human_b = Image.new('RGBA', (32, 42), (0, 255, 255, 255))
    actors = [
        {'sprite': human_a, 'ground_xy': (300, 330), 'ground_anchor_px': (16, 31)},
        {'sprite': human_b, 'ground_xy': (360, 370), 'ground_anchor_px': (16, 31)},
    ]
    base = depth.floor_renderer.render('floor02').convert('RGBA')
    rendered = depth.composite_characters('floor02', actors)
    bboxes = [depth._actor_bbox(a['sprite'], a['ground_xy'], a['ground_anchor_px']) for a in actors]
    changed = 0
    for y in range(base.height):
        for x in range(base.width):
            if any(x0 <= x < x1 and y0 <= y < y1 for x0, y0, x1, y1 in bboxes):
                continue
            if base.getpixel((x, y)) != rendered.getpixel((x, y)):
                changed += 1
    assert changed == 0
