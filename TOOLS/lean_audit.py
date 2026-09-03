from __future__ import annotations

"""Produce a deterministic, non-authoritative source hygiene inventory.

The audit deliberately distinguishes source, tooling, test, generated and
support files.  It reports candidates for review; it never deletes files and
it never treats a CLI entrypoint as dead merely because no Python module
imports it.
"""

import argparse
import ast
import hashlib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


SCHEMA = "gds.lean_audit.v1"
TEXT_SUFFIXES = frozenset(
    {".html", ".js", ".json", ".mjs", ".md", ".py", ".toml", ".txt", ".yml", ".yaml"}
)
IGNORED_TOP_LEVEL = frozenset(
    {
        ".git",
        ".pytest_cache",
        ".worktrees",
        "00_STARTING_POINT",
        "LOCAL_REVIEW",
        "releases",
    }
)
BOOTSTRAP_PATTERN = re.compile(
    r"sys\.path\.(?:insert|append)\b"
)


@dataclass(frozen=True)
class FunctionLocation:
    path: str
    name: str
    line: int

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "name": self.name, "line": self.line}


@dataclass(frozen=True)
class DuplicateFunctionGroup:
    body_sha256: str
    locations: tuple[FunctionLocation, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "body_sha256": self.body_sha256,
            "locations": [location.to_dict() for location in self.locations],
        }


@dataclass(frozen=True)
class ExactDuplicateGroup:
    sha256: str
    size: int
    paths: tuple[str, ...]
    classification: str

    def to_dict(self) -> dict[str, object]:
        return {
            "sha256": self.sha256,
            "size": self.size,
            "paths": list(self.paths),
            "classification": self.classification,
        }


@dataclass(frozen=True)
class BootstrapOccurrence:
    path: str
    line: int
    text: str

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "line": self.line, "text": self.text}


@dataclass(frozen=True)
class LeanAuditReport:
    classifications: dict[str, str]
    tracked_source_files: tuple[str, ...]
    empty_package_markers: tuple[str, ...]
    exact_duplicate_groups: tuple[ExactDuplicateGroup, ...]
    duplicate_functions: tuple[DuplicateFunctionGroup, ...]
    bootstrap_occurrences: tuple[BootstrapOccurrence, ...]
    entrypoint_candidates: tuple[str, ...]
    ruff_findings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "classifications": dict(sorted(self.classifications.items())),
            "tracked_source_files": list(self.tracked_source_files),
            "empty_package_markers": list(self.empty_package_markers),
            "exact_duplicate_groups": [
                group.to_dict() for group in self.exact_duplicate_groups
            ],
            "duplicate_functions": [
                group.to_dict() for group in self.duplicate_functions
            ],
            "bootstrap_occurrences": [
                occurrence.to_dict() for occurrence in self.bootstrap_occurrences
            ],
            "entrypoint_candidates": list(self.entrypoint_candidates),
            "ruff_findings": list(self.ruff_findings),
        }

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )


def _relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_ignored(relative_path: str) -> bool:
    parts = Path(relative_path).parts
    return bool(parts) and (
        parts[0] in IGNORED_TOP_LEVEL or "__pycache__" in parts
    )


def _git_files(root: Path) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    files: list[Path] = []
    for value in result.stdout.splitlines():
        path = root / value
        relative = Path(value).as_posix()
        if path.is_file() and not _is_ignored(relative):
            files.append(path)
    return sorted(files, key=lambda item: _relative_path(root, item))


def _discover_files(root: Path) -> list[Path]:
    git_files = _git_files(root)
    if git_files:
        return git_files
    files = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = _relative_path(root, path)
        if _is_ignored(relative):
            continue
        files.append(path)
    return sorted(files, key=lambda item: _relative_path(root, item))


def _classify(relative_path: str) -> str:
    parts = Path(relative_path).parts
    top = parts[0] if parts else ""
    name = parts[-1] if parts else ""
    if top == "WEB" and (
        name.startswith("runtime_") or "runtime_assets" in parts
    ):
        return "generated"
    if top in {"CHARACTER", "CONTRACTS", "RUNTIME", "SCHEMA", "WORLD"}:
        return "canonical"
    if top in {"TOOLS", "VALIDATION"}:
        return "tooling"
    if top == "TESTS":
        return "test"
    if top == "WEB":
        return "web_source"
    if top == "docs":
        return "documentation"
    return "support"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _duplicate_files(root: Path, files: Sequence[Path]) -> tuple[ExactDuplicateGroup, ...]:
    by_digest: dict[tuple[int, str], list[Path]] = {}
    for path in files:
        if path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size == 0:
            continue
        key = (path.stat().st_size, _sha256(path))
        by_digest.setdefault(key, []).append(path)

    groups: list[ExactDuplicateGroup] = []
    for (size, digest), paths in sorted(by_digest.items(), key=lambda item: item[0]):
        if len(paths) < 2:
            continue
        relative = tuple(sorted(_relative_path(root, path) for path in paths))
        classifications = {_classify(path) for path in relative}
        classification = "generated_copy" if "generated" in classifications else "source_duplicate"
        groups.append(
            ExactDuplicateGroup(
                sha256=digest,
                size=size,
                paths=relative,
                classification=classification,
            )
        )
    return tuple(groups)


