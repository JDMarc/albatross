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
        self.c.setTitle('Project Albatross - Thermal subsystem wiring - Rev A planning')
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
        self.text(40,751,f'REV A - PLANNING / NOT RELEASED FOR FABRICATION    |    2026-09-06    |    SOURCE {COMMIT}',10,DIM)
        self.text(1110,751,f'{self.page:02d} / 10',11,BLUE,True)
    def save(self):self.c.save()


def overview(d):
    d.start('Whole-subsystem wiring overview','29 active sensors / one dedicated Teensy 4.1 / six SPI front ends / CAN to main controller and HUD')
    d.box(40,153,285,92,'4 x K-TYPE THERMOCOUPLES',['EGT L/R + turbine outlet L/R','Dedicated K-alloy wire pairs; sheet 04'],ORANGE)
    d.box(40,282,285,92,'18 x NTC THERMISTORS',['14 air / charge / ambient + 4 coolant','Two isolated element wires; sheet 06'],GREEN)
    d.box(40,411,285,92,'7 x PT1000 RTDs',['Head metal L/R + 5 oil locations','Two-wire current-excited inputs; sheet 07'],GREEN)
    d.box(385,153,310,92,'4 x MAX31856 FRONT ENDS',['One probe per compensated converter','CS 10 / 9 / 8 / 7; sheets 03-04'],ORANGE)
    d.box(385,325,310,170,'ANALOG CONDITIONING + 2 ADCs',['18 NTC pull-ups + 7 RTD excitations','ADS7953 ADC0 CS 6 / ADC1 CS 5','25 analog channels used / 7 unpopulated','Reference + sampling HOLD; sheets 05-09'],GREEN)
    d.line([(325,199),(385,199)],ORANGE)
    d.line([(325,327),(353,327),(353,377),(385,377)],GREEN)
    d.line([(325,456),(385,456)],GREEN)
    d.box(760,235,190,210,'THERMAL TEENSY',['Teensy 4.1 - node 5','SPI: 11 / 12 / 13','CAN1: TX22 / RX23','USB: service only','No direct probe inputs'],BLUE)
    d.line([(695,199),(720,199),(720,285),(760,285)],BLUE)
    d.line([(695,411),(730,411),(730,380),(760,380)],BLUE)
    d.box(1020,235,164,103,'CAN TRANSCEIVER',['3.3 V logic compatible','Exact module TBD'],BLUE)
    d.line([(950,288),(1020,288)],BLUE)
    d.box(1010,413,174,82,'500 kbit/s TRUNK',['Main / ECU / Pi','Other existing nodes'],BLUE)
    d.line([(1105,338),(1105,413)],BLUE)
    d.box(40,558,350,102,'PROTECTED POWER / SHEET 02',['Fused switched supply -> protected DC/DC','5 V VIN; separate regulated peripheral rails','Power return and shield bonds are distinct'],RED)
    d.box(430,558,365,102,'INDEPENDENT ECU SENSORS RETAINED',['ECU coolant + IAT + oil temperature stay wired','Do not parallel thermal and ECU sensor inputs','No ECU replacement-input wiring approved here'],INK)
    d.box(835,558,349,102,'DRAWING KEY',['Solid named net = defined signal assignment','Dashed = proposed / unresolved implementation','Dot = connection; crossing without dot = no join'],DIM)
    d.text(40,697,'Scope: complete functional harness map, not a purchased-board cavity map or a finished analog PCB schematic.',13,RED,True)


