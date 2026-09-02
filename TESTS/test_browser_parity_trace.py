from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


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
