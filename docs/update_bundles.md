# Albatross Update Bundles

Updates are installed from a USB drive through the HUD Settings menu item `INSTALL UPDATE`, or from a terminal:

```powershell
py -3.12 tools\install_update.py --bundle C:\path\to\albatross_update_2026_05_19.zip
```

The updater searches the connected USB drive for the newest `albatross_update*.zip` or unpacked `albatross_update*/manifest.json` bundle. You can force a bundle with `ALBATROSS_UPDATE_BUNDLE`.

## Build A Pi Update Bundle

From the repo root:

```powershell
py -3.12 tools\make_update_bundle.py
```

That creates:

```text
dist/albatross_update_VERSION.zip
```

To include a prebuilt Arduino firmware image:

```powershell
py -3.12 tools\make_update_bundle.py --arduino-hex C:\path\to\albatross_controller.hex
```

Useful options:

```powershell
py -3.12 tools\make_update_bundle.py --version test_001 --output-dir E:\
py -3.12 tools\make_update_bundle.py --arduino-hex build\albatross_controller.hex --arduino-port /dev/ttyACM0
```

The packager excludes local/runtime files such as `.git`, `.venv`, `logs`, `settings`, `updates`, caches, and compiled Python files. It writes SHA-256 hashes into the manifest automatically.

## Bundle Layout

```text
albatross_update_2026_05_19.zip
  manifest.json
  pi/
    app.zip
  arduino/
    albatross_controller.hex
```

`manifest.json`:

```json
{
  "version": "2026.05.19",
  "requires_engine_off": true,
  "min_battery_voltage": 12.2,
  "pi": {
    "app_archive": "pi/app.zip"
  },
  "arduino": {
    "hex": "arduino/albatross_controller.hex",
    "fqbn": "arduino:avr:mega",
    "baud": 115200
  },
  "sha256": {
    "pi/app.zip": "optional_app_archive_sha256",
    "arduino/albatross_controller.hex": "optional_hex_sha256"
  }
}
```

The Pi app archive should contain the repo files to overlay onto the existing install. Runtime folders are preserved and not overwritten: `.git`, `.venv`, `logs`, `settings`, `updates`, and `__pycache__`.
If `sha256` entries are present, the installer verifies each referenced payload before changing anything.

## Arduino Flashing

The Mega can stay permanently USB-connected to the Pi. The updater flashes with `arduino-cli upload -i` when available, then falls back to `avrdude`.

Port detection checks:

- `ALBATROSS_ARDUINO_PORT`
- `manifest.json` field `arduino.port`
- `/dev/ttyACM*`
- `/dev/ttyUSB*`

## Safety Behavior

- Updates are blocked if `requires_engine_off` is true and RPM is nonzero.
- Updates are blocked when battery voltage is known and below `min_battery_voltage`.
- `settings/` and `logs/` are backed up before install.
- Current app files are backed up before a Pi app overlay.
- Pi app updates write `updates/restart_required`; the next service restart or power cycle runs the new app.
- Arduino-only updates do not require a Pi restart.
