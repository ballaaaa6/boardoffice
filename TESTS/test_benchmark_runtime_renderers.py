from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_renderer_benchmark_compares_equal_floor02_paths():
    from TOOLS.benchmark_runtime_renderers import run_benchmark

    report = run_benchmark(ROOT, floor_id="floor02", ticks=2, warmup=1, elapsed_ms=60)

    assert report["schema"] == "gds.runtime_renderer_benchmark.v1"
    assert report["modes"]["canvas"]["renderer"] == "canvas"
    assert report["modes"]["raster"]["renderer"] == "raster"
    assert report["modes"]["canvas"]["actor_count"] == 9
    assert report["modes"]["raster"]["actor_count"] == 9
    assert report["modes"]["canvas"]["payload_bytes"]["p50_bytes"] < report["modes"]["raster"]["payload_bytes"]["p50_bytes"]
    assert report["modes"]["canvas"]["server_metrics"]["encode"]["p50_ms"] == 0.0
    assert report["comparison"]["payload_p50_reduction_pct"] > 0
