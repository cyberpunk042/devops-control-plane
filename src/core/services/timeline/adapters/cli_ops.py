"""
CliOpsAdapter — reads .state/audit.ndjson.

Records CLI-level operations: tool installs, backups, vault operations,
env operations, package operations, audit runs.

Sources produced: TOOLS, BACKUP, VAULT, ENV, PKG, AUDIT(local), PLATFORM
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.core.services.timeline.adapters._util import iso_to_ts
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

# ── operation_type prefix → (Source, subtype) ──────────────────────────

_OP_MAP: list[tuple[str, Source, str]] = [
    ("tool_install",    Source.TOOLS,  "install"),
    ("tool_upgrade",    Source.TOOLS,  "upgrade"),
    ("tool_remove",     Source.TOOLS,  "remove"),
    ("backup_snapshot", Source.BACKUP, "snapshot"),
    ("backup_restore",  Source.BACKUP, "restore"),
    ("vault_rotate",    Source.VAULT,  "rotate"),
    ("vault_add",       Source.VAULT,  "add"),
    ("vault_delete",    Source.VAULT,  "delete"),
    ("env_promote",     Source.ENV,    "promote"),
    ("env_modify",      Source.ENV,    "modify"),
    ("package_install", Source.PKG,    "install"),
    ("package_upgrade", Source.PKG,    "upgrade"),
    ("audit_run",       Source.AUDIT,  "run"),
]


def _map_operation_type(op_type: str) -> tuple[Source, str]:
    for prefix, source, subtype in _OP_MAP:
        if op_type.startswith(prefix):
            return source, subtype
    return Source.PLATFORM, op_type


def _map_status(raw: str) -> EntryStatus:
    if raw == "ok":
        return EntryStatus.OK
    if raw in ("failed", "error"):
        return EntryStatus.FAILED
    if raw == "partial":
        return EntryStatus.WARNING
    return EntryStatus.OK


class CliOpsAdapter:
    """Reads .state/audit.ndjson and produces TimelineEntry list.

    Uses AuditWriter.read_all() — does not read the file directly.
    No noise filter: all CLI ops are deliberate platform actions.
    """

    def __init__(self, project_root: Path) -> None:
        self._root = project_root

    def load(self) -> list[TimelineEntry]:
        """Return all CLI operation entries from audit.ndjson."""
        from src.core.persistence.audit import AuditWriter

        writer = AuditWriter(project_root=self._root)
        raw_entries = writer.read_all()
        result: list[TimelineEntry] = []

        for entry in raw_entries:
            try:
                tl = self._normalize(entry)
                if tl is not None:
                    result.append(tl)
            except Exception as exc:
                logger.warning("cli_ops: skipping corrupt entry: %s", exc)

        return result

    def _normalize(self, entry) -> TimelineEntry | None:
        """Normalize an AuditEntry to a TimelineEntry."""
        ts = iso_to_ts(entry.timestamp)
        if ts == 0.0:
            return None

        source, subtype = _map_operation_type(entry.operation_type)
        status = _map_status(entry.status)

        # Actor: derived from automation field
        auto = (entry.automation or "").lower()
        actor = Actor.USER if auto in ("user", "", "manual") else Actor.AUTOMATION

        # Summary: combine automation context with operation type
        if auto and auto not in ("user", ""):
            summary = f"{auto}: {entry.operation_type}"
        else:
            summary = entry.operation_type
        # Prefer a meaningful summary if available
        if not summary.strip():
            summary = entry.operation_type

        # Detail
        detail: dict = {}
        if entry.actions_total > 0:
            detail["actions"] = f"{entry.actions_succeeded}/{entry.actions_total} succeeded"
        if entry.duration_ms:
            detail["duration_ms"] = entry.duration_ms
        if entry.errors:
            detail["errors"] = entry.errors
        if entry.context:
            detail["context"] = entry.context

        # Severity: non-empty errors → high
        severity: Severity | None = None
        if entry.errors:
            severity = Severity.HIGH
        elif status == EntryStatus.WARNING:
            severity = Severity.MEDIUM
        elif status == EntryStatus.FAILED:
            severity = Severity.HIGH

        # chain_id: operation_id is the anchor — links to ledger_audits entry
        chain_id = entry.operation_id if entry.operation_id else None
        chain_role = ChainRole.ORIGIN if chain_id else None

        return TimelineEntry(
            id=f"cli_ops:{entry.operation_id or f'{ts:.6f}'}",
            ts=ts,
            ref=entry.operation_id or None,
            source=source,
            subtype=subtype,
            actor=actor,
            status=status,
            severity=severity,
            locality=Locality.LOCAL,
            env=[entry.environment] if entry.environment else [],
            modules=list(entry.modules_affected),
            summary=summary,
            detail=detail or None,
            chain_id=chain_id,
            chain_role=chain_role,
            chain_parent_ref=None,
        )
