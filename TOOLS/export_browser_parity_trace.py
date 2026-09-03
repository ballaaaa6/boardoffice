from __future__ import annotations

"""Export deterministic Python oracle traces for the browser runtime port."""

import argparse
import copy
from pathlib import Path
from typing import Any

try:
    from TOOLS._bootstrap import ensure_project_root
except ModuleNotFoundError:
    from _bootstrap import ensure_project_root

PROJECT_ROOT = ensure_project_root(__file__)

from RUNTIME.browser_bundle_contract import TRACE_SCHEMA, VERSION, canonical_json, validate_trace
from RUNTIME.central_core import CentralGameCore
from RUNTIME.runtime_render_state import RuntimeRenderStateProjector


DEFAULT_FLOOR_ID = "floor02"
DEFAULT_SCENARIO = "spawn_work"
DEFAULT_SEED = "gds-browser-runtime-v1"
STEP_MS = 60


class BrowserParityTraceError(ValueError):
    """Raised when an oracle trace cannot be produced."""


def _silence_unrelated_speech(runtime: dict[str, Any]) -> None:
    """Keep scenario checkpoints focused on the requested actor behavior."""
    for actor in runtime["speech_snapshot"]["actors"].values():
        actor.update({
            "greeting_due_ms": 999999,
            "greeting_emitted": True,
            "work_start_due_ms": 999999,
            "work_start_emitted": True,
            "solo_next_due_ms": 999999,
            "pair_next_due_ms": 999999,
            "solo_pending": False,
            "pair_pending": False,
        })


