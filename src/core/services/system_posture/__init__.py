"""
System Posture — environment awareness and deprecation ranking.

Assesses four pillars:
  - Platform:  OS, kernel, glibc, WSL, architecture
  - Toolchain: Installed tool versions vs current/EOL
  - Project:   Code health score (bridges to /metrics/health)
  - Runtime:   Circuit breakers, retry queue, integration adapters

Public API::

    from src.core.services.system_posture import scan_posture, get_summary

    posture = scan_posture()           # Full scan (cached per-pillar TTL)
    summary = get_summary()            # Lightweight dict for nav badge
    scan_posture(force=True)           # Bypass cache
    cache_stats()                      # Diagnostics
"""

from .orchestrator import (
    cache_stats,
    get_summary,
    scan_posture,
)

__all__ = [
    "scan_posture",
    "get_summary",
    "cache_stats",
]
