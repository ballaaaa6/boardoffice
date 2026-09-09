"""Native curved-surface lighting study; seven discrete, hue-shifted tones.

Surface models replace v2's rectangular patches. Geometry/material masks come
from the original drawing. Object-specific profiles choose cylindrical,
ellipsoidal, toroidal, diagonal-shaft or beveled planar surface normals.
All illumination is sampled at native pixels; no blur or enlarged raster input.
"""
import math
from PIL import ImageColor
from humanball_office_shading import SPECS, RAMPS

# Deep cool shade -> core shade -> reflected mid -> base -> warm light -> key -> glint.
PALETTES = {
 'paper': ['#645A72','#99858D','#BDA58F','#DECAA5','#F0DCB5','#FFE9C7','#FFF5DB'],
 'blue': ['#242B4D','#344365','#466987','#6397B0','#91BDC9','#C1DDD9','#F2EDCE'],
 'teal': ['#243449','#315765','#3F827F','#64AB9B','#A2CDAA','#D6E1B8','#FFF0CE'],
 'red': ['#3C2C4C','#71334F','#A74561','#D76A72','#F19A88','#FFC6A1','#FFE9C4'],
 'gold': ['#433248','#735043','#A56E43','#D49B4F','#EDC273','#FFE2A1','#FFF3CD'],
 'purple': ['#282A45','#493959','#735183','#A078AE','#C9A4C8','#E9CACE','#FFE8D6'],
 'metal': ['#252C45','#3C4866','#61758F','#8EA6B6','#BDD0D2','#E3E8D7','#FFF2D6'],
 'wood': ['#413044','#674547','#916049','#C28A59','#E5B57B','#FFDAA3','#FFF0C6'],
 'dark': ['#111A2B','#1B2A42','#2C405A','#435C76','#688A9D','#A4BFBE','#E4DBBE'],
}
MEMBERS = {
 'paper': ['PAPER','WHITE','PS'], 'blue': ['BLUE','BL','BS'],
 'teal': ['TEAL','TL','TS'], 'red': ['RED','RL','RS'],
 'gold': ['GOLD','GL','GS'], 'purple': ['PURPLE','PL','DS'],
 'metal': ['METAL','ML','MS'], 'wood': ['WOOD','BROWN'], 'dark': ['DARK'],
}
EXTRA = {'TS':'#306E68', 'RS':'#833B53'}
FAMILY = {name: family for family, names in MEMBERS.items() for name in names}
FAMILY['ORANGE'] = 'gold'

# Profiles listed in manifest order, explicitly chosen for every object.
# P=beveled plane, C=vertical cylinder, H=horizontal cylinder,
# S=ellipsoid, T=torus, D=diagonal cylinder, B=soft convex panel.
PROFILES = {
 '01_food_drinks': 'C C C C P C T P P H C S S S S P S C P S',
 '02_stationery': 'D D P D D P D B P S D P P P P P C B P P',
 '03_equipment': 'P P P S P P P P P T S D P T C P P S P P',
 '04_documents': 'B P P P P P P P P P P P P P P P P P S P',
 '05_communication': 'P P P C B P B S P S P B P P P C P S P P',
 '06_workflow': 'B T H S C P C S C S P B S B B T S S C P',
 '07_it_security': 'P S C P T P P C D P P P P S P P T S B H',
 '08_facilities': 'P P B P P P P B C C P C S C P C C S P P',
 '09_finance': 'B C B P P P S P S B B P P C P B P C C T',
 '10_rewards': 'C S B B P S B C C C C H P B C P S B B P',
}

# Native bounds for important compound/curved parts: do not include stems,
# handles, leaves or detached decorations when defining their curvature.
BOUNDS = {
 ('01_food_drinks','coffee'):(4,6,11,12),
 ('01_food_drinks','tea'):(3,6,12,12),
 ('01_food_drinks','water'):(5,5,12,14),
 ('01_food_drinks','donut'):(4,4,13,11),
 ('01_food_drinks','apple'):(3,4,14,14),
 ('01_food_drinks','orange'):(3,4,14,15),
 ('01_food_drinks','icecream'):(4,3,13,10),
 ('03_equipment','mouse'):(5,5,12,14),
 ('03_equipment','webcam'):(6,4,11,11),
 ('03_equipment','microphone'):(8,2,14,8),
 ('05_communication','bell'):(4,4,13,12),
 ('05_communication','brainstorm'):(5,3,12,10),
 ('06_workflow','review'):(5,5,9,9),
 ('06_workflow','idea'):(4,2,13,11),
 ('06_workflow','bug'):(5,6,12,14),
 ('07_it_security','virus'):(5,5,12,12),
 ('08_facilities','wall_clock'):(4,4,13,13),
 ('09_finance','piggy'):(3,5,13,12),
 ('10_rewards','trophy'):(5,3,12,10),
 ('10_rewards','medal'):(5,7,12,14),
 ('10_rewards','ribbon'):(4,2,13,11),
}


