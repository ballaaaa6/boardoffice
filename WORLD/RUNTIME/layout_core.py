from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps


class LayoutCore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.assets = self._read("world_assets.json")["assets"]
        self.variants = self._read("visual_variants.json")["variants"]
        self.coordinate_frames = self._read("coordinate_frames.json")["coordinate_frames"]
        self.layouts = self._read("layouts.json")["layouts"]
        self.skins = self._read("floor_skins.json")["skins"]
        self.floors = self._read("floors.json")["floors"]
        self._image_cache: dict[str, Image.Image] = {}
        self._variant_by_asset_transform: dict[tuple[str, str], str] = {}
        for variant_id, entry in self.variants.items():
            key = (entry["asset_id"], entry["transform"])
            if key in self._variant_by_asset_transform and self._variant_by_asset_transform[key] != variant_id:
                raise ValueError(f"Duplicate variant mapping for {key}: {self._variant_by_asset_transform[key]}, {variant_id}")
            self._variant_by_asset_transform[key] = variant_id

    def _read(self, name: str) -> dict[str, Any]:
        return json.loads((self.root / "REGISTRY" / name).read_text(encoding="utf-8"))

    def resolve_asset_blob(self, asset_id: str) -> Path:
        entry = self.assets[asset_id]
        return self.root / "ASSETS" / "blobs" / f"{entry['blob_id']}.png"

    def load_asset(self, asset_id: str) -> Image.Image:
        if asset_id not in self._image_cache:
            self._image_cache[asset_id] = Image.open(self.resolve_asset_blob(asset_id)).convert("RGBA")
        return self._image_cache[asset_id].copy()

    def resolve_variant(self, asset_id: str, transform: str) -> str:
        try:
            return self._variant_by_asset_transform[(asset_id, transform)]
        except KeyError as exc:
            raise KeyError(f"No visual variant for asset={asset_id!r}, transform={transform!r}") from exc

    def load_variant(self, variant_id: str) -> Image.Image:
        entry = self.variants[variant_id]
        image = self.load_asset(entry["asset_id"])
        transform = entry["transform"]
        if transform == "FLIP_X":
            return ImageOps.mirror(image)
        if transform in {"NORMAL", "CROP"}:
            return image
        raise ValueError(f"Unsupported transform: {transform}")


    def regenerate_recipe(self, asset_id: str) -> Image.Image:
        asset = self.assets[asset_id]
        recipe = asset.get("recipe")
        if not recipe:
            raise ValueError(f"Asset has no recipe: {asset_id}")
        raw_path = self.root / "RAW" / "floors" / f"{recipe['floor_id']}_raw_600x800.png"
        raw = Image.open(raw_path).convert("RGBA")
        crop = raw.crop(tuple(recipe["source_rect"])).convert("RGBA")
        if recipe.get("normalize_canvas"):
            cw, ch = recipe["normalize_canvas"]
            w, h = crop.size
            canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
            ox = max(0, (cw - w) // 2)
            oy = max(0, ch - 1 - h)
            if recipe.get("paste_offset"):
                ox, oy = recipe["paste_offset"]
            if w > cw:
                left = (w - cw) // 2
                crop = crop.crop((left, 0, left + cw, h))
                ox = 0
            canvas.alpha_composite(crop, (ox, oy))
            crop = canvas
        return crop

    def recipe_matches_canonical(self, asset_id: str) -> bool:
        regenerated = self.regenerate_recipe(asset_id)
        canonical = self.load_asset(asset_id)
        return regenerated.size == canonical.size and regenerated.tobytes() == canonical.tobytes()

    def floor_record(self, floor_id: str) -> dict[str, Any]:
        return self.floors[floor_id]

    def floor_skin(self, floor_id: str) -> dict[str, Any]:
        floor = self.floor_record(floor_id)
        return self.skins[floor["skin_id"]]

    def floor_layout(self, floor_id: str) -> dict[str, Any]:
        floor = self.floor_record(floor_id)
        return self.layouts[floor["layout_id"]]

    def resolve_floor_placements(self, floor_id: str) -> list[dict[str, Any]]:
        floor = self.floor_record(floor_id)
        layout = self.layouts[floor["layout_id"]]
        skin = self.skins[floor["skin_id"]]
        bindings = skin["bindings"]
        legacy_by_pid = skin.get("placement_legacy_metadata", {})
        resolved: list[dict[str, Any]] = []

        for slot in layout["slots"]:
            asset_id = bindings.get(slot["binding_key"])
            if asset_id is None:
                if slot["required"]:
                    raise KeyError(
                        f"{floor_id}: missing required binding {slot['binding_key']} for slot {slot['slot_id']}"
                    )
                continue
            variant_id = self.resolve_variant(asset_id, slot["transform"])
            item: dict[str, Any] = {
                "floor_id": floor_id,
                "placement_id": slot["slot_id"],
                "canonical_placement_id": f"{floor_id}.{slot['slot_id']}",
                "object_type": slot["object_type"],
                "asset_id": asset_id,
                "variant_id": variant_id,
                "transform": slot["transform"],
                "x_px": slot["x_px"],
                "y_px": slot["y_px"],
                "layer": slot["layer"],
            }
            if slot["slot_id"] in legacy_by_pid:
                item["legacy_metadata"] = legacy_by_pid[slot["slot_id"]]
            resolved.append(item)

        for semantic_slot in layout.get("semantic_slots", []):
            binding = skin.get("semantic_bindings", {}).get(semantic_slot["binding_key"])
            if binding is None:
                if semantic_slot["required"]:
                    raise KeyError(
                        f"{floor_id}: missing required semantic binding {semantic_slot['binding_key']} "
                        f"for slot {semantic_slot['slot_id']}"
                    )
                continue
            asset_id = binding["asset_id"]
            variant_id = self.resolve_variant(asset_id, semantic_slot["transform"])
            if variant_id != binding["variant_id"]:
                raise ValueError(
                    f"{floor_id}.{semantic_slot['slot_id']}: semantic variant mismatch: "
                    f"binding={binding['variant_id']} resolved={variant_id}"
                )
            anchor = semantic_slot["anchor"]
            bounds = binding["visual_bounds_px"]
            if anchor["x_basis"] != "sprite_left" or anchor["y_basis"] != "alpha_top":
                raise ValueError(f"Unsupported semantic anchor basis: {anchor}")
            x_px = int(anchor["x_px"])
            y_px = int(anchor["y_px"]) - int(bounds["top"])
            item = {
                "floor_id": floor_id,
                "placement_id": semantic_slot["slot_id"],
                "canonical_placement_id": f"{floor_id}.{semantic_slot['slot_id']}",
                "object_type": semantic_slot["object_type"],
                "asset_id": asset_id,
                "variant_id": variant_id,
                "transform": semantic_slot["transform"],
                "x_px": x_px,
                "y_px": y_px,
                "layer": semantic_slot["layer"],
                "semantic_anchor": anchor,
                "visual_bounds_px": bounds,
            }
            if semantic_slot["slot_id"] in legacy_by_pid:
                item["legacy_metadata"] = legacy_by_pid[semantic_slot["slot_id"]]
            resolved.append(item)

        for explicit in skin["explicit_placements"]:
            item = {
                "floor_id": floor_id,
                "placement_id": explicit["placement_id"],
                "canonical_placement_id": f"{floor_id}.{explicit['placement_id']}",
                "object_type": explicit["object_type"],
                "asset_id": explicit["asset_id"],
                "variant_id": explicit["variant_id"],
                "transform": explicit["transform"],
                "x_px": explicit["x_px"],
                "y_px": explicit["y_px"],
                "layer": explicit["layer"],
            }
            if explicit.get("legacy_metadata"):
                item["legacy_metadata"] = explicit["legacy_metadata"]
            resolved.append(item)

        return sorted(resolved, key=lambda p: (p["layer"], p["placement_id"]))

    def workstation_group(self, floor_id: str, workstation_id: str) -> dict[str, Any]:
        layout = self.floor_layout(floor_id)
        return layout["workstation_groups"][workstation_id]
