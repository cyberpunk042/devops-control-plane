"""
Git history & maintenance — gc, repack, history reset, filter-repo.

Channel-independent: no Flask or HTTP dependency.

These are "heavy" operations that may take minutes, so
timeouts are generous (300s) compared to normal git ops (15s).
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from src.core.services.git.ops import run_git

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  Maintenance operations
# ═══════════════════════════════════════════════════════════════════


def git_gc(project_root: Path, *, aggressive: bool = False) -> dict:
    """Run ``git gc`` to clean up and optimise the repository.

    Args:
        project_root: Repository root directory.
        aggressive: If True, uses ``--aggressive`` (slower, more thorough).

    Returns::

        {"ok": True, "aggressive": ..., "output": "..."}
        or {"error": "..."}
    """
    args: list[str] = ["gc"]
    if aggressive:
        args.append("--aggressive")

    r = run_git(*args, cwd=project_root, timeout=300)
    if r.returncode != 0:
        return {"error": f"git gc failed: {r.stderr.strip()}"}

    return {
        "ok": True,
        "aggressive": aggressive,
        "output": (r.stdout.strip() + "\n" + r.stderr.strip()).strip(),
    }


def git_repack(project_root: Path) -> dict:
    """Repack objects for better compression.

    Runs ``git repack -a -d --depth=250 --window=250``.

    Args:
        project_root: Repository root directory.

    Returns::

        {"ok": True, "output": "..."}
        or {"error": "..."}
    """
    r = run_git(
        "repack", "-a", "-d", "--depth=250", "--window=250",
        cwd=project_root, timeout=300,
    )
    if r.returncode != 0:
        return {"error": f"git repack failed: {r.stderr.strip()}"}

    return {
        "ok": True,
        "output": (r.stdout.strip() + "\n" + r.stderr.strip()).strip(),
    }


# ═══════════════════════════════════════════════════════════════════
#  History rewriting
# ═══════════════════════════════════════════════════════════════════


def git_history_reset(
    project_root: Path,
    message: str = "Initial commit (history reset)",
) -> dict:
    """Reset git history to a single commit (orphan branch technique).

    Process:
        1. Detect current branch name
        2. Create orphan branch ``_history_reset_tmp``
        3. Stage all files
        4. Commit with *message*
        5. Delete old branch
        6. Rename temp branch → old branch name
        7. Force push to origin (if remote exists)

    This is **destructive and irreversible**.  Callers must confirm
    with the user before invoking.

    Args:
        project_root: Repository root directory.
        message: Commit message for the single commit.

    Returns::

        {"ok": True, "branch": "...", "hash": "...", "pushed": True/False}
        or {"error": "..."}
    """
    message = message.strip() or "Initial commit (history reset)"
    tmp_branch = "_history_reset_tmp"

    # Step 1: Detect current branch
    r = run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=project_root)
    if r.returncode != 0:
        return {"error": f"Cannot detect current branch: {r.stderr.strip()}"}
    current_branch = r.stdout.strip()
    if not current_branch or current_branch == "HEAD":
        return {"error": "Detached HEAD state — cannot reset history"}

    # Step 2: Create orphan branch
    r = run_git("checkout", "--orphan", tmp_branch, cwd=project_root)
    if r.returncode != 0:
        return {"error": f"Failed to create orphan branch: {r.stderr.strip()}"}

    # Step 3: Stage all files
    r = run_git("add", "-A", cwd=project_root)
    if r.returncode != 0:
        # Try to recover back to original branch
        run_git("checkout", current_branch, cwd=project_root)
        run_git("branch", "-D", tmp_branch, cwd=project_root)
        return {"error": f"Failed to stage files: {r.stderr.strip()}"}

    # Step 4: Commit
    r = run_git("commit", "-m", message, cwd=project_root)
    if r.returncode != 0:
        run_git("checkout", current_branch, cwd=project_root)
        run_git("branch", "-D", tmp_branch, cwd=project_root)
        return {"error": f"Failed to commit: {r.stderr.strip()}"}

    new_hash = r.stdout.strip().split()[-1] if r.stdout.strip() else "unknown"
    # Extract short hash from output like "[_history_reset_tmp (root-commit) abc1234] ..."
    for part in r.stdout.strip().split():
        if len(part) >= 7 and part.replace("]", "").isalnum():
            new_hash = part.replace("]", "")
            break

    # Step 5: Delete old branch
    r = run_git("branch", "-D", current_branch, cwd=project_root)
    if r.returncode != 0:
        return {
            "error": f"Orphan commit created but failed to delete old branch: "
                     f"{r.stderr.strip()}",
        }

    # Step 6: Rename temp → old branch name
    r = run_git("branch", "-m", current_branch, cwd=project_root)
    if r.returncode != 0:
        return {
            "error": f"Orphan commit created, old branch deleted, but rename failed: "
                     f"{r.stderr.strip()}. You are now on branch '{tmp_branch}'.",
        }

    # Step 7: Force push (if origin exists)
    pushed = False
    r_remote = run_git("remote", "get-url", "origin", cwd=project_root)
    if r_remote.returncode == 0 and r_remote.stdout.strip():
        r_push = run_git(
            "push", "--force", "origin", current_branch,
            cwd=project_root, timeout=60,
        )
        if r_push.returncode == 0:
            pushed = True
            logger.info("History reset: force-pushed %s to origin", current_branch)
        else:
            logger.warning(
                "History reset: force push failed: %s", r_push.stderr.strip(),
            )

    logger.info(
        "History reset complete: branch=%s hash=%s pushed=%s",
        current_branch, new_hash, pushed,
    )
    return {
        "ok": True,
        "branch": current_branch,
        "hash": new_hash,
        "pushed": pushed,
        "message": f"History reset to single commit on '{current_branch}'",
    }


def git_filter_repo(
    project_root: Path,
    *,
    paths: list[str],
    force: bool = False,
) -> dict:
    """Scrub specific files/paths from entire git history.

    Wraps ``git filter-repo --invert-paths --path <path> [--force]``.
    Each path in *paths* is removed from every commit in history.

    Requires ``git-filter-repo`` (installable via the tool install system).

    Use cases:
        - Remove accidentally committed secrets
        - Strip large binaries from history
        - Clean sensitive data from all commits

    Args:
        project_root: Repository root directory.
        paths: List of file paths or patterns to remove from history.
        force: If True, pass ``--force`` (required on repos that are
               not a fresh clone).

    Returns::

        {"ok": True, "removed_paths": [...], "output": "..."}
        {"ok": False, "error": "git-filter-repo not installed",
         "tool_name": "git-filter-repo"}
    """
    # ── Availability gate ──────────────────────────────────────────
    if not shutil.which("git-filter-repo"):
        return {
            "ok": False,
            "error": "git-filter-repo is not installed",
            "tool_name": "git-filter-repo",
        }

    # ── Validate inputs ───────────────────────────────────────────
    paths = [p.strip() for p in paths if p.strip()]
    if not paths:
        return {"error": "At least one path is required"}

    # ── Build command ─────────────────────────────────────────────
    args: list[str] = ["filter-repo", "--invert-paths"]
    for p in paths:
        args.extend(["--path", p])
    if force:
        args.append("--force")

    # git filter-repo is a git sub-command (git-filter-repo)
    r = run_git(*args, cwd=project_root, timeout=300)
    if r.returncode != 0:
        return {"error": f"git filter-repo failed: {r.stderr.strip()}"}

    output = (r.stdout.strip() + "\n" + r.stderr.strip()).strip()
    logger.info("filter-repo complete: removed %s", paths)

    return {
        "ok": True,
        "removed_paths": paths,
        "output": output,
    }
