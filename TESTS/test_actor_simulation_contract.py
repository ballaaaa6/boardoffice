import json
from pathlib import Path

from jsonschema import Draft202012Validator

from RUNTIME.employee_registry import EmployeeMetadataRegistry


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "CONTRACTS" / "actor_simulation.json"
SCHEMA_PATH = ROOT / "SCHEMA" / "actor_simulation.schema.json"
SNAPSHOT_SCHEMA_PATH = ROOT / "SCHEMA" / "actor_snapshot.schema.json"
METADATA_PATH = ROOT / "CHARACTER" / "EMPLOYEES" / "employee_metadata.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_actor_simulation_contract_matches_schema():
    contract = _load(CONTRACT_PATH)
    schema = _load(SCHEMA_PATH)

    assert list(Draft202012Validator(schema).iter_errors(contract)) == []
    assert contract["schema"] == "gds.actor_simulation.v1"
    assert contract["version"] == "1.0.0"


def _initial_actor_snapshot() -> dict:
    registry = EmployeeMetadataRegistry(ROOT)
    roster = registry.initial_roster()
    row = roster[0]
    employee = registry.get(row["employee_id"])
    return {
        "schema": "gds.actor_snapshot.v1",
        "version": "1.0.0",
        "clock": {
            "simulation_time_ms": 0,
            "tick_ms": 60,
        },
        "determinism": {
            "simulation_seed": "test-actor-snapshot-v1",
            "root_event_counter": 0,
        },
        "actors": {
            row["employee_id"]: {
                "employee_id": row["employee_id"],
                "character_id": employee["character_id"],
                "assignment": {
                    "floor_id": row["floor_id"],
                    "workstation_id": row["workstation_id"],
                    "slot_id": row["slot_id"],
                    "assignment_order": row["assignment_order"],
                    "facing": row["facing"],
                },
                "presence": "present",
                "activity": "working",
                "position": {
                    "floor_id": row["floor_id"],
                    "uv": None,
                    "ground_xy": None,
                    "route": None,
                },
                "stamina": {
                    "current_milli": 100000,
                    "max_milli": 100000,
                    "threshold_band": "normal",
                    "drain_remainder": 0,
                },
                "behavior": {
                    "profile_seed": "gds-employee-stamina-profile-v1",
                    "event_counter": 0,
                    "next_event_due_ms": None,
                    "activity_started_ms": 0,
                    "activity_until_ms": None,
                    "active_event": None,
                    "cooldowns": {},
                },
                "conversation_phase": None,
                "last_event": "initial",
            }
        },
    }


def test_actor_snapshot_schema_accepts_initial_assigned_actor():
    snapshot_schema = _load(SNAPSHOT_SCHEMA_PATH)
    snapshot = _initial_actor_snapshot()

    assert list(Draft202012Validator(snapshot_schema).iter_errors(snapshot)) == []


def test_actor_snapshot_schema_rejects_invalid_state_pairs_and_talk_subphase():
    snapshot_schema = _load(SNAPSHOT_SCHEMA_PATH)
    snapshot = _initial_actor_snapshot()
    actor = next(iter(snapshot["actors"].values()))

    actor["presence"] = "home"
    errors = list(Draft202012Validator(snapshot_schema).iter_errors(snapshot))
    assert any("oneOf" in error.validator for error in errors)

    actor["presence"] = "present"
    actor["activity"] = "working"
    actor["conversation_phase"] = "talking"
    errors = list(Draft202012Validator(snapshot_schema).iter_errors(snapshot))
    assert any(error.json_path.endswith("conversation_phase") for error in errors)


def test_actor_snapshot_schema_rejects_float_or_out_of_range_stamina():
    snapshot_schema = _load(SNAPSHOT_SCHEMA_PATH)
    snapshot = _initial_actor_snapshot()
    actor = next(iter(snapshot["actors"].values()))

    actor["stamina"]["current_milli"] = 100000.5
    errors = list(Draft202012Validator(snapshot_schema).iter_errors(snapshot))
    assert any(error.json_path.endswith("current_milli") for error in errors)

    actor["stamina"]["current_milli"] = 100001
    errors = list(Draft202012Validator(snapshot_schema).iter_errors(snapshot))
    assert any(error.json_path.endswith("current_milli") for error in errors)


