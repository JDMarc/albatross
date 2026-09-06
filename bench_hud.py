"""Standalone Albatross bench HUD: simulation, receive-only CAN, or raw-log replay.

No hardware command transmission or calibration writes are implemented.
"""
import argparse
import os
from pathlib import Path
import time


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    source = p.add_mutually_exclusive_group()
    source.add_argument('--live', action='store_true', help='Receive-only CAN observations; never actuator commands')
    source.add_argument('--replay', type=Path, help='Replay raw CAN JSONL offline')
    p.add_argument('--interface', default='socketcan')
    p.add_argument('--channel', default='can0')
    p.add_argument('--bitrate', type=int, default=500000)
    p.add_argument('--tty-baudrate', type=int)
    p.add_argument('--native-v092', action='store_true', help='Decode observed DBWX2 0.92 read exchanges ONLY after firmware identity verification')
    p.add_argument('--local-node', type=int, default=9)
    p.add_argument('--dbwx2-node', type=int, default=10)
    p.add_argument('--theme', choices=('green','amber','cyan'), default='green')
    p.add_argument('--controller', type=int, help='Optional joystick index; hat navigates, button 0 selects, button 1 cancels')
    p.add_argument('--size', default='1280x720')
    p.add_argument('--logs', type=Path, default=Path('logs/bench'))
    p.add_argument('--screenshot', type=Path, help='Save a SIM preview and exit; no CAN connection')
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    if not (0 <= args.local_node <= 14 and 0 <= args.dbwx2_node <= 14 and args.local_node != args.dbwx2_node):
        parser().error('Native node IDs must be distinct and within 0..14')
    if args.screenshot and (args.live or args.replay):
        parser().error('--screenshot is an offline SIM preview only')
    try:
        width,height = map(int,args.size.lower().split('x'))
        if not (640 <= width <= 3840 and 360 <= height <= 2160): raise ValueError()
    except ValueError: parser().error('--size must be WIDTHxHEIGHT, minimum 640x360, maximum 3840x2160')
    if args.screenshot:
        os.environ.setdefault('SDL_VIDEODRIVER','dummy')
    os.environ.setdefault('SDL_AUDIODRIVER','dummy')
    import pygame
    from albatross_pi.bench.model import BenchModel
    from albatross_pi.bench.decoder import BenchDecoder
    from albatross_pi.bench.io import ReceiveOnlyCAN, Journal, Replay, export_report
    from albatross_pi.bench.view import BenchView, WIDTH, HEIGHT
    mode = 'LIVE' if args.live else 'REPLAY' if args.replay else 'SIM'
    model = BenchModel(mode)
    decoder = BenchDecoder(model,native_v092=args.native_v092,local_node=args.local_node,dbwx2_node=args.dbwx2_node)
    transport = None
    journal = None
    pygame.init()
    try:
        joystick = None
        if args.controller is not None:
            if not 0 <= args.controller < pygame.joystick.get_count():
                raise ValueError('Requested USB controller is not connected')
            joystick = pygame.joystick.Joystick(args.controller)
            joystick.init()
        screen = pygame.display.set_mode((width,height),pygame.RESIZABLE)
        pygame.display.set_caption('ALBATROSS / BENCH ONLY / '+mode+' / NO HARDWARE TX')
        canvas = pygame.Surface((WIDTH,HEIGHT))
        replay = Replay(args.replay) if args.replay else None
        if args.live:
            try:
                transport = ReceiveOnlyCAN(args.interface,args.channel,args.bitrate,tty_baudrate=args.tty_baudrate)
            except Exception as exc:
                model.transport_error = 'CAN OPEN FAILED / '+str(exc)
                # No silent fallback to synthetic healthy data.
        if not args.screenshot:
            try: journal = Journal(args.logs,mode)
            except OSError as exc: model.transport_error = 'RECORDING OPEN FAILED / '+str(exc)
        view = BenchView(model,args.theme,on_export=lambda:export_report(args.logs,model,journal))
        if args.screenshot:
            model.arm();model.run()
            for n in range(1,51): model.tick(n*.05)
            view.render(canvas)
            args.screenshot.parent.mkdir(parents=True,exist_ok=True)
            pygame.image.save(canvas,str(args.screenshot))
            return 0
        start = time.monotonic()
        last = 0.0
        replay_time = 0.0
        replay_paused = False
        running = True
        logged_events = 0
        logged_results = 0
        clock = pygame.time.Clock()
        while running:
            now = time.monotonic()-start
            for event in pygame.event.get():
                if event.type == pygame.QUIT: running = False
                elif event.type == pygame.WINDOWFOCUSLOST:
                    view.confirm = False
                    if mode == 'SIM': model.stop('Window focus lost')
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_q: running = False
                    elif event.key == pygame.K_p and replay:
                        replay_paused = not replay_paused
                    else: view.key(event.key)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    ratio = min(screen.get_width()/WIDTH,screen.get_height()/HEIGHT)
                    offset = ((screen.get_width()-WIDTH*ratio)/2,(screen.get_height()-HEIGHT*ratio)/2)
                    view.click(((event.pos[0]-offset[0])/ratio,(event.pos[1]-offset[1])/ratio))
                elif event.type == pygame.JOYBUTTONDOWN and joystick and event.instance_id == joystick.get_instance_id():
                    if event.button == 0: view.key(pygame.K_RETURN)
                    elif event.button == 1: view.key(pygame.K_ESCAPE)
                    elif event.button == 4: view.key(pygame.K_TAB)
                elif event.type == pygame.JOYHATMOTION and joystick and event.instance_id == joystick.get_instance_id():
                    x,y = event.value
                    if x: view.key(pygame.K_RIGHT if x > 0 else pygame.K_LEFT)
                    if y: view.key(pygame.K_UP if y > 0 else pygame.K_DOWN)
                elif event.type == pygame.JOYDEVICEREMOVED and mode == 'SIM': model.stop('Controller disconnected')
            if replay:
                if not replay_paused: replay_time += now-last
                # Preserve packet timestamps, not GUI processing time. Backlog
                # is processed in bounded batches before advancing the clock.
                for at,row in replay.due(replay_time):
                    model.time = at
                    decoder.ingest(row['frame_id'],row['data'],**{k:v for k,v in row.items() if k not in ('frame_id','data')})
                next_time = replay.rows[replay.cursor][0] if not replay.finished else float('inf')
                model.tick(min(replay_time,next_time))
                decoder.refresh()
                model.reason = 'REPLAY '+('PAUSED' if replay_paused else 'END / AGING DATA' if replay.finished else 'PLAYING')+' / P: PAUSE / no hardware output'
            else:
                model.tick(now)
                if transport:
                    for row in transport.poll():
                        decoder.ingest(row['frame_id'],row['data'],**{k:v for k,v in row.items() if k not in ('frame_id','data')})
                        if journal: journal.add(dict(time_s=now,**{**row,'data':row['data'].hex()}))
                    if transport.error: model.transport_error = transport.error
                if mode == 'LIVE': decoder.refresh()
            if journal:
                if model.event_count != logged_events:
                    count = model.event_count-logged_events
                    for at, message in reversed(list(model.events)[:count]):
                        journal.add(dict(event='BENCH_EVENT', time_s=at, message=message))
                    logged_events = model.event_count
                if model.result_count != logged_results:
                    for result in model.results:
                        if result['number'] > logged_results:
                            journal.add(dict(event='SIM_RESULT', **result))
                    logged_results = model.result_count
                if mode == 'SIM': journal.add(dict(event='SIM_SAMPLE',time_s=model.time,state=model.state,
                    axis=model.axis,scenario=model.scenario,trace=list(model.trace[-1]),hardware_acceptance=False))
                if journal.failed: model.transport_error = 'RECORDING FAILED / DATA MAY BE INCOMPLETE'
            view.render(canvas)
            ratio = min(screen.get_width()/WIDTH,screen.get_height()/HEIGHT)
            scaled = pygame.transform.smoothscale(canvas,(int(WIDTH*ratio),int(HEIGHT*ratio)))
            screen.fill((0,0,0))
            screen.blit(scaled,((screen.get_width()-scaled.get_width())//2,(screen.get_height()-scaled.get_height())//2))
            pygame.display.flip()
            last = now
            clock.tick(20)
        if mode == 'SIM': model.stop('Application exit')
        if journal:
            journal.add(dict(event='FINAL_REPORT', report=model.report()))
            journal.close()
        export_report(args.logs,model,journal)
        return 0
    except (OSError,ValueError) as exc:
        print('Bench startup/session failed:',exc)
        return 1
    finally:
        if transport: transport.close()
        if journal: journal.close()
        pygame.quit()


if __name__ == '__main__':
    raise SystemExit(main())
