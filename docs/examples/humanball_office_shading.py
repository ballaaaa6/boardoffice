"""Authored native surface patches for the office batch's shading revision.

Each row chooses one material and explicit highlight/shadow rectangles on
that object's existing surface. Patches are clipped to the ORIGINAL material
mask so they never paint over labels, controls, openings or another part.
No blur, image scaling, automatic coordinate ramp or outline modification.
"""
from PIL import ImageColor

# Original material -> selective light, turning-plane shadow.
RAMPS = {
    'PAPER': ('#EADBB5', '#FFF2CF', '#B9A180'),
    'WHITE': ('#FFF1CF', '#FFF8DE', '#C6B08B'),
    'PS': ('#AE9673', '#D9BF91', '#7E6B58'),
    'BLUE': ('#5888AF', '#A2D2DC', '#344F78'),
    'BL': ('#A3D1DE', '#DBF3E9', '#6495B5'),
    'BS': ('#2D4D6C', '#638CA7', '#1B304D'),
    'TEAL': ('#60AC9D', '#B5DFB7', '#34766F'),
    'TL': ('#B2E0B9', '#E3F1CA', '#72AA96'),
    'RED': ('#C75C66', '#FFA58B', '#8C3B56'),
    'RL': ('#F8A392', '#FFD4AA', '#C86872'),
    'GOLD': ('#E5B659', '#FFE6A6', '#B77B3E'),
    'GL': ('#FFE0A0', '#FFF2CC', '#D5A35E'),
    'GS': ('#A27038', '#D6A957', '#704B35'),
    'PURPLE': ('#926BB3', '#D9B3E6', '#5B407E'),
    'PL': ('#D9B4DF', '#F1DBE9', '#A179B4'),
    'DS': ('#51406D', '#9272A6', '#352C51'),
    'METAL': ('#9CADBB', '#DDEDE8', '#5B728E'),
    'ML': ('#DCE5DE', '#FFF4D8', '#99AEBC'),
    'MS': ('#54677F', '#9FBECA', '#344259'),
    'BROWN': ('#AF784B', '#E4B677', '#744B39'),
    'WOOD': ('#E0AB6D', '#FFE0A1', '#A96D49'),
    'DARK': ('#283B4D', '#476277', '#172634'),
    'ORANGE': ('#EEA54D', '#FFD38A', '#CB743E'),
}

