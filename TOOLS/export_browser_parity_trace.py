from __future__ import annotations

"""Export deterministic Python oracle traces for the browser runtime port."""

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from RUNTIME.browser_bundle_contract import TRACE_SCHEMA, VERSION, canonical_json, validate_trace
from RUNTIME.central_core import CentralGameCore
from RUNTIME.runtime_render_state import RuntimeRenderStateProjector


DEFAULT_FLOOR_ID = "floor02"
DEFAULT_SCENARIO = "spawn_work"
DEFAULT_SEED = "gds-browser-runtime-v1"
STEP_MS = 60


class BrowserParityTraceError(ValueError):
    """Raised when an oracle trace cannot be produced."""


def _scenario_steps(scenario: str) -> list[dict[str, Any]]:
    if scenario == "spawn_work":
        return [
            {"elapsed_ms": STEP_MS, "actor_commands": [], "speech_commands": []}
            for _ in range(20)
        ]
    if scenario in {"talk_pair", "effects_humanball", "critical_home", "save_load_replay"}:
        # Task 1 freezes the trace vocabulary for every later scenario.  The
        # behavior-specific command vectors are added with their owning port
        # tasks, while this baseline remains a valid quiet deterministic trace.
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
    initial_snapshot = copy.deepcopy(runtime)
    steps: list[dict[str, Any]] = []
    sequence = 0
    for command in _scenario_steps(scenario):
        runtime = core.advance_runtime_snapshot(
            runtime,
            int(command["elapsed_ms"]),
            actor_commands=command["actor_commands"],
            speech_commands=command["speech_commands"],
            dialogue_seed=seed,
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
            "python_snapshot": copy.deepcopy(runtime),
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
