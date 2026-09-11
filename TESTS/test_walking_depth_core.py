from pathlib import Path

from PIL import Image

from WORLD.RUNTIME.walking_depth_core import WalkingDepthCore


ROOT = Path(__file__).resolve().parents[1]


def _by_id(rows):
    return {row['placement_id']: row for row in rows}


def test_depth_resolver_derives_footprint_depth_and_visual_inheritance():
    depth = WalkingDepthCore(ROOT / 'WORLD')
    rows = _by_id(depth.resolve_occluders('floor00'))

    desk = rows['ws3_desk']
    pc = rows['ws3_pc']
    chair = rows['ws3_chair_main']
    chair_sub = rows['ws3_chair_sub']

    assert desk['depth_mode'] == 'ground_footprint'
    assert desk['depth_anchor_y_px'] == max(y for _, y in desk['footprint_corners_world_px'])

    assert pc['depth_mode'] == 'inherit_workstation_desk'
    assert pc['depth_anchor_y_px'] == desk['depth_anchor_y_px']
    assert pc['depth_source_placement_id'] == desk['placement_id']

    assert chair['depth_mode'] == 'ground_footprint'
    assert chair_sub['depth_mode'] == 'inherit_workstation_chair'
    assert chair_sub['depth_anchor_y_px'] == chair['depth_anchor_y_px']
    assert chair_sub['depth_source_placement_id'] == chair['placement_id']
    assert chair_sub['foreground_fragment'] is True


def test_reception_uses_independent_front_envelope_and_overlay_is_always_foreground():
    depth = WalkingDepthCore(ROOT / 'WORLD')
    rows = _by_id(depth.resolve_occluders('floor01'))

    reception = rows['reception']
    overlay = rows['foreground_overlay_00']

    assert reception['depth_mode'] == 'ground_front_envelope'
    assert reception['depth_profile_id'] == 'walking_depth.reception.f1'
    assert reception['depth_anchor_y_px'] == 395
    assert reception['depth_anchor_y_px'] != max(y for _, y in reception['footprint_corners_world_px'])
    assert overlay['depth_mode'] == 'always_foreground'
    assert overlay['always_foreground'] is True


def test_occluder_selection_uses_character_ground_depth_not_static_layer():
    depth = WalkingDepthCore(ROOT / 'WORLD')
    rows = _by_id(depth.resolve_occluders('floor00'))
    desk = rows['ws3_desk']
    desk_y = desk['depth_anchor_y_px']

    behind_ids = {row['placement_id'] for row in depth.occluders_in_front('floor00', desk_y - 1)}
    front_ids = {row['placement_id'] for row in depth.occluders_in_front('floor00', desk_y + 1)}

    assert 'ws3_desk' in behind_ids
    assert 'ws3_pc' in behind_ids
    assert 'ws3_desk' not in front_ids
    assert 'ws3_pc' not in front_ids


def test_talk_hold_filters_nw_desk_and_pc_but_keeps_se_and_chairs():
    depth = WalkingDepthCore(ROOT / 'WORLD')
    ground = (360, 367)
    normal_ids = [
        row['placement_id']
        for row in depth.occluders_for_render('floor02', ground)
    ]
    hold_ids_by_mode = {
        mode: [
            row['placement_id']
            for row in depth.occluders_for_render(
                'floor02',
                ground,
                speech_mode=mode,
                route_phase='talk_hold',
            )
        ]
        for mode in ('standing_pair', 'seated_host', 'ceo_front')
    }

    assert 'ws8_desk' in normal_ids
    assert 'ws8_pc' in normal_ids
    assert 'ws6_desk' in normal_ids
    assert 'ws6_pc' in normal_ids
    assert 'ws8_chair_main' in normal_ids
    for hold_ids in hold_ids_by_mode.values():
        assert 'ws8_desk' not in hold_ids
        assert 'ws8_pc' not in hold_ids
        assert 'ws6_desk' in hold_ids
        assert 'ws6_pc' in hold_ids
        assert 'ws8_chair_main' in hold_ids
        if 'ws8_chair_sub' in normal_ids:
            assert 'ws8_chair_sub' in hold_ids
        assert 'reception' in hold_ids
        assert {'foreground_overlay_00', 'foreground_overlay_01', 'foreground_overlay_02'} <= set(hold_ids)

    for speech_mode, route_phase in (
        ('standing_pair', 'talk_outbound'),
        ('standing_pair', 'talk_return'),
        (None, None),
    ):
        assert [
            row['placement_id']
            for row in depth.occluders_for_render(
                'floor02',
                ground,
                speech_mode=speech_mode,
                route_phase=route_phase,
            )
        ] == normal_ids


