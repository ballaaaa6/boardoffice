from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from RUNTIME.central_core import CentralGameCore, CentralGameCoreError
from TOOLS.render_conversation_pair_gif import ConversationPairGifRenderer


ROOT = Path(__file__).resolve().parents[1]


def floor_ids(core: CentralGameCore) -> list[str]:
    return sorted(core.world.floors, key=lambda value: int(value.removeprefix("floor")))


def floor_actor_ids(core: CentralGameCore, floor_id: str) -> list[str]:
    snapshot = core.resolve_conversation_snapshot(floor_id)
    return sorted(
        snapshot["actors"],
        key=lambda employee_id: (
            int(snapshot["actors"][employee_id]["assignment_order"]),
            employee_id,
        ),
    )


def test_conversation_contract_validates_and_freezes_author_policy():
    schema = json.loads(
        (ROOT / "SCHEMA" / "conversation_behavior.schema.json").read_text(encoding="utf-8")
    )
    contract = json.loads(
        (ROOT / "CONTRACTS" / "conversation_behavior.json").read_text(encoding="utf-8")
    )
    assert list(Draft202012Validator(schema).iter_errors(contract)) == []
    assert contract["policy"]["ceo_outbound_talk"] is False
    assert contract["coordinate_contract"]["standing_pair"]["preferred_axis"] == "V"
    assert contract["coordinate_contract"]["standing_pair"]["fallback_axis"] == "U"
    assert contract["coordinate_contract"]["standing_pair"]["endpoint_order"] == "ascending_v"
    assert contract["coordinate_contract"]["standing_pair"]["talk_gap_cells"] == 4
    assert contract["coordinate_contract"]["standing_pair"]["opener_bubble_extra_offset_px"] == [0, -20]
    assert contract["policy"]["dialogue_layout"] == "direct_head_anchor_overlay_paint_order"


def test_standing_pair_is_axis_aligned_inverse_facing_and_deterministic():
    core = CentralGameCore(ROOT)
    ids = floor_actor_ids(core, "floor02")
    employee_ids = [
        employee_id
        for employee_id in ids
        if core.resolve_conversation_snapshot("floor02")["actors"][employee_id]["role"] == "employee"
    ]
    snapshot = core.resolve_conversation_snapshot("floor02")
    first = core.resolve_conversation_plan(
        employee_ids[0],
        partner_id=employee_ids[1],
        mode="standing_pair",
        snapshot=snapshot,
        talk_frames=2,
    )
    second = core.resolve_conversation_plan(
        employee_ids[0],
        partner_id=employee_ids[1],
        mode="standing_pair",
        snapshot=snapshot,
        talk_frames=2,
    )
    assert first == second
    assert first["ready"] is True
    spot = first["spot"]
    a, b = [tuple(cell) for cell in spot["endpoint_uv"]]
    assert spot["axis"] == "V"
    assert a[0] == b[0]
    assert b[1] - a[1] == 4
    assert spot["endpoint_facings"] == ["SW", "NE"]
    assert spot["endpoint_inverse"] is True
    assert first["facing_by_actor"][employee_ids[0]] != first["facing_by_actor"][employee_ids[1]]
    lower_v = min(first["endpoint_by_actor"], key=lambda employee_id: tuple(first["endpoint_by_actor"][employee_id])[1])
    higher_v = max(first["endpoint_by_actor"], key=lambda employee_id: tuple(first["endpoint_by_actor"][employee_id])[1])
    assert first["facing_by_actor"] == {lower_v: "SW", higher_v: "NE"}
    assert first["locks"]["participant_lock"] == employee_ids[:2]
    assert first["snapshot_reserved"]["actors"][employee_ids[0]]["phase"] == "talk_pending"
    assert first["snapshot_after"]["actors"][employee_ids[0]]["workstation_id"] == snapshot["actors"][employee_ids[0]]["workstation_id"]
    assert first["snapshot_after"]["locks"] == {"participant_lock": [], "talk_slot_lock": []}


