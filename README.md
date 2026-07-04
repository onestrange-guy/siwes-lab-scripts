## 🖥️ Network Diagnostic Scripts

Cross-platform network diagnostic tools that automatically detect the operating system and run the appropriate commands.

### Scripts Available

| Script | Platform | Language |
|---|---|---|
| `script/network_detect.sh` | Linux (Ubuntu) | Bash |
| `script/network_detect.ps1` | Windows Server | PowerShell |
| `script/network_info.py` | Both (auto-detects) | Python |

---

### Requirements

**Windows (DC01):**
- PowerShell 5.0 or higher
- Run as Administrator for full output

**Linux/Ubuntu (DNS01):**
- Bash 4.0 or higher
- `iproute2` package (installed by default on Ubuntu)
- `systemd-resolved` for DNS detection

---

### Installation

**On Ubuntu (DNS01):**
```bash
# Clone or download the script
wget https://raw.githubusercontent.com/onestrange-guy/siwes-server-lab/main/script/network_detect.sh

# Make executable
chmod +x network_detect.sh

# Run
./network_detect.sh
```

**On Windows (DC01):**
```powershell
# Download the script
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/onestrange-guy/siwes-server-lab/main/script/network_detect.ps1" -OutFile "network_detect.ps1"

# Run
.\network_detect.ps1
```

---

### Expected Output

**Windows:**
==================================================
NETWORK INFORMATION REPORT
Script Author : Israel
Date          : 4 July 2026
Shell         : PowerShell
[SYSTEM]
Detected OS : Windows
Hostname    : DC01
OS Version  : Microsoft Windows Server 2022
[IPv4 ADDRESS]
IP Address  : 10.10.10.10
Subnet Mask : /24
Interface   : Ethernet 2
[DEFAULT GATEWAY]
Gateway : 10.10.10.1
[DNS SERVERS]
DNS : 8.8.8.8
DNS : 8.8.4.4

**Ubuntu:**
==================================================
NETWORK INFORMATION REPORT
Script Author : Israel
Date          : 4 July 2026
Shell         : Bash
[SYSTEM]
Detected OS : LINUX
Hostname    : dns01
[IPv4 ADDRESS]
IP Address  : 10.10.10.20
Subnet Mask : /24
[DEFAULT GATEWAY]
Gateway : 10.10.10.1
[DNS SERVERS]
DNS : 8.8.8.8
DNS : 8.8.4.4

---

### Troubleshooting

**"Permission denied" on Linux:**
```bash
chmod +x network_detect.sh
```

**"Cannot be loaded" error on Windows:**
```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**Gateway shows 10.0.2.2 instead of lab gateway:**
This is the VirtualBox NAT gateway — expected if enp0s3 (NAT adapter) is overriding the default route. Check `ip route show` to confirm the lab route exists.

**DNS shows unexpected IP (e.g. 192.168.x.x):**
This is a DHCP-provided DNS from the NAT adapter. It is normal behaviour — your manually configured DNS (8.8.8.8) is also present.
