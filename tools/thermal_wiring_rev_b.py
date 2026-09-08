"""Revision C pack: validate implemented Rev B wiring against firmware config."""
import json
import csv

NTC_IDS = list(range(5, 20)) + [22, 23, 29]
RTD_IDS = [20, 21, 24, 25, 26, 27, 28]
RTD_CS = [2, 3, 4, 5, 6, 14, 15]
# Three boards on Wire; two on Wire1. Addresses are unique per bus.
ADCS = [('N0', 'Wire', 18, 19, '0x48', 'GND'),
        ('N1', 'Wire', 18, 19, '0x49', 'VDD'),
        ('N2', 'Wire', 18, 19, '0x4A', 'SDA'),
        ('N3', 'Wire1', 17, 16, '0x48', 'GND'),
        ('N4', 'Wire1', 17, 16, '0x49', 'VDD')]
BLUE, GREEN, RED, INK, DIM = '#156C99', '#22734F', '#AD3131', '#142B3B', '#526675'


def allocation(s):
    sid = s['id']
    if not s['enabled']:
        return ('UNASSIGNED', '', '', '', '', '')
    if sid <= 4:
        return (f'TC{sid-1}', 'SPI', '', str(11-sid), 'T+', 'T-')
    if sid in RTD_IDS:
        i = RTD_IDS.index(sid)
        return (f'R{i}', 'SPI', '', str(RTD_CS[i]), 'RTD+ / F+', 'RTD- / F-')
    i = NTC_IDS.index(sid)
    name, bus, _, _, addr, _ = ADCS[i//4]
    return (name, bus, addr, '', f'A{i%4}', 'SGND')


def overview(d):
    d.start('Recommended breakout-board architecture', '29 active sensors / second Teensy 4.1 / Rev B supersedes the ADS7953 wiring plan')
    groups = [('4 K-TYPE PROBES', '4 x MAX31856 #3263', 'SPI / CS 10, 9, 8, 7', 'EGT and turbine outlets; sheet 04'),
              ('18 NTC THERMISTORS', '5 x ADS1115 #1085', 'Wire + Wire1 / sheets 05, 08', '14 air/ambient + 4 coolant; sheet 06'),
              ('7 PT1000 PROBES', '7 x MAX31865 #3648', 'SPI / CS 2, 3, 4, 5, 6, 14, 15', 'Dedicated RTD boards; sheets 07, 09')]
    for i, (sensors, board, bus, detail) in enumerate(groups):
        y = 158+i*145
        d.box(40,y,290,100,sensors,[detail],GREEN)
        d.box(400,y,350,100,board,[bus,'VIN/VDD = +3V3_P; common logic GND'],BLUE)
        d.line([(330,y+50),(400,y+50)],GREEN)
        d.line([(750,y+50),(800,y+50),(800,354),(870,354)],BLUE)
    d.box(870,270,314,166,'THERMAL TEENSY 4.1',['SPI: MOSI11 / MISO12 / SCK13','Wire: SDA18 / SCL19','Wire1: SDA17 / SCL16','CAN1: TX22 / RX23 -> transceiver'],BLUE)
    d.box(40,610,550,95,'RETAINED ECU PROTECTION',['Dedicated ECU coolant, IAT and oil sensors remain separate.','No parallel sensor inputs or ECU replacement signal in this plan.'],INK)
    d.box(630,610,554,95,'FIRMWARE IMPLEMENTED / BENCH HOLD',['Thermal config 2.0.0 implements these breakout boards.','Use the matching new binary; validate wiring on the bench.'],RED)


def power(d):
    d.start('Protected power, grounds and CAN', 'No external ADS7953 reference, mux buffer or custom RTD current source in Rev B')
    boxes=[(40,235,'FUSED THERMAL FEED',['Switched vehicle supply','Fuse based on measured loads']),
           (335,245,'INPUT PROTECTION',['Reverse polarity / transient clamp','Automotive input filter']),
           (640,240,'REGULATED +5V_T',['Automotive-rated DC/DC','Return to thermal power branch'])]
    for x,w,title,lines in boxes:d.box(x,155,w,100,title,lines,RED)
    d.line([(275,205),(335,205)],RED); d.line([(580,205),(640,205)],RED)
    d.box(950,155,234,100,'TEENSY VIN / GND',['+5V_T -> VIN','Isolate VUSB for dual supply'],BLUE)
    d.line([(880,205),(950,205)],RED)
    d.box(640,330,240,110,'+3V3_P REGULATOR',['External peripheral regulator','Supply all 16 breakout boards','Current/thermal budget: TBD'],RED)
    d.line([(910,205),(910,290),(760,290),(760,330)],RED);d.dot(910,205,RED)
    d.box(40,325,525,135,'PERIPHERAL POWER CONNECTIONS',['5 x ADS1115: VDD -> +3V3_P; GND -> quiet return','4 x MAX31856 and 7 x MAX31865: VIN -> +3V3_P','MAX 3Vo outputs: unconnected; never parallel regulators','NTC pull-ups -> EXC_NTC derived from quiet +3V3_P','Monitor actual EXC_NTC on N4.A2; sheet 06'],GREEN)
    d.line([(640,385),(565,385)],RED)
    d.box(950,330,234,130,'CAN TRANSCEIVER - TBD',['TX22 -> TXD / D','RXD / R -> RX23','3.3 V-compatible logic','CANH / CANL -> twisted pair'],BLUE)
    d.line([(1060,255),(1060,330)],BLUE)
    d.box(40,510,1144,180,'GROUND, HARNESS AND POWER RULES',['NTC B wires return to SGND at acquisition board; do not use engine metal as the sensor return.','PT1000 wires go only to their MAX31865 sensor terminals. Do NOT ground an RTD lead externally.','Bond quiet signal return and logic/power ground deliberately; keep pump/valve currents out of this path.','Shields terminate at a planned enclosure/chassis bond, not at TC minus or RTD minus. Bond detail remains TBD.','CAN is 500 kbit/s. Fit 120 ohm across H/L only at physical bus ends; verify common-reference offsets.','Keep SPI/I2C inside enclosure. Check rail sequencing; prevent back-power through unpowered digital inputs.','Power budget includes regulator losses, breakout bias/LED loads, transceiver and all NTC excitation currents.'],INK)


def spi(d):
    d.start('SPI backbone and complete Teensy pin allocation', 'Physical thermal-node pins only; main-controller pins are a separate namespace')
    d.box(40,150,270,130,'THERMAL TEENSY',['11 -> all SDI','12 <- all SDO','13 -> all SCK','Common logic ground'],BLUE)
    d.box(455,150,320,130,'4 x MAX31856',['TC0..TC3 / Adafruit #3263','CS pins 10, 9, 8, 7','FLT / DRDY / 3Vo: unconnected'],GREEN)
    d.box(865,150,319,130,'7 x MAX31865',['R0..R6 / PT1000 #3648','CS pins 2, 3, 4, 5, 6, 14, 15','RDY / 3Vo: unconnected'],GREEN)
    d.line([(310,220),(455,220)],BLUE);d.line([(775,220),(865,220)],BLUE)
    rows=[['SPI MOSI / MISO / SCK','11 / 12 / 13','All eleven SPI front ends'],
          ['Thermocouple CS','10 / 9 / 8 / 7','TC0 / TC1 / TC2 / TC3'],
          ['RTD CS','2 / 3 / 4 / 5 / 6 / 14 / 15','R0 / R1 / R2 / R3 / R4 / R5 / R6'],
          ['Wire SDA / SCL','18 / 19','N0, N1, N2 only'],
          ['Wire1 SDA / SCL','17 / 16','N3, N4 only'],
          ['CAN1 TX / RX','22 / 23','Via selected transceiver; never directly to CANH/L']]
    d.table(40,328,[275,280,589],['Function','Teensy pins','Destination'],rows,40,12)
    d.text(40,647,'Each CS is active low; pull up to +3V3_P (proposed 10 kOhm, accounting for board pull-ups).',12,RED)
    d.text(40,674,'Initialize every CS high. Per-device SPI settings and high-impedance unselected SDO require bench verification.',12)
    d.text(40,701,'Pins 5/6 are now RTD selects, NOT the old ADS7953 selects. Older ADS7953 binaries must not operate this harness.',12,RED)


def i2c(d):
    d.start('ADS1115 bus wiring and address straps', 'Five Adafruit #1085 boards / 20 single-ended inputs / no external I2C multiplexer')
    for y,title,pins,names in [(155,'WIRE BUS', 'SDA18 / SCL19',ADCS[:3]),(340,'WIRE1 BUS','SDA17 / SCL16',ADCS[3:])]:
        d.box(40,y,225,120,title,[pins,'Both lines pulled to +3V3_P','Do not join buses together'],BLUE)
        for i,(name,bus,sda,scl,addr,strap) in enumerate(names):
            x=350+i*285
            d.box(x,y,250,120,f'{name} / ADS1115',[f'Address {addr} / ADDR -> {strap}','VDD -> +3V3_P / GND -> SGND','ALRT: unconnected'],GREEN)
            d.line([(265,y+90),(x,y+90)],BLUE)
    d.box(40,530,1144,170,'ADDRESS AND ELECTRICAL CHECKS',['ADDR straps are named nets, not connector cavity numbers. N2 ADDR connects to its own SDA net.','Verify the purchased board revision/default ADDR link; do not leave a conflicting strap to ground.','Expected scan: Wire = 0x48, 0x49, 0x4A; Wire1 = 0x48, 0x49. Duplicate addresses across buses are intentional.','Account for parallel onboard SDA/SCL pull-ups. Measure effective resistance and rise time before choosing bus speed.','Do not add extra pull-ups blindly. Keep every I2C pull-up at 3.3 V, never 5 V.','Use a nonblocking conversion scheduler: the ADS1115 conversion rate is shared across its selected inputs.','Separate buses improve fault containment but are not galvanic isolation. A failed board invalidates its assigned channels.'],INK)


def ntc(d):
    d.start('Thermistor input circuit and excitation monitoring', 'Repeat for 18 probes; ADS1115 internal reference is NOT the thermistor excitation supply')
    d.text(60,152,'QUIET EXC_NTC = nominal +3V3_P',14,RED,True)
    d.line([(230,185),(230,220)],RED)
    d.box(145,220,170,75,'PRECISION PULL-UP',['IAT: 10.0 kOhm','Coolant: 2.49 kOhm'],GREEN)
    d.line([(230,295),(230,342)],GREEN);d.dot(230,342,GREEN)
    d.line([(230,342),(580,342)],GREEN)
    d.box(580,300,550,100,'PROTECTION / RC -> ASSIGNED ADS1115 A0..A3',['Connector fault limiting / clamp / filter values: engineering TBD','Choose impedance and settling to suit the ADC input and probe','No raw vehicle 12 V or negative signal allowed at ADC input'],GREEN)
    d.line([(230,342),(230,425)],GREEN)
    d.box(130,425,200,70,'NTC ELEMENT',['Txx-A signal / Txx-B return'],GREEN)
    d.line([(230,495),(230,540),(450,540)],INK);d.text(245,557,'SGND at acquisition board',12)
    d.box(580,440,550,122,'EXCITATION SENSE / N4.A2',['EXC_NTC -> protective sense network -> N4.A2','No divider nominally required: EXC_NTC stays within ADC VDD','Use measured Vexc and Vin: Rntc = Rpullup * Vin / (Vexc - Vin)','Configured PGA: +/-4.096 V; analog pins still limited by VDD'],BLUE)
    d.note(601,'SIGNED CONVERSION IMPLEMENTED / PROBE CALIBRATION REQUIRED', 'Firmware uses signed ADS1115 counts and measured N4.A2 excitation. Invalid excitation removes all NTC readings. Short/open and stale checks precede conversion; actual probe curves and settling still need validation.')
    d.text(40,700,'Existing beta profiles are provisional: IAT R25=10k/B3435; coolant R80=2.50k/B3977. Verify actual probe tables.',12,RED)


def rtd(d):
    d.start('PT1000 wiring - MAX31865 replaces current sources', 'Selected board: Adafruit #3648 PT1000 version, with 4300 ohm reference resistor; NOT the PT100 version')
    d.box(40,155,320,160,'TWO-WIRE BASELINE',['Retains the previous two-wire harness','One isolated PT1000 per board','Lead A -> RTD+; lead B -> RTD-','Bridge F+ to RTD+ on the board','Bridge F- to RTD- on the board'],GREEN)
    d.box(530,155,360,160,'MAX31865 SENSOR TERMINALS',[],BLUE)
    d.text(550,199,'F+',11);d.text(550,285,'F-',11)
    d.text(775,199,'RTD+',11);d.text(775,285,'RTD-',11)
    d.line([(580,207),(755,207),(755,231)],GREEN)
    d.line([(580,293),(755,293),(755,266)],GREEN)
    d.text(600,185,'Board jumper',10,DIM)
    d.text(600,300,'Board jumper',10,DIM)
    d.box(690,231,165,35,'PT1000',[],GREEN)
    d.line([(360,230),(530,230)],GREEN)
    d.box(940,155,244,160,'LOGIC / POWER',['VIN -> +3V3_P','GND -> logic GND','SDI11 / SDO12 / SCK13','Unique CS: sheet 09','RDY / 3Vo unused'],BLUE)
    d.box(40,375,550,165,'OPTIONAL FOUR-WIRE HARNESS',['Preferred where probe packaging supports it.','Two independent leads from element end A -> F+ and RTD+.','Two independent leads from end B -> F- and RTD-.','Use the board default four-wire jumper arrangement.','No sense/force shorts at the converter for four-wire operation.','Requires four conductors and a matching connector schedule.'],GREEN)
    d.box(630,375,554,165,'THREE-WIRE ALTERNATIVE',['Equal-resistance paired leads -> F+ and RTD+.','Single opposite-end lead -> RTD-; bridge F- to RTD-.','Set the board-specific three-wire selector per Adafruit guide.','Configure MAX31865 three-wire compensation in firmware.','Do not infer wire function solely from insulation color.','Use matching lead lengths/gauges for compensation.'],GREEN)
    d.note(585,'DO NOT CONNECT RTD MINUS TO SGND OR ADD THE OLD 500 uA EXCITATION', 'Sensor current and resistance-ratio measurement belong to the MAX31865. Firmware uses R0=1000 ohm, Rref=4300 ohm, configured lead mode, fault detection and CVD conversion. Two-wire lead error remains.')
    d.text(40,692,'Baseline CSV uses two wires. Four-/three-wire choices require explicit harness revision; shields are separate conductors.',12)


def ntc_map(d,sensors):
    d.start('NTC channel-by-channel harness schedule', 'Stable sensor IDs retained / board names N0-N4 are new Rev B assignments')
    rows=[]
    for sid in NTC_IDS:
        s=sensors[sid];board,bus,addr,_,ain,ret=allocation(s)
        rows.append([sid,s['key'],board,f'{bus} {addr}',ain,'2.49k' if s['technology']=='coolant_ntc' else '10k',f'T{sid:02d}-A / T{sid:02d}-B'])
    d.table(40,150,[45,275,65,150,70,100,439],['ID','Sensor','Board','I2C bus/address','Input','Pull-up','Harness signal / SGND return'],rows,27,11)
    d.text(40,680,'N4.A2 = EXC_NTC sense (internal wire, no new temperature ID). N4.A3 = spare, unconnected and not sampled.',12,BLUE)
    d.text(40,706,'A/B are harness net names, not vendor pin numbers. Protect and filter every exposed NTC signal at enclosure entry.',12)


def rtd_map(d,sensors):
    d.start('RTD harness, unused inputs and board quantities', 'Seven independent converters / no PT1000 connected to any ADS1115 channel')
    rows=[]
    for sid in RTD_IDS:
        s=sensors[sid];board,_,_,cs,_,_=allocation(s)
        rows.append([sid,s['key'],board,cs,f'T{sid:02d}-A -> RTD+',f'T{sid:02d}-B -> RTD-'])
    d.table(40,150,[45,310,65,70,327,327],['ID','Sensor','Board','CS pin','Element end A','Element end B'],rows,35,12)
    d.box(40,470,550,180,'BASELINE BOARD ORDER',['5 x Adafruit ADS1115 #1085','7 x Adafruit MAX31865 PT1000 #3648','4 x Adafruit MAX31856 #3263 (retained)','1 x dedicated Teensy 4.1 (retained)','1 x 3.3 V-compatible CAN transceiver (TBD)','Power/NTC conditioning/connector hardware: still required'],GREEN)
    d.box(630,470,554,180,'RESERVED IS NOT FITTED',['IDs 30/31: CHRA PT1000 probes remain disabled.','No R7/R8 boards or CS pins allocated for these probes.','ID32: reserved, no physical input.','N4.A3 spare is not a direct PT1000 expansion input.','Two-wire baseline: install both force/sense bridges.','RTD B wire is NOT an SGND harness connection.'],RED)
    d.text(40,699,'Purchase links and manufacturer pin/jumper references are listed on sheet 10 and in docs/thermal_wiring.md.',12,DIM)


def release(d):
    d.start('Commissioning boundary and source references', 'Acquisition implemented / wiring and sensor calibration still require physical bench validation')
    d.box(40,148,550,207,'IMPLEMENTED ACQUISITION / CONFIG 2.0.0',['Two-bus ADS1115: 100 kHz I2C / +/-4.096 V / 860 SPS.','Seven MAX31865: 10 ms bias + fault cycle + 66 ms wait.','New channel/CS map; all eleven selects initialize high.','NTC signed conversion + measured N4.A2 excitation.','PT1000 ratio, CVD equation and front-end fault decoding.','750 ms stale boundary; two fresh samples for recovery.','TC asynchronous single shots / requested 5 Hz cadence.','Native fault tests + Teensy compile; bench tests still required.'],RED)
    d.box(630,148,554,207,'BENCH AND HARNESS CHECKS',['Check supply polarity, regulator loading and USB/VIN isolation.','Verify every address and CS with one board at a time.','Check each probe identity using known resistances/TC simulator.','Check N4.A2 excitation reading against a calibrated meter.','Test open, short, board disconnect and stuck-bus behavior.','Check simultaneous sampling load and maximum channel age.','Verify shield bonding, transient protection and fault current paths.','Keep independent ECU temperature sensors connected.'],GREEN)
    refs=[('ADS1115 board / purchase','https://www.adafruit.com/product/1085'),
          ('ADS1115 electrical / conversion limits','https://www.ti.com/lit/ds/symlink/ads1115.pdf'),
          ('MAX31865 PT1000 board / purchase','https://www.adafruit.com/product/3648'),
          ('MAX31865 terminal jumpers','https://learn.adafruit.com/adafruit-max31865-rtd-pt100-amplifier/rtd-wiring-config'),
          ('MAX31865 logic pinouts','https://learn.adafruit.com/adafruit-max31865-rtd-pt100-amplifier/pinouts'),
          ('Teensy I2C ports / pins','https://www.pjrc.com/teensy/td_libs_Wire.html'),
          ('MAX31856 logic and sensor terminals','https://learn.adafruit.com/adafruit-max31856-thermocouple-amplifier/pinouts'),
          ('Teensy pin card / CAN1','https://www.pjrc.com/teensy/card11a_rev4_web.pdf')]
    for i,(label,url) in enumerate(refs):
        y=395+i*36;d.text(40,y,label,11,BLUE,True);d.text(335,y,url,10,DIM)
        d.c.linkURL(url,(40,792-y-18,1184,792-y+2),relative=0)
    d.text(40,707,'Exact probe curves, connector cavities, NTC protection/RC values, power parts and CAN module are still engineering holds.',12,RED)


def render(Drawing,tc,root,source):
    config=json.loads((root/'config/thermal_system.json').read_text())
    hardware=config['acquisition']
    assert hardware['spi']==dict(mosi=11,miso=12,sck=13,tc_cs=[10,9,8,7],rtd_cs=RTD_CS)
    assert hardware['max31865']['lead_wires']==[2]*7, 'Update diagrams for changed lead mode'
    assert hardware['max31865']['reference_ohm']==4300
    assert hardware['ads1115']['excitation_channel']==18
    for index, board in enumerate(hardware['ads1115']['boards']):
        _,bus,sda,scl,address,_=ADCS[index]
        assert board==dict(bus=0 if bus=='Wire' else 1,sda=sda,scl=scl,address=int(address,16))
    assert len(hardware['ads1115']['boards'])==5
    for sensor in source:
        sid=sensor['id']
        expected=('none',0) if not sensor['enabled'] else (
            ('max31856',sid-1) if sid<=4 else
            ('max31865',RTD_IDS.index(sid)) if sid in RTD_IDS else ('ads1115',NTC_IDS.index(sid)))
        if sensor['enabled']:
            assert (sensor['source']['bus'],sensor['source']['channel'])==expected
        else:
            assert sensor['source']['bus']=='none'
    sensors={s['id']:s for s in source}
    assert set(NTC_IDS)=={s['id'] for s in source if s['enabled'] and 'ntc' in s['technology']}
    assert set(RTD_IDS)=={s['id'] for s in source if s['enabled'] and s['technology']=='pt1000'}
    pins=[11,12,13,18,19,17,16,22,23,10,9,8,7]+RTD_CS
    assert len(pins)==len(set(pins)), 'Pin conflict'
    assert len({(b[1],b[4]) for b in ADCS})==5
    assert len({allocation(s)[:5] for s in source if s['enabled']})==29
    out=root/'output'/'pdf';out.mkdir(parents=True,exist_ok=True)
    d=Drawing(out/'albatross-thermal-wiring.pdf')
    overview(d);power(d);spi(d);tc(d);i2c(d);ntc(d);rtd(d);ntc_map(d,sensors);rtd_map(d,sensors);release(d)
    assert d.page==10
    d.save()
    with (out/'thermal-sensor-wire-schedule.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f)
        w.writerow(['revision','sensor_id','sensor_key','enabled','technology','location','frontend','bus','i2c_address','chip_select_teensy','signal_terminal','return_terminal','signal_net','return_net','lead_mode','status'])
        for s in source:
            board,bus,addr,cs,sig,ret=allocation(s);on=s['enabled'];sid=s['id']
            w.writerow(['C',sid,s['key'],on,s['technology'],s['location'],board,bus,addr,cs,sig,ret,f'T{sid:02d}-'+('K+' if sid<=4 else 'A') if on else '',f'T{sid:02d}-'+('K-' if sid<=4 else 'B') if on else '', '2-wire' if sid in RTD_IDS else '', 'IMPLEMENTED / BENCH VALIDATION REQUIRED' if on else 'DISABLED / NO HARDWARE'])
    print(f'Validated 29 unique sensor assignments, 20 non-conflicting Teensy pins, 5 I2C addresses; wrote {out}')