def test_talk_hold_preserves_actor_pixels_over_nw_desk_and_pc_masks():
    depth = WalkingDepthCore(ROOT / 'WORLD')
    sprite = Image.new('RGBA', (32, 42), (255, 0, 255, 255))
    ground = (360, 367)

    normal = depth._mask_character_by_world_occluders(
        'floor02',
        sprite,
        ground,
        ground_anchor_px=(16, 31),
    )
    assert min(normal.getchannel('A').getdata()) == 0
    for mode in ('standing_pair', 'seated_host', 'ceo_front'):
        hold = depth._mask_character_by_world_occluders(
            'floor02',
            sprite,
            ground,
            ground_anchor_px=(16, 31),
            speech_mode=mode,
            route_phase='talk_hold',
        )
        assert hold.getchannel('A').getextrema()[0] == 0


def test_composite_character_redraws_selected_real_asset_occluders():
    depth = WalkingDepthCore(ROOT / 'WORLD')
    rows = _by_id(depth.resolve_occluders('floor00'))
    desk = rows['ws3_desk']
    placement = desk['placement']
    sprite = depth.layout.load_variant(placement['variant_id']).convert('RGBA')
    bbox = sprite.getbbox()
    assert bbox is not None

    # Use a fully opaque test human canvas at the desk visual center so any
    # selected desk redraw has guaranteed overlapping pixels.
    human = Image.new('RGBA', (32, 42), (255, 0, 255, 255))
    visual_center_x = int(placement['x_px']) + (bbox[0] + bbox[2]) // 2
    human_ground_y = desk['depth_anchor_y_px'] - 1
    anchor = (16, 31)

    naive = depth.floor_renderer.render('floor00').convert('RGBA')
    naive.alpha_composite(human, (visual_center_x - anchor[0], human_ground_y - anchor[1]))
    composed = depth.composite_character(
        'floor00',
        human,
        (visual_center_x, human_ground_y),
        ground_anchor_px=anchor,
    )

    assert composed.tobytes() != naive.tobytes()


def test_central_core_shares_navigation_state_with_walking_depth_runtime():
    from RUNTIME.central_core import CentralGameCore

    core = CentralGameCore(ROOT)
    assert core.walking_depth.occupancy is core.navigation_occupancy
    assert core.walking_depth.layout is core.world
    assert core.walking_depth.floor_renderer is core.floors


def test_occlusion_redraw_does_not_double_composite_ground_shadow_pixels():
    depth = WalkingDepthCore(ROOT / 'WORLD')
    rows = _by_id(depth.resolve_occluders('floor00'))
    desk = rows['ws3_desk']
    placement = desk['placement']
    sprite = depth.layout.load_variant(placement['variant_id']).convert('RGBA')

    # Ground shadows in the source furniture assets are semi-transparent black.
    shadow_local = None
    for y in range(sprite.height):
        for x in range(sprite.width):
            r, g, b, a = sprite.getpixel((x, y))
            if (r, g, b, a) == (0, 0, 0, 128):
                shadow_local = (x, y)
                break
        if shadow_local is not None:
            break
    assert shadow_local is not None

    wx = int(placement['x_px']) + shadow_local[0]
    wy = int(placement['y_px']) + shadow_local[1]
    base = depth.floor_renderer.render('floor00').convert('RGBA')

    # Transparent character still triggers the front-object redraw; the floor
    # shadow pixel must remain byte-identical rather than being darkened again.
    transparent_human = Image.new('RGBA', (32, 42), (0, 0, 0, 0))
    composed = depth.composite_character(
        'floor00',
        transparent_human,
        (wx, desk['depth_anchor_y_px'] - 1),
        ground_anchor_px=(16, 31),
    )
    assert composed.getpixel((wx, wy)) == base.getpixel((wx, wy))


def test_occluder_mask_preserves_dark_object_edges_and_source_alpha():
    depth = WalkingDepthCore(ROOT / 'WORLD')
    rows = _by_id(depth.resolve_occluders('floor02'))
    desk = rows['ws3_desk']
    source = depth.layout.load_variant(desk['variant_id']).convert('RGBA')
    mask = depth._load_occluder_visual(desk)

    # Dark pixels include the desk's intentional opaque outline.  They must
    # remain part of the walking mask; otherwise the actor is visible through
    # the object's border while passing behind it.
    dark_opaque = next(
        pixel
        for pixel in source.getdata()
        if pixel[3] == 255 and max(pixel[:3]) <= 64
    )
    assert dark_opaque[3] == 255
    assert mask.getchannel('A').tobytes() == source.getchannel('A').tobytes()
