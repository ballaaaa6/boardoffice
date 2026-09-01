from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "WEB" / "runtime_review.html").read_text(encoding="utf-8")


def test_review_host_uses_fixed_simulation_slices_without_latency_double_wait():
    assert "const SIM_STEP_MS = 60;" in HTML
    assert "elapsed_ms:SIM_STEP_MS * autoSpeed" in HTML
    assert "const targetWallMs = Math.max(MIN_FRAME_WALL_MS, SIM_STEP_MS / autoSpeed);" in HTML
    assert "AUTO_WALL_MS" not in HTML
    assert "MIN_WALL_MS" not in HTML


def test_review_host_swaps_only_after_image_decode_and_keeps_previous_frame():
    assert "target.decode()" in HTML
    assert "target.classList.add('visible'); previous.classList.remove('visible')" in HTML
    # A previously loaded alternate image must not be treated as the new frame
    # merely because its complete flag remained true from the prior request.
    assert "if(target.complete) target.onload();" not in HTML


def test_review_host_retries_transient_live_errors_instead_of_pausing():
    assert "const REQUEST_TIMEOUT_MS = 5000;" in HTML
    assert "const RETRY_BASE_MS = 250;" in HTML
    assert "live reconnecting in" in HTML
    assert "setLive(false); $('note').textContent = `live stopped:" not in HTML


def test_review_demo_pause_is_explicitly_opt_in():
    assert 'id="autoPauseDemo"' in HTML
    assert "if($('autoPauseDemo').checked)" in HTML
    assert "live continues" in HTML
