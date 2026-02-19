"""
Ledger operations — business logic for recording and querying runs.

Uses ``worktree.py`` for git operations and ``models.py`` for data shapes.
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

from src.core.services.ledger.models import Run, RunEvent
from src.core.services.ledger.worktree import (
    TAG_PREFIX,
    create_run_tag,
    current_head_sha,
    current_user,
    ensure_worktree,
    fetch_run_tags,
    ledger_add_and_commit,
    list_run_tags,
    pull_ledger_branch,
    push_ledger_branch,
    push_run_tags,
    read_tag_message,
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


def record_run(
    project_root: Path,
    run: Run,
    events: list[dict[str, Any]] | None = None,
) -> str:
    """Record a run to the ledger.

    Steps:
      1. ``ensure_ledger()``
      2. ``mkdir -p .scp-ledger/ledger/runs/<run_id>/``
      3. Write ``run.json`` (``json.dump``)
      4. Write ``events.jsonl`` (if events provided)
      5. ``git -C .scp-ledger add + commit``
      6. Create annotated tag ``scp/run/<run_id>`` → current HEAD on main

    Args:
        project_root: Repository root.
        run: The Run model to record. ``run_id`` will be auto-generated if empty.
        events: Optional list of event dicts to write as ``events.jsonl``.

    Returns:
        The run_id.
    """
    # Ensure infrastructure
    wt = ensure_ledger(project_root)

    # Ensure run has an ID
    run_id = run.ensure_id()

    # Fill in code_ref if not set
    if not run.code_ref:
        head = current_head_sha(project_root)
        if head:
            run.code_ref = head

    # Fill in user if not set
    if not run.user:
        run.user = current_user(project_root)

    # Create run directory
    run_dir = wt / "ledger" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Write run.json
    run_json_path = run_dir / "run.json"
    run_data = run.model_dump(mode="json")
    run_json_path.write_text(
        json.dumps(run_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    logger.debug("Wrote %s", run_json_path)

    # Write events.jsonl
    relative_paths = [f"ledger/runs/{run_id}/run.json"]
    if events:
        events_path = run_dir / "events.jsonl"
        lines = [json.dumps(e, ensure_ascii=False) + "\n" for e in events]
        events_path.write_text("".join(lines), encoding="utf-8")
        relative_paths.append(f"ledger/runs/{run_id}/events.jsonl")
        logger.debug("Wrote %d events to %s", len(events), events_path)

    # Commit to ledger branch
    ledger_add_and_commit(
        project_root,
        paths=relative_paths,
        message=f"ledger: {run.type or 'run'} {run_id}",
    )

    # Create annotated tag pointing to HEAD on main
    head_sha = current_head_sha(project_root)
    if head_sha:
        tag_name = f"{TAG_PREFIX}{run_id}"
        create_run_tag(
            project_root,
            tag_name=tag_name,
            target_sha=head_sha,
            message=run.to_tag_message(),
        )
        logger.info("Run recorded: %s (tag: %s)", run_id, tag_name)
    else:
        logger.warning(
            "Run recorded to ledger but no tag created (no HEAD commit): %s",
            run_id,
        )

    # Publish to event bus (if available)
    if _bus is not None:
        try:
            _bus.publish(
                "ledger:run",
                key=run_id,
                data={
                    "type": run.type,
                    "subtype": run.subtype,
                    "status": run.status,
                    "summary": run.summary,
                    "user": run.user,
                    "code_ref": run.code_ref[:12] if run.code_ref else "",
                },
            )
        except Exception:
            pass  # event bus failure must never break ledger recording

    return run_id


def list_runs(project_root: Path, *, n: int = 20) -> list[Run]:
    """List recent runs by reading ``scp/run/*`` annotated tags.

    Parses tag messages (compact JSON).
    Returns newest-first, limited to ``n``.
    """
    tags = list_run_tags(project_root)
    runs: list[Run] = []

    for tag_name in tags[:n]:
        msg = read_tag_message(project_root, tag_name)
        if msg:
            try:
                run = Run.from_tag_message(msg)
                runs.append(run)
            except Exception as e:
                logger.warning("Failed to parse tag %s: %s", tag_name, e)

    return runs


def get_run(project_root: Path, run_id: str) -> Run | None:
    """Get a single run's metadata from its tag.

    Args:
        project_root: Repository root.
        run_id: The run ID (without the ``scp/run/`` prefix).

    Returns:
        The Run model, or None if not found.
    """
    tag_name = f"{TAG_PREFIX}{run_id}"
    msg = read_tag_message(project_root, tag_name)
    if not msg:
        return None
    try:
        return Run.from_tag_message(msg)
    except Exception as e:
        logger.warning("Failed to parse run %s: %s", run_id, e)
        return None


def get_run_events(project_root: Path, run_id: str) -> list[dict[str, Any]]:
    """Read ``events.jsonl`` from ``.scp-ledger/ledger/runs/<run_id>/``.

    Direct file read from the worktree (no ``git show`` needed).

    Returns:
        List of event dicts, or empty list if no events file.
    """
    wt = worktree_path(project_root)
    events_file = wt / "ledger" / "runs" / run_id / "events.jsonl"

    if not events_file.is_file():
        return []

    events: list[dict[str, Any]] = []
    try:
        with events_file.open("r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError as e:
                    logger.warning(
                        "Skipping corrupt event at %s line %d: %s",
                        events_file, line_num, e,
                    )
    except OSError as e:
        logger.error("Failed to read events for %s: %s", run_id, e)

    return events


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
    """Push scp-ledger branch and scp/run/* tags to origin.

    Steps:
      1. ``git -C .scp-ledger pull --rebase origin scp-ledger``
      2. ``git -C .scp-ledger push origin scp-ledger``
      3. ``git push origin 'refs/tags/scp/run/*'``

    Returns True if both push operations succeeded.
    """
    ensure_ledger(project_root)
    branch_ok = push_ledger_branch(project_root)
    tags_ok = push_run_tags(project_root)
    return branch_ok and tags_ok


def pull_ledger(project_root: Path) -> bool:
    """Pull scp-ledger branch and scp/run/* tags from origin.

    Steps:
      1. ``git -C .scp-ledger pull --rebase origin scp-ledger``
      2. ``git fetch origin 'refs/tags/scp/run/*:refs/tags/scp/run/*'``

    Returns True if both operations succeeded.
    """
    ensure_ledger(project_root)
    branch_ok = pull_ledger_branch(project_root)
    tags_ok = fetch_run_tags(project_root)
    return branch_ok and tags_ok
