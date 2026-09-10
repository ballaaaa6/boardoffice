from __future__ import annotations

import json
from pathlib import Path

import pytest

from RUNTIME.actor_simulation_core import ActorSimulationCore
from RUNTIME.visual_selection_core import VisualSelectionCore, VisualSelectionError


ROOT = Path(__file__).resolve().parents[1]


def visual_sequence(
    visual: VisualSelectionCore,
    channel: str,
    seed: str,
    employee_id: str,
    count: int,
) -> list[str]:
    state = visual.initial_channel_state(channel)
    result: list[str] = []
    for index in range(count):
        state, binding = visual.select(
            state,
            channel=channel,
            simulation_seed=seed,
            employee_id=employee_id,
            event_id=f"event-{index}",
            started_at_ms=index * 60,
            ends_at_ms=(index + 1) * 60,
        )
        result.append(binding["asset_id"])
        state = visual.clear_active(state, channel=channel, event_id=f"event-{index}")
    return result


def test_visual_catalog_exposes_all_canonical_ids():
    visual = VisualSelectionCore(ROOT)
    catalog = visual.catalog()
    effect_registry = json.loads(
        (ROOT / "CHARACTER/EFFECTS/gds_effects_v1.json").read_text(encoding="utf-8")
    )
    humanball_registry = json.loads(
        (ROOT / "CHARACTER/EFFECTS/humanball_v1.json").read_text(encoding="utf-8")
    )
    office_humanball_registry = json.loads(
        (ROOT / "CHARACTER/EFFECTS/office_humanball_v1.json").read_text(encoding="utf-8")
    )

    assert catalog["vfx"]["ids"] == effect_registry["effect_order"]
    expected_popup_ids = [
        *humanball_registry["humanball_order"],
        *office_humanball_registry["office_humanball_order"],
    ]
    assert catalog["humanball"]["ids"] == expected_popup_ids
    assert len(catalog["vfx"]["ids"]) == 11
    assert len(catalog["humanball"]["ids"]) == 44
    assert catalog["humanball"]["pool_mode"] == "canonical_plus_office"
    assert catalog["profile_id"] == "gds.visual_catalog.v1"


def test_vfx_bag_has_no_repeat_then_refills_deterministically():
    visual = VisualSelectionCore(ROOT)
    selected = visual_sequence(visual, "vfx", "bag-seed", "EMP_W1_0010", 23)
    first_generation = selected[:11]
    second_generation = selected[11:22]

    assert len(set(first_generation)) == 11
    assert len(set(second_generation)) == 11
    assert set(first_generation) == set(visual.catalog()["vfx"]["ids"])
    assert set(second_generation) == set(visual.catalog()["vfx"]["ids"])
    assert selected == visual_sequence(visual, "vfx", "bag-seed", "EMP_W1_0010", 23)


def test_popup_bag_covers_all_44_assets_before_repeat():
    visual = VisualSelectionCore(ROOT)
    selected = visual_sequence(visual, "humanball", "popup-seed", "EMP_W1_0010", 89)

    assert len(set(selected[:44])) == 44
    assert set(selected[:44]) == set(visual.catalog()["humanball"]["ids"])
    assert len(set(selected[44:88])) == 44
    assert selected[88] in visual.catalog()["humanball"]["ids"]


def test_popup_bag_avoids_immediate_repeat_at_generation_boundary():
    visual = VisualSelectionCore(ROOT)
    for seed_index in range(64):
        seed = f"seed-{seed_index}"
        for employee_id in ("EMP_W1_0010", "EMP_W1_0031", "EMP_W1_0044"):
            selected = visual_sequence(visual, "humanball", seed, employee_id, 89)
            assert all(
                left != right for left, right in zip(selected, selected[1:])
            ), f"{employee_id} {seed} repeated at a generation boundary"


