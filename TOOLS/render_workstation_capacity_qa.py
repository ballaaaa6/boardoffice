from __future__ import annotations

"""Render one deterministic actor per authored workstation on five floors.

This is a visual QA tool for the Phase 8D single-actor lifecycle.  It does
not use the full character roster and it does not invent a queue: each actor
gets one distinct workstation/interaction slot, so the actor count is exactly
the number of authored computers on that floor.
"""

import argparse
import json
import sys
from bisect import bisect_right
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_OUTPUT = "PHASE8D_WORKSTATION_CAPACITY_QA_20260831"
CASES = (
    ("F0", "floor00"),
    ("F1", "floor01"),
    ("F2", "floor02"),
    ("F14", "floor14"),
    ("F17", "floor17"),
)
TICK_MS = 60
FRAME_STEP_MS = 120
WORK_TICKS = 24
WORK_DURATION_MS = WORK_TICKS * TICK_MS
CHARACTER_FRAME_MS = 360
EFFECT_FRAME_MS = 240
IMPORTANT_COLORS = (
    (255, 92, 92, 220),
    (85, 220, 255, 220),
    (255, 200, 90, 220),
    (189, 137, 255, 220),
    (92, 255, 170, 220),
    (255, 115, 196, 220),
    (212, 255, 119, 220),
    (125, 167, 255, 220),
    (255, 155, 80, 220),
)


def _font(size: int = 15) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _label(image: Image.Image, text: str) -> Image.Image:
    output = image.convert("RGBA").copy()
    draw = ImageDraw.Draw(output)
    draw.rectangle((0, 0, output.width, 30), fill=(10, 14, 22, 232))
    draw.text((8, 7), text, fill=(245, 247, 250, 255), font=_font())
    return output


def _workstation_sort_key(workstation_id: str) -> tuple[int, int, str]:
    if workstation_id == "ceo":
        return (0, 0, workstation_id)
    if workstation_id.startswith("ws"):
        try:
            return (1, int(workstation_id[2:]), workstation_id)
        except ValueError:
            pass
    return (2, 0, workstation_id)


def workstation_ids(core: Any, floor_id: str) -> list[str]:
    """Return computers, not arbitrary furniture, in deterministic order."""
    groups = core.world.floor_layout(floor_id).get("workstation_groups", {})
    result = []
    for workstation_id, group in groups.items():
        if group.get("group_type") != "workstation":
            continue
        if group.get("component_slots", {}).get("pc") is None:
            continue
        result.append(str(workstation_id))
    return sorted(result, key=_workstation_sort_key)


