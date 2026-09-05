"""Code-native twin-turbo transverse V-twin thermal system schematic.

Coordinates describe a functional overhead schematic, not fabrication dimensions.
Selectable callouts and navigation share this one layout.
"""
import math
import pygame
from .widgets.ui_utils import font, fit_font_size

# key: (center x, center y, concise label), in a 1000 x 400 drawing.
NODES = {
    "AMBIENT_AIR": (500, 18, "AMBIENT"),
    "RAD_IN": (425, 55, "RAD IN"), "RAD_OUT": (575, 55, "RAD OUT"),
    "PRE_WMI": (500, 104, "PRE WMI"), "POST_WMI": (500, 134, "POST WMI"),
    "PLENUM_IAT": (500, 164, "PLENUM"),
    "OIL_GALLERY": (500, 318, "OIL GALLERY"),
    "OIL_COOLER_IN": (425, 365, "OIL IN"), "OIL_COOLER_OUT": (575, 365, "OIL OUT"),
}
for side, mirror in (("LEFT", False), ("RIGHT", True)):
    for key, x, y, label in (
        ("COMP_IN",85,133,"COMP IN"), ("COMP_OUT",85,163,"COMP OUT"),
        ("IC_IN",205,65,"IC IN"), ("IC_OUT",205,95,"IC OUT"),
        ("RUNNER_IAT",350,184,"RUNNER"),
        ("HEAD_COOLANT",320,219,"COOLANT"), ("HEAD_METAL",320,249,"HEAD METAL"),
        ("EGT",245,285,"EGT"), ("TURBINE_OUT",85,285,"EXHAUST OUT"),
        ("TURBO_OIL_DRAIN",85,344,"OIL DRAIN"),
    ):
        NODES[f"{key}_{side}"]=(1000-x if mirror else x,y,label)


def neighbor(key, dx, dy):
    """Prefer the visible row/column; no wrapping across the schematic."""
    x,y,_=NODES.get(key,NODES["AMBIENT_AIR"])
    choices=[]
    for candidate,(cx,cy,_) in NODES.items():
        forward=(cx-x)*dx+(cy-y)*dy
        cross=abs((cy-y)*dx+(cx-x)*dy)
        if forward>0:
            # Close row/column alignment wins, but don't skip a nearby branch
            # to chase a far-away callout with a tiny alignment advantage.
            choices.append((forward+cross*2.5,cross,forward,candidate))
    return min(choices)[-1] if choices else key


