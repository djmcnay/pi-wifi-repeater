#!/usr/bin/env python3
"""
PI WiFi Repeater — NordVPN Layer

Installs NordVPN, authenticates, configures NordLynx (WireGuard),
and routes all downstream AP traffic through South Africa.

Must be run AFTER setup.py (which creates the AP). Requires root.

Usage:
    sudo python3 scripts/setup_vpn.py --token <NORDVPN_TOKEN>
    # or
    export NORDVPN_TOKEN=...
    sudo python3 scripts/setup_vpn.py
"""

import argparse
import os
import subprocess
import sys
import urllib.request
from pathlib import Path


VPN_URL = "https://downloads.nordcdn.com/apps/linux/install.sh"
TARGET_COUNTRY = "South_Africa"
TECHNOLOGY = "NORDLYNX"


def run(cmd: str, check: bool = True, timeout: int = 120) -> subprocess.CompletedProcess:
    """Run a shell command."""
    print(f"[RUN] {cmd}")
    return subprocess.run(cmd, shell=True, check=check, capture_output=True, text=True, timeout=timeout)


def install_nordvpn() -> None:
    """Download and install the NordVPN Linux client."""
    print("\n[1/6] Installing NordVPN CLI...")
    
    # Try the official install script
    installer = "/tmp/nordvpn-install.sh"
    print(f"  Downloading {VPN_URL}...")
    urllib.request.urlretrieve(VPN_URL, installer)
    os.chmod(installer, 0o755)
    
    print("  Running installer...")
    result = run(f"bash {installer}", check=False)
    if result.returncode != 0:
        print(f"WARNING: Installer exited {result.returncode}")
        print(f"stdout: {result.stdout}")
        print(f"stderr: {result.stderr}")
    
    # Verify nordvpn binary is available
    result = run("which nordvpn", check=False)
    if result.returncode != 0:
        print("ERROR: nordvpn binary not found after install.")
        sys.exit(1)


def login(token: str) -> None:
    """Authenticate with NordVPN using an access token."""
    print("\n[2/6] Logging into NordVPN...")
    result = run(f"nordvpn login --token {token}", check=False)
    if "Welcome" not in result.stdout and "success" not in result.stdout.lower():
        print(f"WARNING: Login may have issues. Output:\n{result.stdout}\n{result.stderr}")
    else:
        print("  Logged in successfully.")


def configure_nordvpn() -> None:
    """Set NordVPN preferences suitable for a repeater/AP."""
    print("\n[3/6] Configuring NordVPN settings...")
    
    # Technology: NordLynx (WireGuard) — fastest
    run(f"nordvpn set technology {TECHNOLOGY}", check=False)
    print(f"  Technology: {TECHNOLOGY}")
    
    # Kill Switch: MUST be OFF on a repeater — otherwise VPN hiccups kill the AP
    run("nordvpn set killswitch off", check=False)
    print("  Kill Switch: OFF (required for repeater stability)")
    
    # Notify: off — silent
    run("nordvpn set notify off", check=False)
    print("  Notifications: OFF")
    
    # Autoconnect: on + country
    run(f"nordvpn set autoconnect on", check=False)
    run(f"nordvpn set autoconnect on {TARGET_COUNTRY}", check=False)
    print(f"  Auto-connect: ON ({TARGET_COUNTRY})")
    
    # DNS: let NordVPN handle it (they inject ZA DNS servers)
    run("nordvpn set dns off", check=False)
    print("  Custom DNS: OFF (using NordVPN DNS)")


def connect_to_south_africa() -> bool:
    """Connect to a South Africa server."""
    print(f"\n[4/6] Connecting to {TARGET_COUNTRY}...")
    result = run(f"nordvpn connect {TARGET_COUNTRY}", check=False, timeout=60)
    if "connected" in result.stdout.lower():
        print("  Connected.")
        return True
    else:
        print(f"  Connect output: {result.stdout}\n{result.stderr}")
        return False


def install_wireguard_tools() -> None:
    """Install wireguard-tools for wg-quick if needed."""
    print("\n[5/6] Ensuring wireguard-tools are available...")
    run("apt-get install -y wireguard-tools", check=False)


