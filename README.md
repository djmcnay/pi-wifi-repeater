# PI WiFi Repeater

South Africa region VPN WiFi repeater for Raspberry Pi Zero 2W.

## Purpose

A Pi Zero 2W creates a dedicated WiFi SSID that routes through NordVPN's South Africa servers. Useful for region-locked streaming (projectors, TVs, etc).

## Hardware

- Raspberry Pi Zero 2W
- USB WiFi dongle (BrosTrend AX900 or similar) - downstream AP
- Built-in `wlan0` - upstream connection to home router
- USB dongle `wlan1` - downstream AP broadcasting `SA-VPN`

## Quick Setup

### 1. Flash SD Card

Use Raspberry Pi Imager:
- OS: Raspberry Pi OS Lite (32-bit)
- Enable SSH
- Configure WiFi: your home SSID
- Set hostname/username/password

### 2. First Boot

Insert SD, power on, find IP on your router, SSH in.

### 3. Run Setup

```bash
curl -sSL https://raw.githubusercontent.com/djmcnay/pi-wifi-repeater/main/scripts/install.sh | bash
```

Or manually:

```bash
# Get the code
git clone https://github.com/djmcnay/pi-wifi-repeater.git
cd pi-wifi-repeater

# Run setup
sudo python3 scripts/setup.py
```

## Development (Mac)

```bash
# On your Mac
cd ~/Documents/GitHub/pi-wifi-repeater
uv sync --extra dev
uv run pi-wifi-repeater --help
```
