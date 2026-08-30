from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRECTORY_PARTS = {
    '.git',
    '.mypy_cache',
    '.pytest_cache',
    '.ruff_cache',
    '__pycache__',
    '00_STARTING_POINT',
    'LOCAL_REVIEW',
    'PREVIEW',
    'releases',
}
EXCLUDED_FILE_NAMES = {'HANDOFF_v1.8.3.md'}


def iter_payload_files(root: Path):
    for path in sorted(root.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        parts = relative.split('/')
        if any(part in EXCLUDED_DIRECTORY_PARTS for part in parts[:-1]):
            continue
        if parts[-1] in EXCLUDED_FILE_NAMES or parts[-1].endswith(('.pyc', '.pyo')):
            continue
        if relative.startswith('WORLD/COMPILED_NAV/OCCUPANCY/'):
            continue
        yield path, relative


def build_archive(root: Path, output: Path, *, force: bool = False) -> dict[str, object]:
    root = root.resolve()
    output = output.resolve()
    if output.exists() and not force:
        raise FileExistsError(f'Refusing to overwrite existing archive: {output}')
    output.parent.mkdir(parents=True, exist_ok=True)

    files = list(iter_payload_files(root))
    names = [relative for _path, relative in files]
    forbidden = [
        name for name in names
        if name == 'HANDOFF_v1.8.3.md'
        or name.startswith('LOCAL_REVIEW/')
        or name.startswith('00_STARTING_POINT/')
        or name.startswith('WORLD/COMPILED_NAV/OCCUPANCY/')
        or any(part in EXCLUDED_DIRECTORY_PARTS for part in name.split('/')[:-1])
    ]
    if forbidden:
        raise ValueError(f'Forbidden payload entries: {forbidden[:10]}')
    if names.count('HANDOFF.md') != 1:
        raise ValueError(f'Expected exactly one active HANDOFF.md, found {names.count("HANDOFF.md")}')

    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, relative in files:
            info = zipfile.ZipInfo(relative, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())

    sha256 = hashlib.sha256(output.read_bytes()).hexdigest()
    top_levels = sorted({name.split('/')[0] for name in names})
    return {
        'status': 'PASS',
        'archive': str(output),
        'sha256': sha256,
        'entry_count': len(names),
        'top_levels': top_levels,
        'excluded_directory_parts': sorted(EXCLUDED_DIRECTORY_PARTS),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Build a clean deterministic Phase 8C release archive.')
    parser.add_argument('--root', default=str(PROJECT_ROOT))
    parser.add_argument('--output', required=True)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    result = build_archive(Path(args.root), Path(args.output), force=args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
