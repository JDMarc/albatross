"""Quick rider aids, measured throttle-curve plots, telemetry and event history."""
from pathlib import Path
import json,math,struct,time
import pygame
from ..dynamics import LEVELS,WEATHER
from .widgets.ui_utils import font,fit_font_size
ROOT=Path(__file__).resolve().parents[2]

class DynamicsMenu:
    labels=("TCS","AWC","THROTTLE CURVE","WEATHER ASSIST","WHEELIE TARGET","WHEELIE MAX","LEAN LEFT","LEAN RIGHT","RESTART POLICY","LIVE TELEMETRY","EVENT HISTORY","POWERTRAIN STOP")
    def __init__(self,path=Path("settings/dynamics.json")):
        self.path=Path(path);self.cursor=0;self.page="controls";self.callback=None;self.sequence=0;self.pending=None;self.sent_at=0;self.status="CONTROLLER CONFIRMED SETTINGS";self.preview_only=False
        self.engineering=json.loads((ROOT/"config/vdc_engineering.json").read_text(encoding="utf-8"))
        self.values=dict(tcs=2,awc=2,curve=0,weather=True,target=None,maximum=None,left=None,right=None,persistence=self.engineering["rider_persistence"])
        self.restored=False;self.restore_queue=[];self.configuration_matches=False
        self.stop_confirm_at=None;self.stop_requested=False;self.stop_sent_at=-1e9
        try:
            saved=json.loads(self.path.read_text(encoding="utf-8"))
            if saved.get("persistence")=="remember":
                for key in ("tcs","awc","curve"):
                    value=saved.get(key)
                    if type(value) is int and 0<=value<(3 if key=="curve" else 4):self.values[key]=value
                if type(saved.get("weather")) is bool:self.values["weather"]=saved["weather"]
                self.values["persistence"]="remember"
                for n,key in enumerate(("target","maximum","left","right")):
                    value=saved.get(key)
                    cap=self.engineering["values"]["hard_pitch" if n<2 else "lean_"+("left" if n==2 else "right")]
                    if isinstance(value,(int,float)) and math.isfinite(value) and cap is not None and 0<=value<=cap:
                        self.values[key]=value;self.restore_queue.append((n,value))
        except (OSError,ValueError,TypeError):pass
    def sync(self,d):
        self.configuration_matches=d.calibration_matches
        if d.online and d.faults&8192:
            self.status="POWERTRAIN STOP LATCHED / KEY OFF AND INSPECT";self.pending=None;self.restore_queue=[];return
        if self.stop_requested:
            self.status="STOP REQUEST UNCONFIRMED / USE PHYSICAL KILL SWITCH"
            if self.callback and time.monotonic()-self.stop_sent_at>=.1:self._send_stop()
            return
        if not d.online:self.status="VDC DATA STALE / SETTINGS NOT CONFIRMED";return
        if not self.restored:
            self.restored=True
            self.send();return
        if self.pending is not None:
            if d.ack==self.pending:self.pending=None;self.status="CONTROLLER CONFIRMED"
            elif time.monotonic()-self.sent_at>1:self.status="NO CONTROLLER ACK / LAST CONFIRMED SHOWN IN HUD"
            if self.pending is not None:return
        if self.restore_queue:
            parameter,value=self.restore_queue.pop(0);self.send(parameter,value);return
        self.values.update(tcs=d.tcs,awc=d.awc,curve=d.curve,weather=d.weather_assist)
        if d.calibrated:self.values.update(target=d.wheelie_target,maximum=d.wheelie_max,left=d.lean_left,right=d.lean_right)
    def save(self):
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            p=self.path.with_suffix(".tmp");p.write_text(json.dumps(self.values,indent=2),encoding="utf-8");p.replace(self.path)
        except OSError:self.status="SETTINGS SAVE FAILED / CHECK STORAGE"
    def send(self,parameter=None,value=None):
        self.sequence=(self.sequence+1)&255;self.pending=self.sequence;self.sent_at=time.monotonic()
        if parameter is None:
            v=self.values;frame=(0x208,bytes((1,v["tcs"],v["awc"],v["curve"],int(v["weather"]),0,self.sequence,0xA5)))
        else:frame=(0x209,struct.pack(">BBfBB",1,parameter,value,self.sequence,0xA5))
        if self.callback:self.callback(*frame);self.status="REQUEST SENT"
        else:self.status="PREVIEW / CAN UNAVAILABLE"
    def move(self,delta):
        self.stop_confirm_at=None
        if self.page=="controls":self.cursor=(self.cursor+delta)%len(self.labels)
    def adjust(self,delta,stopped=True):
        self.stop_confirm_at=None
        if self.page!="controls":return
        if self.pending is not None and time.monotonic()-self.sent_at<=1:self.status="WAITING FOR CONTROLLER ACK";return
        keys=("tcs","awc","curve","weather","target","maximum","left","right","persistence")
        if self.cursor>=len(keys):return
        key=keys[self.cursor]
        if key=="curve" and not self.configuration_matches:self.status="CALIBRATION VERSION NOT CONFIRMED";return
        if key in ("tcs","awc","curve"):self.values[key]=(self.values[key]+delta)%(3 if key=="curve" else 4)
        elif key=="weather":self.values[key]=not self.values[key]
        elif key=="persistence":
            if not stopped:self.status="STOP TO CHANGE RESTART POLICY";return
            self.values[key]="remember" if self.values[key]=="reset_on_start" else "reset_on_start";self.save();return
        else:
            capkey="hard_pitch" if key in ("target","maximum") else "lean_"+("left" if key=="left" else "right")
            cap=self.engineering["values"][capkey]
            if cap is None:self.status="ENGINEERING BOUND NOT SET";return
            self.values[key]=max(0,min(cap,(self.values[key] or 0)+delta))
            self.send(("target","maximum","left","right").index(key),self.values[key]);self.save();return
        self.send();self.save()
    def select(self):
        if self.page!="controls":self.page="controls";return
        if self.cursor==9:self.page="telemetry"
        elif self.cursor==10:self.page="events"
        elif self.cursor==11:
            now=time.monotonic()
            if self.stop_confirm_at is not None and now-self.stop_confirm_at<=3:
                self.stop_requested=True;self.pending=None;self.restore_queue=[];self._send_stop()
            else:self.stop_confirm_at=now;self.status="SELECT AGAIN WITHIN 3s TO STOP POWERTRAIN / NO RIDING BYPASS"
    def _send_stop(self):
        self.stop_sent_at=time.monotonic()
        self.status="STOP REQUEST UNCONFIRMED / USE PHYSICAL KILL SWITCH"
        if self.callback:
            try:self.callback(0x20A,bytes((1,ord('S'),ord('T'),ord('O'),ord('P'),0xA5)))
            except Exception:self.status="STOP TRANSMIT FAILED / USE PHYSICAL KILL SWITCH"
    def display_values(self):
        v=self.values
        def angle(x):return "ENGINEERING TBD" if x is None else f"{x:.0f} DEG"
        return (LEVELS[v["tcs"]],LEVELS[v["awc"]],self.engineering["curve_names"][v["curve"]],"ON" if v["weather"] else "OFF",angle(v["target"]),angle(v["maximum"]),angle(v["left"]),angle(v["right"]),"REMEMBER" if v["persistence"]=="remember" else "RESET ON START","SELECT TO OPEN","SELECT TO OPEN","SELECT TWICE / LATCHED")

