"""
Audit staging — one pending audit snapshot per card, awaiting save-to-git or discard.

Each time ``devops_cache.get_cached()`` computes a fresh result for a card,
an audit snapshot (the **full** data blob) is staged here.  The user can then:

  - **Save** → promotes to ``.ledger/audits/<snapshot_id>.json`` + git tag
  - **Discard** → removes from staging (cache is NOT affected)

Invariant
---------
**One snapshot per card_key.**  A new scan for the same card overwrites the
previous unsaved snapshot.  If the user wants to keep a scan, they save it
to the ledger first.

Persistence
-----------
Staged audits are persisted to ``.state/pending_audits.json`` as a dict
keyed by ``card_key``.  The file survives server restarts, following the
same pattern as ``devops_cache.json``.

Thread safety
-------------
A file lock serialises all mutations, matching the pattern used by
``devops_cache._file_lock``.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PENDING_FILE = ".state/pending_audits.json"

# Serialise all mutations.
_file_lock = threading.Lock()


# ═══════════════════════════════════════════════════════════════════════
#  Snapshot ID
# ═══════════════════════════════════════════════════════════════════════


def _make_snapshot_id(card_key: str) -> str:
    """Generate a snapshot ID: ``<card_key>_<YYYYMMDD>_<HHMMSS>``.

    The card key is normalised (colons → underscores) so the ID is
    safe for filenames and git tag names.
    """
    safe_key = card_key.replace(":", "_").replace("/", "_")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{safe_key}_{ts}"


# ═══════════════════════════════════════════════════════════════════════
#  Persistence (load / save)
# ═══════════════════════════════════════════════════════════════════════


def _pending_path(project_root: Path) -> Path:
    return project_root / _PENDING_FILE


def _load_pending(project_root: Path) -> dict[str, dict[str, Any]]:
    """Load the staging dict from disk.  Returns ``{}`` on any error.

    Handles migration from the old list format (pre-2026-03) automatically.
    """
    path = _pending_path(project_root)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return {}

    # Current format: dict keyed by card_key
    if isinstance(raw, dict):
        return raw

    # Legacy format: list of snapshots — migrate by keeping latest per card_key
    if isinstance(raw, list):
        migrated: dict[str, dict[str, Any]] = {}
        for s in raw:
            ck = s.get("card_key")
            if ck:
                migrated[ck] = s
        return migrated

    return {}


def _save_pending(project_root: Path, pending: dict[str, dict[str, Any]]) -> None:
    """Write the staging dict to disk.  Caller MUST hold ``_file_lock``."""
    path = _pending_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(pending, default=str, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# ═══════════════════════════════════════════════════════════════════════
#  Public API — Stage
# ═══════════════════════════════════════════════════════════════════════


def stage_audit(
    project_root: Path,
    card_key: str,
    status: str,
    elapsed_s: float,
    data: dict[str, Any],
    summary: str,
    *,
    audit_type: str = "",
) -> str:
    """Stage a pending audit snapshot from a cache computation.

    Called by ``devops_cache.get_cached()`` after a fresh compute.

    One snapshot per card_key — a new scan overwrites any previous
    unsaved snapshot for the same card.

    Args:
        audit_type: "devops" or "project". If empty, auto-derived from card_key:
            keys starting with ``audit:`` → "project", else "devops".

    Returns:
        The generated ``snapshot_id``.
    """
    if not audit_type:
        audit_type = "project" if card_key.startswith("audit:") else "devops"

    now = time.time()
    snapshot_id = _make_snapshot_id(card_key)
    iso = datetime.fromtimestamp(now, tz=timezone.utc).isoformat()

    snapshot: dict[str, Any] = {
        "snapshot_id": snapshot_id,
        "card_key": card_key,
        "audit_type": audit_type,
        "computed_at": now,
        "iso": iso,
        "status": status,
        "duration_s": round(elapsed_s, 3),
        "summary": summary,
        "data": data,
    }

    with _file_lock:
        pending = _load_pending(project_root)
        pending[card_key] = snapshot
        _save_pending(project_root, pending)

    logger.debug("Staged pending audit: %s (%s, type=%s)", snapshot_id, card_key, audit_type)
    return snapshot_id


# ═══════════════════════════════════════════════════════════════════════
#  Public API — Query
# ═══════════════════════════════════════════════════════════════════════


def list_pending(project_root: Path) -> list[dict[str, Any]]:
    """Return all pending snapshots (metadata only, no data blob).

    The data blob is omitted to keep list responses lightweight.
    Use :func:`get_pending` to retrieve the full blob for a single snapshot.
    """
    with _file_lock:
        pending = _load_pending(project_root)

    return [
        {
            "snapshot_id": s["snapshot_id"],
            "card_key": s["card_key"],
            "audit_type": s.get("audit_type") or ("project" if s["card_key"].startswith("audit:") else "devops"),
            "computed_at": s["computed_at"],
            "iso": s["iso"],
            "status": s["status"],
            "duration_s": s["duration_s"],
            "summary": s["summary"],
        }
        for s in pending.values()
    ]


def get_pending(project_root: Path, snapshot_id: str) -> dict[str, Any] | None:
    """Return the full snapshot (including data blob) for a single pending audit.

    Returns ``None`` if not found.
    """
    with _file_lock:
        pending = _load_pending(project_root)

    return next((s for s in pending.values() if s.get("snapshot_id") == snapshot_id), None)


# ═══════════════════════════════════════════════════════════════════════
#  Public API — Save
# ═══════════════════════════════════════════════════════════════════════


def save_audit(project_root: Path, snapshot_id: str) -> dict[str, Any]:
    """Promote a pending snapshot to the ledger branch.

    Steps:
      1. Find the snapshot in staging.
      2. Write to ``.ledger/audits/<snapshot_id>.json`` + commit + tag.
      3. Remove from staging.
      4. Persist.

    Returns:
        Metadata dict (snapshot_id, card_key, iso, summary) suitable for
        the frontend to display and for chat referencing.

    Raises:
        ValueError: If ``snapshot_id`` is not found in staging.
    """
    with _file_lock:
        pending = _load_pending(project_root)
        # Find by snapshot_id (value lookup since key is card_key)
        match_key = None
        for ck, s in pending.items():
            if s.get("snapshot_id") == snapshot_id:
                match_key = ck
                break

        if match_key is None:
            raise ValueError(f"Pending audit not found: {snapshot_id}")

        snapshot = pending.pop(match_key)
        _save_pending(project_root, pending)

    # Write to ledger (outside the file lock — ledger has its own locking)
    from src.core.services.ledger.ledger_ops import save_audit_snapshot

    save_audit_snapshot(project_root, snapshot_id, snapshot)

    logger.info("Saved audit snapshot to ledger: %s", snapshot_id)

    return {
        "snapshot_id": snapshot["snapshot_id"],
        "card_key": snapshot["card_key"],
        "iso": snapshot["iso"],
        "status": snapshot["status"],
        "summary": snapshot["summary"],
    }


def save_all_pending(project_root: Path) -> list[str]:
    """Save all pending snapshots to the ledger.

    Returns:
        List of saved ``snapshot_id`` values.
    """
    with _file_lock:
        pending = _load_pending(project_root)
        to_save = dict(pending)
        pending.clear()
        _save_pending(project_root, pending)

    from src.core.services.ledger.ledger_ops import save_audit_snapshot

    saved: list[str] = []
    for card_key, snapshot in to_save.items():
        sid = snapshot.get("snapshot_id", "")
        try:
            save_audit_snapshot(project_root, sid, snapshot)
            saved.append(sid)
            logger.info("Saved audit snapshot to ledger: %s", sid)
        except Exception:
            logger.warning("Failed to save audit snapshot: %s", sid, exc_info=True)
            # Put it back in staging so we don't lose it
            with _file_lock:
                pending = _load_pending(project_root)
                pending[card_key] = snapshot
                _save_pending(project_root, pending)

    return saved


# ═══════════════════════════════════════════════════════════════════════
#  Public API — Discard
# ═══════════════════════════════════════════════════════════════════════


def discard_audit(project_root: Path, snapshot_id: str) -> bool:
    """Remove a snapshot from staging.  Cache is unaffected.

    Returns ``True`` if found and removed, ``False`` if not found.
    """
    with _file_lock:
        pending = _load_pending(project_root)
        match_key = None
        for ck, s in pending.items():
            if s.get("snapshot_id") == snapshot_id:
                match_key = ck
                break

        if match_key is None:
            return False

        del pending[match_key]
        _save_pending(project_root, pending)

    logger.debug("Discarded pending audit: %s", snapshot_id)
    return True


def discard_all_pending(project_root: Path) -> int:
    """Discard all pending snapshots.  Cache is unaffected.

    Returns the number of snapshots discarded.
    """
    with _file_lock:
        pending = _load_pending(project_root)
        count = len(pending)
        if count > 0:
            _save_pending(project_root, {})

    if count > 0:
        logger.debug("Discarded all %d pending audits", count)

    return count
