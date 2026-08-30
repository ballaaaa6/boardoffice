from __future__ import annotations

import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'PREVIEW' / 'GROUND_FOOTPRINTS'
OUT.mkdir(parents=True, exist_ok=True)

import sys
sys.path.insert(0, str(ROOT))
from WORLD.RUNTIME.ground_footprint_core import GroundFootprintCore

fp = GroundFootprintCore(ROOT / 'WORLD')
world_assets = json.load(open(ROOT/'WORLD/REGISTRY/world_assets.json', encoding='utf-8'))['assets']
embedded_assets = json.load(open(ROOT/'WORLD/REGISTRY/embedded_assets.json', encoding='utf-8'))['assets']
blob_dir = ROOT/'WORLD/ASSETS/blobs'

try:
    title_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 18)
    small_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 12)
except Exception:
    title_font = small_font = ImageFont.load_default()

GRID=(45,255,130,210)
SHADOW=(0,0,0,105)
BG=(26,28,36,255)
TXT=(245,245,245,255)
SUB=(185,190,200,255)


def asset_path(asset_id):
    rec = world_assets.get(asset_id) or embedded_assets.get(asset_id)
    return blob_dir / f"{rec['blob_id']}.png"


def draw_filled_cells(layer, profile_id, origin):
    p=fp.profiles[profile_id]
    ux,uy=fp.fine_grid['u_step_px']; vx,vy=fp.fine_grid['v_step_px']
    ox,oy=origin
    d=ImageDraw.Draw(layer)
    for u in range(p['axes']['u_cells']):
        for v in range(p['axes']['v_cells']):
            cx=ox + u*ux + v*vx
            cy=oy + u*uy + v*vy
            pts=[(cx,cy-1),(cx+2,cy),(cx,cy+1),(cx-2,cy)]
            d.polygon(pts, fill=SHADOW)
    corners=fp._profile_outer_corners(p)
    d.line(corners+[corners[0]], fill=GRID, width=1)


def render(asset_id, filename, transform=None, title=None):
    resolved=fp.resolve_asset(asset_id, transform=transform)
    im=Image.open(asset_path(asset_id)).convert('RGBA')
    if resolved and resolved['derived_transform']=='FLIP_X':
        im=im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    corners=resolved['outer_corners_asset_px']
    xs=[0,im.width]+[x for x,y in corners]; ys=[0,im.height]+[y for x,y in corners]
    pad=6
    minx=min(xs)-pad; miny=min(ys)-pad; maxx=max(xs)+pad; maxy=max(ys)+pad
    canvas=Image.new('RGBA',(maxx-minx,maxy-miny),(0,0,0,0))
    # footprint layer using the resolved transformed corners as filled polygon plus fine cell view for NORMAL.
    layer=Image.new('RGBA',canvas.size,(0,0,0,0))
    ld=ImageDraw.Draw(layer)
    shifted=[(x-minx,y-miny) for x,y in corners]
    ld.polygon(shifted, fill=SHADOW)
    ld.line(shifted+[shifted[0]], fill=GRID, width=1)
    canvas.alpha_composite(layer)
    canvas.alpha_composite(im,(-minx,-miny))
    # redraw outline over asset for review readability only
    top=Image.new('RGBA',canvas.size,(0,0,0,0)); td=ImageDraw.Draw(top)
    td.line(shifted+[shifted[0]], fill=GRID, width=1)
    canvas.alpha_composite(top)
    scale=8
    zoom=canvas.resize((canvas.width*scale,canvas.height*scale),Image.Resampling.NEAREST)
    card=Image.new('RGBA',(max(420,zoom.width+28),zoom.height+72),BG)
    card.alpha_composite(zoom,((card.width-zoom.width)//2,58))
    cd=ImageDraw.Draw(card)
    cd.text((14,10),title or asset_id,font=title_font,fill=TXT)
    cd.text((14,34),f"{resolved['profile_id']} | {resolved['author_size_fine_cells']} fine-cells | {resolved['derived_transform']}",font=small_font,fill=SUB)
    card.save(OUT/filename)
    return card

items=[
    ('desk_000.part_00','01_desk_standard.png',None,'Desk standard — canonical footprint'),
    ('desk_000.part_00','02_desk_mirrored_DERIVED.png','FLIP_X','Desk mirrored — derived from same profile'),
    ('chair_000.part_01','03_chair_standard.png',None,'Chair standard — parts 00-02 family'),
    ('embedded.floor00.reception_group','04_reception_f0.png',None,'Reception Floor00'),
    ('floor01.reception','05_reception_f1.png',None,'Reception Floor01'),
    ('floor02.reception','06_reception_f2_plus.png',None,'Reception Floor02+ family'),
]
cards=[]
for a,f,t,title in items:
    cards.append(render(a,f,t,title))

# contact sheet 2x3
w=max(c.width for c in cards); h=max(c.height for c in cards)
contact=Image.new('RGBA',(w*2+18,h*3+36),BG)
for i,c in enumerate(cards):
    x=(i%2)*(w+18)+(w-c.width)//2
    y=(i//2)*h+(h-c.height)//2
    contact.alpha_composite(c,(x,y))
contact.save(OUT/'GROUND_FOOTPRINT_CONTACT.png')
print(OUT/'GROUND_FOOTPRINT_CONTACT.png')