def test_ceo_is_host_only_and_front_plan_keeps_ceo_seated():
    core = CentralGameCore(ROOT)
    snapshot = core.resolve_conversation_snapshot("floor02")
    ceo_id = next(employee_id for employee_id, actor in snapshot["actors"].items() if actor["role"] == "ceo")
    employee_id = next(employee_id for employee_id, actor in snapshot["actors"].items() if actor["role"] == "employee")

    outbound = core.resolve_conversation_plan(
        ceo_id,
        partner_id=employee_id,
        mode="standing_pair",
        snapshot=snapshot,
    )
    assert outbound["ready"] is False
    assert outbound["reason"] == "ceo_outbound"

    plan = core.resolve_conversation_plan(
        employee_id,
        partner_id=ceo_id,
        mode="ceo_front",
        snapshot=snapshot,
        talk_frames=2,
    )
    assert plan["ready"] is True
    assert plan["mode"] == "ceo_front"
    assert plan["host_id"] == ceo_id
    assert plan["visitor_ids"] == [employee_id]
    assert plan["spot"]["host_movement"] == "none"
    assert plan["tracks"][ceo_id][-1]["render_owner"] == "work_seat"
    assert all(row["render_owner"] != "work_seat" for row in plan["tracks"][employee_id] if row["phase"] in {"walking_to_talk", "talk_arrival", "talking", "returning_to_work"})


def test_spot_resolver_covers_current_floors_without_mutating_assignments():
    core = CentralGameCore(ROOT)
    before = json.dumps(core.resolve_conversation_snapshot(), sort_keys=True)
    for floor_id in floor_ids(core):
        spot = core.resolve_conversation_spot("standing_pair", floor_id)
        assert spot["ready"] is True, floor_id
        endpoints = [tuple(cell) for cell in spot["endpoint_uv"]]
        assert all(core.navigation_occupancy.is_walkable(floor_id, *cell) for cell in endpoints)
        assert spot["endpoint_inverse"] is True
        front = core.resolve_conversation_spot("ceo_front", floor_id)
        assert front["ready"] is True, floor_id
        assert len(front["endpoint_uv"]) == 1
    after = json.dumps(core.resolve_conversation_snapshot(), sort_keys=True)
    assert before == after


def test_advance_and_cancel_release_locks_and_preserve_workstation_ownership():
    core = CentralGameCore(ROOT)
    snapshot = core.resolve_conversation_snapshot("floor02")
    ids = floor_actor_ids(core, "floor02")
    employees = [employee_id for employee_id in ids if snapshot["actors"][employee_id]["role"] == "employee"]
    plan = core.resolve_conversation_plan(
        employees[0],
        partner_id=employees[1],
        mode="standing_pair",
        snapshot=snapshot,
        talk_frames=1,
    )
    assert plan["ready"] is True
    reserved = plan["snapshot_reserved"]
    cancelled = core.cancel_conversation(reserved, plan, reason="qa_cancel")
    assert cancelled["cancelled"] is True
    assert cancelled["snapshot"]["locks"] == {"participant_lock": [], "talk_slot_lock": []}
    assert all(cancelled["snapshot"]["actors"][employee_id]["phase"] == "working" for employee_id in employees[:2])
    assert all(cancelled["snapshot"]["actors"][employee_id]["workstation_id"] == snapshot["actors"][employee_id]["workstation_id"] for employee_id in employees[:2])

    advanced = core.advance_conversation(reserved, plan, tick_ms=60)
    assert advanced["snapshot"]["clock_ms"] == 60
    assert advanced["complete"] is False
    core.validate_conversation_snapshot(advanced["snapshot"])


def test_timing_seam_is_deterministic_and_alternates_complete_pair_loops():
    core = CentralGameCore(ROOT)
    first = core.resolve_conversation_timing(
        mode="standing_pair",
        participant_ids=["EMP_W1_0031", "EMP_W1_0010"],
        initiator_id="EMP_W1_0031",
        timing={"talk_frames": 12, "loop_count": 2},
    )
    second = core.resolve_conversation_timing(
        mode="standing_pair",
        participant_ids=["EMP_W1_0031", "EMP_W1_0010"],
        initiator_id="EMP_W1_0031",
        timing={"talk_frames": 12, "loop_count": 2},
    )
    assert first == second
    assert first["talk_duration_ms"] == 720
    assert first["loop_count"] == 2
    assert first["turn_count"] == 4
    assert first["speaker_sequence"] == [
        "EMP_W1_0031", "EMP_W1_0010", "EMP_W1_0031", "EMP_W1_0010"
    ]
    assert [row["loop_index"] for row in first["segments"]] == [0, 0, 1, 1]
    assert first["segments"][0]["start_offset_ms"] == 0
    assert first["segments"][-1]["end_offset_ms"] == first["talk_duration_ms"]


