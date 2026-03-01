"""
Kubernetes operations — backward-compat re-export hub.

All implementation has moved to ``src.core.services.k8s/``.
This file re-exports everything so existing ``from src.core.services.k8s_ops import X``
continues to work.
"""

from src.core.services.k8s import *  # noqa: F401, F403
