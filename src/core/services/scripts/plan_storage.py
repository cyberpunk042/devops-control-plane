"""
Execution Plan storage — JSON file CRUD for plans and run results.

File layout::

    .state/
        cdp-plans/
            plans/
                <plan-id>.json          # ExecutionPlan serialized (working copy)
            results/
                <run-id>.json           # PlanRunResult serialized

    .ledger/
        cdp-plans/
            plans/
                <plan-id>.json          # ExecutionPlan committed to git
            .hidden-plans.json          # IDs of plans hidden by the user

Thread-safe: all file I/O is guarded by a module-level lock.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from src.core.services.scripts.plans import (
    ExecutionPlan,
    PlanRunResult,
)

logger = logging.getLogger(__name__)

_lock = threading.Lock()


# ── Local paths (.state/) ──────────────────────────────────────


def _plans_dir(project_root: Path) -> Path:
    """Return (and create) the plans directory."""
    d = project_root / ".state" / "cdp-plans" / "plans"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _results_dir(project_root: Path) -> Path:
    """Return (and create) the results directory."""
    d = project_root / ".state" / "cdp-plans" / "results"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Ledger paths (.ledger/) ────────────────────────────────────


def _ledger_plans_dir(project_root: Path) -> Path:
    """Return (and optionally create) the ledger plans directory."""
    from src.core.services.ledger.worktree import worktree_path

    d = worktree_path(project_root) / "cdp-plans" / "plans"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _hidden_plans_file(project_root: Path) -> Path:
    """Return path to the hidden-plans list in the ledger."""
    from src.core.services.ledger.worktree import worktree_path

    return worktree_path(project_root) / "cdp-plans" / ".hidden-plans.json"


def _read_hidden_ids(project_root: Path) -> set[str]:
    """Read the set of hidden plan IDs from the ledger."""
    hf = _hidden_plans_file(project_root)
    if hf.is_file():
        try:
            return set(json.loads(hf.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    return set()


def _write_hidden_ids(project_root: Path, ids: set[str]) -> None:
    """Write hidden plan IDs to the ledger."""
    hf = _hidden_plans_file(project_root)
    hf.parent.mkdir(parents=True, exist_ok=True)
    hf.write_text(
        json.dumps(sorted(ids), indent=2),
        encoding="utf-8",
    )


# ── Plan CRUD ──────────────────────────────────────────────────


def list_plans(project_root: Path) -> list[dict]:
    """List all execution plans (summary — no step details).

    Merges plans from both local (.state/) and ledger (.ledger/).
    Local version takes precedence when both exist for the same ID.
    Computes ``git_dirty`` for in-git plans by comparing timestamps.

    Returns a list of dicts with plan metadata sorted by updated_at
    descending.
    """
    from src.core.services.ledger.worktree import worktree_path

    seen_ids: set[str] = set()
    summaries: list[dict] = []

    with _lock:
        # 1. Scan local (.state/) — these take precedence
        plans_path = _plans_dir(project_root)
        for f in plans_path.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                pid = data.get("id", f.stem)
                seen_ids.add(pid)
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
                logger.warning("Failed to read plan %s: %s", f.name, exc)

        # 2. Scan ledger (.ledger/) — only add plans not in local
        wt = worktree_path(project_root)
        ledger_dir = wt / "cdp-plans" / "plans"
        if ledger_dir.is_dir():
            hidden = _read_hidden_ids(project_root)
            for f in ledger_dir.glob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    pid = data.get("id", f.stem)
                    if pid in seen_ids or pid in hidden:
                        continue
                    seen_ids.add(pid)
                    summary = _build_summary(data, f.stem)
                    # Ledger-only plans are always in sync (no local edits)
                    summary["in_git"] = True
                    summary["git_dirty"] = False
                    summaries.append(summary)
                except (json.JSONDecodeError, OSError) as exc:
                    logger.warning(
                        "Failed to read ledger plan %s: %s", f.name, exc,
                    )

    # Sort by updated_at descending (newest first)
    summaries.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
    return summaries


def _build_summary(data: dict, stem: str) -> dict:
    """Build a summary dict from raw plan JSON data."""
    return {
        "id": data.get("id", stem),
        "name": data.get("name", ""),
        "description": data.get("description", ""),
        "mode": data.get("mode", "fully_automated"),
        "step_count": len(data.get("steps", [])),
        "browser_mode": (
            data.get("browser_config", {}).get("mode", "")
            if data.get("browser_config") else "none"
        ),
        "created_at": data.get("created_at", ""),
        "updated_at": data.get("updated_at", ""),
        "last_run_at": data.get("last_run_at", ""),
        "last_run_status": data.get("last_run_status", ""),
        "run_count": data.get("run_count", 0),
        "in_git": data.get("in_git", False),
        "git_updated_at": data.get("git_updated_at", ""),
    }


def get_plan(project_root: Path, plan_id: str) -> ExecutionPlan | None:
    """Load a full execution plan by ID.

    Checks local (.state/) first. If not found, checks ledger (.ledger/).
    Local is the "working copy" and always takes precedence.
    """
    from src.core.services.ledger.worktree import worktree_path

    with _lock:
        # 1. Check local
        local_path = _plans_dir(project_root) / f"{plan_id}.json"
        if local_path.is_file():
            try:
                data = json.loads(local_path.read_text(encoding="utf-8"))
                return ExecutionPlan.from_dict(data)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to read plan %s: %s", plan_id, exc)
                return None

        # 2. Check ledger
        wt = worktree_path(project_root)
        ledger_path = wt / "cdp-plans" / "plans" / f"{plan_id}.json"
        if ledger_path.is_file():
            try:
                data = json.loads(ledger_path.read_text(encoding="utf-8"))
                return ExecutionPlan.from_dict(data)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(
                    "Failed to read ledger plan %s: %s", plan_id, exc,
                )
                return None

    return None


def save_plan(project_root: Path, plan: ExecutionPlan) -> None:
    """Save (create or update) an execution plan.

    Writes to local (.state/) ONLY. Does NOT auto-commit to the ledger.
    The user must explicitly trigger "Add to Git" or "Sync to Git" to
    commit to the ledger branch.
    """
    from src.core.services.scripts.plans import _now_iso

    plan.updated_at = _now_iso()
    path = _plans_dir(project_root) / f"{plan.id}.json"
    with _lock:
        path.write_text(
            json.dumps(plan.to_dict(), indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
    logger.info("Saved plan %s (%s)", plan.id, plan.name)


def delete_plan(project_root: Path, plan_id: str) -> bool:
    """Delete an execution plan.

    Removes from local (.state/) if present.
    If the plan was in git, also removes from ledger (.ledger/) and
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
        local_path = _plans_dir(project_root) / f"{plan_id}.json"
        if local_path.is_file():
            local_path.unlink()
            found = True
            logger.info("Deleted plan %s from local", plan_id)

        # Delete from ledger
        wt = worktree_path(project_root)
        ledger_path = wt / "cdp-plans" / "plans" / f"{plan_id}.json"
        if ledger_path.is_file():
            ledger_path.unlink()
            found = True
            logger.info("Deleted plan %s from ledger", plan_id)

    # Outside lock: commit the deletion and update hidden list
    if found:
        # Add to hidden list so it doesn't reappear from remote pulls
        hidden = _read_hidden_ids(project_root)
        hidden.add(plan_id)
        _write_hidden_ids(project_root, hidden)

        # Commit deletion to ledger (if ledger file existed)
        try:
            ledger_add_and_commit(
                project_root,
                paths=[
                    f"cdp-plans/plans/{plan_id}.json",
                    "cdp-plans/.hidden-plans.json",
                ],
                message=f"plans: delete plan {plan_id}",
            )
        except Exception as exc:
            logger.warning("Failed to commit plan deletion: %s", exc)

    return found


