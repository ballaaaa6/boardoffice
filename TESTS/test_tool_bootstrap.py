from __future__ import annotations

import sys
from pathlib import Path

from TOOLS._bootstrap import ensure_project_root, project_root
from VALIDATION._common import resolve_root, write_report


def test_project_root_finds_repository_from_a_nested_script(tmp_path: Path) -> None:
    (tmp_path / "RUNTIME").mkdir()
    (tmp_path / "WORLD").mkdir()
    script = tmp_path / "TOOLS" / "nested" / "script.py"
    script.parent.mkdir(parents=True)
    script.write_text("", encoding="utf-8")

    assert project_root(script) == tmp_path
    assert resolve_root(anchor=script) == tmp_path


def test_ensure_project_root_inserts_only_one_absolute_root(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "RUNTIME").mkdir()
    (tmp_path / "WORLD").mkdir()
    original = list(sys.path)
    monkeypatch.setattr(sys, "path", original.copy())

    assert ensure_project_root(tmp_path) == tmp_path
    assert ensure_project_root(tmp_path) == tmp_path
    assert sys.path.count(str(tmp_path)) == 1


def test_write_report_creates_parent_and_uses_stable_json(tmp_path: Path) -> None:
    path = write_report(tmp_path, "REPORTS/sample.json", {"z": 1, "a": "ไทย"})

    assert path == tmp_path / "REPORTS" / "sample.json"
    assert path.read_text(encoding="utf-8") == '{\n  "a": "ไทย",\n  "z": 1\n}\n'
