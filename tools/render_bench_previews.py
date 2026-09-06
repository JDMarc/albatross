"""Render code-native bench previews, without connecting to CAN."""
import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pygame
from PIL import Image
from albatross_pi.bench.model import BenchModel
from albatross_pi.bench.view import BenchView


def main():
    output = Path(sys.argv[1]); output.mkdir(parents=True,exist_ok=True)
    pygame.init()
    canvas = pygame.Surface((1280,720))
    m = BenchModel(); v = BenchView(m,'green')
    m.configure(limit=65,scenario=1); m.arm(); m.run()
    frames = []
    for n in range(1,121):
        m.tick(n*.05)
        v.render(canvas)
        if n == 50: pygame.image.save(canvas,str(output/'bench-sim.png'))
        if n%2 == 0:
            frames.append(Image.frombytes('RGB',canvas.get_size(),pygame.image.tobytes(canvas,'RGB')).resize((960,540)))
    frames[0].save(output/'bench-animation.gif',save_all=True,append_images=frames[1:],duration=100,loop=0)
    for mode in ('LIVE','REPLAY'):
        model = BenchModel(mode)
        view = BenchView(model,'amber' if mode == 'LIVE' else 'cyan')
        view.render(canvas)
        pygame.image.save(canvas,str(output/('bench-'+mode.lower()+'.png')))
    for tab in range(1,4):
        v.tab=tab; v.render(canvas)
        pygame.image.save(canvas,str(output/f'bench-page-{tab+1}.png'))
    pygame.quit()
    print(output)


if __name__ == '__main__': main()
