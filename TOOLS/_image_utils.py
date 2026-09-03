from __future__ import annotations

"""Shared image-export helpers for review-only tooling."""

from collections.abc import Sequence

from PIL import Image


def build_global_palette(frames: Sequence[Image.Image]) -> list[int]:
    """Build the shared RGB palette used by the floor06 GIF exporters."""

    if not frames:
        raise ValueError("frames required")
    strip = Image.new(
        "RGBA",
        (frames[0].width * len(frames), frames[0].height),
        (0, 0, 0, 0),
    )
    for index, frame in enumerate(frames):
        strip.alpha_composite(frame.convert("RGBA"), (index * frame.width, 0))
    alpha = strip.getchannel("A")
    rgb = Image.new("RGB", strip.size, (0, 0, 0))
    rgb.paste(strip, mask=alpha)
    palette_image = rgb.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    palette = palette_image.getpalette() or []
    if len(palette) < 768:
        palette += [0] * (768 - len(palette))
    return palette[:768]


def to_palette(image: Image.Image, palette: Sequence[int]) -> Image.Image:
    """Convert an RGBA image to the shared palette without dithering."""

    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    rgb = Image.new("RGB", rgba.size, (0, 0, 0))
    rgb.paste(rgba, mask=alpha)
    palette_image = Image.new("P", (1, 1))
    palette_image.putpalette(list(palette))
    result = rgb.quantize(
        colors=255,
        palette=palette_image,
        dither=Image.Dither.NONE,
    )
    transparent_mask = alpha.point(lambda value: 255 if value == 0 else 0)
    result.paste(255, mask=transparent_mask)
    result.putpalette(list(palette))
    result.info["transparency"] = 255
    return result
