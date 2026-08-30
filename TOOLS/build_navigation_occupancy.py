from __future__ import annotations

import json
from pathlib import Path

from WORLD.RUNTIME.navigation_occupancy_core import NavigationOccupancyCore


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / 'WORLD'


def main() -> None:
    core = NavigationOccupancyCore(WORLD)
    core.compiled_root.mkdir(parents=True, exist_ok=True)
    summary = {'schema': 'gds_navigation_occupancy_build_v1', 'floors': {}}
    for floor_id in sorted(core.layout.floors):
        compiled = core.compile_floor(floor_id)
        path = core.compiled_path(floor_id)
        path.write_text(json.dumps(compiled, indent=2) + '\n', encoding='utf-8')
        summary['floors'][floor_id] = {
            'room_cell_count': compiled['room_cell_count'],
            'occupied_cell_count': compiled['occupied_cell_count'],
            'walkable_cell_count': compiled['walkable_cell_count'],
            'portal_inside_cell_count': compiled['portal_inside_cell_count'],
            'outside_room_instance_count': compiled['outside_room_instance_count'],
            'portal_overlap_cell_count': compiled['portal_overlap_cell_count'],
        }
    ROOT.joinpath('REPORTS', 'NAVIGATION_OCCUPANCY_BUILD.json').write_text(
        json.dumps(summary, indent=2) + '\n', encoding='utf-8'
    )


if __name__ == '__main__':
    main()
