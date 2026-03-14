"""
LedgerAuditsAdapter — reads .ledger/ scp/audit/* annotated tags.

These are the SHARED side of audit entries. The same audit operation
appears in cli_ops (local, when it ran) and here (shared, when committed
to the ledger). Both entries are kept as distinct historical facts linked
by chain_id = operation_id.

ts = ledger commit time (tag creatordate), NOT the scan time.
This ensures the cli_ops entry (local, T1) appears before the
ledger_audits entry (shared, T2) on the timeline.

Sources produced: AUDIT (always)
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

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

_AUDIT_TAG_PREFIX = "scp/audit/"


def _findings_to_severity(findings_count: int) -> Severity | None:
    if findings_count <= 0:
        return None
    if findings_count <= 3:
        return Severity.LOW
    if findings_count <= 10:
        return Severity.MEDIUM
    return Severity.HIGH


def _map_status(raw: str | None) -> EntryStatus:
    if not raw:
        return EntryStatus.OK
    if raw in ("failed", "error"):
        return EntryStatus.FAILED
    if raw in ("warn", "warning", "partial"):
        return EntryStatus.WARNING
    return EntryStatus.OK


class LedgerAuditsAdapter:
    """Reads scp/audit/* tags and produces TimelineEntry list.

    Uses git for-each-ref to get both tag creatordate (ledger commit time)
    and tag message (snapshot metadata) in a single git call.
    No noise filter: all ledger audit entries are deliberate signal.
    """

    def __init__(self, project_root: Path) -> None:
        self._root = project_root

    def load(self) -> list[TimelineEntry]:
        """Return all audit ledger entries from scp/audit/* tags."""
        raw_tags = self._list_audit_tags()
        result: list[TimelineEntry] = []

        for tag_data in raw_tags:
            try:
                entry = self._normalize(tag_data)
                if entry is not None:
                    result.append(entry)
            except Exception as exc:
                logger.warning("ledger_audits: skipping tag: %s", exc)

        return result

    def _list_audit_tags(self) -> list[dict]:
        """List scp/audit/* tags with creatordate and message in one call.

        Uses git for-each-ref with TAB-separated format:
          refname:short TAB creatordate:unix TAB contents:lines=1
        Since tag messages are single-line JSON, lines=1 is sufficient.
        """
        try:
            r = subprocess.run(
                [
                    "git", "for-each-ref",
                    f"refs/tags/{_AUDIT_TAG_PREFIX}",
                    "--sort=-creatordate",
                    "--format=%(refname:short)\t%(creatordate:unix)\t%(contents:lines=1)",
                ],
                cwd=str(self._root),
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            logger.warning("ledger_audits: git for-each-ref failed: %s", exc)
            return []

        if r.returncode != 0:
            logger.debug("ledger_audits: no audit tags found (returncode %d)", r.returncode)
            return []

        results: list[dict] = []
        for line in r.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t", 2)
            if len(parts) < 3:
                continue
            tag_name, ts_str, message = parts
            try:
                ts = float(ts_str)
            except ValueError:
                ts = 0.0
            results.append({
                "tag": tag_name.strip(),
                "ts": ts,
                "message": message.strip(),
            })

        return results

    def _normalize(self, tag_data: dict) -> TimelineEntry | None:
        ts: float = tag_data.get("ts", 0.0)
        if ts == 0.0:
            return None

        message: str = tag_data.get("message", "")
        if not message:
            return None

        try:
            meta = json.loads(message)
        except (json.JSONDecodeError, ValueError):
            return None

        snapshot_id: str = meta.get("snapshot_id", "")
        card_key: str = meta.get("card_key", "")
        summary: str = meta.get("summary", "")
        status_raw: str = meta.get("status", "ok")
        iso: str = meta.get("iso", "")

        # Derive audit level from card_key
        subtype = "L0"
        if card_key:
            ck = card_key.lower()
            if "l2" in ck:
                subtype = "L2"
            elif "l1" in ck:
                subtype = "L1"
            else:
                subtype = "L0"

        if not summary:
            summary = f"{card_key} committed to ledger" if card_key else "audit committed"

        # Full snapshot data as detail (loaded separately if needed)
        detail: dict = {}
        if card_key:
            detail["card_key"] = card_key
        if iso:
            detail["scan_iso"] = iso
        if snapshot_id:
            detail["snapshot_id"] = snapshot_id

        status = _map_status(status_raw)

        # Findings count for severity — not available from tag metadata alone
        # Severity derived from status only at this level
        severity: Severity | None = None
        if status == EntryStatus.FAILED:
            severity = Severity.HIGH
        elif status == EntryStatus.WARNING:
            severity = Severity.MEDIUM

        # chain_id: operation_id links to the cli_ops entry for the same run
        # operation_id is present in tag metadata when audit staging preserved it
        op_id = meta.get("operation_id")
        chain_id = str(op_id) if op_id else None
        chain_role = ChainRole.TERMINAL if op_id else None
        chain_parent_ref = str(op_id) if op_id else None

        return TimelineEntry(
            id=f"ledger_audit:{snapshot_id or tag_data.get('tag', '')}",
            ts=ts,
            ref=snapshot_id or None,
            source=Source.AUDIT,
            subtype=subtype,
            actor=Actor.USER,
            status=status,
            severity=severity,
            locality=Locality.SHARED,
            env=[],
            modules=[],
            summary=summary,
            detail=detail or None,
            chain_id=chain_id,
            chain_role=chain_role,
            chain_parent_ref=chain_parent_ref,
        )
