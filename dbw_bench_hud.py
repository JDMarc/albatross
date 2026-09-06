"""Powered DBWX2 bench HUD. Requires the isolated USB bench Teensy firmware."""
import argparse
from collections import deque
from pathlib import Path
import time


def draw(surface, pygame, status, fresh, target, confirm, error, trace):
    from albatross_pi.bench.view import BenchView
    from albatross_pi.bench.model import BenchModel
    from albatross_pi.bench.powered import STATES,REASONS
    if not hasattr(draw,'view'): draw.view=BenchView(BenchModel(),'amber')
    text=draw.view.text
    surface.fill((8,14,21)); accent=(255,194,90); dim=(127,149,163)
    text(surface,'ALBATROSS / POWERED DBW BENCH',(24,20),28,accent)
    text(surface,'ISOLATED FIXTURE ONLY / PHYSICAL MOTION POSSIBLE',(24,65),21,(255,106,105))
    text(surface,'DBWX2 CHANNEL 1 / MT-07 ASSEMBLY',(24,105),20)
    state=STATES[status['state']] if fresh else 'NO FRESH BOARD ACKNOWLEDGEMENT'
    text(surface,state,(24,150),26,accent)
    text(surface,REASONS[status['reason']] if fresh else 'USE INDEPENDENT KILL IF HARDWARE IS ENERGIZED',(24,193),18)
    for n,(label,value) in enumerate((('REQUEST',f'{target/10:.1f}%'),
        ('BOARD COMMAND',f'{status.get("target",0)/10:.1f}%' if fresh else '--'),
        ('TPS FEEDBACK',f'{status["actual"]/10:.1f}%' if fresh and status.get('good') else '--'))):
        x=24+n*410
        pygame.draw.rect(surface,(14,24,34),(x,238,395,108))
        text(surface,label,(x+15,250),17,accent);text(surface,value,(x+15,283),30)
    text(surface,'PERMIT: '+('ON' if status.get('permit') else 'OFF') if fresh else 'PERMIT: UNKNOWN',(24,370),20,accent)
    text(surface,'KEY / DEADMAN: '+str(status.get('key','?'))+' / '+str(status.get('deadman','?')),(420,370),20)
    text(surface,'CURRENT: '+(f'{status["current_ma"]/1000:.2f} A' if fresh and status.get('good') else '--'),(870,370),20)
    graph=pygame.Rect(24,412,1232,130);pygame.draw.rect(surface,(14,24,34),graph)
    for column,color in ((1,accent),(2,(226,235,239))):
        previous=None
        for n,row in enumerate(trace):
            value=row[column]
            if value is None: previous=None;continue
            point=(graph.right-(len(trace)-1-n)*graph.w/500,graph.bottom-max(0,min(1000,value))*graph.h/1000)
            if previous:pygame.draw.line(surface,color,previous,point,2)
            previous=point
    text(surface,'COMMAND / TPS TRACE   0-100% TRAVEL   LAST 10s AT 50 Hz',(24,550),14,dim)
    text(surface,'AIR SHOT: 4 BRANCHES + NC MASTER PROVISIONED / OUTPUTS NOT IMPLEMENTED',(24,582),17,dim)
    text(surface,error or 'Release physical deadman to arm; then hold physical deadman AND H to move.',(24,619),17,(255,106,105) if error else accent,1220)
    text(surface,'A: ARM + ENTER CONFIRM   UP/DOWN: TARGET (RELEASE H FIRST)   H: HOLD TO RUN',(24,655),17)
    text(surface,'SPACE / ESC: REQUEST STOP   Q: EXIT   HARD KILL IS INDEPENDENT',(24,688),16,dim)
    if confirm:
        pygame.draw.rect(surface,(8,14,21),(225,230,830,210))
        pygame.draw.rect(surface,accent,(225,230,830,210),2)
        text(surface,'ARM REAL HARDWARE ON ISOLATED BENCH?',(250,255),24,accent)
        text(surface,'Clear hands/tools. Verify independent kill and guarded fixture.',(250,309),18)
        text(surface,'ENTER confirms arming only. Motion requires BOTH hold controls.',(250,349),18)
        text(surface,'ESC cancels. This does not change road calibration.',(250,392),18)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True,help='USB serial port of dedicated BENCH Teensy, not DBWX2')
    p.add_argument('--profile',type=int,required=True,help='Expected nonzero compiled fixture revision')
    p.add_argument('--logs',type=Path,default=Path('logs/bench'))
    args=p.parse_args(argv)
    import pygame
    from albatross_pi.bench.powered import PoweredLink
    from albatross_pi.bench.io import Journal
    link=None;journal=None;pygame.init()
    try:
        journal=Journal(args.logs,'POWERED_DBW',hardware_tx=True)
        journal.add(dict(event='FIXTURE',profile=args.profile,port=args.port,
            hardware_tx=True,warning='Real actuator requests; local config hashes do not attest board firmware'))
        link=PoweredLink(args.port,args.profile)
        screen=pygame.display.set_mode((1280,720));pygame.display.set_caption('ISOLATED POWERED DBW BENCH')
        target=0;confirm=False;running=True;held=False;trace=deque(maxlen=500);clock=pygame.time.Clock()
        while running:
            for event in pygame.event.get():
                if event.type==pygame.QUIT:running=False
                elif event.type==pygame.WINDOWFOCUSLOST:held=False;confirm=False;link.stop()
                elif event.type==pygame.KEYUP and event.key==pygame.K_h:held=False;link.stop()
                elif event.type==pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE,pygame.K_SPACE):held=False;confirm=False;link.stop()
                    elif event.key==pygame.K_q:running=False
                    elif event.key==pygame.K_a and not held:confirm=True
                    elif confirm and event.key==pygame.K_RETURN:
                        confirm=False;link.arm()
                    elif event.key==pygame.K_h and not confirm:held=True
                    elif not held and not confirm and event.key in (pygame.K_UP,pygame.K_DOWN):
                        target=max(0,min(link.status.get('max',0),target+(10 if event.key==pygame.K_UP else -10)))
            link.poll()
            if not running:link.stop();held=False
            if journal.failed:link.error='RECORDING FAILED';link.stop();held=False
            link.drive(held and pygame.key.get_focused() and not confirm,target)
            for row in link.rows:journal.add(row)
            link.rows.clear()
            s=link.status;fresh=link.fresh()
            trace.append((time.monotonic(),s.get('target') if fresh else None,s.get('actual') if fresh and s.get('good') else None))
            error=link.error
            if fresh and s.get('profile')!=args.profile:error='FIXTURE REVISION MISMATCH / REQUESTS BLOCKED'
            draw(screen,pygame,s,fresh,target,confirm,error,trace)
            pygame.display.flip();clock.tick(50)
        return 0
    except Exception as exc:
        print('Powered bench stopped:',exc);return 1
    finally:
        try:
            if link:
                link.close()
                if journal:
                    for row in link.rows:journal.add(row)
        finally:
            if journal:journal.close()
            pygame.quit()


if __name__=='__main__':raise SystemExit(main())