def power(d):
    d.start('Power distribution, returns and CAN','Functional connections; fuse, DC/DC, transceiver and connector part numbers remain to be selected')
    d.box(40,155,180,105,'PDM / FUSED FEED',['Switched vehicle supply','Dedicated thermal branch','Fuse rating: load-based'],RED)
    d.box(285,155,230,105,'INPUT PROTECTION',['Reverse-polarity protection','Automotive transient clamp','Input filter / power return'],RED)
    d.box(580,155,205,105,'REGULATED +5V_T',['Automotive-rated DC/DC','Budget all downstream loads','Not raw motorcycle 12 V'],RED)
    d.line([(220,207),(285,207)],RED);d.line([(515,207),(580,207)],RED)
    d.box(905,148,279,130,'THERMAL TEENSY 4.1',['+5V_T -> VIN; return -> GND','USB data for programming/logging','Isolate VUSB from VIN for dual supply','Do not parallel 3.3 V regulators'],BLUE)
    d.line([(785,190),(905,190)],RED)
    d.box(580,324,205,118,'PERIPHERAL RAILS',['+3V3_P: dedicated regulator','+5V_A: quiet analog rail','+2V5_REF / EXC: proposed','Current budget + startup: TBD'],RED)
    d.line([(830,190),(830,302),(682,302),(682,324)],RED);d.dot(830,190,RED)
    d.box(40,332,465,110,'BOARD-LEVEL POWER CONNECTIONS',['+3V3_P -> MAX board VIN (Adafruit #3263 example)','+3V3_P -> ADS +VBD; +5V_A -> ADS +VA','+2V5_REF -> ADC REFP; EXC buffer -> NTC pull-ups','All logic 3.3 V; ADC analog voltage is NOT GPIO voltage'],GREEN)
    d.line([(580,380),(505,380)],RED,True)
    d.box(905,329,279,113,'TRANSCEIVER MODULE - TBD',['Teensy TX22 -> TXD / D input','RXD / R output -> Teensy RX23','VCC / VIO: exact module dependent','Never allow a 5 V RXD into Teensy'],BLUE)
    d.line([(1035,278),(1035,329)],BLUE)
    d.line([(930,442),(930,519),(1140,519)],BLUE);d.line([(955,442),(955,548),(1140,548)],GREEN)
    d.text(1145,510,'CANH',12,BLUE,True);d.text(1145,539,'CANL',12,GREEN,True)
    d.text(815,580,'Twisted pair; short stub to the existing trunk.',12)
    d.text(815,605,'120 ohm only if this is a physical bus end.',12)
    d.box(40,494,715,150,'GROUND / SHIELD STRATEGY',['Sensor B returns -> quiet SGND at acquisition PCB; never use engine metal as a sensor wire.','SGND, ADC AGND/BDGND and logic GND join via a deliberate low-noise PCB ground strategy.','DC/DC return -> thermal branch power return; no solenoid/pump return current through SGND.','Cable shields -> planned chassis/shield bond at enclosure entry; not a thermocouple minus wire.','Non-isolated CAN needs an appropriate common reference; verify ground offset and final bonding.'],INK)
    d.text(40,684,'Source [P1]. Proposed separate peripheral regulator avoids assuming spare current capacity on the Teensy regulator.',12,DIM)
    d.text(40,710,'Do not back-power unpowered boards through SPI. Confirm rail sequencing and any required isolation/series protection.',12,RED)


def spi(d):
    d.start('SPI and chip-select wiring','Every module shares MOSI, MISO and SCK; each has its own active-low chip select')
    d.box(40,150,180,160,'TEENSY 4.1',['11 = MOSI / data out','12 = MISO / data in','13 = SCK','GND = logic reference'],BLUE)
    buses=[(190,BLUE,'11 -> SDI / MOSI'),(227,GREEN,'12 <- SDO / MISO'),(264,ORANGE,'13 -> SCK / SCLK')]
    for y,col,label in buses:
        d.line([(220,y),(1180,y)],col);d.text(260,y-20,label,12,col,True)
    modules=[('TC0',10,'EGT LEFT'),('TC1',9,'EGT RIGHT'),('TC2',8,'TURBINE OUT L'),('TC3',7,'TURBINE OUT R'),('ADC0',6,'ANALOG 0-15'),('ADC1',5,'ANALOG 16-31')]
    for n,(name,pin,role) in enumerate(modules):
        x=245+n*157
        d.box(x,356,147,125,name,[f'CS <- Teensy {pin}',role,'Power: sheet 02','Inputs: sheets 04-09'],BLUE)
        for j,(y,col,_) in enumerate(buses):
            xx=x+30+j*34;d.line([(xx,y),(xx,356)],col);d.dot(xx,y,col)
    d.text(40,514,'MODULE PAD NAME CROSSWALK',14,INK,True)
    d.table(40,548,[160,170,170,170,170,304],['Module','MOSI net 11','MISO net 12','Clock net 13','Chip select','Unused / power notes'],[
        ['MAX31856 board','SDI','SDO','SCK','CS (per above)','FLT, DRDY, 3Vo not connected'],
        ['ADS7953 board','SDI','SDO','SCLK','CS (per above)','GPIOs unused; configure safe state'],
    ],32,11)
    d.text(40,668,'Proposed: a 10 kOhm pull-up on each CS to its 3.3 V logic rail. Check for existing pull-ups before adding.',12,RED)
    d.text(40,695,'Keep SPI inside the acquisition enclosure; verify unselected SDO is high impedance. No breadboard-length vehicle SPI.',12)
    d.text(40,721,'Source: repository driver headers; Adafruit shared-SPI guidance [A1]. Crossings without dots are not connected.',11,DIM)


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
    d.text(40,719,'Keep converter boards away from heat gradients. Shared logic ground does not make these inputs galvanically isolated. Source [A1].',11,DIM)


