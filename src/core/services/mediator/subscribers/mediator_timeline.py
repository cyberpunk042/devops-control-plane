"""
Mediator timeline subscriber — direct timeline entry production.

Subscribes to ALL mediator ``"computed"`` events.  For each computation,
creates a ``TimelineEntry`` directly in memory — no file I/O, no adapter
indirection.

The entries accumulate in a thread-safe ring buffer.  The timeline source
node ``timeline.source.mediator`` returns the buffer contents.

This replaces the indirect path:
  activity subscriber → audit_activity.json → ScanActivityAdapter

With the direct path:
  mediator computed → TimelineEntry → in-memory buffer → timeline.source.mediator
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

from src.core.services.mediator.core import QueryMediator
from src.core.services.timeline.models import (
    Actor,
    ChainRole,
    EntryStatus,
    Locality,
    Severity,
    Source,
    TimelineEntry,
)

logger = logging.getLogger(__name__)

# ── Ring buffer ───────────────────────────────────────────────────────

_MAX_ENTRIES = 2000
_lock = threading.Lock()
_entries: deque[TimelineEntry] = deque(maxlen=_MAX_ENTRIES)


def get_entries() -> list[TimelineEntry]:
    """Return all buffered entries (newest first).  Thread-safe."""
    with _lock:
        return list(_entries)


def _append(entry: TimelineEntry) -> None:
    with _lock:
        _entries.append(entry)


# ── Path → (Source, subtype) mapping ──────────────────────────────────

_PATH_MAP: dict[str, tuple[Source, str | None]] = {
    # DevOps
    "devops.docker":     (Source.PLATFORM, "docker"),
    "devops.k8s":        (Source.PLATFORM, "k8s"),
    "devops.git":        (Source.GIT,      "git status"),
    "devops.github":     (Source.GIT,      "github"),
    "devops.ci":         (Source.CI,       "ci scan"),
    "devops.terraform":  (Source.PLATFORM, "terraform"),
    "devops.env":        (Source.ENV,      "env"),
    "devops.security":   (Source.SECURITY, "security scan"),
    "devops.packages":   (Source.PKG,      "packages"),
    "devops.quality":    (Source.TESTS,    "quality"),
    "devops.testing":    (Source.TESTS,    "testing scan"),
    "devops.docs":       (Source.PLATFORM, "docs"),
    "devops.dns":        (Source.PLATFORM, "dns"),
    "devops.status":     (Source.PLATFORM, "status"),
    # GitHub
    "github.pulls":      (Source.GIT,      "pulls"),
    "github.runs":       (Source.CI,       "runs"),
    "github.workflows":  (Source.CI,       "workflows"),
    # Audit
    "audit.scores":      (Source.AUDIT, "scores"),
    "audit.system":      (Source.AUDIT, "L1"),
    "audit.deps":        (Source.AUDIT, "deps"),
    "audit.structure":   (Source.AUDIT, "structure"),
    "audit.clients":     (Source.AUDIT, "clients"),
    "audit.system_deep": (Source.AUDIT, "L1:deep"),
    "audit.l2_structure":(Source.AUDIT, "L2:structure"),
    "audit.l2_quality":  (Source.AUDIT, "L2:quality"),
    "audit.l2_repo":     (Source.AUDIT, "L2:repo"),
    "audit.l2_risks":    (Source.AUDIT, "L2:risks"),
    "audit.scores_enriched": (Source.AUDIT, "scores:enriched"),
    # Index
    "index.scan":        (Source.PLATFORM, "index:scan"),
    "index.delta":       (Source.PLATFORM, "index:delta"),
    "index.files":       (Source.PLATFORM, "index:files"),
    "index.dirs":        (Source.PLATFORM, "index:dirs"),
    "index.paths":       (Source.PLATFORM, "index:paths"),
    "index.classify":    (Source.PLATFORM, "index:classify"),
    "index.symbols":     (Source.PLATFORM, "index:symbols"),
    "index.stats":       (Source.PLATFORM, "index:stats"),
    "index.view":        (Source.PLATFORM, "index:view"),
    "index.peek":        (Source.PLATFORM, "index:peek"),
    # Posture
    "posture.full":      (Source.POSTURE, "full"),
    "posture.summary":   (Source.POSTURE, "summary"),
    "posture.platform":  (Source.POSTURE, "platform"),
    "posture.project":   (Source.POSTURE, "project"),
    "posture.toolchain": (Source.POSTURE, "toolchain"),
    # Catalog
    "catalog.tools":     (Source.TOOLS,    None),
    "catalog.builders":  (Source.TOOLS,    "builders"),
    "catalog.scripts":   (Source.TOOLS,    "scripts"),
    "catalog.pages":     (Source.PLATFORM, "pages"),
}

# ── Path → domain name (used as adapter tag in facets) ────────────────
# This determines how entries group in the Domains side-panel.

_PATH_DOMAIN: dict[str, str] = {
    "devops.docker": "docker", "devops.k8s": "k8s",
    "devops.terraform": "terraform", "devops.git": "integrations",
    "devops.github": "integrations", "devops.ci": "ci",
    "devops.env": "env", "devops.security": "security",
    "devops.packages": "packages", "devops.quality": "quality",
    "devops.testing": "testing", "devops.docs": "docs",
    "devops.dns": "dns", "devops.status": "server",
    "github.pulls": "github", "github.runs": "github",
    "github.workflows": "github",
    "audit.scores": "audit", "audit.system": "audit",
    "audit.deps": "audit", "audit.structure": "audit",
    "audit.clients": "audit", "audit.system_deep": "audit",
    "audit.l2_structure": "audit", "audit.l2_quality": "audit",
    "audit.l2_repo": "audit", "audit.l2_risks": "audit",
    "audit.scores_enriched": "audit",
    "index.scan": "index", "index.delta": "index",
    "index.files": "index", "index.dirs": "index",
    "index.paths": "index", "index.classify": "index",
    "index.symbols": "index", "index.stats": "index",
    "index.view": "index", "index.peek": "index",
    "posture.full": "posture", "posture.summary": "posture",
    "posture.platform": "posture", "posture.project": "posture",
    "posture.toolchain": "posture",
    "catalog.tools": "tools", "catalog.builders": "tools",
    "catalog.scripts": "tools", "catalog.pages": "pages",
}


def get_domain(path: str) -> str:
    """Return the domain name for a mediator path (used as adapter tag)."""
    return _PATH_DOMAIN.get(path, "mediator")

# Paths to suppress — internal timeline/feed recomputations, not user-visible
_SUPPRESS_PREFIXES = (
    "timeline.",
    "detect.",
    "tabmesh.",
)


def _map_path(path: str) -> tuple[Source, str | None] | None:
    """Map mediator path to (Source, subtype).  Returns None to suppress."""
    # Suppress internal nodes
    for prefix in _SUPPRESS_PREFIXES:
        if path.startswith(prefix):
            return None

    if path in _PATH_MAP:
        return _PATH_MAP[path]

    # Fallback: use domain as source hint, rest as subtype
    parts = path.split(".", 1)
    return Source.PLATFORM, parts[1] if len(parts) > 1 else path


def _map_status(data: Any) -> tuple[EntryStatus, str]:
    """Determine status and error message from resolver data."""
    if isinstance(data, dict) and "error" in data:
        return EntryStatus.FAILED, str(data["error"])[:200]
    return EntryStatus.OK, ""


def _extract_summary(path: str, data: Any) -> str:
    """Best-effort one-line summary from resolver output."""
    # Friendly name from path: "devops.docker" → "docker", "audit.l2_risks" → "l2_risks"
    short = path.split(".", 1)[-1] if "." in path else path

    if isinstance(data, dict):
        # Try common summary fields
        for key in ("summary", "label", "message"):
            val = data.get(key)
            if isinstance(val, str) and val:
                return val[:120]
        # Count-based summary
        if "count" in data:
            return f"{short}: {data['count']} items"
        # Key count
        return f"{short}: {len(data)} keys"
    if isinstance(data, list):
        return f"{short}: {len(data)} entries"
    if data is None:
        return short
    return short


# ── Subscriber callback ──────────────────────────────────────────────

def _on_computed(event: dict[str, Any]) -> None:
    """Create a TimelineEntry for each mediator computation."""
    if event.get("type") != "computed":
        return

    meta = event.get("compute_meta")
    if meta is None:
        return

    paths = event.get("paths", [])
    if not paths:
        return

    path = paths[0]
    mapping = _map_path(path)
    if mapping is None:
        return  # suppressed

    source, subtype = mapping
    data = meta.get("data", {})
    elapsed_s = meta.get("elapsed_s", 0.0)
    computed_at = meta.get("computed_at", time.time())

    status, error_msg = _map_status(data)
    summary = _extract_summary(path, data)
    if error_msg:
        summary = f"{path}: {error_msg}"

    # Severity
    severity: Severity | None = None
    if status == EntryStatus.FAILED:
        severity = Severity.HIGH if source in (Source.SECURITY, Source.AUDIT) else Severity.MEDIUM

    # Chain: use operation_id from thread-local context (set by index watcher or @run_tracked)
    chain_id: str | None = None
    chain_role: ChainRole | None = None
    chain_parent_ref: str | None = None
    try:
        from src.core.engine.operation_context import get_operation_id
        op_id = get_operation_id()
        if op_id:
            chain_id = op_id
            chain_role = ChainRole.STEP
            chain_parent_ref = op_id
    except Exception:
        pass

    entry = TimelineEntry(
        id=f"mediator:{path}:{computed_at:.6f}",
        ts=computed_at,
        ref=path,
        source=source,
        subtype=subtype,
        actor=Actor.SCHEDULER,
        status=status,
        severity=severity,
        locality=Locality.LOCAL,
        env=[],
        modules=[],
        summary=summary,
        detail={
            "elapsed_s": round(elapsed_s, 3),
            "path": path,
            "error": error_msg,
        } if error_msg else {
            "elapsed_s": round(elapsed_s, 3),
            "path": path,
        },
        chain_id=chain_id,
        chain_role=chain_role,
        chain_parent_ref=chain_parent_ref,
    )

    _append(entry)


# ── Registration ─────────────────────────────────────────────────────

_project_root = None


def register_mediator_timeline_subscriber(mediator: QueryMediator) -> str:
    """Register the direct timeline subscriber on the mediator.

    Subscribes to all paths.  Also seeds the buffer with any
    already-cached nodes (from warm start hydration) so the timeline
    has data immediately without waiting for recomputation.
    """
    global _project_root
    _project_root = mediator.project_root

    sub_id = mediator.subscribe("*", _on_computed)

    # Seed buffer with already-cached nodes (warm start hydration).
    # hydrate_cache uses notify=False, so the subscriber misses those.
    _seed_from_cache(mediator)

    logger.info(
        "mediator: timeline direct subscriber registered (sub_id=%s, "
        "seeded %d entries from cache)", sub_id, len(_entries),
    )
    return sub_id


def _seed_from_cache(mediator: QueryMediator) -> None:
    """Read all cached mediator nodes and create initial timeline entries."""
    for path in mediator.tree.all_paths():
        mapping = _map_path(path)
        if mapping is None:
            continue  # suppressed

        try:
            result = mediator.peek(path)
            if result is None:
                continue
            data = result.get("data")
            if data is None:
                continue

            source, subtype = mapping
            computed_at = result.get("computed_at", time.time())
            status, error_msg = _map_status(data)
            summary = _extract_summary(path, data)

            entry = TimelineEntry(
                id=f"mediator:{path}:{computed_at:.6f}",
                ts=computed_at,
                ref=path,
                source=source,
                subtype=subtype,
                actor=Actor.SCHEDULER,
                status=status,
                severity=None,
                locality=Locality.LOCAL,
                env=[],
                modules=[],
                summary=summary,
                detail={
                    "elapsed_s": 0.0,
                    "path": path,
                    "source": "hydrated",
                },
                chain_id=None,
                chain_role=None,
                chain_parent_ref=None,
            )
            _append(entry)
        except Exception:
            pass  # skip nodes that can't be peeked
