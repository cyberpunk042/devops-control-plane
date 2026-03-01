"""
Docker & Compose operations — backward-compat re-export hub.

All implementation has moved to ``src.core.services.docker/``.
This file re-exports everything so existing ``from src.core.services.docker_ops import X``
continues to work.
"""

from src.core.services.docker import *  # noqa: F401, F403
