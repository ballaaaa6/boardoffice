from __future__ import annotations

"""Render the floor06 PC-cell animation review using the canonical runtime.

The source atlas is read-only review evidence.  The frame registry and floor
composition now come from the canonical PC animation registry/WorkSeat channel;
the tool only writes the externalized GIF and report under ``LOCAL_REVIEW``.
"""

import json
import math
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from RUNTIME.central_core import CentralGameCore


FLOOR_ID = "floor06"
FRAME_MS = 60
SIM_TICKS_PER_OUTPUT_FRAME = 2  # review preview only; keeps the GIF compact
CHARACTER_FRAME_MS = 220
PC_LOOP_MS = CHARACTER_FRAME_MS * 2  # normal_work has two character frames
PC_LOOP_TICKS = PC_LOOP_MS / FRAME_MS
WORK_TAIL_TICKS = 80
ATLAS_PATH = (
    ROOT
    / "00_STARTING_POINT"
    / "Game_Dev_Story_v2.6.9_EXTRACTED_ASSETS"
    / "01_KAIRO_SPRITE_PACKS"
    / "office"
    / "pc_006.png"
)

WORKSTATIONS = ["ceo", "ws1", "ws2", "ws3", "ws4", "ws5", "ws6", "ws7", "ws8"]


def build_global_palette(frames: list[Image.Image]) -> list[int]:
    strip = Image.new(
        "RGBA",
        (frames[0].width * len(frames), frames[0].height),
        (0, 0, 0, 0),
    )
    for idx, frame in enumerate(frames):
        strip.alpha_composite(frame.convert("RGBA"), (idx * frame.width, 0))
    alpha = strip.getchannel("A")
    rgb = Image.new("RGB", strip.size, (0, 0, 0))
    rgb.paste(strip, mask=alpha)
    pal = rgb.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    palette = pal.getpalette() or []
    if len(palette) < 768:
        palette += [0] * (768 - len(palette))
    return palette[:768]


def to_palette(im: Image.Image, palette: list[int]) -> Image.Image:
    rgba = im.convert("RGBA")
    alpha = rgba.getchannel("A")
    rgb = Image.new("RGB", rgba.size, (0, 0, 0))
    rgb.paste(rgba, mask=alpha)
    palette_image = Image.new("P", (1, 1))
    palette_image.putpalette(palette)
    pal = rgb.quantize(colors=255, palette=palette_image, dither=Image.Dither.NONE)
    transparent_mask = alpha.point(lambda value: 255 if value == 0 else 0)
    pal.paste(255, mask=transparent_mask)
    pal.putpalette(palette)
    pal.info["transparency"] = 255
    return pal