# ── Git operations ─────────────────────────────────────────────


def add_plan_to_git(project_root: Path, plan_id: str) -> bool:
    """Add an execution plan to git (ledger branch).

    This is the FIRST commit. Takes the current local version and
    commits it to the ledger.

    1. Load plan from local storage (.state/)
    2. Set in_git = True, git_updated_at = updated_at
    3. Write to .ledger/cdp-plans/plans/<id>.json
    4. Update local copy with in_git = True, git_updated_at
    5. Commit to ledger branch

    Returns True if successful, False if plan not found.
    """
    from src.core.services.ledger.worktree import (
        ensure_worktree,
        ledger_add_and_commit,
    )

    plan = get_plan(project_root, plan_id)
    if plan is None:
        return False

    if plan.in_git:
        # Already in git — nothing to do
        return True

    # Ensure worktree is ready
    ensure_worktree(project_root)

    # Mark as in-git
    plan.in_git = True
    plan.git_updated_at = plan.updated_at

    # Write to ledger
    ledger_dir = _ledger_plans_dir(project_root)
    ledger_path = ledger_dir / f"{plan_id}.json"
    plan_json = json.dumps(plan.to_dict(), indent=2, ensure_ascii=True)

    with _lock:
        ledger_path.write_text(plan_json, encoding="utf-8")

        # Update local copy with in_git flag
        local_path = _plans_dir(project_root) / f"{plan_id}.json"
        local_path.write_text(plan_json, encoding="utf-8")

    # Commit to ledger branch
    ledger_add_and_commit(
        project_root,
        paths=[f"cdp-plans/plans/{plan_id}.json"],
        message=f"plans: add plan {plan_id} ({plan.name})",
    )

    logger.info("Added plan %s to git", plan_id)
    return True


