from pathlib import Path
from PIL import Image, ImageDraw
import json

import argparse

parser = argparse.ArgumentParser(description='Reproduce the author-approved HumanBall entertainment artwork.')
parser.add_argument('--output', type=Path, required=True, help='Dedicated output directory; matching generated files are overwritten.')
ROOT = parser.parse_args().output.resolve()
ROOT.mkdir(parents=True, exist_ok=True)
INK='#000000'; CREAM='#FFFBF0'
items=[]
def canvas():
    im=Image.new('RGBA',(18,18)); return im,ImageDraw.Draw(im)
def rows(im, entries, col):
    d=ImageDraw.Draw(im)
    for y,a,b in entries: d.line((a,y,b,y),fill=col)
def dilate(s): return {(x+a,y+b) for x,y in s for a in (-1,0,1) for b in (-1,0,1)}
def add(name,label,im):
    f={(x,y) for y in range(18) for x in range(18) if im.getpixel((x,y))[3]}
    b=dilate(f)-f; c=dilate(f|b)-f-b
    assert all(0<=x<18 and 0<=y<18 for x,y in f|b|c),name
    out=Image.new('RGBA',(18,18)); d=ImageDraw.Draw(out)
    for points,col in [(c,CREAM),(b,INK)]:
        for p in points: d.point(p,fill=col)
    out.alpha_composite(im)
    out.save(ROOT/(name+'.png'))
    items.append((name,label,out,f,b,c))

# 01 Modern twin-stick controller: narrow bridge, sloping long handles.
im,d=canvas()
rows(im,[(4,5,6),(4,11,12),(5,4,13),(6,4,13),(7,3,14),(8,3,14),(9,3,6),(9,11,14),(10,2,5),(10,12,15),(11,2,5),(11,12,15),(12,2,4),(12,13,15)],'#46677B')
rows(im,[(5,5,6),(5,11,12),(6,4,5),(6,12,13)],'#A3D8DA')
rows(im,[(8,4,13),(10,3,4),(10,13,14),(11,2,4),(11,13,15),(12,2,3),(12,14,15)],'#294454')
d.rectangle((5,7,6,8),fill='#172A39');d.rectangle((11,7,12,8),fill='#172A39')
d.point((5,7),fill='#99BAC1');d.point((11,7),fill='#99BAC1')
d.line((7,5,7,6),fill='#162934');d.line((6,6,8,6),fill='#162934')
d.point((11,5),fill='#FFB34C');d.point((12,6),fill='#E87150')
d.point((9,6),fill='#9AE3E3')
f={(x,y) for y in range(18) for x in range(18) if im.getpixel((x,y))[3]}
assert f=={(17-x,y) for x,y in f}
add('game_controller','Game controller',im)

# 02 Handheld: wide flat console, distinct screen and side controls.
im,d=canvas();d.rectangle((3,6,14,11),fill='#936CC4')
d.rectangle((4,5,13,5),fill='#C6A5E6');d.rectangle((4,12,13,12),fill='#5E418B')
d.rectangle((6,6,11,10),fill='#263B57');d.line((7,7,10,7),fill='#69B8BF');d.line((7,8,8,8),fill='#397387')
d.line((4,7,4,9),fill='#352743');d.line((3,8,5,8),fill='#352743')
d.point((13,7),fill='#FFD172');d.point((13,9),fill='#FF8D96');d.line((7,11,10,11),fill='#C0A2E0')
add('handheld_console','Handheld console',im)

# 03 Arcade: side profile with overhang and projecting control deck.
im,d=canvas();d.polygon([(5,2),(12,2),(12,5),(10,8),(13,10),(12,14),(4,14),(4,10),(6,9),(5,5)],fill='#BE475A')
d.rectangle((5,2,11,3),fill='#FFC677');d.rectangle((6,3,10,3),fill='#FFE4A2')
d.polygon([(6,5),(11,5),(9,8),(6,8)],fill='#20394B');d.line((7,5,10,5),fill='#84D6CE');d.point((7,6),fill='#4D9EAF')
d.polygon([(6,9),(10,9),(12,10),(5,10)],fill='#EC8290');d.point((7,9),fill='#272E40');d.point((10,10),fill='#FFE099')
d.polygon([(10,11),(12,11),(11,14),(10,14)],fill='#6D2C49');d.line((5,12,5,13),fill='#F1898B');d.rectangle((7,12,8,13),fill='#5A293D')
add('arcade_machine','Arcade machine',im)

