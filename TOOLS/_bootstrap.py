from __future__ import annotations

"""Repository-root discovery shared by direct CLI entrypoints."""

import sys
from pathlib import Path


def project_root(anchor: str | Path | None = None) -> Path:
    """Find the nearest project root containing the runtime and world trees."""

    candidate = Path(anchor or __file__).resolve()
    if candidate.is_file():
        candidate = candidate.parent
    for parent in (candidate, *candidate.parents):
        if (parent / "RUNTIME").is_dir() and (parent / "WORLD").is_dir():
            return parent
    raise RuntimeError(f"Could not find project root from {candidate}")


def ensure_project_root(anchor: str | Path | None = None) -> Path:
    """Return the project root and add it to ``sys.path`` exactly once."""

    root = project_root(anchor)
    value = str(root)
    if value not in sys.path:
        sys.path.insert(0, value)
    return root
