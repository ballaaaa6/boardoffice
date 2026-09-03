from __future__ import annotations

"""Small deterministic helpers shared by asset builders and audits.

These helpers intentionally contain no project-root discovery or gameplay
policy.  Keeping them under ``RUNTIME`` lets world, character, validation and
tooling code share one implementation without making the runtime depend on a
QA tool module.
"""

import hashlib
import json
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image


def file_sha256(path: Path) -> str:
    """Return the SHA-256 digest of a file's bytes."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rgba_sha256(image: Image.Image) -> str:
    """Return the canonical digest of an image's RGBA dimensions and pixels."""

    rgba = image.convert("RGBA")
    payload = (
        rgba.width.to_bytes(4, "big")
        + rgba.height.to_bytes(4, "big")
        + rgba.tobytes()
    )
    return hashlib.sha256(payload).hexdigest()


def png_bytes(image: Image.Image) -> bytes:
    """Encode an image as the existing RGBA PNG builder payload."""

    output = BytesIO()
    image.convert("RGBA").save(output, format="PNG")
    return output.getvalue()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
