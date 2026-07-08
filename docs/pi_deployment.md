# Raspberry Pi Deployment

This is the preferred install path for the Albatross HUD on Raspberry Pi with
the Waveshare 2-CH isolated CAN HAT.

## Recommended Boot Strategy

For first bring-up, use Raspberry Pi OS 64-bit with Desktop so you can debug
the screen, network, and CAN tools easily.

For the bike, move toward Raspberry Pi OS Lite and run the HUD from `systemd`
with SDL's KMS/DRM backend. That avoids waiting for the desktop and usually
boots faster.

## Install Runtime Packages

```sh
sudo apt update
sudo apt install -y git python3-pip python3-venv python3-pygame can-utils
python3 -m pip install --break-system-packages python-can pyserial
```

Clone or update the repo at:

```sh
/home/pi/albatross
```

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
bitrate, update `deploy/can@.service` before copying it.

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

The production service uses:

```ini
Environment=SDL_VIDEODRIVER=kmsdrm
Environment=SDL_RENDER_DRIVER=opengles2
ExecStart=/usr/bin/python3 /home/pi/albatross/pi_main.py --can-interface can0 --width 1920 --height 720
```

If the HUD fails to open the display during early bring-up on Desktop, change
the service to:

```ini
Environment=DISPLAY=:0
```

and remove `SDL_VIDEODRIVER=kmsdrm`. That starts later because it depends on the
desktop session, but it is easier to debug.

## Useful Commands

```sh
ip -details link show can0
candump can0
cansend can0 100#07D0
sudo systemctl restart albatross-hud.service
sudo systemctl restart can@can0.service
```