def test_approved_default_timing_is_one_staggered_exchange_with_global_fade():
    core = CentralGameCore(ROOT)
    timing = core.resolve_conversation_timing(
        mode="standing_pair",
        participant_ids=["EMP_W1_0031", "EMP_W1_0010"],
        initiator_id="EMP_W1_0031",
    )
    assert timing["preview_only"] is False
    assert timing["loop_count"] == 1
    assert timing["speaker_cadence"] == "staggered_persistent"
    assert timing["bubble_visible_ms"] == 4000
    assert timing["speaker_gap_ms"] == 500
    assert timing["bubble_fade_ms"] == 300
    assert timing["talk_duration_ms"] == 4300
    assert timing["speaker_sequence"] == ["EMP_W1_0031", "EMP_W1_0010"]
    assert [row["start_offset_ms"] for row in timing["segments"]] == [0, 500]
    assert all(row["fade_start_offset_ms"] == 4000 for row in timing["segments"])
    assert all(row["fade_end_offset_ms"] == 4300 for row in timing["segments"])


def test_default_pair_keeps_both_lines_until_shared_fade_then_returns_to_work():
    core = CentralGameCore(ROOT)
    snapshot = core.resolve_conversation_snapshot("floor02")
    ids = floor_actor_ids(core, "floor02")
    employees = [employee_id for employee_id in ids if snapshot["actors"][employee_id]["role"] == "employee"]
    plan = core.resolve_conversation_plan(
        employees[0],
        partner_id=employees[1],
        mode="standing_pair",
        snapshot=snapshot,
        origin_uvs=[],
    )
    assert plan["talk_end_ms"] - plan["talk_start_ms"] == 4300
    assert plan["dialogue"]["selection_policy"] == "pair_open_then_reply"
    lines = plan["dialogue"]["speaker_lines"]
    assert len(lines) == 2
    assert lines[0]["category"] == "conversation_open"
    assert lines[1]["category"] == "conversation_reply"
    assert lines[0]["dialogue_id"] != lines[1]["dialogue_id"]
    offsets = plan["bubble_offset_by_actor"]
    assert len(offsets) == 2
    opener, reply = plan["timing"]["speaker_sequence"]
    assert offsets[opener] == [0, -20]
    assert offsets[reply] == [0, 0]
    assert plan["dialogue_layout_policy"] == "direct_head_anchor_overlay_paint_order"

    by_time = {row["timestamp_ms"]: row for row in plan["timeline"]}
    start = plan["talk_start_ms"]
    assert sum(bool(actor.get("dialogue_visible")) for actor in by_time[start]["actors"].values()) == 1
    gap_row = by_time[start + 500]
    assert sum(bool(actor.get("dialogue_visible")) for actor in gap_row["actors"].values()) == 2
    fade_row = by_time[start + 4000]
    assert all(actor.get("dialogue_phase") == "fading" for actor in fade_row["actors"].values())
    end_row = by_time[start + 4300]
    assert all(not actor.get("dialogue_visible") for actor in end_row["actors"].values())
    assert all(actor["phase"] == "talk_complete" for actor in end_row["actors"].values())
    for employee_id in employees[:2]:
        assert plan["snapshot_after"]["actors"][employee_id]["workstation_id"] == snapshot["actors"][employee_id]["workstation_id"]


