import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from RUNTIME.central_core import CentralGameCore
from RUNTIME.central_core import CentralGameCoreError
from RUNTIME.employee_registry import EmployeeMetadataRegistry
from TOOLS.generate_employee_metadata import build_metadata


ROOT = Path(__file__).resolve().parents[1]
METADATA_PATH = ROOT / "CHARACTER" / "EMPLOYEES" / "employee_metadata.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalized(values: list[str]) -> set[str]:
    return {value.casefold() for value in values}


def test_employee_metadata_matches_schema_and_is_deterministic():
    payload = _load(METADATA_PATH)
    schema = _load(ROOT / "SCHEMA" / "CHARACTER" / "employee_metadata.schema.json")

    assert list(Draft202012Validator(schema).iter_errors(payload)) == []
    assert payload == build_metadata(ROOT)


def test_wave1_and_wave2_bind_every_canonical_template_once():
    payload = _load(METADATA_PATH)
    cards = _load(
        ROOT / "CHARACTER" / "IDENTITY" / "CHARACTERS" / "identity_cards.json"
    )
    canonical_ids = {row["character_id"] for row in cards["characters"]}
    rows = payload["employees"]

    assert len(rows) == 604
    assert len({row["employee_id"] for row in rows}) == 604
    for wave in (1, 2):
        wave_rows = [row for row in rows if row["generation_wave"] == wave]
        assert len(wave_rows) == 302
        assert {row["character_id"] for row in wave_rows} == canonical_ids


def test_wave2_names_are_new_unique_and_gender_aligned():
    payload = _load(METADATA_PATH)
    cards = _load(
        ROOT / "CHARACTER" / "IDENTITY" / "CHARACTERS" / "identity_cards.json"
    )
    cards_by_id = {row["character_id"]: row for row in cards["characters"]}
    wave1 = [row for row in payload["employees"] if row["generation_wave"] == 1]
    wave2 = [row for row in payload["employees"] if row["generation_wave"] == 2]

    for field in ("first_name", "last_name", "nickname", "full_name"):
        wave2_values = _normalized([row[field] for row in wave2])
        wave1_values = _normalized([row[field] for row in wave1])
        assert len(wave2_values) == 302
        assert wave2_values.isdisjoint(wave1_values)
    assert len(_normalized([row["nickname"] for row in payload["employees"]])) == 604

    for row in wave2:
        template = cards_by_id[row["character_id"]]
        assert row["name_profile"]["pool"] == template["name_profile"]["pool"]
        assert row["name_profile"]["source_label"] == template["name_profile"]["source_label"]
        if row["name_profile"]["pool"] == "neutral":
            assert row["name_profile"]["source_label"] is None


def test_stamina_and_visual_references_are_ready_for_the_next_behavior_slice():
    payload = _load(METADATA_PATH)
    policy = payload["stamina_policy"]
    effect_registry = _load(ROOT / "CHARACTER" / "EFFECTS" / "gds_effects_v1.json")
    humanball_registry = _load(ROOT / "CHARACTER" / "EFFECTS" / "humanball_v1.json")

    assert policy["stamina_max"] == 100
    assert policy["critical_threshold"] == 10
    assert policy["target_work_cycle_seconds_range"] == [120, 300]
    assert policy["per_employee_work_drain_range"] == [600, 850]
    assert sum(
        event["selection_weight"] for event in policy["recovery_events"].values()
    ) == 100
    positive_effect_ids = {
        effect_id
        for effect_id in effect_registry["effect_order"]
        if effect_registry["effects"][effect_id].get("mood") == "positive"
    }
    assert set(policy["visual_recovery_references"]["effect_ids"]) == positive_effect_ids
    assert set(policy["visual_recovery_references"]["humanball_ids"]) == set(
        humanball_registry["humanball_order"]
    )

    rows = payload["employees"]
    drains = {
        row["stamina_profile"]["work_drain_milli_per_second"]
        for row in rows
    }
    assert len(drains) > 1
    assert all(
        row["stamina_profile"]["stamina_max"] == 100
        and 600 <= row["stamina_profile"]["work_drain_milli_per_second"] <= 850
        and 90 <= row["stamina_profile"]["event_timing_multiplier_percent"] <= 115
        for row in rows
    )


def test_initial_roster_uses_each_ready_computer_once_and_leaves_wave2_unassigned():
    registry = EmployeeMetadataRegistry(ROOT)
    roster = registry.initial_roster()
    wave1_assigned = registry.list(wave=1, assigned=True)
    wave1_unassigned = registry.list(wave=1, assigned=False)
    wave2_unassigned = registry.list(wave=2, assigned=False)

    assert len(roster) == 219
    assert len(wave1_assigned) == 219
    assert len(wave1_unassigned) == 83
    assert len(wave2_unassigned) == 302
    assert [row["assignment_order"] for row in roster] == list(range(219))
    assert roster[0]["floor_id"] == "floor00"
    assert roster[0]["workstation_id"] == "ceo"
    assert len({row["slot_id"] for row in roster}) == 219
    assert all(row["generation_wave"] == 1 for row in wave1_assigned)
    assert sum(row["character_pool"] == "original" for row in wave1_assigned) == 64
    assert sum(row["character_pool"] == "custom" for row in wave1_assigned) == 155
    assert all(row["assignment"] is None for row in wave2_unassigned)


def test_central_employee_bridge_keeps_character_render_identity_unchanged():
    core = CentralGameCore(ROOT)
    employee = core.resolve_employee("EMP_W2_0001")
    character_id = employee["character_id"]

    assert character_id == core.resolve_employee_movement_profile("EMP_W2_0001")["character_id"]
    assert core.resolve_employee_assignment("EMP_W2_0001") is None
    assert core.resolve_character_id(character_id) == character_id
    assert core.resolve_initial_employee_roster("floor00")[0]["workstation_id"] == "ceo"


def test_assigned_employee_can_use_existing_workseat_lifecycle_with_its_own_identity():
    core = CentralGameCore(ROOT)
    assignment = core.resolve_initial_employee_roster("floor00")[0]
    employee_id = assignment["employee_id"]
    start = tuple(core.resolve_portal_navigation_start("floor00"))

    cycle = core.resolve_employee_work_seat_actor_cycle(
        employee_id,
        "floor00",
        assignment["workstation_id"],
        start,
        work_ticks=1,
    )
    assert cycle["employee_id"] == employee_id
    assert cycle["character_id"] == assignment["character_id"]
    assert employee_id in cycle["actor_id"]
    assert cycle["movement_profile"]["employee_id"] == employee_id
    assert cycle["final_slot_state"] == "free"

    with pytest.raises(CentralGameCoreError):
        core.resolve_employee_work_seat_actor_cycle(
            "EMP_W2_0001",
            "floor00",
            "ceo",
            start,
            work_ticks=1,
        )
