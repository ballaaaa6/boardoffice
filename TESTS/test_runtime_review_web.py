from __future__ import annotations

import json
from pathlib import Path
from urllib.request import urlopen

import pytest


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
    # Discrete screenshots must swap atomically.  Cross-fading two full
    # rasters makes the floor flash/shimmer when the stream is faster than the
    # CSS transition.
    assert "transition:opacity" not in HTML
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


def test_review_host_exposes_normal_full_system_and_auto_critical_demo_buttons():
    assert 'id="fullDemo"' in HTML
    assert "Full system demo (normal)" in HTML
    assert "/api/demo-full" in HTML
    assert 'id="critical"' in HTML
    assert "Critical demo</button>" in HTML
    assert "begin('/api/demo-critical',{employee_id:selected})" in HTML
    assert "resume:false" not in HTML


def test_canvas_renderer_module_has_component_contract_and_pixel_art_defaults():
    source = (ROOT / "WEB" / "runtime_canvas_renderer.js").read_text(encoding="utf-8")

    assert "export class RuntimeCanvasRenderer" in source
    for method in ("constructor(", "loadManifest(", "setState(", "render(", "destroy("):
        assert method in source
    assert "imageSmoothingEnabled = false" in source
    assert "requestAnimationFrame" not in source
    assert "image_data_url" not in source


def test_canvas_client_polls_at_fixed_interval_and_keeps_fetch_out_of_raf():
    source = (ROOT / "WEB/runtime_render_client.js").read_text(encoding="utf-8")

    assert "export class RuntimeRenderClient" in source
    assert "intervalMs = 100" in source or "intervalMs: 100" in source
    assert "renderer: 'canvas'" in source or 'renderer: "canvas"' in source
    assert "/api/tick" in source
    assert "requestAnimationFrame" in source
    assert "fetchImpl(" in source
    assert "tickOnce(" in source


def test_review_page_exposes_canvas_mode_and_raster_fallback():
    assert 'id="runtimeCanvas"' in HTML
    assert 'id="rendererMode"' in HTML
    assert "runtime_canvas_renderer.js" in HTML
    assert "runtime_render_client.js" in HTML
    assert "renderer:rendererMode" in HTML or "renderer: rendererMode" in HTML
    assert "image_data_url" in HTML
    assert "setScene(x.image_data_url)" in HTML
    assert "render_state" in HTML


def test_review_host_serves_manifest_and_runtime_component_assets():
    from TOOLS.runtime_review_server import ReviewHandler, ThreadingHTTPServer

    server = ThreadingHTTPServer(("127.0.0.1", 0), ReviewHandler)
    try:
        port = server.server_address[1]
        # The handler must serve these from WEB only; this test intentionally
        # exercises the same endpoint a browser module import will use.
        import threading

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        with urlopen(f"http://127.0.0.1:{port}/runtime_render_manifest.json") as response:
            manifest = json.loads(response.read().decode("utf-8"))
            assert manifest["schema"] == "gds.runtime_render_manifest.v1"
        with urlopen(f"http://127.0.0.1:{port}/runtime_assets/floor02.static.png") as response:
            assert response.headers.get_content_type() == "image/png"
            assert response.read(8) == b"\x89PNG\r\n\x1a\n"
    finally:
        server.shutdown()
        server.server_close()


def test_runtime_review_static_path_rejects_asset_traversal():
    from TOOLS.runtime_review_server import ReviewHandler

    assert ReviewHandler._web_static_path(
        "/runtime_assets/../runtime_render_manifest.json"
    ) is None
