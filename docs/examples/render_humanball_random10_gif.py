"""Make a review-only animated HumanBall contact sheet from ten new icons.

The selected icon stays fixed for the ten visible frames of its HumanBall
cycle; only its native motion changes. Frames 10 and 11 are hidden, matching
the existing HumanBall timing contract. This script never touches registries
or canonical assets.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from RUNTIME.central_core import CentralGameCore


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "LOCAL_REVIEW/humanball_office_200_cinematic_v3"
OUTPUT = SOURCE / "floor00_random10_gif"
SEED = "humanball-office-review-floor00-10"
FLOOR_ID = "floor00"
WORKSTATION_ID = "ceo"
CROP = (180, 210, 340, 370)
SCALE = 2
TILE_W = (CROP[2] - CROP[0]) * SCALE
TILE_H = (CROP[3] - CROP[1]) * SCALE + 35
SHEET_W = TILE_W * 5 + 60
SHEET_H = 45 + TILE_H * 2 + 30
BG = "#252830"
TEXT = "#FFFBF0"
MUTED = "#B5BBC4"


def load_font(size: int):
    path = Path("C:/Windows/Fonts/tahoma.ttf")
    return ImageFont.truetype(str(path), size) if path.exists() else ImageFont.load_default()


def main() -> None:
    manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
    all_items = [
        {"category_id": category["id"], "category_title": category["title"], **item}
        for category in manifest["categories"]
        for item in category["items"]
    ]
    selected = random.Random(SEED).sample(all_items, 10)

    core = CentralGameCore(ROOT)
    assignment = {"workstation_id": WORKSTATION_ID, "character": 0, "subaction": "normal_work"}
    resolved = {**assignment, "character_id": core.resolve_character_id(0)}
    data, _ = core.work_seats._resolve_floor_assignment_data(
        FLOOR_ID, [resolved], frame_index=0, character_frame_index=0, pc_frame_index=0
    )
    seat = data[WORKSTATION_ID]
    direction = seat["direction"]
    registry = json.loads((ROOT / "CHARACTER/EFFECTS/humanball_v1.json").read_text(encoding="utf-8"))
    offsets = registry["motion_offsets_from_character_top_left_px"][direction]
    assert len(offsets) == 10

    icon_images = {
        item["id"]: Image.open(SOURCE / item["category_id"] / (item["id"] + ".png")).convert("RGBA")
        for item in selected
    }
    base_frames = [
        core.render_floor_with_work_effects(
            FLOOR_ID,
            [assignment],
            frame_index=frame,
            character_frame_index=0,
            pc_frame_index=0,
        ).convert("RGBA")
        for frame in range(12)
    ]
    title_font = load_font(20)
    label_font = load_font(14)

    def make_tile(item, frame_index: int) -> Image.Image:
        scene = base_frames[frame_index].copy()
        offset = offsets[frame_index] if frame_index < 10 else None
        if offset is not None:
            icon = icon_images[item["id"]]
            scene.alpha_composite(
                icon,
                (int(seat["human_x_px"]) + int(offset[0]), int(seat["human_y_px"]) + int(offset[1])),
            )
        crop = scene.crop(CROP).resize((TILE_W, TILE_W), Image.Resampling.NEAREST)
        tile = Image.new("RGB", (TILE_W, TILE_H), BG)
        tile.paste(crop.convert("RGB"), (0, 0))
        draw = ImageDraw.Draw(tile)
        label = f"{item['index']:02}  {item['label']}"
        draw.text((8, TILE_W + 7), label, font=label_font, fill=TEXT)
        return tile

    def make_sheet(frame_index: int) -> Image.Image:
        sheet = Image.new("RGB", (SHEET_W, SHEET_H), BG)
        draw = ImageDraw.Draw(sheet)
        heading = "floor00 / CEO / HumanBall  —  10 random office icons"
        phase = "visible" if frame_index < 10 else "hidden"
        heading += f"  / frame {frame_index + 1}/12 ({phase})"
        draw.text((20, 12), heading, font=title_font, fill=TEXT)
        for index, item in enumerate(selected):
            x = 10 + (index % 5) * (TILE_W + 10)
            y = 45 + (index // 5) * (TILE_H + 10)
            sheet.paste(make_tile(item, frame_index), (x, y))
        return sheet

    OUTPUT.mkdir(parents=True, exist_ok=True)
    frames = [make_sheet(index) for index in range(12)]
    frames[0].save(
        OUTPUT / "floor00_random10_humanball_sheet.png",
        format="PNG",
    )
    frames[0].save(
        OUTPUT / "floor00_random10_humanball_sheet.gif",
        save_all=True,
        append_images=frames[1:],
        duration=240,
        loop=0,
        disposal=2,
        optimize=False,
    )
    selection = {
        "seed": SEED,
        "floor_id": FLOOR_ID,
        "workstation_id": WORKSTATION_ID,
        "direction": direction,
        "character_frame_locked": 0,
        "crop_box_native": list(CROP),
        "scale": SCALE,
        "humanball_timing": {
            "total_frames": 12,
            "visible_frames": 10,
            "hidden_frames": 2,
            "frame_ms": 240,
            "icon_changes_during_cycle": False,
        },
        "items": [
            {key: item[key] for key in ("index", "id", "label", "category_id", "category_title")}
            for item in selected
        ],
    }
    (OUTPUT / "selection.json").write_text(
        json.dumps(selection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(OUTPUT), "frames": len(frames), "items": selected}, ensure_ascii=False))


if __name__ == "__main__":
    main()
