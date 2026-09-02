from __future__ import annotations

import json
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
