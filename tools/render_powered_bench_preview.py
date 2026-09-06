"""Synthetic preview of powered-bench UI; never opens a USB/CAN connection."""
import os
os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy'
from pathlib import Path
import sys
import math
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pygame
from PIL import Image
from dbw_bench_hud import draw


def main():
    output=Path(sys.argv[1]);output.mkdir(parents=True,exist_ok=True)
    pygame.init();surface=pygame.Surface((1280,720));trace=[];frames=[]
    for n in range(100):
        target=int(180*(1-math.cos(n/100*math.pi*2))/2)
        actual=max(0,target-8)
        status=dict(state=2,reason=0,permit=1,key=1,deadman=1,good=1,target=target,actual=actual,current_ma=150)
        trace.append((n,target,actual))
        draw(surface,pygame,status,True,target,False,'SYNTHETIC UI PREVIEW / NO HARDWARE CONNECTED',trace)
        if n==50:pygame.image.save(surface,str(output/'powered-bench.png'))
        frames.append(Image.frombytes('RGB',surface.get_size(),pygame.image.tobytes(surface,'RGB')).resize((960,540)))
    frames[0].save(output/'powered-bench.gif',save_all=True,append_images=frames[1:],duration=50,loop=0)
    draw(surface,pygame,{},False,0,False,'',[])
    pygame.image.save(surface,str(output/'powered-bench-disconnected.png'))
    pygame.quit()


if __name__=='__main__':main()
