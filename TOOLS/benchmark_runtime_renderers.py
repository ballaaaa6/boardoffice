from __future__ import annotations

"""Measure the live review server's raster and lean render request paths.

The benchmark drives the same ``ReviewState.tick`` boundary used by the local
review page.  ``renderer=canvas`` advances Central through the headless loop,
projects metadata and returns a JSON component state.  ``renderer=raster``
adds the compatibility image composition and base64 encoding step.  Gameplay
state, elapsed time, compact payload policy and actor count are kept equal for
both samples.
"""

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Iterable

try:
    from TOOLS._bootstrap import ensure_project_root
except ModuleNotFoundError:
    from _bootstrap import ensure_project_root

PROJECT_ROOT = ensure_project_root(__file__)

from TOOLS.runtime_review_server import ReviewState


DEFAULT_FLOOR_ID = "floor02"
DEFAULT_TICKS = 60
DEFAULT_WARMUP = 5
DEFAULT_ELAPSED_MS = 60


def _percentile(values: Iterable[float], percentile: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("percentile requires at least one sample")
    if len(ordered) == 1:
        return round(ordered[0], 3)
    position = (len(ordered) - 1) * float(percentile)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    value = ordered[lower] + (ordered[upper] - ordered[lower]) * fraction
    return round(value, 3)


def _optional_rss_bytes() -> int | None:
    """Return current process RSS when a supported provider is available."""
    try:
        import psutil  # type: ignore

        return int(psutil.Process(os.getpid()).memory_info().rss)
    except (ImportError, OSError, AttributeError):
        return None


def _metric_value(metrics: dict[str, Any], key: str) -> float | None:
    value = metrics.get(key)
    if value is None:
        return None
    return float(value)


def _summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        raise ValueError("benchmark requires at least one measured sample")

    def stats(key: str, *, unit: str) -> dict[str, float]:
        values = [float(sample[key]) for sample in samples]
        return {
            f"p50_{unit}": _percentile(values, 0.50),
            f"p95_{unit}": _percentile(values, 0.95),
        }

    def optional_stats(key: str) -> dict[str, float | None]:
        values = [sample[key] for sample in samples if sample[key] is not None]
        if not values:
            return {"p50_ms": None, "p95_ms": None}
        return {
            "p50_ms": _percentile(values, 0.50),
            "p95_ms": _percentile(values, 0.95),
        }

    actor_counts = sorted({int(sample["actor_count"]) for sample in samples})
    payload = stats("payload_bytes", unit="bytes")
    return {
        "samples": len(samples),
        "actor_count": actor_counts[0] if len(actor_counts) == 1 else actor_counts,
        "wall_call": stats("wall_call_ms", unit="ms"),
        "payload_bytes": payload,
        "server_metrics": {
            "tick_compute": optional_stats("tick_compute_ms"),
            "render": optional_stats("render_ms"),
            "encode": optional_stats("encode_ms"),
            "payload_build": optional_stats("payload_build_ms"),
        },
        "rss_bytes": {
            "before": samples[0]["rss_before_bytes"],
            "after": samples[-1]["rss_after_bytes"],
        },
    }


def _run_mode(
    *,
    floor_id: str,
    renderer: str,
    ticks: int,
    warmup: int,
    elapsed_ms: int,
) -> dict[str, Any]:
    state = ReviewState(floor_id)
    for _ in range(warmup):
        state.tick(elapsed_ms, include_runtime=False, renderer=renderer)

    samples: list[dict[str, Any]] = []
    for _ in range(ticks):
        rss_before = _optional_rss_bytes()
        started = time.perf_counter()
        payload = state.tick(elapsed_ms, include_runtime=False, renderer=renderer)
        wall_call_ms = (time.perf_counter() - started) * 1000.0
        rss_after = _optional_rss_bytes()
        metrics = payload.get("metrics", {})
        payload_bytes = len(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        samples.append({
            "wall_call_ms": round(wall_call_ms, 3),
            "payload_bytes": payload_bytes,
            "actor_count": len(payload.get("actors", [])),
            "tick_compute_ms": _metric_value(metrics, "tick_compute_ms"),
            "render_ms": _metric_value(metrics, "render_ms"),
            "encode_ms": _metric_value(metrics, "encode_ms"),
            "payload_build_ms": _metric_value(metrics, "payload_build_ms"),
            "rss_before_bytes": rss_before,
            "rss_after_bytes": rss_after,
        })

    result = _summary(samples)
    result["renderer"] = renderer
    return result


def _reduction_percent(raster_value: float, lean_value: float) -> float | None:
    if raster_value <= 0:
        return None
    return round((raster_value - lean_value) / raster_value * 100.0, 2)


def run_benchmark(
    root: Path = PROJECT_ROOT,
    *,
    floor_id: str = DEFAULT_FLOOR_ID,
    ticks: int = DEFAULT_TICKS,
    warmup: int = DEFAULT_WARMUP,
    elapsed_ms: int = DEFAULT_ELAPSED_MS,
) -> dict[str, Any]:
    """Run equal compact live samples through both renderer request paths."""
    del root  # ReviewState resolves the repository root from its server module.
    if ticks <= 0:
        raise ValueError("ticks must be positive")
    if warmup < 0:
        raise ValueError("warmup must be non-negative")
    if elapsed_ms <= 0:
        raise ValueError("elapsed_ms must be positive")

    lean = _run_mode(
        floor_id=floor_id,
        renderer="canvas",
        ticks=ticks,
        warmup=warmup,
        elapsed_ms=elapsed_ms,
    )
    raster = _run_mode(
        floor_id=floor_id,
        renderer="raster",
        ticks=ticks,
        warmup=warmup,
        elapsed_ms=elapsed_ms,
    )
    return {
        "schema": "gds.runtime_renderer_benchmark.v1",
        "floor_id": floor_id,
        "elapsed_ms": elapsed_ms,
        "warmup_ticks": warmup,
        "measured_ticks": ticks,
        "modes": {
            "canvas": lean,
            "raster": raster,
        },
        "comparison": {
            "payload_p50_reduction_pct": _reduction_percent(
                raster["payload_bytes"]["p50_bytes"],
                lean["payload_bytes"]["p50_bytes"],
            ),
            "wall_call_p50_reduction_pct": _reduction_percent(
                raster["wall_call"]["p50_ms"],
                lean["wall_call"]["p50_ms"],
            ),
            "raster_encode_p50_ms": raster["server_metrics"]["encode"]["p50_ms"],
            "canvas_encode_p50_ms": lean["server_metrics"]["encode"]["p50_ms"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--floor-id", default=DEFAULT_FLOOR_ID)
    parser.add_argument("--ticks", type=int, default=DEFAULT_TICKS)
    parser.add_argument("--warmup", type=int, default=DEFAULT_WARMUP)
    parser.add_argument("--elapsed-ms", type=int, default=DEFAULT_ELAPSED_MS)
    args = parser.parse_args()
    report = run_benchmark(
        floor_id=args.floor_id,
        ticks=args.ticks,
        warmup=args.warmup,
        elapsed_ms=args.elapsed_ms,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
