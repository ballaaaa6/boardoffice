"""Render exact Work action and body/face asset reference sheets.

This is a presentation-only tool. It reads the canonical character asset,
frame, action and identity registries and writes review artifacts under an
explicit output directory. It never edits source artwork or runtime data.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
CHARACTER_ROOT = ROOT / "CHARACTER"
DEFAULT_OUTPUT = ROOT / "outputs" / "01a057c6-2d38-7be3-bfbe-4cadb1b6cc66"

sys.path.insert(0, str(ROOT))
from CHARACTER.RUNTIME.frame_renderer import CharacterFrameRenderer  # noqa: E402


BG = (7, 15, 28, 255)
PANEL = (17, 32, 52, 255)
PANEL_2 = (13, 25, 42, 255)
GRID_A = (31, 49, 70, 255)
GRID_B = (24, 40, 59, 255)
TEXT = (232, 240, 248, 255)
MUTED = (159, 178, 199, 255)
GOLD = (255, 209, 102, 255)
BODY_COLOR = (110, 231, 183, 255)
FACE_COLOR = (96, 165, 250, 255)
FRAME_COLOR = (244, 114, 182, 255)
MIRROR_COLOR = (196, 181, 253, 255)
SE_COLOR = (251, 191, 36, 255)
SW_COLOR = (52, 211, 153, 255)
NW_COLOR = (129, 140, 248, 255)
NE_COLOR = (96, 165, 250, 255)


def font_candidates() -> list[Path]:
    return [
        CHARACTER_ROOT / "ASSETS" / "dialogue" / "fonts" / "M+1p-medium.ttf",
        Path(r"C:\Windows\Fonts\consola.ttf"),
        Path(r"C:\Windows\Fonts\segoeui.ttf"),
    ]


def make_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in font_candidates():
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def checker(size: tuple[int, int], cell: int = 8) -> Image.Image:
    image = Image.new("RGBA", size, GRID_A)
    draw = ImageDraw.Draw(image)
    for y in range(0, size[1], cell):
        for x in range(0, size[0], cell):
            if ((x // cell) + (y // cell)) % 2:
                draw.rectangle((x, y, min(x + cell - 1, size[0] - 1), min(y + cell - 1, size[1] - 1)), fill=GRID_B)
    return image


def draw_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, size: int, fill=TEXT, *, anchor=None) -> None:
    draw.text(xy, value, font=make_font(size), fill=fill, anchor=anchor)


def draw_multiline(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, size: int, fill=TEXT, spacing: int = 4) -> None:
    draw.multiline_text(xy, value, font=make_font(size), fill=fill, spacing=spacing)


def panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], *, outline=SE_COLOR, fill=PANEL, radius: int = 12, width: int = 2) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def paste_centered(canvas: Image.Image, art: Image.Image, box: tuple[int, int, int, int], scale: int | None = None, *, background=True) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    if scale is None:
        scale = max(1, min((x1 - x0) // art.width, (y1 - y0) // art.height))
    scaled = art.resize((art.width * scale, art.height * scale), Image.Resampling.NEAREST)
    if background:
        tile = checker((x1 - x0, y1 - y0), cell=max(4, scale * 2))
        canvas.alpha_composite(tile, (x0, y0))
    px = x0 + ((x1 - x0) - scaled.width) // 2
    py = y0 + ((y1 - y0) - scaled.height) // 2
    canvas.alpha_composite(scaled, (px, py))
    return (px, py, px + scaled.width, py + scaled.height)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_context(character_id: str) -> dict:
    characters = load_json(CHARACTER_ROOT / "CHARACTERS" / "characters.json")
    identities = load_json(CHARACTER_ROOT / "IDENTITY" / "CHARACTERS" / "identity_cards.json")
    frames = load_json(CHARACTER_ROOT / "FRAME_RULES" / "frame_registry.json")
    actions = load_json(CHARACTER_ROOT / "ACTIONS" / "gds_standard_v1.json")
    profiles = load_json(ROOT / "CONTRACTS" / "work_pose_profiles.json")
    assets = load_json(CHARACTER_ROOT / "ASSETS" / "characters" / "asset_registry.json")

    character = next(c for c in characters["characters"] if c["character_id"] == character_id)
    identity = next(c for c in identities["characters"] if c["character_id"] == character_id)
    asset_records = {a["asset_id"]: a for a in assets["assets"]}
    body_id = character["composition"]["body"]
    face_id = character["composition"]["face"]
    body_record = asset_records[body_id]
    face_record = asset_records[face_id]
    body_path = CHARACTER_ROOT / "ASSETS" / "characters" / body_record["path"]
    face_path = CHARACTER_ROOT / "ASSETS" / "characters" / face_record["path"]
    return {
        "character": character,
        "identity": identity,
        "frames": frames,
        "actions": actions,
        "profiles": profiles,
        "assets": assets,
        "asset_records": asset_records,
        "body_id": body_id,
        "face_id": face_id,
        "body_record": body_record,
        "face_record": face_record,
        "body_path": body_path,
        "face_path": face_path,
    }


def display_frame(context: dict, frame_id: str) -> str:
    record = context["frames"]["frames"][frame_id]
    return record.get("display_id", frame_id)


def machine_display(context: dict, frame_id: str) -> str:
    shown = display_frame(context, frame_id)
    return shown if shown == frame_id else f"{shown} / {frame_id}"


def crop(sheet: Image.Image, source: list[int] | tuple[int, int, int, int]) -> Image.Image:
    x, y, w, h = source
    return sheet.crop((x, y, x + w, y + h))


def native_rule(context: dict, frame_id: str) -> dict:
    rule = context["frames"]["frames"][frame_id]
    if rule["kind"] != "native":
        return native_rule(context, rule["source_frame_id"])
    return rule


def work_bindings(context: dict) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    directions = context["actions"]["actions"]["work"]["directions"]
    for direction, payload in directions.items():
        for subaction, subpayload in payload["subactions"].items():
            for index, frame_id in enumerate(subpayload["frames"]):
                result[frame_id].append(f"{direction}:{subaction}[{index}]")
    return dict(result)


def turn_keys(direction: str) -> tuple[str, str]:
    if direction == "SW":
        return "turn_side_se", "turn_side_nw"
    return "turn_side_sw", "turn_side_ne"


def direction_color(direction: str):
    return {"SE": SE_COLOR, "SW": SW_COLOR, "NW": NW_COLOR, "NE": NE_COLOR}[direction]


def sequence_label(context: dict, frame_ids: Iterable[str]) -> str:
    return " → ".join(machine_display(context, frame_id) for frame_id in frame_ids)


def render_frame_set(context: dict, renderer: CharacterFrameRenderer, frame_ids: list[str]) -> dict[str, Image.Image]:
    return {frame_id: renderer.render_composition_frame(context["body_id"], context["face_id"], frame_id) for frame_id in frame_ids}


def draw_page_header(canvas: Image.Image, title: str, subtitle: str, *, y: int = 28) -> int:
    draw = ImageDraw.Draw(canvas)
    draw_text(draw, (40, y), title, 34, TEXT)
    draw_text(draw, (40, y + 52), subtitle, 19, MUTED)
    draw.line((40, y + 91, canvas.width - 40, y + 91), fill=(48, 72, 96, 255), width=2)
    return y + 116


def draw_direction_sheet(context: dict, renderer: CharacterFrameRenderer, output: Path) -> None:
    width = 3000
    row_h = 410
    left_w = 270
    header_h = 120
    top = 150
    footer_h = 155
    height = top + header_h + 4 * row_h + footer_h
    canvas = Image.new("RGBA", (width, height), BG)
    draw = ImageDraw.Draw(canvas)
    subtitle = (
        f"{context['character']['character_id']} | {context['identity']['full_name']} | "
        f"body {context['body_id']} + face {context['face_id']} | Work only"
    )
    draw_page_header(canvas, "WORK ACTION × DIRECTION", subtitle)

    columns = [
        "normal_work",
        "turn_side_sw",
        "turn_side_ne",
        "turn_side_se",
        "turn_side_nw",
        "happy",
    ]
    x0 = 30
    gap = 10
    cell_w = (width - 2 * x0 - left_w - len(columns) * gap) // len(columns)
    header_y = top
    panel(draw, (x0, header_y, x0 + left_w, header_y + header_h), outline=GOLD)
    draw_text(draw, (x0 + 18, header_y + 25), "DIRECTION", 20, GOLD)
    draw_text(draw, (x0 + 18, header_y + 57), "work direction", 16, MUTED)
    for index, label in enumerate(columns):
        cx = x0 + left_w + gap + index * (cell_w + gap)
        panel(draw, (cx, header_y, cx + cell_w, header_y + header_h), outline=(57, 89, 120, 255))
        draw_text(draw, (cx + cell_w // 2, header_y + 31), label.upper(), 20, TEXT, anchor="mm")
        if label == "normal_work":
            draw_text(draw, (cx + cell_w // 2, header_y + 70), "loop", 15, MUTED, anchor="mm")
        elif label == "happy":
            draw_text(draw, (cx + cell_w // 2, header_y + 70), "one-shot", 15, MUTED, anchor="mm")
        else:
            draw_text(draw, (cx + cell_w // 2, header_y + 70), "named target turn", 15, MUTED, anchor="mm")

    directions = context["actions"]["actions"]["work"]["directions"]
    target_by_direction = {
        "SE": {"turn_side_sw": "SW", "turn_side_ne": "NE"},
        "SW": {"turn_side_se": "SE", "turn_side_nw": "NW"},
        "NW": {"turn_side_sw": "SW", "turn_side_ne": "NE"},
        "NE": {"turn_side_se": "SE", "turn_side_nw": "NW"},
    }
    for row_index, direction in enumerate(("NE", "SE", "SW", "NW")):
        y = top + header_h + row_index * row_h
        color = direction_color(direction)
        node = directions[direction]
        profile = context["profiles"]["profiles"].get(direction)
        panel(draw, (x0, y, x0 + left_w, y + row_h - 10), outline=color)
        draw_text(draw, (x0 + 18, y + 25), direction, 30, color)
        if node.get("source") == "derived":
            source_direction = node.get("derived_from", "unknown")
            draw_text(draw, (x0 + 18, y + 74), "action-derived", 16, MUTED)
            draw_multiline(draw, (x0 + 18, y + 112), f"source: {source_direction}\nfinal composite: FLIP_LEFT_RIGHT", 15, MUTED, spacing=6)
        else:
            profile_mode = profile.get("mode", "native") if profile else "native"
            draw_text(draw, (x0 + 18, y + 74), profile_mode, 16, MUTED)
            draw_multiline(draw, (x0 + 18, y + 112), "source: native\ncanonical frame rules", 15, MUTED, spacing=6)
        draw_text(draw, (x0 + 18, y + row_h - 48), "seated work", 15, color)

        for col_index, key in enumerate(columns):
            cx = x0 + left_w + gap + col_index * (cell_w + gap)
            panel(draw, (cx, y, cx + cell_w, y + row_h - 10), outline=(57, 89, 120, 255), fill=PANEL_2)
            draw_text(draw, (cx + 18, y + 17), key, 17, color)
            payload = node["subactions"].get(key)
            if payload is None:
                draw_text(draw, (cx + 18, y + 55), "not used for this facing", 14, MUTED)
                draw_text(draw, (cx + cell_w // 2, y + 205), "—", 26, MUTED, anchor="mm")
                continue
            frames = payload["frames"]
            if key.startswith("turn_side_"):
                mapping = (profile or {}).get("turn_side_mapping", {}).get(key)
                target = mapping["target_idle_direction"] if mapping else target_by_direction[direction][key]
                axis = mapping["axis_direction"] if mapping else "derived axis"
                draw_text(draw, (cx + 18, y + 47), f"target idle: {target}  |  {axis}", 14, MUTED)
            elif key == "normal_work":
                draw_text(draw, (cx + 18, y + 47), "seated work loop", 14, MUTED)
            else:
                draw_text(draw, (cx + 18, y + 47), "seated happy", 14, MUTED)
            draw_text(draw, (cx + 18, y + 79), sequence_label(context, frames), 15, GOLD if len(frames) > 1 else TEXT)
            total_w = len(frames) * 138 + max(0, len(frames) - 1) * 16
            start_x = cx + (cell_w - total_w) // 2
            for frame_index, frame_id in enumerate(frames):
                art = renderer.render_composition_frame(context["body_id"], context["face_id"], frame_id)
                bx = start_x + frame_index * 154
                paste_centered(canvas, art, (bx, y + 120, bx + 138, y + 300), scale=4)
                draw_text(draw, (bx + 69, y + 325), machine_display(context, frame_id), 14, GOLD if frame_index == 0 else TEXT, anchor="ma")

    footer_y = top + header_h + 4 * row_h + 12
    draw.line((x0, footer_y, width - x0, footer_y), fill=(48, 72, 96, 255), width=2)
    draw_text(draw, (x0, footer_y + 20), "KEY", 16, GOLD)
    draw_multiline(
        draw,
        (x0 + 80, footer_y + 17),
        "SE = native M20–M24 + M42–M43     |     NW = native M25–M29 + M44–M45\n"
        "SW = mirror_y from SE     |     NE = mirror_y from NW. `turn_side_<direction>` names the partner's target idle facing.\n"
        "Character Work NE is available at the action layer; world-seat NE remains a separate verified-world gate.",
        16,
        MUTED,
        spacing=7,
    )
    canvas.save(output)


BODY_REGIONS = {
    (65, 20, 16, 13): ("B1", "M20 / M22 / M23"),
    (65, 33, 16, 13): ("B2", "M21 / M42 / M43"),
    (82, 21, 20, 21): ("B3", "M24"),
    (48, 51, 17, 15): ("B4", "M25 / M27 / M28"),
    (65, 46, 17, 13): ("B5", "M26 / M44 / M45"),
    (82, 42, 20, 24): ("B6", "M29"),
}

FACE_REGIONS = {
    (0, 0, 16, 15): ("H1", "M22 / M27 / M42 / M44  (SW head crop)"),
    (16, 0, 16, 15): ("H2", "M20 / M21  (SE head crop)"),
    (32, 0, 16, 15): ("H3", "M25 / M26  (NW head crop)"),
    (48, 0, 16, 15): ("H4", "M23 / M28 / M43 / M45  (NE head crop)"),
    (0, 15, 16, 15): ("H5", "M24  (happy crop)"),
    (16, 15, 16, 15): ("H6", "M29  (happy crop)"),
}


WORK_NATIVE_FRAMES = [
    "M20", "M21", "M22", "M23", "M24",
    "M25", "M26", "M27", "M28", "M29",
    "M42", "M43", "M44", "M45",
]
WORK_DERIVED_FRAMES = [
    "Mp20", "Mp21", "Mp22", "Mp23", "Mp24",
    "Mp25", "Mp26", "Mp27", "Mp28", "Mp29",
    "Mp42", "Mp43", "Mp44", "Mp45",
]


def draw_annotated_atlas(canvas: Image.Image, sheet: Image.Image, box: tuple[int, int, int, int], regions: dict, scale: int) -> None:
    x0, y0, x1, y1 = box
    tile = sheet.resize((sheet.width * scale, sheet.height * scale), Image.Resampling.NEAREST)
    background = checker(tile.size, cell=max(4, scale * 2))
    background.alpha_composite(tile)
    canvas.alpha_composite(background, (x0, y0))
    draw = ImageDraw.Draw(canvas)
    for source, (label, _) in regions.items():
        x, y, w, h = source
        px0, py0 = x0 + x * scale, y0 + y * scale
        px1, py1 = px0 + w * scale, py0 + h * scale
        draw.rectangle((px0, py0, px1 - 1, py1 - 1), outline=GOLD, width=3)
        draw.rectangle((px0, py0, px0 + 42, py0 + 25), fill=(7, 15, 28, 220))
        draw_text(draw, (px0 + 7, py0 + 3), label, 15, GOLD)


def draw_region_legend(draw: ImageDraw.ImageDraw, xy: tuple[int, int], title: str, regions: dict, size: int = 15) -> int:
    x, y = xy
    draw_text(draw, (x, y), title, 17, TEXT)
    y += 31
    for source, (label, use) in regions.items():
        draw_text(draw, (x, y), f"{label}  src {list(source)}", size, GOLD)
        draw_text(draw, (x + 220, y), use, size, MUTED)
        y += 27
    return y


def draw_source_atlas_section(context: dict, canvas: Image.Image, y: int) -> int:
    draw = ImageDraw.Draw(canvas)
    draw_text(draw, (40, y), "SOURCE ATLAS CROPS USED BY WORK", 22, GOLD)
    draw_text(draw, (40, y + 34), "B*/H* are labels on this review sheet only; the runtime names the crop by its frame rule `src` rectangle.", 15, MUTED)
    y += 72
    body_panel = (40, y, 1050, y + 600)
    face_panel = (1070, y, 2160, y + 600)
    panel(draw, body_panel, outline=BODY_COLOR)
    panel(draw, face_panel, outline=FACE_COLOR)
    draw_text(draw, (65, y + 22), f"BODY  {context['body_id']}  |  {context['body_record']['path']}  |  102×66", 18, BODY_COLOR)
    draw_text(draw, (1095, y + 22), f"HEAD/FACE  {context['face_id']}  |  {context['face_record']['path']}  |  80×30", 18, FACE_COLOR)
    body = Image.open(context["body_path"]).convert("RGBA")
    face = Image.open(context["face_path"]).convert("RGBA")
    draw_annotated_atlas(canvas, body, (65, y + 65, 65 + body.width * 4, y + 65 + body.height * 4), BODY_REGIONS, 4)
    draw_annotated_atlas(canvas, face, (1095, y + 65, 1095 + face.width * 6, y + 65 + face.height * 6), FACE_REGIONS, 6)
    draw_region_legend(draw, (65, y + 355), "BODY CROPS", BODY_REGIONS, 14)
    draw_region_legend(draw, (1095, y + 355), "HEAD CROPS", FACE_REGIONS, 14)
    return y + 640


def frame_caption(context: dict, frame_id: str) -> str:
    bindings = work_bindings(context).get(frame_id, [])
    return "; ".join(bindings)


def draw_formula_card(
    context: dict,
    renderer: CharacterFrameRenderer,
    canvas: Image.Image,
    box: tuple[int, int, int, int],
    frame_id: str,
    body_sheet: Image.Image,
    face_sheet: Image.Image,
) -> None:
    draw = ImageDraw.Draw(canvas)
    x0, y0, x1, y1 = box
    rule = native_rule(context, frame_id)
    body_src = tuple(rule["body"]["src"])
    face_src = tuple(rule["face"]["src"])
    body_crop = crop(body_sheet, body_src)
    face_crop = crop(face_sheet, face_src)
    result = renderer.render_composition_frame(context["body_id"], context["face_id"], frame_id)
    panel(draw, box, outline=FRAME_COLOR, fill=PANEL_2)
    draw_text(draw, (x0 + 18, y0 + 14), machine_display(context, frame_id), 20, FRAME_COLOR)
    draw_text(draw, (x0 + 168, y0 + 17), frame_caption(context, frame_id), 13, MUTED)

    art_y0 = y0 + 48
    body_box = (x0 + 22, art_y0 + 17, x0 + 160, art_y0 + 142)
    face_box = (x0 + 220, art_y0 + 17, x0 + 358, art_y0 + 142)
    result_box = (x0 + 420, art_y0, x0 + 575, art_y0 + 160)
    paste_centered(canvas, body_crop, body_box, scale=4)
    paste_centered(canvas, face_crop, face_box, scale=5)
    paste_centered(canvas, result, result_box, scale=3)
    draw_text(draw, (x0 + 188, art_y0 + 63), "+", 28, GOLD, anchor="mm")
    draw_text(draw, (x0 + 388, art_y0 + 63), "=", 28, GOLD, anchor="mm")
    body_label = BODY_REGIONS.get(body_src, ("B?", ""))[0]
    face_label = FACE_REGIONS.get(face_src, ("H?", ""))[0]
    draw_text(draw, (x0 + 91, art_y0 + 150), body_label, 15, BODY_COLOR, anchor="ma")
    draw_text(draw, (x0 + 289, art_y0 + 150), face_label, 15, FACE_COLOR, anchor="ma")
    draw_text(draw, (x0 + 497, art_y0 + 166), "32×42 output", 13, MUTED, anchor="ma")

    meta_x = x0 + 610
    body_dst = rule["body"]["dst"]
    face_dst = rule["face"]["dst"]
    origin = context["frames"]["render_profile"]["origin"]
    body_canvas_dst = [origin[0] + body_dst[0], origin[1] + body_dst[1]]
    face_canvas_dst = [origin[0] + face_dst[0], origin[1] + face_dst[1]]
    draw_text(draw, (meta_x, art_y0 + 5), "BODY", 14, BODY_COLOR)
    draw_text(draw, (meta_x + 72, art_y0 + 5), f"src {list(body_src)}", 14, TEXT)
    draw_text(draw, (meta_x + 72, art_y0 + 31), f"dst rel {body_dst}  → canvas {body_canvas_dst}", 13, MUTED)
    draw_text(draw, (meta_x, art_y0 + 66), "HEAD", 14, FACE_COLOR)
    draw_text(draw, (meta_x + 72, art_y0 + 66), f"src {list(face_src)}", 14, TEXT)
    draw_text(draw, (meta_x + 72, art_y0 + 92), f"dst rel {face_dst}  → canvas {face_canvas_dst}", 13, MUTED)
    draw_text(draw, (meta_x, art_y0 + 129), "order", 14, GOLD)
    draw_text(draw, (meta_x + 72, art_y0 + 129), "body first, then head", 13, MUTED)


def draw_component_sheet(context: dict, renderer: CharacterFrameRenderer, output: Path) -> None:
    width = 2200
    source_y = 155
    source_bottom = source_y + 640
    formula_y = source_bottom + 40
    card_w = 1050
    card_h = 255
    gap = 20
    formula_rows = math.ceil(len(WORK_NATIVE_FRAMES) / 2)
    derived_y = formula_y + 70 + formula_rows * card_h + 45
    derived_columns = 5
    derived_card_h = 320
    derived_rows = math.ceil(len(WORK_DERIVED_FRAMES) / derived_columns)
    derived_h = derived_rows * (derived_card_h + 20) + 100
    height = derived_y + derived_h + 70
    canvas = Image.new("RGBA", (width, height), BG)
    subtitle = (
        f"{context['character']['character_id']} | {context['identity']['full_name']} | "
        f"canonical composition: {context['body_id']} + {context['face_id']} | exact crop recipes"
    )
    draw_page_header(canvas, "WORK FRAME COMPONENT RECIPES", subtitle)
    draw_source_atlas_section(context, canvas, source_y)
    draw = ImageDraw.Draw(canvas)
    draw_text(draw, (40, formula_y), "NATIVE M-FRAMES: BODY CROP + HEAD CROP = FINAL FRAME", 22, GOLD)
    draw_text(draw, (40, formula_y + 34), "The crop rectangles below are from the selected character's atlases; every canonical character uses the same frame geometry with its own body/face asset IDs.", 15, MUTED)
    body_sheet = Image.open(context["body_path"]).convert("RGBA")
    face_sheet = Image.open(context["face_path"]).convert("RGBA")
    for index, frame_id in enumerate(WORK_NATIVE_FRAMES):
        column = index % 2
        row = index // 2
        x = 40 + column * (card_w + gap)
        y = formula_y + 70 + row * card_h
        draw_formula_card(context, renderer, canvas, (x, y, x + card_w, y + card_h - 10), frame_id, body_sheet, face_sheet)

    draw_text(draw, (40, derived_y), "DERIVED MIRROR FRAMES: MIRROR THE COMPLETE NATIVE COMPOSITE", 22, MIRROR_COLOR)
    draw_text(draw, (40, derived_y + 34), "Mp20–Mp29 and Mp42–Mp45 have no new body/head crop; the renderer flips the final native 32×42 image left↔right exactly once.", 15, MUTED)
    mirror_y = derived_y + 76
    for index, frame_id in enumerate(WORK_DERIVED_FRAMES):
        row, column = divmod(index, derived_columns)
        x = 40 + column * 425
        y = mirror_y + row * (derived_card_h + 20)
        source_id = context["frames"]["frames"][frame_id]["source_frame_id"]
        panel(draw, (x, y, x + 400, y + derived_card_h), outline=MIRROR_COLOR, fill=PANEL_2)
        draw_text(draw, (x + 18, y + 18), machine_display(context, frame_id), 18, MIRROR_COLOR)
        draw_text(draw, (x + 18, y + 49), f"source: {machine_display(context, source_id)}", 14, MUTED)
        source_art = renderer.render_composition_frame(context["body_id"], context["face_id"], source_id)
        result_art = renderer.render_composition_frame(context["body_id"], context["face_id"], frame_id)
        paste_centered(canvas, source_art, (x + 25, y + 85, x + 165, y + 270), scale=4)
        draw_text(draw, (x + 190, y + 168), "FLIP\nLEFT↔RIGHT", 16, GOLD, anchor="mm")
        paste_centered(canvas, result_art, (x + 235, y + 85, x + 375, y + 270), scale=4)
        draw_text(draw, (x + 95, y + 284), machine_display(context, source_id), 13, TEXT, anchor="ma")
        draw_text(draw, (x + 305, y + 284), machine_display(context, frame_id), 13, MIRROR_COLOR, anchor="ma")
    footer_y = mirror_y + derived_rows * (derived_card_h + 20) + 15
    draw_text(draw, (40, footer_y), "Do not double-mirror materialized frames. SW derives from SE and NE derives from NW at the complete-frame level.", 16, MIRROR_COLOR)
    canvas.save(output)


def draw_asset_catalog(context: dict, output: Path, kind: str) -> None:
    records = sorted((a for a in context["assets"]["assets"] if a["kind"] == kind), key=lambda a: a["index"])
    if kind == "body":
        columns, tile_w, tile_h, scale = 4, 465, 335, 3
        title = "BODY ASSET CATALOG"
        accent = BODY_COLOR
        asset_label = "body"
    else:
        columns, tile_w, tile_h, scale = 5, 390, 270, 4
        title = "HEAD / FACE ASSET CATALOG"
        accent = FACE_COLOR
        asset_label = "face"
    rows = math.ceil(len(records) / columns)
    width = columns * tile_w + 2 * 30 + (columns - 1) * 10
    height = 175 + rows * tile_h + 80
    canvas = Image.new("RGBA", (width, height), BG)
    draw = ImageDraw.Draw(canvas)
    draw_page_header(canvas, title, f"Canonical {asset_label} assets | {len(records)} registered files | IDs and filenames are the authoritative names", y=25)
    for index, record in enumerate(records):
        row, col = divmod(index, columns)
        x = 30 + col * (tile_w + 10)
        y = 150 + row * tile_h
        is_selected = record["asset_id"] in {context["body_id"], context["face_id"]}
        panel(draw, (x, y, x + tile_w, y + tile_h - 10), outline=accent if is_selected else (57, 89, 120, 255), fill=PANEL_2)
        draw_text(draw, (x + 16, y + 14), record["asset_id"], 18, accent if is_selected else TEXT)
        draw_text(draw, (x + 16, y + 43), record["path"], 15, MUTED)
        draw_text(draw, (x + 16, y + 70), f"index {record['index']:03d}  |  {record['dimensions'][0]}×{record['dimensions'][1]}  |  refs {record.get('source_reference_count', 0)}", 14, MUTED)
        sheet_path = CHARACTER_ROOT / "ASSETS" / "characters" / record["path"]
        with Image.open(sheet_path) as source:
            sheet = source.convert("RGBA")
        paste_centered(canvas, sheet, (x + 16, y + 98, x + tile_w - 16, y + tile_h - 24), scale=scale)
        if is_selected:
            draw_text(draw, (x + tile_w - 16, y + 14), "SELECTED", 13, accent, anchor="ra")
    footer_y = 150 + rows * tile_h + 15
    draw.line((30, footer_y, width - 30, footer_y), fill=(48, 72, 96, 255), width=2)
    draw_text(draw, (30, footer_y + 25), "Note: the registry has numeric canonical IDs only; it does not define human-readable clothing, hair or costume names. Frame-specific pieces are crop rectangles in frame_registry.json.", 15, MUTED)
    canvas.save(output)


def write_maps(context: dict, output_dir: Path) -> tuple[Path, Path]:
    bindings = work_bindings(context)
    frame_registry = context["frames"]["frames"]
    origin = context["frames"]["render_profile"]["origin"]
    rows: list[dict[str, str]] = []
    for frame_id in WORK_NATIVE_FRAMES + WORK_DERIVED_FRAMES:
        record = frame_registry[frame_id]
        if record["kind"] == "native":
            rule = record
            bsrc = rule["body"]["src"]
            fsrc = rule["face"]["src"]
            bdst = rule["body"]["dst"]
            fdst = rule["face"]["dst"]
            row = {
                "character_id": context["character"]["character_id"],
                "body_asset_id": context["body_id"],
                "body_file": context["body_record"]["path"],
                "face_asset_id": context["face_id"],
                "face_file": context["face_record"]["path"],
                "frame_id": frame_id,
                "display_id": record.get("display_id", frame_id),
                "kind": record["kind"],
                "source_frame_id": "",
                "transform": "",
                "uses": "; ".join(bindings.get(frame_id, [])),
                "body_src": str(bsrc),
                "body_dst_relative": str(bdst),
                "body_dst_canvas": str([origin[0] + bdst[0], origin[1] + bdst[1]]),
                "face_src": str(fsrc),
                "face_dst_relative": str(fdst),
                "face_dst_canvas": str([origin[0] + fdst[0], origin[1] + fdst[1]]),
            }
        else:
            row = {
                "character_id": context["character"]["character_id"],
                "body_asset_id": context["body_id"],
                "body_file": context["body_record"]["path"],
                "face_asset_id": context["face_id"],
                "face_file": context["face_record"]["path"],
                "frame_id": frame_id,
                "display_id": record.get("display_id", frame_id),
                "kind": record["kind"],
                "source_frame_id": record["source_frame_id"],
                "transform": record["transform"],
                "uses": "; ".join(bindings.get(frame_id, [])),
                "body_src": "",
                "body_dst_relative": "",
                "body_dst_canvas": "",
                "face_src": "",
                "face_dst_relative": "",
                "face_dst_canvas": "",
            }
        rows.append(row)
    frame_csv = output_dir / "work_frame_component_map.csv"
    fieldnames = list(rows[0].keys())
    with frame_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    asset_csv = output_dir / "body_head_asset_catalog.csv"
    asset_fields = ["asset_id", "kind", "index", "path", "dimensions", "source_reference_count", "sha256"]
    with asset_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=asset_fields)
        writer.writeheader()
        for record in sorted(context["assets"]["assets"], key=lambda a: (a["kind"], a["index"])):
            if record["kind"] not in {"body", "face"}:
                continue
            writer.writerow({
                "asset_id": record["asset_id"],
                "kind": record["kind"],
                "index": record["index"],
                "path": record["path"],
                "dimensions": record["dimensions"],
                "source_reference_count": record.get("source_reference_count", 0),
                "sha256": record["sha256"],
            })
    return frame_csv, asset_csv


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_manifest(context: dict, output_dir: Path, files: list[Path]) -> None:
    manifest = {
        "schema": "gds.work_frame_reference_artifacts.v1",
        "character_id": context["character"]["character_id"],
        "character_name": context["identity"]["full_name"],
        "body_asset_id": context["body_id"],
        "face_asset_id": context["face_id"],
        "source_registries": [
            "CHARACTER/ACTIONS/gds_standard_v1.json",
            "CHARACTER/FRAME_RULES/frame_registry.json",
            "CHARACTER/ASSETS/characters/asset_registry.json",
            "CONTRACTS/work_pose_profiles.json",
        ],
        "files": [
            {"path": path.name, "sha256": sha256(path), "dimensions": list(Image.open(path).size) if path.suffix.lower() == ".png" else None}
            for path in files
        ],
    }
    (output_dir / "reference_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--character", default="RND_F_004")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    context = load_context(args.character)
    renderer = CharacterFrameRenderer(CHARACTER_ROOT, verify_asset_hashes=True)
    direction_path = output_dir / f"{args.character}_work_direction_sheet.png"
    component_path = output_dir / f"{args.character}_work_components_sheet.png"
    body_path = output_dir / "body_asset_catalog.png"
    face_path = output_dir / "face_asset_catalog.png"
    draw_direction_sheet(context, renderer, direction_path)
    draw_component_sheet(context, renderer, component_path)
    draw_asset_catalog(context, body_path, "body")
    draw_asset_catalog(context, face_path, "face")
    frame_csv, asset_csv = write_maps(context, output_dir)
    write_manifest(context, output_dir, [direction_path, component_path, body_path, face_path, frame_csv, asset_csv])
    print(json.dumps({
        "character_id": context["character"]["character_id"],
        "body_asset_id": context["body_id"],
        "face_asset_id": context["face_id"],
        "output_dir": str(output_dir),
        "files": [direction_path.name, component_path.name, body_path.name, face_path.name, frame_csv.name, asset_csv.name, "reference_manifest.json"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
