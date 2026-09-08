"""No installed fonts or particular working directory required for the HUD."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import sys
import tempfile
import shutil
import zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pygame
from albatross_pi.hud.widgets import ui_utils as ui
from tools import make_update_bundle as bundle

pygame.font.init()
assert ui.BUNDLED_FONT.is_file()
assert (ui.BUNDLED_FONT.parent/'OFL.markdown').is_file()
original_cwd=Path.cwd()
with tempfile.TemporaryDirectory() as temp:
    try:
        os.chdir(temp)
        ui._FONT_CACHE.clear()
        with patch('pygame.font.SysFont',side_effect=AssertionError('system font lookup')):
            for bold in (False,True):
                for size in (8,12,24,64):
                    loaded=ui.font(size,bold=bold)
                    assert loaded.render('ALBATROSS 0123456789',True,(255,255,255)).get_width()>0
                    assert loaded is ui.font(size,bold=bold)
    finally:os.chdir(original_cwd)
    # The real archive builder retains binaries and license in a fresh install.
    root=Path(temp)/'repo'
    asset=root/'albatross_pi/assets/fonts/orbitron'
    asset.mkdir(parents=True)
    for path in ui.BUNDLED_FONT.parent.iterdir():shutil.copy2(path,asset/path.name)
    archive=Path(temp)/'app.zip'
    with patch.object(bundle,'ROOT',root):bundle._build_app_archive(archive)
    with zipfile.ZipFile(archive) as z:
        for name in ('Orbitron-Bold.ttf','OFL.markdown'):
            assert z.read('albatross_pi/assets/fonts/orbitron/'+name)==(asset/name).read_bytes()
    # Missing and corrupt assets degrade gracefully without system dependencies.
    corrupt=Path(temp)/'corrupt.ttf';corrupt.write_bytes(b'not a font')
    for path in (Path(temp)/'missing.ttf',corrupt):
        ui._FONT_CACHE.clear();ui._FONT_WARNING_EMITTED=False
        with patch.object(ui,'BUNDLED_FONT',path),patch('pygame.font.SysFont',side_effect=AssertionError),patch.object(ui.logging.getLogger(ui.__name__),'warning') as warn:
            assert ui.font(12).size('FALLBACK')[0]>0
            assert ui.font(24,bold=True).size('FALLBACK')[0]>0
            assert warn.call_count==1
ui._FONT_CACHE.clear();ui._FONT_WARNING_EMITTED=False
print('PASS bundled font loading, cache, arbitrary CWD, missing/corrupt fallback and update archive')
