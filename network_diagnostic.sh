#!/bin/bash
# ============================================================
# Network Information Collector — Bash (Linux)
# Author: Israel
# Date: 24 June 2026
# Description: Collects IP, Gateway, and DNS information.
#              Handles broken/misconfigured networks gracefully.
#              Never shows raw command errors to the user.
#              Exits with proper status codes.
# ============================================================

# --- Track overall script health ---
# We start assuming success (0) and flip to failure (1)
# if any critical check fails. This becomes our exit code.
EXIT_CODE=0

# --- Suppress raw stderr globally where needed ---
# Every command below redirects stderr to /dev/null and
# checks output explicitly, rather than letting raw errors
# print to the terminal.

# ============================================================
# HELPER FUNCTIONS
# ============================================================

print_banner() {
    echo "=================================================="
    echo "  $1"
    echo "=================================================="
}

print_header() {
    echo ""
    echo "  [$1]"
    echo "  ----------------------------------------"
}

print_error() {
    # Clear, human-readable error — never the raw command error
    echo "  ERROR: $1"
}

print_warning() {
    echo "  WARNING: $1"
}

# ============================================================
# SECTION 1: HOSTNAME (very unlikely to fail, but still guarded)
# ============================================================

get_hostname() {
    local name
    name=$(hostname 2>/dev/null)
    if [ -n "$name" ]; then
        echo "$name"
    else
        echo "Unknown"
    fi
}

# ============================================================
# SECTION 2: IPv4 ADDRESSES
# ============================================================

get_ipv4_addresses() {
    # Redirect stderr to /dev/null so raw command errors never surface
    local raw_output
    raw_output=$(ip -4 addr show 2>/dev/null | grep inet | grep -v "127.0.0.1" | awk '{print $2}' | cut -d'/' -f1)

    if [ -z "$raw_output" ]; then
        # Empty result — could mean adapter disabled or no IP assigned
        return 1
    else
        echo "$raw_output"
        return 0
    fi
}

# ============================================================
# SECTION 3: DEFAULT GATEWAY
# ============================================================

get_gateway() {
    local gw
    gw=$(ip route show default 2>/dev/null | awk '{print $3}' | head -1)

    if [ -z "$gw" ]; then
        # No default route exists — common on Host-Only adapters
        return 1
    else
        echo "$gw"
        return 0
    fi
}

# ============================================================
# SECTION 4: DNS SERVERS
# ============================================================

get_dns_servers() {
    local dns_list

    # Try resolvectl first — gives real upstream DNS, not the
    # systemd-resolved stub (127.0.0.53)
    dns_list=$(resolvectl status 2>/dev/null | grep "DNS Servers" | awk '{print $3}')

    if [ -z "$dns_list" ]; then
        # Fallback to /etc/resolv.conf directly
        dns_list=$(grep "^nameserver" /etc/resolv.conf 2>/dev/null | awk '{print $2}')
    fi

    if [ -z "$dns_list" ]; then
        # Both methods returned nothing — truly no DNS configured
        return 1
    else
        echo "$dns_list"
        return 0
    fi
}

# ============================================================
# SECTION 5: ADAPTER STATUS CHECK
# ============================================================

check_adapters_up() {
    # Returns the names of interfaces that are administratively UP
    # Excludes loopback
    ip link show 2>/dev/null | grep -E "^[0-9]+:" | grep -v "lo:" | grep "state UP" | awk -F': ' '{print $2}'
}

check_adapters_down() {
    # Returns interfaces that exist but are DOWN
    ip link show 2>/dev/null | grep -E "^[0-9]+:" | grep -v "lo:" | grep "state DOWN" | awk -F': ' '{print $2}'
}

# ============================================================
# MAIN EXECUTION
# ============================================================

