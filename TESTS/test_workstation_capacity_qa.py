from pathlib import Path

import pytest

from RUNTIME.central_core import CentralGameCore
from TOOLS.render_workstation_capacity_qa import (
    CASES,
    character_ids,
    portal_starts,
    workstation_ids,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("floor_id", "expected_count"),
    (
        ("floor00", 5),
        ("floor01", 7),
        ("floor02", 9),
        ("floor14", 9),
        ("floor17", 9),
    ),
)
def test_capacity_qa_actor_count_matches_authored_computers(floor_id: str, expected_count: int):
    core = CentralGameCore(ROOT)
    computers = workstation_ids(core, floor_id)
    starts = portal_starts(core, floor_id, len(computers))

    assert len(computers) == expected_count
    assert len(starts) == expected_count
    assert len(set(starts)) == expected_count


@pytest.mark.parametrize("_label,floor_id", CASES)
def test_capacity_qa_assigns_one_ready_capacity_one_slot_per_computer(
    _label: str, floor_id: str
):
    core = CentralGameCore(ROOT)
    computers = workstation_ids(core, floor_id)
    slots = [core.resolve_work_seat_interaction_slot(floor_id, workstation_id) for workstation_id in computers]

    assert len(slots) == len(computers)
    assert len({slot["slot_id"] for slot in slots}) == len(slots)
    assert all(slot["capacity"] == 1 for slot in slots)
    assert all(slot["seat_transition_ready"] for slot in slots)


def test_capacity_qa_uses_only_as_many_canonical_characters_as_computers():
    roster = character_ids(ROOT)
    assert len(roster) >= max(
        len(workstation_ids(CentralGameCore(ROOT), floor_id)) for _label, floor_id in CASES
    )
