"""
Operation Tracker — single service for tracking all operations.

Every operation in the system (user-initiated or system-initiated) flows
through this tracker:

    op = tracker.begin("system", "cycle:20260315-031504")
    # ... mediator computes nodes, each calls tracker.record_computation()
    tracker.end(op, "ok", "Index cycle: 52 nodes")

The tracker:
  1. Owns the thread-local operation context (replaces operation_context.py)
  2. Accumulates computation steps during the operation
  3. Produces TimelineEntry objects as output (replaces mediator_timeline subscriber)
  4. Manages multi-request chains (replaces chain_context.py)
  5. Emits SSE events for live UI updates

Thread-safe. Fail-safe (tracking errors never break operations).
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ── Data Objects ──────────────────────────────────────────────────────


@dataclass
class OperationStep:
    """One computation step within an operation."""
    ts: float
    path: str           # mediator path: "devops.docker", "audit.scores"
    domain: str         # derived: "docker", "audit", "posture"
    subtype: str        # derived: "docker", "scores", "full"
    source: str         # timeline source: "platform", "audit", "ci"
    status: str         # "ok", "error"
    elapsed_s: float
    summary: str
    detail: dict = field(default_factory=dict)


@dataclass
class Operation:
    """A tracked operation — from begin() to end()."""
    id: str
    origin: str         # "user" or "system"
    trigger: str        # "cycle:20260315", "route:vault_unlock", "cli:detect"
    started_at: float
    steps: list[OperationStep] = field(default_factory=list)
    chain_id: str | None = None
    chain_role: str | None = None
    meta: dict = field(default_factory=dict)
    status: str = "ok"
    summary: str = ""
    ended_at: float = 0.0


# ── Domain derivation ────────────────────────────────────────────────

_SUFFIX_PREFIXES = ("devops.", "catalog.")


def derive_domain(path: str) -> str:
    """Derive domain name from a mediator path.

    devops.docker → "docker"   (suffix — devops is a bag of integrations)
    catalog.tools → "tools"    (suffix — same pattern)
    audit.scores  → "audit"    (prefix — cohesive domain)
    posture.full  → "posture"  (prefix)
    github.pulls  → "github"   (prefix)
    index.scan    → "index"    (prefix)
    """
    if "." not in path:
        return path
    prefix, suffix = path.split(".", 1)
    if any(path.startswith(p) for p in _SUFFIX_PREFIXES):
        return suffix
    return prefix


# ── Source mapping ───────────────────────────────────────────────────

def derive_source(path: str) -> str:
    """Derive timeline source value from a mediator path."""
    from src.core.services.timeline.models import Source

    _PREFIX_SOURCE = {
        "devops": {
            "docker": Source.PLATFORM, "k8s": Source.PLATFORM,
            "terraform": Source.PLATFORM, "git": Source.GIT,
            "github": Source.GIT, "ci": Source.CI,
            "env": Source.ENV, "security": Source.SECURITY,
            "packages": Source.PKG, "quality": Source.TESTS,
            "testing": Source.TESTS, "docs": Source.PLATFORM,
            "dns": Source.PLATFORM, "status": Source.PLATFORM,
        },
        "audit": Source.AUDIT,
        "posture": Source.POSTURE,
        "github": Source.CI,
        "index": Source.PLATFORM,
        "catalog": Source.TOOLS,
    }

    if "." not in path:
        return Source.PLATFORM.value
    prefix, suffix = path.split(".", 1)

    mapping = _PREFIX_SOURCE.get(prefix)
    if isinstance(mapping, dict):
        src = mapping.get(suffix, Source.PLATFORM)
        return src.value
    if mapping is not None:
        return mapping.value
    return Source.PLATFORM.value


def derive_subtype(path: str) -> str:
    """Derive timeline subtype from a mediator path."""
    if "." not in path:
        return path
    prefix, suffix = path.split(".", 1)

    # For devops: use the suffix with context
    _DEVOPS_SUBTYPES = {
        "git": "git status", "ci": "ci scan",
        "security": "security scan", "testing": "testing scan",
        "env": "env", "packages": "packages",
        "status": "status",
    }
    if prefix == "devops":
        return _DEVOPS_SUBTYPES.get(suffix, suffix)

    # For index: prefix with "index:"
    if prefix == "index":
        return f"index:{suffix}"

    # For everything else: use the suffix directly
    return suffix


# ── Suppression ──────────────────────────────────────────────────────

_SUPPRESS_PREFIXES = ("timeline.", "detect.", "tabmesh.")


def should_suppress(path: str) -> bool:
    """Return True if this mediator path should not produce timeline entries."""
    return any(path.startswith(p) for p in _SUPPRESS_PREFIXES)


# ── Summary extraction ───────────────────────────────────────────────

def extract_summary(path: str, data: Any) -> str:
    """Best-effort one-line summary from resolver output."""
    short = path.split(".", 1)[-1] if "." in path else path
    if isinstance(data, dict):
        for key in ("summary", "label", "message"):
            val = data.get(key)
            if isinstance(val, str) and val:
                return val[:120]
        if "count" in data:
            return f"{short}: {data['count']} items"
        return f"{short}: {len(data)} keys"
    if isinstance(data, list):
        return f"{short}: {len(data)} entries"
    if data is None:
        return short
    return short


# ── The Tracker ──────────────────────────────────────────────────────

_MAX_COMPLETED = 2000  # ring buffer size for completed entries

_local = threading.local()


class OperationTracker:
    """Single service for tracking all operations in the system."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._completed: deque[Operation] = deque(maxlen=_MAX_COMPLETED)
        self._chains: dict[str, dict] = {}  # active multi-request chains

    # ── Lifecycle ─────────────────────────────────────────────────

    def begin(
        self,
        origin: str,
        trigger: str,
        *,
        chain_id: str | None = None,
        chain_role: str | None = None,
        **meta: Any,
    ) -> Operation:
        """Start tracking an operation. Sets thread-local context."""
        op = Operation(
            id=f"op-{uuid.uuid4().hex[:12]}",
            origin=origin,
            trigger=trigger,
            started_at=time.time(),
            chain_id=chain_id,
            chain_role=chain_role,
            meta=dict(meta) if meta else {},
        )
        _local.current_op = op
        return op

    def record_computation(
        self,
        path: str,
        elapsed_s: float,
        data: Any,
        status: str,
    ) -> OperationStep | None:
        """Record a mediator computation as a step.

        Called from mediator.get() after a resolver runs.
        If there's an active operation, adds a step to it.
        If no active operation, creates a standalone entry.

        Returns the step, or None if suppressed.
        """
        if should_suppress(path):
            return None

        domain = derive_domain(path)
        subtype = derive_subtype(path)
        source = derive_source(path)
        summary = extract_summary(path, data)

        step = OperationStep(
            ts=time.time(),
            path=path,
            domain=domain,
            subtype=subtype,
            source=source,
            status=status,
            elapsed_s=elapsed_s,
            summary=summary,
        )

        # Add to active operation if one exists
        op = self.current()
        if op is not None:
            op.steps.append(step)
        else:
            # Standalone computation — create a mini-operation
            standalone = Operation(
                id=f"compute-{uuid.uuid4().hex[:8]}",
                origin="system",
                trigger=f"compute:{path}",
                started_at=step.ts,
                steps=[step],
                status=status,
                summary=summary,
                ended_at=step.ts,
            )
            with self._lock:
                self._completed.append(standalone)

        return step

    def end(
        self,
        op: Operation,
        status: str = "ok",
        summary: str = "",
    ) -> None:
        """Finalize an operation. Clears thread-local context."""
        op.status = status
        op.summary = summary or op.trigger
        op.ended_at = time.time()

        with self._lock:
            self._completed.append(op)

        # Clear thread-local
        _local.current_op = None

        # Emit SSE event
        try:
            from src.core.services.event_bus import bus
            bus.publish("operation:completed", key=op.id, data={
                "id": op.id,
                "origin": op.origin,
                "trigger": op.trigger,
                "status": op.status,
                "summary": op.summary,
                "steps": len(op.steps),
                "duration_s": round(op.ended_at - op.started_at, 3),
            })
        except Exception:
            pass

    # ── Thread-local access ───────────────────────────────────────

    def current(self) -> Operation | None:
        """Get the active operation on this thread, or None."""
        return getattr(_local, "current_op", None)

    def resume(self, op: Operation) -> None:
        """Attach an operation to this thread (for worker threads)."""
        _local.current_op = op

    def suspend(self) -> None:
        """Detach operation from this thread (worker cleanup)."""
        _local.current_op = None

    # ── Chain management ──────────────────────────────────────────

    def start_chain(self, domain: str, chain_id: str) -> None:
        """Register an active chain for multi-request operations."""
        self._chains[domain] = {
            "chain_id": chain_id,
            "started_at": time.time(),
        }

    def get_chain(self, domain: str) -> str | None:
        """Get the active chain_id for a domain."""
        entry = self._chains.get(domain)
        if entry is None:
            return None
        if time.time() - entry["started_at"] > 86400:
            self._chains.pop(domain, None)
            return None
        return entry["chain_id"]

    def end_chain(self, domain: str) -> str | None:
        """End an active chain. Returns the chain_id."""
        entry = self._chains.pop(domain, None)
        return entry["chain_id"] if entry else None

    # ── Timeline entry production ─────────────────────────────────

    def get_timeline_entries(self) -> list:
        """Return all completed operations as TimelineEntry objects.

        Each operation produces one entry per step (for chain members)
        plus the operation itself is the chain.
        """
        from src.core.services.timeline.models import (
            Actor, ChainRole, EntryStatus, Locality,
            Severity, Source, TimelineEntry,
        )

        entries: list[TimelineEntry] = []

        with self._lock:
            ops = list(self._completed)

        for op in ops:
            if not op.steps:
                continue

            chain_id = op.chain_id or op.id
            origin_actor = Actor.USER if op.origin == "user" else Actor.SCHEDULER

            for i, step in enumerate(op.steps):
                try:
                    source = Source(step.source)
                except ValueError:
                    source = Source.PLATFORM

                status = EntryStatus.OK if step.status == "ok" else EntryStatus.FAILED
                severity = None
                if status == EntryStatus.FAILED:
                    severity = (Severity.HIGH
                                if source in (Source.SECURITY, Source.AUDIT)
                                else Severity.MEDIUM)

                role = ChainRole.ORIGIN if i == 0 else ChainRole.STEP

                entry = TimelineEntry(
                    id=f"{op.id}:{step.path}:{step.ts:.6f}",
                    ts=step.ts,
                    ref=step.path,
                    source=source,
                    subtype=step.subtype,
                    actor=origin_actor,
                    status=status,
                    severity=severity,
                    locality=Locality.LOCAL,
                    env=[],
                    modules=[],
                    summary=step.summary,
                    detail={
                        "elapsed_s": round(step.elapsed_s, 3),
                        "path": step.path,
                        "operation": op.id,
                        "origin": op.origin,
                    },
                    chain_id=chain_id,
                    chain_role=role,
                    chain_parent_ref=chain_id if role == ChainRole.STEP else None,
                )
                entries.append(entry)

        return entries