def atlas_cells() -> list[Image.Image]:
    with Image.open(ATLAS_PATH) as source:
        atlas = source.convert("RGBA")
    if atlas.size != (100, 96):
        raise RuntimeError(f"Expected pc_006.png to be 100x96, got {atlas.size}")
    return [
        atlas.crop(((index % 2) * 50, (index // 2) * 32, (index % 2) * 50 + 50, (index // 2) * 32 + 32))
        for index in range(6)
    ]


def verify_atlas(core: CentralGameCore, cells: list[Image.Image]) -> dict[str, Any]:
    variants = {
        index: core.world.load_asset(f"pc_006.slot_{index:02d}").convert("RGBA")
        for index in range(6)
    }
    matches = {
        f"cell{index}_matches_canonical_asset": bool(cells[index].tobytes() == variants[index].tobytes())
        for index in range(6)
    }
    unique_frames = len({cells[index].tobytes() for index in range(1, 6)})
    return {
        "atlas": ATLAS_PATH.relative_to(ROOT).as_posix(),
        "atlas_size": [100, 96],
        "cell_size": [50, 32],
        "cell_layout": {
            "cell0": "SE / static",
            "cell1": "NW / active slot_01",
            "cell2": "NW / additional frame 1",
            "cell3": "NW / additional frame 2",
            "cell4": "NW / additional frame 3",
            "cell5": "NW / additional frame 4",
        },
        **matches,
        "unique_nw_cells_1_to_5": unique_frames,
        "nw_cells_1_to_5_are_distinct": unique_frames == 5,
    }


def overlay_alpha_at_reference(
    canvas: Image.Image,
    placement: dict[str, Any],
    dynamic_sprite: Image.Image,
    world,
) -> None:
    """Patch only pixels that still belong to the authored static PC.

    Work-seat humans and foreground chair pieces are rendered after a PC in the
    canonical event order.  Comparing the current canvas to the static PC
    reference keeps this POC overlay from painting over those later layers.
    """

    x = int(placement["x_px"])
    y = int(placement["y_px"])
    reference = world.load_variant(placement["variant_id"]).convert("RGBA")
    dynamic = dynamic_sprite.convert("RGBA").copy()
    if reference.size != dynamic.size:
        raise RuntimeError(
            f"PC overlay size mismatch for {placement['placement_id']}: "
            f"{reference.size} vs {dynamic.size}"
        )
    region = canvas.crop((x, y, x + reference.width, y + reference.height))
    ref_pixels = list(reference.getdata())
    current_pixels = list(region.getdata())
    mask = Image.new("L", reference.size, 0)
    mask.putdata(
        [
            255
            if ref_pixel[3] > 0 and current_pixel == ref_pixel
            else 0
            for ref_pixel, current_pixel in zip(ref_pixels, current_pixels)
        ]
    )
    dynamic.putalpha(ImageChops.multiply(dynamic.getchannel("A"), mask))
    canvas.alpha_composite(dynamic, (x, y))


def patch_pc_cells(
    canvas: Image.Image,
    core: CentralGameCore,
    cells: list[Image.Image],
    specs: list[dict[str, Any]],
    sim_tick: int,
    *,
    static: bool = False,
) -> dict[str, int]:
    selected: dict[str, int] = {}
    placements = {
        placement["placement_id"]: placement
        for placement in core.world.resolve_floor_placements(FLOOR_ID)
    }
    for spec in specs:
        workstation_id = spec["workstation_id"]
        direction = spec["direction"]
        if direction == "NW":
            cell_index = 1 if static or sim_tick < spec["arrival_tick"] else 1 + (
                ((sim_tick - spec["arrival_tick"]) // PC_LOOP_TICKS) % 5
            )
            placement_id = f"{workstation_id}_pc"
            placement = placements[placement_id]
            overlay_alpha_at_reference(canvas, placement, cells[cell_index], core.world)
        else:
            cell_index = 0
        selected[workstation_id] = cell_index
    return selected


def composite_walking_on_base(
    canvas: Image.Image,
    core: CentralGameCore,
    actors: list[dict[str, Any]],
) -> Image.Image:
    result = canvas.convert("RGBA").copy()
    normalized = []
    for index, actor in enumerate(actors):
        gx, gy = actor["ground_xy"]
        normalized.append((float(gy), index, actor, (float(gx), float(gy))))
    anchor = tuple(core.character_movement.GROUND_ANCHOR_PX)
    for _gy, _index, actor, ground_xy in sorted(normalized, key=lambda row: (row[0], row[1])):
        sprite = core.walking_depth._mask_character_by_world_occluders(
            FLOOR_ID,
            actor["sprite"],
            ground_xy,
            ground_anchor_px=anchor,
        )
        x0, y0, _x1, _y1 = core.walking_depth._actor_bbox(sprite, ground_xy, anchor)
        result.alpha_composite(sprite, (x0, y0))
    return result


def transition_states(
    core: CentralGameCore,
    start_uv: tuple[int, int],
    outside_uv: tuple[int, int],
    movement_profile: dict[str, Any],
) -> list[dict[str, Any]]:
    outside_xy = tuple(map(float, core.character_movement.uv_cell_center_to_pixel(*outside_uv)))
    start_xy = tuple(map(float, core.character_movement.uv_cell_center_to_pixel(*start_uv)))
    direction = core.character_movement.direction_for_step(outside_uv, start_uv)
    states: list[dict[str, Any]] = []
    for index, alpha in enumerate((0.25, 0.5, 0.75, 1.0), start=1):
        t = index / 4.0
        xy = (
            outside_xy[0] + (start_xy[0] - outside_xy[0]) * t,
            outside_xy[1] + (start_xy[1] - outside_xy[1]) * t,
        )
        previous_t = (index - 1) / 4.0
        previous_xy = (
            outside_xy[0] + (start_xy[0] - outside_xy[0]) * previous_t,
            outside_xy[1] + (start_xy[1] - outside_xy[1]) * previous_t,
        )
        states.append(
            {
                "ground_xy": xy,
                "previous_ground_xy": previous_xy,
                "direction": direction,
                "raw_direction": direction,
                "action": "move",
                "cumulative_distance_px": math.dist(outside_xy, xy),
                "alpha": alpha,
                "phase": "entry",
                "current_uv": list(start_uv),
                "from_uv": list(outside_uv),
                "to_uv": list(start_uv),
                "progress_t": round(t, 4),
                "speed_percent": movement_profile["speed_percent"],
                "speed_multiplier": movement_profile["speed_multiplier"],
            }
        )
    return states


def movement_states(core: CentralGameCore, spec: dict[str, Any]) -> list[dict[str, Any]]:
    movement = core.resolve_employee_movement(
        spec["employee_id"],
        FLOOR_ID,
        spec["start_uv"],
        spec["target_uv"],
    )
    profile = movement["movement_profile"]
    states = transition_states(
        core,
        tuple(spec["start_uv"]),
        tuple(spec["outside_uv"]),
        profile,
    )
    previous_xy = states[-1]["ground_xy"]
    transition_distance = float(states[-1]["cumulative_distance_px"])
    for sample in movement["timed_motion_samples"]:
        xy = tuple(map(float, sample["ground_xy"]))
        # ``timed_motion_samples`` already stores distance from the start of
        # the sampled path; do not accumulate that cumulative value again.
        cumulative = transition_distance + float(sample["cumulative_distance_px"])
        states.append(
            {
                "ground_xy": xy,
                "previous_ground_xy": previous_xy,
                "direction": sample["visual_direction"],
                "raw_direction": sample["raw_direction"],
                "action": "move",
                "cumulative_distance_px": cumulative,
                "alpha": 1.0,
                "phase": "outward",
                "step_index": sample["step_index"],
                "tick_index": sample["tick_index"],
                "current_uv": list(sample["to_uv"]),
                "from_uv": list(sample["from_uv"]),
                "to_uv": list(sample["to_uv"]),
                "progress_t": sample["progress_t"],
                "speed_percent": profile["speed_percent"],
                "speed_multiplier": profile["speed_multiplier"],
            }
        )
        previous_xy = xy
    return states


def load_floor06_specs(core: CentralGameCore) -> list[dict[str, Any]]:
    employees = {
        row["assignment"]["workstation_id"]: row
        for row in core.list_employees(assigned=True)
        if row.get("assignment", {}).get("floor_id") == FLOOR_ID
    }
    portal = core.resolve_portal(FLOOR_ID)
    inside = [tuple(cell) for cell in portal["inside_cells_uv"]]
    outside = [tuple(cell) for cell in portal["outside_cells_uv"]]
    specs: list[dict[str, Any]] = []
    for index, workstation_id in enumerate(WORKSTATIONS):
        employee = employees[workstation_id]
        seat = core.resolve_work_seat(FLOOR_ID, workstation_id)
        slot = core.resolve_work_seat_interaction_slot(FLOOR_ID, workstation_id)
        portal_index = min(index * 3, len(inside) - 1)
        specs.append(
            {
                "employee_id": employee["employee_id"],
                "character_id": employee["character_id"],
                "full_name": employee["full_name"],
                "workstation_id": workstation_id,
                "direction": seat["direction"],
                "start_uv": list(inside[portal_index]),
                "outside_uv": list(outside[portal_index]),
                "target_uv": list(slot["transition_gate_uv"]),
                "priority": index,
            }
        )
    return specs


def render_frame(
    core: CentralGameCore,
    cells: list[Image.Image],
    specs: list[dict[str, Any]],
    schedule_rows: dict[str, dict[str, Any]],
    output_frame_index: int,
    *,
    static_pc: bool,
) -> tuple[Image.Image, dict[str, Any]]:
    sim_tick = output_frame_index * SIM_TICKS_PER_OUTPUT_FRAME
    arrived = [spec for spec in specs if sim_tick >= spec["arrival_tick"]]
    selected_cells: dict[str, int] = {}
    assignments = [
        {
            "workstation_id": spec["workstation_id"],
            "character_id": spec["character_id"],
            "subaction": "normal_work",
            "pc_frame_index": (
                0
                if static_pc or spec["direction"] not in {"NW", "NE"}
                else (((sim_tick - spec["arrival_tick"]) * FRAME_MS) // PC_LOOP_MS) % 5
            ),
        }
        for spec in arrived
    ]
    for spec in specs:
        if spec["direction"] in {"NW", "NE"}:
            frame_index = (
                0
                if static_pc or sim_tick < spec["arrival_tick"]
                else (((sim_tick - spec["arrival_tick"]) * FRAME_MS) // PC_LOOP_MS) % 5
            )
            selected_cells[spec["workstation_id"]] = frame_index + 1
        else:
            selected_cells[spec["workstation_id"]] = 0
    global_work_frame = (sim_tick * FRAME_MS) // CHARACTER_FRAME_MS
    if assignments:
        base = core.work_seats.render_floor_with_work(
            FLOOR_ID,
            assignments,
            frame_index=int(global_work_frame),
        ).convert("RGBA")
    else:
        base = core.render_floor(FLOOR_ID).convert("RGBA")
    actors: list[dict[str, Any]] = []
    for spec in specs:
        row = schedule_rows[spec["actor_id"]]
        local_index = sim_tick - int(row["start_delay"])
        states = row["states"]
        if local_index < 0 or local_index >= len(states):
            continue
        state = states[local_index]
        profile = spec["movement_profile"]
        direction = state["direction"]
        frames = core.render_character(spec["character_id"], "move", direction).frames
        frame_index = core.character_movement.walk_cycle_frame_index(
            float(state["cumulative_distance_px"]),
            len(frames),
            frame_distance_cells=float(profile["walk_frame_distance_cells"]),
        )
        sprite = frames[frame_index].convert("RGBA")
        alpha = float(state.get("alpha", 1.0))
        if alpha < 0.999:
            sprite = sprite.copy()
            sprite.putalpha(sprite.getchannel("A").point(lambda value: int(value * alpha)))
        actors.append(
            {
                "actor_id": spec["actor_id"],
                "sprite": sprite,
                "ground_xy": tuple(map(float, state["ground_xy"])),
                "ground_anchor_px": tuple(core.character_movement.GROUND_ANCHOR_PX),
            }
        )

    frame = composite_walking_on_base(base, core, actors) if actors else base
    return frame, {
        "sim_tick": sim_tick,
        "arrived_workstations": [spec["workstation_id"] for spec in arrived],
        "pc_cells": selected_cells,
        "walking_actor_count": len(actors),
    }


def save_gif(frames: list[Image.Image], path: Path) -> None:
    palette = build_global_palette(frames)
    paletted = [to_palette(frame, palette) for frame in frames]
    paletted[0].save(
        path,
        save_all=True,
        append_images=paletted[1:],
        duration=FRAME_MS,
        loop=0,
        disposal=2,
    )


def contact_sheet(
    frames: list[Image.Image],
    metadata: list[dict[str, Any]],
    path: Path,
    indices: list[int],
) -> None:
    caption_height = 28
    columns = 3
    rows = (len(indices) + columns - 1) // columns
    sheet = Image.new("RGBA", (600 * columns, (600 + caption_height) * rows), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for slot, index in enumerate(indices):
        x = (slot % columns) * 600
        y = (slot // columns) * (600 + caption_height)
        sheet.alpha_composite(frames[index].convert("RGBA"), (x, y))
        meta = metadata[index]
        cells = ", ".join(
            f"{workstation}:{cell}"
            for workstation, cell in sorted(meta["pc_cells"].items())
            if cell != 0
        )
        caption = (
            f"frame {index} / sim {meta['sim_tick']} / "
            f"walking {meta['walking_actor_count']} / NW {cells or 'not working yet'}"
        )
        draw.rectangle((x, y + 600, x + 600, y + 600 + caption_height), fill=(245, 245, 245, 255))
        draw.text((x + 5, y + 7 * 0 + 606), caption, fill=(20, 20, 20, 255), font=font)
    sheet.save(path)


def zoom_frames(frames: list[Image.Image]) -> list[Image.Image]:
    box = (180, 220, 410, 370)
    return [
        frame.crop(box).resize((460, 300), Image.Resampling.NEAREST).convert("RGBA")
        for frame in frames
    ]


def zoom_contact_sheet(
    frames: list[Image.Image],
    metadata: list[dict[str, Any]],
    path: Path,
    indices: list[int],
) -> None:
    width, height, caption_height = 460, 300, 28
    columns = 3
    rows = (len(indices) + columns - 1) // columns
    sheet = Image.new("RGBA", (width * columns, (height + caption_height) * rows), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for slot, index in enumerate(indices):
        x = (slot % columns) * width
        y = (slot // columns) * (height + caption_height)
        sheet.alpha_composite(frames[index], (x, y))
        meta = metadata[index]
        nw_cells = ", ".join(
            f"{workstation}:{cell}"
            for workstation, cell in sorted(meta["pc_cells"].items())
            if cell != 0
        )
        caption = f"frame {index} / sim {meta['sim_tick']} / NW {nw_cells or 'not working yet'}"
        draw.rectangle((x, y + height, x + width, y + height + caption_height), fill=(245, 245, 245, 255))
        draw.text((x + 5, y + height + 6), caption, fill=(20, 20, 20, 255), font=font)
    sheet.save(path)


def main() -> int:
    core = CentralGameCore(ROOT)
    output_root = ROOT / "LOCAL_REVIEW" / "PHASE8E_PC_ANIMATION_POC_20260901"
    output_root.mkdir(parents=True, exist_ok=True)

    cells = atlas_cells()
    atlas_report = verify_atlas(core, cells)
    specs = load_floor06_specs(core)
    for spec in specs:
        spec["actor_id"] = f"floor06:{spec['employee_id']}"
        spec["movement_states"] = movement_states(core, spec)
        spec["movement_profile"] = core.resolve_employee_movement_profile(spec["employee_id"])

    schedule = core.resolve_crowd_movement_schedule(
        [
            {
                "actor_id": spec["actor_id"],
                "states": spec["movement_states"],
                "start_delay": 0,
                "priority": spec["priority"],
            }
            for spec in specs
        ]
    )
    schedule_rows = {row["actor_id"]: row for row in schedule["actors"]}
    for spec in specs:
        row = schedule_rows[spec["actor_id"]]
        spec["arrival_tick"] = int(row["start_delay"]) + len(row["states"])

    max_sim_tick = max(spec["arrival_tick"] for spec in specs) + WORK_TAIL_TICKS
    output_frame_count = (max_sim_tick // SIM_TICKS_PER_OUTPUT_FRAME) + 1
    animated_frames: list[Image.Image] = []
    baseline_frames: list[Image.Image] = []
    metadata: list[dict[str, Any]] = []
    for output_index in range(output_frame_count):
        animated, frame_meta = render_frame(
            core,
            cells,
            specs,
            schedule_rows,
            output_index,
            static_pc=False,
        )
        baseline, _baseline_meta = render_frame(
            core,
            cells,
            specs,
            schedule_rows,
            output_index,
            static_pc=True,
        )
        animated_frames.append(animated)
        baseline_frames.append(baseline)
        metadata.append(frame_meta)

    animated_path = output_root / "floor06_pc_animation_poc.gif"
    baseline_path = output_root / "floor06_pc_animation_baseline.gif"
    save_gif(animated_frames, animated_path)
    save_gif(baseline_frames, baseline_path)

    animated_zoom_frames = zoom_frames(animated_frames)
    zoom_path = output_root / "floor06_pc_animation_zoom.gif"
    save_gif(animated_zoom_frames, zoom_path)

    sample_indices = sorted(
        {
            0,
            min(output_frame_count - 1, output_frame_count // 4),
            min(output_frame_count - 1, output_frame_count // 2),
            min(output_frame_count - 1, (output_frame_count * 3) // 4),
            output_frame_count - 1,
        }
    )
    sheet_path = output_root / "floor06_pc_animation_keyframes.png"
    contact_sheet(animated_frames, metadata, sheet_path, sample_indices)
    zoom_sheet_path = output_root / "floor06_pc_animation_zoom_keyframes.png"
    zoom_contact_sheet(animated_zoom_frames, metadata, zoom_sheet_path, sample_indices)

    first_work = next((item for item in metadata if item["arrived_workstations"]), metadata[-1])
    first_nw = next(
        (item for item in metadata if any(cell >= 2 for cell in item["pc_cells"].values())),
        metadata[-1],
    )
    final_nw = metadata[-1]
    report = {
        "schema": "gds.floor06_pc_animation_poc.v1",
        "floor_id": FLOOR_ID,
        "review_scope": "isolated_LOCAL_REVIEW_only",
        "canonical_runtime_used": True,
        "canonical_registry_verified": True,
        "source_assets_changed": False,
        "frame_ms": FRAME_MS,
        "preview_sim_ticks_per_output_frame": SIM_TICKS_PER_OUTPUT_FRAME,
        "preview_time_scale": SIM_TICKS_PER_OUTPUT_FRAME,
        "character_frame_ms": CHARACTER_FRAME_MS,
        "normal_work_loop_ms": PC_LOOP_MS,
        "pc_loop_tick_equivalent": round(PC_LOOP_TICKS, 4),
        "pc_cell_sequence_nw": [1, 2, 3, 4, 5],
        "pc_cell_sequence_se_sw": [0],
        "atlas": atlas_report,
        "schedule": {
            key: value
            for key, value in schedule.items()
            if key != "actors"
        },
        "assignments": [
            {
                key: spec[key]
                for key in (
                    "employee_id",
                    "character_id",
                    "full_name",
                    "workstation_id",
                    "direction",
                    "start_uv",
                    "outside_uv",
                    "target_uv",
                    "arrival_tick",
                )
            }
            | {
                "start_delay": int(schedule_rows[spec["actor_id"]]["start_delay"]),
                "movement_state_count": len(schedule_rows[spec["actor_id"]]["states"]),
            }
            for spec in specs
        ],
        "frame_count": output_frame_count,
        "duration_ms": output_frame_count * FRAME_MS,
        "first_work_frame": first_work,
        "first_additional_nw_cell_frame": first_nw,
        "final_frame": final_nw,
        "outputs": {
            "animated_gif": animated_path.relative_to(ROOT).as_posix(),
            "baseline_gif": baseline_path.relative_to(ROOT).as_posix(),
            "zoom_gif": zoom_path.relative_to(ROOT).as_posix(),
            "keyframes_png": sheet_path.relative_to(ROOT).as_posix(),
            "zoom_keyframes_png": zoom_sheet_path.relative_to(ROOT).as_posix(),
        },
        "visual_approval": "author_approved_poc_then_canonical_runtime_integrated",
    }
    report_path = output_root / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
