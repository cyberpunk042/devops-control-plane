"""
L0 Data — WSL transport channel recipes.

These recipes provision the prerequisites for WSL↔Windows
transport channels used by the CDP communication layer.
Each maps to a tunnel backend in ``wsl_transport.tunnel_backends``.

Categories: wsl_transport
Pure data, no logic.

Backend → Recipe mapping:
    SocatTunnel   → socat-wsl-channel
    SshTunnel     → openssh-server-windows
    MirroredConfig → wsl-mirrored-networking

WslTunnel (python_proxy) and NetshTunnel need no recipe —
they are pure Python + PowerShell with zero external deps.
"""

from __future__ import annotations


_WSL_TRANSPORT_RECIPES: dict[str, dict] = {

    # ── socat — WSL-side socket relay ────────────────────────────
    #
    # Used by SocatTunnel backend. Spawns:
    #   socat TCP-LISTEN:<port>,fork,reuseaddr TCP:<host_ip>:<port>
    # Simple subprocess, zero config. Needs socat binary in WSL.
    #
    # Available in ALL native Linux PMs. Not typically needed on
    # macOS (no WSL). No _default needed — if no PM, can't WSL.
    #
    "socat-wsl-channel": {
        "cli": "socat",
        "label": "socat (WSL channel relay)",
        "category": "wsl_transport",
        "description": (
            "Socket relay for the WSL↔Windows CDP tunnel. "
            "Forwards TCP traffic from WSL localhost to the "
            "Windows host IP where Chrome listens."
        ),
        "install": {
            "apt":    ["apt-get", "install", "-y", "socat"],
            "dnf":    ["dnf", "install", "-y", "socat"],
            "apk":    ["apk", "add", "socat"],
            "pacman": ["pacman", "-S", "--noconfirm", "socat"],
            "zypper": ["zypper", "install", "-y", "socat"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True,
        },
        "prefer": ["apt", "dnf", "apk", "pacman", "zypper"],
        "verify": ["socat", "-V"],
        "update": {
            "apt":    ["apt-get", "install", "-y", "--only-upgrade", "socat"],
            "dnf":    ["dnf", "upgrade", "-y", "socat"],
            "apk":    ["apk", "upgrade", "socat"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "socat"],
            "zypper": ["zypper", "update", "-y", "socat"],
        },
        "rollback": {
            "apt":    ["apt-get", "remove", "-y", "socat"],
            "dnf":    ["dnf", "remove", "-y", "socat"],
            "apk":    ["apk", "del", "socat"],
            "pacman": ["pacman", "-R", "--noconfirm", "socat"],
            "zypper": ["zypper", "remove", "-y", "socat"],
        },
        "risk": "low",
        "notes": (
            "socat is a standard Unix network utility. Installing it "
            "adds no services or daemons — it only runs when explicitly "
            "started by the tunnel backend."
        ),
    },

    # ── OpenSSH Server on Windows ────────────────────────────────
    #
    # Used by SshTunnel backend. The SSH tunnel connects:
    #   ssh -N -L <port>:localhost:<port> <user>@<host_ip>
    # This requires OpenSSH Server to be running on the Windows side.
    #
    # Windows 10/11 include OpenSSH as an "Optional Feature" —
    # it just needs to be enabled and the service started.
    #
    # Cross-system: runs PowerShell commands on the Windows side
    # from within WSL via powershell.exe interop.
    #
    "openssh-server-windows": {
        "cli": "sshd.exe",  # NOT "sshd" — that matches Linux sshd in WSL
        "label": "OpenSSH Server (Windows)",
        "category": "wsl_transport",
        "description": (
            "Enable the Windows built-in OpenSSH Server so the SSH "
            "tunnel backend can create an encrypted channel from "
            "WSL to Windows."
        ),
        "install": {
            # Windows Optional Feature — needs admin elevation (UAC)
            # Start-Process -Verb RunAs triggers the UAC prompt
            "_default": [
                "powershell.exe", "-NoProfile", "-Command",
                "Start-Process powershell -Verb RunAs -Wait "
                "-ArgumentList '-NoProfile -Command "
                "\"Add-WindowsCapability -Online "
                "-Name OpenSSH.Server~~~~0.0.1.0\"'",
            ],
        },
        "needs_sudo": {"_default": False},  # UAC handled by -Verb RunAs
        "post_install": [
            {
                "label": "Start OpenSSH Server service",
                "command": [
                    "powershell.exe", "-NoProfile", "-Command",
                    "Start-Process powershell -Verb RunAs -Wait "
                    "-ArgumentList '-NoProfile -Command "
                    "\"Start-Service sshd\"'",
                ],
                "needs_sudo": False,
            },
            {
                "label": "Set OpenSSH Server to auto-start",
                "command": [
                    "powershell.exe", "-NoProfile", "-Command",
                    "Start-Process powershell -Verb RunAs -Wait "
                    "-ArgumentList '-NoProfile -Command "
                    "\"Set-Service -Name sshd -StartupType Automatic\"'",
                ],
                "needs_sudo": False,
            },
        ],
        "verify": [
            "powershell.exe", "-NoProfile", "-Command",
            "if ((Get-Service sshd -ErrorAction SilentlyContinue).Status "
            "-eq 'Running') { exit 0 } else { exit 1 }",
        ],
        "rollback": {
            "_default": [
                "powershell.exe", "-NoProfile", "-Command",
                "Start-Process powershell -Verb RunAs -Wait "
                "-ArgumentList '-NoProfile -Command \""
                "Stop-Service sshd -ErrorAction SilentlyContinue; "
                "Remove-WindowsCapability -Online "
                "-Name OpenSSH.Server~~~~0.0.1.0\"'",
            ],
        },
        "risk": "medium",
        "risk_detail": (
            "Enables an SSH server on Windows. By default it listens "
            "on all interfaces (port 22). Ensure the Windows Firewall "
            "restricts access to trusted networks only."
        ),
        "restart_required": "none",
        "notes": (
            "Windows 10 (1809+) and Windows 11 include OpenSSH Server "
            "as a built-in Optional Feature. This recipe enables it, "
            "starts the service, and sets it to auto-start. The SSH "
            "tunnel backend in this project uses it for an encrypted "
            "localhost-forwarding channel between WSL and Windows."
        ),
        "requires": {
            "binaries": ["powershell.exe"],
        },
    },

    # ── WSL Mirrored Networking ──────────────────────────────────
    #
    # Used by MirroredConfig backend. Edits .wslconfig to set
    # networkingMode=mirrored. After WSL restart, localhost in WSL
    # reaches Windows localhost natively — no tunnel, no portproxy.
    #
    # Cross-system: modifies a Windows-side config file (.wslconfig)
    # and requires a FULL WSL restart to take effect.
    #
    # RISKY: Can break VS Code Remote, Docker Desktop, and other
    # tools that depend on the default NAT networking mode.
    #
    "wsl-mirrored-networking": {
        "label": "WSL Mirrored Networking",
        "category": "wsl_transport",
        "description": (
            "Switch WSL2 to mirrored networking mode. Localhost in "
            "WSL reaches Windows localhost directly — no tunnel, "
            "no port forwarding, sub-millisecond latency."
        ),
        "install": {
            # Add [wsl2] networkingMode=mirrored to .wslconfig
            "_default": [
                "powershell.exe", "-NoProfile", "-Command",
                "$wslconfig = \"$env:USERPROFILE\\.wslconfig\"; "
                "$content = if (Test-Path $wslconfig) "
                "{ Get-Content $wslconfig -Raw } else { '' }; "
                "if ($content -notmatch 'networkingMode') { "
                "  if ($content -notmatch '\\[wsl2\\]') { "
                "    $content += \"`n[wsl2]`n\"; "
                "  }; "
                "  $content = $content -replace "
                "'(\\[wsl2\\])', \"`$1`nnetworkingMode=mirrored\"; "
                "  Set-Content $wslconfig $content; "
                "  Write-Host 'Added networkingMode=mirrored'; "
                "} else { "
                "  $content = $content -replace "
                "'networkingMode=\\w+', 'networkingMode=mirrored'; "
                "  Set-Content $wslconfig $content; "
                "  Write-Host 'Updated networkingMode to mirrored'; "
                "}",
            ],
        },
        "needs_sudo": {"_default": False},
        "verify": [
            "powershell.exe", "-NoProfile", "-Command",
            "if ((Get-Content \"$env:USERPROFILE\\.wslconfig\" -Raw) "
            "-match 'networkingMode=mirrored') { exit 0 } else { exit 1 }",
        ],
        "rollback": {
            "_default": [
                "powershell.exe", "-NoProfile", "-Command",
                "$wslconfig = \"$env:USERPROFILE\\.wslconfig\"; "
                "if (Test-Path $wslconfig) { "
                "  $content = Get-Content $wslconfig -Raw; "
                "  $content = $content -replace "
                "'networkingMode=mirrored', 'networkingMode=nat'; "
                "  Set-Content $wslconfig $content; "
                "  Write-Host 'Reverted to NAT mode'; "
                "}",
            ],
        },
        "risk": "high",
        "risk_detail": (
            "Mirrored networking changes how WSL2 accesses the network. "
            "Known to break: VS Code Remote WSL extension, Docker "
            "Desktop WSL2 backend, port forwarding assumptions in "
            "development tools. Test thoroughly before committing. "
            "Requires full WSL restart (wsl --shutdown) to take effect."
        ),
        "restart_required": "wsl",
        "notes": (
            "Mirrored networking (available since Windows 11 22H2 / "
            "WSL 2.0.0) makes WSL2 share the Windows network stack. "
            "Localhost in WSL IS Windows localhost. This eliminates "
            "all tunnel/proxy overhead but changes fundamental "
            "networking assumptions. The verify step checks .wslconfig "
            "content — actual activation requires 'wsl --shutdown' "
            "followed by WSL restart."
        ),
        "requires": {
            "binaries": ["powershell.exe"],
        },
    },
}
