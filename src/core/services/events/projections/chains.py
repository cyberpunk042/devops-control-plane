"""
Chain projection — groups events by correlation_id into chains.

Each correlation_id becomes a chain. The first event is the origin,
subsequent events are steps. Chains with fewer than 2 members are
excluded (solo events aren't chains).
"""

from __future__ import annotations

from typing import Any

from src.core.services.events.store import EventStore
from src.core.services.events.projections.timeline import (
    _should_suppress,
    _derive_source,
    _derive_subtype,
    _derive_domain,
    _map_status,
)


_DOMAIN_LABELS = {
    "audit": "Audit lifecycle",
    "github": "GitHub status",
    "catalog": "Catalog scan",
    "posture": "Posture check",
    "index": "Index refresh",
    "docker": "Docker status",
    "k8s": "Kubernetes status",
    "terraform": "Terraform status",
    "security": "Security scan",
    "testing": "Test results",
    "quality": "Quality check",
    "env": "Environment status",
    "packages": "Package status",
    "ci": "CI/CD status",
    "dns": "DNS status",
    "docs": "Documentation",
}


def _friendly_chain_name(cid: str, group: list) -> str:
    """Derive a human-friendly name for a chain."""
    from datetime import datetime, UTC

    # Cycle domain sub-chain: "cycle-xxx:audit" → "Audit lifecycle"
    if cid.startswith("cycle-") and ":" in cid:
        domain = cid.split(":")[-1]
        return _DOMAIN_LABELS.get(domain, f"{domain.capitalize()} cycle")

    # Main cycle chain: "cycle-20260315-201710" → "System scan · 20:17"
    if cid.startswith("cycle-"):
        try:
            # Extract time from cycle id: cycle-YYYYMMDD-HHMMSS
            parts = cid.split("-")
            time_part = parts[-1]  # HHMMSS
            hh, mm = time_part[:2], time_part[2:4]
            return f"System scan · {hh}:{mm}"
        except Exception:
            return "System scan"

    # Git branch: "git:main" → "Branch: main"
    if cid.startswith("git:"):
        branch = cid[4:]
        return f"Branch: {branch}"

    # Use the origin event's summary
    if group:
        origin = group[-1]  # oldest event
        if origin.summary and origin.summary != cid:
            return origin.summary

    return cid


class ChainProjection:
    """Builds chain summaries from event store."""

    def __init__(self, store: EventStore) -> None:
        self._store = store

    def build(self) -> list[dict[str, Any]]:
        """Build chain summaries grouped by correlation_id.

        For index cycle chains (cycle-*), entries are further split
        by domain so each domain forms its own chain within the cycle.
        This produces audit, posture, index, docker, etc. chains
        instead of one giant cycle chain.
        """
        events = self._store.all_events()

        # Group by correlation_id
        raw_groups: dict[str, list] = {}
        for event in events:
            if _should_suppress(event):
                continue
            cid = event.correlation_id
            if not cid:
                continue
            raw_groups.setdefault(cid, []).append(event)

        # Split cycle chains by domain AND keep the full cycle
        groups: dict[str, list] = {}
        for cid, group in raw_groups.items():
            if cid.startswith("cycle-"):
                # Keep the full cycle chain (all members)
                groups[cid] = group

                # Also create domain sub-chains for domains with 2+ events
                by_domain: dict[str, list] = {}
                for event in group:
                    if event.type.startswith("index.cycle."):
                        continue  # lifecycle events stay in main chain only
                    domain = _derive_domain(event)
                    by_domain.setdefault(domain, []).append(event)

                for domain, domain_events in by_domain.items():
                    if len(domain_events) >= 2:
                        groups[f"{cid}:{domain}"] = domain_events
            else:
                groups[cid] = group

        chains = []
        for cid, group in groups.items():
            if len(group) < 2:
                continue  # solo events aren't chains

            # Sort newest first
            group.sort(key=lambda e: e.ts, reverse=True)

            sources = set()
            first_ts = float("inf")
            last_ts = 0.0
            members = []

            for i, event in enumerate(group):
                source = _derive_source(event)
                subtype = _derive_subtype(event)
                status = _map_status(event.status)

                sources.add(source.value)
                first_ts = min(first_ts, event.ts)
                last_ts = max(last_ts, event.ts)

                role = "origin" if i == len(group) - 1 else "step"  # oldest = origin
                if event.type.endswith(".started") or event.type.endswith(".created"):
                    role = "origin"

                members.append({
                    "id": event.id,
                    "ts": event.ts,
                    "source": source.value,
                    "subtype": subtype,
                    "status": status.value,
                    "locality": "local",
                    "summary": event.summary or event.type,
                    "chain_role": role,
                    "chain_parent_ref": event.causation_id,
                })

            # Friendly summary
            summary = _friendly_chain_name(cid, group)

            chains.append({
                "chain_id": cid,
                "entry_count": len(group),
                "first_ts": first_ts,
                "last_ts": last_ts,
                "summary": summary,
                "sources": sorted(sources),
                "members": members,
            })

        # Sort: user/meaningful chains first, cycle infrastructure last
        def _chain_sort_key(c):
            is_cycle = c["chain_id"].startswith("cycle-")
            return (is_cycle, -c["last_ts"])  # False < True, so non-cycle comes first
        chains.sort(key=_chain_sort_key)
        return chains
