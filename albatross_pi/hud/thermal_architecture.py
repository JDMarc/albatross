"""Code-native twin-turbo transverse V-twin thermal system schematic.

Coordinates describe a functional overhead schematic, not fabrication dimensions.
Selectable callouts and navigation share this one layout.
"""
import math
import pygame
from .widgets.ui_utils import font, fit_font_size
from .thermal_style import thermal_chrome

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


def cylinder_geometry(side):
    """Build the bank and its inset fin spans from the same four corners."""
    polygon = ((300, 200), (365, 180), (495, 295), (445, 322))

    def lerp(a, b, t):
        return tuple(x + (y - x) * t for x, y in zip(a, b))

    def bank_point(point):
        x, y = point
        return (1000 - x if side == "RIGHT" else x, y)

    fins = []
    for n in range(8):
        t = .16 + n * .09
        outer = lerp(polygon[0], polygon[3], t)
        inner = lerp(polygon[1], polygon[2], t)
        # Inset both ends so line width and pixel rounding stay on the casting.
        fins.append((bank_point(lerp(outer, inner, .10)),
                     bank_point(lerp(outer, inner, .90))))
    return tuple(map(bank_point, polygon)), fins


class FlowAnimation:
    """Presentation-only phases; boost controls visual revolutions, never torque."""
    ARROW_SPACING = 70.0
    FLOW_SPEED = 34.0
    MAX_VISUAL_BOOST_PSI = 40.0
    IDLE_RPS = 0.15
    RPS_PER_PSI = 0.075
    SPOOL_SECONDS = 0.35

    def __init__(self):
        self.last_ms = None
        self.rotors = {"LEFT": 0.0, "RIGHT": 0.0}
        self.speeds = {"LEFT": 0.0, "RIGHT": 0.0}
        self.flow = 0.0
        self.raster = 0.0

    @classmethod
    def boost(cls, engine, side):
        value = getattr(engine, "boost_" + side.lower() + "_psi", -1)
        if not math.isfinite(value) or value < 0:
            value = engine.boost_psi
        return max(0.0, min(cls.MAX_VISUAL_BOOST_PSI, value)) if math.isfinite(value) else 0.0

    def advance(self, engine, now_ms):
        # Bound the delta so returning to the map never causes a large jump.
        dt = 0.0 if self.last_ms is None else max(0.0, min(.1, (now_ms - self.last_ms) / 1000.0))
        self.last_ms = now_ms
        self.flow = (self.flow + dt * self.FLOW_SPEED) % self.ARROW_SPACING
        self.raster = (self.raster + dt * 42.0) % 400.0
        for side in self.rotors:
            # Screen rotations/second only, explicitly not a turbo RPM estimate.
            target = self.IDLE_RPS + self.RPS_PER_PSI * self.boost(engine, side)
            previous = self.speeds[side]
            alpha = 1 - math.exp(-dt / self.SPOOL_SECONDS)
            self.speeds[side] += (target - previous) * alpha
            # Integrate the exponential exactly, independent of frame cadence.
            turns = target * dt + (previous - target) * self.SPOOL_SECONDS * alpha
            self.rotors[side] = (self.rotors[side] + turns * 360) % 360


