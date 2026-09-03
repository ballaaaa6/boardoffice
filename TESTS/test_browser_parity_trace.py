from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _run_browser_trace(trace, bundle):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser runtime checkpoint")
    completed = subprocess.run(
        [node, "TESTS/browser_runtime_parity_runner.mjs"],
        cwd=ROOT,
        check=True,
        input=json.dumps({"bundle": bundle, "trace": trace}, separators=(",", ":")),
        text=True,
        capture_output=True,
    )
    return json.loads(completed.stdout)


def _api():
    try:
        from TOOLS.export_browser_parity_trace import export_trace
        from RUNTIME.browser_bundle_contract import TraceContractError, validate_trace
    except ModuleNotFoundError as exc:
        pytest.fail(f"browser parity trace exporter is not available: {exc}")
    return export_trace, TraceContractError, validate_trace


def test_spawn_work_trace_contains_python_snapshot_and_render_oracle():
    export_trace, _TraceContractError, validate_trace = _api()
    trace = export_trace(ROOT, "floor02", scenario="spawn_work", seed="browser-test-seed")

    assert validate_trace(trace)["schema"] == "gds.browser_runtime_parity_trace.v1"
    assert trace["floor_id"] == "floor02"
    assert trace["seed"] == "browser-test-seed"
    assert trace["initial_snapshot"]["schema"] == "gds.runtime_snapshot.v1"
    assert trace["steps"]
    assert all(step["elapsed_ms"] == 60 for step in trace["steps"])
    assert all(step["python_snapshot"]["schema"] == "gds.runtime_snapshot.v1" for step in trace["steps"])
    assert all(
        step["python_render_state"]["schema"] == "gds.runtime_render_state.v1"
        for step in trace["steps"]
    )
    assert all("image_data_url" not in step["python_render_state"] for step in trace["steps"])
    json.dumps(trace, ensure_ascii=False, separators=(",", ":"))


def test_parity_trace_rejects_unsupported_schema():
    _export_trace, TraceContractError, validate_trace = _api()
    broken = {
        "schema": "not-a-trace",
        "version": "1.0.0",
        "floor_id": "floor02",
        "seed": "seed",
        "initial_snapshot": {},
        "steps": [],
    }

    with pytest.raises(TraceContractError, match="unsupported schema"):
        validate_trace(broken)


def test_node_parity_runner_returns_image_free_shell_checkpoints():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser runtime checkpoint")
    from RUNTIME.browser_bundle_contract import validate_bundle
    from TOOLS.build_runtime_simulation_bundle import build_bundle

    bundle = build_bundle(ROOT, "floor02")
    validate_bundle(bundle, root=ROOT, expected_floor_id="floor02")
    trace = {
        "floor_id": "floor02",
        "seed": "browser-test-seed",
        "steps": [
            {
                "elapsed_ms": 60,
                "actor_commands": [],
                "speech_commands": [],
            }
        ],
    }
    completed = subprocess.run(
        [node, "TESTS/browser_runtime_parity_runner.mjs"],
        cwd=ROOT,
        check=True,
        input=json.dumps({"bundle": bundle, "trace": trace}, separators=(",", ":")),
        text=True,
        capture_output=True,
    )
    result = json.loads(completed.stdout)

    assert result["schema"] == "gds.browser_runtime_parity_result.v1"
    assert result["floor_id"] == "floor02"
    assert len(result["steps"]) == 1
    checkpoint = result["steps"][0]
    assert checkpoint["snapshot"]["schema"] == "gds.runtime_snapshot.v1"
    assert checkpoint["snapshot"]["actor_snapshot"]["clock"]["simulation_time_ms"] == 60
    assert checkpoint["render_state"]["schema"] == "gds.runtime_render_state.v1"
    assert "image_data_url" not in checkpoint["render_state"]


