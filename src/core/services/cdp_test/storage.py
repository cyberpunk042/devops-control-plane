"""
CDP Test storage — JSON file CRUD for test suites and run results.

File layout::

    .state/
        cdp-tests/
            suites/
                <suite-id>.json        # TestSuite serialized (working copy)
            results/
                <run-id>.json          # TestRunResult serialized

    .ledger/
        cdp-tests/
            suites/
                <suite-id>.json        # TestSuite committed to git
            .hidden-suites.json        # IDs of suites hidden by the user

Thread-safe: all file I/O is guarded by a module-level lock.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from src.core.services.cdp_test.models import TestRunResult, TestSuite

logger = logging.getLogger(__name__)

_lock = threading.Lock()

# ── Local paths (.state/) ──────────────────────────────────────


def _suites_dir(project_root: Path) -> Path:
    """Return (and create) the suites directory."""
    d = project_root / ".state" / "cdp-tests" / "suites"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _results_dir(project_root: Path) -> Path:
    """Return (and create) the results directory."""
    d = project_root / ".state" / "cdp-tests" / "results"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Ledger paths (.ledger/) ────────────────────────────────────


def _ledger_suites_dir(project_root: Path) -> Path:
    """Return (and optionally create) the ledger suites directory."""
    from src.core.services.ledger.worktree import worktree_path

    d = worktree_path(project_root) / "cdp-tests" / "suites"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _hidden_suites_file(project_root: Path) -> Path:
    """Return path to the hidden-suites list in the ledger."""
    from src.core.services.ledger.worktree import worktree_path

    return worktree_path(project_root) / "cdp-tests" / ".hidden-suites.json"


def _read_hidden_ids(project_root: Path) -> set[str]:
    """Read the set of hidden suite IDs from the ledger."""
    hf = _hidden_suites_file(project_root)
    if hf.is_file():
        try:
            return set(json.loads(hf.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    return set()


def _write_hidden_ids(project_root: Path, ids: set[str]) -> None:
    """Write hidden suite IDs to the ledger."""
    hf = _hidden_suites_file(project_root)
    hf.parent.mkdir(parents=True, exist_ok=True)
    hf.write_text(
        json.dumps(sorted(ids), indent=2),
        encoding="utf-8",
    )


# ── Suite CRUD ─────────────────────────────────────────────────


def list_suites(project_root: Path) -> list[dict]:
    """List all test suites (summary — no step details).

    Merges suites from both local (.state/) and ledger (.ledger/).
    Local version takes precedence when both exist for the same ID.
    Computes ``git_dirty`` for in-git suites by comparing timestamps.

    Returns a list of dicts with suite metadata sorted by updated_at
    descending.
    """
    from src.core.services.ledger.worktree import worktree_path

    seen_ids: set[str] = set()
    summaries: list[dict] = []

    with _lock:
        # 1. Scan local (.state/) — these take precedence
        suites_path = _suites_dir(project_root)
        for f in suites_path.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                sid = data.get("id", f.stem)
                seen_ids.add(sid)
                summary = _build_summary(data, f.stem)
                # Compute git_dirty: in_git=True and updated_at > git_updated_at
                if summary["in_git"] and summary["git_updated_at"]:
                    summary["git_dirty"] = (
                        summary["updated_at"] > summary["git_updated_at"]
                    )
                else:
                    summary["git_dirty"] = False
                summaries.append(summary)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to read suite %s: %s", f.name, exc)

        # 2. Scan ledger (.ledger/) — only add suites not in local
        wt = worktree_path(project_root)
        ledger_dir = wt / "cdp-tests" / "suites"
        if ledger_dir.is_dir():
            hidden = _read_hidden_ids(project_root)
            for f in ledger_dir.glob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    sid = data.get("id", f.stem)
                    if sid in seen_ids or sid in hidden:
                        continue
                    seen_ids.add(sid)
                    summary = _build_summary(data, f.stem)
                    # Ledger-only suites are always in sync (no local edits)
                    summary["in_git"] = True
                    summary["git_dirty"] = False
                    summaries.append(summary)
                except (json.JSONDecodeError, OSError) as exc:
                    logger.warning(
                        "Failed to read ledger suite %s: %s", f.name, exc,
                    )

    # Sort by updated_at descending (newest first)
    summaries.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
    return summaries


def _build_summary(data: dict, stem: str) -> dict:
    """Build a summary dict from raw suite JSON data."""
    return {
        "id": data.get("id", stem),
        "name": data.get("name", ""),
        "description": data.get("description", ""),
        "target_url": data.get("target_url", ""),
        "category": data.get("category", "smoke"),
        "tags": data.get("tags", []),
        "step_count": len(data.get("steps", [])),
        "created_at": data.get("created_at", ""),
        "updated_at": data.get("updated_at", ""),
        "created_by": data.get("created_by", ""),
        "last_run_at": data.get("last_run_at", ""),
        "last_run_status": data.get("last_run_status", ""),
        "run_count": data.get("run_count", 0),
        "in_git": data.get("in_git", False),
        "git_updated_at": data.get("git_updated_at", ""),
    }


def get_suite(project_root: Path, suite_id: str) -> TestSuite | None:
    """Load a full test suite by ID.

    Checks local (.state/) first. If not found, checks ledger (.ledger/).
    Local is the "working copy" and always takes precedence.
    """
    from src.core.services.ledger.worktree import worktree_path

    with _lock:
        # 1. Check local
        local_path = _suites_dir(project_root) / f"{suite_id}.json"
        if local_path.is_file():
            try:
                data = json.loads(local_path.read_text(encoding="utf-8"))
                return TestSuite.from_dict(data)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to read suite %s: %s", suite_id, exc)
                return None

        # 2. Check ledger
        wt = worktree_path(project_root)
        ledger_path = wt / "cdp-tests" / "suites" / f"{suite_id}.json"
        if ledger_path.is_file():
            try:
                data = json.loads(ledger_path.read_text(encoding="utf-8"))
                return TestSuite.from_dict(data)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(
                    "Failed to read ledger suite %s: %s", suite_id, exc,
                )
                return None

    return None


def save_suite(project_root: Path, suite: TestSuite) -> None:
    """Save (create or update) a test suite.

    Writes to local (.state/) ONLY. Does NOT auto-commit to the ledger.
    The user must explicitly trigger "Add to Git" or "Sync to Git" to
    commit to the ledger branch.
    """
    from src.core.services.cdp_test.models import _now_iso

    suite.updated_at = _now_iso()
    path = _suites_dir(project_root) / f"{suite.id}.json"
    with _lock:
        path.write_text(
            json.dumps(suite.to_dict(), indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
    logger.info("Saved suite %s (%s)", suite.id, suite.name)


def delete_suite(project_root: Path, suite_id: str) -> bool:
    """Delete a test suite.

    Removes from local (.state/) if present.
    If the suite was in git, also removes from ledger (.ledger/) and
    commits the deletion. Adds to hidden list to prevent reappearing
    on next ledger pull.

    Returns True if it existed in either location.
    """
    from src.core.services.ledger.worktree import (
        ledger_add_and_commit,
        worktree_path,
    )

    found = False

    with _lock:
        # Delete from local
        local_path = _suites_dir(project_root) / f"{suite_id}.json"
        if local_path.is_file():
            local_path.unlink()
            found = True
            logger.info("Deleted suite %s from local", suite_id)

        # Delete from ledger
        wt = worktree_path(project_root)
        ledger_path = wt / "cdp-tests" / "suites" / f"{suite_id}.json"
        if ledger_path.is_file():
            ledger_path.unlink()
            found = True
            logger.info("Deleted suite %s from ledger", suite_id)

    # Outside lock: commit the deletion and update hidden list
    if found:
        # Add to hidden list so it doesn't reappear from remote pulls
        hidden = _read_hidden_ids(project_root)
        hidden.add(suite_id)
        _write_hidden_ids(project_root, hidden)

        # Commit deletion to ledger (if ledger file existed)
        try:
            ledger_add_and_commit(
                project_root,
                paths=[
                    f"cdp-tests/suites/{suite_id}.json",
                    "cdp-tests/.hidden-suites.json",
                ],
                message=f"cdp-test: delete suite {suite_id}",
            )
        except Exception as exc:
            logger.warning("Failed to commit suite deletion: %s", exc)

    return found


# ── Git operations ─────────────────────────────────────────────


def add_suite_to_git(project_root: Path, suite_id: str) -> bool:
    """Add a test suite to git (ledger branch).

    This is the FIRST commit. Takes the current local version and
    commits it to the ledger.

    1. Load suite from local storage (.state/)
    2. Set in_git = True, git_updated_at = updated_at
    3. Write to .ledger/cdp-tests/suites/<id>.json
    4. Update local copy with in_git = True, git_updated_at
    5. Commit to ledger branch

    Returns True if successful, False if suite not found.
    """
    from src.core.services.ledger.worktree import (
        ensure_worktree,
        ledger_add_and_commit,
    )

    suite = get_suite(project_root, suite_id)
    if suite is None:
        return False

    if suite.in_git:
        # Already in git — nothing to do
        return True

    # Ensure worktree is ready
    ensure_worktree(project_root)

    # Mark as in-git
    suite.in_git = True
    suite.git_updated_at = suite.updated_at

    # Write to ledger
    ledger_dir = _ledger_suites_dir(project_root)
    ledger_path = ledger_dir / f"{suite_id}.json"
    suite_json = json.dumps(suite.to_dict(), indent=2, ensure_ascii=True)

    with _lock:
        ledger_path.write_text(suite_json, encoding="utf-8")

        # Update local copy with in_git flag
        local_path = _suites_dir(project_root) / f"{suite_id}.json"
        local_path.write_text(suite_json, encoding="utf-8")

    # Commit to ledger branch
    ledger_add_and_commit(
        project_root,
        paths=[f"cdp-tests/suites/{suite_id}.json"],
        message=f"cdp-test: add suite {suite_id} ({suite.name})",
    )

    logger.info("Added suite %s to git", suite_id)
    return True


def sync_suite_to_git(project_root: Path, suite_id: str) -> bool:
    """Sync local changes to the ledger (commit updated version).

    Called when the user explicitly triggers "Sync to Git" in the UI
    after editing an in-git suite locally.

    1. Load suite from local storage (.state/)
    2. Verify in_git == True
    3. Set git_updated_at = updated_at
    4. Write to .ledger/cdp-tests/suites/<id>.json
    5. Update local copy with new git_updated_at
    6. Commit to ledger branch

    Returns True if successful, False if not found or not in git.
    """
    from src.core.services.ledger.worktree import (
        ensure_worktree,
        ledger_add_and_commit,
    )

    suite = get_suite(project_root, suite_id)
    if suite is None:
        return False

    if not suite.in_git:
        logger.warning("Cannot sync suite %s: not in git", suite_id)
        return False

    # Ensure worktree is ready
    ensure_worktree(project_root)

    # Update git timestamp to match local
    suite.git_updated_at = suite.updated_at

    # Write to ledger
    ledger_dir = _ledger_suites_dir(project_root)
    ledger_path = ledger_dir / f"{suite_id}.json"
    suite_json = json.dumps(suite.to_dict(), indent=2, ensure_ascii=True)

    with _lock:
        ledger_path.write_text(suite_json, encoding="utf-8")

        # Update local copy with new git_updated_at
        local_path = _suites_dir(project_root) / f"{suite_id}.json"
        local_path.write_text(suite_json, encoding="utf-8")

    # Commit to ledger branch
    ledger_add_and_commit(
        project_root,
        paths=[f"cdp-tests/suites/{suite_id}.json"],
        message=f"cdp-test: sync suite {suite_id} ({suite.name})",
    )

    logger.info("Synced suite %s to git", suite_id)
    return True


def remove_suite_from_git(project_root: Path, suite_id: str) -> bool:
    """Remove a test suite from git (ledger branch).

    The suite remains in local storage (.state/) but its ledger copy
    is deleted and the in_git flag is cleared.

    1. Load suite
    2. Set in_git = False, git_updated_at = ""
    3. Delete from .ledger/cdp-tests/suites/
    4. Update local copy with in_git = False
    5. Commit the deletion to ledger branch

    Returns True if successful, False if not found.
    """
    from src.core.services.ledger.worktree import (
        ensure_worktree,
        ledger_add_and_commit,
        worktree_path,
    )

    suite = get_suite(project_root, suite_id)
    if suite is None:
        return False

    if not suite.in_git:
        # Already not in git
        return True

    ensure_worktree(project_root)

    # Clear git flags
    suite.in_git = False
    suite.git_updated_at = ""

    with _lock:
        # Update local copy
        local_path = _suites_dir(project_root) / f"{suite_id}.json"
        local_path.write_text(
            json.dumps(suite.to_dict(), indent=2, ensure_ascii=True),
            encoding="utf-8",
        )

        # Delete from ledger
        wt = worktree_path(project_root)
        ledger_path = wt / "cdp-tests" / "suites" / f"{suite_id}.json"
        if ledger_path.is_file():
            ledger_path.unlink()

    # Commit the deletion
    ledger_add_and_commit(
        project_root,
        paths=[f"cdp-tests/suites/{suite_id}.json"],
        message=f"cdp-test: remove suite {suite_id} from git",
    )

    logger.info("Removed suite %s from git", suite_id)
    return True


# ── Result CRUD ────────────────────────────────────────────────


def list_results(
    project_root: Path,
    *,
    suite_id: str | None = None,
    last: int = 20,
) -> list[dict]:
    """List test run results (newest first).

    Optionally filter by suite_id.
    """
    results_path = _results_dir(project_root)
    items: list[dict] = []

    with _lock:
        for f in results_path.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if suite_id and data.get("suite_id") != suite_id:
                    continue
                items.append(data)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to read result %s: %s", f.name, exc)

    # Sort by started_at descending
    items.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return items[:last]


def get_result(project_root: Path, run_id: str) -> TestRunResult | None:
    """Load a single run result by ID."""
    path = _results_dir(project_root) / f"{run_id}.json"
    with _lock:
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return TestRunResult.from_dict(data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read result %s: %s", run_id, exc)
            return None


def save_result(project_root: Path, result: TestRunResult) -> None:
    """Save a test run result."""
    path = _results_dir(project_root) / f"{result.id}.json"
    with _lock:
        path.write_text(
            json.dumps(result.to_dict(), indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
    logger.info(
        "Saved result %s (suite=%s, status=%s)",
        result.id, result.suite_id, result.status,
    )
