"""Render a review-only NW -> NE WorkSeat mirror proof GIF.

The preview samples one real NW workstation group and one character with a
reproducible seed. It composes the authored NW desk, PC, chair, optional chair
foreground and NW Work character frames, then mirrors the complete composite
once to produce the NE result. It remains a review artifact and never edits
world assets, placements, navigation data or canonical runtime contracts; the
same derivation is now available through the canonical NE WorkSeat path.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    ROOT
    / "outputs"
    / "01a057c6-2d38-7be3-bfbe-4cadb1b6cc66"
    / "NE_WORKSTATION_MIRROR_PREVIEW"
)
sys.path.insert(0, str(ROOT))

from CHARACTER.RUNTIME.character_system import CharacterSystem  # noqa: E402
from RUNTIME.work_seat_core import WorkSeatCore  # noqa: E402
from TOOLS.render_work_frame_reference import (  # noqa: E402
    BG,
    GOLD,
    MIRROR_COLOR,
    MUTED,
    NE_COLOR,
    NW_COLOR,
    PANEL_2,
    checker,
    draw_multiline,
    draw_text,
    make_font,
    panel,
)


TARGET_TO_SOURCE: dict[str, str] = {
    "normal_work": "normal_work",
    "turn_side_se": "turn_side_sw",
    "turn_side_nw": "turn_side_ne",
    "happy": "happy",
}
TARGET_SUBACTIONS = tuple(TARGET_TO_SOURCE)


def _save_gif(frames: list[Image.Image], path: Path, *, duration: int) -> None:
    if not frames:
        raise ValueError(f"Cannot save empty GIF: {path}")
    palettes = [
        frame.convert("RGB").quantize(
            colors=255,
            method=Image.Quantize.MEDIANCUT,
            dither=Image.Dither.NONE,
        )
        for frame in frames
    ]
    palettes[0].save(
        path,
        save_all=True,
        append_images=palettes[1:],
        duration=[duration] * len(palettes),
        loop=0,
        disposal=2,
    )


def _all_nw_workstations(seat: WorkSeatCore) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for floor_id in sorted(seat.world.floors):
        layout = seat.world.floor_layout(floor_id)
        for workstation_id in sorted(layout.get("workstation_groups", {})):
            direction = seat.directions.resolve_character_action_direction(
                floor_id,
                workstation_id,
                action_family="work",
            )
            if direction != "NW":
                continue
            group = seat.world.workstation_group(floor_id, workstation_id)
            placements = {
                placement["placement_id"]: placement
                for placement in seat.world.resolve_floor_placements(floor_id)
            }
            component_slots = group["component_slots"]
            components: dict[str, dict[str, Any]] = {}
            for component_name in ("desk", "pc", "chair_main"):
                placement_id = component_slots[component_name]
                if placement_id not in placements:
                    raise ValueError(
                        f"Missing {component_name} placement for {floor_id}.{workstation_id}"
                    )
                components[component_name] = placements[placement_id]

            foreground_id = group.get("optional_component_slots", {}).get("chair_foreground")
            if foreground_id and foreground_id in placements:
                components["chair_foreground"] = placements[foreground_id]

            records.append(
                {
                    "floor_id": floor_id,
                    "workstation_id": workstation_id,
                    "direction": direction,
                    "group": group,
                    "components": components,
                }
            )
    if not records:
        raise ValueError("No NW workstation groups were found")
    return records


def _load_variant(seat: WorkSeatCore, placement: dict[str, Any]) -> Image.Image:
    return seat.world.load_variant(placement["variant_id"]).convert("RGBA")


def _compose_nw_source(
    seat: WorkSeatCore,
    sample: dict[str, Any],
    human: Image.Image,
) -> tuple[Image.Image, dict[str, Any]]:
    components = sample["components"]
    loaded = {
        name: _load_variant(seat, placement)
        for name, placement in components.items()
    }
    chair_placement = components["chair_main"]
    chair = loaded["chair_main"]
    offset = seat.resolve_world_offset(
        "NW",
        chair_size=chair.size,
        human_size=human.size,
    )
    human_xy = (
        int(chair_placement["x_px"]) + int(offset[0]),
        int(chair_placement["y_px"]) + int(offset[1]),
    )

    rectangles: list[tuple[int, int, int, int]] = []
    for name, placement in components.items():
        asset = loaded[name]
        x = int(placement["x_px"])
        y = int(placement["y_px"])
        rectangles.append((x, y, x + asset.width, y + asset.height))
    rectangles.append((human_xy[0], human_xy[1], human_xy[0] + human.width, human_xy[1] + human.height))

    padding = 10
    min_x = min(rect[0] for rect in rectangles)
    min_y = min(rect[1] for rect in rectangles)
    max_x = max(rect[2] for rect in rectangles)
    max_y = max(rect[3] for rect in rectangles)
    origin = (padding - min_x, padding - min_y)
    canvas = Image.new(
        "RGBA",
        (max_x - min_x + (2 * padding), max_y - min_y + (2 * padding)),
        (0, 0, 0, 0),
    )

    # The authored NW workstation has desk/PC behind the chair, the human
    # between chair main and optional foreground, and the foreground last.
    static_names = ["desk", "pc", "chair_main"]
    static_names.sort(key=lambda name: int(components[name]["layer"]))
    for name in static_names:
        placement = components[name]
        canvas.alpha_composite(
            loaded[name],
            (origin[0] + int(placement["x_px"]), origin[1] + int(placement["y_px"])),
        )
    canvas.alpha_composite(human, (origin[0] + human_xy[0], origin[1] + human_xy[1]))
    if "chair_foreground" in components:
        placement = components["chair_foreground"]
        canvas.alpha_composite(
            loaded["chair_foreground"],
            (origin[0] + int(placement["x_px"]), origin[1] + int(placement["y_px"])),
        )

    detail = {
        "source_direction": "NW",
        "source_human_offset_from_chair_px": [int(offset[0]), int(offset[1])],
        "source_canvas_size": [canvas.width, canvas.height],
        "source_origin_world_px": [min_x, min_y],
        "component_asset_ids": {
            name: placement["asset_id"] for name, placement in components.items()
        },
        "component_variant_ids": {
            name: placement["variant_id"] for name, placement in components.items()
        },
        "component_positions_world_px": {
            name: [int(placement["x_px"]), int(placement["y_px"])]
            for name, placement in components.items()
        },
        "component_layers": {
            name: int(placement["layer"]) for name, placement in components.items()
        },
        "draw_order_policy": ["desk", "pc", "chair_main", "human", "chair_foreground_if_present"],
    }
    return canvas, detail


def _fit_art(canvas: Image.Image, art: Image.Image, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    tile = checker((x1 - x0, y1 - y0), cell=12)
    canvas.alpha_composite(tile, (x0, y0))
    scale = max(1, min((x1 - x0) // art.width, (y1 - y0) // art.height))
    scaled = art.resize((art.width * scale, art.height * scale), Image.Resampling.NEAREST)
    px = x0 + ((x1 - x0) - scaled.width) // 2
    py = y0 + ((y1 - y0) - scaled.height) // 2
    canvas.alpha_composite(scaled, (px, py))


def _draw_card(
    *,
    source: Image.Image,
    target: Image.Image,
    sample: dict[str, Any],
    character_id: str,
    target_subaction: str,
    source_subaction: str,
    source_frame_id: str,
    target_frame_id: str,
    frame_index: int,
    seed: int,
    identity_name: str,
) -> Image.Image:
    width = 1280
    height = 790
    canvas = Image.new("RGBA", (width, height), BG)
    draw = ImageDraw.Draw(canvas)

    draw_text(draw, (32, 24), "NE WORKSTATION MIRROR — REVIEW GIF", 27, NE_COLOR)
    draw_text(
        draw,
        (32, 64),
        "complete NW composite → mirror once → NE | canonical NE bridge ready",
        15,
        MUTED,
    )

    panel_y0 = 104
    panel_y1 = 610
    left = (28, panel_y0, 616, panel_y1)
    right = (664, panel_y0, 1252, panel_y1)
    panel(draw, left, outline=NW_COLOR, fill=PANEL_2, radius=14, width=3)
    panel(draw, right, outline=NE_COLOR, fill=PANEL_2, radius=14, width=3)
    draw_text(draw, (54, 126), "NW SOURCE", 22, NW_COLOR)
    draw_text(draw, (690, 126), "NE RESULT", 22, NE_COLOR)
    draw_text(draw, (54, 160), f"work/{source_subaction} · frame {frame_index}", 15, MUTED)
    draw_text(draw, (690, 160), f"work/{target_subaction} · frame {frame_index}", 15, MUTED)

    _fit_art(canvas, source, (54, 194, 590, 536))
    _fit_art(canvas, target, (690, 194, 1226, 536))
    draw_text(draw, (616, 320), "→", 38, MIRROR_COLOR, anchor="mm")
    draw_text(draw, (616, 360), "mirror_y", 13, MIRROR_COLOR, anchor="mm")

    floor_id = sample["floor_id"]
    workstation_id = sample["workstation_id"]
    components = sample["components"]
    footer = (
        f"seed {seed} · {floor_id}.{workstation_id} · character {character_id} ({identity_name})\n"
        f"desk {components['desk']['asset_id']} · pc {components['pc']['asset_id']} · "
        f"chair {components['chair_main']['asset_id']}"
    )
    if "chair_foreground" in components:
        footer += f" + foreground {components['chair_foreground']['asset_id']}"
    draw_multiline(draw, (32, 642), footer, 15, MUTED, spacing=5)
    draw.line((32, 718, width - 32, 718), fill=(48, 72, 96, 255), width=2)
    draw_text(
        draw,
        (32, 738),
        f"source frame {source_frame_id} → target frame {target_frame_id} · one final-composite mirror, no double mirror",
        14,
        GOLD,
    )
    return canvas


def render(seed: int, output_dir: Path) -> dict[str, Any]:
    rng = random.Random(seed)
    seat = WorkSeatCore(ROOT)
    characters = CharacterSystem(ROOT / "CHARACTER")
    workstation_pool = _all_nw_workstations(seat)
    sample = rng.choice(workstation_pool)
    character_id = rng.choice(characters.list_characters())
    identity = characters.get_character(character_id)
    identity_name = str(identity.get("name") or identity.get("full_name") or character_id)

    output_dir.mkdir(parents=True, exist_ok=True)
    frames: list[Image.Image] = []
    frame_records: list[dict[str, Any]] = []
    source_details: dict[str, Any] | None = None

    for target_subaction, source_subaction in TARGET_TO_SOURCE.items():
        source_action = characters.render(character_id, "work", "NW", source_subaction)
        target_action = characters.render(character_id, "work", "NE", target_subaction)
        if len(source_action.frames) != len(target_action.frames):
            raise ValueError(
                f"Frame-count mismatch for {target_subaction}: "
                f"NW={len(source_action.frames)} NE={len(target_action.frames)}"
            )
        for frame_index, source_human in enumerate(source_action.frames):
            expected_target = source_human.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            actual_target = target_action.frames[frame_index].convert("RGBA")
            if expected_target.tobytes() != actual_target.tobytes():
                raise ValueError(
                    f"Character mirror mismatch for {target_subaction} frame {frame_index}"
                )
            source_composite, detail = _compose_nw_source(seat, sample, source_human.convert("RGBA"))
            target_composite = source_composite.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            if source_details is None:
                source_details = detail
            elif detail != source_details:
                raise ValueError("Static workstation composition changed between animation frames")

            frames.append(
                _draw_card(
                    source=source_composite,
                    target=target_composite,
                    sample=sample,
                    character_id=character_id,
                    target_subaction=target_subaction,
                    source_subaction=source_subaction,
                    source_frame_id=source_action.frame_ids[frame_index],
                    target_frame_id=target_action.frame_ids[frame_index],
                    frame_index=frame_index,
                    seed=seed,
                    identity_name=identity_name,
                )
            )
            frame_records.append(
                {
                    "target_subaction": target_subaction,
                    "source_subaction": source_subaction,
                    "frame_index": frame_index,
                    "source_frame_id": source_action.frame_ids[frame_index],
                    "target_frame_id": target_action.frame_ids[frame_index],
                    "character_mirror_exact": True,
                    "composite_transform": "mirror_y",
                }
            )

    gif_path = output_dir / "NE_workstation_mirror_preview.gif"
    first_frame_path = output_dir / "NE_workstation_mirror_preview_first_frame.png"
    manifest_path = output_dir / "NE_workstation_mirror_preview_manifest.json"
    _save_gif(frames, gif_path, duration=720)
    frames[0].save(first_frame_path)
    manifest = {
        "schema": "gds.review.ne_workstation_mirror_preview.v1",
        "review_only": True,
        "canonical_registry_edited": False,
        "world_bridge_enabled": True,
        "runtime_integration_status": "canonical_four_way_ne_ready",
        "seed": seed,
        "source_direction": "NW",
        "target_direction": "NE",
        "derivation": "compose_complete_NW_workstation_then_mirror_y_once",
        "target_to_source_subactions": TARGET_TO_SOURCE,
        "character_id": character_id,
        "character_name": identity_name,
        "sampled_workstation": {
            "floor_id": sample["floor_id"],
            "workstation_id": sample["workstation_id"],
            "group_id": sample["group"]["group_id"],
            "components": {
                name: {
                    "asset_id": placement["asset_id"],
                    "variant_id": placement["variant_id"],
                    "position_px": [int(placement["x_px"]), int(placement["y_px"])],
                    "layer": int(placement["layer"]),
                }
                for name, placement in sample["components"].items()
            },
        },
        "source_composition": source_details,
        "frame_records": frame_records,
        "outputs": {
            "gif": str(gif_path),
            "first_frame_png": str(first_frame_path),
            "manifest": str(manifest_path),
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20260831)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = render(args.seed, args.output_dir.resolve())
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
