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
# EXTERNAL IP CONNECTIVITY TEST (cross-platform)
# ============================================================

EXTERNAL_TEST_IP = "8.8.8.8"

def test_external_ip(os_name):
    """
    Ping 8.8.8.8 directly — bypasses DNS entirely.
    Tests raw internet routing and firewall rules.
    If this passes but domain resolution fails → DNS problem.
    If this fails → internet connectivity or routing problem.
    Returns True (pass) or False (fail).
    """
    try:
        if os_name == "windows":
            cmd = f"ping -n 1 -w 2000 {EXTERNAL_TEST_IP}"
        else:
            cmd = f"ping -c 1 -W 2 {EXTERNAL_TEST_IP}"

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
# DNS RESOLUTION TEST (cross-platform)
# ============================================================

TEST_DOMAIN = "google.com"

def test_dns_resolution(os_name):
    """
    Resolve TEST_DOMAIN to an IP address using the OS resolver.
    Tests the full DNS pipeline: configured DNS server receives
    query, resolves the name, returns an IP.
    Returns (resolved_ip: str | None) — None means failure.
    """
    # Method 1: use Python's socket.getaddrinfo (works on both OS,
    # uses whatever DNS the OS has configured — most accurate test)
    try:
        results = socket.getaddrinfo(TEST_DOMAIN, None, socket.AF_INET)
        if results:
            return results[0][4][0]  # first IPv4 address
    except Exception:
        pass

    # Method 2: fallback — nslookup via shell (catches edge cases
    # where getaddrinfo is restricted)
    try:
        if os_name == "windows":
            cmd = f"nslookup {TEST_DOMAIN}"
            output = subprocess.run(cmd, shell=True, capture_output=True,
                                    text=True, timeout=10)
            for line in output.stdout.splitlines():
                if "Address" in line and "10.10.10" not in line and "#" not in line:
                    parts = line.split(":")
                    if len(parts) > 1:
                        ip = parts[1].strip()
                        if ip and ip != "0.0.0.0":
                            return ip
        else:
            cmd = f"nslookup {TEST_DOMAIN} 2>/dev/null | grep -A1 'Name:' | grep 'Address' | head -1 | awk '{{print $2}}'"
            output = subprocess.run(cmd, shell=True, capture_output=True,
                                    text=True, timeout=10)
            ip = output.stdout.strip()
            if ip:
                return ip
    except Exception:
        pass

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


# ============================================================
# DIAGNOSTIC REPORT GENERATOR
# ============================================================

