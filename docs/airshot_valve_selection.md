# Air Shot proportional valve shortlist and priming plan

Research date: 2026-09-08. Engineering shortlist, not an approved BOM.
Stock, quotations, exact coil variants and application suitability are unverified.

## Five-valve arrangement

One normally closed on/off master supplies four independently controlled,
normally closed proportional metering valves. Electrical PWM can regulate coil
current without making the pneumatic output an on/off pulse train. Use the
manufacturer's driver/current requirements; GPIO duty is not measured opening.

User-proposed distribution, adopted as the planning topology:

```text
tank -> regulator -> master NC -> common distribution manifold
                                  |-- pressure sensor (post-master)
                                  |-- splitter -> intake L / intake R valves
                                  `-- splitter -> turbine L / turbine R valves
```

The first block needs FOUR total ports: one inlet, three outlets. Each subsequent
splitter needs THREE total ports. Port size is not flow capacity: size the master,
regulator, distribution block and hoses for simultaneous aggregate flow. Avoid
making the common fitting the limiting restriction. A short sensor connection
limits measurement lag; specify pressure rating, vibration support and sealing.

The post-master sensor measures the common feed cavity, not pressure beyond the
four metering valves. It cannot identify a blocked individual branch. Do not
assume static pressure proves regulator delivery under flow. Log pressure sag.
Closing a two-port NC master traps air downstream; PRIMED NO must never mean
safe to service. Provide a separately engineered manual depressurization/bleed
procedure. Do not discharge trapped air through engine-facing valves for service.
Any automatic dump addition must be separately specified, not silently assumed
within this five-valve design. Protect turbine branches against hot reverse flow.

## HUD implementation and remaining firmware work

The main Air Shot tile now has PRIMED and COMP cells, with extra height and the
existing inverted FIRING badge preserved. COMP ON CMD is a controller relay
command, not verified compressor rotation/air delivery; WAIT means restart
cooldown, OFF means command off, FAULT means reported fault, -- means stale.

CAN 0x245 extension v1 now reports controller-qualified priming separately from
physical closure quality. Legacy frames only support command/unverified display.
PRIMED SETUP = uncommissioned; PRIMING = filling/stabilizing; PRIMED = fresh
post-master pressure qualified by the main controller; PRIME FAULT = latched
timeout or pressure loss; ? = legacy open command without pressure proof;
NO = not commanded open; -- = stale/unavailable. None proves safe depressurization.

The controller now implements the following sequence, with commissioning still
required before hardware can energize:
request/permissions -> four metering commands zero -> master open -> valid
post-master pressure stable within commissioned limits -> primed -> metering.
Loss of permission/fault/reset revokes readiness and isolates. Valid low pressure
is accepted while initially filling; invalid/stale pressure is not. A fill timeout
or pressure fall below the usable limits after priming latches master closed until
OFF is selected. No automatic repeated retries. OFF is an acknowledgement, not a
repair; remaining faults still inhibit subsequent arming.

Sensor choice, conditioned ADC input (or real CAN publisher), range, validity,
minimum/maximum pressure, stability time, fill timeout and recovery hysteresis
remain hardware commissioning requirements, not guessed calibrations. Stable and
fill-timeout durations, tank rearm pressure and sensor-location verification are
in config/fault_manager.json under master_air_isolation.precharge. Generate with
tools/generate_fault_config.py; runtime checks require rearm above min_tank and no
higher than full_tank. Existing regulated pressure input 0x193
may serve this role only after the sensor location and publisher are explicitly
commissioned; a sensor upstream of the master cannot prove post-master pressure.
Readiness must require fresh pressure and controller permission, not solely a
historically high pressure value. Keep manifold pressure distinct from firing
eligibility and from verified master closure. The production IO always gates
live metering on primed; shadow predictions remain possible without energizing
the master. Direct controller test fixtures may explicitly omit this IO
requirement. No shot request is queued across priming: release/repress FIRE after
readiness, or wait for a new AUTO trigger.

Precharge does not require launch RPM, gear, rider torque, an active WMI spray,
or current spool demand. It does require a running/noncranking engine, healthy
DBW/dynamics/driver/pressure/thermal/WG data, thermal warm-up and upper limits,
no WMI fault, no TCS/AWC intervention, no overboost/ECU protection, and the selected
mode's Air Shot capability. Relevant fault-manager CLOSE_AIR/ISOLATE_AIR actions
close the master. Pi/weather-only faults do not become new engine-critical
dependencies. All normal shot-specific checks remain in force before metering.
Shadow/configuration/engine-off operation never precharges. A tank rearm margin
avoids cycling around min_tank. The master stays open across shots while healthy.

## Shortlist

Numbers are manufacturer conditions, not comparable installed-flow guarantees.
Kv (water m3/h at 1 bar drop) is NOT air L/min. Do not combine a family's maximum
orifice with its maximum pressure rating. Request gas-flow curves at actual
upstream/downstream absolute pressures and temperature.

| Family | Published capability | Assessment for this build |
| --- | --- | --- |
| Parker VSO MAX HP | Model 2: 200 SLPM at 45 psi; 0-120 psi operating; typical 10 ms response; 5/12/24 V coils, ~2 W | Strong compact first enquiry. NC two-port; 5-55 C environment and pressure-dependent flow require review. Model 4 is a different lower-pressure selection, not interchangeable. [Datasheet](https://www.parker.com/content/dam/Parker-com/Literature/Precision-Fluidics/Miniature-Proportional-Valves/VSOMAX_Data.pdf) |
| Burkert 2875 | NC two-port, 2-9.5 mm; Kv 0.12-1.4; standard 4 mm version Kv .45, nominal 8 bar and listed max differential 4 bar; high-differential variants separately listed | Strong industrial candidate. Larger variants lose pressure capability. Confirm response, current driver and exact pressure curve. [Datasheet](https://www.burkert.com/en/Media/plm/DTS/DS/ds2875-standard-eu-en.pdf) |
| Burkert 2865 | Direct-acting basic proportional family; manufacturer lists a 2 mm 24 V normally closed version | Secondary quote alternative to 2875; do not assume identical hysteresis/flow. [Product](https://www.burkert.com/en/products/solenoid-control-valves/general-purpose-solenoid-control-valves/291478) |
| Burkert 2836 | NC two-port; 6 mm Kv .9 / nominal 8 bar; 8 mm Kv 1.5 / 5 bar; 12 mm Kv 2.5 / 2 bar; about 4 kg brass | High-flow but very heavy: four brass units alone about 16 kg. Check proportional differential limits with supplier. [Datasheet](https://www.burkert.com/en/Media/plm/DTS/DS/ds2836-standard-eu-en.pdf) |
| Burkert 6024 | NC, Kv 1.4-2.8, listed differential .7/.4/.2 bar for 8/10/12 mm | Low-differential niche, not a direct high-pressure replacement. [Datasheet](https://www.burkert.com/en/Media/plm/DTS/DS/ds6024-standard-eu-en.pdf) |
| ASCO 209 | Kv .02-.26; manufacturer advertises <=15 ms response | Worth a compact-valve quote; match orifice, pressure, coil and actual compressed-air flow. [Product](https://discreteautomation.emerson.com/product/asco-209), [response specification](https://www.emerson.com/en/corporate/news/2022/22-12-new-asco-series-209-proportional-flow-control-valves) |
| ASCO 202 Posiflow | Air-rated direct-acting choices; larger Cv options have lower pressure differentials | Quote only the air/inert-gas variant. The linked 8203 high-flow table is WATER/LIGHT OIL, so do not select its Cv 2.4 option for air. [Manufacturer catalog](https://discreteautomation.emerson.com/sfsites/c/cms/delivery/media/MCANWTMJWQL5B6NHALKOBSXALAFA?v=1000) |
| Humphrey ProControl PC30 | Typical max 225 SLPM, configuration dependent; 25/50/100 psi settings; 5.8 W rated, 7.7 W max; 0-52 C ambient | Strong alternative enquiry. Ask factory for exact flow/response and pressure calibration. [Datasheet](https://dpk3n3gg92jwt.cloudfront.net/domains/humphrey/pdf/PC30.pdf) |
| Humphrey Servoid | NC two-port; up to 200 SLPM at 11 psi; balanced design | Particularly interesting if lower regulated pressure suffices; confirm operating-pressure limits and response. [Manufacturer](https://www.humphrey-products.com/product-categories/proportional-valves) |
| Clippard DVP | Two-way proportional, published flows over 60 L/min | Lower-flow fallback/trim candidate, not automatically large enough for assist. [Manufacturer](https://www.clippard.com/products/electronic-valve-proportional-dvp) |
| Festo VPCF | 1000/1500 L/min range; 24 V, max 36 W, 856 g; 3-way with exhaust | High-flow research option, NOT a drop-in NC two-port. Below minimum setpoint it exhausts; has internal consumption and 15-35 C medium range. Backflow and loss-of-power port behavior are gating questions. [Datasheet](https://ftp.festo.com/Public/PNEUMATIC/SOFTWARE_SERVICE/Documentation/2024/EN/VPCF_EN.PDF) |
| Norgren VP60 | 1200 L/min at p1 90/p2 75 psi; 3 ms dead time + 5 ms 10-90% rise at specified free-exhaust test; 24 V | Fast high-flow 5/3 spool, NOT four independent NC channels. Center leakage and exhaust paths conflict with simple primed isolation. Needs manufacturer-supported architecture, not casual port plugging. [Datasheet](https://cdn.norgren.com/pdf/VP60%205_3%20Proportional%20flow%20control%20valve.pdf) |

Adjacent technologies: [Festo VEMD](https://media.festo.com/media/232788_documentation.pdf)
now includes 100/200 L/min versions in its selection guide (older 20 L/min data
does not cover the whole family). It is a mass-flow controller; obtain exact
step/settling response. [SMC VEF](https://www.smcworld.com/catalog/BEST-5-5-en/mpv/5-p0886-0891-vefvep_en/data/5-p0886-0891-vefvep_en.pdf)
is another flow-control family for supplier review, not yet sized here.
[HOERBIGER Tecno plus](https://www.hoerbiger.com/en/products-and-services/flow-motion-control/tecno-piezo-proportional-valve.html)
is a pressure regulator, not an equivalent metering valve. Keep pressure-control
and flow-control alternatives separate. Burkert 6223 is not shortlisted for air:
the manufacturer's proportional overview lists neutral liquids.

## Recommendation and supplier enquiry

Start with Parker VSO MAX HP, Burkert 2875, Humphrey PC30/Servoid and ASCO 209/202.
Escalate to high-flow spool hardware only if sizing rules out simple two-port
devices. Paying more does not remove leakage, exhaust, temperature or power limits.
No quoted unit prices or verified stock were obtained; request four-unit pricing,
driver/connectors, sample availability and lead times separately.

Provide suppliers: compressed air, desired four independent channels, simultaneous
flow, regulator dynamic range, downstream plenum/exhaust pressure envelopes,
temperature range, target mass flow versus time, longest hold, duty cycle, hose
volumes, vibration/water exposure, supply voltage, and normally closed preference.
Ask for opening and closing/settling time versus pressure and temperature,
minimum controllable flow, hysteresis, leakage, reverse-pressure tolerance,
driver/dither requirements, continuous-duty rating, and safe power-loss behavior.

Select a master for aggregate flow and emergency closing response, not just
precharge speed. A slow closing master still compromises isolation. Commission
one instrumented branch before buying four valves. No final pressure/flow/latency
thresholds have been invented or enabled by this research/UI change.
