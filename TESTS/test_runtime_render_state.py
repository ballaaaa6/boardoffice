from __future__ import annotations

import json
from pathlib import Path

import pytest

from RUNTIME.central_core import CentralGameCore
from RUNTIME.runtime_presentation_renderer import RuntimePresentationLoop


ROOT = Path(__file__).resolve().parents[1]


def _quiet_runtime(core: CentralGameCore) -> dict:
    runtime = core.resolve_runtime_snapshot("floor02")
    for actor in runtime["speech_snapshot"]["actors"].values():
        actor.update({
            "greeting_due_ms": None,
            "greeting_emitted": True,
            "work_start_due_ms": None,
            "work_start_emitted": True,
            "solo_next_due_ms": None,
            "pair_next_due_ms": None,
        })
    for actor in runtime["actor_snapshot"]["actors"].values():
        actor["behavior"]["next_event_due_ms"] = 10**9
    return runtime


def test_runtime_frame_count_does_not_materialize_character_image(monkeypatch):
    core = CentralGameCore(ROOT)
    calls = []

    def record_render(*args, **kwargs):
        calls.append((args, kwargs))
        return type("RenderResult", (), {"frames": [object(), object()]})()

    monkeypatch.setattr(core.characters, "render", record_render)
    count = core._runtime_frame_count(
        {"character_id": "TP_009"},
        action="work",
        direction="SE",
        subaction="normal_work",
    )

    assert count == 2
    assert calls == []


def test_headless_loop_returns_no_image_and_advances_snapshot():
    core = CentralGameCore(ROOT)
    runtime = _quiet_runtime(core)
    try:
        loop = RuntimePresentationLoop(
            core,
            runtime_snapshot=runtime,
            floor_id="floor02",
            render_mode="headless",
        )
    except TypeError as exc:
        pytest.fail(f"headless render mode is not available: {exc}")

    initial = loop.render_current()
    assert initial["image"] is None
    frame = loop.tick(60)
    assert frame["image"] is None
    assert frame["runtime_snapshot"]["actor_snapshot"]["clock"]["simulation_time_ms"] == 60


def test_projector_emits_small_json_state_without_runtime_or_image_fields(monkeypatch):
    try:
        from RUNTIME.runtime_render_state import RuntimeRenderStateProjector
    except ModuleNotFoundError as exc:
        pytest.fail(f"metadata-only projector is not available: {exc}")

    core = CentralGameCore(ROOT)
    runtime = _quiet_runtime(core)
    monkeypatch.setattr(
        core.characters,
        "render",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("image render")),
    )

    state = RuntimeRenderStateProjector(core).project(runtime, floor_id="floor02")

    assert state["schema"] == "gds.runtime_render_state.v1"
    assert state["floor_id"] == "floor02"
    assert "image" not in state
    assert "image_data_url" not in state
    assert "runtime_snapshot" not in state
    assert all("runtime_snapshot" not in actor for actor in state["actors"])
    json.dumps(state, ensure_ascii=False, sort_keys=True)
    assert len(json.dumps(state, ensure_ascii=False, separators=(",", ":"))) < 20_000