def test_popup_bag_scope_can_be_shared_across_actors():
    visual = VisualSelectionCore(ROOT)
    shared_state = visual.initial_channel_state("humanball")
    first_state, first = visual.select(
        shared_state,
        channel="humanball",
        simulation_seed="shared-popup-seed",
        employee_id="EMP_W1_0010",
        bag_employee_id="global_humanball",
        event_id="shared-event-1",
        started_at_ms=0,
        ends_at_ms=60,
    )
    first_state = visual.clear_active(
        first_state,
        channel="humanball",
        event_id="shared-event-1",
    )
    _second_state, second = visual.select(
        first_state,
        channel="humanball",
        simulation_seed="shared-popup-seed",
        employee_id="EMP_W1_0011",
        bag_employee_id="global_humanball",
        event_id="shared-event-2",
        started_at_ms=60,
        ends_at_ms=120,
    )

    assert first["asset_id"] != second["asset_id"]


def test_visual_bags_are_independent_by_actor_and_channel():
    visual = VisualSelectionCore(ROOT)
    vfx_a = visual_sequence(visual, "vfx", "same-seed", "EMP_W1_0010", 1)[0]
    vfx_b = visual_sequence(visual, "vfx", "same-seed", "EMP_W1_0011", 1)[0]
    popup_a = visual_sequence(visual, "humanball", "same-seed", "EMP_W1_0010", 1)[0]

    assert vfx_a in visual.catalog()["vfx"]["ids"]
    assert vfx_b in visual.catalog()["vfx"]["ids"]
    assert popup_a in visual.catalog()["humanball"]["ids"]
    assert visual_sequence(visual, "vfx", "same-seed", "EMP_W1_0010", 3) != visual_sequence(
        visual, "humanball", "same-seed", "EMP_W1_0010", 3
    )


def test_active_binding_is_stable_and_clears_only_for_its_event():
    visual = VisualSelectionCore(ROOT)
    state, binding = visual.select(
        visual.initial_channel_state("vfx"),
        channel="vfx",
        simulation_seed="binding-seed",
        employee_id="EMP_W1_0010",
        event_id="event-a",
        started_at_ms=120,
        ends_at_ms=420,
    )

    assert state["active_binding"] == binding
    assert binding["cursor_after"] == 1
    with pytest.raises(VisualSelectionError, match="active binding belongs to event"):
        visual.clear_active(state, event_id="event-b")
    cleared = visual.clear_active(state, event_id="event-a")
    assert cleared["active_binding"] is None
    assert cleared["cursor"] == 1


def test_invalid_channel_and_invalid_catalog_state_fail_fast():
    visual = VisualSelectionCore(ROOT)
    with pytest.raises(VisualSelectionError, match="unknown visual channel"):
        visual.initial_channel_state("dialogue")

    state = visual.initial_channel_state("vfx")
    state["catalog_profile"] = "gds.visual_catalog.v1:wrong"
    with pytest.raises(VisualSelectionError, match="catalog profile mismatch"):
        visual.select(
            state,
            channel="vfx",
            simulation_seed="seed",
            employee_id="EMP_W1_0010",
            event_id="event-a",
            started_at_ms=0,
            ends_at_ms=60,
        )


def test_registry_with_duplicate_ids_is_rejected(tmp_path: Path):
    effect_path = ROOT / "CHARACTER/EFFECTS/gds_effects_v1.json"
    humanball_path = ROOT / "CHARACTER/EFFECTS/humanball_v1.json"
    for source in (effect_path, humanball_path):
        target = tmp_path / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    duplicate = json.loads(effect_path.read_text(encoding="utf-8"))
    duplicate["effect_order"].append(duplicate["effect_order"][0])
    (tmp_path / "CHARACTER/EFFECTS/gds_effects_v1.json").write_text(
        json.dumps(duplicate),
        encoding="utf-8",
    )

    with pytest.raises(VisualSelectionError, match="must contain unique IDs"):
        VisualSelectionCore(tmp_path)


