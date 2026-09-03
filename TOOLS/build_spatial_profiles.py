from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

try:
    from TOOLS._bootstrap import ensure_project_root
except ModuleNotFoundError:
    from _bootstrap import ensure_project_root

SCOPE = ("chair", "desk", "pc", "reception")


def dump_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build(root: Path) -> dict:
    root = ensure_project_root(root)
    from WORLD.RUNTIME.layout_core import LayoutCore

    core = LayoutCore(root / "WORLD")
    usage: dict[str, set[str]] = defaultdict(set)
    use_counts: dict[str, int] = defaultdict(int)
    floors_by_variant: dict[str, set[str]] = defaultdict(set)

    for floor_id in sorted(core.floors):
        for placement in core.resolve_floor_placements(floor_id):
            if placement["object_type"] not in SCOPE:
                continue
            variant_id = placement["variant_id"]
            usage[variant_id].add(placement["object_type"])
            use_counts[variant_id] += 1
            floors_by_variant[variant_id].add(floor_id)

    profiles = {}
    for variant_id in sorted(usage):
        variant = core.variants[variant_id]
        image = core.load_variant(variant_id)
        bbox = image.getbbox()
        if bbox is None:
            bounds = None
            padding = {
                "left": image.width,
                "top": image.height,
                "right": image.width,
                "bottom": image.height,
            }
        else:
            left, top, right, bottom = bbox
            bounds = {
                "left": left,
                "top": top,
                "right": right,
                "bottom": bottom,
                "width": right - left,
                "height": bottom - top,
            }
            padding = {
                "left": left,
                "top": top,
                "right": image.width - right,
                "bottom": image.height - bottom,
            }

        profiles[variant_id] = {
            "variant_id": variant_id,
            "asset_id": variant["asset_id"],
            "transform": variant["transform"],
            "object_types": sorted(usage[variant_id]),
            "canvas_size_px": {"width": image.width, "height": image.height},
            "visual_bounds_px": bounds,
            "transparent_padding_px": padding,
            "spatial": {
                "footprint": None,
                "semantic_anchor_policy": "placement_or_layout_evidence_only",
            },
            "physics": {
                "solid": None,
                "collision_shape": None,
            },
            "interaction": {
                "anchor": None,
                "radius_px": None,
            },
            "evidence": {
                "visual_bounds_method": "alpha_bbox_from_canonical_variant_pixels",
                "use_count": use_counts[variant_id],
                "used_floors": sorted(floors_by_variant[variant_id]),
            },
        }

    return {
        "schema": "gds.spatial_profiles.v1",
        "scope": {
            "primary_object_types": list(SCOPE),
            "chair_foreground_policy": "chair_sub_is_render_fragment_not_primary_spatial_object",
            "unknown_value_policy": "explicit_null_no_guessing",
        },
        "profile_count": len(profiles),
        "profiles": profiles,
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    registry = build(root)
    out = root / "WORLD" / "REGISTRY" / "spatial_profiles.json"
    dump_json(out, registry)
    print(f"wrote {out} profiles={registry['profile_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
