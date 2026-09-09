"""Check shading-only changes and render an old/new review comparison."""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--before', required=True, type=Path)
    p.add_argument('--after', required=True, type=Path)
    p.add_argument('--label', default='Shaded v2')
    args = p.parse_args()
    manifest = json.loads((args.after / 'manifest.json').read_text(encoding='utf-8'))
    rings = {(0, 0, 0, 255), (255, 251, 240, 255)}
    counts = []
    for category in manifest['categories']:
        for item in category['items']:
            relative = Path(category['id']) / (item['id'] + '.png')
            old = Image.open(args.before / relative).convert('RGBA')
            new = Image.open(args.after / relative).convert('RGBA')
            assert old.size == new.size == (18, 18)
            assert old.getchannel('A').tobytes() == new.getchannel('A').tobytes(), relative
            changed = 0
            for a, b in zip(old.getdata(), new.getdata()):
                if a in rings or b in rings: assert a == b, relative
                if a != b: changed += 1
            assert changed > 0, relative
            counts.append(changed)
    assert len(counts) == 200
    result = {'changed_sprites': 200, 'identical_alpha_masks': 200,
              'identical_black_and_cream_masks': 200,
              'changed_pixels_min': min(counts), 'changed_pixels_max': max(counts)}
    (args.after / 'comparison_audit.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    samples = [('01_food_drinks', 'coffee', 'Ceramic cup'),
               ('01_food_drinks', 'apple', 'Apple'),
               ('02_stationery', 'sticky', 'Folded note'),
               ('03_equipment', 'laptop', 'Laptop screen'),
               ('07_it_security', 'cloud', 'Cloud'),
               ('08_facilities', 'chair', 'Office chair'),
               ('09_finance', 'piggy', 'Piggy bank'),
               ('10_rewards', 'trophy', 'Gold trophy')]
    sheet = Image.new('RGB', (920, 1050), '#252830')
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype('C:/Windows/Fonts/tahoma.ttf', 19)
    draw.text((25, 15), 'BEFORE  /  ADDED LIGHT & SHADOW  -  SAME GEOMETRY', font=font, fill='#FFFBF0')
    for i, (category, name, label) in enumerate(samples):
        x = 25 + (i % 2) * 455
        y = 62 + (i // 2) * 245
        draw.text((x, y), label, font=font, fill='#FFFBF0')
        for j, root in enumerate((args.before, args.after)):
            icon = Image.open(root / category / (name + '.png')).convert('RGBA')
            icon = icon.resize((180, 180), Image.Resampling.NEAREST)
            sheet.paste(icon, (x + j * 215, y + 30), icon)
            draw.text((x + j * 215, y + 211), 'Before' if j == 0 else args.label, font=font, fill='#B5BBC4')
    sheet.save(args.after / 'before_after.png')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