def adc(d):
    d.start('Analog front-end board connections','ADC0 and ADC1 repeat this functional circuit; physical package / breakout connector pin numbers are not selected')
    d.box(40,156,242,140,'16 CONDITIONED INPUTS',['CH0 ... CH15 from sheets 08/09','NTC / RTD circuits sheets 06/07','Clamp exposed harness faults','RC / source settling: design TBD'],GREEN)
    d.box(350,156,250,238,'ADS7953 x 2',['+VA <- +5V_A (proposed)','+VBD <- +3V3_P','REFP <- +2V5_REF (proposed)','REFM / AINM -> AGND','AGND / BDGND -> local ground','SDI / SDO / SCLK / CS: sheet 03'],BLUE)
    d.line([(282,210),(350,210)],GREEN)
    d.box(760,165,424,110,'REFERENCE / EXCITATION BLOCK - HOLD',['Precision 2.5 V reference + local bypassing','Separate buffered 2.5 V NTC excitation, ratio-tracked to REF','Driver/conversion calibration must match this proposal'],RED)
    d.line([(760,221),(660,221),(660,292),(600,292)],RED,True)
    d.box(760,336,424,128,'MUX OUTPUT PATH MUST BE PRESENT',['ADS MXO -> suitable unity buffer/filter -> ADS AINP','AINM -> analog return (single-ended measurement)','Select buffer and settling network for the actual source','No open MXO/AINP path; inspect any breakout schematic'],GREEN)
    d.line([(600,347),(685,347),(685,373),(760,373)],GREEN)
    d.line([(760,426),(665,426),(665,378),(600,378)],GREEN)
    d.box(40,442,560,146,'LOCAL PCB DETAILS STILL REQUIRED',['Local supply and reference decoupling; validated ADC input protection','RTD current-source compliance / stability and NTC excitation loading','ADC input RC, buffer stability and multiplexer settling across channel steps','Unpopulated channels: terminate/park per PCB design; do not add phantom sensors','No ADC channel connects directly to a Teensy analog pin'],INK)
    d.note(615,'HOLD: CURRENT FIRMWARE IS NOT YET COMPATIBLE WITH A RELEASED ANALOG DESIGN',
        'ADS7953 REF permits 2.0-3.0 V, not 3.3 V. Current RTD conversion assumes a 3.3 V full scale. The two-frame read also needs N+2 pipeline verification. Resolve range, excitation ratio, priming and channel tags before trusting temperatures.')
    d.text(40,711,'Proposed implementation, not a selected ADC breakout. Source [T1] plus repository analog_adc_driver.cpp / sensor_conversion.cpp.',11,DIM)


def ntc(d):
    d.start('NTC conditioning - repeat for 18 channels','14 air/charge/ambient channels use the IAT profile; four coolant channels use their separate profile')
    for x,title,res,profile in [(40,'IAT / CHARGE / AMBIENT', '10.0 kOhm','R25 = 10 kOhm / B = 3435 K'),(640,'COOLANT', '2.49 kOhm','R80 = 2.50 kOhm / B = 3977 K')]:
        d.box(x,151,544,405,title,[],GREEN)
        d.text(x+24,197,'EXC_NTC (proposed buffered 2.5 V)',12,RED)
        d.line([(x+125,224),(x+125,253)],RED)
        d.box(x+78,253,95,56,'R pull-up',[res],GREEN)
        d.line([(x+125,309),(x+125,345)],GREEN);d.dot(x+125,345,GREEN)
        d.line([(x+125,345),(x+220,345)],GREEN)
        d.box(x+220,314,290,83,'INPUT PROTECTION / RC',['Series input/filter network: TBD','Sense output -> assigned ADC CH'],GREEN)
        d.line([(x+125,345),(x+125,415)],GREEN)
        d.box(x+76,415,99,53,'NTC',['Probe element'],GREEN)
        d.line([(x+125,468),(x+125,502),(x+285,502)],INK)
        d.text(x+200,470,'B wire -> SGND',12)
        d.text(x+23,365,'A wire = SIG',11,GREEN)
        d.text(x+24,525,profile+' (existing profile, not verified probe data)',10,RED)
    d.note(582,'THE PULL-UP CIRCUIT IS REQUIRED; A BREAKOUT ADC DOES NOT SUPPLY IT',
        'Each NTC has its own pull-up and dedicated signal/return pair. Excitation must track ADC full scale for the existing resistance-ratio formula. A 3.3 V pull-up with a 2.5 V full scale is not interchangeable.')
    d.text(40,676,'Do not assume a common automotive coolant sender matches 2.50 kOhm at 80 C. Obtain actual resistance tables.',12,RED)
    d.text(40,703,'Specify probe temperature rating, sealing, thread, response time and WMI-fluid compatibility before ordering. No ECU sensor sharing.',12)


