"""Network topology discovery for WSL2↔Windows transport.

Answers: "how can we reach the Windows host?" and "what network
mode are we in?"

Unlike ``environment.py`` (which reads files and calls ``which``),
these checks probe actual TCP connections and DNS resolution.

Functions:
    resolve_host_ip  — hostname.local → IP via mDNS (cached)
    is_mirrored      — WSL2 mirrored networking active? (cached)
    direct_http_reachable — TCP probe to host_ip:port
    localhost_reachable   — TCP probe to localhost:port
"""

from __future__ import annotations

import logging
import socket
import subprocess

logger = logging.getLogger(__name__)


# ── Host IP resolution (cached) ──────────────────────────────

_host_ip: str | None = None
_host_ip_resolved: bool = False


def resolve_host_ip() -> str | None:
    """Resolve ``hostname.local`` → IP via mDNS.  Cached.

    When WSL2 has ``netsh portproxy`` + firewall rule set up,
    Chrome (or any Windows-side service) is reachable at
    ``hostname.local:<port>`` via direct Python socket.
    This is the fastest path (~5 ms) — no subprocess, no tunnel.

    Calls ``hostname`` subprocess once, then ``getaddrinfo()``
    on ``<hostname>.local``.

    Returns the IP string (e.g. ``"172.17.128.1"``) or None if
    resolution fails.
    """
    global _host_ip, _host_ip_resolved
    if _host_ip_resolved:
        return _host_ip

    _host_ip_resolved = True
    try:
        r = subprocess.run(
            ["hostname"],
            capture_output=True, text=True, timeout=3,
        )
        hostname = r.stdout.strip()
        if not hostname:
            return None

        fqdn = f"{hostname}.local"
        infos = socket.getaddrinfo(
            fqdn, None,
            socket.AF_INET, socket.SOCK_STREAM,
        )
        if infos:
            _host_ip = infos[0][4][0]
            logger.info(
                "Windows host IP resolved: %s → %s",
                fqdn, _host_ip,
            )
    except Exception:
        pass

    return _host_ip


# ── Mirrored networking detection (cached) ────────────────────

_is_mirrored: bool | None = None


def is_mirrored() -> bool:
    """Check if WSL2 mirrored networking is active.

    When mirrored networking is enabled (via ``.wslconfig``), WSL2
    shares the Windows network interface.  ``localhost`` in WSL
    reaches Windows ``localhost`` directly — no tunnel, no portproxy.

    Detection: try connecting to localhost on a port that is
    typically NOT open (port 135 — Windows RPC, always listening
    on Windows but not on standard Linux).  If it connects from
    WSL, we're mirrored.

    This is cached after first check.  Returns False on non-WSL2.

    ⚠️  Mirrored networking may break VS Code, Docker Desktop,
    and other IDE networking.  The transport router treats this
    as the fastest channel but never enables it automatically.
    """
    global _is_mirrored

    if _is_mirrored is not None:
        return _is_mirrored

    from .environment import is_wsl2

    if not is_wsl2():
        _is_mirrored = False
        return False

    # Port 135 (MS-RPC) is always open on Windows.
    # On regular WSL2, localhost:135 is unreachable (different network).
    # On mirrored WSL2, localhost:135 connects to the Windows RPC service.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3)
        s.connect(("127.0.0.1", 135))
        s.close()
        _is_mirrored = True
        logger.info("WSL2 mirrored networking detected (localhost:135 reachable)")
    except (ConnectionRefusedError, OSError, TimeoutError):
        _is_mirrored = False

    return _is_mirrored


# ── Reachability probes (not cached — state can change) ───────


def direct_http_reachable(host_ip: str, port: int,
                          timeout: float = 0.5) -> bool:
    """Quick TCP probe: can we connect to ``host_ip:port``?

    Used by the transport router to test if the direct channel
    (via hostname.local) is working for a given port.

    Not cached — a port may become reachable or unreachable
    as services start and stop.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host_ip, port))
        s.close()
        return True
    except (ConnectionRefusedError, OSError, TimeoutError):
        return False


def localhost_reachable(port: int, timeout: float = 0.5) -> bool:
    """Quick TCP probe: can we connect to ``localhost:port``?

    Returns True if reachable — either because a tunnel is
    forwarding this port, or because mirrored networking is active.

    Not cached — tunnel state can change.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(("127.0.0.1", port))
        s.close()
        return True
    except (ConnectionRefusedError, OSError, TimeoutError):
        return False
