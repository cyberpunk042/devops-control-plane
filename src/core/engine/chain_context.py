"""
Chain context — server-side session chains for grouping related runs.

Some operations span multiple HTTP requests but are logically connected:
  - Vault: unlock → key ops → lock (session chain)
  - Pages: build → deploy (pipeline chain)
  - Audit: L0 → L1 → L2 → scores (lifecycle chain)

This module provides a simple key-value store for active chains.
Routes that start a chain call ``start_chain()``, routes that continue
call ``get_chain()``, and routes that end call ``end_chain()``.

The chain info is stored in the Run's metadata dict under ``_chain_id``,
``_chain_role``, and ``_chain_parent_ref``.  The RunsAdapter reads these
to set the TimelineEntry chain fields.

Storage is in-memory (dict) — chains don't survive server restart,
which is fine since they represent active sessions.
"""

from __future__ import annotations

import time

_active_chains: dict[str, dict] = {}


def start_chain(domain: str, chain_id: str) -> None:
    """Register a new active chain for the given domain.

    Args:
        domain: The chain domain (e.g., "vault", "pages:segment_name").
        chain_id: Unique chain identifier.
    """
    _active_chains[domain] = {
        "chain_id": chain_id,
        "started_at": time.time(),
    }


def get_chain(domain: str) -> str | None:
    """Get the active chain_id for a domain, or None if no chain is active."""
    entry = _active_chains.get(domain)
    if entry is None:
        return None
    # Expire chains older than 24h (safety net)
    if time.time() - entry["started_at"] > 86400:
        _active_chains.pop(domain, None)
        return None
    return entry["chain_id"]


def end_chain(domain: str) -> str | None:
    """End the active chain for a domain.  Returns the chain_id or None."""
    entry = _active_chains.pop(domain, None)
    return entry["chain_id"] if entry else None