def rtd(d):
    d.start('PT1000 conditioning - repeat for seven channels','A 500 uA precision excitation is assumed by the current conversion code; the actual conditioning board is not designed yet')
    d.box(40,156,300,100,'QUIET ANALOG SUPPLY',['Current-source rail: select for compliance','Do not substitute a pull-up resistor','Keep channel excitation independent'],RED)
    d.box(430,156,250,100,'500 uA EXCITATION',['Precision current source','Per channel / implementation TBD'],GREEN)
    d.line([(340,205),(430,205)],RED,True)
    d.line([(555,256),(555,324)],GREEN);d.dot(555,324,GREEN)
    d.text(390,293,'A wire / RTD SIG',12,GREEN,True)
    d.box(815,285,369,115,'ADC SENSE BRANCH',['SIG -> protection / RC -> assigned ADC CH','Do not put filter resistance in the RTD loop','Buffer / settling / leakage budget: TBD'],GREEN)
    d.line([(555,324),(815,324)],GREEN)
    d.line([(555,324),(555,393)],GREEN)
    d.box(430,393,250,88,'PT1000 ELEMENT',['Isolated two-wire probe','B return -> dedicated SGND'],GREEN)
    d.line([(555,481),(555,539),(870,539)],INK)
    d.text(885,530,'SGND / acquisition return',12,INK,True)
    d.box(40,323,305,199,'ACTIVE RTD INPUTS',['20 / HEAD METAL LEFT','21 / HEAD METAL RIGHT','24 / OIL GALLERY','25-26 / OIL COOLER IN / OUT','27-28 / TURBO OIL DRAIN L / R','CHRA housing inputs remain disabled'],GREEN)
    d.note(584,'TWO-WIRE LIMITATION AND CONVERSION HOLD',
        'Lead resistance is included in this measurement. Three/four-wire compensation is not implemented. Validate self-heating, current accuracy and full temperature conversion; the existing linear RTD model is an approximation and must be recalibrated for the chosen ADC range.')
    d.text(40,682,'Keep both probe conductors isolated from chassis. Open/short protection must not damage the current source or ADC.',12)
    d.text(40,710,'A MAX31865 RTD breakout is not a drop-in replacement for this ADS7953/current-source architecture; firmware would change.',12,RED)


def channel_sheet(d,device):
    d.start(f'ADC{device} channel-by-channel harness',f'ADS7953 device {device} / CS = Teensy {6-device} / logical analog channels {device*16}-{device*16+15}')
    d.text(40,145,'Each row is one complete two-wire sensor circuit. A/B are proposed harness net labels, NOT manufacturer connector cavity numbers.',12,RED)
    rows=[]
    for channel in range(16):
        logical=device*16+channel
        s=next((s for s in SENSORS if s['source']['bus']=='ads7953' and s['source']['channel']==logical),None)
        if s and s['enabled']:
            sid=s['id'];typ=s['technology'];circuit='RTD / 500 uA' if typ=='pt1000' else 'CLT / 2.49k' if typ=='coolant_ntc' else 'IAT / 10k'
            rows.append([f'CH{channel}',str(logical),str(sid),s['key'],circuit,f'T{sid:02d}-A -> SIG -> CH{channel}',f'T{sid:02d}-B -> SGND'])
        else:
            rows.append([f'CH{channel}',str(logical),str(s['id']) if s else '-',s['key'] if s else 'UNALLOCATED SPARE','NOT FITTED','No sensor lead','No sensor return'])
    d.table(40,183,[65,65,50,273,145,285,261],['ADC pin','Logical','ID','Sensor / reserved name','Conditioning','Signal wire path','Return wire path'],rows,28,11)
    d.text(40,689,'All input filtering/protection is on the acquisition side of the harness connector. See sheets 05-07 for circuit topology.',12)
    d.text(40,713,'ID32 has no physical input assignment. The stable ID namespace is not the same thing as ADC channel numbering.',12,DIM)