def test_self_talk_uses_general_line_and_never_leaves_workseat():
    core = CentralGameCore(ROOT)
    snapshot = core.resolve_conversation_snapshot("floor02")
    employee_id = next(iter(snapshot["actors"]))
    plan = core.resolve_conversation_self_talk(employee_id)
    assert plan["ready"] is True
    assert plan["dialogue"]["selection_policy"] == "self_talk_general"
    assert plan["dialogue"]["speaker_lines"][0]["category"] not in {
        "conversation_open", "conversation_reply"
    }
    assert all(row["render_owner"] == "work_seat" for row in plan["tracks"][employee_id])
    assert any(row.get("dialogue_visible") for row in plan["tracks"][employee_id])
    advanced = core.advance_conversation(snapshot, plan, tick_ms=60)
    assert advanced["complete"] is False
    assert advanced["snapshot"]["clock_ms"] == 60
    finished = advanced
    for _ in range(100):
        if finished["complete"]:
            break
        finished = core.advance_conversation(finished["snapshot"], plan, tick_ms=60)
    assert finished["complete"] is True
    assert finished["snapshot"]["actors"][employee_id]["phase"] == "working"


@pytest.mark.parametrize(
    ("mode", "expected_extra_offset", "expected_actual_delta"),
    [
        ("seated_host", [0, -20], -40),
        ("ceo_front", [0, 0], -20),
    ],
)
def test_walking_visitor_bubble_uses_mode_specific_offsets(
    mode: str,
    expected_extra_offset: list[int],
    expected_actual_delta: int,
):
    core = CentralGameCore(ROOT)
    snapshot = core.resolve_conversation_snapshot("floor02")
    employees = [
        employee_id
        for employee_id, actor in snapshot["actors"].items()
        if actor["role"] == "employee"
    ]
    visitor_id = employees[0]
    partner_id = (
        next(employee_id for employee_id, actor in snapshot["actors"].items() if actor["role"] == "ceo")
        if mode == "ceo_front"
        else employees[1]
    )

    plan = core.resolve_conversation_plan(
        visitor_id,
        partner_id=partner_id,
        mode=mode,
        snapshot=snapshot,
    )
    host_id = plan["host_id"]
    at_reply = next(
        row for row in plan["timeline"]
        if row["timestamp_ms"] == plan["talk_start_ms"] + 500
    )

    assert plan["bubble_offset_by_actor"].get(visitor_id, [0, 0]) == expected_extra_offset
    assert at_reply["actors"][visitor_id].get("dialogue_bubble_offset_px", [0, 0]) == expected_extra_offset
    assert at_reply["actors"][host_id].get("dialogue_bubble_offset_px", [0, 0]) == [0, 0]

    renderer = ConversationPairGifRenderer(ROOT)
    visitor_bubble = renderer._bubble_payload(visitor_id, at_reply["actors"][visitor_id])["bubble"]
    host_bubble = renderer._bubble_payload(host_id, at_reply["actors"][host_id])["bubble"]
    assert visitor_bubble.bubble_top_left[1] - visitor_bubble.head_anchor[1] == expected_actual_delta
    assert host_bubble.bubble_top_left[1] - host_bubble.head_anchor[1] == -20


def test_gif_bubbles_use_exact_head_anchors_and_later_turn_paints_last():
    renderer = ConversationPairGifRenderer(ROOT)
    snapshot = renderer.core.resolve_conversation_snapshot("floor02")
    ids = floor_actor_ids(renderer.core, "floor02")
    employees = [
        employee_id
        for employee_id in ids
        if snapshot["actors"][employee_id]["role"] == "employee"
    ]
    plan = renderer.core.resolve_conversation_plan(
        employees[0],
        partner_id=employees[1],
        mode="standing_pair",
        snapshot=snapshot,
        origin_uvs=[],
    )
    row = next(
        row for row in plan["timeline"]
        if row["timestamp_ms"] == plan["talk_start_ms"] + 500
    )
    payloads = [
        payload
        for employee_id, state in row["actors"].items()
        if (payload := renderer._bubble_payload(employee_id, state)) is not None
    ]
    assert len(payloads) == 2
    assert all(
        payload["bubble"].bubble_tail_global[0] == payload["anchor"][0]
        for payload in payloads
    )
    class CaptureCanvas:
        def __init__(self):
            self.destinations = []

        def alpha_composite(self, _image, destination):
            self.destinations.append(tuple(destination))

    for payload in payloads:
        canvas = CaptureCanvas()
        renderer._draw_bubble(canvas, payload)
        assert canvas.destinations == [tuple(payload["bubble"].bubble_top_left)]
    assert all(payload["turn_index"] in {0, 1} for payload in payloads)
    # The renderer sorts only by speaker turn, so the later bubble is painted
    # last; no screen-space collision resolver or offset is involved.
    paint_order = [payload["employee_id"] for payload in sorted(
        payloads,
        key=lambda payload: (payload["turn_index"], payload["employee_id"]),
    )]
    expected_order = [
        segment["speaker_id"]
        for segment in plan["speaker_schedule"]
    ]
    assert paint_order == expected_order


