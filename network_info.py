#!/usr/bin/env python3

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
# LOOPBACK TEST (cross-platform)
# ============================================================

def test_loopback():
    """
    Test TCP/IP stack by pinging the loopback address (127.0.0.1).
    This never touches a physical NIC or cable — it tests only
    whether the OS network stack is loaded and functional.
    Returns True (pass) or False (fail).
    """
    import subprocess

    os_name = detect_os()

    try:
        if os_name == "windows":
            # -n 1 = send 1 packet, -w 1000 = 1 second timeout
            cmd = "ping -n 1 -w 1000 127.0.0.1"
        else:
            # -c 1 = send 1 packet, -W 1 = 1 second timeout
            cmd = "ping -c 1 -W 1 127.0.0.1"

        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0

    except Exception:
        return False


# ============================================================
# GATEWAY TEST (cross-platform)
# ============================================================

def test_gateway(gateway_ip):
    """
    Test reachability of the default gateway by pinging it.
    Gateway IP is auto-detected by the caller (get_windows_gateway
    or get_linux_gateway) — never hardcoded here.
    Returns True (pass) or False (fail).
    If no gateway IP is supplied, returns False immediately.
    """
    if not gateway_ip:
        return False

    os_name = detect_os()

    try:
        if os_name == "windows":
            # -n 1 = one packet, -w 2000 = 2 second timeout
            cmd = f"ping -n 1 -w 2000 {gateway_ip}"
        else:
            # -c 1 = one packet, -W 2 = 2 second timeout
            cmd = f"ping -c 1 -W 2 {gateway_ip}"

        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0

    except Exception:
        return False


# ============================================================
# DNS SERVER CONNECTIVITY TEST (cross-platform)
# ============================================================

def test_dns_servers(dns_list, os_name):
    """
    Ping each configured DNS server individually.
    dns_list : list of DNS server IP strings (auto-detected by caller)
    os_name  : 'windows' or 'linux'
    Returns  : (overall_result, per_server_results)
                overall_result     — 'PASS', 'PARTIAL', 'FAIL', or 'SKIP'
                per_server_results — list of (ip, reachable: bool) tuples
    """
    if not dns_list:
        return "SKIP", []

    per_server = []
    for dns_ip in dns_list:
        try:
            if os_name == "windows":
                cmd = f"ping -n 1 -w 2000 {dns_ip}"
            else:
                cmd = f"ping -c 1 -W 2 {dns_ip}"

            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            per_server.append((dns_ip, result.returncode == 0))
        except Exception:
            per_server.append((dns_ip, False))

    passed  = sum(1 for _, ok in per_server if ok)
    total   = len(per_server)

    if passed == total:
        overall = "PASS"
    elif passed == 0:
        overall = "FAIL"
    else:
        overall = "PARTIAL"

    return overall, per_server


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

    # ── OS Detection ────────────────────────────────────────
    detected_os = detect_os()
    os_display = platform.system() + " " + platform.release()

    print_header("SYSTEM")
    print(f"  Hostname        : {get_hostname()}")
    print(f"  Operating System: {os_display}")
    print(f"  Detected OS     : {detected_os.upper()}")

    # ── Loopback Test ────────────────────────────────────────
    print_header("LOOPBACK TEST")
    loopback_ok = test_loopback()
    if loopback_ok:
        print("  [PASS] 127.0.0.1 replied. TCP/IP stack is functional.")
    else:
        print("  [FAIL] 127.0.0.1 did not reply. Network stack may be broken.")
        print("  Possible causes:")
        print("    - NIC driver not loaded or corrupted")
        print("    - TCP/IP protocol unbound from adapter (Windows)")
        print("    - Loopback interface is DOWN (Linux: run 'ip link set lo up')")

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

    # ── Gateway Reachability Test ─────────────────────────────
    print_header("GATEWAY TEST")
    if not gateway:
        print("  [SKIP] No gateway IP detected — cannot test reachability.")
        gateway_ok = False
    else:
        print(f"  Gateway IP : {gateway}")
        gateway_ok = test_gateway(gateway)
        if gateway_ok:
            print(f"  [PASS] {gateway} replied. Local network is reachable.")
        else:
            print(f"  [FAIL] {gateway} did not reply.")
            print("  Possible causes:")
            print("    - Wrong gateway IP configured")
            print("    - Subnet mask puts you on a different network than the gateway")
            print("    - Gateway device is down or offline")
            print("    - Firewall on gateway is blocking ICMP")

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

    # ── DNS Server Connectivity Test ─────────────────────────
    print_header("DNS SERVER TEST")
    dns_overall, dns_results = test_dns_servers(dns, detected_os)

    if dns_overall == "SKIP":
        print("  [SKIP] No DNS servers detected — cannot test reachability.")
        dns_reach_status = "SKIP"
    else:
        for dns_ip, reachable in dns_results:
            status = "PASS" if reachable else "FAIL"
            print(f"  Testing : {dns_ip}")
            if reachable:
                print(f"  [PASS] {dns_ip} is reachable.")
            else:
                print(f"  [FAIL] {dns_ip} did not reply.")

        print("")
        if dns_overall == "PASS":
            print("  Result : ALL DNS servers reachable.")
            dns_reach_status = "PASS"
        elif dns_overall == "PARTIAL":
            print("  Result : PARTIAL — some DNS servers unreachable.")
            print("  Note   : Name resolution may still work via reachable servers.")
            dns_reach_status = "PARTIAL"
        else:
            print("  Result : ALL DNS servers unreachable.")
            print("  Possible causes:")
            print("    - DNS server IP is wrong")
            print("    - Firewall blocking UDP/TCP port 53")
            print("    - DNS server is down")
            dns_reach_status = "FAIL"

    # ── Diagnostic Summary ───────────────────────────────────
    print_header("DIAGNOSTIC SUMMARY")
    loopback_status  = "PASS"    if loopback_ok        else "FAIL"
    ip_status        = "PASS"    if ips                else "FAIL"
    gateway_status   = "PASS"    if gateway            else "WARNING"
    gw_reach_status  = "PASS"    if gateway_ok         else ("SKIP" if not gateway else "FAIL")
    dns_cfg_status   = "PASS"    if dns                else "WARNING"

    print(f"  Loopback (TCP/IP stack)  : {loopback_status}")
    print(f"  Local IP assignment      : {ip_status}")
    print(f"  Default Gateway detected : {gateway_status}")
    print(f"  Gateway reachability     : {gw_reach_status}")
    print(f"  DNS Servers configured   : {dns_cfg_status}")
    print(f"  DNS Server reachability  : {dns_reach_status}")

    all_ok = (loopback_ok and bool(ips) and bool(gateway) and gateway_ok
              and bool(dns) and dns_reach_status == "PASS")
    print("")
    if all_ok:
        print("  Status: ALL CHECKS PASSED")
        print("  Note  : Presence of values does not confirm correct values.")
        print("          Verify IP/gateway match expected lab configuration.")
    else:
        print("  Status: ISSUES DETECTED")
        print("  Review the warnings above for details.")

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
