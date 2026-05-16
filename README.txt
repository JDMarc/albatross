Hello All,

This my major project, which has been active for years, ever since I bought my bike.
A 1982 Honda GL500, which is exactly what this "albatross" project is for.
In essence, we are building a twin turbocharged motorcycle in homage to the 80s and the cx500 turbo as a whole, 
this is done through liberal fault correction and tuning options controlled by 3 main systems, those being:
- RASPBERRY PI -
 - Controls and drives the digital dash, which I often refer to as the "HUD"

Albatross Pi HUD + Control Scaffold
===================================

The Pi side is the coordinator and display brain for the project. It receives live CAN telemetry,
renders an 80s-inspired HUD with modern safety overlays, and sends supervisory requests back to
the control layers when we need to derate, limp, or synchronize mode state.

What this repo is trying to accomplish
--------------------------------------

At a practical level, this repository exists to do four things reliably:

1) **Render a useful rider HUD at speed**
   - Fast Pygame rendering with a consistent layout and scalable resolution.
   - Priority status/warning indicators that are visible under stress.

2) **Decode and normalize CAN data into one coherent state**
   - ECU + Arduino frames are merged into a single `StateSnapshot` model.
   - HUD code reads that snapshot instead of dealing with raw frame parsing.

3) **Enforce safe supervisory behavior**
   - Detect key out-of-bounds conditions and request conservative actions.
   - Keep the UI and outbound requests in sync during fault transitions.

4) **Stay testable during long development cycles**
   - Works in simulator/demo mode for desktop iteration.
   - Works in live CAN mode on Pi hardware with SocketCAN.

System roles (quick memory aid for me)
--------------------------------------

This is the short version I want to remember when I revisit after a break:

- **Raspberry Pi (this repo)**
  - Runs HUD, handles top-level state presentation, and sends high-level requests.
  - Supervises and coordinates behavior; does not try to be hard real-time torque control.

- **Arduino controller**
  - Handles actuator-facing logic and publishes supervisory status.
  - Owns wheel speed / traction plumbing and mode-aware actuator controls.

- **MS3Pro Mini ECU**
  - Owns core engine management, primary telemetry, and ECU-side strategy.
  - Receives selected control intents/limits from the network.



- **Arduino Mega 2560 controller (`arduino/albatross_controller`)**
  - Runs dual electronic wastegate actuator outputs (`PWM/DIR/EN` per channel).
  - Manages Air Shot compressor + shot latch/rearm logic.
  - Computes wheel speed + slip, accepts Pi traction level command (`0x124`), and publishes torque-reduction request (`0x125`) for ECU cooperation.
  - Enforces WMI/flame interlocks and limp-aware behavior.

Arduino firmware notes (important)
----------------------------------

The Arduino code is not just placeholder code; it is part of the active control stack.
Current sketch target is **Arduino Mega 2560 Rev3** with an MCP2515 CAN interface.

Quick references:

- Main sketch: `arduino/albatross_controller/albatross_controller.ino`
- Arduino details/tuning notes: `arduino/README.md`

What Arduino currently publishes for the HUD/stack:

- Air Shot status (`0x130`)
- AWC/lean status (`0x131`)
- Tank pressure (`0x133`)
- Twin turbo feedback (`0x134`)
- Wastegate status (`0x135`)
- Gear + wheel speed/fuel support frames (`0x136`–`0x138`)

Bring-up reminder for this repo architecture:

1) Flash Arduino sketch and verify CAN traffic exists first.
2) Confirm Pi receives expected IDs on `can0`.
3) Then validate HUD rendering/state transitions.

Repository layout
-----------------

- `main.py`  
  Flexible development entrypoint (desktop/demo/snapshot/live-CAN capable).

- `pi_main.py`  
  Pi-focused launcher used for deployment/autostart defaults.

- `albatross_pi/canbus/`  
  CAN IDs, frame encode/decode, and `CANStateAggregator`.

- `albatross_pi/hud/`  
  Renderer + HUD widgets.

- `albatross_pi/state/`  
  Snapshot dataclasses and simulator.

- `deploy/albatross-hud.service`  
  Example systemd unit for power-on auto-launch on Raspberry Pi.

- `docs/`  
  Project spec and ECU setup notes.

Running the project
-------------------

Desktop / demo iteration:

```
python main.py --width 1280 --height 480
```

Live CAN mode (SocketCAN):

```
python main.py --can-interface can0 --width 1280 --height 480
```

Pi-focused launch path (recommended on hardware):

```
python pi_main.py --can-interface can0 --width 1280 --height 480
```

Headless screenshot capture:

```
python main.py --width 1920 --height 720 --snapshot docs/assets/hud_demo.png
```

Power-on autostart on Raspberry Pi (systemd)
--------------------------------------------

1. Copy service template:

```
sudo cp deploy/albatross-hud.service /etc/systemd/system/albatross-hud.service
```

2. Edit user/path/flags for your install:

```
sudo nano /etc/systemd/system/albatross-hud.service
```

3. Enable and start:

```
sudo systemctl daemon-reload
sudo systemctl enable albatross-hud.service
sudo systemctl start albatross-hud.service
```

4. Verify:

```
systemctl status albatross-hud.service
journalctl -u albatross-hud.service -f
```

Notes I want to remember
------------------------

- `python-can` must be installed on Pi for SocketCAN mode.
- `can0` must be configured and up before expecting live telemetry.
- If CAN is quiet at startup, HUD can still boot, but safety/fault behavior depends on incoming data quality.
- Keep `main.py` for flexible dev/testing; keep `pi_main.py` as deployment entrypoint.

Advice for others porting this to their own build
-------------------------------------------------

If you are adapting this to a different bike/car/ECU stack:

1) **Start with your CAN map first**
   - Update IDs/scaling in `albatross_pi/canbus/ids.py` and decode paths.
   - Mirror those changes in your controller firmware map (Arduino/other MCU) so both sides agree.
   - Validate with logged sample frames before touching UI styling.

2) **Define your safety contract early**
   - Decide what conditions trigger limp/derate and what exact outbound actions happen.
   - Keep those rules centralized and auditable.

3) **Separate demo and deployment entrypoints**
   - You will want different defaults for desktop iteration vs vehicle boot.
   - Keep your autostart path boring and explicit.

4) **Design UI around glanceability, not density**
   - Prioritize warning hierarchy and readability over showing every metric at once.

5) **Treat this as supervisory, not absolute authority**
   - Hard real-time controls should remain in dedicated controller/ECU layers.
   - Let the Pi coordinate, visualize, and request safe limits.

6) **Log aggressively during integration**
   - Bring-up is mostly about proving assumptions wrong safely.
   - Keep a reproducible test loop: capture frames -> replay -> verify state -> verify actions.

MS3Pro-specific setup details are in `docs/ms3_tunerstudio_setup.md`.
Full project vision/spec notes are in `docs/albatross_pi_spec.md`.