def bike(surface,rect,pitch,slip,active,color,dim):
    """Code-native pixel motorcycle; rotation follows measured pitch, trail follows slip."""
    unit=min(rect.width/180,rect.height/105);origin=(rect.x+rect.width*.2,rect.y+rect.height*.78)
    angle=math.radians(max(-15,min(55,pitch)))
    def point(x,y):return (round(origin[0]+unit*(x*math.cos(angle)+y*math.sin(angle))),round(origin[1]+unit*(-x*math.sin(angle)+y*math.cos(angle))))
    pygame.draw.line(surface,dim,(rect.x+10,round(origin[1]+16*unit)),(rect.right-10,round(origin[1]+16*unit)),2)
    for x in (0,105):
        pygame.draw.circle(surface,color,point(x,0),max(4,int(15*unit)),max(2,int(2*unit)))
        pygame.draw.circle(surface,dim,point(x,0),max(2,int(5*unit)),1)
    for poly in [[(0,0),(28,-27),(55,-3),(0,0)],[(28,-27),(72,-27),(105,0)],[(55,-3),(76,-35),(86,-43),(94,-43)],[(15,-29),(48,-29)],[(42,-32),(60,-47),(77,-43)],[(60,-47),(48,-59),(34,-52),(42,-32)]]:
        pygame.draw.lines(surface,color,False,[point(x,y) for x,y in poly],max(2,int(3*unit)))
    if active:
        phase=(pygame.time.get_ticks()//60)%4
        for n in range(1,5):
            length=4+min(16,abs(slip));x=origin[0]-(n*14+phase*3)*unit
            pygame.draw.line(surface,color,(x,origin[1]+15*unit),(x-length*unit,origin[1]+15*unit),max(2,int(unit*2)))

def draw_curves(surface,rect,menu,colors,d):
    bg,bright,glow,fault=colors
    pygame.draw.rect(surface,bg,rect);pygame.draw.rect(surface,glow,rect,1)
    surface.blit(font(18,bold=True).render("RIDER INPUT / REQUESTED TORQUE",True,bright),(rect.x+20,rect.y+14))
    if not menu.configuration_matches and not menu.preview_only:
        surface.blit(font(16,bold=True).render("CALIBRATION VERSION NOT CONFIRMED",True,fault),(rect.x+20,rect.centery));return
    plot=pygame.Rect(rect.x+60,rect.y+60,rect.width-100,rect.height-115)
    for n in range(5):
        x=plot.x+plot.width*n/4;y=plot.bottom-plot.height*n/4
        pygame.draw.line(surface,(70,46,10),(x,plot.y),(x,plot.bottom),1)
        pygame.draw.line(surface,(70,46,10),(plot.x,y),(plot.right,y),1)
        surface.blit(font(12).render(str(n*25),True,glow),(plot.x-34,y-6))
        surface.blit(font(12).render(str(n*25),True,glow),(x-10,plot.bottom+8))
    palette=[(115,91,36),(232,166,29),(255,225,120)]
    missing=False
    for n,name in enumerate(menu.engineering["curve_names"]):
        values=[menu.engineering["values"].get(f"curves[{n}][{k}]") for k in range(5)]
        chosen=n==menu.values["curve"]
        if any(v is None for v in values):missing=True;continue
        points=[(plot.x+plot.width*k/4,plot.bottom-plot.height*v) for k,v in enumerate(values)]
        pygame.draw.lines(surface,palette[n],False,points,4 if chosen else 2)
        if chosen:
            for p in points:pygame.draw.rect(surface,bright,pygame.Rect(p[0]-3,p[1]-3,6,6))
    for n,name in enumerate(menu.engineering["curve_names"]):
        x=rect.x+20+n*(rect.width-30)//3
        surface.blit(font(12,bold=True).render(name,True,palette[n]),(x,rect.bottom-26))
    if missing:surface.blit(font(16,bold=True).render("CALIBRATION POINTS NOT SET",True,fault),(plot.x+20,plot.centery))
    if menu.preview_only:surface.blit(font(12,bold=True).render("SYNTHETIC PREVIEW — NOT VEHICLE CALIBRATION",True,fault),(plot.x,plot.y-22))

def draw_dynamics(surface,state,menu,colors):
    bg,bright,glow,fault=colors;d=state.dynamics;w,h=surface.get_size()
    panel=pygame.Rect(24,60,w-48,h-102);pygame.draw.rect(surface,bg,panel);pygame.draw.rect(surface,glow,panel,2)
    title="DYNAMICS / "+{"controls":"RIDER AIDS","telemetry":"LIVE TELEMETRY","events":"EVENT RECORDER"}[menu.page]
    surface.blit(font(24,bold=True).render(title,True,bright),(panel.x+18,panel.y+14))
    status=("SYNTHETIC PREVIEW / " if menu.preview_only else "")+(d.state if d.online else "VDC DATA STALE")
    text=font(16,bold=True).render(status,True,fault if not d.online or d.faults else glow)
    surface.blit(text,(panel.right-text.get_width()-18,panel.y+18))
    if menu.page=="controls":
        left=pygame.Rect(panel.x+18,panel.y+62,int(panel.width*.38),panel.height-118)
        rowh=max(22,left.height//len(menu.labels))
        for n,(label,value) in enumerate(zip(menu.labels,menu.display_values())):
            y=left.y+n*rowh;selected=n==menu.cursor
            if selected:pygame.draw.rect(surface,(62,42,8),(left.x-4,y-4,left.width,rowh))
            fs=max(12,min(19,rowh-10))
            surface.blit(font(fs,bold=True).render(("> " if selected else "  ")+label,True,bright if selected else glow),(left.x,y))
            val=font(fs,bold=True).render(value,True,fault if value=="OFF" or value=="ENGINEERING TBD" else bright)
            surface.blit(val,(left.right-val.get_width()-10,y))
        graph=pygame.Rect(left.right+24,left.y,panel.right-left.right-42,int(left.height*.66))
        draw_curves(surface,graph,menu,colors,d)
        anim=pygame.Rect(graph.x,graph.bottom+10,graph.width*.45,left.bottom-graph.bottom-10)
        bike(surface,anim,d.pitch,d.slip,bool(d.flags&1),bright,glow)
        x=anim.right+18;y=graph.bottom+18
        tracking="AWC // CORRECTING" if d.flags&2 else "AWC // TRACKING" if d.flags&4 else "CHASSIS // SETTLED"
        for n,line in enumerate((tracking,f"LIFT {d.pitch:.1f} DEG / TARGET {d.wheelie_target:.1f}",f"REAR SLIP {d.slip:+.1f}% / TORQUE {d.permitted:.0f}%",f"WEATHER {WEATHER[d.weather]} / ADVISORY")):
            surface.blit(font(16,bold=True).render(line,True,bright if n==0 else glow),(x,y+n*25))
    elif menu.page=="events":
        for n,line in enumerate(d.history[:12] or ("NO RECORDED INTERVENTIONS",)):
            surface.blit(font(18).render(line,True,bright),(panel.x+28,panel.y+68+n*34))
        surface.blit(font(15).render("3s PRE-TRIGGER + 3s POST / RAW CAN / BOUNDED BACKGROUND WRITER",True,glow),(panel.x+28,panel.bottom-64))
    else:
        actual="INVALID" if not d.online or d.faults&(64|128) else f"{d.throttle_actual:.2f}"
        rows=[("FRONT / REAR SPEED",f"{d.front:.2f} / {d.rear:.2f} m/s"),("ESTIMATED SPEED",f"{d.speed:.2f} m/s"),("SLIP / TARGET",f"{d.slip:.2f} / {d.slip_target:.2f} %"),("LEAN / PITCH",f"{d.lean:+.2f} / {d.pitch:+.2f} DEG"),("PITCH RATE",f"{d.pitch_rate:+.2f} DEG/s"),("TCS / AWC",f"{LEVELS[d.tcs]} / {LEVELS[d.awc]}"),("LIMITS TCS / AWC",f"{d.tcs_limit:.0f} / {d.awc_limit:.0f} %"),("RIDER / PERMITTED",f"{d.rider:.0f} / {d.permitted:.0f} %"),("DBW CMD / ACTUAL",f"{d.throttle_target:.2f} / {actual} DEG"),("BOOST / AIR MARGIN",f"{d.boost_target:.1f} PSI / {d.air_margin:.0f}%"),("SLIP / LIFT CONFIDENCE",f"{d.slip_confidence:.0f} / {d.wheelie_confidence:.0f}%"),("FRONT CONTACT",f"{d.front_contact:.0f}%"),("EVENT",d.event),("FAULT MASK",f"0x{d.faults:08X}"),("WEATHER",WEATHER[d.weather]),("CALIBRATION","VALIDATED" if d.calibrated else "ENGINEERING TBD")]
        for n,(label,value) in enumerate(rows):
            col,row=divmod(n,8);x=panel.x+26+col*panel.width//2;y=panel.y+65+row*(panel.height-118)//8
            surface.blit(font(14,bold=True).render(label,True,glow),(x,y))
            surface.blit(font(20,bold=True).render(value,True,bright),(x,y+19))
    footer="UP/DOWN: ROW | LEFT/RIGHT: CHANGE | SELECT: PAGE | BACK: HOME"
    surface.blit(font(13).render(footer,True,glow),(panel.x+18,panel.bottom-20))
    if menu.page=="controls":
        text=font(12).render(menu.status,True,bright);surface.blit(text,(panel.x+18,panel.bottom-42))
