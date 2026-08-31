"""Render review-only animated GIFs for the canonical Work character poses.

The GIFs are review artifacts outside the runtime package. They compose the
approved fixed-head/alternating-body recipe from registered body/head crops,
derive SW from SE and NE from NW with a final-composite ``mirror_y`` and do not
edit character art, action data, world data or runtime code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "outputs" / "01a057c6-2d38-7be3-bfbe-4cadb1b6cc66"
sys.path.insert(0, str(ROOT))

from TOOLS.render_proposed_work_action_sheet import (  # noqa: E402
    compose_preview_frame,
    native_rule,
)
from TOOLS.render_work_frame_reference import (  # noqa: E402
    BG,
    BODY_COLOR,
    GOLD,
    MUTED,
    NE_COLOR,
    NW_COLOR,
    PANEL_2,
    SE_COLOR,
    SW_COLOR,
    CharacterFrameRenderer,
    checker,
    direction_color,
    draw_multiline,
    draw_page_header,
    draw_text,
    load_context,
    make_font,
    panel,
    paste_centered,
)


DIRECTIONS = ("NE", "SE", "SW", "NW")

# Native frame rules used as source crops for this review. Canonical side-turn
# frame IDs point to the equivalent registered composites in frame_registry.
NATIVE_RECIPES: dict[tuple[str, str], tuple[tuple[str, str], ...]] = {
    ("SE", "normal_work"): (("M20", "M20"), ("M21", "M21")),
    ("SE", "turn_side_sw"): (("M20", "M22"), ("M21", "M22")),
    ("SE", "turn_side_ne"): (("M20", "M23"), ("M21", "M23")),
    ("SE", "happy"): (("M24", "M24"),),
    ("NW", "normal_work"): (("M25", "M25"), ("M26", "M26")),
    ("NW", "turn_side_sw"): (("M25", "M27"), ("M26", "M27")),
    ("NW", "turn_side_ne"): (("M25", "M28"), ("M26", "M28")),
    ("NW", "happy"): (("M29", "M29"),),
}

# Direction names follow the partner-facing target after reflection: SW↔SE
# and NW↔NE. The derived image is mirrored only once at the finished frame.
DERIVED_FROM: dict[tuple[str, str], tuple[str, str]] = {
    ("SW", "normal_work"): ("SE", "normal_work"),
    ("SW", "turn_side_se"): ("SE", "turn_side_sw"),
    ("SW", "turn_side_nw"): ("SE", "turn_side_ne"),
    ("SW", "happy"): ("SE", "happy"),
    ("NE", "normal_work"): ("NW", "normal_work"),
    ("NE", "turn_side_se"): ("NW", "turn_side_sw"),
    ("NE", "turn_side_nw"): ("NW", "turn_side_ne"),
    ("NE", "happy"): ("NW", "happy"),
}

SUBACTIONS = {
    "NE": ("normal_work", "turn_side_se", "turn_side_nw", "happy"),
    "SE": ("normal_work", "turn_side_sw", "turn_side_ne", "happy"),
    "SW": ("normal_work", "turn_side_se", "turn_side_nw", "happy"),
    "NW": ("normal_work", "turn_side_sw", "turn_side_ne", "happy"),
}

BODY_LABELS = {
    "M20": "B1",
    "M21": "B2",
    "M24": "B3",
    "M25": "B4",
    "M26": "B5",
    "M29": "B6",
}

FACE_LABELS = {
    "M20": "H2",
    "M22": "H1",
    "M23": "H4",
    "M24": "H5",
    "M25": "H3",
    "M27": "H1",
    "M28": "H4",
    "M29": "H6",
}


@dataclass(frozen=True)
class PoseFrame:
    frame_index: int
    image: Image.Image
    body_frame: str
    face_frame: str
    source_key: str
    source_frame_index: int
    transform: str | None


@dataclass(frozen=True)
class PoseSequence:
    direction: str
    subaction: str
    frames: tuple[PoseFrame, ...]
    source_key: str
    transform: str | None
    source_loop: bool


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _render_sequences(context: dict) -> dict[tuple[str, str], PoseSequence]:
    body_sheet = Image.open(context["body_path"]).convert("RGBA")
    face_sheet = Image.open(context["face_path"]).convert("RGBA")
    cache: dict[tuple[str, str], PoseSequence] = {}

    def render(key: tuple[str, str]) -> PoseSequence:
        if key in cache:
            return cache[key]
        direction, subaction = key
        if key in NATIVE_RECIPES:
            raw_frames = NATIVE_RECIPES[key]
            frames = tuple(
                PoseFrame(
                    frame_index=index,
                    image=compose_preview_frame(
                        context, body_sheet, face_sheet, body_frame, face_frame
                    ),
                    body_frame=body_frame,
                    face_frame=face_frame,
                    source_key=f"{direction}/{subaction}",
                    source_frame_index=index,
                    transform=None,
                )
                for index, (body_frame, face_frame) in enumerate(raw_frames)
            )
            source_loop = len(frames) > 1
            sequence = PoseSequence(
                direction=direction,
                subaction=subaction,
                frames=frames,
                source_key=f"{direction}/{subaction}",
                transform=None,
                source_loop=source_loop,
            )
            cache[key] = sequence
            return sequence

        source_key = DERIVED_FROM[key]
        source = render(source_key)
        frames = tuple(
            PoseFrame(
                frame_index=source_frame.frame_index,
                image=source_frame.image.transpose(Image.Transpose.FLIP_LEFT_RIGHT),
                body_frame=source_frame.body_frame,
                face_frame=source_frame.face_frame,
                source_key=f"{source.direction}/{source.subaction}",
                source_frame_index=source_frame.frame_index,
                transform="mirror_y",
            )
            for source_frame in source.frames
        )
        sequence = PoseSequence(
            direction=direction,
            subaction=subaction,
            frames=frames,
            source_key=f"{source.direction}/{source.subaction}",
            transform="mirror_y",
            source_loop=source.source_loop,
        )
        cache[key] = sequence
        return sequence

    for direction in DIRECTIONS:
        for subaction in SUBACTIONS[direction]:
            render((direction, subaction))
    return cache


def _frame_detail(frame: PoseFrame) -> str:
    body_label = BODY_LABELS.get(frame.body_frame, frame.body_frame)
    face_label = FACE_LABELS.get(frame.face_frame, frame.face_frame)
    if frame.transform:
        return (
            f"mirror_y ← {frame.source_key}\n"
            f"source frame_index {frame.source_frame_index}\n"
            f"source {body_label}+{face_label}"
        )
    return (
        f"body {body_label} + head {face_label}\n"
        f"rules {frame.body_frame}.body + {frame.face_frame}.face"
    )


def _display_frame(sequence: PoseSequence, tick: int) -> PoseFrame:
    return sequence.frames[tick % len(sequence.frames)]


def _gif_palette(image: Image.Image) -> Image.Image:
    # The review sheets are opaque; reserving 255 colors keeps text and pixel
    # art stable while leaving one palette slot available for GIF tooling.
    rgb = image.convert("RGB")
    return rgb.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)


def _save_gif(frames: list[Image.Image], path: Path, *, duration: int) -> None:
    if not frames:
        raise ValueError(f"Cannot save empty GIF: {path}")
    palettes = [_gif_palette(frame) for frame in frames]
    palettes[0].save(
        path,
        save_all=True,
        append_images=palettes[1:],
        duration=[duration] * len(palettes),
        loop=0,
        disposal=2,
    )


def _draw_sequence_card(
    context: dict,
    sequence: PoseSequence,
    tick: int,
    *,
    width: int = 430,
    height: int = 535,
    art_scale: int = 8,
) -> Image.Image:
    canvas = Image.new("RGBA", (width, height), BG)
    draw = ImageDraw.Draw(canvas)
    color = direction_color(sequence.direction)
    panel(draw, (8, 8, width - 8, height - 8), outline=color, fill=PANEL_2)
    draw_text(draw, (26, 24), sequence.direction, 25, color)
    draw_text(draw, (112, 27), sequence.subaction, 17, GOLD)
    frame = _display_frame(sequence, tick)
    draw_text(draw, (26, 67), f"frame_index {frame.frame_index}", 15, MUTED)
    art_box = (42, 102, width - 42, 438)
    paste_centered(canvas, frame.image, art_box, scale=art_scale)
    draw_multiline(draw, (26, 450), _frame_detail(frame), 13, MUTED, spacing=4)
    return canvas


def _draw_sheet_frame(context: dict, sequences: dict[tuple[str, str], PoseSequence], tick: int) -> Image.Image:
    width = 1390
    margin = 24
    gap = 14
    header_h = 132
    cell_w = (width - (2 * margin) - (3 * gap)) // 4
    cell_h = 344
    height = header_h + (4 * cell_h) + (5 * gap) + 76
    canvas = Image.new("RGBA", (width, height), BG)
    subtitle = (
        f"{context['character']['character_id']} | {context['identity']['full_name']} | "
        f"body {context['body_id']} + face {context['face_id']} | review-only, canonical data unchanged"
    )
    draw_page_header(canvas, "WORK CHARACTER SHEET — ANIMATED PREVIEW", subtitle)
    draw = ImageDraw.Draw(canvas)
    draw_text(draw, (margin, 118), "fixed partner-facing head · alternating seated-work body", 15, BODY_COLOR)
    draw_text(draw, (width - margin, 118), f"preview frame_index {tick % 2}", 15, GOLD, anchor="ra")

    for row_index, subaction_index in enumerate(range(4)):
        for col_index, direction in enumerate(DIRECTIONS):
            subaction = SUBACTIONS[direction][subaction_index]
            sequence = sequences[(direction, subaction)]
            x = margin + col_index * (cell_w + gap)
            y = header_h + gap + row_index * (cell_h + gap)
            color = direction_color(direction)
            panel(draw, (x, y, x + cell_w, y + cell_h), outline=color, fill=PANEL_2)
            frame = _display_frame(sequence, tick)
            draw_text(draw, (x + 16, y + 15), direction, 22, color)
            draw_text(draw, (x + 84, y + 18), subaction, 16, GOLD)
            draw_text(draw, (x + 16, y + 51), f"frame_index {frame.frame_index}", 13, MUTED)
            paste_centered(canvas, frame.image, (x + 34, y + 82, x + cell_w - 34, y + 284), scale=5)
            detail = _frame_detail(frame)
            draw_multiline(draw, (x + 16, y + 290), detail, 11, MUTED, spacing=3)

    footer_y = header_h + gap + (4 * (cell_h + gap))
    draw.line((margin, footer_y, width - margin, footer_y), fill=(48, 72, 96, 255), width=2)
    draw_text(
        draw,
        (margin, footer_y + 20),
        "NE = mirror_y from NW  ·  SW = mirror_y from SE  ·  one mirror at final composite",
        14,
        MUTED,
    )
    return canvas


def _write_sequence_gifs(
    context: dict,
    sequences: dict[tuple[str, str], PoseSequence],
    output_dir: Path,
) -> list[dict]:
    gif_dir = output_dir / f"{context['character']['character_id']}_work_character_gifs"
    gif_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    for direction in DIRECTIONS:
        for subaction in SUBACTIONS[direction]:
            sequence = sequences[(direction, subaction)]
            frames = [
                _draw_sequence_card(context, sequence, index)
                for index in range(max(2, len(sequence.frames)))
            ]
            path = gif_dir / f"{context['character']['character_id']}__{direction}__{subaction}.gif"
            _save_gif(frames, path, duration=520 if subaction != "happy" else 760)
            records.append(
                {
                    "direction": direction,
                    "subaction": subaction,
                    "path": str(path.relative_to(output_dir)),
                    "frame_ids": [
                        {
                            "frame_index": frame.frame_index,
                            "body_frame": frame.body_frame,
                            "face_frame": frame.face_frame,
                            "source": frame.source_key,
                            "transform": frame.transform,
                        }
                        for frame in sequence.frames
                    ],
                    "source_loop": sequence.source_loop,
                    "preview_loop": True,
                    "sha256": file_sha(path),
                    "dimensions": [frames[0].width, frames[0].height],
                }
            )
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--character", default="RND_F_004")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    context = load_context(args.character)
    # Instantiating with hash verification keeps the preview tied to the
    # registered body/head assets without touching their files.
    CharacterFrameRenderer(ROOT / "CHARACTER", verify_asset_hashes=True)
    sequences = _render_sequences(context)

    sheet_frames = [_draw_sheet_frame(context, sequences, tick) for tick in range(2)]
    sheet_gif = output_dir / f"{args.character}_work_character_sheet.gif"
    _save_gif(sheet_frames, sheet_gif, duration=650)
    for index, frame in enumerate(sheet_frames):
        frame.save(output_dir / f"{args.character}_work_character_sheet_frame_{index}.png")

    sequence_records = _write_sequence_gifs(context, sequences, output_dir)
    manifest = {
        "schema": "gds.work_character_gif_preview.v1",
        "canonical_registry_edited": False,
        "character_id": context["character"]["character_id"],
        "identity": context["identity"]["full_name"],
        "body_asset_id": context["body_id"],
        "face_asset_id": context["face_id"],
        "canonical_recipe": {
            "SE/turn_side_sw": "B1+H1 -> B2+H1",
            "SE/turn_side_ne": "B1+H4 -> B2+H4",
            "NW/turn_side_sw": "B4+H1 -> B5+H1",
            "NW/turn_side_ne": "B4+H4 -> B5+H4",
            "SW": "mirror_y from SE final composite",
            "NE": "mirror_y from NW final composite",
        },
        "sheet": {
            "path": sheet_gif.name,
            "sha256": file_sha(sheet_gif),
            "dimensions": [sheet_frames[0].width, sheet_frames[0].height],
            "frame_count": len(sheet_frames),
            "frame_ms": 650,
        },
        "sequences": sequence_records,
    }
    manifest_path = output_dir / f"{args.character}_work_character_gif_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "character_id": args.character,
                "output_dir": str(output_dir),
                "sheet": sheet_gif.name,
                "sequence_gif_count": len(sequence_records),
                "manifest": manifest_path.name,
                "canonical_registry_edited": False,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