def test_node_actor_and_workseat_fields_match_spawn_work_oracle():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser runtime checkpoint")
    from RUNTIME.browser_bundle_contract import validate_bundle
    from TOOLS.build_runtime_simulation_bundle import build_bundle
    from TOOLS.export_browser_parity_trace import export_trace

    bundle = build_bundle(ROOT, "floor02")
    validate_bundle(bundle, root=ROOT, expected_floor_id="floor02")
    trace = export_trace(ROOT, "floor02", scenario="spawn_work", seed="browser-test-seed")
    completed = subprocess.run(
        [node, "TESTS/browser_runtime_parity_runner.mjs"],
        cwd=ROOT,
        check=True,
        input=json.dumps({"bundle": bundle, "trace": trace}, separators=(",", ":")),
        text=True,
        capture_output=True,
    )
    result = json.loads(completed.stdout)

    render_fields = (
        "action",
        "activity",
        "direction",
        "subaction",
        "resolved_action",
        "resolved_direction",
        "resolved_subaction",
        "render_owner",
        "workstation_id",
        "assignment_order",
        "ground_xy",
        "route_phase",
        "route_elapsed_ms",
        "route_duration_ms",
        "cumulative_distance_px",
        "frame_id",
        "frame_index",
        "character_frame_index",
        "character_frame_count",
        "pc_frame_index",
        "pc_frame_count",
        "animation_clock_ms",
        "stamina",
    )
    assert len(result["steps"]) == len(trace["steps"])
    for expected_step, actual_step in zip(trace["steps"], result["steps"], strict=True):
        assert actual_step["events"] == expected_step["events"]
        expected_actors = expected_step["python_snapshot"]["actor_snapshot"]["actors"]
        actual_actors = actual_step["snapshot"]["actor_snapshot"]["actors"]
        assert sorted(actual_actors) == sorted(expected_actors)
        for employee_id in expected_actors:
            assert actual_actors[employee_id] == expected_actors[employee_id]

        expected_rows = {
            row["employee_id"]: row for row in expected_step["python_render_state"]["actors"]
        }
        actual_rows = {row["employee_id"]: row for row in actual_step["render_state"]["actors"]}
        assert sorted(actual_rows) == sorted(expected_rows)
        for employee_id in expected_rows:
            assert {field: actual_rows[employee_id].get(field) for field in render_fields} == {
                field: expected_rows[employee_id].get(field) for field in render_fields
            }


def test_node_home_route_boundary_matches_python_actor_and_render_oracle():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser runtime checkpoint")
    from RUNTIME.central_core import CentralGameCore
    from RUNTIME.runtime_render_state import RuntimeRenderStateProjector
    from RUNTIME.browser_bundle_contract import validate_bundle
    from TOOLS.build_runtime_simulation_bundle import build_bundle

    employee_id = "EMP_W1_0010"
    core = CentralGameCore(ROOT)
    runtime = core.resolve_runtime_snapshot("floor02", simulation_seed="browser-test-seed")
    advanced = core.advance_runtime_snapshot(
        runtime,
        60,
        actor_commands=[{"type": "request_home", "employee_id": employee_id}],
        dialogue_seed="browser-test-seed",
    )
    presentation = core.resolve_runtime_presentation(advanced, floor_id="floor02")
    expected_render = RuntimeRenderStateProjector(core).project(
        advanced,
        floor_id="floor02",
        sequence=1,
        events=(),
        presentation=presentation,
    )
    bundle = build_bundle(ROOT, "floor02")
    validate_bundle(bundle, root=ROOT, expected_floor_id="floor02")
    trace = {
        "floor_id": "floor02",
        "seed": "browser-test-seed",
        "steps": [{
            "elapsed_ms": 60,
            "actor_commands": [{"type": "request_home", "employee_id": employee_id}],
            "speech_commands": [],
        }],
    }
    completed = subprocess.run(
        [node, "TESTS/browser_runtime_parity_runner.mjs"],
        cwd=ROOT,
        check=True,
        input=json.dumps({"bundle": bundle, "trace": trace}, separators=(",", ":")),
        text=True,
        capture_output=True,
    )
    actual = json.loads(completed.stdout)["steps"][0]
    assert actual["snapshot"]["actor_snapshot"]["actors"] == advanced["actor_snapshot"]["actors"]
    expected_row = next(row for row in expected_render["actors"] if row["employee_id"] == employee_id)
    actual_row = next(row for row in actual["render_state"]["actors"] if row["employee_id"] == employee_id)
    for field in (
        "action",
        "direction",
        "subaction",
        "resolved_action",
        "resolved_direction",
        "resolved_subaction",
        "render_owner",
        "ground_xy",
        "route_phase",
        "route_elapsed_ms",
        "route_duration_ms",
        "cumulative_distance_px",
        "frame_id",
        "frame_index",
        "character_frame_index",
        "character_frame_count",
        "animation_clock_ms",
        "workstation_id",
    ):
        assert actual_row.get(field) == expected_row.get(field), field


