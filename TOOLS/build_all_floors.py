from __future__ import annotations

"""Build browser runtime bundles and render manifests for all 25 floors."""

import argparse
import json
import time
from pathlib import Path

try:
    from TOOLS._bootstrap import ensure_project_root
except ModuleNotFoundError:
    from _bootstrap import ensure_project_root

PROJECT_ROOT = ensure_project_root(__file__)

from RUNTIME.browser_bundle_contract import canonical_json
from RUNTIME.central_core import CentralGameCore
from TOOLS.build_runtime_render_manifest import build_manifest
from TOOLS.build_runtime_simulation_bundle import build_bundle


def build_all_floors(
    root: str | Path,
    output_dir: str | Path | None = None,
    assets_dir: str | Path | None = None,
) -> list[dict[str, any]]:
    project_root = Path(root).resolve()
    floors_dir = (
        Path(output_dir).resolve()
        if output_dir is not None
        else project_root / "WEB" / "floors"
    )
    shared_assets_dir = (
        Path(assets_dir).resolve()
        if assets_dir is not None
        else project_root / "WEB" / "runtime_assets"
    )

    floors_dir.mkdir(parents=True, exist_ok=True)
    shared_assets_dir.mkdir(parents=True, exist_ok=True)

    core = CentralGameCore(project_root)
    floors = sorted(core.world.floors)
    print(f"Building browser bundles and manifests for {len(floors)} floors...")

    index_entries = []

    for index, floor_id in enumerate(floors, start=1):
        t0 = time.perf_counter()
        target_floor_dir = floors_dir / floor_id
        target_floor_dir.mkdir(parents=True, exist_ok=True)

        bundle_path = target_floor_dir / "bootstrap.json"
        manifest_path = target_floor_dir / "manifest.json"

        # 1. Build & save simulation bundle
        bundle = build_bundle(project_root, floor_id=floor_id)
        bundle_path.write_text(canonical_json(bundle) + "\n", encoding="utf-8", newline="\n")

        # 2. Build & save render manifest and copy assets to shared runtime_assets
        manifest = build_manifest(
            project_root,
            floor_id=floor_id,
            output_dir=shared_assets_dir,
        )
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

        emp_count = len(bundle["employees"])
        ws_count = len(bundle["work_seats"])
        floor_num = floor_id.replace("floor", "")
        friendly_name = (
            f"Floor {floor_num} (Lobby)"
            if floor_id == "floor00"
            else f"Floor {floor_num} (Executive)"
            if floor_id == "floor02"
            else f"Floor {floor_num}"
        )

        entry = {
            "floor_id": floor_id,
            "name": friendly_name,
            "floor_number": floor_num,
            "employee_count": emp_count,
            "workstation_count": ws_count,
            "bootstrap_url": f"./floors/{floor_id}/bootstrap.json",
            "manifest_url": f"./floors/{floor_id}/manifest.json",
            "bundle_revision": bundle["bundle_revision"],
            "manifest_revision": manifest["revision"],
        }
        index_entries.append(entry)

        elapsed = (time.perf_counter() - t0) * 1000.0
        print(f"  [{index:02d}/{len(floors):02d}] {floor_id}: {emp_count} employees, {len(manifest['files'])} assets ({elapsed:.0f}ms)")

    # 3. Write index file
    index_path = floors_dir / "index.json"
    index_path.write_text(
        json.dumps(index_entries, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    # 4. Ensure canonical root runtime_render_manifest.json remains floor02
    build_manifest(
        project_root,
        floor_id="floor02",
        output_dir=shared_assets_dir,
    )

    print(f"Successfully generated {len(index_entries)} floor bundles in {floors_dir}")
    return index_entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(PROJECT_ROOT))
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--assets-dir", default=None)
    args = parser.parse_args()

    build_all_floors(
        args.root,
        output_dir=args.output_dir,
        assets_dir=args.assets_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
