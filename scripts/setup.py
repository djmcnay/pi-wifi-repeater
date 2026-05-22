#!/usr/bin/env python3
"""
PI WiFi Repeater Setup Script
Configures a Raspberry Pi Zero 2W as a WiFi repeater/AP.

Built-in wlan0: upstream to home router
USB dongle wlan1: downstream AP "Boulders Way" (open network, no password)
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Default configuration
DEFAULTS = {
    "upstream_interface": "wlan0",
    "downstream_interface": "wlan1",
    "ssid": "Boulders Way",
    "channel": 6,
    "downstream_ip": "192.168.4.1",
    "dhcp_range_start": "192.168.4.50",
    "dhcp_range_end": "192.168.4.100",
    "dhcp_lease": "24h",
}

HOSTAPD_CONF = """# Auto-generated hostapd config
interface={interface}
driver=nl80211
ssid={ssid}
hw_mode=g
channel={channel}
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
"""

DNSMASQ_CONF = """# Auto-generated dnsmasq config
interface={interface}
dhcp-range={dhcp_start},{dhcp_end},{lease}
server=8.8.8.8
server=8.8.4.4
"""

SYSCTL_CONF = """net.ipv4.ip_forward=1
"""

INTERFACES_CONF = """# Loopback
auto lo
iface lo inet loopback

# Upstream (home WiFi)
allow-hotplug {upstream}
iface {upstream} inet dhcp
    wpa-conf /etc/wpa_supplicant/wpa_supplicant.conf

# Downstream (AP)
allow-hotplug {downstream}
iface {downstream} inet static
    address {downstream_ip}
    netmask 255.255.255.0
    nohook wpa_supplicant
"""


def run(cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command."""
    print(f"[RUN] {cmd}")
    return subprocess.run(cmd, shell=True, check=check, capture_output=True, text=True)


def install_packages() -> None:
    """Install required packages."""
    print("\n[1/7] Updating package list and installing dependencies...")
    run("apt-get update")
    run("apt-get install -y hostapd dnsmasq iptables-persistent")
    run("systemctl unmask hostapd")
    run("systemctl enable hostapd dnsmasq")


def write_hostapd_conf(interface: str, ssid: str, channel: int) -> None:
    """Write hostapd configuration."""
    print("\n[2/7] Writing hostapd configuration...")
    conf = HOSTAPD_CONF.format(interface=interface, ssid=ssid, channel=channel)
    Path("/etc/hostapd/hostapd.conf").write_text(conf)
    # Tell hostapd where its config is
    Path("/etc/default/hostapd").write_text(f'DAEMON_CONF="/etc/hostapd/hostapd.conf"\n')


def write_dnsmasq_conf(interface: str, dhcp_start: str, dhcp_end: str, lease: str) -> None:
    """Write dnsmasq configuration."""
    print("\n[3/7] Writing dnsmasq configuration...")
    conf = DNSMASQ_CONF.format(
        interface=interface,
        dhcp_start=dhcp_start,
        dhcp_end=dhcp_end,
        lease=lease,
    )
    # Remove old config, write ours
    run("mv /etc/dnsmasq.conf /etc/dnsmasq.conf.bak 2>/dev/null || true", check=False)
    Path("/etc/dnsmasq.conf").write_text(conf)


def configure_interfaces(upstream: str, downstream: str, downstream_ip: str) -> None:
    """Configure network interfaces."""
    print("\n[4/7] Configuring network interfaces...")
    conf = INTERFACES_CONF.format(
        upstream=upstream,
        downstream=downstream,
        downstream_ip=downstream_ip,
    )
    # Append to /etc/network/interfaces (keep existing if careful)
    with open("/etc/network/interfaces", "r") as f:
        existing = f.read()
    if "Boulders Way" not in existing:
        with open("/etc/network/interfaces", "a") as f:
            f.write("\n" + conf + "\n")


def enable_ip_forward() -> None:
    """Enable IP forwarding in kernel."""
    print("\n[5/7] Enabling IP forwarding...")
    with open("/etc/sysctl.conf", "r") as f:
        existing = f.read()
    if "net.ipv4.ip_forward=1" not in existing:
        with open("/etc/sysctl.conf", "a") as f:
            f.write("\nnet.ipv4.ip_forward=1\n")
    run("sysctl -p")