main() {
    print_banner "NETWORK INFORMATION REPORT"
    echo "  Script Author : Israel"
    echo "  Date          : 24 June 2026"
    echo "  Shell         : Bash $BASH_VERSION"

    # ── System Info ──────────────────────────────────────────
    print_header "SYSTEM"
    echo "  Hostname        : $(get_hostname)"
    echo "  Operating System: $(uname -s) $(uname -r)"

    # ── Adapter Status Check ─────────────────────────────────
    print_header "NETWORK ADAPTER STATUS"
    UP_ADAPTERS=$(check_adapters_up)
    DOWN_ADAPTERS=$(check_adapters_down)

    if [ -n "$UP_ADAPTERS" ]; then
        echo "  Adapters UP:"
        echo "$UP_ADAPTERS" | while read -r adapter; do
            echo "    - $adapter"
        done
    else
        print_warning "No network adapters are currently UP."
        EXIT_CODE=1
    fi

    if [ -n "$DOWN_ADAPTERS" ]; then
        echo "  Adapters DOWN (disabled):"
        echo "$DOWN_ADAPTERS" | while read -r adapter; do
            echo "    - $adapter"
        done
        print_warning "One or more network adapters are disabled."
        # This is a real issue worth flagging in the final exit code,
        # even if IP/Gateway/DNS still resolve via another adapter
        EXIT_CODE=1
    fi

    # ── IPv4 Addresses ────────────────────────────────────────
    print_header "IPv4 ADDRESSES"
    IP_LIST=$(get_ipv4_addresses)
    IP_STATUS=$?

    if [ "$IP_STATUS" -eq 0 ]; then
        echo "$IP_LIST" | while read -r ip; do
            echo "  $ip"
        done
    else
        print_error "No IPv4 address found. Network may be misconfigured."
        echo "  Possible causes:"
        echo "    - Network adapter is disabled"
        echo "    - DHCP server unreachable"
        echo "    - Static IP not assigned"
        EXIT_CODE=1
    fi

    # ── Default Gateway ───────────────────────────────────────
    print_header "DEFAULT GATEWAY"
    GATEWAY=$(get_gateway)
    GATEWAY_STATUS=$?

    if [ "$GATEWAY_STATUS" -eq 0 ]; then
        echo "  $GATEWAY"
    else
        print_error "No default gateway found. Network may be misconfigured."
        echo "  Possible causes:"
        echo "    - This interface is Host-Only by design (no gateway expected)"
        echo "    - NAT adapter did not receive a DHCP lease"
        echo "    - Routing table is empty"
        EXIT_CODE=1
    fi

    # ── DNS Servers ───────────────────────────────────────────
    print_header "DNS SERVERS"
    DNS_LIST=$(get_dns_servers)
    DNS_STATUS=$?

    if [ "$DNS_STATUS" -eq 0 ]; then
        echo "$DNS_LIST" | while read -r dns; do
            echo "  $dns"
        done
    else
        print_error "No DNS servers found. Name resolution will fail."
        echo "  Possible causes:"
        echo "    - /etc/resolv.conf is empty or missing"
        echo "    - systemd-resolved is not running"
        echo "    - No DNS configured in Netplan"
        EXIT_CODE=1
    fi

    # ── Final Summary ─────────────────────────────────────────
    print_header "DIAGNOSTIC SUMMARY"
    if [ "$EXIT_CODE" -eq 0 ]; then
        echo "  Status: ALL CHECKS PASSED"
        echo "  The network configuration appears healthy."
    else
        echo "  Status: ISSUES DETECTED"
        echo "  One or more network components are misconfigured."
        echo "  Review the warnings and errors above for details."
    fi

    echo ""
    print_banner "END OF REPORT"
    echo ""

    return "$EXIT_CODE"
}

# ============================================================
# ENTRY POINT
# ============================================================

main
FINAL_EXIT_CODE=$?

# Explicitly exit with the tracked status code
# 0 = all checks passed | 1 = one or more issues detected
exit "$FINAL_EXIT_CODE"
