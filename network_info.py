#!/usr/bin/env python3
# ============================================================
# Network Information Collector — Cross-Platform
# Description: Detects OS and collects IP, Gateway, and DNS
#              information. Works on Windows and Linux.
#              Handles errors gracefully without crashing.
# ============================================================

import platform
import subprocess
import socket
import sys

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def print_header(title):
    """Print a formatted section header"""
    print("")
    print(f"  [{title}]")
    print("  " + "-" * 40)

def print_banner(text):
    """Print a top-level banner"""
    print("=" * 50)
    print(f"  {text}")
    print("=" * 50)

def run_command(command, shell=True):
    """
    Run a shell command safely.
    Returns output string or None if command fails.
    Never crashes the script on failure.
    """
    try:
        result = subprocess.run(
            command,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=10  # Prevents script hanging if command stalls
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        else:
            return None
    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None

# ============================================================
# WINDOWS FUNCTIONS (PowerShell)
# ============================================================

def get_windows_ips():
    """Get IPv4 addresses on Windows, excluding loopback"""
    output = run_command(
        'powershell -command "'
        'Get-NetIPAddress -AddressFamily IPv4 | '
        'Where-Object {$_.IPAddress -ne \'127.0.0.1\'} | '
        'Select-Object -ExpandProperty IPAddress'
        '"'
    )
    if output:
        return output.splitlines()
    return []

def get_windows_gateway():
    """Get default gateway on Windows"""
    output = run_command(
        'powershell -command "'
        '(Get-NetRoute -DestinationPrefix \'0.0.0.0/0\' | '
        'Select-Object -First 1).NextHop'
        '"'
    )
    if output and output.strip() != "0.0.0.0":
        return output.strip()
    return None

def get_windows_dns():
    """Get DNS servers on Windows, excluding empty entries"""
    output = run_command(
        'powershell -command "'
        'Get-DnsClientServerAddress -AddressFamily IPv4 | '
        'Where-Object {$_.ServerAddresses.Count -gt 0} | '
        'Select-Object -ExpandProperty ServerAddresses'
        '"'
    )
    if output:
        # Remove duplicates and empty lines
        servers = list(set([
            line.strip() for line in output.splitlines()
            if line.strip() and line.strip() != "{}"
        ]))
        return servers
    return []

# ============================================================
# LINUX FUNCTIONS (Bash)
# ============================================================

def get_linux_ips():
    """Get IPv4 addresses on Linux, excluding loopback"""
    output = run_command(
        "ip -4 addr show | grep inet | grep -v '127.0.0.1' | "
        "awk '{print $2}' | cut -d'/' -f1"
    )
    if output:
        return output.splitlines()
    return []

def get_linux_gateway():
    """Get default gateway on Linux"""
    output = run_command(
        "ip route show default | awk '{print $3}' | head -1"
    )
    if output and output.strip():
        return output.strip()
    return None

def get_linux_dns():
    """
    Get DNS servers on Linux.
    On Ubuntu 22.04+, /etc/resolv.conf may show 127.0.0.53
    (systemd-resolved stub). We check resolvectl for real upstream DNS.
    """
    # First try resolvectl for real upstream DNS servers
    output = run_command(
        "resolvectl status 2>/dev/null | grep 'DNS Servers' | "
        "awk '{print $3}' | head -5"
    )
    if output:
        return output.splitlines()

    # Fallback: read /etc/resolv.conf directly
    output = run_command(
        "grep '^nameserver' /etc/resolv.conf | awk '{print $2}'"
    )
    if output:
        return output.splitlines()

    return []

# ============================================================
# HOSTNAME (works on both OS)
# ============================================================

def get_hostname():
    """Get system hostname — works on both Windows and Linux"""
    try:
        return socket.gethostname()
    except Exception:
        return "Unknown"

# ============================================================
# OS DETECTION AND MAIN LOGIC
# ============================================================

def detect_os():
    """Detect operating system — returns 'windows' or 'linux'"""
    os_name = platform.system().lower()
    if "windows" in os_name:
        return "windows"
    elif "linux" in os_name:
        return "linux"
    else:
        return "unknown"

def collect_and_display():
    """Main function — detects OS, collects data, displays results"""

    # ── Banner ──────────────────────────────────────────────
    print_banner("NETWORK INFORMATION REPORT")
    print(f"  Python Version: {sys.version.split()[0]}")

    # ── OS Detection ────────────────────────────────────────
    detected_os = detect_os()
    os_display = platform.system() + " " + platform.release()

    print_header("SYSTEM")
    print(f"  Hostname        : {get_hostname()}")
    print(f"  Operating System: {os_display}")
    print(f"  Detected OS     : {detected_os.upper()}")

    # ── Collect data based on OS ─────────────────────────────
    if detected_os == "windows":
        ips     = get_windows_ips()
        gateway = get_windows_gateway()
        dns     = get_windows_dns()

    elif detected_os == "linux":
        ips     = get_linux_ips()
        gateway = get_linux_gateway()
        dns     = get_linux_dns()

    else:
        print("\n  ERROR: Unsupported operating system detected.")
        print(f"  Platform reported: {platform.system()}")
        sys.exit(1)

    # ── IP Addresses ─────────────────────────────────────────
    print_header("IPv4 ADDRESSES")
    if ips:
        for ip in ips:
            print(f"  {ip}")
    else:
        print("  WARNING: No IPv4 addresses found")
        print("  Possible causes:")
        print("    - Network adapter is disabled")
        print("    - No IP address assigned (check DHCP or static config)")

    # ── Default Gateway ──────────────────────────────────────
    print_header("DEFAULT GATEWAY")
    if gateway:
        print(f"  {gateway}")
    else:
        print("  WARNING: No default gateway configured")
        print("  Possible causes:")
        print("    - Host-Only adapter has no gateway by design")
        print("    - NAT adapter not receiving DHCP lease")
        print("    - Network adapter is disabled")

    # ── DNS Servers ──────────────────────────────────────────
    print_header("DNS SERVERS")
    if dns:
        for server in dns:
            print(f"  {server}")
    else:
        print("  WARNING: No DNS servers configured")
        print("  Possible causes:")
        print("    - DNS not set in network adapter properties")
        print("    - /etc/resolv.conf missing or empty (Linux)")

    # ── Footer ───────────────────────────────────────────────
    print("")
    print("=" * 50)
    print("  END OF REPORT")
    print("=" * 50)
    print("")

# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    collect_and_display()
