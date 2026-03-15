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

            # Summary: use correlation_id for cycles, first event summary for others
            summary = cid
            if not cid.startswith("cycle-"):
                # Use the origin (oldest) event's summary
                summary = group[-1].summary or cid

            chains.append({
                "chain_id": cid,
                "entry_count": len(group),
                "first_ts": first_ts,
                "last_ts": last_ts,
                "summary": summary,
                "sources": sorted(sources),
                "members": members,
            })

        # Sort chains by last_ts descending
        chains.sort(key=lambda c: c["last_ts"], reverse=True)
        return chains
