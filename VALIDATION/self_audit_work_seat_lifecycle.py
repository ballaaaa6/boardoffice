from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def audit(core_root: str | Path, *, write_report: bool = True) -> dict[str, Any]:
    root = Path(core_root).resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from RUNTIME.central_core import CentralGameCore

    schema_path = root / "SCHEMA" / "work_seat_lifecycle.schema.json"
    contract_path = root / "CONTRACTS" / "work_seat_lifecycle.json"
    schema = _load(schema_path)
    contract = _load(contract_path)
    schema_errors = [error.message for error in Draft202012Validator(schema).iter_errors(contract)]

    core = CentralGameCore(root)
    slot_audit = core.audit_work_seat_interaction_slots()
    metadata = _load(root / "CHARACTER" / "CHARACTERS" / "characters.json")
    cards = _load(root / "CHARACTER" / "IDENTITY" / "CHARACTERS" / "identity_cards.json")
    cards_by_id = {row["character_id"]: row for row in cards["characters"]}
    profile_rows = metadata["characters"]
    metadata_ok = (
        len(profile_rows) == 302
        and metadata["movement_profile_contract"]["speed_range_percent"] == [225, 250]
        and metadata["movement_profile_contract"]["assignment_policy"]
        == "embedded_character_metadata"
        and all(
            225 <= row["movement_profile"]["speed_percent"] <= 250
            and cards_by_id[row["character_id"]]["movement_profile"] == row["movement_profile"]
            for row in profile_rows
        )
    )
    actions = _load(root / "CHARACTER" / "ACTIONS" / "gds_standard_v1.json")
    semantics = actions.get("action_semantics", {})
    semantics_ok = (
        semantics.get("primary_groups") == ["idle", "move", "work"]
        and semantics.get("event_groups") == ["sad", "happy"]
        and semantics.get("sad", {}).get("directional") is False
        and semantics.get("happy", {}).get("directional") is False
        and semantics.get("work", {}).get("pose_category") == "seated"
    )

    cycle_cases = [
        ("floor00", "ceo"),
        ("floor00", "ws3"),
        ("floor01", "ceo"),
        ("floor01", "ws3"),
        ("floor02", "ws1"),
        ("floor02", "ws3"),
        ("floor02", "ceo"),
        ("floor14", "ceo"),
        ("floor17", "ws3"),
    ]
    cycle_errors: list[dict[str, str]] = []
    cycles_checked = 0
    for floor_id, workstation_id in cycle_cases:
        try:
            start = tuple(core.resolve_portal_navigation_start(floor_id))
            cycle = core.resolve_work_seat_actor_cycle(
                0,
                floor_id,
                workstation_id,
                start,
                work_ticks=24,
            )
            states = cycle["states"]
            timestamps = [row["timestamp_ms"] for row in states]
            phases = [row["phase"] for row in states]
            if (
                not cycle["completed"]
                or cycle["final_slot_state"] != "free"
                or cycle["final_state"]["current_uv"] != list(start)
                or cycle["phase_counts"].get("seated_work") != 24
                or timestamps != sorted(timestamps)
                or any(
                    current <= previous
                    for previous, current in zip(timestamps, timestamps[1:])
                )
                or phases[0] != "walking_to_seat"
                or phases[-1] != "walking_from_seat"
                or any(
                    row["walking_visible"] and row["seated_visible"] for row in states
                )
            ):
                raise ValueError("state/slot/timing invariant failed")
            cycles_checked += 1
        except Exception as exc:  # pragma: no cover - audit reports preserve all evidence
            cycle_errors.append(
                {"floor_id": floor_id, "workstation_id": workstation_id, "error": repr(exc)}
            )

    report = {
        "schema": "gds.phase8d.work_seat_lifecycle_audit.v1",
        "pass": bool(
            not schema_errors
            and slot_audit["pass"]
            and metadata_ok
            and semantics_ok
            and cycles_checked == len(cycle_cases)
            and not cycle_errors
        ),
        "checks": {
            "contract_schema_valid": not schema_errors,
            "all_219_slots_runtime_derived": slot_audit["pass"],
            "per_character_speed_metadata_302": metadata_ok,
            "action_semantics_locked": semantics_ok,
            "canonical_single_actor_cycles": cycles_checked == len(cycle_cases),
            "exclusive_render_channels": not cycle_errors,
        },
        "counts": {
            "floor_count": slot_audit["floor_count"],
            "workstation_count": slot_audit["workstation_count"],
            "slot_count": slot_audit["slot_count"],
            "character_count": len(profile_rows),
            "canonical_cycles_checked": cycles_checked,
        },
        "slot_audit": slot_audit,
        "schema_errors": schema_errors,
        "cycle_errors": cycle_errors,
        "speed_profile_contract": metadata["movement_profile_contract"],
        "acceptance": "visual_author_acceptance_pending",
    }
    if write_report:
        out = root / "REPORTS" / "PHASE8D_WORK_SEAT_LIFECYCLE_AUDIT.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--core-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    result = audit(args.core_root, write_report=not args.no_write)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result["pass"] else 1)