def generate_diagnostic_report(os_name, hostname, ips, gateway, dns,
                                loopback_ok, gateway_ok, dns_reach,
                                ext_ok, dns_res_ok, resolved_ip):
    """
    Collect all test results, determine overall status, produce
    a specific diagnosis based on failure patterns, and print
    remediation steps.

    Status levels:
      HEALTHY  — all checks pass
      WARNING  — partial failures, some connectivity works
      CRITICAL — fundamental failure, network non-functional
    """

    W = "=" * 46

    # ── Determine overall status and diagnosis ────────────────
    if not loopback_ok:
        status    = "CRITICAL"
        diagnosis = "TCP/IP stack is not functional. The network stack failed to respond to loopback."
        remediation = [
            "Windows: Run 'netsh winsock reset' then reboot.",
            "Linux  : Run 'sudo ip link set lo up' to restore loopback interface.",
            "Check that the NIC driver is installed and loaded.",
            "If the problem persists, reinstall the network adapter driver.",
        ]

    elif not ips:
        status    = "CRITICAL"
        diagnosis = "No IP address is assigned to any adapter. The machine has no network identity."
        remediation = [
            "Check if the adapter is UP: 'Get-NetAdapter' (Win) or 'ip link show' (Linux).",
            "Apply a static IP or verify DHCP is configured and a lease is being issued.",
            "In VirtualBox: confirm adapter is enabled and attached to the correct network.",
        ]

    elif not gateway:
        status    = "WARNING"
        diagnosis = "No default gateway configured. Machine can only reach its own local subnet."
        remediation = [
            "Set the default gateway in adapter properties (Win) or Netplan (Linux).",
            "Verify the gateway IP is correct for your subnet (e.g. 10.10.10.1 for /24).",
            "Note: Host-Only adapters may intentionally have no gateway.",
        ]

    elif not gateway_ok:
        status    = "WARNING"
        diagnosis = f"Gateway {gateway} is configured but unreachable. Local network connectivity is broken."
        remediation = [
            "Verify the gateway IP is correct — check your subnet mask.",
            "Confirm the gateway device (router/pfSense) is powered on.",
            "In VirtualBox: check both VMs are on the same Host-Only Adapter name.",
            "Check for firewall rules on the gateway blocking ICMP.",
        ]

    elif not ext_ok and not dns_res_ok:
        status    = "WARNING"
        diagnosis = "Gateway reachable but no internet access. Local network works; external path is broken."
        remediation = [
            "Check the WAN/uplink connection on the gateway/router.",
            "Verify the NAT adapter is enabled in VirtualBox (if using NAT for internet).",
            "Test from the host machine — if host has internet, check VirtualBox NAT settings.",
            "Check for firewall rules blocking outbound traffic beyond the gateway.",
        ]

    elif not ext_ok and dns_res_ok:
        status    = "WARNING"
        diagnosis = (
            f"DNS resolved {EXTERNAL_TEST_IP} blocked but {TEST_DOMAIN} resolved via local DNS proxy. "
            "Direct internet ICMP is blocked; name resolution works through host-side resolver."
        )
        remediation = [
            "This is expected in some VirtualBox NAT configurations — DNS works via the host.",
            "If direct internet is needed: check firewall ICMP rules on NAT adapter.",
            "Verify the NAT adapter is enabled and VirtualBox NAT is not blocking ICMP out.",
        ]

    elif ext_ok and not dns_res_ok:
        status    = "WARNING"
        diagnosis = f"Internet reachable ({EXTERNAL_TEST_IP} replied) but DNS resolution failed. DNS is the only broken component."
        remediation = [
            "Verify the configured DNS server IP is correct.",
            "Test manually: 'nslookup google.com 8.8.8.8' to bypass the configured server.",
            "Check if UDP port 53 is blocked by a firewall.",
            "Try setting DNS to 8.8.8.8 directly if the current server is unreachable.",
        ]

    elif dns_reach in ("FAIL", "PARTIAL") and ext_ok and dns_res_ok:
        status    = "WARNING"
        diagnosis = (
            "Some configured DNS servers are unreachable (ping), but name resolution is working. "
            "Redundancy is reduced — if the working server goes down, DNS will fail."
        )
        remediation = [
            "Investigate the unreachable DNS server — may be misconfigured or down.",
            "Consider replacing unreachable DNS entries with reliable public servers (8.8.8.8, 1.1.1.1).",
            "No immediate action required — network is functional.",
        ]

    else:
        status    = "HEALTHY"
        diagnosis = "All connectivity tests passed. Network is functioning normally."
        remediation = []

    # ── Build test result lines ───────────────────────────────
    def tick(ok):
        return "[PASS]" if ok else "[FAIL]"

    dns_reach_ok = dns_reach == "PASS"
    ip_ok        = bool(ips)
    gw_cfg_ok    = bool(gateway)

    results = [
        (tick(loopback_ok),  "Loopback (127.0.0.1)"),
        (tick(ip_ok),        "Local IP assignment"),
        (tick(gw_cfg_ok),    "Default Gateway configured"),
        (tick(gateway_ok),   "Gateway reachability"),
        (tick(dns_reach_ok), f"DNS Server reachability  [{dns_reach}]"),
        (tick(ext_ok),       f"External IP ({EXTERNAL_TEST_IP})"),
        (tick(dns_res_ok),   f"DNS Resolution ({TEST_DOMAIN}" +
                              (f" → {resolved_ip}" if resolved_ip else "") + ")"),
    ]

    # ── Print the report ─────────────────────────────────────
    print("")
    print(W)
    print("     NETWORK DIAGNOSTIC REPORT")
    print(W)
    print(f"  OS       : {os_name.upper()}")
    print(f"  Hostname : {hostname}")
    print(f"  IP(s)    : {', '.join(ips) if ips else 'None detected'}")
    print(f"  Gateway  : {gateway if gateway else 'Not configured'}")
    print(f"  DNS      : {', '.join(dns) if dns else 'Not configured'}")
    print("")
    print("  --- TEST RESULTS ---")
    for status_tag, label in results:
        print(f"  {status_tag}  {label}")
    print("")
    print(W)
    print(f"  OVERALL STATUS: {status}")
    print(W)
    print(f"  {diagnosis}")
    if remediation:
        print("")
        print("  REMEDIATION STEPS:")
        for i, step in enumerate(remediation, 1):
            print(f"    {i}. {step}")
    print(W)


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

    # ── External IP Connectivity Test ────────────────────────
    print_header("EXTERNAL CONNECTIVITY TEST")
    print(f"  Target : {EXTERNAL_TEST_IP}  (bypasses DNS — tests raw internet path)")
    ext_ok = test_external_ip(detected_os)
    if ext_ok:
        print(f"  [PASS] {EXTERNAL_TEST_IP} replied. Internet connectivity confirmed.")
    else:
        print(f"  [FAIL] {EXTERNAL_TEST_IP} did not reply. No internet connectivity.")
        print("  Possible causes:")
        print("    - Default route is missing or points to unreachable gateway")
        print("    - Firewall is blocking outbound ICMP")
        print("    - ISP/NAT link is down")

    # ── DNS Resolution Test ───────────────────────────────────
    print_header("DNS RESOLUTION TEST")
    print(f"  Target : {TEST_DOMAIN}  (tests full DNS pipeline)")
    resolved_ip = test_dns_resolution(detected_os)
    if resolved_ip:
        print(f"  [PASS] {TEST_DOMAIN} resolved to {resolved_ip}")
        dns_res_ok = True
    else:
        print(f"  [FAIL] Could not resolve {TEST_DOMAIN}.")
        dns_res_ok = False
        if ext_ok:
            print("  Diagnosis : External IP works but DNS fails → DNS problem.")
            print("  Possible causes:")
            print("    - Configured DNS server is unreachable")
            print("    - DNS server is not responding to queries (UDP 53 blocked)")
            print("    - Wrong DNS server IP configured")
        else:
            print("  Diagnosis : Both external IP and DNS fail → internet connectivity problem.")
            print("              Fix internet path first, then re-test DNS.")
    # ── Build and print final diagnostic report ───────────────
    generate_diagnostic_report(
        os_name     = detected_os,
        hostname    = get_hostname(),
        ips         = ips,
        gateway     = gateway,
        dns         = dns,
        loopback_ok = loopback_ok,
        gateway_ok  = gateway_ok,
        dns_reach   = dns_reach_status,
        ext_ok      = ext_ok,
        dns_res_ok  = dns_res_ok,
        resolved_ip = resolved_ip,
    )

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