def setup_routing(downstream_if: str = "wlan1", downstream_subnet: str = "192.168.35.0/24") -> None:
    """
    Configure policy-based routing:
    - Downstream traffic (from wlan1 / 192.168.35.x) → routes through VPN tunnel (NordLynx = wg0)
    - Upstream / SSH traffic stays on normal route so we don't lose access
    """
    print(f"\n[6/6] Setting up policy-based routing for {downstream_if}...")
    
    # Find the NordVPN tunnel interface (usually wg0 for NordLynx)
    tunnel_result = run("ip link show | grep -E 'wg|tun' || true", check=False)
    tunnel_if = None
    if "wg0" in tunnel_result.stdout:
        tunnel_if = "wg0"
    elif "nordlynx" in tunnel_result.stdout:
        tunnel_if = "nordlynx"
    else:
        # Fall back to checking what nordvpn reports
        tun_res = run("nordvpn status | grep -i interface", check=False)
        if tun_res.returncode == 0 and tun_res.stdout.strip():
            tunnel_if = tun_res.stdout.strip().split()[-1]
    
    if not tunnel_if:
        print("WARNING: Could not detect NordVPN tunnel interface. Using 'wg0' as default.")
        tunnel_if = "wg0"
    else:
        print(f"  Detected tunnel interface: {tunnel_if}")
    
    # --- Step A: NAT from VPN tunnel to downstream subnet ---
    # Remove any old rules first
    run(f"iptables -t nat -D POSTROUTING -o {tunnel_if} -s {downstream_subnet} -j MASQUERADE 2>/dev/null || true", check=False)
    run(f"iptables -t nat -A POSTROUTING -o {tunnel_if} -s {downstream_subnet} -j MASQUERADE", check=False)
    print(f"  NAT: {downstream_subnet} -> {tunnel_if}")
    
    # --- Step B: Forward from downstream to VPN ---
    run(f"iptables -D FORWARD -i {downstream_if} -o {tunnel_if} -j ACCEPT 2>/dev/null || true", check=False)
    run(f"iptables -A FORWARD -i {downstream_if} -o {tunnel_if} -j ACCEPT", check=False)
    print(f"  Forward: {downstream_if} -> {tunnel_if}")
    
    # --- Step C: Allow return traffic ---
    run(f"iptables -D FORWARD -i {tunnel_if} -o {downstream_if} -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true", check=False)
    run(f"iptables -A FORWARD -i {tunnel_if} -o {downstream_if} -m state --state RELATED,ESTABLISHED -j ACCEPT", check=False)
    print(f"  Return path: {tunnel_if} -> {downstream_if}")
    
    # --- Step D: Save rules ---
    run("mkdir -p /etc/iptables", check=False)
    run("iptables-save > /etc/iptables/rules.v4", check=False)
    
    # --- Step E: Policy routing with ip rule + route tables ---
    # Create a custom route table for downstream traffic
    rt_table = "200"
    run(f"ip rule del from {downstream_subnet} lookup vpn_rt 2>/dev/null || true", check=False)
    run(f"ip rule add from {downstream_subnet} lookup vpn_rt", check=False)
    print(f"  ip rule: {downstream_subnet} -> table vpn_rt")
    
    # Find the VPN gateway IP (we need the next-hop for the default route in vpn_rt)
    gw_result = run(f"ip route show table main | grep default | head -1", check=False)
    default_gw = "192.168.1.1"  # fallback
    if gw_result.returncode == 0 and gw_result.stdout.strip():
        gw_parts = gw_result.stdout.strip().split()
        for i, part in enumerate(gw_parts):
            if part == "via":
                default_gw = gw_parts[i + 1]
                break
    
    # Add route: in vpn_rt, default goes through the VPN tunnel
    run("ip route flush table vpn_rt 2>/dev/null || true", check=False)
    run(f"ip route add default dev {tunnel_if} table vpn_rt", check=False)
    print(f"  Route table 'vpn_rt': default via {tunnel_if}")
    
    print("\n  Routing setup complete.")
    print("  Verify: devices on 'Boulders Way' should exit via South Africa.")


def verify_connection() -> None:
    """Quick sanity check that the VPN is up and routing."""
    print("\n[VERIFY] Checking VPN status...")
    result = run("nordvpn status", check=False)
    print(result.stdout)
    
    # Check external IP from the Pi
    print("\nPi's external IP (should be ZA IP when VPN is up):")
    run("curl -s --max-time 5 https://ipinfo.io/ip || echo 'check failed'", check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Set up NordVPN on Pi WiFi Repeater")
    parser.add_argument("--token", default=os.environ.get("NORDVPN_TOKEN"),
                        help="NordVPN access token (or set NORDVPN_TOKEN env var)")
    parser.add_argument("--downstream-iface", default="wlan1",
                        help="Downstream AP interface (default: wlan1)")
    parser.add_argument("--subnet", default="192.168.35.0/24",
                        help="Downstream subnet (default: 192.168.35.0/24)")
    
    args = parser.parse_args()
    
    if not args.token:
        print("ERROR: NordVPN token required.")
        print("  Pass --token or set NORDVPN_TOKEN environment variable.")
        print("  Get your token at: https://my.nordaccount.com/dashboard/nordvpn/")
        return 1
    
    if os.geteuid() != 0:
        print("ERROR: Must run as root (sudo)")
        return 1
    
    print("=" * 60)
    print("PI WiFi Repeater — NordVPN Layer")
    print("=" * 60)
    print(f"  Target country: {TARGET_COUNTRY}")
    print(f"  Technology:     {TECHNOLOGY}")
    print(f"  Downstream IF:  {args.downstream_iface}")
    print(f"  Subnet:         {args.subnet}")
    print("=" * 60)
    
    install_nordvpn()
    login(args.token)
    configure_nordvpn()
    
    connected = connect_to_south_africa()
    if not connected:
        print("\nWARNING: Initial connect failed. Will try again after auto-connect is set.")
    
    install_wireguard_tools()
    setup_routing(args.downstream_iface, args.subnet)
    
    # Enable and start nordvpnd service
    run("systemctl enable nordvpnd")
    run("systemctl restart nordvpnd")
    
    verify_connection()
    
    print("\n" + "=" * 60)
    print("NordVPN layer complete!")
    print("=" * 60)
    print("Reboot the Pi. On boot:")
    print("  - 'Boulders Way' AP will be up")
    print("  - NordVPN will auto-connect to South Africa")
    print("  - Devices on the AP will route through ZA")
    print("\nVerify externally:")
    print("  Connect a device to 'Boulders Way'")
    print("  Visit https://ipinfo.io — should show South Africa")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
