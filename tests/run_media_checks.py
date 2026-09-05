"""Media transport, scrolling device picker and theme/layout regression."""
import os
os.environ.setdefault("SDL_VIDEODRIVER","dummy")
os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import sys
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pygame
from albatross_pi.hud.renderer import HUDRenderer
from albatross_pi.hud.media_view import timestamp

def check():
    assert timestamp(125)=="02:05" and timestamp(float('nan'))=="--:--"
    output=os.environ.get("ALBATROSS_MEDIA_PREVIEWS")
    if output:Path(output).mkdir(parents=True,exist_ok=True)
    for size in ((1280,480),(1920,720)):
        with patch("albatross_pi.hud.renderer.EvaAlertAudio"),patch("albatross_pi.hud.renderer.PiNetworkManager"):
            hud=HUDRenderer(size,use_display=False,preferences_path=None)
        hud._navigation.online_enabled=False
        hud._post_complete=True;hud._post_fault_active=False
        hud._auto_dim_enabled=False;hud._brightness_index=len(hud._brightness_levels)-1
        hud._active_menu="media";hud._media_callback=Mock()
        devices=tuple((f"00:11:22:33:44:{i:02d}",f"Audio device {i+1}") for i in range(8))
        hud.update_phone_status(artist="KENNY LOGGINS",track="DANGER ZONE",position_s=83,length_s=215,devices=devices)
        for i,command in enumerate(("prev","play_pause","next")):
            hud._media_index=i;hud._activate_media_action()
            hud._media_callback.assert_called_with(command,1)
        hud._media_index=3;hud._activate_media_action()
        for _ in range(7):hud._handle_down()
        assert hud._media_device_cursor==7
        hud._activate_media_action();hud._media_callback.assert_called_with("connect:"+devices[7][0],1)
        assert not hud._media_device_menu_open
        for theme_index,theme in enumerate(hud._themes):
            hud._theme_index=theme_index
            for picker in (False,True):
                hud._media_device_menu_open=picker
                frame=hud.capture_frame()
                if output and size==(1280,480) and theme_index==0:
                    pygame.image.save(frame,str(Path(output)/("media-devices.png" if picker else "media-player.png")))
        hud._available_devices=();hud._media_device_menu_open=True
        index=hud._media_index;hud._handle_down();hud._activate_media_action()
        assert hud._media_index==index and hud._media_device_menu_open
        hud.capture_frame()
        hud._media_device_menu_open=False;hud._media_callback=None;hud._media_index=1
        hud._activate_media_action();assert "UNAVAILABLE" in hud._media_feedback
        hud.update_phone_status(artist="A"*300,track="T"*300,position_s=float('inf'),length_s=float('nan'),devices=())
        hud.capture_frame()
    pygame.quit()
    print("PASS media requests, device scrolling/empty lists, long metadata, unknown duration and all themes/sizes")

if __name__=="__main__":check()
