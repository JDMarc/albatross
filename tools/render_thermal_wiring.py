"""Generate a source-driven thermal wiring planning pack (vector PDF + CSV).

Not a released PCB schematic. Unknown circuits and connector cavities are
explicitly held for engineering; this script does not change firmware.
"""
from pathlib import Path
import csv
import json
import subprocess
import textwrap
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, white

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output'/'pdf'
W,H=1224,792
INK='#142B3B'; DIM='#526675'; BLUE='#156C99'; GREEN='#22734F'; ORANGE='#A35419'; RED='#AD3131'; LIGHT='#EEF3F6'
SENSORS=json.loads((ROOT/'config/thermal_system.json').read_text())['sensors']
COMMIT=subprocess.check_output(['git','rev-parse','--short','HEAD'],cwd=ROOT,text=True).strip()


class Drawing:
    def __init__(self,path):
        self.c=canvas.Canvas(str(path),pagesize=(W,H))
        self.c.setTitle('Project Albatross - Thermal subsystem wiring - Rev C - implemented wiring / bench hold')
        self.c.setAuthor('Project Albatross')
        self.page=0
    def text(self,x,y,s,size=12,color=INK,bold=False):
        self.c.setFillColor(HexColor(color));self.c.setFont('Helvetica-Bold' if bold else 'Helvetica',size)
        self.c.drawString(x,H-y-size*.8,str(s))
    def para(self,x,y,s,width=90,size=12,color=INK):
        for n,line in enumerate(textwrap.wrap(s,width=width)):
            self.text(x,y+n*(size+5),line,size,color)
    def line(self,points,color=BLUE,dash=False,width=1.6):
        self.c.setStrokeColor(HexColor(color));self.c.setLineWidth(width);self.c.setDash(5,3) if dash else self.c.setDash()
        p=self.c.beginPath();p.moveTo(points[0][0],H-points[0][1])
        for x,y in points[1:]:p.lineTo(x,H-y)
        self.c.drawPath(p);self.c.setDash()
    def dot(self,x,y,color=BLUE):
        self.c.setFillColor(HexColor(color));self.c.circle(x,H-y,3,fill=1,stroke=0)
    def box(self,x,y,w,h,title,lines=(),color=BLUE):
        self.c.setFillColor(HexColor(LIGHT));self.c.setStrokeColor(HexColor(color));self.c.setLineWidth(1.2)
        self.c.roundRect(x,H-y-h,w,h,5,stroke=1,fill=1)
        self.text(x+12,y+12,title,14,color,True)
        for n,s in enumerate(lines):self.text(x+12,y+38+n*19,s,11)
    def note(self,y,title,body,color=RED):
        self.box(40,y,1144,68,title,(),color);self.para(54,y+35,body,145,11,color)
    def table(self,x,y,widths,headers,rows,row_h=29,size=11):
        total=sum(widths)
        for row,data in enumerate([headers]+rows):
            yy=y+row*row_h
            self.c.setFillColor(HexColor(INK if row==0 else LIGHT if row%2 else '#FFFFFF'))
            self.c.rect(x,H-yy-row_h,total,row_h,fill=1,stroke=0)
            xx=x
            for col,value in enumerate(data):
                value=str(value)
                # Fail authoring if a cell would silently clip.
                font='Helvetica-Bold' if row==0 else 'Helvetica'
                assert self.c.stringWidth(value,font,size)<=widths[col]-16,(self.page,value,widths[col])
                self.text(xx+8,yy+8,value,size,'#FFFFFF' if row==0 else INK,row==0);xx+=widths[col]
    def start(self,title,subtitle):
        if self.page:self.c.showPage()
        self.page+=1
        self.text(40,24,'ALBATROSS / THERMAL SYSTEM',12,BLUE,True)
        self.text(40,52,title,27,INK,True)
        self.text(40,91,subtitle,12,DIM)
        self.line([(40,119),(1184,119)],INK)
        self.text(40,751,f'REV C - FIRMWARE 2.0.0 / BENCH VALIDATION REQUIRED    |    2026-09-08    |    BASE {COMMIT} + LOCAL CHANGES',10,DIM)
        self.text(1110,751,f'{self.page:02d} / 10',11,BLUE,True)
    def save(self):self.c.save()


def tc(d):
    d.start('Thermocouple harnesses and breakout boards','Four independent K-type pairs; proposed example breakout: Adafruit MAX31856 #3263, not a generic pin-order guarantee')
    for n,s in enumerate(SENSORS[:4]):
        y=149+n*116
        d.box(40,y,305,89,f'T{s["id"]:02d} / {s["key"]}',[s['location'],'K-type probe; insulated junction preferred'],ORANGE)
        d.box(530,y,240,89,f'TC{n} / MAX31856',[f'T+ = positive / T- = negative',f'CS = Teensy {10-n}'],ORANGE)
        d.line([(345,y+37),(530,y+37)],ORANGE);d.text(372,y+17,'K+ -> T+',11,ORANGE)
        d.line([(345,y+69),(530,y+69)],ORANGE);d.text(372,y+74,'K- -> T-',11,ORANGE)
        d.text(811,y+15,'VIN <- +3V3_P; GND <- logic GND',12)
        d.text(811,y+39,'SDI 11 / SDO 12 / SCK 13',12)
        d.text(811,y+63,'3Vo, FLT and DRDY: leave unconnected',11,DIM)
    d.note(635,'THERMOCOUPLE ROUTING IS NOT ORDINARY COPPER SENSOR WIRING',
        'Keep K-alloy extension cable and matched polarity connectors through to the cold-junction terminals. Do not tie T- to chassis or SGND. Confirm grounded-junction compatibility and input common-mode limits before using a grounded probe.')
    d.text(40,719,'Keep boards away from heat gradients. These inputs are not galvanically isolated. MAX31856 source: sheet 10.',11,DIM)



if __name__ == '__main__':
    from thermal_wiring_rev_b import render
    render(Drawing, tc, ROOT, SENSORS)