def tone(profile, x, y, bounds):
    x0,y0,x1,y1 = bounds
    u = (x-(x0+x1)/2) / max((x1-x0+1)/2, 1)
    v = (y-(y0+y1)/2) / max((y1-y0+1)/2, 1)
    if profile == 'S':
        nx,ny = u*.91,v*.91
    elif profile == 'C':
        nx,ny = u*.96,v*.20
    elif profile == 'H':
        nx,ny = u*.20,v*.96
    elif profile == 'D':
        transverse = max(-.98,min(.98,(u+v)*1.45))
        nx,ny = transverse*.70,transverse*.70
    elif profile == 'T':
        radius = math.hypot(u,v)
        slope = max(-.94,min(.94,(radius-.56)*2.8))
        nx,ny = (u*slope/max(radius,.01),v*slope/max(radius,.01))
    elif profile == 'B':
        nx,ny = u*.66,v*.50
    else:
        # Mostly planar center, narrow bent/beveled right and bottom edges.
        nx = u*.14 + max(0,(u-.48))*.95
        ny = v*.10 + max(0,(v-.55))*.7
    nz = math.sqrt(max(.015,1-nx*nx-ny*ny))
    length = math.sqrt(nx*nx+ny*ny+nz*nz)
    nx,ny,nz = nx/length,ny/length,nz/length
    diffuse = max(0, -.64*nx-.48*ny+.60*nz)
    # Key light falloff, not a pasted highlight box. Specular contours follow N.
    specular = max(0,-.36*nx-.27*ny+.892*nz) ** (18 if profile in 'CTD' else 11)
    intensity = .16 + .87*diffuse + .22*specular
    if profile == 'P':
        intensity -= .09*math.hypot(u+.65,v+.65)
    # Restrained cool bounce within the colored edge; outline is untouched.
    if u>.78 and -.3<v<.65 and diffuse<.22:
        intensity = max(intensity,.27)
    thresholds = [.22,.36,.49,.64,.86,1.13]
    return sum(intensity >= edge for edge in thresholds)


def apply(categories):
    audit = []
    for category in categories:
        materials = {row.split()[0]:row.split()[1] for row in SPECS[category['id']].strip().splitlines()}
        profiles = PROFILES[category['id']].split()
        assert len(profiles)==len(category['items'])==20
        items=[]
        for (name,label,original), profile in zip(category['items'],profiles):
            family = FAMILY[materials[name]]
            colors = set()
            for member in MEMBERS[family]:
                color = RAMPS[member][0] if member in RAMPS else EXTRA[member]
                colors.add(ImageColor.getcolor(color,'RGBA'))
            if materials[name]=='ORANGE':
                colors = {ImageColor.getcolor(c,'RGBA') for c in ['#EEA54D','#DC873C']}
            mask = {(x,y) for y in range(18) for x in range(18) if original.getpixel((x,y)) in colors}
            assert mask,(name,'missing material')
            bounds=BOUNDS.get((category['id'],name),
                             (min(x for x,y in mask),min(y for x,y in mask),max(x for x,y in mask),max(y for x,y in mask)))
            palette=[ImageColor.getcolor(c,'RGBA') for c in PALETTES[family]]
            # Retain authored face seams, grooves and printed dark marks.
            # Small disconnected dark clusters get extra contrast; broad side
            # planes retain a one-step occlusion bias under the curved light.
            shadow_name = MEMBERS[family][-1]
            if len(MEMBERS[family]) > 1:
                shadow_hex = RAMPS[shadow_name][0] if shadow_name in RAMPS else EXTRA[shadow_name]
                shadow_color = ImageColor.getcolor(shadow_hex,'RGBA')
            else:
                shadow_color = None
            remaining = {p for p in mask if original.getpixel(p)==shadow_color}
            shadow_bias={}
            while remaining:
                start=remaining.pop(); component={start}; frontier=[start]
                while frontier:
                    ax,ay=frontier.pop()
                    for neighbor in ((ax-1,ay),(ax+1,ay),(ax,ay-1),(ax,ay+1)):
                        if neighbor in remaining:
                            remaining.remove(neighbor);component.add(neighbor);frontier.append(neighbor)
                bias=2 if len(component)<=12 else 1
                shadow_bias.update({p:bias for p in component})
            result=original.copy();used=set()
            for x,y in mask:
                level=max(0,tone(profile,x,y,bounds)-shadow_bias.get((x,y),0))
                result.putpixel((x,y),palette[level]);used.add(level)
            assert result.getchannel('A').tobytes()==original.getchannel('A').tobytes()
            assert result.tobytes()!=original.tobytes()
            items.append((name,label,result))
            audit.append({'category':category['id'],'id':name,'surface_profile':profile,
                          'surface_bounds':bounds,'material':family,'used_tones':sorted(used),
                          'palette_hex':PALETTES[family],'shape_preserved':True})
        category['items']=items
    return audit