def draw_architecture(surface, area, state, selected, dev, score_color, animation, colors):
    chrome=thermal_chrome(colors)
    sx,sy=area.width/1000,area.height/400
    def point(x,y):return (round(area.x+x*sx),round(area.y+y*sy))
    def rect(x,y,w,h):return pygame.Rect(*point(x,y),round(w*sx),round(h*sy))
    def line(color, points, width=2):
        pygame.draw.lines(surface,color,False,[point(x,y) for x,y in points],width)
    def label(text,x,y,color=None,size=10):
        surface.blit(font(size,bold=True).render(text,True,chrome["muted"] if color is None else color),point(x,y))
    def pipe(points,color):
        line(chrome["shadow"],points,7);line(color,points,2)
        # Follow the complete polyline, including corners, with spaced chevrons.
        lengths=[math.dist(a,b) for a,b in zip(points,points[1:])]
        distance=animation.flow
        total_length=sum(lengths)
        while distance<total_length:
            remaining=distance
            for a,b,length in zip(points,points[1:],lengths):
                if length>0 and remaining<=length:
                    ux,uy=(b[0]-a[0])/length,(b[1]-a[1])/length
                    mx,my=a[0]+ux*remaining,a[1]+uy*remaining
                    pygame.draw.polygon(surface,color,[point(mx+ux*5,my+uy*5),point(mx-ux*4-uy*4,my-uy*4+ux*4),point(mx-ux*4+uy*4,my-uy*4-ux*4)])
                    break
                remaining-=length
            distance+=animation.ARROW_SPACING
    def heat(key):
        reading=state.thermal.get(key)
        return score_color((reading.thermal_dev if dev else reading.thermal_abs) if reading else 0, bool(reading and reading.valid))
    pygame.draw.rect(surface,chrome["field"],area,border_radius=6)
    old_clip=surface.get_clip();surface.set_clip(area)
    # Subtle phosphor raster under the schematic, never over sensor text.
    for y in range(2,400,4):line(chrome["raster"],[(0,y),(1000,y)],1)
    # Blueprint field and avionics-style edge graduations.
    for x in range(0,1001,40):line(chrome["grid"],[(x,0),(x,400)],1)
    for y in range(0,401,40):line(chrome["grid"],[(0,y),(1000,y)],1)
    # A low-contrast CRT refresh sweep lives behind every component and reading.
    for offset,role in ((-6,"raster"),(-3,"grid"),(0,"sweep"),(3,"grid")):
        y=(animation.raster+offset)%400
        line(chrome[role],[(18,y),(982,y)],1)
    for y in range(40,381,10):
        tick=12 if y%40==0 else 6
        line(chrome["ticks"],[(3,y),(3+tick,y)],1)
        line(chrome["ticks"],[(997-tick,y),(997,y)],1)
    for x,y,dx,dy in ((3,3,1,1),(997,3,-1,1),(3,397,1,-1),(997,397,-1,-1)):
        line(chrome["edge"],[(x+dx*20,y),(x,y),(x,y+dy*18)],2)
    for y in range(75,340,12):line(chrome["centerline"],[(500,y),(500,y+5)],1)
    label("FRONT",574,5,chrome["ink"],9)
    line(chrome["ink"],[(624,22),(624,6),(619,11),(624,6),(629,11)],1)
    charge=(57,169,184);exhaust=(195,108,60);coolant=(72,125,175);oil=(167,143,66)
    # Forward radiator and low oil cooler, independent of the charge-air path.
    pygame.draw.rect(surface,chrome["component"],rect(356,34,288,42),border_radius=4)
    for x in range(360,640,8):line(chrome["centerline"],[(x,38),(x,72)],1)
    label("RADIATOR",449,32,chrome["muted"],9)
    line(coolant,[(380,55),(295,55),(295,219),(320,219)])
    line(coolant,[(680,219),(705,219),(705,55),(620,55)])
    # Intake banks, distinct compressor/turbine housings and cylinder assemblies.
    for side,mirror in (("LEFT",False),("RIGHT",True)):
        def p(x,y):return (1000-x if mirror else x,y)
        def bank_pipe(points,color):pipe([p(x,y) for x,y in points],color)
        label(side+" BANK",35 if not mirror else 810,14,chrome["ink"],11)
        line(chrome["edge"],[p(35,32),p(111,32),p(118,25)],1)
        bank_pipe([(85,133),(140,133),(140,193)],charge)
        bank_pipe([(140,193),(160,193),(160,45),(205,45),(205,65)],charge)
        bank_pipe([(205,95),(260,95),(260,104),(500,104)],charge)
        bank_pipe([(500,164),(420,164),(350,184),(320,219)],charge)
        bank_pipe([(320,249),(245,249),(245,285),(185,285),(185,236),(140,236)],exhaust)
        bank_pipe([(140,236),(85,236),(85,285),(42,285),(42,310)],exhaust)
        bank_pipe([(140,232),(140,344),(85,344),(85,382),(500,382),(500,318)],oil)
        x,_=p(205,65)
        pygame.draw.rect(surface,chrome["component"],rect(x-74,43,148,72),border_radius=5)
        for fy in range(47,113,6):line(chrome["centerline"],[p(135,fy),p(275,fy)],1)
        label("INTERCOOLER",x-70,116,chrome["muted"],9)
        # A mirrored rotor animation correlated with bank boost, not shaft RPM.
        cx,_=p(140,213)
        pygame.draw.line(surface,chrome["edge"],point(cx,187),point(cx,243),3)
        for y,key in ((194,"COMP_OUT_"+side),(239,"TURBINE_OUT_"+side)):
            housing=rect(cx-32,y-28,64,56)
            pygame.draw.ellipse(surface,tuple(max(12,int(c*.20)) for c in heat(key)),housing)
            pygame.draw.ellipse(surface,heat(key),housing,2)
            pygame.draw.arc(surface,chrome["ink"],housing.inflate(-8,-8),.3,5.2,2)
            for angle in range(0,360,60):
                a=math.radians(angle+animation.rotors[side]*(-1 if mirror else 1))
                line(chrome["edge"],[(cx,y),(cx+18*math.cos(a),y+18*math.sin(a))],2)
            pygame.draw.circle(surface,chrome["ink"],point(cx,y),3)
        label("TURBO",cx-28,271,chrome["muted"],9)
        # Finned cylinder bank leans outward from the shared crankcase.
        polygon,fins=cylinder_geometry(side)
        pygame.draw.polygon(surface,tuple(max(15,int(c*.23)) for c in heat("HEAD_METAL_"+side)),[point(*v) for v in polygon])
        pygame.draw.polygon(surface,heat("HEAD_METAL_"+side),[point(*v) for v in polygon],2)
        for endpoints in fins:
            line(chrome["shadow"],endpoints,3)
            line(chrome["ink"],endpoints,1)
    # Shared water/meth treatment, plenum and V-twin crankcase.
    pipe([(500,104),(500,164)],charge)
    pygame.draw.ellipse(surface,chrome["edge"],rect(488,145,24,14),1)
    line(chrome["ink"],[(491,146),(509,157)],2)
    pygame.draw.rect(surface,chrome["component"],rect(426,149,148,30),border_radius=7)
    label("WMI",570,117,charge,10)
    line(charge,[(565,124),(559,124),(540,134)],1)
    pygame.draw.ellipse(surface,chrome["component"],rect(427,272,146,66))
    pygame.draw.ellipse(surface,chrome["edge"],rect(427,272,146,66),2)
    pygame.draw.ellipse(surface,chrome["centerline"],rect(460,282,80,42),2)
    label("GL500 / V-TWIN",439,287,chrome["ink"],10)
    pygame.draw.rect(surface,chrome["component"],rect(355,349,290,40),border_radius=4)
    for x in range(360,642,9):line(chrome["centerline"],[(x,352),(x,386)],1)
    label("OIL COOLER",448,389,oil,9)
    line(oil,[(500,318),(500,340),(425,340),(425,365)])
    line(oil,[(575,365),(602,365),(602,318),(535,318)])
    # Sensor callouts overlay physical components; only these are selectable.
    rectangles={}
    for key,(x,y,name) in NODES.items():
        box=rect(x-62,y-12,124,24);rectangles[key]=box
        reading=state.thermal.get(key);valid=bool(reading and reading.valid)
        color=heat(key);focus=key==selected
        pygame.draw.rect(surface,chrome["surface"],box,border_radius=3)
        pygame.draw.rect(surface,color,box,1,border_radius=3)
        if focus:
            # A steady acquisition bracket, not a flashing warning indicator.
            for bx,by,dx,dy in ((box.left,box.top,1,1),(box.right-1,box.top,-1,1),
                                (box.left,box.bottom-1,1,-1),(box.right-1,box.bottom-1,-1,-1)):
                pygame.draw.lines(surface,chrome["bright"],False,
                                  [(bx+dx*9,by),(bx,by),(bx,by+dy*5)],2)
        pygame.draw.rect(surface,color,(box.x+2,box.y+2,3,box.height-4))
        value=f"{reading.temperature_c:.0f}" if valid else "--"
        vs=font(10,bold=True).render(value,True,color)
        size=fit_font_size(name,box.width-vs.get_width()-16,box.height-5,start_size=10,bold=True)
        ts=font(size,bold=True).render(name,True,chrome["bright"] if focus else chrome["ink"])
        surface.blit(ts,(box.x+8,box.centery-ts.get_height()//2))
        surface.blit(vs,(box.right-vs.get_width()-5,box.centery-vs.get_height()//2))
    surface.set_clip(old_clip)
    return rectangles