def sync_plan_to_git(project_root: Path, plan_id: str) -> bool:
    """Sync local changes to the ledger (commit updated version).

    Called when the user explicitly triggers "Sync to Git" in the UI
    after editing an in-git plan locally.

    1. Load plan from local storage (.state/)
    2. Verify in_git == True
    3. Set git_updated_at = updated_at
    4. Write to .ledger/cdp-plans/plans/<id>.json
    5. Update local copy with new git_updated_at
    6. Commit to ledger branch

    Returns True if successful, False if not found or not in git.
    """
    from src.core.services.ledger.worktree import (
        ensure_worktree,
        ledger_add_and_commit,
    )

    plan = get_plan(project_root, plan_id)
    if plan is None:
        return False

    if not plan.in_git:
        logger.warning("Cannot sync plan %s: not in git", plan_id)
        return False

    # Ensure worktree is ready
    ensure_worktree(project_root)

    # Update git timestamp to match local
    plan.git_updated_at = plan.updated_at

    # Write to ledger
    ledger_dir = _ledger_plans_dir(project_root)
    ledger_path = ledger_dir / f"{plan_id}.json"
    plan_json = json.dumps(plan.to_dict(), indent=2, ensure_ascii=True)

    with _lock:
        ledger_path.write_text(plan_json, encoding="utf-8")

        # Update local copy with new git_updated_at
        local_path = _plans_dir(project_root) / f"{plan_id}.json"
        local_path.write_text(plan_json, encoding="utf-8")

    # Commit to ledger branch
    ledger_add_and_commit(
        project_root,
        paths=[f"cdp-plans/plans/{plan_id}.json"],
        message=f"plans: sync plan {plan_id} ({plan.name})",
    )

    logger.info("Synced plan %s to git", plan_id)
    return True


def remove_plan_from_git(project_root: Path, plan_id: str) -> bool:
    """Remove an execution plan from git (ledger branch).

    The plan remains in local storage (.state/) but its ledger copy
    is deleted and the in_git flag is cleared.

    1. Load plan
    2. Set in_git = False, git_updated_at = ""
    3. Delete from .ledger/cdp-plans/plans/
    4. Update local copy with in_git = False
    5. Commit the deletion to ledger branch

    Returns True if successful, False if not found.
    """
    from src.core.services.ledger.worktree import (
        ensure_worktree,
        ledger_add_and_commit,
        worktree_path,
    )

    plan = get_plan(project_root, plan_id)
    if plan is None:
        return False

    if not plan.in_git:
        # Already not in git
        return True

    ensure_worktree(project_root)

    # Clear git flags
    plan.in_git = False
    plan.git_updated_at = ""

    with _lock:
        # Update local copy
        local_path = _plans_dir(project_root) / f"{plan_id}.json"
        local_path.write_text(
            json.dumps(plan.to_dict(), indent=2, ensure_ascii=True),
            encoding="utf-8",
        )

        # Delete from ledger
        wt = worktree_path(project_root)
        ledger_path = wt / "cdp-plans" / "plans" / f"{plan_id}.json"
        if ledger_path.is_file():
            ledger_path.unlink()

    # Commit the deletion
    ledger_add_and_commit(
        project_root,
        paths=[f"cdp-plans/plans/{plan_id}.json"],
        message=f"plans: remove plan {plan_id} from git",
    )

    logger.info("Removed plan %s from git", plan_id)
    return True


