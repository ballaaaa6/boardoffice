"""Render a review-only full action sheet with the canonical Work turn recipe.

The sheet reads the canonical action/frame registries and also exposes the
approved body/head crop recipe behind the four-way Work turns:
the head stays on the partner-facing crop while the seated body alternates
between the two normal-work body poses. SW preview frames mirror the complete
SE preview composite once and NE preview frames mirror the complete NW
composite once.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
CHARACTER_ROOT = ROOT / "CHARACTER"
DEFAULT_OUTPUT = ROOT / "outputs" / "01a057c6-2d38-7be3-bfbe-4cadb1b6cc66"
sys.path.insert(0, str(ROOT))

from TOOLS.render_work_frame_reference import (  # noqa: E402
    BG,
    BODY_COLOR,
    FACE_COLOR,
    FRAME_COLOR,
    GOLD,
    MIRROR_COLOR,
    MUTED,
    NE_COLOR,
    NW_COLOR,
    PANEL,
    PANEL_2,
    SE_COLOR,
    SW_COLOR,
    CharacterFrameRenderer,
    direction_color,
    display_frame,
    draw_multiline,
    draw_text,
    load_context,
    machine_display,
    make_font,
    panel,
    paste_centered,
)


def native_rule(context: dict, frame_id: str) -> dict:
    record = context["frames"]["frames"][frame_id]
    if record["kind"] == "native":
        return record
    return native_rule(context, record["source_frame_id"])


def crop(sheet: Image.Image, source: list[int]) -> Image.Image:
    x, y, w, h = source
    return sheet.crop((x, y, x + w, y + h))


def compose_preview_frame(
    context: dict,
    body_sheet: Image.Image,
    face_sheet: Image.Image,
    body_rule_frame: str,
    face_rule_frame: str,
) -> Image.Image:
    """Compose a 32x42 frame from the body rule of one native frame and the
    face rule of another native frame, using the canonical renderer geometry.
    """
    body_rule = native_rule(context, body_rule_frame)
    face_rule = native_rule(context, face_rule_frame)
    origin = context["frames"]["render_profile"]["origin"]
    canvas_size = tuple(context["frames"]["render_profile"]["canvas"])
    canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    body = crop(body_sheet, body_rule["body"]["src"])
    face = crop(face_sheet, face_rule["face"]["src"])
    body_dst = body_rule["body"]["dst"]
    face_dst = face_rule["face"]["dst"]
    canvas.alpha_composite(body, (origin[0] + body_dst[0], origin[1] + body_dst[1]))
    canvas.alpha_composite(face, (origin[0] + face_dst[0], origin[1] + face_dst[1]))
    return canvas


def build_proposed_sequences(context: dict) -> tuple[dict, dict]:
    body_sheet = Image.open(context["body_path"]).convert("RGBA")
    face_sheet = Image.open(context["face_path"]).convert("RGBA")

    def make(label: str, body_frame: str, face_frame: str) -> dict:
        return {
            "label": label,
            "body_frame": body_frame,
            "face_frame": face_frame,
            "image": compose_preview_frame(context, body_sheet, face_sheet, body_frame, face_frame),
        }

    native = {
        "SE:turn_side_sw": [make("SE/turn_side_sw/frame_0", "M20", "M22"), make("SE/turn_side_sw/frame_1", "M21", "M22")],
        "SE:turn_side_ne": [make("SE/turn_side_ne/frame_0", "M20", "M23"), make("SE/turn_side_ne/frame_1", "M21", "M23")],
        "NW:turn_side_sw": [make("NW/turn_side_sw/frame_0", "M25", "M27"), make("NW/turn_side_sw/frame_1", "M26", "M27")],
        "NW:turn_side_ne": [make("NW/turn_side_ne/frame_0", "M25", "M28"), make("NW/turn_side_ne/frame_1", "M26", "M28")],
    }
    mirrored = {
        "SW:turn_side_se": [
            {**item, "label": f"SW/turn_side_se/frame_{index}", "image": item["image"].transpose(Image.Transpose.FLIP_LEFT_RIGHT), "mirror_of": item["label"]}
            for index, item in enumerate(native["SE:turn_side_sw"])
        ],
        "SW:turn_side_nw": [
            {**item, "label": f"SW/turn_side_nw/frame_{index}", "image": item["image"].transpose(Image.Transpose.FLIP_LEFT_RIGHT), "mirror_of": item["label"]}
            for index, item in enumerate(native["SE:turn_side_ne"])
        ],
        "NE:turn_side_se": [
            {**item, "label": f"NE/turn_side_se/frame_{index}", "image": item["image"].transpose(Image.Transpose.FLIP_LEFT_RIGHT), "mirror_of": item["label"]}
            for index, item in enumerate(native["NW:turn_side_sw"])
        ],
        "NE:turn_side_nw": [
            {**item, "label": f"NE/turn_side_nw/frame_{index}", "image": item["image"].transpose(Image.Transpose.FLIP_LEFT_RIGHT), "mirror_of": item["label"]}
            for index, item in enumerate(native["NW:turn_side_ne"])
        ],
    }
    return native, mirrored


def canonical_items(renderer: CharacterFrameRenderer, context: dict, frame_ids: list[str]) -> list[dict]:
    return [
        {
            "label": machine_display(context, frame_id),
            "frame_id": frame_id,
            "image": renderer.render_composition_frame(context["body_id"], context["face_id"], frame_id),
        }
        for frame_id in frame_ids
    ]


def draw_action_cell(canvas: Image.Image, box: tuple[int, int, int, int], title: str, subtitle: str, items: list[dict], *, outline=(57, 89, 120, 255), empty: bool = False) -> None:
    draw = ImageDraw.Draw(canvas)
    x0, y0, x1, y1 = box
    panel(draw, box, outline=outline, fill=PANEL_2)
    draw_text(draw, (x0 + 15, y0 + 13), title, 16, outline if outline != (57, 89, 120, 255) else TEXT)
    draw_text(draw, (x0 + 15, y0 + 42), subtitle, 13, MUTED)
    if empty:
        draw_text(draw, ((x0 + x1) // 2, (y0 + y1) // 2 + 8), "—", 25, MUTED, anchor="mm")
        return
    labels = " → ".join(item["label"] for item in items)
    draw_text(draw, (x0 + 15, y0 + 69), labels, 13, GOLD if len(items) > 1 else TEXT)
    art_w = 130
    art_h = 165
    gap = 16
    total_w = len(items) * art_w + max(0, len(items) - 1) * gap
    start_x = x0 + ((x1 - x0) - total_w) // 2
    for index, item in enumerate(items):
        ax = start_x + index * (art_w + gap)
        paste_centered(canvas, item["image"], (ax, y0 + 100, ax + art_w, y0 + 100 + art_h), scale=3)
        draw_text(draw, (ax + art_w // 2, y0 + 280), item["label"], 12, GOLD if index == 0 else TEXT, anchor="ma")


TEXT = (232, 240, 248, 255)


def draw_full_action_sheet(context: dict, renderer: CharacterFrameRenderer, native_proposed: dict, mirrored_proposed: dict, output: Path) -> None:
    width = 2360
    left_w = 315
    gap = 10
    x0 = 30
    cell_w = (width - 2 * x0 - left_w - 4 * gap) // 4
    header_h = 110
    row_h = 305
    top = 150
    row_count = 9
    event_h = 265
    height = top + header_h + row_count * row_h + 35 + event_h + 80
    canvas = Image.new("RGBA", (width, height), BG)
    subtitle = (
        f"{context['character']['character_id']} | {context['identity']['full_name']} | "
        f"body {context['body_id']} + face {context['face_id']} | canonical Work turn recipes"
    )
    draw_page_header = __import__("TOOLS.render_work_frame_reference", fromlist=["draw_page_header"]).draw_page_header
    draw_page_header(canvas, "CHARACTER ACTION SHEET — CANONICAL WORK TURNS", subtitle)
    draw = ImageDraw.Draw(canvas)
    directions = ("NE", "SE", "SW", "NW")
    col_x = {direction: x0 + left_w + gap + i * (cell_w + gap) for i, direction in enumerate(directions)}
    header_y = top
    panel(draw, (x0, header_y, x0 + left_w, header_y + header_h), outline=GOLD)
    draw_text(draw, (x0 + 18, header_y + 26), "ACTION", 21, GOLD)
    draw_text(draw, (x0 + 18, header_y + 62), "all canonical groups", 15, MUTED)
    for direction in directions:
        color = direction_color(direction)
        cx = col_x[direction]
        panel(draw, (cx, header_y, cx + cell_w, header_y + header_h), outline=color)
        draw_text(draw, (cx + cell_w // 2, header_y + 32), direction, 22, color, anchor="mm")
        draw_text(draw, (cx + cell_w // 2, header_y + 71), "facing / source direction", 14, MUTED, anchor="mm")

    action_rows = [
        ("IDLE", "stand / loop", "idle", ("idle", "idle")),
        ("MOVE", "walk / loop", "move", ("move", "move")),
        ("VARIANTS", "standing pose variant", "variants", ("variants", "variants")),
        ("WORK · NORMAL_WORK", "seated work / loop", "work:normal_work", ("work", "normal_work")),
        ("WORK · TURN_SIDE_SW", "fixed head · target SW", "work:turn_side_sw", ("work", "turn_side_sw")),
        ("WORK · TURN_SIDE_NE", "fixed head · target NE", "work:turn_side_ne", ("work", "turn_side_ne")),
        ("WORK · TURN_SIDE_SE", "fixed head · target SE", "work:turn_side_se", ("work", "turn_side_se")),
        ("WORK · TURN_SIDE_NW", "fixed head · target NW", "work:turn_side_nw", ("work", "turn_side_nw")),
        ("WORK · HAPPY", "seated happy / one-shot", "work:happy", ("work", "happy")),
    ]
    actions = context["actions"]["actions"]
    for row_index, (label, sublabel, key, _) in enumerate(action_rows):
        y = top + header_h + row_index * row_h
        accent = FRAME_COLOR if key.startswith("work") else GOLD
        panel(draw, (x0, y, x0 + left_w, y + row_h - 10), outline=accent)
        draw_text(draw, (x0 + 18, y + 22), label, 17, accent)
        draw_multiline(draw, (x0 + 18, y + 62), sublabel, 15, MUTED, spacing=6)

        for direction in directions:
            cx = col_x[direction]
            items: list[dict]
            title = ""
            subtitle_cell = ""
            empty = False
            if key == "idle":
                frames = actions["idle"]["directions"][direction]["frames"]
                items = canonical_items(renderer, context, frames)
                title, subtitle_cell = "idle", "canonical"
            elif key == "move":
                frames = actions["move"]["directions"][direction]["frames"]
                items = canonical_items(renderer, context, frames)
                title, subtitle_cell = "move", "canonical"
            elif key == "variants":
                frames = actions["variants"]["directions"][direction]["frames"]
                items = canonical_items(renderer, context, frames)
                title, subtitle_cell = "variants", "canonical"
            elif key.startswith("work:"):
                subaction = key.split(":", 1)[1]
                payload = actions["work"]["directions"][direction]["subactions"].get(subaction)
                if payload is None:
                    items, title, subtitle_cell, empty = [], subaction, "not used for this facing", True
                else:
                    items = canonical_items(renderer, context, payload["frames"])
                    title = subaction
                    subtitle_cell = "canonical loop" if subaction == "normal_work" else "canonical one-shot" if subaction == "happy" else "fixed head · alternating body"
            else:
                raise ValueError(f"Unhandled action sheet row: {key}")
            draw_action_cell(canvas, (cx, y, cx + cell_w, y + row_h - 10), title, subtitle_cell, items, outline=direction_color(direction), empty=empty)

    event_y = top + header_h + row_count * row_h + 20
    draw.line((x0, event_y, width - x0, event_y), fill=(48, 72, 96, 255), width=2)
    draw_text(draw, (x0, event_y + 22), "DIRECTIONLESS EVENTS", 18, GOLD)
    event_box_y = event_y + 58
    event_w = (width - 2 * x0 - gap) // 2
    for index, (action, frames, color, caption) in enumerate((
        ("SAD", actions["sad"]["frames"], (248, 113, 113, 255), "negative event"),
        ("HAPPY", actions["happy"]["frames"], GOLD, "positive event"),
    )):
        bx = x0 + index * (event_w + gap)
        panel(draw, (bx, event_box_y, bx + event_w, event_box_y + event_h), outline=color)
        draw_text(draw, (bx + 18, event_box_y + 20), action, 18, color)
        draw_text(draw, (bx + 18, event_box_y + 53), caption, 14, MUTED)
        items = canonical_items(renderer, context, frames)
        total_w = len(items) * 118 + (len(items) - 1) * 15
        start_x = bx + (event_w - total_w) // 2
        for item_index, item in enumerate(items):
            ax = start_x + item_index * 133
            paste_centered(canvas, item["image"], (ax, event_box_y + 75, ax + 118, event_box_y + 235), scale=3)
            draw_text(draw, (ax + 59, event_box_y + 246), item["label"], 12, color, anchor="ma")
    footer_y = event_box_y + event_h + 25
    draw.line((x0, footer_y, width - x0, footer_y), fill=(48, 72, 96, 255), width=2)
    draw_multiline(
        draw,
        (x0, footer_y + 17),
        "CANONICAL: turn-side head stays locked to the partner-facing crop while the body alternates its normal-work hand bob.\n"
        "All action cells use direction-named subactions and registry frame IDs. SW mirrors SE and NE mirrors NW at the complete-frame level.",
        15,
        MUTED,
        spacing=7,
    )
    canvas.save(output)


def draw_comparison_sheet(context: dict, renderer: CharacterFrameRenderer, native_proposed: dict, mirrored_proposed: dict, output: Path) -> None:
    width = 2260
    header = 170
    row_h = 300
    rows = [
        ("SE", "turn_side_sw", ["M20", "M22"], native_proposed["SE:turn_side_sw"], "legacy head changed during loop", "head H1 fixed; body B1→B2"),
        ("SE", "turn_side_ne", ["M20", "M23"], native_proposed["SE:turn_side_ne"], "legacy head changed during loop", "head H4 fixed; body B1→B2"),
        ("NW", "turn_side_sw", ["M25", "M27"], native_proposed["NW:turn_side_sw"], "legacy head changed during loop", "head H1 fixed; body B4→B5"),
        ("NW", "turn_side_ne", ["M25", "M28"], native_proposed["NW:turn_side_ne"], "legacy head changed during loop", "head H4 fixed; body B4→B5"),
        ("SW", "turn_side_se", ["Mp20", "Mp22"], mirrored_proposed["SW:turn_side_se"], "derived legacy relation", "mirror of canonical SE turn"),
        ("SW", "turn_side_nw", ["Mp20", "Mp23"], mirrored_proposed["SW:turn_side_nw"], "derived legacy relation", "mirror of canonical SE turn"),
        ("NE", "turn_side_se", [], mirrored_proposed["NE:turn_side_se"], "not registered in legacy three-way Work", "mirror of canonical NW turn"),
        ("NE", "turn_side_nw", [], mirrored_proposed["NE:turn_side_nw"], "not registered in legacy three-way Work", "mirror of canonical NW turn"),
    ]
    height = header + len(rows) * row_h + 140
    canvas = Image.new("RGBA", (width, height), BG)
    subtitle = f"{context['character']['character_id']} | {context['identity']['full_name']} | legacy bindings vs canonical fixed-head turns"
    draw_page_header = __import__("TOOLS.render_work_frame_reference", fromlist=["draw_page_header"]).draw_page_header
    draw_page_header(canvas, "WORK TURN COMPARISON — LEGACY vs CANONICAL", subtitle)
    draw = ImageDraw.Draw(canvas)
    y = 145
    label_w = 360
    current_w = 640
    proposed_w = 640
    note_w = width - 2 * 30 - label_w - current_w - proposed_w - 30
    x = 30
    headers = [("ACTION", label_w, GOLD), ("CURRENT LOOP", current_w, FRAME_COLOR), ("PROPOSED LOOP", proposed_w, BODY_COLOR), ("READ", note_w, MUTED)]
    for title, w, color in headers:
        panel(draw, (x, y, x + w, y + 62), outline=color)
        draw_text(draw, (x + 16, y + 22), title, 17, color)
        x += w + 10
    y += 72
    for direction, subaction, current_ids, proposed_items, current_note, proposed_note in rows:
        x = 30
        color = direction_color(direction)
        panel(draw, (x, y, x + label_w, y + row_h - 10), outline=color)
        draw_text(draw, (x + 18, y + 25), direction, 24, color)
        draw_text(draw, (x + 92, y + 27), subaction, 17, TEXT)
        draw_text(draw, (x + 18, y + 78), "current:", 14, MUTED)
        draw_text(draw, (x + 86, y + 78), " → ".join(machine_display(context, fid) for fid in current_ids), 14, TEXT)
        draw_text(draw, (x + 18, y + 117), "canonical:", 14, MUTED)
        draw_text(draw, (x + 86, y + 117), " → ".join(item["label"] for item in proposed_items), 14, BODY_COLOR)
        draw_multiline(draw, (x + 18, y + 176), "fixed partner-facing head\nwith alternating body crop.", 14, MUTED, spacing=5)
        x += label_w + 10
        current_items = canonical_items(renderer, context, current_ids)
        panel(draw, (x, y, x + current_w, y + row_h - 10), outline=FRAME_COLOR, fill=PANEL_2)
        draw_text(draw, (x + 18, y + 17), "existing", 14, FRAME_COLOR)
        total_w = len(current_items) * 142 + 20
        start_x = x + (current_w - total_w) // 2
        for index, item in enumerate(current_items):
            ax = start_x + index * 162
            paste_centered(canvas, item["image"], (ax, y + 52, ax + 142, y + 212), scale=3)
            draw_text(draw, (ax + 71, y + 227), item["label"], 13, GOLD if index == 0 else TEXT, anchor="ma")
        x += current_w + 10
        panel(draw, (x, y, x + proposed_w, y + row_h - 10), outline=BODY_COLOR, fill=PANEL_2)
        draw_text(draw, (x + 18, y + 17), "canonical recipe", 14, BODY_COLOR)
        total_w = len(proposed_items) * 142 + 20
        start_x = x + (proposed_w - total_w) // 2
        for index, item in enumerate(proposed_items):
            ax = start_x + index * 162
            paste_centered(canvas, item["image"], (ax, y + 52, ax + 142, y + 212), scale=3)
            draw_text(draw, (ax + 71, y + 227), item["label"], 12, BODY_COLOR, anchor="ma")
        x += proposed_w + 10
        panel(draw, (x, y, x + note_w, y + row_h - 10), outline=MUTED, fill=PANEL_2)
        draw_text(draw, (x + 16, y + 18), "CURRENT", 13, FRAME_COLOR)
        draw_text(draw, (x + 16, y + 45), current_note, 13, MUTED)
        draw_text(draw, (x + 16, y + 100), "PROPOSED", 13, BODY_COLOR)
        draw_text(draw, (x + 16, y + 127), proposed_note, 13, MUTED)
        y += row_h
    draw.line((30, y + 4, width - 30, y + 4), fill=(48, 72, 96, 255), width=2)
    draw_multiline(
        draw,
        (30, y + 28),
        "The canonical side-turn loop never uses the normal-facing head in its repeating pair.\n"
        "Each named turn resolves to a fixed partner-facing head plus the next normal-work body crop; mirrored directions flip the complete frame once.",
        15,
        MUTED,
        spacing=7,
    )
    canvas.save(output)


def write_preview_csv(context: dict, native: dict, mirrored: dict, output_dir: Path) -> Path:
    rows = []
    for key, items in {**native, **mirrored}.items():
        direction, subaction = key.split(":", 1)
        for index, item in enumerate(items):
            body_rule = native_rule(context, item["body_frame"])
            face_rule = native_rule(context, item["face_frame"])
            rows.append({
                "direction": direction,
                "subaction": subaction,
                "frame_label": item["label"],
                "frame_index": index,
                "body_asset_id": context["body_id"],
                "face_asset_id": context["face_id"],
                "body_rule_frame": item["body_frame"],
                "face_rule_frame": item["face_frame"],
                "body_src": body_rule["body"]["src"],
                "body_dst": body_rule["body"]["dst"],
                "face_src": face_rule["face"]["src"],
                "face_dst": face_rule["face"]["dst"],
                "mirror_of": item.get("mirror_of", ""),
            })
    path = output_dir / "proposed_work_turn_preview_map.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--character", default="RND_F_004")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    context = load_context(args.character)
    renderer = CharacterFrameRenderer(CHARACTER_ROOT, verify_asset_hashes=True)
    native, mirrored = build_proposed_sequences(context)
    action_path = output_dir / f"{args.character}_proposed_action_sheet.png"
    compare_path = output_dir / f"{args.character}_proposed_turn_comparison.png"
    draw_full_action_sheet(context, renderer, native, mirrored, action_path)
    draw_comparison_sheet(context, renderer, native, mirrored, compare_path)
    csv_path = write_preview_csv(context, native, mirrored, output_dir)
    manifest = {
        "schema": "gds.work_turn_recipe_review.v2",
        "canonical_registry_edited": False,
        "character_id": context["character"]["character_id"],
        "body_asset_id": context["body_id"],
        "face_asset_id": context["face_id"],
        "canonical_recipe": {
            "SE:turn_side_sw": "B1+H1 -> B2+H1",
            "SE:turn_side_ne": "B1+H4 -> B2+H4",
            "NW:turn_side_sw": "B4+H1 -> B5+H1",
            "NW:turn_side_ne": "B4+H4 -> B5+H4",
            "SW": "mirror revised SE composite once",
            "NE": "mirror revised NW composite once",
        },
        "files": [
            {"path": path.name, "sha256": file_sha(path), "dimensions": list(Image.open(path).size) if path.suffix == ".png" else None}
            for path in (action_path, compare_path, csv_path)
        ],
    }
    manifest_path = output_dir / "proposed_work_turn_preview_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "character_id": context["character"]["character_id"],
        "output_dir": str(output_dir),
        "files": [action_path.name, compare_path.name, csv_path.name, manifest_path.name],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