# 04 Ball, thin shaft and trapezoid base.
im,d=canvas();rows(im,[(3,7,10),(4,6,11),(5,6,11),(6,7,10)],'#E75A52')
rows(im,[(3,7,9),(4,7,8)],'#FFAD83');rows(im,[(6,8,10)],'#972F45')
d.rectangle((8,7,9,10),fill='#53667D');d.line((8,7,8,9),fill='#BAC6D6')
d.polygon([(5,11),(12,11),(14,13),(13,14),(4,14),(3,13)],fill='#357EAD')
d.line((5,11,11,11),fill='#80C7D5');d.line((4,14,13,14),fill='#214762');d.point((12,12),fill='#FFCF62')
add('joystick','Joystick',im)

# 05 Approved open headphone construction.
im,d=canvas();rows(im,[(3,6,11),(4,4,13),(5,3,4),(5,13,14),(6,3,3),(6,14,14),(7,3,3),(7,14,14)],'#8067BC')
rows(im,[(3,6,10),(4,4,6)],'#CCB6F1');d.rectangle((3,8,5,12),fill='#7452A4');d.rectangle((12,8,14,12),fill='#7452A4')
d.line((3,8,3,11),fill='#B996E0');d.line((14,8,14,10),fill='#9F7ECD')
d.line((5,9,5,12),fill='#352B57');d.line((12,9,12,12),fill='#352B57')
d.line((3,12,4,12),fill='#58B5AD');d.line((13,12,14,12),fill='#58B5AD')
add('headphones','Headphones',im)

# 06 Two separate buds and stems, staggered vertically.
im,d=canvas()
for x,y in [(3,4),(11,6)]:
    d.rectangle((x,y,x+2,y+2),fill='#C8E5DE');d.line((x,y,x+1,y),fill='#EFF5DD')
    d.line((x+2,y+1,x+2,y+2),fill='#396B7D');d.rectangle((x+1,y+3,x+2,y+6),fill='#7AB5B9')
    d.line((x+2,y+4,x+2,y+6),fill='#3D7688')
add('earbuds','Earbuds',im)

# 07 Rectangular wooden cabinet and two drivers.
im,d=canvas();d.rectangle((5,3,12,14),fill='#A76B3C');d.line((5,3,11,3),fill='#EAB36D');d.line((5,4,5,13),fill='#CB9054');d.line((12,4,12,14),fill='#644630')
d.rectangle((6,4,10,13),fill='#344650');d.rectangle((7,5,9,7),fill='#141E2B');d.point((8,6),fill='#688A96')
rows(im,[(9,7,9),(10,6,10),(11,6,10),(12,7,9)],'#172A34');d.line((7,9,8,9),fill='#6CA5AF');d.point((8,11),fill='#A1C5C3')
add('speaker','Speaker',im)

# 08 Tall capsule grille with U cradle and small base.
im,d=canvas();rows(im,[(2,8,9),(3,7,10),(4,7,10),(5,7,10),(6,7,10),(7,8,9)],'#91B5C9')
d.line((7,3,8,3),fill='#E4EFE8');d.line((9,6,10,6),fill='#49677F')
for y in [4,6]:d.line((8,y,9,y),fill='#31465E')
d.line([(5,6),(5,8),(7,10),(10,10),(12,8),(12,6)],fill='#66849C')
d.line((8,11,8,13),fill='#BCD4DB');d.line((9,11,9,13),fill='#3D5873');d.line((6,14,11,14),fill='#526A85')
add('microphone','Microphone',im)

# 09 Oval note head and upright stem.
im,d=canvas();d.rectangle((10,3,11,11),fill='#A957B7')
rows(im,[(11,7,10),(12,5,10),(13,5,9),(14,6,8)],'#B663BD')
d.line((10,3,10,10),fill='#E0A3DF');rows(im,[(12,6,7)],'#E8B4E5');rows(im,[(14,6,8),(13,8,9)],'#743378')
add('music_note','Music note',im)

# 10 Approved disc geometry; grooves and concentric label.
im,d=canvas();disc=[(3,7,10),(4,5,12),(5,4,13),(6,4,13),(7,3,14),(8,3,14),(9,3,14),(10,3,14),(11,4,13),(12,4,13),(13,5,12),(14,7,10)]
rows(im,disc,'#26334D');rows(im,[(11,12,13),(12,11,13),(13,8,12),(14,7,10)],'#151F34')
d.line((6,5,9,5),fill='#687899');d.line((5,6,5,7),fill='#596A8D');d.line((8,12,11,12),fill='#425474')
rows(im,[(7,8,9),(8,7,10),(9,7,10),(10,8,9)],'#D3647B');d.line((8,7,9,7),fill='#F8B093');d.point((8,8),fill='#141D31');d.point((9,9),fill='#9A405E')
add('vinyl_record','Vinyl record',im)