def test_talk_pair_browser_checkpoint_matches_speech_route_and_bubbles():
    from RUNTIME.browser_bundle_contract import validate_bundle
    from TOOLS.build_runtime_simulation_bundle import build_bundle
    from TOOLS.export_browser_parity_trace import export_trace

    bundle = build_bundle(ROOT, "floor02")
    validate_bundle(bundle, root=ROOT, expected_floor_id="floor02")
    trace = export_trace(ROOT, "floor02", scenario="talk_pair", seed="browser-test-seed")
    result = _run_browser_trace(trace, bundle)

    assert any(
        step["python_snapshot"]["speech_snapshot"]["active_sessions"]
        for step in trace["steps"]
    )
    assert any(
        step["snapshot"]["speech_snapshot"]["active_sessions"]
        for step in result["steps"]
    )
    for expected_step, actual_step in zip(trace["steps"], result["steps"], strict=True):
        expected_actors = expected_step["python_snapshot"]["actor_snapshot"]["actors"]
        actual_actors = actual_step["snapshot"]["actor_snapshot"]["actors"]
        for employee_id in ("EMP_W1_0010", "EMP_W1_0011"):
            assert actual_actors[employee_id] == expected_actors[employee_id]
        expected_speech = expected_step["python_snapshot"]["speech_snapshot"]
        actual_speech = actual_step["snapshot"]["speech_snapshot"]
        assert set(actual_speech["active_sessions"]) == set(expected_speech["active_sessions"])
        for employee_id in ("EMP_W1_0010", "EMP_W1_0011"):
            for field in (
                "speech_phase",
                "emotion",
                "emotion_until_ms",
                "last_session_id",
                "last_partner_id",
                "speech_event_counter",
            ):
                assert actual_speech["actors"][employee_id].get(field) == expected_speech["actors"][employee_id].get(field), (
                    employee_id,
                    field,
                )
        for session_id, expected_session in expected_speech["active_sessions"].items():
            actual_session = actual_speech["active_sessions"][session_id]
            for field in (
                "mode",
                "category",
                "participants",
                "movement_started_ms",
                "movement_arrival_ms",
                "bubble_start_ms",
                "bubble_visible_end_ms",
                "fade_end_ms",
                "emotion_roll",
                "emotion_outcome",
                "emotion_hold_ms",
            ):
                assert actual_session.get(field) == expected_session.get(field), (session_id, field)
            assert actual_session["bubble_schedule"] == expected_session["bubble_schedule"]
        expected_rows = {
            row["employee_id"]: row for row in expected_step["python_render_state"]["actors"]
        }
        actual_rows = {
            row["employee_id"]: row for row in actual_step["render_state"]["actors"]
        }
        for employee_id in ("EMP_W1_0010", "EMP_W1_0011"):
            for field in (
                "activity",
                "presence",
                "action",
                "direction",
                "subaction",
                "ground_xy",
                "route_phase",
                "route_elapsed_ms",
                "route_duration_ms",
                "speech_session_id",
                "speech_mode",
                "speech_category",
            ):
                assert actual_rows[employee_id].get(field) == expected_rows[employee_id].get(field), (
                    employee_id,
                    field,
                )
            assert actual_rows[employee_id]["dialogue"] == expected_rows[employee_id]["dialogue"]


def test_effects_humanball_browser_checkpoint_keeps_effect_channel_metadata_only():
    from RUNTIME.browser_bundle_contract import validate_bundle
    from TOOLS.build_runtime_simulation_bundle import build_bundle
    from TOOLS.export_browser_parity_trace import export_trace

    bundle = build_bundle(ROOT, "floor02")
    validate_bundle(bundle, root=ROOT, expected_floor_id="floor02")
    trace = export_trace(ROOT, "floor02", scenario="effects_humanball", seed="browser-test-seed")
    result = _run_browser_trace(trace, bundle)

    expected_step = trace["steps"][0]
    actual_step = result["steps"][0]
    expected_actor = expected_step["python_snapshot"]["actor_snapshot"]["actors"]["EMP_W1_0031"]
    actual_actor = actual_step["snapshot"]["actor_snapshot"]["actors"]["EMP_W1_0031"]
    assert actual_actor == expected_actor
    expected_row = next(
        row for row in expected_step["python_render_state"]["actors"]
        if row["employee_id"] == "EMP_W1_0031"
    )
    actual_row = next(
        row for row in actual_step["render_state"]["actors"]
        if row["employee_id"] == "EMP_W1_0031"
    )
    assert actual_row["channels"] == expected_row["channels"]
    assert actual_row["channels"]["humanball"]["asset_id"] == expected_row["channels"]["humanball"]["asset_id"]
    assert actual_row["channels"]["humanball"]["asset_id"] in bundle["visual_catalog"]["humanball"]["ids"]
    assert "image_data_url" not in actual_step["render_state"]


def test_critical_home_browser_checkpoint_queues_then_enters_portal_route():
    from RUNTIME.browser_bundle_contract import validate_bundle
    from TOOLS.build_runtime_simulation_bundle import build_bundle
    from TOOLS.export_browser_parity_trace import export_trace

    bundle = build_bundle(ROOT, "floor02")
    validate_bundle(bundle, root=ROOT, expected_floor_id="floor02")
    trace = export_trace(ROOT, "floor02", scenario="critical_home", seed="browser-test-seed")
    result = _run_browser_trace(trace, bundle)

    expected_steps = trace["steps"]
    actual_steps = result["steps"]
    assert len(expected_steps) == len(actual_steps)
    for expected_step, actual_step in zip(expected_steps, actual_steps, strict=True):
        expected_actor = expected_step["python_snapshot"]["actor_snapshot"]["actors"]["EMP_W1_0010"]
        actual_actor = actual_step["snapshot"]["actor_snapshot"]["actors"]["EMP_W1_0010"]
        assert actual_actor == expected_actor
    final_actor = actual_steps[-1]["snapshot"]["actor_snapshot"]["actors"]["EMP_W1_0010"]
    assert final_actor["presence"] in {"leaving", "home"}
    assert any(
        event.get("type") == "home_queued"
        for step in actual_steps
        for event in step["events"]
    )
