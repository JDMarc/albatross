import os
os.environ.setdefault("SDL_VIDEODRIVER","dummy")
os.environ.setdefault("SDL_AUDIODRIVER","dummy")
from pathlib import Path
import sys,json,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
from albatross_pi.hud.dynamics_view import DynamicsMenu,draw_dynamics
from albatross_pi.hud.renderer import HUDRenderer
from albatross_pi.dynamics import Dynamics,DynamicsService
import pygame

def check():
    with tempfile.TemporaryDirectory() as tmp:
        menu=DynamicsMenu(Path(tmp)/"settings.json")
        source=Path(tmp)/"engineering.json"
        source.write_text(json.dumps(menu.engineering),encoding="utf-8");menu.engineering_path=source
        menu.cursor=2;menu.select();assert menu.page=="curve_editor"
        menu.edit_cursor=2;before=menu.edit_points[:]
        menu.adjust(1,False);assert menu.edit_points==before
        menu.adjust(1,True);assert menu.edit_points[1]==before[1]+.01
        for _ in range(100):menu.adjust(1)
        assert menu.edit_points[1]==menu.edit_points[2]
        menu.edit_cursor=7;menu.select(False);assert not menu.source_changed
        menu.select(True);assert menu.source_changed and not json.loads(source.read_text())["validated"]
        menu.sync(Dynamics(online=True,calibration_matches=True));assert not menu.configuration_matches
        menu.edit_cursor=0;menu.adjust(-1);assert menu.edit_curve==3 and menu.edit_points==[0,.25,.5,.75,1]
        menu.edit_cursor=2;menu.adjust(1);assert menu.edit_points==[0,.25,.5,.75,1]
        service=DynamicsService();service.ingest(0x220,bytes((1,3,0,2,2,3,0,0)));assert service.value.curve==3
        with patch("albatross_pi.hud.renderer.EvaAlertAudio"):
            hud=HUDRenderer((1280,480),use_display=False,preferences_path=None)
        menu.edit_curve=0;menu._load_curve_draft();menu.edit_cursor=6;menu.select();menu.edit_cursor=2;menu.status="LOCAL BASELINE PREVIEW / NOT APPLIED TO VEHICLE"
        output=os.environ.get("ALBATROSS_CURVE_PREVIEW")
        if output:
            draw_dynamics(hud.screen,hud.state,menu,hud._theme_colors())
            pygame.image.save(hud.screen,output)
        service.close();pygame.quit()
    print("PASS curve editing, stationary gate, bounds, persistence, identity and telemetry")

if __name__=="__main__":check()
