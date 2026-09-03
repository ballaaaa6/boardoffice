from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path

from PIL import Image

from RUNTIME.asset_utils import file_sha256, load_json, png_bytes, rgba_sha256, write_json
from WORLD.RUNTIME.floor_renderer import rgba_sha256 as floor_rgba_sha256


def test_asset_hash_helpers_preserve_file_and_rgba_contracts(tmp_path: Path) -> None:
    payload = b"canonical source bytes"
    source = tmp_path / "source.bin"
    source.write_bytes(payload)
    assert file_sha256(source) == hashlib.sha256(payload).hexdigest()

    image = Image.new("RGBA", (2, 1), (10, 20, 30, 40))
    expected = hashlib.sha256(
        image.width.to_bytes(4, "big")
        + image.height.to_bytes(4, "big")
        + image.tobytes()
    ).hexdigest()
    assert rgba_sha256(image) == expected
    assert floor_rgba_sha256 is rgba_sha256

    with Image.open(BytesIO(png_bytes(image))) as decoded:
        assert decoded.convert("RGBA").tobytes() == image.tobytes()


def test_json_helpers_use_stable_utf8_indented_output(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "payload.json"
    write_json(target, {"z": "ไทย", "a": [2, 1]})

    assert load_json(target) == {"z": "ไทย", "a": [2, 1]}
    assert target.read_text(encoding="utf-8") == (
        '{\n  "a": [\n    2,\n    1\n  ],\n  "z": "ไทย"\n}\n'
    )
    json.loads(target.read_text(encoding="utf-8"))
