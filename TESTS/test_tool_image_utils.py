from __future__ import annotations

from PIL import Image

from TOOLS._image_utils import build_global_palette, to_palette


def test_palette_helpers_produce_a_shared_768_entry_palette() -> None:
    frames = [
        Image.new("RGBA", (2, 2), (255, 0, 0, 255)),
        Image.new("RGBA", (2, 2), (0, 255, 0, 0)),
    ]

    palette = build_global_palette(frames)
    converted = to_palette(frames[1], palette)

    assert len(palette) == 768
    assert converted.mode == "P"
    assert converted.size == frames[1].size
    assert converted.info["transparency"] == 255


def test_palette_builder_rejects_empty_frame_sets() -> None:
    try:
        build_global_palette([])
    except ValueError as exc:
        assert str(exc) == "frames required"
    else:
        raise AssertionError("empty frame set must be rejected")
