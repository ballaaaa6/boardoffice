from __future__ import annotations

"""Shared path and report helpers for validation entrypoints."""

import sys
from pathlib import Path
from typing import Any

# Direct ``python VALIDATION/script.py`` execution puts the validation folder
# on ``sys.path`` rather than the repository root.  Keep that one compatibility
# bootstrap here so individual audits do not each carry their own copy.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from RUNTIME.asset_utils import load_json, write_json
from TOOLS._bootstrap import project_root


def resolve_root(
    core_root: str | Path | None = None,
    *,
    anchor: str | Path | None = None,
) -> Path:
    """Resolve an explicit root or discover it from a script/test anchor."""

    root = Path(core_root).resolve() if core_root is not None else project_root(anchor)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


def write_report(root: str | Path, relative_path: str | Path, payload: Any) -> Path:
    """Write a validation report below ``root`` using stable JSON formatting."""

    path = Path(root).resolve() / Path(relative_path)
    write_json(path, payload)
    return path


__all__ = ["load_json", "resolve_root", "write_json", "write_report"]