# id material | highlight x0 y0 x1 y1 | shadow x0 y0 x1 y1
# Positions refer to the real body/face/overlap, not a canvas-wide light mask.
SPECS = {
'01_food_drinks': '''
coffee PAPER 5 7 6 10 8 11 11 12
tea TEAL 5 7 6 9 7 11 11 12
water BLUE 7 6 8 8 10 7 12 13
soda RED 6 5 7 7 9 11 12 13
milk PAPER 5 5 6 6 7 12 10 14
juice GOLD 5 6 6 10 8 12 12 14
donut RED 5 4 7 5 10 8 13 11
sandwich PAPER 9 7 11 8 5 10 13 11
pizza GOLD 5 6 7 7 9 11 12 14
burger WOOD 5 6 7 7 10 13 13 14
fries RED 5 9 6 11 8 13 12 14
salad BLUE 5 9 7 10 10 10 13 13
apple RED 5 6 6 8 6 11 10 14
banana GOLD 4 7 5 9 11 10 13 13
orange ORANGE 5 6 7 7 10 9 12 12
cake RED 4 9 5 10 11 9 14 13
cookie WOOD 4 5 6 6 10 10 13 12
noodles RED 5 7 6 8 8 12 11 14
lunchbox PAPER 5 7 6 9 7 10 8 12
icecream RL 6 4 8 5 9 6 11 7
''',
'02_stationery': '''
pen BLUE 9 5 10 7 6 11 8 14
pencil GOLD 9 5 10 7 6 11 8 14
eraser BLUE 4 10 6 10 7 12 9 14
highlighter GOLD 8 5 9 7 8 9 10 12
marker MS 9 5 10 7 6 11 8 14
ruler GOLD 9 5 11 7 6 11 8 14
scissors METAL 5 4 6 5 9 6 11 8
stapler RED 5 7 8 7 10 7 14 9
tape BLUE 4 11 6 12 11 12 14 14
correction TL 6 5 8 6 8 9 10 10
paperclip METAL 4 6 4 8 10 10 12 13
binder_clip DARK 5 9 7 10 9 12 11 14
sticky GOLD 4 4 6 5 11 7 13 10
notebook PAPER 7 4 9 5 10 10 11 13
clipboard PAPER 6 6 6 9 10 12 12 13
envelope PAPER 4 7 6 7 9 11 14 12
stamp RED 6 10 8 11 10 11 14 12
punch BLUE 5 8 7 9 11 9 14 10
nameplate PAPER 6 7 8 7 10 9 13 11
desk_board BS 6 5 8 5 10 9 12 10
''',
'03_equipment': '''
laptop BS 6 5 7 7 10 7 12 9
monitor DARK 5 5 7 5 11 7 13 9
keyboard METAL 4 6 8 6 12 10 14 11
mouse METAL 6 10 7 11 10 8 12 12
desk_phone METAL 5 7 5 9 11 10 14 13
printer BLUE 4 8 6 9 12 10 14 12
scanner BS 5 6 7 6 10 7 12 8
copier METAL 4 9 4 11 11 11 13 14
projector METAL 4 6 6 7 10 11 14 12
webcam BLUE 7 4 9 4 10 8 11 11
conference_camera METAL 5 7 6 9 10 10 12 11
microphone METAL 11 4 12 4 11 6 13 8
speaker BS 4 9 4 10 8 11 14 12
headset BLUE 4 5 5 6 12 5 14 7
usb RED 6 7 8 7 7 12 10 14
external_drive BS 6 5 8 6 11 8 12 14
power_strip PAPER 4 8 4 9 9 10 14 10
lamp BLUE 5 4 6 5 7 5 10 6
calculator BLUE 5 5 5 9 12 7 12 14
charger BLUE 5 13 7 13 10 13 13 14
''',
'04_documents': '''
folder GOLD 4 9 5 12 11 11 14 14
report PAPER 6 4 8 5 12 7 13 13
spreadsheet PAPER 5 6 5 9 10 11 13 14
presentation PAPER 4 5 6 5 12 10 14 11
memo WHITE 6 6 7 6 12 7 13 13
checklist PAPER 5 4 7 4 12 8 13 14
contract PAPER 6 4 8 5 12 7 13 10
invoice PAPER 6 4 8 5 12 8 13 13
receipt WHITE 6 2 8 3 10 11 12 14
payslip TL 6 4 7 5 10 6 11 7
calendar PAPER 5 7 7 7 12 8 13 13
agenda PAPER 7 4 9 5 10 11 11 13
todo PAPER 5 5 6 5 10 7 11 13
chart_report PAPER 6 4 8 5 12 8 13 13
archive_box BROWN 4 8 5 11 10 12 14 14
document_tray BLUE 4 11 6 11 11 11 14 12
letter WHITE 6 4 8 4 12 7 13 13
signature PAPER 4 9 6 9 11 12 13 14
confirmation TL 6 6 8 6 10 9 12 12
confidential METAL 6 4 7 5 12 6 13 13
''',
'05_communication': '''
meeting_table WOOD 5 6 8 6 11 9 15 10
whiteboard WHITE 5 4 8 4 12 8 13 10
projection_screen PAPER 4 4 7 4 12 9 14 10
presenter MS 7 5 7 9 9 10 10 14
speech BLUE 4 5 6 6 8 9 13 11
email BLUE 4 7 5 8 10 11 14 12
chat TEAL 8 11 9 12 11 13 14 15
calling TEAL 5 4 6 5 10 12 13 14
video_call DS 4 5 4 7 11 9 13 9
handshake WOOD 6 8 7 9 8 11 11 13
feedback BLUE 5 10 6 12 10 13 13 14
question PURPLE 5 5 6 5 10 6 13 8
vote TEAL 5 9 6 11 11 12 14 14
agenda_board PAPER 5 4 8 4 12 8 13 12
attendee PAPER 5 8 5 10 11 11 13 13
bell GOLD 6 8 7 10 8 11 12 12
broadcast BLUE 9 6 10 7 8 9 12 12
brainstorm GOLD 6 6 7 7 10 8 12 10
send BLUE 10 8 11 9 9 10 11 13
group WOOD 4 12 5 12 11 13 13 14
''',
'06_workflow': '''
start TEAL 6 5 7 6 10 7 14 8
focus RED 4 6 4 8 10 12 13 14
progress TEAL 4 9 5 9 7 10 9 10
done TEAL 4 6 6 7 10 11 13 13
waiting GOLD 7 5 8 5 9 12 11 13
urgent GOLD 7 6 7 8 11 11 14 14
blocked RED 5 9 6 11 8 13 10 14
review BL 6 5 7 5 8 8 9 9
approved TEAL 7 4 8 5 11 11 14 12
rejected RED 4 6 5 8 10 12 13 14
backlog GOLD 4 11 6 11 11 13 14 14
priority RED 6 4 7 5 10 7 13 9
deadline PAPER 5 7 6 8 10 12 13 14
upload BLUE 7 8 8 10 9 11 10 14
download TEAL 6 5 6 8 9 10 11 13
sync TEAL 5 4 7 4 12 5 14 8
bug RED 6 9 7 10 10 11 12 14
idea GOLD 5 5 6 7 11 7 13 10
analysis GOLD 11 4 11 8 12 9 12 13
milestone MS 6 11 7 12 12 11 15 14
''',
'07_it_security': '''
server MS 5 3 5 10 11 10 12 15
cloud BLUE 7 6 9 7 11 9 15 11
database BLUE 5 7 6 8 11 9 13 13
network TEAL 3 12 4 12 5 14 6 15
wifi BLUE 5 3 8 3 11 5 14 7
router BLUE 4 11 6 11 11 13 14 14
firewall RED 3 7 5 7 9 13 14 14
padlock GOLD 5 9 6 11 7 13 10 14
key GOLD 4 4 5 5 11 12 14 14
password PAPER 4 7 6 7 10 11 14 11
twofactor DARK 6 4 7 5 10 10 11 13
qr PAPER 3 3 7 3 13 8 14 14
code DARK 7 6 9 6 10 12 14 13
settings METAL 5 5 7 6 10 11 12 13
ai_chip DS 6 7 7 8 9 11 11 11
backup DARK 5 5 5 7 10 9 12 10
update BLUE 6 3 8 4 12 6 14 8
virus PL 7 5 8 6 9 8 10 9
shield BLUE 9 4 10 5 10 10 12 12
battery TEAL 5 8 6 9 7 10 9 11
''',
'08_facilities': '''
employee_id PAPER 5 8 5 10 11 12 13 14
keycard BLUE 5 9 6 10 10 11 13 12
chair BLUE 6 3 7 5 10 5 12 7
desk WOOD 4 7 7 7 11 8 15 9
locker BLUE 5 3 6 3 11 9 13 14
elevator METAL 5 6 6 10 10 11 12 14
restroom BLUE 4 4 6 4 12 12 14 14
firstaid PAPER 4 7 5 9 9 12 11 13
extinguisher RED 7 6 8 8 9 12 11 13
sanitizer TEAL 6 8 6 11 10 13 12 14
tissues PURPLE 4 10 6 11 11 12 14 13
water_cooler BL 7 3 8 4 10 5 12 7
umbrella BLUE 4 5 5 6 12 6 15 8
coat_rack BLUE 3 5 4 7 5 8 6 10
cleaning_cart GOLD 5 9 6 10 8 11 10 12
bin TEAL 5 7 5 10 11 11 12 14
plant BROWN 6 11 7 13 9 13 11 15
wall_clock PAPER 5 5 7 6 10 10 12 12
thermostat PAPER 4 6 7 6 11 11 14 12
floorplan PAPER 5 5 6 6 11 11 12 12
''',
'09_finance': '''
banknote TL 6 7 7 7 11 9 13 10
coins GOLD 4 6 5 7 11 11 13 13
wallet BROWN 4 6 6 7 10 12 14 13
credit_card BLUE 4 6 6 6 11 11 14 11
bank METAL 6 4 7 5 10 5 13 6
pos MS 5 8 5 11 12 10 14 14
piggy RED 4 8 6 9 9 10 12 12
calculator GOLD 5 5 5 8 12 12 14 14
budget TEAL 5 6 6 8 7 12 10 14
income TEAL 10 7 10 9 12 10 13 13
expense RED 10 6 10 8 12 11 13 13
salary_slip PAPER 6 4 8 4 11 7 13 9
tax PAPER 6 7 6 9 12 8 13 13
sales_funnel TEAL 5 6 7 6 9 8 11 10
shopping_cart BLUE 6 7 7 8 12 9 14 10
briefcase BROWN 4 7 6 8 11 12 14 14
company METAL 5 3 5 9 11 9 12 14
investment GOLD 11 5 11 8 12 9 12 13
exchange GOLD 4 4 5 5 11 12 13 13
sales_target BLUE 4 6 4 8 10 12 13 14
''',
'10_rewards': '''
trophy GOLD 7 4 8 6 10 6 12 9
medal GOLD 6 9 7 10 10 11 12 13
star GOLD 9 6 10 7 10 8 13 12
gift RED 5 9 6 11 11 12 12 14
certificate PAPER 5 6 5 8 12 10 13 12
ribbon GL 7 4 8 5 9 7 11 9
badge PURPLE 9 4 10 5 10 10 12 12
crown GOLD 5 8 6 9 11 11 13 13
party_hat PURPLE 7 8 8 9 11 12 14 14
confetti GOLD 5 9 6 10 7 12 9 13
fireworks GOLD 8 2 8 3 8 13 8 15
birthday RED 4 11 6 12 11 12 14 13
event_calendar PAPER 5 7 6 8 12 10 13 13
milestone_flag PAPER 7 3 8 4 11 8 14 9
launch PAPER 8 3 9 4 10 9 11 10
leaderboard GOLD 7 6 7 10 9 11 10 14
applause WOOD 5 10 6 11 7 12 9 14
team_flag BLUE 5 5 6 6 11 8 14 10
promotion GOLD 6 11 7 12 10 12 11 14
holiday PAPER 5 7 7 7 12 11 13 13
''',
}


