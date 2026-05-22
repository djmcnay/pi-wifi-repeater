#!/bin/bash
# Install AIC8800 driver for BrosTrend AX900 / AX7L on Raspberry Pi
# Uses DKMS source from BrosTrend .deb package

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIVER_SRC="$SCRIPT_DIR/drivers/aic8800"
FIRMWARE_SRC="$SCRIPT_DIR/firmware/aic8800DC"

echo "=== AIC8800 Driver Installer ==="
echo "Target: BrosTrend AX900 / AX7L (a69c:5723)"
echo ""

if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Must run as root (sudo)"
    exit 1
fi

# Step 1: Prep system
echo "[1/6] Installing build dependencies..."
apt-get update
apt-get install -y build-essential dkms eject linux-headers-$(uname -r) || true

# Step 2: USB mode switch — eject CDROM mode to expose WiFi
echo ""
echo "[2/6] Switching USB dongle from storage to WiFi mode..."
# Try udisksctl eject first, then sg_start, then usb_modeswitch
if command -v udisksctl >/dev/null; then
    for dev in /dev/sr0 /dev/sr1; do
        if [ -e "$dev" ]; then
            udisksctl unmount -b "$dev" 2>/dev/null || true
            sleep 0.5
        fi
    done
fi

# usb_modeswitch with Huawei-style message (script expects this)
if command -v usb_modeswitch >/dev/null; then
    usb_modeswitch -KQ -v a69c -p 5723 2>/dev/null || true
fi

sleep 2
current_id=$(lsusb | grep a69c | awk '{print $6}' || true)
echo "  Current USB ID: $current_id"

# Step 3: Install firmware
echo ""
echo "[3/6] Installing firmware..."
mkdir -p /lib/firmware/aic8800DC
cp "$FIRMWARE_SRC"/* /lib/firmware/aic8800DC/
echo "  Firmware copied ($(ls "$FIRMWARE_SRC"/*.bin 2>/dev/null | wc -l) firmware files)"

# Step 4: Build + install DKMS source
echo ""
echo "[4/6] Building DKMS driver (kernel $(uname -r))..."
cd "$DRIVER_SRC"

# Register with DKMS
DKMS_NAME="aic8800"
DKMS_VER="1.0.9-brostrend"

# Remove old registration
if [ -d "/var/lib/dkms/$DKMS_NAME" ]; then
    dkms remove "$DKMS_NAME/$DKMS_VER" --all 2>/dev/null || true
fi

# Copy source to /usr/src
rm -rf "/usr/src/${DKMS_NAME}-${DKMS_VER}"
cp -r "$DRIVER_SRC" "/usr/src/${DKMS_NAME}-${DKMS_VER}"

# Write dkms.conf
cat > "/usr/src/${DKMS_NAME}-${DKMS_VER}/dkms.conf" <<EOF
PACKAGE_NAME="$DKMS_NAME"
PACKAGE_VERSION="$DKMS_VER"
CLEAN="make clean"
MAKE[0]="make -C . KDIR=/lib/modules/\$kernelver/build"
BUILT_MODULE_NAME[0]="aic8800_fdrv"
BUILT_MODULE_LOCATION[0]="aic8800_fdrv"
DEST_MODULE_LOCATION[0]="/kernel/drivers/net/wireless/aic8800"
BUILT_MODULE_NAME[1]="aic_load_fw"
BUILT_MODULE_LOCATION[1]="aic_load_fw"
DEST_MODULE_LOCATION[1]="/kernel/drivers/net/wireless/aic8800"
AUTOINSTALL="yes"
EOF

# Build
dkms add -m "$DKMS_NAME" -v "$DKMS_VER"
dkms build -m "$DKMS_NAME" -v "$DKMS_VER"
dkms install -m "$DKMS_NAME" -v "$DKMS_VER"

# Step 5: Load modules
echo ""
echo "[5/6] Loading kernel modules..."
modprobe -r aic8800_fdrv aic_load_fw 2>/dev/null || true
modprobe aic_load_fw
modprobe aic8800_fdrv

# Step 6: Verify
echo ""
echo "[6/6] Verifying..."
sleep 3

if ip link show | grep -E "wlan1|wlx|wlp" >/dev/null; then
    NEW_IFACE=$(ip link show | grep -E "wlan1|wlx|wlp" | head -1 | awk '{print $2}' | sed 's/://')
    echo "  SUCCESS: New interface detected: $NEW_IFACE"
    echo ""
    echo "You can now run: sudo python3 scripts/setup.py"
    echo ""
    exit 0
else
    echo "  WARNING: No new WiFi interface detected yet."
    echo "  This may happen if the dongle hasn't fully switched modes."
    echo "  Try unplugging and re-inserting the dongle, then re-run this script."
    echo ""
    echo "  Current lsusb output:"
    lsusb | grep -i aic
    echo ""
    echo "  dmesg tail:"
    dmesg | tail -10
    exit 1
fi
