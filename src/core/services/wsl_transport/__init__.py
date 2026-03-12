"""WSL Transport — adaptive networking for WSL2↔Windows communication.

Provides a unified, environment-aware transport layer that automatically
discovers the fastest available path to reach TCP ports on the Windows
host from within WSL2.

Supports multiple backends: direct socket, TCP tunnel (python_proxy,
socat, netsh, ssh), mirrored networking, curl.exe bridge, and
PowerShell bridge.

Modules:
    environment     — system capability detection (WSL2? tools?)
    network         — host resolution, mirrored detection, reachability
    websocket       — raw WebSocket client (protocol-agnostic)
    tunnel_backends — TCP tunnel implementations (python_proxy, socat, etc.)
    curl_bridge     — HTTP requests via curl.exe subprocess
    ps_bridge       — PowerShell bridge (warm process + one-shot)
    router          — TransportRouter (adaptive channel selection)

Usage (once fully wired)::

    from src.core.services.wsl_transport import get_router

    router = get_router()
    data = router.http_get(9222, "/json/version")
    ws = router.connect_ws("ws://...:9222/devtools/page/ABC")
"""

# Public API
from src.core.services.wsl_transport.router import get_router  # noqa: F401

__all__ = ["get_router"]
