"""Export editable sources, verify round trips, and package the office review batch."""
import argparse
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path
from PIL import Image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--aseprite', required=True, type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    files = [root / name for name in ('manifest.json', 'audit.json', 'overview_200.png', 'README.md')]
    sources = ['humanball_office_200.py', 'package_humanball_office_200.py', 'humanball_office_shading.py', 'humanball_office_cinematic.py']
    if (root / 'shading_audit.json').exists():
        files.extend(root / name for name in ('shading_audit.json', 'comparison_audit.json', 'before_after.png'))
        sources.append('audit_humanball_shading.py')
    verified = 0
    with tempfile.TemporaryDirectory(prefix='humanball-roundtrip-') as temp:
        for category in manifest['categories']:
            folder = root / category['id']
            names = [item['id'] for item in category['items']] + ['sheet_native']
            for name in names:
                png = folder / (name + '.png')
                source = folder / (name + '.aseprite')
                restored = Path(temp) / (category['id'] + '_' + name + '.png')
                for src, dst in ((png, source), (source, restored)):
                    subprocess.run([str(args.aseprite.resolve()), '-b', str(src), '--save-as', str(dst)],
                                   check=True, capture_output=True, timeout=30,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    assert dst.is_file(), dst
                with Image.open(png) as original, Image.open(restored) as result:
                    assert original.size == result.size, png
                    assert original.convert('RGBA').tobytes() == result.convert('RGBA').tobytes(), png
                verified += 1
                files.extend([png, source])
            files.extend(folder / name for name in ('manifest.json', 'sheet_10x.png', 'sheet_review.png'))
            print(category['id'] + ': 21 editable sources verified', flush=True)
    assert verified == 210
    audit = root / 'export_audit.json'
    audit.write_text(json.dumps({'editable_individuals': 200, 'editable_sheets': 10,
                                'pixel_identical_roundtrips': verified}, indent=2), encoding='utf-8')
    files.append(audit)
    archive = root / 'humanball_office_200.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as output:
        for file in files:
            output.write(file, file.relative_to(root).as_posix())
        for name in sources:
            output.write(Path(__file__).parent / name, 'source/' + name)
    with zipfile.ZipFile(archive) as output:
        assert output.testzip() is None
        assert len(output.namelist()) == len(set(output.namelist()))
        assert len(output.namelist()) == len(files) + len(sources)
    print(json.dumps({'roundtrips': verified, 'archive_entries': len(files) + len(sources), 'zip': str(archive)}))


if __name__ == '__main__':
    main()