def apply(categories):
    audit = []
    errors = []
    for category in categories:
        specs = {}
        for row in SPECS[category['id']].strip().splitlines():
            name, material, *coords = row.split()
            specs[name] = (material, list(map(int, coords)))
        assert set(specs) == {item[0] for item in category['items']}
        updated = []
        for name, label, original in category['items']:
            material, coords = specs[name]
            base, light, shadow = [ImageColor.getcolor(c, 'RGBA') for c in RAMPS[material]]
            result = original.copy()
            counts = []
            for rect, color in ((coords[:4], light), (coords[4:], shadow)):
                x0, y0, x1, y1 = rect
                count = 0
                for y in range(y0, y1 + 1):
                    for x in range(x0, x1 + 1):
                        if original.getpixel((x, y)) == base:
                            result.putpixel((x, y), color)
                            count += 1
                counts.append(count)
            if not all(counts): errors.append((category['id'], name, counts))
            assert original.getchannel('A').tobytes() == result.getchannel('A').tobytes()
            updated.append((name, label, result))
            audit.append({'category': category['id'], 'id': name, 'material': material,
                          'highlight_pixels': counts[0], 'shadow_pixels': counts[1],
                          'original_fill_mask_preserved': True})
        category['items'] = updated
    assert not errors, ('empty shading patches', errors)
    return audit
