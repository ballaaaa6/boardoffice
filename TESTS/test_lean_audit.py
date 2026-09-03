from __future__ import annotations

import json
from pathlib import Path

from TOOLS.lean_audit import scan


def test_scan_reports_nonempty_duplicate_files_and_function_bodies(tmp_path: Path) -> None:
    runtime = tmp_path / "RUNTIME"
    runtime.mkdir()
    source = "def shared_value():\n    return 7\n"
    (runtime / "first.py").write_text(source, encoding="utf-8")
    (runtime / "second.py").write_text(source, encoding="utf-8")

    report = scan(tmp_path, run_ruff=False)

    duplicate_paths = [group.paths for group in report.exact_duplicate_groups]
    assert duplicate_paths == [("RUNTIME/first.py", "RUNTIME/second.py")]
    assert any(
        location.path == "RUNTIME/first.py"
        and location.name == "shared_value"
        for group in report.duplicate_functions
        for location in group.locations
    )


def test_scan_keeps_generated_files_and_empty_package_markers_out_of_dead_code_count(
    tmp_path: Path,
) -> None:
    (tmp_path / "WEB" / "runtime_assets").mkdir(parents=True)
    (tmp_path / "WEB" / "runtime_render_manifest.json").write_text(
        "{}\n", encoding="utf-8"
    )
    (tmp_path / "RUNTIME").mkdir()
    (tmp_path / "RUNTIME" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "TOOLS").mkdir()
    (tmp_path / "TOOLS" / "script.py").write_text(
        "import sys\nsys.path.insert(0, '.')\n", encoding="utf-8"
    )

    report = scan(tmp_path, run_ruff=False)
    payload = report.to_dict()

    assert payload["schema"] == "gds.lean_audit.v1"
    assert payload["classifications"]["WEB/runtime_render_manifest.json"] == "generated"
    assert payload["empty_package_markers"] == ["RUNTIME/__init__.py"]
    assert payload["bootstrap_occurrences"] == [
        {
            "path": "TOOLS/script.py",
            "line": 2,
            "text": "sys.path.insert(0, '.')",
        }
    ]
    json.dumps(payload, ensure_ascii=False, sort_keys=True)


def test_scan_ignores_immutable_starting_point_archive(tmp_path: Path) -> None:
    archive = tmp_path / "00_STARTING_POINT" / "archive.py"
    archive.parent.mkdir()
    archive.write_text("def copied():\n    return 1\n", encoding="utf-8")
    runtime = tmp_path / "RUNTIME" / "current.py"
    runtime.parent.mkdir()
    runtime.write_text("def current():\n    return 2\n", encoding="utf-8")

    report = scan(tmp_path, run_ruff=False)

    assert "00_STARTING_POINT/archive.py" not in report.tracked_source_files
    assert all(
        "00_STARTING_POINT/archive.py" not in group.paths
        for group in report.exact_duplicate_groups
    )


def test_scan_marks_unimported_cli_as_entrypoint_candidate_not_dead(
    tmp_path: Path,
) -> None:
    tools = tmp_path / "TOOLS"
    tests = tmp_path / "TESTS"
    tools.mkdir()
    tests.mkdir()
    (tools / "orphan.py").write_text(
        "def main():\n    return 0\n\nif __name__ == '__main__':\n    main()\n",
        encoding="utf-8",
    )
    (tools / "imported.py").write_text(
        "def main():\n    return 0\n\nif __name__ == '__main__':\n    main()\n",
        encoding="utf-8",
    )
    (tests / "test_imported.py").write_text(
        "from TOOLS.imported import main\n\nassert main() == 0\n",
        encoding="utf-8",
    )

    report = scan(tmp_path, run_ruff=False)

    assert report.entrypoint_candidates == ("TOOLS/orphan.py",)
