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

Automatic rebooting is delegated to the root-owned
`albatross-update-reboot.path` unit. Install and enable the two reboot watcher
units during Pi deployment:

```sh
sudo cp deploy/albatross-update-reboot.service /etc/systemd/system/
sudo cp deploy/albatross-update-reboot.path /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now albatross-update-reboot.path
```

This path updates the Pi application only. Continue using a USB update bundle
when a Teensy firmware image must be installed at the same time.

Environment overrides:

- `ALBATROSS_GITHUB_REMOTE`: Git remote name, default `origin`.
- `ALBATROSS_GITHUB_BRANCH`: branch to follow, default `main`.
- `ALBATROSS_SKIP_REBOOT`: set to any value to block automatic Pi reboot.

Private repositories must already be accessible through the Pi user's Git
credentials or SSH configuration.

## Diagnosing online-update installation problems

Run from the installed HUD folder, using the same Python environment and OS user
as the HUD service:

```sh
python3 tools/install_update.py --diagnose
```

This prints the actual application directory and checks Git locally. It does
not fetch, install, flash firmware, reboot, initialize a repository, or alter
Git's ownership/trust settings. ZIP/COPY INSTALL means the Git history is
missing. Other results distinguish missing Git, ownership/access failures,
an invalid HEAD, a missing remote, and an unrelated parent repository.
Git worktrees with a .git file are supported.

### Migrating a ZIP installation

GitHub ZIP downloads and Pi update bundles intentionally omit .git.
Extracting a ZIP can run the HUD, but cannot use fast-forward Git updates.
A USB app overlay does not turn a ZIP installation into a clone.

With the engine off and stable power:

1. Back up the existing installation and leave that folder intact.
2. Install Git if needed (`sudo apt install git` on Raspberry Pi OS).
3. As the HUD service user (not root), clone into a NEW, unused sibling folder:
   `git clone https://github.com/JDMarc/albatross.git ~/albatross-git`.
4. Preserve settings/, logs/, and maps/ as needed. Review differences in config/
   and any modified code before transferring them. Do not blindly replace new
   engineering configuration with old files. Do not copy an old updates/ folder,
   pending rollback markers, or virtual environment into the new clone.
5. Install the application's dependencies for the new folder. Run its
   `tools/install_update.py --diagnose` as the service user.
6. Stop the HUD service and update BOTH WorkingDirectory and the script path
   in ExecStart to the new absolute path (and the new interpreter if using a
   virtual environment). Check User and desktop environment paths too.
   Run `sudo systemctl daemon-reload`, then restart the service.
7. Verify the new HUD, settings, CAN connections and POST before using ONLINE
   UPDATE. Retain the old folder until the new installation is proven.

The supplied service template uses /home/albatross/albatross and User=albatross;
your installed service may differ. Inspect it with
`systemctl cat albatross-hud.service` before editing. An interactive clone owned
by one user can fail when the service runs as another. Do not solve that by
globally trusting every Git directory or running the HUD as root.

Do not use git init/reset --hard inside the ZIP directory as a shortcut: the
updater cannot distinguish your edits from archive contents without history.
After migration, tracked local calibration/code changes will correctly block
online updates with LOCAL CHANGES; reconcile those explicitly rather than
discarding them.

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
