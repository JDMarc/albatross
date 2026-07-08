# Raspberry Pi Deployment

This is the preferred install path for the Albatross HUD on Raspberry Pi with
the Waveshare 2-CH isolated CAN HAT.

## Recommended Boot Strategy

For first bring-up, use Raspberry Pi OS 64-bit with Desktop so you can debug
the screen, network, and CAN tools easily.

For the bike, move toward Raspberry Pi OS Lite once the display path is proven.
The bundled service targets Raspberry Pi OS Desktop/X11 because it is the
least surprising first bring-up path. SDL's KMS/DRM backend can boot faster on
Lite, but only after the OS image, permissions, and pygame build all support it.

## Install Runtime Packages

```sh
sudo apt update
sudo apt install -y git python3-pip python3-venv python3-pygame python3-can can-utils
python3 -m pip install --break-system-packages pyserial
```

Clone or update the repo at:

```sh
/home/albatross/albatross
```

The service template assumes the Raspberry Pi login user is `albatross`. If
your Pi user is different, edit `User=`, `WorkingDirectory=`, and `ExecStart=`
in `/etc/systemd/system/albatross-hud.service`.

## Waveshare 2-CH CAN HAT Setup

The HAT is not USB-style plug-and-play. It uses two MCP2515 CAN controllers over
SPI, so Raspberry Pi OS needs device-tree overlays before `can0` and `can1`
exist.

Merge this repo fragment into `/boot/firmware/config.txt`:

```sh
sudo nano /boot/firmware/config.txt
```

Add:

```ini
dtparam=spi=on
dtoverlay=mcp2515-can0,oscillator=16000000,interrupt=23
dtoverlay=mcp2515-can1,oscillator=16000000,interrupt=25
```

Those interrupt pins match the Waveshare board defaults: CAN0 interrupt on
GPIO23 and CAN1 interrupt on GPIO25.

Reboot:

```sh
sudo reboot
```

Verify:

```sh
ip link show can0
ip link show can1
dmesg | grep -i mcp
```

## Bring Up CAN

Install the SocketCAN systemd unit:

```sh
sudo cp deploy/can@.service /etc/systemd/system/can@.service
sudo systemctl daemon-reload
sudo systemctl enable can@can0.service
sudo systemctl enable can@can1.service
sudo systemctl start can@can0.service
sudo systemctl start can@can1.service
```

The project default is 500 kbit/s. If the MS3 tune is changed to a different
bitrate, update `deploy/can@.service` before copying it. Some MCP2515 driver
stacks reject `berr-reporting on`, so the service intentionally uses the
widely-supported `bitrate 500000 restart-ms 100` form.

Quick loopback test with only the Pi HAT:

```sh
candump can0
cansend can1 123#11223344
```

For this test only, connect CAN0_H to CAN1_H and CAN0_L to CAN1_L, with correct
termination. For the bike harness, use a trunk with short stubs and exactly two
120 ohm terminators total.

## HUD Autostart

Install the HUD service:

```sh
sudo cp deploy/albatross-hud.service /etc/systemd/system/albatross-hud.service
sudo systemctl daemon-reload
sudo systemctl enable albatross-hud.service
sudo systemctl start albatross-hud.service
```

Check it:

```sh
systemctl status albatross-hud.service
journalctl -u albatross-hud.service -f
```

During first bring-up, stop the service before digging through crashes:

```sh
sudo systemctl stop albatross-hud.service
journalctl -u albatross-hud.service -n 120 --no-pager
```

The service retries failures three times over two minutes, then stops so a bad
HUD build does not trap the Pi in a restart loop.

If the journal says `python-can is required for SocketCAN interaction`, install
the Pi package and restart the HUD:

```sh
sudo apt update
sudo apt install -y python3-can
sudo systemctl restart albatross-hud.service
```

The bundled service uses the Desktop display:

```ini
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/albatross/.Xauthority
Environment=SDL_VIDEODRIVER=x11
ExecStart=/usr/bin/python3 /home/albatross/albatross/pi_main.py --can-interface can0 --width 1920 --height 720
```

For later Raspberry Pi OS Lite testing, try replacing the display environment
with:

```ini
Environment=SDL_VIDEODRIVER=kmsdrm
Environment=SDL_RENDER_DRIVER=opengles2
```

If that reports `kmsdrm not available`, go back to the Desktop/X11 service
until the KMS/DRM stack is installed and accessible.

## Useful Commands

```sh
ip -details link show can0
candump can0
cansend can0 100#07D0
sudo systemctl restart albatross-hud.service
sudo systemctl restart can@can0.service
```