def setup_iptables(upstream: str, downstream: str) -> None:
    """Configure NAT and forwarding rules."""
    print("\n[6/7] Setting up iptables (NAT and forwarding)...")
    # Flush existing rules first
    run("iptables -t nat -F", check=False)
    run("iptables -F", check=False)
    
    # NAT: masquerade outbound traffic from downstream subnet
    run(f"iptables -t nat -A POSTROUTING -o {upstream} -j MASQUERADE")
    
    # Allow forwarding from downstream to upstream
    run(f"iptables -A FORWARD -i {downstream} -o {upstream} -j ACCEPT")
    run(f"iptables -A FORWARD -i {upstream} -o {downstream} -m state --state RELATED,ESTABLISHED -j ACCEPT")
    
    # Save rules
    run("iptables-save > /etc/iptables/rules.v4")


def start_services() -> None:
    """Start and enable services."""
    print("\n[7/7] Starting services...")
    run("systemctl restart dnsmasq")
    run("systemctl restart hostapd")
    run("systemctl enable dnsmasq hostapd")


def verify_interfaces(expected: list[str]) -> list[str]:
    """Check available network interfaces."""
    result = run("ip link show", check=False)
    interfaces = []
    for line in result.stdout.splitlines():
        if ":" in line:
            iface = line.split(":")[1].strip()
            if iface and iface != "lo":
                interfaces.append(iface)
    
    missing = [e for e in expected if e not in interfaces]
    if missing:
        print(f"\nWARNING: Expected interfaces {missing} not found!")
        print(f"Available interfaces: {interfaces}")
    
    return interfaces


def main() -> int:
    parser = argparse.ArgumentParser(description="Set up Pi as WiFi repeater/AP")
    parser.add_argument("--upstream", default=DEFAULTS["upstream_interface"], help="Upstream interface (default: wlan0)")
    parser.add_argument("--downstream", default=DEFAULTS["downstream_interface"], help="Downstream AP interface (default: wlan1)")
    parser.add_argument("--ssid", default=DEFAULTS["ssid"], help="AP SSID")
    parser.add_argument("--channel", type=int, default=DEFAULTS["channel"], help="WiFi channel")
    parser.add_argument("--ip", default=DEFAULTS["downstream_ip"], help="Downstream static IP")
    parser.add_argument("--dhcp-start", default=DEFAULTS["dhcp_range_start"], help="DHCP range start")
    parser.add_argument("--dhcp-end", default=DEFAULTS["dhcp_range_end"], help="DHCP range end")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without doing it")
    
    args = parser.parse_args()
    
    if os.geteuid() != 0:
        print("ERROR: Must run as root (sudo)")
        return 1
    
    print("=" * 60)
    print("PI WiFi Repeater Setup")
    print("=" * 60)
    print(f"  Upstream:    {args.upstream} (to home router)")
    print(f"  Downstream:  {args.downstream} (broadcasts '{args.ssid}')")
    print(f"  AP IP:       {args.ip}")
    print(f"  DHCP Range:  {args.dhcp_start} - {args.dhcp_end}")
    print(f"  WiFi:        Open network (no password)")
    print("=" * 60)
    
    if args.dry_run:
        print("\nDRY RUN - no changes made.")
        return 0
    
    # Confirm
    response = input("\nProceed? [Y/n]: ")
    if response.lower() not in ("", "y", "yes"):
        print("Aborted.")
        return 0
    
    # Verify interfaces
    print("\nChecking network interfaces...")
    verify_interfaces([args.upstream, args.downstream])
    
    # Run setup steps
    install_packages()
    write_hostapd_conf(args.downstream, args.ssid, args.channel)
    write_dnsmasq_conf(args.downstream, args.dhcp_start, args.dhcp_end, DEFAULTS["dhcp_lease"])
    configure_interfaces(args.upstream, args.downstream, args.ip)
    enable_ip_forward()
    setup_iptables(args.upstream, args.downstream)
    start_services()
    
    print("\n" + "=" * 60)
    print("Setup complete!")
    print("=" * 60)
    print(f"The network '{args.ssid}' should now be visible.")
    print("Devices can connect with no password.")
    print(f"AP gateway IP: {args.ip}")
    print("\nTo check status:")
    print("  sudo systemctl status hostapd")
    print("  sudo systemctl status dnsmasq")
    print("  sudo iw dev wlan1 info")
    print("\nReboot recommended.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
