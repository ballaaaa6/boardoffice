from __future__ import annotations

"""Materialize the additional authored PC atlas cells for the active families.

The starting-point sheets are read-only evidence.  This builder writes the
content-addressed cell blobs and the small runtime registry consumed by
``LayoutCore``; it never edits the archived source sheets.
"""

import argparse
import hashlib
import json
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rgba_sha256(image: Image.Image) -> str:
    rgba = image.convert("RGBA")
    payload = (
        rgba.width.to_bytes(4, "big")
        + rgba.height.to_bytes(4, "big")
        + rgba.tobytes()
    )
    return hashlib.sha256(payload).hexdigest()


def png_bytes(image: Image.Image) -> bytes:
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


def build(root: Path, source_office: Path) -> dict[str, Any]:
    assets_path = root / "WORLD" / "REGISTRY" / "world_assets.json"
    variants_path = root / "WORLD" / "REGISTRY" / "visual_variants.json"
    assets_payload = load_json(assets_path)
    variants_payload = load_json(variants_path)
    assets = assets_payload["assets"]
    variants = variants_payload["variants"]
    blobs_dir = root / "WORLD" / "ASSETS" / "blobs"
    blobs_dir.mkdir(parents=True, exist_ok=True)

    families = sorted(
        {
            asset_id.split(".", 1)[0]
            for asset_id in assets
            if asset_id.startswith("pc_") and ".slot_00" in asset_id
        }
    )
    if not families:
        raise RuntimeError("No active pc_* slot_00 assets found")

    registry_families: dict[str, Any] = {}
    restored_assets: list[str] = []
    existing_assets: list[str] = []
    new_blob_ids: set[str] = set()
    source_mismatches: list[str] = []

    for family_id in families:
        source_sheet = source_office / f"{family_id}.png"
        if not source_sheet.is_file():
            raise FileNotFoundError(source_sheet)
        source_hash = file_sha256(source_sheet)
        with Image.open(source_sheet) as image:
            sheet = image.convert("RGBA")
        if sheet.size != (100, 96):
            raise ValueError(f"{source_sheet}: expected 100x96, got {sheet.size}")

        cells: list[Image.Image] = []
        for cell_index in range(6):
            left = (cell_index % 2) * 50
            top = (cell_index // 2) * 32
            cells.append(sheet.crop((left, top, left + 50, top + 32)).convert("RGBA"))

        # Existing active cells remain the byte-level anchors for the recovered
        # source sheet.  The source archive's PNG encoding may differ, so the
        # comparison intentionally uses decoded RGBA pixels.
        for cell_index in (0, 1):
            asset_id = f"{family_id}.slot_{cell_index:02d}"
            existing = assets.get(asset_id)
            if existing is None:
                raise RuntimeError(f"Missing active asset {asset_id}")
            blob_path = blobs_dir / f"{existing['blob_id']}.png"
            if not blob_path.is_file():
                raise FileNotFoundError(blob_path)
            with Image.open(blob_path) as image:
                current = image.convert("RGBA")
            if current.size != cells[cell_index].size or current.tobytes() != cells[cell_index].tobytes():
                source_mismatches.append(asset_id)

        animated_asset_ids: list[str] = []
        for cell_index in range(1, 6):
            asset_id = f"{family_id}.slot_{cell_index:02d}"
            cell = cells[cell_index]
            rgba_hash = rgba_sha256(cell)
            blob_path = blobs_dir / f"{rgba_hash}.png"
            if blob_path.exists():
                with Image.open(blob_path) as image:
                    current = image.convert("RGBA")
                if current.size != cell.size or current.tobytes() != cell.tobytes():
                    raise RuntimeError(f"Blob collision for {asset_id}: {rgba_hash}")
            else:
                blob_path.write_bytes(png_bytes(cell))
                new_blob_ids.add(rgba_hash)

            if asset_id in assets:
                existing = assets[asset_id]
                if existing["rgba_sha256"] != rgba_hash:
                    raise RuntimeError(
                        f"{asset_id}: existing RGBA hash {existing['rgba_sha256']} != {rgba_hash}"
                    )
                existing_assets.append(asset_id)
            else:
                assets[asset_id] = {
                    "asset_id": asset_id,
                    "blob_id": rgba_hash,
                    "height": 32,
                    "legacy_shared_path": f"office/pc/{family_id}/slot_{cell_index:02d}.png",
                    "recipe": {
                        "type": "source_sheet_cell_crop",
                        "source_package": "Game_Dev_Story_v2.6.9_EXTRACTED_ASSETS",
                        "source_path": f"01_KAIRO_SPRITE_PACKS/office/{family_id}.png",
                        "source_rect": [
                            (cell_index % 2) * 50,
                            (cell_index // 2) * 32,
                            (cell_index % 2) * 50 + 50,
                            (cell_index // 2) * 32 + 32,
                        ],
                    },
                    "recipe_validation": {
                        "status": "exact",
                        "source_rgba_sha256": rgba_hash,
                        "canonical_rgba_sha256": rgba_hash,
                    },
                    "rgba_sha256": rgba_hash,
                    "semantic_type": "pc",
                    "source_class": "recovered_original_sheet_cell",
                    "source_png_sha256": source_hash,
                    "width": 50,
                }
                restored_assets.append(asset_id)

            variant_id = f"{asset_id}@normal"
            if variant_id not in variants:
                variants[variant_id] = {
                    "asset_id": asset_id,
                    "semantic_type": "pc",
                    "transform": "NORMAL",
                    "variant_id": variant_id,
                }
            animated_asset_ids.append(asset_id)

        registry_families[family_id] = {
            "family_id": family_id,
            "source_sheet": f"01_KAIRO_SPRITE_PACKS/office/{family_id}.png",
            "source_sheet_sha256": source_hash,
            "static_asset_id": f"{family_id}.slot_00",
            "animated_asset_ids": animated_asset_ids,
            "direction_policy": {
                "NW": "animated_asset_ids",
                "NE": "animated_asset_ids_mirrored_at_workseat_composition",
                "SE": "static_asset_id",
                "SW": "static_asset_id",
            },
            "cell_layout": {
                "cell0": "SE/SW static",
                "cell1": "NW/NE frame 0",
                "cell2": "NW/NE frame 1",
                "cell3": "NW/NE frame 2",
                "cell4": "NW/NE frame 3",
                "cell5": "NW/NE frame 4",
            },
        }

    if source_mismatches:
        raise RuntimeError(
            "Active PC cells did not match the supplied source sheets: "
            + ", ".join(source_mismatches)
        )

    assets_payload["assets"] = dict(sorted(assets.items()))
    variants_payload["variants"] = dict(sorted(variants.items()))
    write_json(assets_path, assets_payload)
    write_json(variants_path, variants_payload)

    registry = {
        "$schema": "gds.pc_animation.v1",
        "schema": "gds.pc_animation.v1",
        "contract_id": "registry.gds.pc_animation.v1",
        "version": "1.0.0",
        "source_package": "Game_Dev_Story_v2.6.9_EXTRACTED_ASSETS",
        "cell_size_px": [50, 32],
        "sheet_size_px": [100, 96],
        "frame_policy": {
            "active_frame_count": 5,
            "advance_boundary": "one_frame_after_each_complete_work_action_loop",
            "sequence": ["slot_01", "slot_02", "slot_03", "slot_04", "slot_05"],
            "wrap": True,
            "static_directions": ["SE", "SW"],
            "animated_directions": ["NW", "NE"],
        },
        "families": registry_families,
    }
    write_json(root / "WORLD" / "REGISTRY" / "pc_animation.json", registry)

    return {
        "family_count": len(registry_families),
        "new_logical_asset_count": len(restored_assets),
        "new_logical_assets": restored_assets,
        "existing_verified_asset_count": len(existing_assets),
        "new_unique_blob_count": len(new_blob_ids),
        "world_logical_asset_count": len(assets),
        "world_variant_count": len(variants),
        "registry": "WORLD/REGISTRY/pc_animation.json",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--source-office",
        default="00_STARTING_POINT/Game_Dev_Story_v2.6.9_EXTRACTED_ASSETS/01_KAIRO_SPRITE_PACKS/office",
    )
    args = parser.parse_args()
    report = build(Path(args.root).resolve(), Path(args.source_office).resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
