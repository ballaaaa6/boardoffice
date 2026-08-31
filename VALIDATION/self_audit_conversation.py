from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]


def audit(root: str | Path = ROOT) -> dict[str, Any]:
    root = Path(root).resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from RUNTIME.central_core import CentralGameCore

    schema = json.loads((root / "SCHEMA" / "conversation_behavior.schema.json").read_text(encoding="utf-8"))
    contract = json.loads((root / "CONTRACTS" / "conversation_behavior.json").read_text(encoding="utf-8"))
    schema_errors = [error.message for error in Draft202012Validator(schema).iter_errors(contract)]
    core = CentralGameCore(root)
    floor_ids = sorted(core.world.floors, key=lambda value: int(value.removeprefix("floor")))
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for floor_id in floor_ids:
        try:
            pair = core.resolve_conversation_spot("standing_pair", floor_id)
            front = core.resolve_conversation_spot("ceo_front", floor_id)
            snapshot = core.resolve_conversation_snapshot(floor_id)
            employees = [
                actor for actor in snapshot["actors"].values()
                if actor["role"] == "employee"
            ]
            employees.sort(key=lambda actor: (actor["assignment_order"], actor["employee_id"]))
            pair_plan = core.resolve_conversation_plan(
                employees[0]["employee_id"],
                partner_id=employees[1]["employee_id"],
                mode="standing_pair",
                snapshot=snapshot,
            )
            ceo = next(actor for actor in snapshot["actors"].values() if actor["role"] == "ceo")
            ceo_plan = core.resolve_conversation_plan(
                employees[0]["employee_id"],
                partner_id=ceo["employee_id"],
                mode="ceo_front",
                snapshot=snapshot,
            )
            endpoint_pair = [tuple(cell) for cell in pair["endpoint_uv"]]
            inverse = pair.get("endpoint_inverse") is True
            if not pair.get("ready") or not inverse or not all(
                core.navigation_occupancy.is_walkable(floor_id, *cell)
                for cell in endpoint_pair
            ):
                raise AssertionError("standing pair is not ready/walkable/inverse")
            if not front.get("ready") or not ceo_plan.get("ready"):
                raise AssertionError("CEO front spot/plan is not ready")
            if ceo_plan["tracks"][ceo["employee_id"]][-1]["render_owner"] != "work_seat":
                raise AssertionError("CEO left the WorkSeat render channel")
            for plan in (pair_plan, ceo_plan):
                timing = plan.get("timing", {})
                if (
                    plan.get("loop_count") != 1
                    or timing.get("bubble_visible_ms") != 4000
                    or timing.get("speaker_gap_ms") != 500
                    or timing.get("bubble_fade_ms") != 300
                    or len(plan.get("speaker_schedule", [])) != 2
                ):
                    raise AssertionError("approved one-loop bubble timing is not active")
                start = int(plan["talk_start_ms"])
                by_time = {int(row["timestamp_ms"]): row for row in plan.get("timeline", [])}
                if sum(bool(actor.get("dialogue_visible")) for actor in by_time[start]["actors"].values()) != 1:
                    raise AssertionError("first speaker bubble did not start the talk window")
                if sum(bool(actor.get("dialogue_visible")) for actor in by_time[start + 500]["actors"].values()) != 2:
                    raise AssertionError("partner bubble did not follow after the short gap")
                if any(actor.get("dialogue_phase") != "fading" for actor in by_time[start + 4000]["actors"].values()):
                    raise AssertionError("both bubbles did not enter the shared fade")
                if any(actor.get("dialogue_visible") for actor in by_time[start + 4300]["actors"].values()):
                    raise AssertionError("bubble remained visible after fade completion")
            rows.append({
                "floor_id": floor_id,
                "standing_pair_ready": True,
                "standing_pair_axis": pair["axis"],
                "standing_pair_gap_cells": pair["gap_cells"],
                "standing_pair_candidate_count": pair.get("candidate_count"),
                "ceo_front_ready": True,
                "ceo_front_endpoint_uv": front["endpoint_uv"],
                "ceo_front_candidate_count": front.get("candidate_count"),
                "standing_plan_ready": pair_plan["ready"],
                "ceo_plan_ready": ceo_plan["ready"],
                "speaker_loop_count": pair_plan["loop_count"],
                "speaker_turn_count": len(pair_plan["speaker_schedule"]),
                "bubble_visible_ms": pair_plan["timing"]["bubble_visible_ms"],
                "speaker_gap_ms": pair_plan["timing"]["speaker_gap_ms"],
                "bubble_fade_ms": pair_plan["timing"]["bubble_fade_ms"],
            })
        except Exception as exc:
            errors.append({"floor_id": floor_id, "error": repr(exc)})
    result = {
        "schema": "gds.conversation_behavior_audit.v1",
        "status": "PASS" if not schema_errors and not errors else "FAIL",
        "pass": not schema_errors and not errors,
        "contract_schema_errors": schema_errors,
        "floor_count": len(floor_ids),
        "floor_rows": rows,
        "errors": errors,
        "policy": {
            "ceo_outbound_talk": contract["policy"]["ceo_outbound_talk"],
            "standing_pair_axis": contract["coordinate_contract"]["standing_pair"]["preferred_axis"],
            "talk_gap_cells": contract["coordinate_contract"]["standing_pair"]["talk_gap_cells"],
            "timing_policy": contract["timing"]["talk_duration_policy"],
        },
    }
    report = root / "LOCAL_REVIEW" / "PHASE8E_CONVERSATION_QA_20260901" / "CONVERSATION_BEHAVIOR_AUDIT.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result["report_json"] = str(report)
    return result


if __name__ == "__main__":
    result = audit()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["pass"] else 1)