def test_gif_bubble_anchors_seated_human_to_composed_workseat_offset():
    renderer = ConversationPairGifRenderer(ROOT)
    snapshot = renderer.core.resolve_conversation_snapshot("floor02")
    ids = floor_actor_ids(renderer.core, "floor02")
    employees = [
        employee_id
        for employee_id in ids
        if snapshot["actors"][employee_id]["role"] == "employee"
    ]
    plan = renderer.core.resolve_conversation_plan(
        employees[0],
        partner_id=employees[1],
        mode="seated_host",
        snapshot=snapshot,
    )
    host_id = plan["host_id"]
    row = next(
        row for row in plan["timeline"]
        if row["timestamp_ms"] == plan["talk_start_ms"] + 500
    )
    state = row["actors"][host_id]
    payload = renderer._bubble_payload(host_id, state)
    assert payload is not None
    actor = renderer.core.employee_metadata.get(host_id)
    workstation_id = (actor.get("assignment") or {})["workstation_id"]
    seat = renderer.core.work_seats.resolve_workstation_seat("floor02", workstation_id)
    action = renderer.core.characters.render(
        actor["character_id"], "work", seat["direction"], state.get("subaction", "normal_work")
    )
    chair = renderer.core.world.load_asset(seat["chair_asset_id"]).convert("RGBA")
    visual_offset = renderer.core.work_seats.resolve_world_offset(
        seat["direction"], chair_size=chair.size, human_size=action.frames[0].size
    )
    actual_top_left = (
        seat["chair_x_px"] + visual_offset[0],
        seat["chair_y_px"] + visual_offset[1],
    )
    frame_ids = renderer.core.characters.resolve_frame_ids(
        actor["character_id"], "work", seat["direction"], state.get("subaction", "normal_work")
    )
    frame_id = frame_ids[int(state.get("frame_index", 0)) % len(frame_ids)]
    expected = renderer.core.render_employee_dialogue_bubble(
        host_id,
        frame_id,
        state["dialogue_text"],
        actor_top_left=actual_top_left,
        locale=state.get("dialogue_locale", "en"),
    )
    assert payload["bubble"].head_anchor == expected.head_anchor


def test_plan_emits_one_visible_speaker_per_pair_turn_and_validates_timing_conflicts():
    core = CentralGameCore(ROOT)
    snapshot = core.resolve_conversation_snapshot("floor02")
    ids = floor_actor_ids(core, "floor02")
    employees = [employee_id for employee_id in ids if snapshot["actors"][employee_id]["role"] == "employee"]
    plan = core.resolve_conversation_plan(
        employees[0],
        partner_id=employees[1],
        mode="standing_pair",
        snapshot=snapshot,
        timing={"talk_frames": 12, "loop_count": 2},
        origin_uvs=[],
    )
    assert plan["ready"] is True
    assert plan["loop_count"] == 2
    talking_rows = [
        row for row in plan["timeline"]
        if any(actor.get("phase") == "talking" for actor in row["actors"].values())
    ]
    assert talking_rows
    assert all(
        sum(bool(actor.get("dialogue_visible")) for actor in row["actors"].values()) == 1
        for row in talking_rows
    )
    with pytest.raises(CentralGameCoreError, match="conflicts"):
        core.resolve_conversation_plan(
            employees[0],
            partner_id=employees[1],
            mode="standing_pair",
            snapshot=snapshot,
            talk_frames=2,
            timing={"talk_frames": 3},
            origin_uvs=[],
        )
