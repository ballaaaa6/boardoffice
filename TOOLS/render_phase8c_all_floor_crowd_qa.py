from __future__ import annotations

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from TOOLS.render_phase8b_crowd_portal_qa import CrowdPortalRenderer

if __name__ == '__main__':
    output_root = PROJECT_ROOT / 'LOCAL_REVIEW' / 'PHASE8C_ALL_FLOOR_CROWD_QA'
    renderer = CrowdPortalRenderer(PROJECT_ROOT)
    result = renderer.render_all_registered_floors(output_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['status'] == 'PASS' else 1)