def _browser_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Encode persisted uint64 PRNG state without lossy JSON Numbers."""
    result = copy.deepcopy(snapshot)
    determinism = result.get("speech_snapshot", {}).get("determinism", {})
    state = determinism.get("emotion_rng_state")
    if isinstance(state, int) and not isinstance(state, bool):
        determinism["emotion_rng_state"] = str(state)
    return result


def _prepare_scenario_runtime(
    runtime: dict[str, Any],
    *,
    scenario: str,
) -> dict[str, Any]:
    """Return a valid deterministic initial state for a focused checkpoint."""
    current = copy.deepcopy(runtime)
    if scenario == "talk_pair":
        keep = {"EMP_W1_0010", "EMP_W1_0011"}
        _silence_unrelated_speech(current)
        for employee_id, actor in current["actor_snapshot"]["actors"].items():
            if employee_id in keep:
                continue
            actor["presence"] = "home"
            actor["activity"] = "home_recovery"
            actor["position"] = {
                "floor_id": None,
                "uv": None,
                "ground_xy": None,
                "route": None,
            }
            actor["behavior"]["activity_until_ms"] = 999999
            actor["behavior"]["next_event_due_ms"] = None
            actor["last_event"] = "home_recovered"
            speech_actor = current["speech_snapshot"]["actors"][employee_id]
            speech_actor["last_activity"] = "home_recovery"
            speech_actor["stamina_band"] = "normal"
            conversation_actor = current["conversation_snapshot"]["actors"][employee_id]
            conversation_actor["presence"] = "home"
            conversation_actor["phase"] = "working"
            conversation_actor["locked"] = False
        for employee_id in keep:
            current["conversation_snapshot"]["actors"][employee_id]["phase"] = "working"
            current["conversation_snapshot"]["actors"][employee_id]["locked"] = False
        return current

    if scenario == "effects_humanball":
        _silence_unrelated_speech(current)
        actor = current["actor_snapshot"]["actors"]["EMP_W1_0031"]
        actor["behavior"].update({
            "event_counter": 1,
            "active_event": "popup",
            "activity_started_ms": 0,
            "activity_until_ms": 600,
            "next_event_due_ms": None,
        })
        actor["activity"] = "popup_event"
        actor["last_event"] = "work_tick"
        current["speech_snapshot"]["actors"]["EMP_W1_0031"]["last_activity"] = "popup_event"
        return current

    if scenario == "critical_home":
        _silence_unrelated_speech(current)
        actor = current["actor_snapshot"]["actors"]["EMP_W1_0010"]
        actor["stamina"].update({
            "current_milli": 10000,
            "threshold_band": "critical",
            "drain_remainder": 0,
        })
        actor["behavior"].update({
            "work_loop_elapsed_ms": 660,
            "next_event_due_ms": 999999,
        })
        actor["last_event"] = "work_tick"
        current["speech_snapshot"]["actors"]["EMP_W1_0010"]["stamina_band"] = "critical"
        return current

    return current


def _scenario_steps(scenario: str) -> list[dict[str, Any]]:
    if scenario == "spawn_work":
        return [
            {"elapsed_ms": STEP_MS, "actor_commands": [], "speech_commands": []}
            for _ in range(20)
        ]
    if scenario == "talk_pair":
        # Isolate one deterministic pair so this checkpoint exercises the
        # browser speech scheduler and committed talk routes without unrelated
        # automatic office chatter winning the checkpoint.
        # Stop immediately after the shared emotion hold starts the authored
        # return boundary.  A later idle checkpoint would intentionally allow
        # the general lifecycle scheduler to open another session, which is a
        # separate parity concern from this focused routed-talk checkpoint.
        durations = (60, 900, 13200, 4320, 1200)
        steps = []
        first = True
        for duration in durations:
            remaining = int(duration)
            while remaining > 0:
                elapsed_ms = min(960, remaining)
                # The browser clock deliberately consumes only bounded,
                # 60ms-aligned slices.  Keep each oracle checkpoint on that
                # same grid so the trace tests the reducers, not host
                # catch-up policy.
                if elapsed_ms % STEP_MS:
                    elapsed_ms -= elapsed_ms % STEP_MS
                if elapsed_ms <= 0:
                    raise BrowserParityTraceError(
                        f"scenario duration is not aligned to {STEP_MS}ms: {duration}"
                    )
                steps.append({
                    "elapsed_ms": elapsed_ms,
                    "actor_commands": [],
                    "speech_commands": (
                        [{
                            "type": "behavior_started",
                            "employee_id": "EMP_W1_0010",
                            "behavior": "talk",
                            "effective_at_ms": 0,
                        }]
                        if first else []
                    ),
                })
                first = False
                remaining -= elapsed_ms
        return steps
    if scenario == "effects_humanball":
        return [
            {"elapsed_ms": elapsed_ms, "actor_commands": [], "speech_commands": []}
            for elapsed_ms in (60, 240, 300, 60)
        ]
    if scenario == "critical_home":
        steps = []
        for duration in (60, 14160, 240):
            remaining = int(duration)
            while remaining > 0:
                elapsed_ms = min(960, remaining)
                steps.append({"elapsed_ms": elapsed_ms, "actor_commands": [], "speech_commands": []})
                remaining -= elapsed_ms
        return steps
    if scenario == "save_load_replay":
        return [
            {"elapsed_ms": STEP_MS, "actor_commands": [], "speech_commands": []}
            for _ in range(4)
        ]
    raise BrowserParityTraceError(f"unsupported parity scenario: {scenario}")


def export_trace(
    root: str | Path,
    floor_id: str = DEFAULT_FLOOR_ID,
    *,
    scenario: str = DEFAULT_SCENARIO,
    seed: str = DEFAULT_SEED,
) -> dict[str, Any]:
    """Produce a JSON-safe Python trace with render-state checkpoints."""
    if not isinstance(seed, str) or not seed:
        raise BrowserParityTraceError("seed must be non-empty text")
    project_root = Path(root).resolve()
    core = CentralGameCore(project_root)
    runtime = core.resolve_runtime_snapshot(floor_id, simulation_seed=seed)
    projector = RuntimeRenderStateProjector(core)
    runtime = _prepare_scenario_runtime(runtime, scenario=scenario)
    if scenario == "effects_humanball":
        # The scenario injects an already-admitted popup so the parity check
        # starts at a stable frame.  Seed the same persistent visual binding
        # the live actor reducer would create at behavior admission; renderers
        # must never infer the asset from the event name alone.
        actor = runtime["actor_snapshot"]["actors"]["EMP_W1_0031"]
        behavior = actor["behavior"]
        visual_state, _binding = core.actor_simulation.visual_selection.select(
            behavior["visual_channels"]["humanball"],
            channel="humanball",
            simulation_seed=runtime["actor_snapshot"]["determinism"]["simulation_seed"],
            employee_id=actor["employee_id"],
            event_id="visual:EMP_W1_0031:popup:1:0",
            started_at_ms=int(behavior["activity_started_ms"]),
            ends_at_ms=int(behavior["activity_until_ms"]),
        )
        behavior["visual_channels"]["humanball"] = visual_state
    # The snapshot was constructed by Central and is validated once here.
    # Subsequent checkpoints use the trusted in-place path; this keeps a long
    # route trace cheap without changing the reducer's fixed 60ms semantics.
    core.validate_runtime_snapshot(runtime)
    initial_snapshot = _browser_snapshot(runtime)
    steps: list[dict[str, Any]] = []
    sequence = 0
    for command in _scenario_steps(scenario):
        runtime = core.advance_runtime_snapshot(
            runtime,
            int(command["elapsed_ms"]),
            actor_commands=command["actor_commands"],
            speech_commands=command["speech_commands"],
            dialogue_seed=seed,
            validate=False,
        )
        sequence += 1
        presentation = core.resolve_runtime_presentation(
            runtime,
            floor_id=floor_id,
        )
        render_state = projector.project(
            runtime,
            floor_id=floor_id,
            sequence=sequence,
            events=(),
            presentation=presentation,
        )
        steps.append({
            "elapsed_ms": int(command["elapsed_ms"]),
            "actor_commands": copy.deepcopy(command["actor_commands"]),
            "speech_commands": copy.deepcopy(command["speech_commands"]),
            "python_snapshot": _browser_snapshot(runtime),
            "python_render_state": render_state,
            "events": [],
        })
    trace = {
        "schema": TRACE_SCHEMA,
        "version": VERSION,
        "floor_id": floor_id,
        "scenario": scenario,
        "seed": seed,
        "initial_snapshot": initial_snapshot,
        "steps": steps,
    }
    return validate_trace(trace)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(PROJECT_ROOT))
    parser.add_argument("--floor-id", default=DEFAULT_FLOOR_ID)
    parser.add_argument("--scenario", default=DEFAULT_SCENARIO)
    parser.add_argument("--seed", default=DEFAULT_SEED)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    trace = export_trace(
        args.root,
        args.floor_id,
        scenario=args.scenario,
        seed=args.seed,
    )
    serialized = canonical_json(trace) + "\n"
    if args.output:
        Path(args.output).resolve().write_text(serialized, encoding="utf-8", newline="\n")
    else:
        print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
