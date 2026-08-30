from pathlib import Path

from TOOLS.render_ceo_desk_depth_qa import CeoDeskDepthRenderer, choose_floors


ROOT = Path(__file__).resolve().parents[1]


def test_ceo_qa_uses_required_and_deterministic_random_floors():
    renderer = CeoDeskDepthRenderer(ROOT)
    floors, extras = choose_floors(renderer, renderer.SEED)

    assert floors[:3] == ['floor00', 'floor01', 'floor02']
    assert extras == ['floor14', 'floor17']
    assert len(floors) == 5


def test_ceo_qa_targets_are_reachable_and_inside_the_front_envelope():
    renderer = CeoDeskDepthRenderer(ROOT)
    for floor_id in ['floor00', 'floor01', 'floor02', 'floor14', 'floor17']:
        targets = renderer.distributed_targets(floor_id, renderer.AGENT_COUNT)
        metadata = renderer._target_metadata[floor_id]

        assert len(targets) == renderer.AGENT_COUNT
        assert len(metadata) == renderer.AGENT_COUNT
        assert all(row['target_role'] == 'ceo_front_envelope' for row in metadata)
        assert all(
            renderer.core.navigation_occupancy.is_walkable(floor_id, *target)
            for target in targets
        )
        assert all(4.0 <= row['front_margin'] <= 24.0 for row in metadata)
        assert all(row['ground_xy'][1] < row['scalar_anchor_y'] for row in metadata)
