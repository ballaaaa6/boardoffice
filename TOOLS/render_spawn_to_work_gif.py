from __future__ import annotations

"""Render one end-to-end actor spawn -> WorkSeat -> return GIF.

The older Phase 8D preview intentionally emitted sparse keyframes.  This tool
keeps the real portal entry/exit lifecycle and samples the complete combined
timeline so a reviewer can see the actor appear, walk to a workstation, sit,
work, stand, walk back to the portal and disappear.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_OUTPUT = "PHASE8D_SPAWN_TO_WORK_QA_20260831"
DEFAULT_FLOOR = "floor00"
DEFAULT_WORKSTATION = "ws3"
DEFAULT_CHARACTER = 0
TICK_MS = 60
WALK_SAMPLE_STRIDE = 4
GIF_SPEED = 0.5


def _font() -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", 15)
    except OSError:
        return ImageFont.load_default()


def _with_alpha(image: Image.Image, alpha: float) -> Image.Image:
    if alpha >= 0.999:
        return image.convert("RGBA")
    rgba = image.convert("RGBA").copy()
    channel = rgba.getchannel("A").point(lambda value: int(value * max(0.0, min(1.0, alpha))))
    rgba.putalpha(channel)
    return rgba


def _label(image: Image.Image, text: str) -> Image.Image:
    output = image.convert("RGBA").copy()
    draw = ImageDraw.Draw(output)
    draw.rectangle((0, 0, output.width, 30), fill=(10, 14, 22, 232))
    draw.text((8, 7), text, fill=(245, 247, 250, 255), font=_font())
    return output


def _phase_indices(states: list[dict[str, Any]]) -> list[int]:
    """Keep portal transitions and work states, thin only long walking runs."""
    selected: set[int] = set()
    for index, state in enumerate(states):
        phase = state["phase"]
        phase_rows = [i for i, row in enumerate(states) if row["phase"] == phase]
        if not phase_rows:
            continue
        if phase in {"walking_to_seat", "walking_from_seat"}:
            if index == phase_rows[0] or index == phase_rows[-1] or index % WALK_SAMPLE_STRIDE == 0:
                selected.add(index)
        elif phase == "seated_work":
            selected.add(index)
        else:
            selected.add(index)
    return sorted(selected)


def _portal_prefix(portal_cycle: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        state
        for state in portal_cycle["states"]
        if state["phase"] in {"unspawned", "entering"}
    ]


def _portal_suffix(portal_cycle: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        state
        for state in portal_cycle["states"]
        if state["phase"] in {"active", "exiting", "despawned"}
    ]


def _combine_states(
    portal_cycle: dict[str, Any],
    work_cycle: dict[str, Any],
) -> list[dict[str, Any]]:
    """Join the portal lifecycle and WorkSeat lifecycle at the portal inside cell."""
    prefix = _portal_prefix(portal_cycle)
    suffix = _portal_suffix(portal_cycle)
    combined: list[dict[str, Any]] = []

    for index, state in enumerate(prefix):
        row = dict(state)
        row["timeline_timestamp_ms"] = index * TICK_MS
        combined.append(row)

    work_offset = combined[-1]["timeline_timestamp_ms"] + TICK_MS if combined else 0
    for state in work_cycle["states"]:
        row = dict(state)
        row["timeline_timestamp_ms"] = work_offset + int(state["timestamp_ms"])
        combined.append(row)

    suffix_offset = combined[-1]["timeline_timestamp_ms"] + TICK_MS if combined else 0
    for index, state in enumerate(suffix):
        row = dict(state)
        row["timeline_timestamp_ms"] = suffix_offset + index * TICK_MS
        combined.append(row)
    return combined


def _walking_frame_index(core, character_id: str, state: dict[str, Any]) -> int:
    action = state["action"]
    direction = state["direction"]
    result = core.characters.render(character_id, action, direction, None)
    if action != "move":
        return int(state.get("frame_index") or 0) % len(result.frames)
    if state.get("frame_index") is not None:
        return int(state["frame_index"]) % len(result.frames)
    profile = state.get("movement_profile") or {}
    return core.character_movement.walk_cycle_frame_index(
        float(state.get("cumulative_distance_px") or 0.0),
        len(result.frames),
        frame_distance_cells=float(profile.get("walk_frame_distance_cells", 0.65)),
    )


def _render_state(core, floor_id: str, workstation_id: str, character_id: str, state: dict[str, Any]) -> Image.Image:
    if state["phase"] == "seated_work":
        work = state["work_render"]
        return core.render_work_seat_lifecycle_state(
            floor_id,
            workstation_id,
            character_id,
            subaction=work["subaction"],
            effect_id=work.get("effect_id"),
            humanball_id=work.get("humanball_id"),
            character_frame_index=work["character_frame_index"],
            effect_frame_index=work.get("effect_frame_index"),
            humanball_frame_index=work.get("humanball_frame_index"),
        )

    base = core.render_floor(floor_id).convert("RGBA")
    if not state.get("visible", True):
        return base
    action = state["action"]
    direction = state["direction"]
    character = core.characters.render(character_id, action, direction, None)
    frame = character.frames[_walking_frame_index(core, character_id, state)].convert("RGBA")
    frame = _with_alpha(frame, float(state.get("alpha", 1.0)))
    ground = state.get("ground_xy")
    if ground is None:
        ground = core.character_movement.uv_cell_center_to_pixel(*state["transition_gate_uv"])
    return core.walking_depth.composite_character(
        floor_id,
        frame,
        tuple(ground),
        ground_anchor_px=tuple(core.character_movement.GROUND_ANCHOR_PX),
    )


def render(
    root: str | Path,
    output: str | Path | None = None,
    *,
    floor_id: str = DEFAULT_FLOOR,
    workstation_id: str = DEFAULT_WORKSTATION,
    character_query: int | str = DEFAULT_CHARACTER,
) -> dict[str, Any]:
    from RUNTIME.central_core import CentralGameCore

    root = Path(root).resolve()
    output_root = Path(output).resolve() if output else root / "LOCAL_REVIEW" / DEFAULT_OUTPUT
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    core = CentralGameCore(root)
    character_id = core.resolve_character_id(character_query)
    inside_uv = tuple(core.resolve_portal_navigation_start(floor_id))
    portal_cycle = core.resolve_portal_actor_cycle(character_id, floor_id, inside_uv)
    work_cycle = core.resolve_work_seat_actor_cycle(
        character_id,
        floor_id,
        workstation_id,
        inside_uv,
        exit_goal_uv=inside_uv,
        work_ticks=24,
        effect_id="thunder_cloud",
        humanball_id="coin",
    )
    states = _combine_states(portal_cycle, work_cycle)
    indices = _phase_indices(states)
    frames: list[Image.Image] = []
    durations: list[int] = []
    for ordinal, state_index in enumerate(indices):
        state = states[state_index]
        image = _render_state(core, floor_id, workstation_id, character_id, state)
        image = _label(
            image,
            f"{floor_id}.{workstation_id}  {character_id}  {state['phase']}  "
            f"t={state['timeline_timestamp_ms']}ms  speed={state.get('speed_percent', work_cycle['movement_profile']['speed_percent'])}%",
        )
        frames.append(image)
        if ordinal + 1 < len(indices):
            next_state = states[indices[ordinal + 1]]
            delta = int(next_state["timeline_timestamp_ms"]) - int(state["timeline_timestamp_ms"])
        else:
            delta = TICK_MS
        durations.append(max(60, int(round(delta * GIF_SPEED))))

    gif_path = output_root / f"{floor_id}_{workstation_id}_{character_id}_spawn_to_work.gif"
    paletted = [frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=255) for frame in frames]
    paletted[0].save(
        gif_path,
        save_all=True,
        append_images=paletted[1:],
        duration=durations,
        loop=0,
        disposal=2,
    )

    phase_counts: dict[str, int] = {}
    for state in states:
        phase_counts[state["phase"]] = phase_counts.get(state["phase"], 0) + 1
    report = {
        "schema": "gds.phase8d.spawn_to_work_visual_qa.v1",
        "status": "PASS",
        "pass": bool(
            states
            and states[0]["phase"] == "unspawned"
            and states[-1]["phase"] == "despawned"
            and work_cycle["final_slot_state"] == "free"
            and work_cycle["phase_counts"].get("seated_work") == 24
        ),
        "floor_id": floor_id,
        "workstation_id": workstation_id,
        "character_id": character_id,
        "start_uv": list(inside_uv),
        "phase_counts": phase_counts,
        "rendered_frame_count": len(frames),
        "gif": str(gif_path.relative_to(root)),
        "source_cycles": {
            "portal_schema": portal_cycle["schema"],
            "work_seat_schema": work_cycle["schema"],
            "work_duration_ms": work_cycle["timing"]["work_duration_ms"],
            "slot_transition_history": work_cycle["slot_transition_history"],
            "final_slot_state": work_cycle["final_slot_state"],
        },
        "sampling": {
            "walk_sample_stride": WALK_SAMPLE_STRIDE,
            "gif_speed_multiplier": GIF_SPEED,
            "tick_ms": TICK_MS,
        },
        "acceptance": "visual_author_acceptance_pending",
    }
    (output_root / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--core-root", default=str(ROOT))
    parser.add_argument("--output", default=None)
    parser.add_argument("--floor", default=DEFAULT_FLOOR)
    parser.add_argument("--workstation", default=DEFAULT_WORKSTATION)
    parser.add_argument("--character", default=str(DEFAULT_CHARACTER))
    args = parser.parse_args()
    try:
        character: int | str = int(args.character)
    except ValueError:
        character = args.character
    report = render(
        args.core_root,
        args.output,
        floor_id=args.floor,
        workstation_id=args.workstation,
        character_query=character,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
