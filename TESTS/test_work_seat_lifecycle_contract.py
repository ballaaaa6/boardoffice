from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from RUNTIME.central_core import CentralGameCore


ROOT = Path(__file__).resolve().parents[1]


def test_work_seat_lifecycle_contract_validates_and_action_semantics_are_explicit():
    schema = json.loads(
        (ROOT / "SCHEMA" / "work_seat_lifecycle.schema.json").read_text(encoding="utf-8")
    )
    contract = json.loads(
        (ROOT / "CONTRACTS" / "work_seat_lifecycle.json").read_text(encoding="utf-8")
    )
    assert list(Draft202012Validator(schema).iter_errors(contract)) == []

    actions = json.loads(
        (ROOT / "CHARACTER" / "ACTIONS" / "gds_standard_v1.json").read_text(encoding="utf-8")
    )
    semantics = actions["action_semantics"]
    assert semantics["primary_groups"] == ["idle", "move", "work"]
    assert semantics["event_groups"] == ["sad", "happy"]
    assert semantics["idle"]["directional"] is True
    assert semantics["move"]["directional"] is True
    assert semantics["work"]["usage"] == "allowed_only_after_work_seat_takeover"
    assert semantics["sad"]["directional"] is False
    assert semantics["happy"]["directional"] is False


def test_per_character_speed_metadata_is_complete_rerolled_and_synchronized():
    technical = json.loads(
        (ROOT / "CHARACTER" / "CHARACTERS" / "characters.json").read_text(encoding="utf-8")
    )
    cards = json.loads(
        (ROOT / "CHARACTER" / "IDENTITY" / "CHARACTERS" / "identity_cards.json").read_text(encoding="utf-8")
    )
    by_id = {row["character_id"]: row for row in cards["characters"]}
    rows = technical["characters"]
    assert len(rows) == 302
    assert technical["movement_profile_contract"]["assignment_policy"] == "embedded_character_metadata"
    assert technical["movement_profile_contract"]["speed_range_percent"] == [225, 250]
    assert technical["movement_profile_contract"]["profile_seed"].endswith("20260831")
    assert all(225 <= row["movement_profile"]["speed_percent"] <= 250 for row in rows)
    assert all(
        by_id[row["character_id"]]["movement_profile"] == row["movement_profile"]
        for row in rows
    )
    assert len({row["movement_profile"]["speed_percent"] for row in rows}) == 26


def test_all_workstation_interaction_slots_are_runtime_derived_and_unique():
    core = CentralGameCore(ROOT)
    audit = core.audit_work_seat_interaction_slots()
    assert audit["pass"] is True
    assert audit["floor_count"] == 25
    assert audit["slot_count"] == 219
    assert audit["unique_slot_id_count"] == 219
    assert audit["capacity_values"] == [1]
    assert audit["direction_counts"] == {"SE": 100, "NW": 96, "SW": 23, "NE": 0}

    for floor_id, workstation_id, direction in (
        ("floor00", "ceo", "SE"),
        ("floor00", "ws3", "NW"),
        ("floor01", "ceo", "SE"),
        ("floor01", "ws3", "NW"),
        ("floor02", "ws1", "SE"),
        ("floor02", "ws3", "NW"),
        ("floor02", "ceo", "SW"),
    ):
        slot = core.resolve_work_seat_interaction_slot(floor_id, workstation_id)
        assert slot["slot_id"] == f"workseat:{floor_id}:{workstation_id}:primary"
        assert slot["facing"] == direction
        assert slot["capacity"] == 1
        assert slot["seat_transition_ready"] is True
        assert slot["enter_action"] is None
        assert slot["exit_action"] is None
        assert slot["turn_side_bindings"]["work_direction"] == direction
        expected_turn_names = {
            "SE": {"turn_side_sw", "turn_side_ne"},
            "SW": {"turn_side_se", "turn_side_nw"},
            "NW": {"turn_side_sw", "turn_side_ne"},
            "NE": {"turn_side_se", "turn_side_nw"},
        }[direction]
        assert set(slot["turn_side_bindings"]) == {"work_direction", *expected_turn_names}
        assert all(
            entry["action"] == "work"
            and entry["direction"] == direction
            and entry["direction_source"] == "turn_axis_mapping"
            for entry in [slot["turn_side_bindings"][name] for name in sorted(expected_turn_names)]
        )


def test_directionless_event_actions_reject_direction_and_resolve_without_one():
    core = CentralGameCore(ROOT)
    happy = core.resolve_character_event_action(0, "happy")
    sad = core.resolve_character_event_action("TP_000", "sad")
    assert happy["direction"] is None
    assert sad["direction"] is None
    assert happy["semantic_group"] == sad["semantic_group"] == "event_emotion"
    assert happy["frame_count"] == 3
    assert sad["frame_count"] == 3