# 11 Upright acoustic guitar, approved bouts/waist construction.
im,d=canvas();d.rectangle((8,2,9,4),fill='#AD713C');d.line((8,5,8,8),fill='#D6A265')
rows(im,[(8,6,10),(9,6,11),(10,7,10),(11,6,11),(12,5,12),(13,5,12),(14,6,11),(15,7,10)],'#CC8C48')
rows(im,[(8,6,8),(9,6,7),(11,6,7),(12,5,6),(13,6,6)],'#F0C378')
rows(im,[(12,11,12),(13,11,12),(14,9,11),(15,7,10)],'#85512E')
d.rectangle((8,9,9,10),fill='#3D2B25');d.line((7,13,10,13),fill='#513726');d.point((8,3),fill='#F3CB83')
add('guitar','Guitar',im)

# 12 Ticket has genuine external side notches, perforation and star.
im,d=canvas();rows(im,[(6,3,14),(7,3,14),(8,5,12),(9,5,12),(10,3,14),(11,3,14)],'#E6B856')
d.line((3,6,14,6),fill='#FFE0A0');d.line((3,11,14,11),fill='#B37B3B')
for y in [7,9,11]:d.point((11,y),fill='#815038')
d.line((7,7,7,9),fill='#B94C52');d.line((6,8,8,8),fill='#B94C52')
add('movie_ticket','Movie ticket',im)

# 13 Popcorn: kernels above a tapered red paper carton.
im,d=canvas();d.polygon([(4,8),(13,8),(11,14),(6,14)],fill='#C64F50')
d.line((5,9,6,12),fill='#F1C684');d.line((8,9,8,13),fill='#FFE3A0');d.line((11,9,10,13),fill='#F0C280');d.line((7,14,11,14),fill='#873345')
for x,y in [(5,5),(8,4),(11,5),(6,7),(9,7)]:
    d.rectangle((x,y,x+1,y+1),fill='#F6D48B');d.point((x,y),fill='#FFF0BB');d.point((x+1,y+1),fill='#CE9F51')
add('popcorn_box','Popcorn',im)

# 14 Reel holes, hub, silver material and short film tail.
im,d=canvas();rows(im,[(3,6,9),(4,4,11),(5,3,12),(6,3,12),(7,3,12),(8,3,12),(9,3,12),(10,4,11),(11,6,10)],'#93A7AE')
rows(im,[(4,5,9),(5,4,5)],'#D9E6DC');rows(im,[(9,11,12),(10,9,11),(11,6,10)],'#546878')
for x,y in [(6,5),(9,6),(5,8),(8,9)]:d.rectangle((x,y,x+1,y+1),fill='#2E3C4C')
d.point((7,7),fill='#E0B16D');d.line([(11,10),(13,11),(14,12),(14,14),(11,14)],fill='#798C99');d.point((13,14),fill='#CEDAD4')
add('film_reel','Film reel',im)

# 15 Compact side-view projector, two reels and protruding lens.
im,d=canvas()
for x in (5,10):
    d.rectangle((x,3,x+2,5),fill='#AAB9B8');d.point((x,3),fill='#DFE7D5');d.point((x+1,4),fill='#374A5B')
d.rectangle((4,7,11,11),fill='#579495');d.line((4,7,10,7),fill='#A0D3BE');d.line((5,11,11,11),fill='#345D70')
d.rectangle((12,8,14,10),fill='#59758A');d.line((14,8,14,10),fill='#9FC5D0')
d.line((5,12,5,13),fill='#718293');d.line((10,12,10,13),fill='#718293')
d.line((6,9,9,9),fill='#2D5261');d.point((5,8),fill='#E9C778')
add('projector','Projector',im)

# 16 Crisp overlapping cards, heart and spade.
im,d=canvas();d.polygon([(3,3),(9,3),(10,12),(4,13)],fill='#B4C7D8')
d.line((3,3,8,3),fill='#E1EBE4');d.line((4,4,4,9),fill='#426E94')
d.rectangle((7,5,14,14),fill='#E5D8B6');d.line((7,5,14,5),fill='#FFF0CA');d.line((14,6,14,14),fill='#AC987B');d.line((8,14,13,14),fill='#BBA689')
rows(im,[(8,9,9),(8,11,11),(9,9,11),(10,10,10)],'#BD4D58')
d.point((8,6),fill='#BD4D58');d.point((13,12),fill='#BD4D58')
add('playing_cards','Playing cards',im)

# 17 Approved projected cube, with three distinct planar values.
im,d=canvas();d.polygon([(8,2),(14,5),(8,8),(3,5)],fill='#F1D591')
d.polygon([(3,5),(8,8),(8,15),(3,11)],fill='#CE9D55')
d.polygon([(8,8),(14,5),(14,11),(8,15)],fill='#93633C')
d.line([(3,5),(8,8),(14,5)],fill='#735135');d.line((8,8,8,15),fill='#65452E')
d.line((4,6,4,9),fill='#E5BD75')
for p in [(8,5),(5,8),(6,11),(11,8),(12,10),(10,12)]:d.point(p,fill='#45352C')
add('dice','Dice',im)

