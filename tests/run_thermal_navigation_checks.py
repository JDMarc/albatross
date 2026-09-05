"""Thermal entry, map reachability and layout checks at supported sizes."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
from dataclasses import replace
import pygame
from albatross_pi.hud.renderer import HUDRenderer
from albatross_pi.hud.widgets.thermal_summary import ThermalSummary
from albatross_pi.hud.widgets.temps_grid import TempsGrid
from albatross_pi.hud.thermal_views import MAP_KEYS
from albatross_pi.hud.thermal_architecture import NODES, FlowAnimation
from albatross_pi.thermal.simulation import ThermalSimulator


def check():
    from albatross_pi.state.snapshot import EngineState
    animation=FlowAnimation()
    engine=EngineState(boost_psi=5,boost_left_psi=2,boost_right_psi=18)
    for tick in range(0,2001,20):animation.advance(engine,tick)
    assert animation.speeds["RIGHT"]>animation.speeds["LEFT"]>0
    assert 0<=animation.rotors["LEFT"]<360 and animation.flow>0
    assert 0<animation.raster<400
    previous=animation.speeds["RIGHT"]
    animation.advance(EngineState(boost_psi=0),2020)
    assert 0<animation.speeds["RIGHT"]<previous
    assert FlowAnimation.boost(EngineState(boost_psi=8),"LEFT")==8
    assert FlowAnimation.boost(EngineState(boost_psi=float("nan")),"LEFT")==0
    assert FlowAnimation.boost(EngineState(boost_psi=-5),"LEFT")==0
    assert FlowAnimation.boost(EngineState(boost_psi=100),"LEFT")==40
    assert FlowAnimation.boost(EngineState(boost_psi=8,boost_left_psi=0),"LEFT")==0
    assert FlowAnimation.boost(EngineState(boost_psi=8,boost_left_psi=float("inf")),"LEFT")==8
    slow,fast=FlowAnimation(),FlowAnimation()
    for tick in range(0,2001,100):slow.advance(engine,tick)
    for tick in range(0,2001,10):fast.advance(engine,tick)
    assert abs(slow.rotors["RIGHT"]-fast.rotors["RIGHT"])<1e-8
    assert abs(slow.speeds["RIGHT"]-fast.speeds["RIGHT"])<1e-8
    assert abs(slow.raster-fast.raster)<1e-8
    # Wrapped arrow phase and long page absences must not cause large jumps.
    slow.flow=slow.ARROW_SPACING-1
    slow.raster=399
    slow.advance(engine,100000)
    assert abs(slow.flow-2.4)<1e-8
    assert abs(slow.raster-3.2)<1e-8
    phase=slow.rotors["RIGHT"]
    slow.advance(engine,100000)
    assert slow.rotors["RIGHT"]==phase
    for size in ((1280,480),(1920,720)):
        with patch("albatross_pi.hud.renderer.EvaAlertAudio"):
            hud=HUDRenderer(size,use_display=False,preferences_path=None)
        hud._post_complete=True; hud._navigation.online_enabled=False
        hud._auto_dim_enabled=False; hud._brightness_index=len(hud._brightness_levels)-1
        hud._dynamics_menu.preview_only=True
        simulator=ThermalSimulator(); thermal=simulator.step(40)
        for index, mode in enumerate(hud._modes):
            hud._mode_index=index; hud._mode_layout_state={}; hud._create_widgets()
            state=replace(hud.state,thermal=thermal,environment=replace(hud.state.environment,mode=mode))
            hud._active_menu="home"; hud._set_home_focus_target("TEMPS")
            assert any(isinstance(w,ThermalSummary if index<2 else TempsGrid) for w in hud.widgets)
            with patch.object(hud._thermal_views,"draw_focus_submenu") as menu:
                hud.capture_frame(state); menu.assert_not_called()
                hud._handle_select(); hud.capture_frame(state); menu.assert_called_once()
            assert hud._active_menu=="thermal_menu"
            hud._thermal_views.menu_cursor=1; hud._handle_select()
            hud.capture_frame(state)
            views=hud._thermal_views
            # Both map modes redraw motion without changing selection geometry.
            if index==0:
                colors=((4,12,17),(255,198,64),(148,166,167),(255,80,40))
                for page in ("thermal_abs","thermal_dev"):
                    views.animation=FlowAnimation()
                    first=pygame.Surface(size); second=pygame.Surface(size)
                    with patch("pygame.time.get_ticks",return_value=0):views.draw(first,state,page,colors)
                    geometry=dict(views.map_rects)
                    with patch("pygame.time.get_ticks",return_value=100):views.draw(second,state,page,colors)
                    assert pygame.image.tostring(first,"RGB")!=pygame.image.tostring(second,"RGB")
                    assert views.map_rects==geometry
            assert set(views.map_rects)==set(MAP_KEYS)
            rectangles=list(views.map_rects.values())
            assert all(hud.screen.get_rect().contains(r) for r in rectangles)
            assert not any(a.colliderect(b) for n,a in enumerate(rectangles) for b in rectangles[n+1:])
            reached={"AMBIENT_AIR"}; queue=list(reached)
            while queue:
                key=queue.pop()
                for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                    views.map_selected=key; views.map_move(dx,dy)
                    if views.map_selected not in reached:
                        reached.add(views.map_selected); queue.append(views.map_selected)
            assert reached==set(MAP_KEYS)
            views.map_selected="COMP_IN_LEFT"; hud._handle_down()
            assert views.map_selected=="COMP_OUT_LEFT" and hud._active_menu=="thermal_abs"
            previous=views.map_selected
            hud._handle_dpad_right(); assert NODES[views.map_selected][0]>NODES[previous][0]
            previous=views.map_selected
            hud._handle_dpad_right(); assert NODES[views.map_selected][0]>NODES[previous][0]
            hud._handle_back(); assert hud._active_menu=="thermal_menu"
            hud._handle_back(); assert hud._active_menu=="home" and hud._home_focus_target()=="TEMPS"
            output=os.environ.get("ALBATROSS_THERMAL_NAV_PREVIEWS")
            if output and size==(1280,480) and index in (0,2):
                folder=Path(output); folder.mkdir(parents=True,exist_ok=True)
                pygame.image.save(hud.capture_frame(state),str(folder/f"thermal-entry-{mode.lower()}.png"))
                if index==2:
                    hud._handle_select(); pygame.image.save(hud.capture_frame(state),str(folder/"thermal-page-menu.png"))
                    hud._thermal_views.menu_cursor=1; hud._handle_select()
                    views.map_selected="HEAD_METAL_RIGHT"
                    pygame.image.save(hud.capture_frame(state),str(folder/"thermal-map-navigation.png"))
                    hud._active_menu="thermal_dev"
                    assert views.map_selected=="HEAD_METAL_RIGHT"
                    pygame.image.save(hud.capture_frame(state),str(folder/"thermal-architecture-dev.png"))
    pygame.quit()
    print("PASS thermal entry, all modes, map reachability, geometry and boost-driven animation")


if __name__=="__main__": check()
