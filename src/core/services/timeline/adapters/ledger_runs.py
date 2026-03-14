"""
LedgerRunsAdapter — reads .ledger/ scp/run/* annotated tags.

Each tag annotation contains a Run JSON with metadata for the run.
Run.code_ref is the git commit hash that triggered the run — this
becomes chain_id, linking the run back to its commit entry in git_log.

Sources produced: CI, TESTS, PLATFORM(other run types)
"""

from __future__ import annotations

import json
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

# ── Run.type → (Source, subtype) ──────────────────────────────────────

_RUN_TYPE_MAP: dict[str, tuple[Source, str | None]] = {
    "ci":     (Source.CI,    None),
    "test":   (Source.TESTS, None),
    "deploy": (Source.CI,    "deploy"),
}


def _map_run_type(run_type: str, run_subtype: str) -> tuple[Source, str | None]:
    if run_type in _RUN_TYPE_MAP:
        src, sub = _RUN_TYPE_MAP[run_type]
        return src, sub or run_subtype or None
    return Source.PLATFORM, run_type


def _map_status(raw: str) -> EntryStatus:
    if raw == "ok":
        return EntryStatus.OK
    if raw == "failed":
        return EntryStatus.FAILED
    if raw == "partial":
        return EntryStatus.WARNING
    return EntryStatus.OK


class LedgerRunsAdapter:
    """Reads scp/run/* tags from the main repo and produces TimelineEntry list.

    Uses list_run_tags() and read_tag_message() from ledger.worktree.
    No noise filter: all ledger runs are deliberate signal.
    """

    def __init__(self, project_root: Path) -> None:
        self._root = project_root

    def load(self) -> list[TimelineEntry]:
        """Return all run entries from scp/run/* annotated tags."""
        from src.core.services.ledger.models import Run
        from src.core.services.ledger.worktree import list_run_tags, read_tag_message

        tags = list_run_tags(self._root)
        result: list[TimelineEntry] = []

        for tag_name in tags:
            try:
                message = read_tag_message(self._root, tag_name)
                if not message:
                    continue
                run = Run.from_tag_message(message)
                entry = self._normalize(run)
                if entry is not None:
                    result.append(entry)
            except Exception as exc:
                logger.warning("ledger_runs: skipping tag %s: %s", tag_name, exc)

        return result

    def _normalize(self, run) -> TimelineEntry | None:
        ts = iso_to_ts(run.started_at)
        if ts == 0.0:
            return None

        source, subtype = _map_run_type(run.type, run.subtype)
        status = _map_status(run.status)

        actor = Actor.USER if (run.user or "").lower() in ("user", "") else Actor.AUTOMATION

        summary = run.summary if run.summary else f"{run.type} run"

        detail: dict = {}
        if run.duration_ms:
            detail["duration_ms"] = run.duration_ms
        if run.ended_at:
            detail["ended_at"] = run.ended_at
        if run.metadata:
            detail.update(run.metadata)

        # Severity
        severity: Severity | None = None
        if status == EntryStatus.FAILED:
            severity = Severity.HIGH if source == Source.CI else Severity.MEDIUM

        # chain_id: code_ref (git commit) links run → commit in git_log
        chain_id = run.code_ref if run.code_ref else run.run_id
        chain_role = ChainRole.STEP if run.code_ref else ChainRole.ORIGIN

        return TimelineEntry(
            id=f"ledger_run:{run.run_id}",
            ts=ts,
            ref=run.run_id,
            source=source,
            subtype=subtype,
            actor=actor,
            status=status,
            severity=severity,
            locality=Locality.SHARED,
            env=[run.environment] if run.environment else [],
            modules=list(run.modules_affected),
            summary=summary,
            detail=detail or None,
            chain_id=chain_id,
            chain_role=chain_role,
            chain_parent_ref=run.code_ref if run.code_ref else None,
        )