# 18 Pawn with round head, collar, narrow shaft and plinth.
im,d=canvas();rows(im,[(2,8,9),(3,7,10),(4,7,10),(5,8,9),(6,6,11),(7,8,9),(8,8,9),(9,7,10),(10,7,10),(11,6,11),(12,5,12),(13,4,13),(14,4,13)],'#8C9BAC')
rows(im,[(3,7,8),(6,6,9),(9,7,7),(11,6,7),(13,4,10)],'#D1DCE0')
rows(im,[(4,9,10),(8,9,9),(10,9,10),(12,10,12),(14,4,13)],'#4B5B76')
add('chess_piece','Chess pawn',im)

# 19 Jigsaw: top tab, right tab, deep left socket.
im,d=canvas();d.rectangle((6,6,11,13),fill='#58AA87')
d.rectangle((8,3,10,5),fill='#58AA87');d.line((8,3,9,3),fill='#ACE0AB')
d.rectangle((12,8,14,10),fill='#58AA87')
d.rectangle((4,6,5,7),fill='#58AA87');d.rectangle((4,11,5,13),fill='#58AA87')
d.line((6,6,10,6),fill='#A4DCA1');d.line((4,6,5,6),fill='#A4DCA1');d.line((7,7,7,10),fill='#82C79C')
d.line((6,13,11,13),fill='#2E725F');d.line((11,11,11,12),fill='#2E725F');d.line((14,9,14,10),fill='#2E725F')
add('puzzle_piece','Puzzle piece',im)

# 20 Open comic: two page planes and central valley, panel and speech balloon.
im,d=canvas();d.polygon([(3,4),(6,4),(8,6),(8,14),(6,12),(3,12)],fill='#E7C584')
d.polygon([(9,6),(11,4),(14,4),(14,12),(11,12),(9,14)],fill='#EDE2BC')
d.line((3,4,6,4),fill='#FFF0C5');d.line((11,4,14,4),fill='#FFF3D5')
d.line((8,6,8,13),fill='#865D48');d.line((9,6,9,13),fill='#BD9E77')
d.rectangle((4,6,6,8),fill='#B45159');d.point((5,7),fill='#F3AC74')
d.line((4,10,6,10),fill='#926449')
d.rectangle((11,6,13,8),fill='#82B3BE');d.point((11,9),fill='#82B3BE')
d.line((11,11,13,11),fill='#658699');d.line((14,10,14,12),fill='#C9B18A')
add('comic_book','Comic book',im)

sheet=Image.new('RGBA',(90,72))
review=Image.new('RGB',(1040,920),'#252830');rd=ImageDraw.Draw(review)
rd.text((22,12),'HUMANBALL / ENTERTAINMENT 20 / V6',fill='#EEE8D8')
for i,(name,label,im,f,b,c) in enumerate(items):
    col=i%5; row=i//5
    sheet.alpha_composite(im,(col*18,row*18))
    large=im.resize((180,180),Image.Resampling.NEAREST)
    review.paste(large,(22+col*204,44+row*214),large)
    rd.text((22+col*204,226+row*214),f'{i+1:02}  {label}',fill='#EEE8D8')
sheet.save(ROOT/'entertainment_20_native.png')
sheet.resize((900,720),Image.Resampling.NEAREST).save(ROOT/'entertainment_20_10x.png')
review.save(ROOT/'entertainment_20_review.png')
manifest={'version':6,'cell':[18,18],'columns':5,'rows':4,'borders':{'black':INK,'cream':CREAM,'width':1},'items':[{'index':i+1,'id':v[0],'label':v[1]} for i,v in enumerate(items)]}
(ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2))
audit=[]
for i,(name,label,expected,f,b,c) in enumerate(items):
    actual=Image.open(ROOT/(name+'.png')).convert('RGBA')
    assert actual.size==(18,18)
    assert set(actual.getchannel('A').getdata()) <= {0,255}
    assert actual.tobytes()==expected.tobytes()
    for points,color in [(b,INK),(c,CREAM)]:
        rgba=Image.new('RGBA',(1,1),color).getpixel((0,0))
        assert all(actual.getpixel(p)==rgba for p in points)
    assert sheet.crop(((i%5)*18,(i//5)*18,(i%5+1)*18,(i//5+1)*18)).tobytes()==actual.tobytes()
    audit.append({'id':name,'size':[18,18],'binary_alpha':True,'unclipped_complete_rings':True,'exact_sheet_cell':True})
(ROOT/'audit.json').write_text(json.dumps({'controller_silhouette_symmetric':True,'count':20,'items':audit},indent=2))
print('Created',len(items),'sprites. All complete borders fit 18x18; controller silhouette is mirrored.')
