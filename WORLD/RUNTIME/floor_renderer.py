from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import zlib

from PIL import Image

from .layout_core import LayoutCore


def rgba_sha256(image: Image.Image) -> str:
    image = image.convert("RGBA")
    payload = image.size[0].to_bytes(4, "big") + image.size[1].to_bytes(4, "big") + image.tobytes()
    return hashlib.sha256(payload).hexdigest()


def png_sha256(image: Image.Image) -> str:
    """Return a hash of a deterministic RGBA PNG representation.

    Pillow's default PNG encoder can produce different byte streams across
    Pillow/zlib versions even when the rendered pixels are identical.  The
    release audits use this canonical representation so a dependency upgrade
    does not turn a pixel-identical floor into a false regression.
    """
    rgba = image.convert("RGBA")
    width, height = rgba.size
    row_width = width * 4
    raw = bytearray()
    pixels = rgba.tobytes()
    for y in range(height):
        raw.append(0)  # PNG filter: None, fixed for deterministic encoding.
        start = y * row_width
        raw.extend(pixels[start:start + row_width])

    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return (
            len(payload).to_bytes(4, "big")
            + body
            + (zlib.crc32(body) & 0xFFFFFFFF).to_bytes(4, "big")
        )

    png = bytearray(b"\x89PNG\r\n\x1a\n")
    png.extend(chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)))
    # Stored DEFLATE blocks avoid compressor heuristics changing the hash.
    png.extend(chunk(b"IDAT", zlib.compress(bytes(raw), level=0)))
    png.extend(chunk(b"IEND", b""))
    return hashlib.sha256(bytes(png)).hexdigest()


class FloorRenderer:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.core = LayoutCore(self.root)

    def render(self, floor_id: str) -> Image.Image:
        skin = self.core.floor_skin(floor_id)
        canvas = self.core.load_variant(skin["base_variant_id"]).copy()
        for placement in self.core.resolve_floor_placements(floor_id):
            sprite = self.core.load_variant(placement["variant_id"])
            canvas.alpha_composite(sprite, (int(placement["x_px"]), int(placement["y_px"])))
        return canvas

    def render_rgba_sha256(self, floor_id: str) -> str:
        return rgba_sha256(self.render(floor_id))

    def render_png_sha256(self, floor_id: str) -> str:
        return png_sha256(self.render(floor_id))

    def render_to(self, floor_id: str, output: str | Path) -> Path:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        self.render(floor_id).save(output)
        return output
