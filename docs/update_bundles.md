# Albatross Update Bundles

Updates are installed from a USB drive through the HUD Settings menu item `INSTALL UPDATE`, from the latest repository commit through `ONLINE UPDATE`, or from a terminal:

```powershell
py -3.12 tools\install_update.py --bundle C:\path\to\albatross_update_2026_05_19.zip
```

The updater searches the connected USB drive for the newest `albatross_update*.zip` or unpacked `albatross_update*/manifest.json` bundle. You can force a bundle with `ALBATROSS_UPDATE_BUNDLE`.

## Online Updates From The Repository

The HUD Settings item `ONLINE UPDATE` fetches the configured Git remote and
branch, then compares the installed commit with the newest branch commit.
The defaults are `origin` and `main`, which track the latest state of
`JDMarc/albatross`. If both commits match, the HUD reports `UP TO DATE`.

When the remote has a newer commit, the updater requires a clean tracked
worktree and fast-forward-only history. It backs up the current application,
applies the fetched commit, writes the existing health-check and rollback
markers, and reboots automatically on a Raspberry Pi. A dirty worktree, local
commits ahead of the remote, or divergent history is reported without
overwriting anything.

This path updates the Pi application only. Continue using a USB update bundle
when a Teensy firmware image must be installed at the same time.

Environment overrides:

- `ALBATROSS_GITHUB_REMOTE`: Git remote name, default `origin`.
- `ALBATROSS_GITHUB_BRANCH`: branch to follow, default `main`.
- `ALBATROSS_SKIP_REBOOT`: set to any value to block automatic Pi reboot.

Private repositories must already be accessible through the Pi user's Git
credentials or SSH configuration.

## Build A Pi Update Bundle

From the repo root:

```powershell
py -3.12 tools\make_update_bundle.py
```

That creates:

```text
dist/albatross_update_VERSION.zip
```

To include a prebuilt Teensy 4.1 controller firmware image:

```powershell
py -3.12 tools\make_update_bundle.py --arduino-hex C:\path\to\albatross_controller_teensy41.hex
```

Useful options:

```powershell
py -3.12 tools\make_update_bundle.py --version test_001 --output-dir E:\
py -3.12 tools\make_update_bundle.py --arduino-hex build\albatross_controller_teensy41.hex --arduino-port /dev/ttyACM0
```

The packager excludes local/runtime files such as `.git`, `.venv`, `logs`, `maps`, `settings`, `updates`, caches, and compiled Python files. It writes SHA-256 hashes into the manifest automatically.

## Bundle Layout

```text
albatross_update_2026_05_19.zip
  manifest.json
  pi/
    app.zip
  controller/
    albatross_controller_teensy41.hex
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
    "hex": "controller/albatross_controller_teensy41.hex",
    "fqbn": "teensy:avr:teensy41",
    "baud": 115200
  },
  "sha256": {
    "pi/app.zip": "optional_app_archive_sha256",
    "controller/albatross_controller_teensy41.hex": "optional_hex_sha256"
  }
}
```

The manifest key is still named `arduino` for backward compatibility with older
bundles and updater code, even when the payload targets the Teensy 4.1
controller.

The Pi app archive should contain the repo files to overlay onto the existing install. Runtime folders are preserved and not overwritten: `.git`, `.venv`, `logs`, `maps`, `settings`, `updates`, and `__pycache__`.
If `sha256` entries are present, the installer verifies each referenced payload before changing anything.

## Controller Flashing

The Teensy 4.1 can stay permanently USB-connected to the Pi. The updater flashes
with `arduino-cli upload -i` using the Teensy board package. The old Mega
`avrdude` fallback is retained only when a legacy bundle explicitly sets
`fqbn` to `arduino:avr:mega`.

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
- Online repository updates refuse tracked local changes and non-fast-forward history.
- Pi app updates write `updates/restart_required`; the next service restart or power cycle runs the new app.
- New Pi overlays must keep the HUD alive through POST and 15 seconds of
  runtime. Two unconfirmed starts are permitted; the following launch restores
  the versioned app backup and previous Git commit automatically.
- Controller-only updates do not require a Pi restart.

This is application-level overlay rollback. It is not yet a full A/B
filesystem or OS-image update scheme.
