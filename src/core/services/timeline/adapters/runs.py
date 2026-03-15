"""
RunsAdapter — reads .state/runs.jsonl (local ephemeral run records).

Every route decorated with @run_tracked produces a Run entry in runs.jsonl.
This adapter maps those runs to TimelineEntry objects, making all tracked
operations visible in the timeline.

The run_id becomes chain_id with ORIGIN role.  Downstream scan_activity
entries that fire during the run share the same operation_id (= run_id)
and appear as STEP members of the chain.
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

# ── Run.type → (Source, subtype) ──────────────────────────────────────

_RUN_TYPE_MAP: dict[str, tuple[Source, str | None]] = {
    # Lifecycle
    "build":     (Source.PLATFORM, "build"),
    "deploy":    (Source.CI,       "deploy"),
    "destroy":   (Source.PLATFORM, "destroy"),
    "install":   (Source.PKG,      "install"),
    # Maintenance
    "setup":     (Source.CONFIG,   "setup"),
    "plan":      (Source.PLATFORM, "plan"),
    "validate":  (Source.TESTS,    "validate"),
    "format":    (Source.TOOLS,    "format"),
    # Execution
    "test":      (Source.TESTS,    None),
    "scan":      (Source.SECURITY, "scan"),
    "generate":  (Source.PLATFORM, "generate"),
    "script":    (Source.PLATFORM, "script"),
    # Data
    "backup":    (Source.BACKUP,   "backup"),
    "restore":   (Source.BACKUP,   "restore"),
    # Git / CI
    "git":       (Source.GIT,      None),
    "ci":        (Source.CI,       None),
    # Browser testing
    "cdp_test":  (Source.TESTS,    "cdp"),
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


class RunsAdapter:
    """Reads .state/runs.jsonl and produces TimelineEntry list.

    Every @run_tracked route produces a Run record.  This adapter makes
    those records visible in the timeline with proper source mapping
    and chain linking.
    """

    def __init__(self, project_root: Path) -> None:
        self._root = project_root

    def load(self) -> list[TimelineEntry]:
        """Return all run entries from .state/runs.jsonl."""
        from src.core.services.run_tracker import load_runs

        raw_runs = load_runs(self._root, n=200)
        result: list[TimelineEntry] = []

        for run_data in raw_runs:
            try:
                entry = self._normalize(run_data)
                if entry is not None:
                    result.append(entry)
            except Exception as exc:
                logger.warning(
                    "runs: skipping run %s: %s",
                    run_data.get("run_id", "?"), exc,
                )

        return result

    def _normalize(self, r: dict) -> TimelineEntry | None:
        ts = iso_to_ts(r.get("started_at", ""))
        if ts == 0.0:
            return None

        run_id = r.get("run_id", "")
        run_type = r.get("type", "")
        run_subtype = r.get("subtype", "")

        source, subtype = _map_run_type(run_type, run_subtype)
        status = _map_status(r.get("status", "ok"))

        user = r.get("user", "")
        actor = Actor.USER if user else Actor.AUTOMATION

        summary = r.get("summary", "") or f"{run_type} run"

        detail: dict = {}
        if r.get("duration_ms"):
            detail["duration_ms"] = r["duration_ms"]
        if r.get("ended_at"):
            detail["ended_at"] = r["ended_at"]
        if r.get("metadata"):
            detail.update(r["metadata"])

        severity: Severity | None = None
        if status == EntryStatus.FAILED:
            severity = Severity.HIGH if source == Source.CI else Severity.MEDIUM

        # Chain info: prefer explicit chain from metadata, fall back to run_id as origin
        meta = r.get("metadata", {}) or {}
        chain_id = meta.get("_chain_id") or run_id
        chain_role_raw = meta.get("_chain_role")
        chain_parent_ref = meta.get("_chain_parent_ref")

        if chain_role_raw == "step":
            chain_role = ChainRole.STEP
        elif chain_role_raw == "terminal":
            chain_role = ChainRole.TERMINAL
        else:
            chain_role = ChainRole.ORIGIN

        # Remove internal chain keys from detail
        for k in ("_chain_id", "_chain_role", "_chain_parent_ref"):
            detail.pop(k, None)

        return TimelineEntry(
            id=f"run:{run_id}",
            ts=ts,
            ref=run_id,
            source=source,
            subtype=run_subtype or subtype,
            actor=actor,
            status=status,
            severity=severity,
            locality=Locality.LOCAL,
            env=[r["environment"]] if r.get("environment") else [],
            modules=list(r.get("modules_affected", [])),
            summary=summary,
            detail=detail or None,
            chain_id=chain_id,
            chain_role=chain_role,
            chain_parent_ref=chain_parent_ref,
        )
