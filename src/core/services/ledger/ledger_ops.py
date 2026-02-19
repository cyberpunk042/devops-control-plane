"""
Ledger operations — business logic for saving and querying audit snapshots.

Uses ``worktree.py`` for git operations and ``models.py`` for data shapes.
The ledger branch (``scp-ledger``) stores audit snapshots only.
Runs are ephemeral and stored locally in ``.state/runs.jsonl``.

All functions are safe to call from any context (CLI, web, engine) — they
never raise exceptions to callers.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

try:
    from src.core.services.event_bus import bus as _bus
except Exception:  # pragma: no cover — bus may not be available in all contexts
    _bus = None  # type: ignore[assignment]


from src.core.services.ledger.worktree import (
    create_run_tag,
    current_head_sha,
    current_user,
    ensure_worktree,
    ledger_add_and_commit,
    pull_ledger_branch,
    push_ledger_branch,
    worktree_path,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════════


def ensure_ledger(project_root: Path) -> Path:
    """Ensure ledger worktree is ready. Returns worktree path.

    Calls ``ensure_worktree()``. Idempotent.
    """
    return ensure_worktree(project_root)





# ═══════════════════════════════════════════════════════════════════════
#  Audit snapshots
# ═══════════════════════════════════════════════════════════════════════

AUDIT_TAG_PREFIX = "scp/audit/"


def save_audit_snapshot(
    project_root: Path,
    snapshot_id: str,
    snapshot_data: dict[str, Any],
) -> str:
    """Write an audit snapshot to the ledger branch.

    Steps:
      1. ``ensure_ledger()``
      2. Write ``audits/<snapshot_id>.json``
      3. ``git add + commit``
      4. Create annotated tag ``scp/audit/<snapshot_id>``

    Args:
        project_root: Repository root.
        snapshot_id: e.g. ``"security_20260218_150300"``.
        snapshot_data: Full snapshot dict (card_key, data blob, etc.).

    Returns:
        The snapshot_id.
    """
    wt = ensure_ledger(project_root)

    # Write to audits directory
    audit_dir = wt / "audits"
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_path = audit_dir / f"{snapshot_id}.json"
    audit_path.write_text(
        json.dumps(snapshot_data, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    logger.debug("Wrote %s", audit_path)

    # Commit to ledger branch
    ledger_add_and_commit(
        project_root,
        paths=[f"audits/{snapshot_id}.json"],
        message=f"audit: {snapshot_data.get('card_key', '?')} {snapshot_id}",
    )

    # Create annotated tag pointing to HEAD on main
    head_sha = current_head_sha(project_root)
    if head_sha:
        tag_name = f"{AUDIT_TAG_PREFIX}{snapshot_id}"
        tag_message = json.dumps(
            {
                "snapshot_id": snapshot_id,
                "card_key": snapshot_data.get("card_key"),
                "status": snapshot_data.get("status"),
                "iso": snapshot_data.get("iso"),
                "summary": snapshot_data.get("summary"),
            },
            ensure_ascii=False,
        )
        create_run_tag(
            project_root,
            tag_name=tag_name,
            target_sha=head_sha,
            message=tag_message,
        )
        logger.info("Audit snapshot saved: %s (tag: %s)", snapshot_id, tag_name)
    else:
        logger.warning(
            "Audit snapshot saved to ledger but no tag created (no HEAD): %s",
            snapshot_id,
        )

    # Publish to event bus (if available)
    if _bus is not None:
        try:
            _bus.publish(
                "audit:saved",
                key=snapshot_id,
                data={
                    "card_key": snapshot_data.get("card_key"),
                    "status": snapshot_data.get("status"),
                    "summary": snapshot_data.get("summary"),
                    "iso": snapshot_data.get("iso"),
                },
            )
        except Exception:
            pass  # event bus failure must never break ledger recording

    return snapshot_id


def get_saved_audit(
    project_root: Path, snapshot_id: str,
) -> dict[str, Any] | None:
    """Read a saved audit snapshot from the ledger worktree.

    Returns the full snapshot dict, or ``None`` if not found.
    """
    wt = worktree_path(project_root)
    audit_path = wt / "audits" / f"{snapshot_id}.json"
    if not audit_path.is_file():
        return None
    try:
        return json.loads(audit_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read saved audit %s: %s", snapshot_id, e)
        return None


def delete_saved_audit(
    project_root: Path, snapshot_id: str,
) -> bool:
    """Delete a saved audit snapshot from the ledger worktree.

    Steps:
      1. Remove ``audits/<snapshot_id>.json`` from the worktree.
      2. Commit the deletion.
      3. Try to delete the associated tag.

    Returns ``True`` if found and deleted, ``False`` if not found.
    """
    wt = worktree_path(project_root)
    audit_path = wt / "audits" / f"{snapshot_id}.json"
    if not audit_path.is_file():
        return False

    audit_path.unlink()

    ledger_add_and_commit(
        project_root,
        paths=[f"audits/{snapshot_id}.json"],
        message=f"audit: delete {snapshot_id}",
    )

    # Try to delete the associated tag
    tag_name = f"{AUDIT_TAG_PREFIX}{snapshot_id}"
    try:
        import subprocess
        subprocess.run(
            ["git", "tag", "-d", tag_name],
            cwd=str(project_root),
            capture_output=True,
        )
        logger.debug("Deleted tag %s", tag_name)
    except Exception:
        pass  # tag deletion failure is non-critical

    logger.info("Deleted saved audit: %s", snapshot_id)
    return True


def list_saved_audits(
    project_root: Path, *, n: int = 50,
) -> list[dict[str, Any]]:
    """List saved audit snapshots (metadata only, no data blobs).

    Reads from the ``audits/`` directory in the ledger worktree.
    Returns newest-first, limited to ``n``.
    """
    wt = worktree_path(project_root)
    audits_dir = wt / "audits"
    if not audits_dir.is_dir():
        return []

    results: list[dict[str, Any]] = []
    for path in sorted(audits_dir.glob("*.json"), reverse=True):
        if len(results) >= n:
            break
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            card_key = data.get("card_key", "")
            results.append({
                "snapshot_id": data.get("snapshot_id", path.stem),
                "card_key": card_key,
                "audit_type": data.get("audit_type") or ("project" if card_key.startswith("audit:") else "devops"),
                "computed_at": data.get("computed_at"),
                "iso": data.get("iso"),
                "status": data.get("status"),
                "summary": data.get("summary"),
                "duration_s": data.get("duration_s"),
            })
        except (json.JSONDecodeError, OSError):
            continue

    return results


# ═══════════════════════════════════════════════════════════════════════
#  Push / Pull
# ═══════════════════════════════════════════════════════════════════════


def push_ledger(project_root: Path) -> bool:
    """Push scp-ledger branch to origin."""
    ensure_ledger(project_root)
    return push_ledger_branch(project_root)


def pull_ledger(project_root: Path) -> bool:
    """Pull scp-ledger branch from origin."""
    ensure_ledger(project_root)
    return pull_ledger_branch(project_root)
