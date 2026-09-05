"""Theme-native media instrument: metadata, transport and bounded device browser."""
import math
import pygame
from .widgets.ui_utils import font, fit_font_size


def timestamp(seconds):
    if not math.isfinite(seconds) or seconds < 0:
        return "--:--"
    seconds=int(seconds)
    return f"{seconds//60:02d}:{seconds%60:02d}"


def draw_media(hud):
    surface=hud.screen
    bg,bright,glow,fault=hud._theme_colors()
    sw,sh=surface.get_size()
    panel=pygame.Rect(0,0,min(820,sw-64),min(360,sh-80));panel.center=(sw//2,sh//2)
    pygame.draw.rect(surface,bg,panel)
    x,y,r,b=panel.x,panel.y,panel.right-1,panel.bottom-1
    pygame.draw.lines(surface,glow,True,[(x+10,y),(r,y),(r,b-10),(r-10,b),(x,b),(x,y+10)],2)
    def text(value,rect,color=bright,size=18,bold=False):
        value=str(value).replace("\n"," ").replace("\r"," ")
        # Preserve readable minimum size; ellipsize only when necessary.
        fitted=fit_font_size(value,rect.width,rect.height,start_size=size,min_size=12,bold=bold)
        while value and font(fitted,bold=bold).size(value)[0]>rect.width:
            value=value[:-4]+"..." if len(value)>4 else ""
        label=font(fitted,bold=bold).render(value,True,color)
        surface.blit(label,(rect.x,rect.centery-label.get_height()//2))
    text("COMMS / MEDIA",pygame.Rect(x+22,y+10,350,30),size=22,bold=True)
    text("BLUETOOTH / TRANSPORT",pygame.Rect(r-270,y+12,248,26),glow,13)
    pygame.draw.line(surface,glow,(x+22,y+48),(r-22,y+48))
    if hud._media_device_menu_open:
        devices=hud._available_devices
        text("SELECT AUDIO DEVICE",pygame.Rect(x+22,y+58,500,28),size=18,bold=True)
        if not devices:
            text("NO DEVICES FOUND",pygame.Rect(x+22,y+110,panel.width-44,30),fault,20,True)
            text("Pair a device on the Pi, then return here.",pygame.Rect(x+22,y+150,panel.width-44,26),glow,15)
        else:
            hud._media_device_cursor%=len(devices)
            count=5;first=max(0,min(hud._media_device_cursor-2,len(devices)-count))
            for index in range(first,min(first+count,len(devices))):
                mac,name=devices[index]
                row=pygame.Rect(x+22,y+94+(index-first)*35,panel.width-44,31)
                selected=index==hud._media_device_cursor
                if selected:pygame.draw.rect(surface,bright,row)
                color=bg if selected else glow
                text(f"{index+1:02d}  {name}",pygame.Rect(row.x+8,row.y,row.width-190,row.height),color,16,selected)
                text(mac,pygame.Rect(row.right-175,row.y,166,row.height),color,12)
            text(f"{hud._media_device_cursor+1} / {len(devices)}",pygame.Rect(r-100,y+58,78,25),glow,13)
        hint="D-PAD: DEVICE   SELECT: CONNECT REQUEST   BACK: PLAYER"
    else:
        text(hud._phone_track or "NO TRACK AVAILABLE",pygame.Rect(x+22,y+62,panel.width-44,42),size=30,bold=True)
        text(hud._phone_artist or "Waiting for player metadata",pygame.Rect(x+22,y+109,panel.width-44,30),glow,18)
        length=hud._phone_length_s;position=hud._phone_position_s
        known=math.isfinite(length) and length>0
        position=max(0,position) if math.isfinite(position) else 0
        if known:position=min(position,length)
        bar=pygame.Rect(x+22,y+159,panel.width-44,10)
        pygame.draw.rect(surface,glow,bar,1)
        if known:pygame.draw.rect(surface,bright,(bar.x+2,bar.y+2,int((bar.width-4)*position/length),6))
        text(timestamp(position)+" ELAPSED",pygame.Rect(x+22,y+178,250,23),glow,13)
        remaining="-"+timestamp(length-position)+" REMAIN" if known else "DURATION UNKNOWN"
        text(remaining,pygame.Rect(r-260,y+178,238,23),glow,13)
        labels=("<< PREV","PLAY / PAUSE","NEXT >>","DEVICES")
        width=(panel.width-44-24)//4
        for index,label in enumerate(labels):
            button=pygame.Rect(x+22+index*(width+8),y+224,width,43)
            selected=index==hud._media_index
            pygame.draw.rect(surface,bright if selected else glow,button,0 if selected else 1)
            text(label,button.inflate(-14,-6),bg if selected else glow,16,True)
        hint="D-PAD: CONTROL   SELECT: ACTIVATE   BACK: HUD"
    text(hud._media_feedback,pygame.Rect(x+22,b-70,panel.width-44,23),glow,13)
    pygame.draw.line(surface,glow,(x+22,b-39),(r-22,b-39))
    text(hint,pygame.Rect(x+22,b-33,panel.width-44,25),glow,13)
