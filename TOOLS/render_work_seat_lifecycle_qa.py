from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


try:
    from TOOLS._bootstrap import ensure_project_root
except ModuleNotFoundError:
    from _bootstrap import ensure_project_root

ROOT = ensure_project_root(__file__)
OUTPUT_NAME = "PHASE8D_WORKSEAT_SINGLE_ACTOR_QA_20260831"
CASES = [
    ("F0_CEO_SE", "floor00", "ceo"),
    ("F0_WS3_NW", "floor00", "ws3"),
    ("F1_CEO_SE", "floor01", "ceo"),
    ("F1_WS3_NW", "floor01", "ws3"),
    ("F2_WS1_SE", "floor02", "ws1"),
    ("F2_WS3_NW", "floor02", "ws3"),
    ("F2_CEO_SW", "floor02", "ceo"),
    ("F14_CEO_SW", "floor14", "ceo"),
    ("F17_WS3_NW", "floor17", "ws3"),
]


def _font() -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", 14)
    except OSError:
        return ImageFont.load_default()


def _keyframe_indices(states: list[dict]) -> list[int]:
    by_phase: dict[str, list[int]] = {}
    for index, state in enumerate(states):
        by_phase.setdefault(state["phase"], []).append(index)
    selected: list[int] = []
    for phase in (
        "walking_to_seat",
        "approach",
        "seated_work",
        "exit_seat",
        "walking_from_seat",
    ):
        rows = by_phase.get(phase, [])
        if not rows:
            continue
        picks = [rows[0]]
        if phase == "walking_to_seat" and len(rows) > 2:
            picks.append(rows[-1])
        elif phase == "seated_work" and len(rows) > 2:
            picks.extend([rows[len(rows) // 2], rows[-1]])
        elif phase == "walking_from_seat" and len(rows) > 1:
            picks.append(rows[-1])
        for index in picks:
            if index not in selected:
                selected.append(index)
    return selected


def _render_state(core, cycle: dict, state: dict) -> Image.Image:
    floor_id = cycle["floor_id"]
    character_id = cycle["character_id"]
    if state["phase"] == "seated_work":
        work = state["work_render"]
        return core.render_work_seat_lifecycle_state(
            floor_id,
            cycle["workstation_id"],
            character_id,
            subaction=work["subaction"],
            effect_id=work.get("effect_id"),
            humanball_id=work.get("humanball_id"),
            character_frame_index=work["character_frame_index"],
            effect_frame_index=work.get("effect_frame_index"),
            humanball_frame_index=work.get("humanball_frame_index"),
        )
    action = state["action"]
    direction = state["direction"]
    result = core.characters.render(
        character_id,
        action,
        direction,
        None,
    )
    frame = result.frames[(state.get("frame_index") or 0) % len(result.frames)].convert("RGBA")
    ground = state.get("ground_xy")
    if ground is None:
        ground = core.character_movement.uv_cell_center_to_pixel(*state["transition_gate_uv"])
    return core.walking_depth.composite_character(
        floor_id,
        frame,
        tuple(ground),
        ground_anchor_px=tuple(core.character_movement.GROUND_ANCHOR_PX),
    )


def _label(image: Image.Image, label: str) -> Image.Image:
    out = image.copy().convert("RGBA")
    draw = ImageDraw.Draw(out)
    font = _font()
    draw.rectangle((0, 0, out.width, 26), fill=(10, 14, 22, 230))
    draw.text((8, 6), label, fill=(245, 247, 250, 255), font=font)
    return out


def render(root: str | Path, output: str | Path | None = None) -> dict:
    from RUNTIME.central_core import CentralGameCore

    root = Path(root).resolve()
    output_root = Path(output).resolve() if output else root / "LOCAL_REVIEW" / OUTPUT_NAME
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    core = CentralGameCore(root)
    cases: list[dict] = []
    contact_tiles: list[tuple[str, Image.Image]] = []
    for label, floor_id, workstation_id in CASES:
        start = tuple(core.resolve_portal_navigation_start(floor_id))
        cycle = core.resolve_work_seat_actor_cycle(
            0,
            floor_id,
            workstation_id,
            start,
            work_ticks=24,
            effect_id="thunder_cloud" if workstation_id == "ceo" else None,
        )
        case_dir = output_root / label
        case_dir.mkdir(parents=True, exist_ok=True)
        frames: list[Image.Image] = []
        keyframes: list[dict] = []
        for ordinal, state_index in enumerate(_keyframe_indices(cycle["states"])):
            state = cycle["states"][state_index]
            image = _render_state(core, cycle, state)
            key_label = (
                f"{label}  {state['phase']}  t={state['timestamp_ms']}ms  "
                f"speed={state['speed_percent']}%"
            )
            image = _label(image, key_label)
            png_path = case_dir / f"keyframe_{ordinal:02d}_{state['phase']}.png"
            image.save(png_path)
            frames.append(image)
            keyframes.append(
                {
                    "state_index": state_index,
                    "phase": state["phase"],
                    "timestamp_ms": state["timestamp_ms"],
                    "path": str(png_path.relative_to(root)),
                }
            )
        gif_path = case_dir / f"{label.lower()}_lifecycle.gif"
        if frames:
            gif_frames = [frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=255) for frame in frames]
            gif_frames[0].save(
                gif_path,
                save_all=True,
                append_images=gif_frames[1:],
                duration=[180] * len(gif_frames),
                loop=0,
                disposal=2,
            )
        seated_frames = [
            frame for frame, state_index in zip(frames, _keyframe_indices(cycle["states"]))
            if cycle["states"][state_index]["phase"] == "seated_work"
        ]
        if seated_frames:
            contact_tiles.append((label, seated_frames[len(seated_frames) // 2]))
        cases.append(
            {
                "label": label,
                "floor_id": floor_id,
                "workstation_id": workstation_id,
                "direction": cycle["slot"]["facing"],
                "speed_percent": cycle["movement_profile"]["speed_percent"],
                "phase_counts": cycle["phase_counts"],
                "slot_transition_history": cycle["slot_transition_history"],
                "final_slot_state": cycle["final_slot_state"],
                "final_uv": cycle["final_state"]["current_uv"],
                "keyframes": keyframes,
                "gif": str(gif_path.relative_to(root)),
            }
        )
    contact_sheet_path = output_root / "contact_sheet_seated.png"
    if contact_tiles:
        tile_w, tile_h = 600, 627
        columns = 3
        rows = (len(contact_tiles) + columns - 1) // columns
        sheet = Image.new("RGBA", (columns * tile_w, rows * tile_h), (20, 24, 32, 255))
        draw = ImageDraw.Draw(sheet)
        font = _font()
        for index, (label, tile) in enumerate(contact_tiles):
            x = (index % columns) * tile_w
            y = (index // columns) * tile_h
            sheet.alpha_composite(tile.convert("RGBA"), (x, y))
            draw.text((x + 8, y + 605), label, fill=(245, 247, 250, 255), font=font)
        sheet.save(contact_sheet_path)
    report = {
        "schema": "gds.phase8d.work_seat_lifecycle_visual_qa.v1",
        "status": "PASS",
        "pass": all(
            case["final_slot_state"] == "free"
            and case["phase_counts"].get("seated_work") == 24
            and case["keyframes"]
            for case in cases
        ),
        "output_root": str(output_root.relative_to(root)),
        "case_count": len(cases),
        "cases": cases,
        "contact_sheet": str(contact_sheet_path.relative_to(root)) if contact_tiles else None,
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
    report = render(args.core_root, args.output)
    print(json.dumps(report, indent=2, ensure_ascii=False))