# ── Dependency checks ──────────────────────────────────────────


def check_plan_suite_deps(
    project_root: Path, plan_id: str,
) -> dict:
    """Check the git status of all suites referenced by a plan.

    Returns a dict with:
        - ``suites``: list of dicts, each with ``suite_id``, ``suite_name``,
          ``in_git``, ``git_dirty``
        - ``not_in_git``: list of suite dicts that are NOT in git
        - ``dirty``: list of suite dicts that are in git but have local changes

    Used by the frontend to warn before add-to-git / sync-to-git.
    """
    from src.core.services.cdp_test.storage import list_suites as list_all_suites

    plan = get_plan(project_root, plan_id)
    if plan is None:
        return {"suites": [], "not_in_git": [], "dirty": []}

    # Collect referenced suite IDs from cdp_test steps
    suite_ids: set[str] = set()
    for step in plan.steps:
        if step.type == "cdp_test" and step.suite_id:
            suite_ids.add(step.suite_id)

    if not suite_ids:
        return {"suites": [], "not_in_git": [], "dirty": []}

    # Build lookup from suite list (includes in_git, git_dirty)
    all_suites = list_all_suites(project_root)
    suite_map = {s["id"]: s for s in all_suites}

    result_suites = []
    not_in_git = []
    dirty = []

    for sid in sorted(suite_ids):
        s = suite_map.get(sid)
        if s is None:
            # Suite doesn't exist at all — still report it
            entry = {
                "suite_id": sid, "suite_name": "(missing)",
                "in_git": False, "git_dirty": False,
            }
            result_suites.append(entry)
            not_in_git.append(entry)
            continue

        entry = {
            "suite_id": sid,
            "suite_name": s.get("name", ""),
            "in_git": s.get("in_git", False),
            "git_dirty": s.get("git_dirty", False),
        }
        result_suites.append(entry)
        if not entry["in_git"]:
            not_in_git.append(entry)
        elif entry["git_dirty"]:
            dirty.append(entry)

    return {"suites": result_suites, "not_in_git": not_in_git, "dirty": dirty}


def find_plans_referencing_suite(
    project_root: Path, suite_id: str,
) -> list[dict]:
    """Find all in-git plans that reference a given suite ID.

    Scans all plans (local + ledger) and returns a list of dicts for
    plans that are ``in_git=True`` and have at least one ``cdp_test``
    step with the given ``suite_id``.

    Each dict: ``{"plan_id": "...", "plan_name": "..."}``.

    Used by the suite "Remove from Git" UI to warn about breaking
    dependencies.
    """
    all_plans = list_plans(project_root)
    dependents: list[dict] = []

    for p in all_plans:
        if not p.get("in_git", False):
            continue

        # Need to load full plan to inspect steps
        full = get_plan(project_root, p["id"])
        if full is None:
            continue

        for step in full.steps:
            if step.type == "cdp_test" and step.suite_id == suite_id:
                dependents.append({
                    "plan_id": p["id"],
                    "plan_name": p.get("name", ""),
                })
                break  # One match per plan is enough

    return dependents


# ── Result CRUD ────────────────────────────────────────────────


def list_results(
    project_root: Path,
    *,
    plan_id: str | None = None,
    last: int = 20,
) -> list[dict]:
    """List plan run results (newest first).

    Optionally filter by plan_id.
    """
    results_path = _results_dir(project_root)
    items: list[dict] = []

    with _lock:
        for f in results_path.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if plan_id and data.get("plan_id") != plan_id:
                    continue
                items.append(data)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to read result %s: %s", f.name, exc)

    # Sort by started_at descending
    items.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return items[:last]


def get_result(project_root: Path, run_id: str) -> PlanRunResult | None:
    """Load a single plan run result by ID."""
    path = _results_dir(project_root) / f"{run_id}.json"
    with _lock:
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return PlanRunResult.from_dict(data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read result %s: %s", run_id, exc)
            return None


def save_result(project_root: Path, result: PlanRunResult) -> None:
    """Save a plan run result."""
    path = _results_dir(project_root) / f"{result.id}.json"
    with _lock:
        path.write_text(
            json.dumps(result.to_dict(), indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
    logger.info(
        "Saved plan result %s (plan=%s, status=%s)",
        result.id, result.plan_id, result.status,
    )