def _duplicate_functions(root: Path, files: Sequence[Path]) -> tuple[DuplicateFunctionGroup, ...]:
    by_body: dict[str, list[FunctionLocation]] = {}
    for path in files:
        if path.suffix.lower() != ".py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        relative = _relative_path(root, path)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = ast.dump(
                ast.Module(body=node.body, type_ignores=[]),
                annotate_fields=True,
                include_attributes=False,
            )
            digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
            by_body.setdefault(digest, []).append(
                FunctionLocation(path=relative, name=node.name, line=node.lineno)
            )

    groups: list[DuplicateFunctionGroup] = []
    for digest, locations in sorted(by_body.items()):
        if len(locations) < 2:
            continue
        ordered = tuple(sorted(locations, key=lambda item: (item.path, item.line, item.name)))
        groups.append(DuplicateFunctionGroup(body_sha256=digest, locations=ordered))
    return tuple(groups)


def _module_name(root: Path, path: Path) -> str:
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imported_module_names(module_name: str, tree: ast.AST) -> tuple[str, ...]:
    package = module_name.split(".")[:-1]
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            if node.level > len(package) + 1:
                continue
            base_parts = package[: len(package) - node.level + 1]
        else:
            base_parts = []
        if node.module:
            base_parts.extend(node.module.split("."))
        base = ".".join(base_parts)
        if base:
            names.add(base)
        for alias in node.names:
            if alias.name == "*":
                continue
            names.add(".".join(part for part in (base, alias.name) if part))
    return tuple(sorted(names))


def _has_main_guard(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        if not isinstance(node.test.left, ast.Name) or node.test.left.id != "__name__":
            continue
        if any(
            isinstance(comparator, ast.Constant) and comparator.value == "__main__"
            for comparator in node.test.comparators
        ):
            return True
    return False


def _entrypoint_candidates(root: Path, files: Sequence[Path]) -> tuple[str, ...]:
    module_paths = {
        _module_name(root, path): path for path in files if path.suffix.lower() == ".py"
    }
    importers: dict[Path, set[Path]] = {path: set() for path in module_paths.values()}
    main_guards: set[Path] = set()
    for source in importers:
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        if _has_main_guard(tree):
            main_guards.add(source)
        source_module = _module_name(root, source)
        for imported in _imported_module_names(source_module, tree):
            target = module_paths.get(imported)
            if target is not None and target != source:
                importers[target].add(source)
    candidates = [
        _relative_path(root, path)
        for path in main_guards
        if path.relative_to(root).parts[0] in {"TOOLS", "VALIDATION"}
        and not importers[path]
    ]
    return tuple(sorted(candidates))


def _bootstrap_occurrences(root: Path, files: Iterable[Path]) -> tuple[BootstrapOccurrence, ...]:
    occurrences: list[BootstrapOccurrence] = []
    for path in files:
        if path.suffix.lower() != ".py":
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        lines = source.splitlines()
        relative = _relative_path(root, path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            receiver = node.func.value
            if not (
                node.func.attr in {"insert", "append"}
                and isinstance(receiver, ast.Attribute)
                and receiver.attr == "path"
                and isinstance(receiver.value, ast.Name)
                and receiver.value.id == "sys"
            ):
                continue
            line_number = node.lineno
            line = lines[line_number - 1] if line_number <= len(lines) else ""
            if BOOTSTRAP_PATTERN.search(line):
                occurrences.append(
                    BootstrapOccurrence(
                        path=relative,
                        line=line_number,
                        text=line.strip(),
                    )
                )
    return tuple(occurrences)


def _ruff_executable() -> str | None:
    found = shutil.which("ruff")
    if found:
        return found
    candidate = Path(sys.executable).resolve().parent / "Scripts" / "ruff.exe"
    return str(candidate) if candidate.is_file() else None


def _ruff_findings(root: Path, *, run_ruff: bool) -> tuple[str, ...]:
    if not run_ruff:
        return ()
    executable = _ruff_executable()
    if executable is None:
        return ()
    targets = [
        name
        for name in ("RUNTIME", "WORLD", "CHARACTER", "TOOLS", "VALIDATION", "TESTS")
        if (root / name).is_dir()
    ]
    if not targets:
        return ()
    result = subprocess.run(
        [
            executable,
            "check",
            *targets,
            "--select",
            "F401,F841",
            "--output-format",
            "concise",
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    lines = (result.stdout + result.stderr).splitlines()
    return tuple(line.strip() for line in lines if re.match(r"^\S+[:\\]\d+[:\\]\d+:", line))


def scan(root: Path, *, run_ruff: bool = True) -> LeanAuditReport:
    """Scan source files below ``root`` without mutating the repository."""

    resolved_root = root.resolve()
    files = _discover_files(resolved_root)
    relative_files = tuple(_relative_path(resolved_root, path) for path in files)
    classifications = {
        relative: _classify(relative) for relative in relative_files
    }
    empty_markers = tuple(
        relative
        for relative, path in zip(relative_files, files)
        if path.name == "__init__.py" and path.stat().st_size == 0
    )
    return LeanAuditReport(
        classifications=classifications,
        tracked_source_files=relative_files,
        empty_package_markers=empty_markers,
        exact_duplicate_groups=_duplicate_files(resolved_root, files),
        duplicate_functions=_duplicate_functions(resolved_root, files),
        bootstrap_occurrences=_bootstrap_occurrences(resolved_root, files),
        entrypoint_candidates=_entrypoint_candidates(resolved_root, files),
        ruff_findings=_ruff_findings(resolved_root, run_ruff=run_ruff),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--report")
    parser.add_argument("--skip-ruff", action="store_true")
    args = parser.parse_args(argv)
    report = scan(Path(args.root), run_ruff=not args.skip_ruff)
    if args.report:
        report.write_json(Path(args.report))
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
