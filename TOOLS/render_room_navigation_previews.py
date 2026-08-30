from __future__ import annotations
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from WORLD.RUNTIME.room_navigation_core import RoomNavigationCore
from WORLD.RUNTIME.floor_renderer import FloorRenderer

nav=RoomNavigationCore(ROOT/'WORLD')
renderer=FloorRenderer(ROOT/'WORLD')
OUT=ROOT/'PREVIEW'/'NAVIGATION'
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'AUTHOR').mkdir(parents=True,exist_ok=True)
(OUT/'CELL_MAP').mkdir(parents=True,exist_ok=True)
BLUE=(0,125,255,255); YELLOW=(255,214,0,255); GRID=(0,220,190,80)
ROOM=(37,208,111); OUTSIDE=(23,25,34); UVGRID=(71,77,94)
TEXT=(244,246,250); SUB=(178,184,196)
try:
    F1=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',25)
    F2=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',14)
    FC=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',20)
except Exception:
    F1=F2=FC=ImageFont.load_default()

def px(u,v): return nav.uv_vertex_to_pixel(u,v)
def cell_poly(u,v): return [px(u,v),px(u+1,v),px(u+1,v+1),px(u,v+1)]

def author(floor):
    base=renderer.render(floor).convert('RGBA')
    lay=Image.new('RGBA',base.size,(0,0,0,0)); d=ImageDraw.Draw(lay)
    cells=nav.room_cell_set(floor)
    for u,v in cells:
        pts=cell_poly(u,v); d.line(pts+[pts[0]],fill=GRID,width=1)
    dom=nav.domain(floor)['polygon_uv']; pts=[px(u,v) for u,v in dom]; d.line(pts+[pts[0]],fill=BLUE,width=2)
    edge=nav.portal(floor)['edge_uv']; d.line([px(*edge[0]),px(*edge[1])],fill=YELLOW,width=4)
    return Image.alpha_composite(base,lay).resize((2400,2400),Image.Resampling.NEAREST)

def cellmap(floor,cell_px=5):
    cells=nav.room_cell_set(floor); dom=nav.domain(floor)['polygon_uv']
    min_u=min(p[0] for p in dom)-3; max_u=max(p[0] for p in dom)+3
    min_v=min(p[1] for p in dom)-3; max_v=max(p[1] for p in dom)+3
    left,top,right,bottom=42,86,28,54
    w=left+(max_u-min_u)*cell_px+right; h=top+(max_v-min_v)*cell_px+bottom
    im=Image.new('RGB',(w,h),OUTSIDE); d=ImageDraw.Draw(im)
    for u,v in cells:
        x=left+(u-min_u)*cell_px; y=top+(v-min_v)*cell_px
        d.rectangle((x,y,x+cell_px-1,y+cell_px-1),fill=ROOM)
    for u in range(min_u,max_u+1):
        x=left+(u-min_u)*cell_px; d.line((x,top,x,top+(max_v-min_v)*cell_px),fill=UVGRID,width=1)
    for v in range(min_v,max_v+1):
        y=top+(v-min_v)*cell_px; d.line((left,y,left+(max_u-min_u)*cell_px,y),fill=UVGRID,width=1)
    a,b=nav.portal(floor)['edge_uv']; ax=left+(a[0]-min_u)*cell_px; ay=top+(a[1]-min_v)*cell_px; bx=left+(b[0]-min_u)*cell_px; by=top+(b[1]-min_v)*cell_px
    d.line((ax,ay,bx,by),fill=YELLOW,width=max(3,cell_px))
    d.text((left,18),f'{floor.upper()} ROOM CELL MAP',fill=TEXT,font=F1)
    d.text((left,52),f'green=ROOM  yellow=PORTAL  dark=OUTSIDE  cells={len(cells)}',fill=SUB,font=F2)
    return im

def contact(items,title,out):
    thumbs=[]
    for label,im in items:
        t=im.copy(); t.thumbnail((720,720),Image.Resampling.NEAREST); thumbs.append((label,t))
    pad=24; lh=42; W=max(i.width for _,i in thumbs)+pad*2; H=sum(i.height+lh+pad for _,i in thumbs)+pad
    c=Image.new('RGB',(W,H),(20,22,30)); d=ImageDraw.Draw(c); y=pad
    for label,im in thumbs:
        d.text((pad,y),label,fill=TEXT,font=FC); y+=lh; c.paste(im,(pad,y)); y+=im.height+pad
    c.save(out)

a=[]; c=[]
for f in ['floor00','floor01','floor02']:
    ai=author(f); ci=cellmap(f)
    ai.save(OUT/'AUTHOR'/f'{f}_author_preview_4x.png')
    ci.save(OUT/'CELL_MAP'/f'{f}_room_cell_map.png')
    a.append((f,ai)); c.append((f,ci))
contact(a,'AUTHOR',OUT/'AUTHOR_CONTACT.png')
contact(c,'CELL',OUT/'CELL_MAP_CONTACT.png')
print(OUT/'AUTHOR_CONTACT.png')
print(OUT/'CELL_MAP_CONTACT.png')
