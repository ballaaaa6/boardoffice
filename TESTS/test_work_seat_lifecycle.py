from __future__ import annotations

from pathlib import Path

import pytest

from RUNTIME.central_core import CentralGameCore, CentralGameCoreError


ROOT = Path(__file__).resolve().parents[1]


def _assert_four_neighbor_path(core: CentralGameCore, floor_id: str, path: list[list[int]]):
    for cell in path:
        assert core.is_walkable_cell(floor_id, *cell)
    for a, b in zip(path, path[1:]):
        assert abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1


def test_single_actor_cycle_keeps_actor_slot_and_render_tracks_in_lockstep():
    core = CentralGameCore(ROOT)
    start = tuple(core.resolve_portal_navigation_start("floor02"))
    cycle = core.resolve_work_seat_actor_cycle(
        0, "floor02", "ceo", start, work_ticks=24, effect_id="thunder_cloud", humanball_id="coin"
    )
    assert cycle["schema"] == "gds.work_seat_actor_cycle.v1"
    assert cycle["completed"] is True
    assert cycle["slot_transition_history"] == ["free", "reserved", "occupied", "releasing", "free"]
    assert cycle["final_slot_state"] == "free"
    assert cycle["final_state"]["current_uv"] == list(start)
    assert cycle["timing"]["work_duration_ms"] == 1440
    _assert_four_neighbor_path(core, "floor02", cycle["inbound_path_cells_uv"])
    _assert_four_neighbor_path(core, "floor02", cycle["outbound_path_cells_uv"])
    gate = cycle["slot"]["transition_gate_uv"]
    assert cycle["inbound_path_cells_uv"][-1] == gate
    assert cycle["outbound_path_cells_uv"][0] == gate

    phases = [state["phase"] for state in cycle["states"]]
    assert phases == sorted(phases, key=lambda phase: {
        "walking_to_seat": 0,
        "approach": 1,
        "seated_work": 2,
        "exit_seat": 3,
        "walking_from_seat": 4,
    }[phase])
    assert cycle["phase_counts"]["seated_work"] == 24
    assert all(
        not (state["walking_visible"] and state["seated_visible"])
        for state in cycle["states"]
    )
    seated = [state for state in cycle["states"] if state["phase"] == "seated_work"]
    assert all(state["render_owner"] == "work_seat" for state in seated)
    assert all(state["current_uv"] is None for state in seated)
    assert all(state["work_render"]["effect_id"] == "thunder_cloud" for state in seated)
    assert all(state["work_render"]["humanball_id"] == "coin" for state in seated)
    assert len({state["work_render"]["character_frame_index"] for state in seated}) >= 2
    assert len({state["work_render"]["effect_frame_index"] for state in seated}) >= 2
    assert len({state["work_render"]["humanball_frame_index"] for state in seated}) >= 2

    timestamps = [state["timestamp_ms"] for state in cycle["states"]]
    assert timestamps == sorted(timestamps)
    assert all(b > a and (b - a) % 60 == 0 for a, b in zip(timestamps, timestamps[1:]))
    assert cycle["slot_transition_events"][0]["timestamp_ms"] == 0
    assert cycle["slot_transition_events"][-1]["phase"] == "walking_from_seat"


def test_cycle_is_deterministic_across_character_aliases_and_actor_seed_is_ignored():
    core = CentralGameCore(ROOT)
    start = tuple(core.resolve_portal_navigation_start("floor00"))
    first = core.resolve_work_seat_actor_cycle(0, "floor00", "ws3", start, work_ticks=2)
    second = core.resolve_work_seat_actor_cycle("TP_000", "floor00", "ws3", start, work_ticks=2)
    assert first == second
    assert core.resolve_character_movement_profile(0, actor_seed="instance-a") == core.resolve_character_movement_profile(
        0, actor_seed="instance-b"
    )


@pytest.mark.parametrize(
    "args",
    [
        (0, "floor00", "does-not-exist", (284, 152)),
        (0, "floor00", "ceo", (0, 0)),
    ],
)
def test_cycle_rejects_unknown_workstation_and_non_walkable_start(args):
    core = CentralGameCore(ROOT)
    with pytest.raises(CentralGameCoreError):
        core.resolve_work_seat_actor_cycle(*args, work_ticks=1)


def test_cycle_rejects_invalid_work_duration_subaction_and_overlay_pairing():
    core = CentralGameCore(ROOT)
    start = tuple(core.resolve_portal_navigation_start("floor00"))
    with pytest.raises(CentralGameCoreError):
        core.resolve_work_seat_actor_cycle(0, "floor00", "ceo", start, work_ticks=0)
    with pytest.raises(CentralGameCoreError):
        core.resolve_work_seat_actor_cycle(0, "floor00", "ceo", start, work_ticks=1, subaction="not-real")
    with pytest.raises(CentralGameCoreError):
        core.resolve_work_seat_actor_cycle(
            0, "floor00", "ceo", start, work_ticks=1, subaction="happy", effect_id="fire_original"
        )