def portal_starts(core: Any, floor_id: str, count: int) -> list[tuple[int, int]]:
    """Choose distinct walkable portal-inside cells for the floor's actors."""
    inside_cells = sorted(
        {tuple(cell) for cell in core.resolve_portal(floor_id)["inside_cells_uv"]},
        key=lambda cell: (cell[1], cell[0]),
    )
    if count <= 0:
        raise ValueError("count must be positive")
    if count > len(inside_cells):
        raise ValueError(
            f"{floor_id} has only {len(inside_cells)} distinct portal-inside cells for {count} actors"
        )
    if count == 1:
        return [inside_cells[len(inside_cells) // 2]]
    indices = [round(index * (len(inside_cells) - 1) / (count - 1)) for index in range(count)]
    starts = [inside_cells[index] for index in indices]
    if len(set(starts)) != count:
        starts = inside_cells[:count]
    if len(set(starts)) != count:
        raise ValueError(f"{floor_id} could not produce distinct portal starts")
    return starts


def character_ids(root: Path) -> list[str]:
    payload = json.loads(
        (root / "CHARACTER" / "CHARACTERS" / "characters.json").read_text(encoding="utf-8")
    )
    result = [str(row["character_id"]) for row in payload["characters"]]
    if not result:
        raise ValueError("character registry is empty")
    return result


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


def combine_states(
    portal_cycle: dict[str, Any],
    work_cycle: dict[str, Any],
) -> list[dict[str, Any]]:
    """Join portal entry/exit to the WorkSeat cycle on the shared tick."""
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


def _shift_states(states: list[dict[str, Any]], delay_ms: int) -> None:
    for state in states:
        state["timeline_timestamp_ms"] = int(state["timeline_timestamp_ms"]) + int(delay_ms)


def _state_at(states: list[dict[str, Any]], timestamps: list[int], timestamp_ms: int) -> dict[str, Any] | None:
    index = bisect_right(timestamps, int(timestamp_ms)) - 1
    return states[index] if index >= 0 else None


def _phase_change_times(states: list[dict[str, Any]]) -> set[int]:
    times: set[int] = set()
    previous_phase: str | None = None
    for index, state in enumerate(states):
        phase = str(state["phase"])
        if index == 0 or phase != previous_phase or index == len(states) - 1:
            times.add(int(state["timeline_timestamp_ms"]))
        previous_phase = phase
    return times


def _walking_frame_index(core: Any, character_id: str, state: dict[str, Any]) -> int:
    action = str(state.get("action") or "idle")
    direction = str(state.get("direction") or "SE")
    result = core.characters.render(character_id, action, direction, None)
    if state.get("frame_index") is not None:
        return int(state["frame_index"]) % len(result.frames)
    if action == "move":
        profile = state.get("movement_profile") or {}
        return core.character_movement.walk_cycle_frame_index(
            float(state.get("cumulative_distance_px") or 0.0),
            len(result.frames),
            frame_distance_cells=float(profile.get("walk_frame_distance_cells", 0.65)),
        )
    return int(state.get("idle_frame_index") or 0) % len(result.frames)


def _with_alpha(image: Image.Image, alpha: float) -> Image.Image:
    if alpha >= 0.999:
        return image.convert("RGBA")
    output = image.convert("RGBA").copy()
    channel = output.getchannel("A").point(
        lambda value: int(value * max(0.0, min(1.0, float(alpha))))
    )
    output.putalpha(channel)
    return output


def _walking_actor(core: Any, spec: dict[str, Any], state: dict[str, Any]) -> tuple[dict[str, Any] | None, tuple[int, int, int, int] | None]:
    if not state.get("visible", True) or state.get("ground_xy") is None:
        return None, None
    character_id = str(spec["character_id"])
    action = str(state.get("action") or "idle")
    direction = str(state.get("direction") or "SE")
    rendered = core.characters.render(character_id, action, direction, None)
    frame = rendered.frames[_walking_frame_index(core, character_id, state)]
    frame = _with_alpha(frame, float(state.get("alpha", 1.0)))
    ground_xy = tuple(map(float, state["ground_xy"]))
    anchor = tuple(core.character_movement.GROUND_ANCHOR_PX)
    bbox = core.walking_depth._actor_bbox(frame, ground_xy, anchor)
    return (
        {
            "actor_id": spec["actor_id"],
            "sprite": frame,
            "ground_xy": ground_xy,
            "ground_anchor_px": anchor,
        },
        bbox,
    )


def _composite_walking_on_base(
    core: Any,
    floor_id: str,
    base: Image.Image,
    actors: list[dict[str, Any]],
) -> Image.Image:
    canvas = base.convert("RGBA").copy()
    normalized = []
    for index, actor in enumerate(actors):
        normalized.append((float(actor["ground_xy"][1]), index, actor))
    for _ground_y, _index, actor in sorted(normalized, key=lambda row: (row[0], row[1])):
        masked = core.walking_depth._mask_character_by_world_occluders(
            floor_id,
            actor["sprite"],
            tuple(actor["ground_xy"]),
            ground_anchor_px=tuple(actor["ground_anchor_px"]),
        )
        x0, y0, _x1, _y1 = core.walking_depth._actor_bbox(
            masked,
            tuple(actor["ground_xy"]),
            tuple(actor["ground_anchor_px"]),
        )
        canvas.alpha_composite(masked, (x0, y0))
    return canvas


def _dynamic_boxes_from_seated(by_workstation: dict[str, dict[str, Any]]) -> list[tuple[int, int, int, int]]:
    boxes: list[tuple[int, int, int, int]] = []
    for data in by_workstation.values():
        human = data.get("human")
        if human is not None:
            x = int(data["human_x_px"])
            y = int(data["human_y_px"])
            boxes.append((x, y, x + human.width, y + human.height))
        effect = data.get("effect")
        if effect is not None:
            x = int(data["effect_x_px"])
            y = int(data["effect_y_px"])
            boxes.append((x, y, x + effect.width, y + effect.height))
        popup = data.get("humanball")
        if popup is not None and data.get("humanball_x_px") is not None:
            x = int(data["humanball_x_px"])
            y = int(data["humanball_y_px"])
            boxes.append((x, y, x + popup.width, y + popup.height))
    return boxes


def _changed_outside_boxes(
    base: Image.Image,
    frame: Image.Image,
    boxes: list[tuple[int, int, int, int]],
) -> int:
    diff = ImageChops.difference(base.convert("RGBA"), frame.convert("RGBA"))
    draw = ImageDraw.Draw(diff)
    for box in boxes:
        draw.rectangle(box, fill=(0, 0, 0, 0))
    return 0 if diff.getbbox() is None else 1


def _work_frame_indices(timestamp_ms: int, seat_sync_ms: int) -> tuple[int, int, int]:
    elapsed = max(0, int(timestamp_ms) - int(seat_sync_ms))
    return (
        elapsed // CHARACTER_FRAME_MS,
        elapsed // EFFECT_FRAME_MS,
        elapsed // EFFECT_FRAME_MS,
    )


def _render_frame(
    core: Any,
    floor_id: str,
    specs: list[dict[str, Any]],
    timestamp_ms: int,
    seat_sync_ms: int,
) -> tuple[Image.Image, list[tuple[int, int, int, int]], list[str], list[str]]:
    seated_specs: list[dict[str, Any]] = []
    walking_actors: list[dict[str, Any]] = []
    dynamic_boxes: list[tuple[int, int, int, int]] = []
    visible_actor_ids: list[str] = []
    seated_actor_ids: list[str] = []
    seated_states: dict[str, dict[str, Any]] = {}

    for spec in specs:
        state = _state_at(spec["states"], spec["timestamps"], timestamp_ms)
        if state is None:
            continue
        if state["phase"] == "seated_work":
            seated_specs.append(spec)
            seated_states[spec["actor_id"]] = state
            visible_actor_ids.append(spec["actor_id"])
            seated_actor_ids.append(spec["actor_id"])
            continue
        actor, bbox = _walking_actor(core, spec, state)
        if actor is not None:
            walking_actors.append(actor)
            visible_actor_ids.append(spec["actor_id"])
            if bbox is not None:
                dynamic_boxes.append(bbox)

    assignments = []
    for spec in seated_specs:
        assignment = {
            "workstation_id": spec["workstation_id"],
            "character_id": spec["character_id"],
            "subaction": "normal_work",
        }
        if spec.get("effect_id") is not None:
            assignment["effect_id"] = spec["effect_id"]
        if spec.get("humanball_id") is not None:
            assignment["humanball_id"] = spec["humanball_id"]
        assignments.append(assignment)

    base = core.render_floor(floor_id).convert("RGBA")
    if assignments:
        character_index, effect_index, humanball_index = _work_frame_indices(
            timestamp_ms, seat_sync_ms
        )
        by_workstation, _rendered = core.work_seats._resolve_floor_assignment_data(
            floor_id,
            assignments,
            frame_index=character_index,
            character_frame_index=character_index,
            effect_frame_index=effect_index,
            humanball_frame_index=humanball_index,
        )
        dynamic_boxes.extend(_dynamic_boxes_from_seated(by_workstation))
        if any("effect_id" in row or "humanball_id" in row for row in assignments):
            frame = core.work_seats.render_floor_with_work_effects(
                floor_id,
                assignments,
                frame_index=character_index,
                character_frame_index=character_index,
                effect_frame_index=effect_index,
                humanball_frame_index=humanball_index,
            )
        else:
            frame = core.work_seats.render_floor_with_work(
                floor_id,
                assignments,
                frame_index=character_index,
                character_frame_index=character_index,
            )
    else:
        frame = base

    frame = _composite_walking_on_base(core, floor_id, frame, walking_actors)
    return frame, dynamic_boxes, visible_actor_ids, seated_actor_ids


def _render_overlay(
    core: Any,
    floor_id: str,
    specs: list[dict[str, Any]],
    output_path: Path,
) -> None:
    image = core.render_floor(floor_id).convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    for index, spec in enumerate(specs):
        color = IMPORTANT_COLORS[index % len(IMPORTANT_COLORS)]
        path = [tuple(cell) for cell in spec["work_cycle"]["inbound_path_cells_uv"]]
        points = [core.character_movement.uv_cell_center_to_pixel(*cell) for cell in path]
        if len(points) >= 2:
            draw.line(points, fill=color, width=2)
        start = core.character_movement.uv_cell_center_to_pixel(*spec["start_uv"])
        gate = core.character_movement.uv_cell_center_to_pixel(
            *spec["work_cycle"]["slot"]["transition_gate_uv"]
        )
        sx, sy = start
        gx, gy = gate
        draw.ellipse((sx - 4, sy - 4, sx + 4, sy + 4), fill=(255, 255, 255, 255), outline=(0, 0, 0, 255))
        draw.ellipse((gx - 5, gy - 5, gx + 5, gy + 5), fill=color, outline=(0, 0, 0, 255))
        draw.text(
            (gx + 6, gy - 8),
            f"{index + 1}:{spec['workstation_id']}",
            fill=(255, 255, 255, 255),
            stroke_width=2,
            stroke_fill=(0, 0, 0, 255),
            font=_font(12),
        )
    image.save(output_path)


def _render_case(
    core: Any,
    root: Path,
    label: str,
    floor_id: str,
    roster: list[str],
    output_root: Path,
) -> dict[str, Any]:
    workstation_list = workstation_ids(core, floor_id)
    count = len(workstation_list)
    if count <= 0:
        raise ValueError(f"{floor_id} has no authored computers")
    if count > len(roster):
        raise ValueError(f"{floor_id} needs {count} characters but roster has {len(roster)}")

    starts = portal_starts(core, floor_id, count)
    specs: list[dict[str, Any]] = []
    for index, (workstation_id, start_uv) in enumerate(zip(workstation_list, starts)):
        character_id = roster[index]
        portal_cycle = core.resolve_portal_actor_cycle(character_id, floor_id, start_uv)
        work_cycle = core.resolve_work_seat_actor_cycle(
            character_id,
            floor_id,
            workstation_id,
            start_uv,
            exit_goal_uv=start_uv,
            work_ticks=WORK_TICKS,
            effect_id="thunder_cloud" if workstation_id == "ceo" else None,
            humanball_id="coin" if workstation_id == "ceo" else None,
        )
        states = combine_states(portal_cycle, work_cycle)
        seated_start_ms = next(
            int(state["timeline_timestamp_ms"])
            for state in states
            if state["phase"] == "seated_work"
        )
        specs.append(
            {
                "actor_id": work_cycle["actor_id"],
                "character_id": character_id,
                "workstation_id": workstation_id,
                "start_uv": list(start_uv),
                "portal_cycle": portal_cycle,
                "work_cycle": work_cycle,
                "states": states,
                "seated_start_ms": seated_start_ms,
                "effect_id": "thunder_cloud" if workstation_id == "ceo" else None,
                "humanball_id": "coin" if workstation_id == "ceo" else None,
            }
        )

    seat_sync_ms = max(int(spec["seated_start_ms"]) for spec in specs)
    for spec in specs:
        delay_ms = seat_sync_ms - int(spec["seated_start_ms"])
        spec["start_delay_ms"] = delay_ms
        _shift_states(spec["states"], delay_ms)
        spec["timestamps"] = [int(state["timeline_timestamp_ms"]) for state in spec["states"]]

    max_timestamp = max(spec["timestamps"][-1] for spec in specs)
    frame_times = set(range(0, max_timestamp + 1, FRAME_STEP_MS))
    frame_times.add(max_timestamp)
    for spec in specs:
        frame_times.update(_phase_change_times(spec["states"]))
    frame_times = sorted(frame_times)

    output_dir = output_root / label
    output_dir.mkdir(parents=True, exist_ok=True)
    gif_path = output_dir / f"{label.lower()}_{count}_computers_one_actor_each.gif"
    base = core.render_floor(floor_id).convert("RGBA")
    paletted_frames: list[Image.Image] = []
    max_static_diff = 0
    max_visible_actor_count = 0
    max_seated_actor_count = 0
    max_duplicate_actor_count = 0
    max_duplicate_slot_count = 0

    for timestamp_ms in frame_times:
        frame, boxes, visible_ids, seated_ids = _render_frame(
            core, floor_id, specs, timestamp_ms, seat_sync_ms
        )
        max_static_diff = max(max_static_diff, _changed_outside_boxes(base, frame, boxes))
        max_visible_actor_count = max(max_visible_actor_count, len(visible_ids))
        max_seated_actor_count = max(max_seated_actor_count, len(seated_ids))
        max_duplicate_actor_count = max(
            max_duplicate_actor_count,
            len(visible_ids) - len(set(visible_ids)),
        )
        active_slots = [
            spec["work_cycle"]["slot"]["slot_id"]
            for spec in specs
            if _state_at(spec["states"], spec["timestamps"], timestamp_ms)
            and _state_at(spec["states"], spec["timestamps"], timestamp_ms)["phase"]
            == "seated_work"
        ]
        max_duplicate_slot_count = max(
            max_duplicate_slot_count,
            len(active_slots) - len(set(active_slots)),
        )
        frame = _label(
            frame,
            f"{label}  {count} actors / {count} computers  t={timestamp_ms}ms  "
            f"seated={len(seated_ids)}",
        )
        if not paletted_frames:
            paletted_frames.append(
                frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=255)
            )
        else:
            paletted_frames.append(
                frame.convert("RGB").quantize(
                    palette=paletted_frames[0], dither=Image.Dither.NONE
                )
            )
        frame.close()

    paletted_frames[0].save(
        gif_path,
        save_all=True,
        append_images=paletted_frames[1:],
        duration=FRAME_STEP_MS,
        loop=0,
        disposal=2,
        optimize=True,
    )
    encoded_frame_count = 0
    with Image.open(gif_path) as encoded:
        encoded_frame_count = int(getattr(encoded, "n_frames", 1))
    for frame in paletted_frames:
        frame.close()

    overlay_path = output_dir / f"{label.lower()}_{count}_computers_routes.png"
    _render_overlay(core, floor_id, specs, overlay_path)

    actor_summaries = []
    for spec in specs:
        cycle = spec["work_cycle"]
        actor_summaries.append(
            {
                "actor_id": spec["actor_id"],
                "character_id": spec["character_id"],
                "workstation_id": spec["workstation_id"],
                "slot_id": cycle["slot"]["slot_id"],
                "capacity": cycle["slot"]["capacity"],
                "start_uv": spec["start_uv"],
                "transition_gate_uv": cycle["slot"]["transition_gate_uv"],
                "facing": cycle["slot"]["facing"],
                "seat_transition_ready": cycle["slot"]["seat_transition_ready"],
                "start_delay_ms": spec["start_delay_ms"],
                "speed_percent": cycle["movement_profile"]["speed_percent"],
                "inbound_path_cell_count": len(cycle["inbound_path_cells_uv"]),
                "outbound_path_cell_count": len(cycle["outbound_path_cells_uv"]),
                "final_slot_state": cycle["final_slot_state"],
                "work_ticks": cycle["timing"]["work_ticks"],
            }
        )

    unique_workstations = len({spec["workstation_id"] for spec in specs}) == count
    unique_slots = len({spec["work_cycle"]["slot"]["slot_id"] for spec in specs}) == count
    result = {
        "label": label,
        "floor_id": floor_id,
        "workstation_ids": workstation_list,
        "workstation_count": count,
        "actor_count": len(specs),
        "actor_count_matches_computer_count": len(specs) == count,
        "unique_workstation_assignments": unique_workstations,
        "unique_slot_assignments": unique_slots,
        "capacity_values": sorted({int(spec["work_cycle"]["slot"]["capacity"]) for spec in specs}),
        "all_slots_ready": all(bool(spec["work_cycle"]["slot"]["seat_transition_ready"]) for spec in specs),
        "all_final_slots_free": all(spec["work_cycle"]["final_slot_state"] == "free" for spec in specs),
        "all_work_durations_1440ms": all(
            spec["work_cycle"]["timing"]["work_duration_ms"] == WORK_DURATION_MS
            for spec in specs
        ),
        "seat_sync_timestamp_ms": seat_sync_ms,
        "rendered_frame_count": len(frame_times),
        "encoded_frame_count": encoded_frame_count,
        "gif_bytes": gif_path.stat().st_size,
        "gif": str(gif_path.relative_to(root)),
        "routes_overlay": str(overlay_path.relative_to(root)),
        "max_visible_actor_count": max_visible_actor_count,
        "max_seated_actor_count": max_seated_actor_count,
        "max_duplicate_visible_actor_count": max_duplicate_actor_count,
        "max_duplicate_active_slot_count": max_duplicate_slot_count,
        "static_world_changed_pixels_outside_actor_bounds": max_static_diff,
        "actors": actor_summaries,
    }
    result["pass"] = bool(
        result["actor_count_matches_computer_count"]
        and result["unique_workstation_assignments"]
        and result["unique_slot_assignments"]
        and result["capacity_values"] == [1]
        and result["all_slots_ready"]
        and result["all_final_slots_free"]
        and result["all_work_durations_1440ms"]
        and result["max_duplicate_visible_actor_count"] == 0
        and result["max_duplicate_active_slot_count"] == 0
        and result["static_world_changed_pixels_outside_actor_bounds"] == 0
        and result["encoded_frame_count"] >= 1
    )
    return result


def render(root: str | Path, output: str | Path | None = None) -> dict[str, Any]:
    from RUNTIME.central_core import CentralGameCore

    root = Path(root).resolve()
    output_root = (
        Path(output).resolve()
        if output is not None
        else root / "LOCAL_REVIEW" / DEFAULT_OUTPUT
    )
    output_root.mkdir(parents=True, exist_ok=True)
    roster = character_ids(root)
    core = CentralGameCore(root)
    cases = [
        _render_case(core, root, label, floor_id, roster, output_root)
        for label, floor_id in CASES
    ]
    report = {
        "schema": "gds.phase8d.workstation_capacity_visual_qa.v1",
        "status": "PASS" if all(case["pass"] for case in cases) else "FAIL",
        "pass": bool(all(case["pass"] for case in cases)),
        "actor_policy": "one_actor_per_authored_workstation",
        "case_count": len(cases),
        "floors": [case["floor_id"] for case in cases],
        "total_actor_cycles": sum(case["actor_count"] for case in cases),
        "total_rendered_frames": sum(case["rendered_frame_count"] for case in cases),
        "max_gif_bytes": max(case["gif_bytes"] for case in cases),
        "cases": cases,
        "frame_step_ms": FRAME_STEP_MS,
        "timing_policy": {
            "playback_tick_ms": TICK_MS,
            "character_frame_ms": CHARACTER_FRAME_MS,
            "effect_frame_ms": EFFECT_FRAME_MS,
            "humanball_frame_ms": EFFECT_FRAME_MS,
            "pc_frame_loop_ms": CHARACTER_FRAME_MS * 2,
        },
        "work_ticks": WORK_TICKS,
        "work_duration_ms": WORK_DURATION_MS,
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
    args = parser.parse_args()
    result = render(args.core_root, args.output)
    print(json.dumps(result, indent=2, ensure_ascii=False))
