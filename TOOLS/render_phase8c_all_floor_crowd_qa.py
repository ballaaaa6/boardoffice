from __future__ import annotations

import json

try:
    from TOOLS._bootstrap import ensure_project_root
except ModuleNotFoundError:
    from _bootstrap import ensure_project_root

PROJECT_ROOT = ensure_project_root(__file__)

from TOOLS.render_phase8b_crowd_portal_qa import CrowdPortalRenderer

if __name__ == '__main__':
    output_root = PROJECT_ROOT / 'LOCAL_REVIEW' / 'PHASE8C_ALL_FLOOR_CROWD_QA'
    renderer = CrowdPortalRenderer(PROJECT_ROOT)
    result = renderer.render_all_registered_floors(output_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['status'] == 'PASS' else 1)
