"""Standalone cockpit-style bench display. No road-HUD navigation changes."""
import math
import pygame
from .model import AXES, SCENARIOS

WIDTH, HEIGHT = 1280, 720
THEMES = {'green': (103, 242, 162), 'amber': (255, 194, 90), 'cyan': (95, 217, 246)}
BG = (8, 14, 21)
PANEL = (14, 24, 34)
DIM = (127, 149, 163)
WHITE = (226, 235, 239)
RED = (255, 106, 105)


class BenchView:
    tabs = ('ACTUATORS', 'SIGNAL INSPECTOR', 'FAULTS / EVENTS', 'SESSION')
    controls = ('AXIS', 'FIXTURE', 'PEAK REQUEST', 'DURATION', 'ARM SIMULATION',
                'RUN EXERCISE', 'DISARM SIMULATION', 'EXPORT REPORT')

    def __init__(self, model, theme='green', on_export=None):
        self.model = model
        self.accent = THEMES[theme]
        self.tab = 0
        self.focus = 0
        self.page = 0
        self.confirm = False
        self.on_export = on_export
        self.export_status = 'Reports include provenance; never hardware approval'
        self.fonts = {}
        self.hits = []

    def text(self, surface, text, xy, size=18, color=WHITE, max_width=None):
        font = self.fonts.setdefault(size, pygame.font.SysFont('consolas', size))
        text = str(text)
        if max_width:
            while font.size(text)[0] > max_width and len(text) > 3:
                text = text[:-4]+'...'
        surface.blit(font.render(text, True, color), xy)

    def panel(self, s, rect, title, tag=''):
        pygame.draw.rect(s, PANEL, rect)
        pygame.draw.line(s, self.accent, rect.topleft, (rect.right, rect.top), 2)
        self.text(s, title, (rect.x+16, rect.y+12), 17, self.accent, rect.w-(170 if tag else 32))
        if tag: self.text(s, tag, (rect.right-150, rect.y+12), 14, DIM, 140)

    def change(self, direction):
        m = self.model
        if self.tab == 1:
            self.page = max(0, self.page+direction)
            return
        if self.tab != 0: return
        if self.focus == 0:
            if m.state in ('RUNNING','ARMED'): return
            m.axis = (m.axis+direction) % 3
            m.trace.clear()
        elif self.focus == 1: m.configure(scenario=(m.scenario+direction) % len(SCENARIOS))
        elif self.focus == 2: m.configure(limit=max(0, min(100, m.limit+direction*5)))
        elif self.focus == 3: m.configure(duration=max(1, min(15, m.duration+direction)))

    def select(self):
        m = self.model
        if self.confirm:
            self.confirm = False
            m.arm()
            return
        if self.tab != 0: return
        if self.focus == 4 and m.mode == 'SIM' and m.state != 'RUNNING': self.confirm = True
        elif self.focus == 5: m.run()
        elif self.focus == 6: m.stop()
        elif self.focus == 7: self.export()

    def export(self):
        if self.on_export:
            try:
                path = self.on_export()
                self.export_status = 'Saved: '+str(path)
                self.model.event('Report exported')
            except (OSError,ValueError,TypeError) as exc:
                self.export_status = 'EXPORT FAILED: '+str(exc)
                self.model.event(self.export_status)

    def key(self, key):
        if key in (pygame.K_ESCAPE, pygame.K_SPACE):
            self.confirm = False
            self.model.stop('Operator stop/cancel')
            return
        if self.confirm:
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER): self.select()
            return
        if key == pygame.K_TAB:
            self.tab = (self.tab+1) % len(self.tabs)
            self.page = 0
        elif key in (pygame.K_1,pygame.K_2,pygame.K_3,pygame.K_4): self.tab = key-pygame.K_1
        elif key == pygame.K_UP: self.focus = max(0, self.focus-1)
        elif key == pygame.K_DOWN: self.focus = min(7, self.focus+1)
        elif key == pygame.K_LEFT: self.change(-1)
        elif key == pygame.K_RIGHT: self.change(1)
        elif key in (pygame.K_RETURN,pygame.K_KP_ENTER): self.select()
        elif key == pygame.K_e: self.export()

    def click(self, pos):
        if self.confirm: return  # confirmation requires a deliberate Enter
        for rect, kind, index in reversed(self.hits):
            if not rect.collidepoint(pos): continue
            if kind == 'tab': self.tab = index; self.page = 0
            elif kind == 'control':
                if self.focus == index and index >= 4: self.select()
                else: self.focus = index
            elif kind == 'minus': self.focus = index; self.change(-1)
            elif kind == 'plus': self.focus = index; self.change(1)
            return

    def render(self, surface):
        m = self.model
        surface.fill(BG)
        self.hits = []
        self.text(surface, 'ALBATROSS', (24, 16), 30, self.accent)
        self.text(surface, '/ BENCH OPERATIONS', (213, 23), 20)
        self.text(surface, 'NO HARDWARE COMMAND TRANSMITTER', (760, 24), 20, self.accent)
        badge = {'SIM':'SIMULATED PLANT / NO CAN CONNECTION',
                 'LIVE':'LIVE CAN OBSERVER / APPLICATION TX DISABLED',
                 'REPLAY':'RECORDED CAN / NO CAN CONNECTION'}[m.mode]
        pygame.draw.rect(surface, self.accent, (24, 62, 1232, 32))
        self.text(surface, badge, (36, 68), 18, BG)
        for n, label in enumerate(self.tabs):
            rect = pygame.Rect(24+n*310, 109, 302, 36)
            pygame.draw.rect(surface, PANEL if n != self.tab else self.accent, rect)
            self.text(surface, f'0{n+1}  {label}', (rect.x+12, rect.y+9), 17, BG if n == self.tab else DIM)
            self.hits.append((rect,'tab',n))
        if self.tab == 0: self._actuators(surface)
        elif self.tab == 1: self._signals(surface)
        elif self.tab == 2: self._faults(surface)
        else: self._session(surface)
        status = m.transport_error or m.reason
        self.text(surface, status, (24, 648), 17, RED if m.transport_error else self.accent, 1220)
        pygame.draw.line(surface, DIM, (24,679), (1256,679))
        self.text(surface, 'TAB / 1-4: PAGE   ARROWS: NAV / EDIT   ENTER: SELECT   E: EXPORT', (24,692), 15, DIM)
        self.text(surface, 'SPACE: SIM STOP ONLY' if m.mode == 'SIM' else 'HARDWARE STOP: USE PHYSICAL KILL', (912,692), 15, RED)
        if self.confirm:
            rect = pygame.Rect(265,225,750,235)
            pygame.draw.rect(surface, BG, rect)
            pygame.draw.rect(surface, self.accent, rect, 2)
            self.text(surface, 'ARM OFFLINE SIMULATION?', (295,249), 27, self.accent)
            for n,line in enumerate(('Only the illustrative actuator model will move.',
                'No road calibration changes. No CAN frames transmitted.',
                'Arming expires in 10 seconds. RUN is a separate action.',
                'ENTER: CONFIRM                         ESC: CANCEL')):
                self.text(surface,line,(295,302+n*35),18)

    def _actuators(self, s):
        m = self.model
        self.panel(s,pygame.Rect(24,164,340,465),'EXERCISE CONSOLE',m.state)
        values = (AXES[m.axis],SCENARIOS[m.scenario],f'{m.limit:.0f}%  [SIM]',f'{m.duration:.0f}s  [SIM]',
                  'CONFIRM TO ARM','BOUNDED RISE / RETURN','NO PHYSICAL STOP','JSON + TRACE CSV')
        for n,(label,value) in enumerate(zip(self.controls,values)):
            rect = pygame.Rect(36,208+n*48,316,43)
            active = n == self.focus
            if active: pygame.draw.rect(s,(28,48,58),rect)
            if active: pygame.draw.line(s,self.accent,rect.topleft,rect.bottomleft,3)
            blocked = m.mode != 'SIM' and n not in (0,7)
            self.text(s,label,(48,rect.y+3),13,DIM)
            self.text(s,'UNAVAILABLE' if blocked else value,(48,rect.y+21),16,DIM if blocked else WHITE,258)
            self.hits.append((rect,'control',n))
            if n < 4:
                self.text(s,'< >',(310,rect.y+20),15,self.accent)
                self.hits.extend(((pygame.Rect(303,rect.y,23,43),'minus',n),
                                  (pygame.Rect(327,rect.y,23,43),'plus',n)))
        axis = AXES[m.axis]
        for n,(suffix,title) in enumerate((('target','REQUESTED'),('actual','SIMULATED' if m.mode == 'SIM' else 'REPORTED'),('current','CURRENT'))):
            rect = pygame.Rect(384+n*296,164,280,110)
            self.panel(s,rect,title)
            key = axis+' '+suffix
            value = m.get(key)
            r = m.readings.get(key)
            text = '--' if value is None else f'{value:.2f}'
            self.text(s,text,(rect.x+16,rect.y+39),32,self.accent if value is not None else DIM)
            self.text(s,r.unit if r else 'NO DATA',(rect.right-93,rect.y+51),16,DIM)
            self.text(s,m.quality(key)+' / '+m.mode,(rect.x+16,rect.y+85),13,DIM)
        self.panel(s,pygame.Rect(384,292,872,244),axis+' / TARGET AND RESPONSE','60s MAX TRACE')
        graph = pygame.Rect(427,338,796,160)
        pygame.draw.rect(s,(9,18,25),graph)
        for k in range(5):
            y = graph.y+k*graph.h/4
            pygame.draw.line(s,(34,49,58),(graph.x,y),(graph.right,y))
        points = list(m.trace)
        finite = [v for row in points for v in row[1:3] if v is not None and math.isfinite(v)]
        maximum = max(100,max(finite,default=0))
        span = max(10, min(60,m.time))
        for column,color in ((1,self.accent),(2,WHITE)):
            previous = None
            for row in points:
                x = graph.right-(m.time-row[0])/span*graph.w
                value = row[column]
                if value is None or x < graph.x:
                    previous = None
                    continue
                point = (int(x),int(graph.bottom-max(0,min(maximum,value))/maximum*graph.h))
                if previous: pygame.draw.line(s,color,previous,point,2)
                previous = point
        self.text(s,'TARGET',(430,510),13,self.accent)
        self.text(s,'OBSERVED',(535,510),13,WHITE)
        self.text(s,'GAPS = MISSING / INVALID / STALE',(770,510),13,DIM)
        self.panel(s,pygame.Rect(384,554,872,75),'HARDWARE AUTHORITY: UNAVAILABLE')
        self.text(s,'SIM is an illustrative plant, not the production VDC or actuator calibration.',(400,586),16,DIM,840)

    def _signals(self,s):
        m = self.model
        self.panel(s,pygame.Rect(24,164,1232,465),'SIGNAL INSPECTOR / EACH VALUE HAS ITS OWN AGE')
        rows = sorted(m.readings.items())
        pages = max(1,(len(rows)+10)//11)
        self.page = min(self.page,pages-1)
        for x,label in ((40,'SIGNAL'),(345,'VALUE'),(510,'QUALITY'),(650,'AGE'),(775,'PROVENANCE')):
            self.text(s,label,(x,210),16,self.accent)
        for n,(key,r) in enumerate(rows[self.page*11:self.page*11+11]):
            y = 244+n*30
            value = m.get(key)
            self.text(s,key,(40,y),16,max_width=285)
            self.text(s,'--' if value is None else f'{value:.3f} {r.unit}',(345,y),16,max_width=155)
            self.text(s,m.quality(key),(510,y),16,self.accent if value is not None else RED)
            self.text(s,f'{m.time-r.at:.2f}s',(650,y),16,DIM)
            self.text(s,r.source,(775,y),16,DIM,450)
        if not rows:self.text(s,'Waiting for supported telemetry. No values are fabricated.',(40,260),20,DIM)
        self.text(s,f'PAGE {self.page+1}/{pages}  LEFT / RIGHT TO PAGE',(40,598),15,DIM)

    def _faults(self,s):
        m = self.model
        self.panel(s,pygame.Rect(24,164,530,465),'REPORTED FAULTS / NOT A HARDWARE SAFETY CERTIFICATE')
        faults = ([m.transport_error] if m.transport_error else [])+m.fault_names
        if m.mode != 'SIM' and m.get('VDC faults') is not None:
            faults += [f'VDC FAULT MASK: 0x{int(m.get("VDC faults")):08X}']
        if not faults: faults = ['No reported fault names.', 'Absence of telemetry is not proof of health.']
        for n,line in enumerate(faults[:13]): self.text(s,line,(40,214+n*29),16,RED if n == 0 else WHITE,498)
        self.panel(s,pygame.Rect(574,164,682,465),'SESSION EVENTS / NEWEST FIRST')
        for n,(at,text) in enumerate(list(m.events)[:13]):
            self.text(s,f'{at:7.2f}  {text}',(590,214+n*29),16,DIM,645)

    def _session(self,s):
        m = self.model
        self.panel(s,pygame.Rect(24,164,1232,465),'SESSION / EXPORT AND COMMISSIONING BOUNDARY')
        lines = [f'SOURCE: {m.mode}      RECEIVED: {m.frames}      REJECTED: {m.rejected}',
                 'Hardware transmit: absent. No calibration upload or road-enable path.',
                 'LIVE: observe existing publishers. DBWX2 does not get polled by this tool.',
                 'REPLAY: recorded observations only; timestamps control signal freshness.',
                 'SIM: bounded illustrative plant; results are NOT hardware acceptance tests.',
                 'NEXT HARDWARE WORK: verified wiring, independent kill, actuator calibration,',
                 'and a dedicated controller-side bench protocol with local physical authorization.',
                 '',self.export_status]
        for n,line in enumerate(lines): self.text(s,line,(40,215+n*34),18,self.accent if n == 0 else DIM,1190)
        self.text(s,f'Synthetic exercises recorded: {m.result_count}  /  PRESS E TO EXPORT',(40,583),18,self.accent)
