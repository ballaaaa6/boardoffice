from __future__ import annotations

from pathlib import Path

from RUNTIME.central_core import CentralGameCore


ROOT = Path(__file__).resolve().parents[1]


def test_lifecycle_render_facade_keeps_character_and_overlay_indices_independent():
    core = CentralGameCore(ROOT)
    plain = core.render_work_seat_lifecycle_state(
        "floor06", "ws1", 0, character_frame_index=1
    )
    combined = core.render_work_seat_lifecycle_state(
        "floor06",
        "ws3",
        0,
        effect_id="thunder_cloud",
        humanball_id="coin",
        character_frame_index=1,
        effect_frame_index=3,
        humanball_frame_index=5,
    )
    assert plain.size == (600, 600)
    assert combined.size == (600, 600)
    assert plain.tobytes() != combined.tobytes()
