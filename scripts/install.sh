#!/bin/bash
# One-liner install script for PI WiFi Repeater (AP + VPN)
# Usage: curl -sSL https://raw.githubusercontent.com/djmcnay/pi-wifi-repeater/main/scripts/install.sh | bash

set -e

REPO="https://github.com/djmcnay/pi-wifi-repeater.git"
DIR="/tmp/pi-wifi-repeater"

echo "=== PI WiFi Repeater Installer ==="
echo "Cloning repo..."
rm -rf "$DIR"
git clone "$REPO" "$DIR"
cd "$DIR"

echo ""
echo "=== Step 1: WiFi Repeater (AP) ==="
sudo python3 scripts/setup.py

echo ""
echo "=== Step 2: NordVPN (South Africa) ==="
echo "Get your NordVPN token at: https://my.nordaccount.com/dashboard/nordvpn/"
echo "Then run:"
echo "  export NORDVPN_TOKEN=your_token"
echo "  sudo python3 scripts/setup_vpn.py --token \$NORDVPN_TOKEN"