def release(d):
    d.start('Build boundary, connector schedule and checks','Close these items before turning the planning pack into a fabrication-ready schematic')
    d.table(40,147,[215,440,489],['Connection group','Defined now','Still required'],[
        ['T01-T04 / 4 K pairs','TC polarity, probe role, converter CS','K connector family, grounded/ungrounded probe part'],
        ['T05-T29 / 25 A/B pairs','Signal role, sensor profile, ADC channel','Sealed connector cavities, wire gauge/length, probe PN'],
        ['Power / thermal branch','VIN 5 V, regulated peripheral rails, return','Fuse/DC/DC/transient devices and measured load budget'],
        ['CAN interface','TX22 to TXD; RXD to RX23; H/L trunk','Exact 3.3 V-compatible module and termination location'],
        ['Analog acquisition PCB','Channel allocation and required circuit blocks','Reference, excitation, buffer, filter, protection schematic'],
        ['Firmware commissioning','Source sensor IDs and baseline profiles','ADC pipeline/range repair and measured calibration'],
    ],34,11)
    d.box(40,407,545,178,'BENCH CHECKLIST',['1. Check power polarity, shorts and USB/VIN isolation before power.','2. Verify rails / logic levels with sensors disconnected.','3. Confirm each probe label by substituting one known input at a time.','4. Test resistor/RTD standards and K-type simulator points.','5. Validate open, short, crossed lead, stale node and power-loss faults.','6. Compare raw codes to expected voltage and confirm channel identity.','7. Confirm main-controller thermal fallback with the Pi unplugged.'],GREEN)
    d.box(625,407,559,178,'IMPORTANT FINDINGS / NO FIRMWARE EDIT IN THIS PACK',['H1: 3.3 V conversion assumption versus ADS reference/range.','H2: manual-mode channel return is N+2; current read is two frames.','H3: ADS board and excitation/protection circuits are not selected.','H4: exact sensor curves, connectors and shield bonds are unverified.','H5: keep independent ECU coolant, IAT and oil-temperature inputs.','Do not order an arbitrary ADS7953 module and assume it includes','NTC pull-ups, RTD current sources, buffer or a valid reference.'],RED)
    refs=[('[P1] PJRC Teensy 4.1 pin card; TX22 / RX23','https://www.pjrc.com/teensy/card11a_rev4_web.pdf'),('[A1] Adafruit MAX31856 breakout pinouts','https://learn.adafruit.com/adafruit-max31856-thermocouple-amplifier/pinouts'),('[T1] TI ADS7953 datasheet, SLAS605C; reference / MXO / Fig. 51','https://www.ti.com/lit/ds/symlink/ads7953.pdf')]
    for n,(label,url) in enumerate(refs):
        y=613+n*33;d.text(40,y,label,11,BLUE,True);d.text(440,y,url,10,DIM)
        d.c.linkURL(url,(40,H-y-18,1184,H-y+2),relative=0)
    d.text(40,722,'Repository: config/thermal_system.json and arduino/teensy41/albatross_thermal_node/*; source hash on every sheet.',11,DIM)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    d=Drawing(OUT/'albatross-thermal-wiring.pdf')
    overview(d);power(d);spi(d);tc(d);adc(d);ntc(d);rtd(d);channel_sheet(d,0);channel_sheet(d,1);release(d);d.save()
    with (OUT/'thermal-sensor-wire-schedule.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.writer(f);writer.writerow(['sensor_id','sensor_key','enabled','technology','location','frontend','chip_select_teensy','adc_channel','signal_net','return_net','connector_cavity_status'])
        for s in SENSORS:
            src=s['source'];bus=src['bus'];ch=src['channel'];on=s['enabled']
            tc_bus=bus=='max31856';analog=bus=='ads7953'
            writer.writerow([s['id'],s['key'],on,s['technology'],s['location'],f'TC{ch}' if tc_bus else f'ADC{ch//16}' if analog else 'NONE',10-ch if tc_bus else 6-ch//16 if analog else '',ch%16 if analog else '',f'T{s["id"]:02d}-'+('K+' if tc_bus else 'A') if on else '',f'T{s["id"]:02d}-'+('K-' if tc_bus else 'B -> SGND') if on else '', 'TBD - logical labels only'])
    print(OUT/'albatross-thermal-wiring.pdf')


if __name__=='__main__':main()
