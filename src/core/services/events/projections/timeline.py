"""
Timeline projection — builds TimelineEntry list from events.

Maps each event to a TimelineEntry with proper source, subtype,
domain, chain_id, and actor. The event type prefix IS the domain.
"""

from __future__ import annotations

from typing import Any

from src.core.services.events.models import Event
from src.core.services.events.store import EventStore
from src.core.services.timeline.models import (
    Actor,
    ChainRole,
    EntryStatus,
    Locality,
    Severity,
    Source,
    TimelineEntry,
)


# ── Event type → (Source, subtype) mapping ────────────────────────────
# The event type is a dotted string. We derive Source from the domain
# and subtype from the specific operation.

_DOMAIN_SOURCE: dict[str, Source] = {
    "mediator": Source.PLATFORM,
    "index": Source.PLATFORM,
    "vault": Source.VAULT,
    "content": Source.PLATFORM,
    "pages": Source.PLATFORM,
    "docker": Source.PLATFORM,
    "k8s": Source.PLATFORM,
    "terraform": Source.PLATFORM,
    "backup": Source.BACKUP,
    "git": Source.GIT,
    "ci": Source.CI,
    "quality": Source.TESTS,
    "testing": Source.TESTS,
    "security": Source.SECURITY,
    "secrets": Source.CONFIG,
    "tools": Source.TOOLS,
    "plan": Source.PLAN,
    "script": Source.PLATFORM,
    "trace": Source.TESTS,
    "cdp_test": Source.TESTS,
    "changelog": Source.PLATFORM,
    "artifact": Source.PLATFORM,
    "wizard": Source.WIZARD,
    "server": Source.PLATFORM,
    "notification": Source.PLATFORM,
    "audit": Source.AUDIT,
    "posture": Source.POSTURE,
    "catalog": Source.TOOLS,
    "devops": Source.PLATFORM,
    "github": Source.CI,
}

# Mediator path → override source (for mediator.computed events)
_PATH_SOURCE: dict[str, Source] = {
    "devops.git": Source.GIT,
    "devops.github": Source.GIT,
    "devops.ci": Source.CI,
    "devops.env": Source.ENV,
    "devops.security": Source.SECURITY,
    "devops.packages": Source.PKG,
    "devops.quality": Source.TESTS,
    "devops.testing": Source.TESTS,
    "github.pulls": Source.GIT,
    "github.runs": Source.CI,
    "github.workflows": Source.CI,
}

# Mediator path → subtype override (for readable subtypes)
_PATH_SUBTYPE: dict[str, str] = {
    "devops.git": "git status",
    "devops.ci": "ci scan",
    "devops.security": "security scan",
    "devops.testing": "testing scan",
    "devops.env": "env",
    "devops.packages": "packages",
    "devops.status": "status",
    "audit.system": "L1",
    "audit.system_deep": "L1:deep",
    "audit.l2_structure": "L2:structure",
    "audit.l2_quality": "L2:quality",
    "audit.l2_repo": "L2:repo",
    "audit.l2_risks": "L2:risks",
    "audit.scores_enriched": "scores:enriched",
}

# Prefixes where domain = suffix (bag-of-integrations pattern)
_SUFFIX_PREFIXES = ("devops.", "catalog.")


def _derive_domain(event: Event) -> str:
    """Derive the domain adapter name from an event.

    Semantic event types make this simple:
      docker.scanned → "docker"
      audit.scores.computed → "audit"
      vault.unlocked → "vault"
      index.scanned → "index"
    """
    parts = event.type.split(".")
    return parts[0]


def _derive_source(event: Event) -> Source:
    """Derive timeline Source from event type domain."""
    domain = event.type.split(".")[0]
    return _DOMAIN_SOURCE.get(domain, Source.PLATFORM)


def _derive_subtype(event: Event) -> str:
    """Derive timeline subtype from semantic event type.

    docker.scanned → "scanned"
    audit.scores.computed → "scores.computed"
    vault.key.added → "key.added"
    index.delta.computed → "delta.computed"
    """
    parts = event.type.split(".", 1)
    return parts[1] if len(parts) > 1 else event.type


def _map_status(status: str) -> EntryStatus:
    if status == "error":
        return EntryStatus.FAILED
    if status == "warning":
        return EntryStatus.WARNING
    return EntryStatus.OK


def _map_actor(event: Event) -> Actor:
    if event.origin == "user" or event.actor == "user":
        return Actor.USER
    if event.actor == "automation":
        return Actor.AUTOMATION
    return Actor.SCHEDULER


def _should_suppress(event: Event) -> bool:
    """Suppress internal events that shouldn't appear in the timeline."""
    # Suppress infrastructure events
    if event.type in ("mediator.invalidated", "mediator.cached"):
        return True
    # Suppress internal node computations
    if event.path and event.path.startswith(("timeline.", "detect.", "tabmesh.")):
        return True
    return False


class TimelineProjection:
    """Builds TimelineEntry list from event store."""

    def __init__(self, store: EventStore) -> None:
        self._store = store

    def build(self, limit: int = 5000) -> list[dict[str, Any]]:
        """Build timeline entries from all events."""
        events = self._store.all_events()
        entries = []

        for event in events:
            if _should_suppress(event):
                continue

            source = _derive_source(event)
            subtype = _derive_subtype(event)
            domain = _derive_domain(event)
            status = _map_status(event.status)
            actor = _map_actor(event)

            severity = None
            if status == EntryStatus.FAILED:
                severity = (Severity.HIGH
                            if source in (Source.SECURITY, Source.AUDIT)
                            else Severity.MEDIUM)

            chain_role = ChainRole.STEP
            if event.type.endswith(".started") or event.type.endswith(".created"):
                chain_role = ChainRole.ORIGIN
            elif event.type.endswith(".completed") or event.type.endswith(".done"):
                chain_role = ChainRole.TERMINAL

            entry = TimelineEntry(
                id=event.id,
                ts=event.ts,
                ref=event.path or event.type,
                source=source,
                subtype=subtype,
                actor=actor,
                status=status,
                severity=severity,
                locality=Locality.LOCAL,
                env=[],
                modules=[],
                summary=event.summary,
                detail=event.detail,
                chain_id=event.correlation_id or None,
                chain_role=chain_role if event.correlation_id else None,
                chain_parent_ref=event.causation_id,
            )

            d = entry.to_dict()
            d["adapter"] = domain
            entries.append((domain, entry, d))

        return entries