def test_actor_snapshot_starts_with_two_empty_visual_channel_states():
    actor_snapshot = ActorSimulationCore(ROOT).initial_snapshot("floor02")
    behavior = actor_snapshot["actors"]["EMP_W1_0010"]["behavior"]

    assert set(behavior["visual_channels"]) == {"vfx", "humanball"}
    assert behavior["visual_channels"]["vfx"]["cursor"] == 0
    assert behavior["visual_channels"]["humanball"]["cursor"] == 0
    assert behavior["visual_channels"]["vfx"]["active_binding"] is None


def test_actor_effect_presentation_uses_one_binding_until_event_completion():
    core = ActorSimulationCore(ROOT)
    snapshot = core.initial_snapshot("floor02")
    actor = snapshot["actors"]["EMP_W1_0010"]
    employee = core.employee_registry.get("EMP_W1_0010")
    events: list[dict] = []

    core._start_event(
        snapshot,
        actor,
        employee,
        "background_effect",
        timestamp_ms=0,
        events=events,
    )
    first = core._presentation_for_behavior(
        employee,
        "background_effect",
        counter=1,
        actor=actor,
    )
    second = core._presentation_for_behavior(
        employee,
        "background_effect",
        counter=1,
        actor=actor,
    )

    assert first["asset_id"] in core.visual_selection.catalog()["vfx"]["ids"]
    assert first["asset_id"] == second["asset_id"]
    assert actor["behavior"]["visual_channels"]["vfx"]["active_binding"]["asset_id"] == first["asset_id"]

    core._complete_event(
        snapshot,
        actor,
        employee,
        timestamp_ms=int(actor["behavior"]["activity_until_ms"]),
        events=events,
    )
    assert actor["behavior"]["visual_channels"]["vfx"]["active_binding"] is None


def test_actor_vfx_events_consume_all_catalog_ids_without_repetition():
    core = ActorSimulationCore(ROOT)
    snapshot = core.initial_snapshot("floor02")
    actor = snapshot["actors"]["EMP_W1_0010"]
    employee = core.employee_registry.get("EMP_W1_0010")
    selected: list[str] = []

    for index in range(11):
        events: list[dict] = []
        core._start_event(
            snapshot,
            actor,
            employee,
            "background_effect",
            timestamp_ms=index * 6000,
            events=events,
        )
        selected.append(actor["behavior"]["visual_channels"]["vfx"]["active_binding"]["asset_id"])
        core._complete_event(
            snapshot,
            actor,
            employee,
            timestamp_ms=(index + 1) * 6000,
            events=events,
        )

    assert len(set(selected)) == 11
    assert set(selected) == set(core.visual_selection.catalog()["vfx"]["ids"])


def test_actor_popup_events_share_one_global_humanball_bag():
    core = ActorSimulationCore(ROOT)
    snapshot = core.initial_snapshot("floor02")
    first_actor = snapshot["actors"]["EMP_W1_0011"]
    second_actor = snapshot["actors"]["EMP_W1_0030"]
    first_employee = core.employee_registry.get(first_actor["employee_id"])
    second_employee = core.employee_registry.get(second_actor["employee_id"])

    core._start_event(
        snapshot,
        first_actor,
        first_employee,
        "popup",
        timestamp_ms=0,
        events=[],
    )
    first_asset = first_actor["behavior"]["visual_channels"]["humanball"]["active_binding"]["asset_id"]
    core._complete_event(
        snapshot,
        first_actor,
        first_employee,
        timestamp_ms=first_actor["behavior"]["activity_until_ms"],
        events=[],
    )
    core._start_event(
        snapshot,
        second_actor,
        second_employee,
        "popup",
        timestamp_ms=6000,
        events=[],
    )
    second_asset = second_actor["behavior"]["visual_channels"]["humanball"]["active_binding"]["asset_id"]

    assert first_asset != second_asset
    assert snapshot["determinism"]["humanball_global_bag"]["cursor"] == 2
    assert snapshot["determinism"]["humanball_global_bag"]["active_binding"] is None
