"""WSL↔Windows tunnel backends — re-export stub.

The implementation has moved to ``wsl_transport.tunnel_backends``.
This stub preserves backward compatibility for existing importers.
"""

from src.core.services.wsl_transport.tunnel_backends import (  # noqa: F401
    WslTunnel,
    SocatTunnel,
    NetshTunnel,
    SshTunnel,
    MirroredConfig,
    TUNNEL_METHODS,
    get_active_tunnel,
    start_tunnel,
    stop_tunnel,
)
