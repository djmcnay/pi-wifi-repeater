#!/bin/bash
# One-liner install script for PI WiFi Repeater
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
echo "Running setup..."
sudo python3 scripts/setup.py
