from __future__ import annotations

import argparse
from pathlib import Path

from .action_core import ActionCore


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Resolve a central GDS character action from the Core.')
    ap.add_argument('--core-root', default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument('--character-root', help='Optional legacy package root; enables compatibility path output.')
    ap.add_argument('--character', required=True)
    ap.add_argument('--action', required=True)
    ap.add_argument('--direction')
    ap.add_argument('--subaction')
    ns = ap.parse_args(argv)
    core = ActionCore(ns.core_root, ns.character_root)
    if ns.character_root:
        values = core.resolve_legacy_paths(ns.character, ns.action, ns.direction, ns.subaction)
    else:
        values = core.resolve_frame_ids(ns.character, ns.action, ns.direction, ns.subaction)
    for value in values:
        print(value)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