def test_actor_snapshot_contract_binds_existing_identity_and_workseat_sources():
    contract = _load(CONTRACT_PATH)

    assert contract["identity_binding"]["actor_id"] == "employee_id"
    assert contract["identity_binding"]["visual_template_id"] == "character_id"
    assert contract["snapshot"]["assignment_validation"].startswith("resolve_against_")
    assert contract["assignment"]["slot_id_policy"] == (
        "runtime_derived_and_validated_not_a_second_registry"
    )

    registry = EmployeeMetadataRegistry(ROOT)
    roster = registry.initial_roster()
    assert len(roster) == 219
    assert len({row["employee_id"] for row in roster}) == 219
    assert len({row["slot_id"] for row in roster}) == 219


def test_actor_simulation_contract_freezes_state_pairs_and_transitions():
    contract = _load(CONTRACT_PATH)
    vocabulary = contract["state_vocabulary"]

    assert vocabulary["presence"] == ["home", "entering", "present", "leaving"]
    assert vocabulary["activity"] == [
        "walking_to_work",
        "working",
        "talking",
        "wandering",
        "popup_event",
        "going_home",
        "home_recovery",
        "returning_to_work",
    ]
    pairs = {(row["presence"], row["activity"]) for row in vocabulary["legal_state_pairs"]}
    assert ("present", "working") in pairs
    assert ("home", "home_recovery") in pairs
    assert ("leaving", "going_home") in pairs
    assert ["present/working", "present/talking"] in vocabulary["legal_transitions"]
    assert ["home/home_recovery", "entering/returning_to_work"] in vocabulary["legal_transitions"]


def test_actor_simulation_contract_freezes_integer_stamina_policy_and_weights():
    contract = _load(CONTRACT_PATH)
    stamina = contract["stamina"]
    behavior = contract["behavior"]
    metadata = _load(METADATA_PATH)

    assert stamina["storage_unit"] == "milli_stamina"
    assert stamina["display_to_storage_scale"] == 1000
    assert stamina["max_milli"] == stamina["max_display"] * 1000
    assert stamina["low_threshold_display"] == 30
    assert stamina["critical_threshold_display"] == metadata["stamina_policy"]["critical_threshold"]
    assert stamina["drain_range_milli_per_second"] == metadata["stamina_policy"]["per_employee_work_drain_range"]
    assert sum(behavior["selection_weights"].values()) == behavior["selection_weights_sum"] == 100
    assert behavior["visual_side_effect_policy"].endswith("never_mutates_stamina")


def test_actor_simulation_contract_keeps_snapshot_storage_renderer_agnostic():
    contract = _load(CONTRACT_PATH)
    snapshot = contract["snapshot"]
    output = contract["output"]

    assert snapshot["assignment_is_authoritative"] is False
    assert snapshot["render_policy"] == "render_action_and_render_owner_are_derived_presentation_outputs"
    assert output["storage_owner"] == "dashboard_or_calling_application"
    assert output["database_or_network"] is False
    assert output["hidden_process_state"] is False


def test_actor_simulation_contract_declares_route_and_presentation_bridges():
    contract = _load(CONTRACT_PATH)
    assert contract["routing"]["commands"] == ["request_home", "request_return"]
    assert contract["routing"]["portal_fade_steps"] == 4
    assert contract["routing"]["assignment_return_policy"] == (
        "same_owned_workstation_and_transition_gate"
    )
    assert contract["presentation"]["channels"] == [
        "conversation", "vfx", "humanball", "movement"
    ]
    assert contract["presentation"]["timing_ms"] == {
        "simulation_tick": 60,
        "character_frame": 360,
        "effect_frame": 240,
        "humanball_frame": 240,
        "normal_work_loop": 720,
    }