def draw_architecture(surface, area, state, selected, dev, score_color):
    sx,sy=area.width/1000,area.height/400
    def point(x,y):return (round(area.x+x*sx),round(area.y+y*sy))
    def rect(x,y,w,h):return pygame.Rect(*point(x,y),round(w*sx),round(h*sy))
    def line(color, points, width=2):
        pygame.draw.lines(surface,color,False,[point(x,y) for x,y in points],width)
    def label(text,x,y,color=(102,146,151),size=10):
        surface.blit(font(size,bold=True).render(text,True,color),point(x,y))
    def pipe(points,color):
        line((9,20,25),points,7);line(color,points,2)
        # Static directional arrow at the midpoint of the final segment.
        a,b=points[-2:];vx,vy=b[0]-a[0],b[1]-a[1];length=math.hypot(vx,vy)
        if length>0:
            ux,uy=vx/length,vy/length;mx,my=(a[0]+b[0])/2,(a[1]+b[1])/2
            pygame.draw.polygon(surface,color,[point(mx+ux*5,my+uy*5),point(mx-ux*4-uy*4,my-uy*4+ux*4),point(mx-ux*4+uy*4,my-uy*4-ux*4)])
    def heat(key):
        reading=state.thermal.get(key)
        return score_color((reading.thermal_dev if dev else reading.thermal_abs) if reading else 0, bool(reading and reading.valid))
    pygame.draw.rect(surface,(4,12,17),area,border_radius=6)
    old_clip=surface.get_clip();surface.set_clip(area)
    # Blueprint field and a mechanical centerline make the transverse layout legible.
    for x in range(0,1001,40):line((10,24,30),[(x,0),(x,400)],1)
    for y in range(0,401,40):line((10,24,30),[(0,y),(1000,y)],1)
    for y in range(75,340,12):line((24,49,56),[(500,y),(500,y+5)],1)
    label("FRONT",574,5,(144,183,190),9)
    line((144,183,190),[(624,22),(624,6),(619,11),(624,6),(629,11)],1)
    charge=(57,169,184);exhaust=(195,108,60);coolant=(72,125,175);oil=(167,143,66)
    # Forward radiator and low oil cooler, independent of the charge-air path.
    pygame.draw.rect(surface,(13,27,34),rect(356,34,288,42),border_radius=4)
    for x in range(360,640,8):line((35,56,63),[(x,38),(x,72)],1)
    label("RADIATOR",449,32,(119,162,177),9)
    line(coolant,[(380,55),(295,55),(295,219),(320,219)])
    line(coolant,[(680,219),(705,219),(705,55),(620,55)])
    # Intake banks, distinct compressor/turbine housings and cylinder assemblies.
    for side,mirror in (("LEFT",False),("RIGHT",True)):
        def p(x,y):return (1000-x if mirror else x,y)
        def bank_pipe(points,color):pipe([p(x,y) for x,y in points],color)
        label(side+" BANK",35 if not mirror else 810,14,(146,180,184),11)
        bank_pipe([(85,133),(140,133),(140,193)],charge)
        bank_pipe([(140,193),(160,193),(160,45),(205,45),(205,65)],charge)
        bank_pipe([(205,95),(260,95),(260,104),(500,104)],charge)
        bank_pipe([(500,164),(420,164),(350,184),(320,219)],charge)
        bank_pipe([(320,249),(245,249),(245,285),(185,285),(185,236),(140,236)],exhaust)
        bank_pipe([(140,236),(85,236),(85,285),(42,285),(42,310)],exhaust)
        bank_pipe([(140,232),(140,344),(85,344),(85,382),(500,382),(500,318)],oil)
        x,_=p(205,65)
        pygame.draw.rect(surface,(13,31,36),rect(x-74,43,148,72),border_radius=5)
        for fy in range(47,113,6):line((42,75,79),[p(135,fy),p(275,fy)],1)
        label("INTERCOOLER",x-70,116,(104,158,168),9)
        # Turbo scroll outlines, shared shaft and blades (no inferred shaft speed).
        cx,_=p(140,213)
        pygame.draw.line(surface,(88,102,103),point(cx,187),point(cx,243),3)
        for y,key in ((194,"COMP_OUT_"+side),(239,"TURBINE_OUT_"+side)):
            housing=rect(cx-32,y-28,64,56)
            pygame.draw.ellipse(surface,tuple(max(12,int(c*.20)) for c in heat(key)),housing)
            pygame.draw.ellipse(surface,heat(key),housing,2)
            pygame.draw.arc(surface,(112,146,151),housing.inflate(-8,-8),.3,5.2,2)
            for angle in range(0,360,60):
                a=math.radians(angle)
                line((78,108,117),[(cx,y),(cx+18*math.cos(a),y+18*math.sin(a))],2)
            pygame.draw.circle(surface,(152,176,178),point(cx,y),3)
        label("TURBO",cx-28,271,(166,153,130),9)
        # Finned cylinder bank leans outward from the shared crankcase.
        polygon=[p(300,200),p(365,180),p(495,295),p(445,322)]
        pygame.draw.polygon(surface,tuple(max(15,int(c*.23)) for c in heat("HEAD_METAL_"+side)),[point(*v) for v in polygon])
        pygame.draw.polygon(surface,heat("HEAD_METAL_"+side),[point(*v) for v in polygon],2)
        for n in range(5):
            yy=255+n*8;xx=373+n*8
            line((66,85,89),[p(xx-26,yy+14),p(xx+30,yy-12)],2)
    # Shared water/meth treatment, plenum and V-twin crankcase.
    pipe([(500,104),(500,164)],charge)
    pygame.draw.ellipse(surface,(121,172,175),rect(488,145,24,14),1)
    line((168,199,194),[(491,146),(509,157)],2)
    pygame.draw.rect(surface,(11,38,42),rect(426,149,148,30),border_radius=7)
    label("WMI",570,117,charge,10)
    line(charge,[(565,124),(559,124),(540,134)],1)
    pygame.draw.ellipse(surface,(23,36,44),rect(427,272,146,66))
    pygame.draw.ellipse(surface,(92,111,118),rect(427,272,146,66),2)
    pygame.draw.ellipse(surface,(40,55,62),rect(460,282,80,42),2)
    label("GL500 / V-TWIN",439,287,(170,191,190),10)
    pygame.draw.rect(surface,(20,30,31),rect(355,349,290,40),border_radius=4)
    for x in range(360,642,9):line((54,58,47),[(x,352),(x,386)],1)
    label("OIL COOLER",448,389,oil,9)
    line(oil,[(500,318),(500,340),(425,340),(425,365)])
    line(oil,[(575,365),(602,365),(602,318),(535,318)])
    # Sensor callouts overlay physical components; only these are selectable.
    rectangles={}
    for key,(x,y,name) in NODES.items():
        box=rect(x-62,y-12,124,24);rectangles[key]=box
        reading=state.thermal.get(key);valid=bool(reading and reading.valid)
        color=heat(key);focus=key==selected
        pygame.draw.rect(surface,(12,23,29),box,border_radius=3)
        pygame.draw.rect(surface,(234,249,243) if focus else color,box,2 if focus else 1,border_radius=3)
        pygame.draw.rect(surface,color,(box.x+2,box.y+2,3,box.height-4))
        value=f"{reading.temperature_c:.0f}" if valid else "--"
        vs=font(10,bold=True).render(value,True,(238,248,243) if focus else color)
        size=fit_font_size(name,box.width-vs.get_width()-16,box.height-5,start_size=10,bold=True)
        ts=font(size,bold=True).render(name,True,(221,237,236) if focus else (160,187,192))
        surface.blit(ts,(box.x+8,box.centery-ts.get_height()//2))
        surface.blit(vs,(box.right-vs.get_width()-5,box.centery-vs.get_height()//2))
    surface.set_clip(old_clip)
    return rectangles
