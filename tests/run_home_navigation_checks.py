"""Exercise home D-pad routes against the panels' actual on-screen placement."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pygame
from albatross_pi.hud.renderer import HUDRenderer


def check():
    for size in ((1280, 480), (1920, 720)):
        with patch("albatross_pi.hud.renderer.EvaAlertAudio"), \
                patch("albatross_pi.hud.renderer.NavigationManager"), \
                patch("albatross_pi.hud.renderer.PiNetworkManager"):
            hud = HUDRenderer(size, use_display=False, preferences_path=None)
        hud._save_preferences = Mock()
        hud._air_mode_callback = Mock()
        hud._mode_callback = Mock()
        hud._visible_faults = ()

        # Header traversal retains the physical mode / settings / media order.
        header = ["MODE:0", "MODE:1", "MODE:2", "MODE:3", "MODE:4", "SETTINGS", "MEDIA"]
        hud._set_home_focus_target(header[0])
        for expected in header[1:] + header[:1]:
            hud._handle_dpad_right()
            assert hud._home_focus_target() == expected
        for expected in list(reversed(header[1:])) + header[:1]:
            hud._handle_dpad_left()
            assert hud._home_focus_target() == expected
        hud._mode_callback.assert_not_called()

        for index, mode in enumerate(hud._modes):
            hud._mode_index = index
            hud._mode_layout_state = {}
            hud._create_widgets()
            hud._active_menu = "home"
            hud._home_bottom_target = "AIR"
            hud._set_home_focus_target("SETTINGS")
            hud._handle_up()
            assert hud._home_focus_target() == "SETTINGS"

            route = ["NAV", "DYNAMICS", "AIR"] if index < 2 else ["NAV", "TEMPS", "DYNAMICS", "AIR"]
            panels = {type(widget).__name__: widget.rect for widget in hud.widgets if hasattr(widget, "rect")}
            panel_types = {"NAV": "NavigationPanel", "TEMPS": "TempsGrid", "DYNAMICS": "TractionPanel", "AIR": "AirShotPanel"}
            previous_y = -1
            for target in route:
                hud._handle_down()
                assert hud._home_focus_target() == target, (size, mode, target)
                rectangle = panels[panel_types[target]]
                assert rectangle.centery > previous_y, (mode, target)
                previous_y = rectangle.centery
                assert hud._active_menu == "home"
            for _ in range(5):
                hud._handle_down()
                assert hud._home_focus_target() == "AIR", "Bottom must not wrap to NAV or the header"
            for target in list(reversed(route[:-1])) + ["SETTINGS"]:
                hud._handle_up()
                assert hud._home_focus_target() == target

            if index < 2:
                # TEMP is physically left of AIR and keeps its column after an up/down trip.
                assert panels["ThermalSummary"].right < panels["AirShotPanel"].left
                assert panels["ThermalSummary"].centery == panels["AirShotPanel"].centery
                hud._set_home_focus_target("AIR")
                hud._handle_dpad_left()
                assert hud._home_focus_target() == "TEMPS"
                hud._handle_up()
                assert hud._home_focus_target() == "DYNAMICS"
                hud._handle_down()
                assert hud._home_focus_target() == "TEMPS"
                hud._handle_dpad_right()
                assert hud._home_focus_target() == "AIR"
            hud._air_mode_callback.assert_not_called()

            # Merely navigating to temperatures never opens their menu.
            hud._set_home_focus_target("TEMPS")
            assert hud._active_menu == "home"
            hud._handle_select()
            assert hud._active_menu == "thermal_menu"
            hud._handle_back()
            assert hud._active_menu == "home" and hud._home_focus_target() == "TEMPS"
            hud._handle_back()
            assert hud._home_focus_target() == "SETTINGS"

            # Error focus is a lateral detour; clearing an error returns to its side panel.
            hud._set_home_focus_target("DYNAMICS")
            hud._visible_faults = ("THERMAL OFFLINE",)
            hud._handle_dpad_left()
            assert hud._home_focus_target() == "FAULTS"
            hud._handle_dpad_right()
            assert hud._home_focus_target() == "DYNAMICS"
            hud._normalize_home_focus("DYNAMICS", False)
            assert hud._home_focus_target() == "FAULTS"
            hud._visible_faults = ()
            hud._normalize_home_focus("FAULTS", True)
            assert hud._home_focus_target() == "DYNAMICS"

        # Air mode changes still need Select; Up leaves edit mode and moves upward.
        hud._set_home_focus_target("AIR")
        hud._handle_select()
        assert hud._active_menu == "air_selected"
        hud._handle_dpad_right()
        hud._air_mode_callback.assert_called_once()
        hud._handle_up()
        assert hud._active_menu == "home" and hud._home_focus_target() == "DYNAMICS"
        # Other modal pages must not silently move home focus behind the overlay.
        hud._active_menu = "service"
        hud._handle_dpad_right()
        hud._handle_dpad_left()
        assert hud._home_focus_target() == "DYNAMICS"

    pygame.quit()
    print("PASS home navigation: all modes, both sizes, physical directions, boundaries, errors and Select entry")


if __name__ == "__main__":
    check()
