"""
Git worktree management for the SCP ledger.

Provides a dedicated ``.ledger/`` worktree at the project root for
writes to the ``ledger`` orphan branch. Also provides helpers for
annotated tags and git notes — operations that run against the main repo.

Design:
    - ``_run_ledger_git()`` operates in ``.ledger/`` (git -C)
    - ``_run_main_git()`` operates in the main project root
    - ``ensure_worktree()`` is idempotent — safe to call on every operation
    - All functions return errors gracefully; callers never see exceptions
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# ─── Constants ──────────────────────────────────────────────────────────

LEDGER_BRANCH = "ledger"
WORKTREE_DIR = ".ledger"
GITIGNORE_ENTRY = ".ledger/"
TAG_PREFIX = "scp/run/"


class GitIdentityError(Exception):
    """Raised when git user.name / user.email are not configured."""


# ═══════════════════════════════════════════════════════════════════════
#  Low-level git runners
# ═══════════════════════════════════════════════════════════════════════


def _run_ledger_git(
    *args: str,
    project_root: Path,
    timeout: int = 15,
) -> subprocess.CompletedProcess[str]:
    """Run a git command in the .ledger worktree.

    Equivalent to: ``git -C <project_root>/.ledger <args>``
    Injects git auth env (ssh-agent, etc.) automatically.
    """
    from src.core.services.git_auth import git_env

    wt = project_root / WORKTREE_DIR
    cmd = ["git", "-C", str(wt), *args]
    logger.debug("ledger-git: %s", " ".join(cmd))
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=git_env(),
    )


def _run_main_git(
    *args: str,
    project_root: Path,
    timeout: int = 15,
) -> subprocess.CompletedProcess[str]:
    """Run a git command in the main repo (for tags, notes, fetch).

    Injects git auth env (ssh-agent, etc.) automatically.
    """
    from src.core.services.git_auth import git_env

    cmd = ["git", "-C", str(project_root), *args]
    logger.debug("main-git: %s", " ".join(cmd))
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=git_env(),
    )


import time as _time

# Rebase cooldown — prevents retrying the same failed rebase every 5 seconds.
# When rebase fails (e.g., conflict), wait before retrying.
_rebase_fail_ts: float = 0
_REBASE_COOLDOWN = 300  # 5 minutes


def _safe_rebase(project_root: Path, *, label: str = "rebase") -> bool:
    """Stash → rebase origin/ledger → pop.  Returns True on success.

    Wraps the common stash/rebase/pop pattern so uncommitted changes
    (e.g. updated trace metadata) don't block the rebase.

    Includes a cooldown: if a rebase failed recently, skip the attempt
    to avoid an infinite retry loop on every poll.
    """
    global _rebase_fail_ts

    # Skip if a recent rebase failed (cooldown active)
    if _rebase_fail_ts and (_time.time() - _rebase_fail_ts) < _REBASE_COOLDOWN:
        return False

    # Stash uncommitted changes (modified tracked files only —
    # local traces now live outside the worktree in .state/traces/)
    stash_r = _run_ledger_git(
        "stash",
        project_root=project_root, timeout=10,
    )
    did_stash = (
        stash_r.returncode == 0
        and "No local changes" not in stash_r.stdout
    )

    r = _run_ledger_git(
        "rebase", f"origin/{LEDGER_BRANCH}",
        project_root=project_root, timeout=15,
    )
    ok = r.returncode == 0
    if not ok:
        stderr = r.stderr.strip()
        if stderr:
            logger.warning("Ledger %s issue: %s", label, stderr)
        _run_ledger_git("rebase", "--abort", project_root=project_root)

        # Set cooldown to prevent retry loop
        _rebase_fail_ts = _time.time()

        # Notify user with resolution options
        try:
            from src.core.services.event_bus import bus
            bus.publish("ledger:conflict", key="rebase", data={
                "error": "Ledger rebase conflict — remote sync paused.",
                "detail": stderr[:200] if stderr else "",
                "label": label,
                "needs_resolution": True,
            })
        except Exception:
            pass
    else:
        # Success — clear any previous cooldown
        _rebase_fail_ts = 0

    # Restore stashed changes
    if did_stash:
        _run_ledger_git(
            "stash", "pop",
            project_root=project_root, timeout=10,
        )

    return ok


def ledger_resolve_conflict(project_root: Path, action: str) -> dict:
    """Resolve a ledger rebase conflict.

    Args:
        project_root: Repository root.
        action: One of:
          - ``"retry"``  — abort current rebase, fetch fresh, rebase again.
                           Safest option. With ``.gitattributes`` union merge,
                           JSONL conflicts auto-resolve. No data loss.
          - ``"skip"``   — skip the conflicting commit and continue rebase.
                           The local commit is dropped (message still in file
                           but won't sync to remote). Moderate risk.
          - ``"reset"``  — hard-reset local ledger to remote. ALL local
                           unpushed commits are discarded. Clean state.

    Returns:
        ``{"ok": True, "message": "..."}`` or ``{"ok": False, "error": "..."}``.
    """
    global _rebase_fail_ts

    logger.info("Ledger conflict resolution: action=%s", action)

    if action == "retry":
        # Abort any in-progress rebase
        _run_ledger_git("rebase", "--abort", project_root=project_root)
        logger.info("Ledger resolve (retry): aborted any in-progress rebase")

        # Fetch latest from remote
        r = _run_ledger_git(
            "fetch", "origin",
            f"+refs/heads/{LEDGER_BRANCH}:refs/remotes/origin/{LEDGER_BRANCH}",
            project_root=project_root,
            timeout=30,
        )
        if r.returncode != 0:
            msg = f"Fetch failed: {r.stderr.strip()[:200]}"
            logger.warning("Ledger resolve (retry): %s", msg)
            return {"ok": False, "error": msg}
        logger.info("Ledger resolve (retry): fetch succeeded")

        # Clear cooldown and retry rebase
        _rebase_fail_ts = 0
        ok = _safe_rebase(project_root, label="conflict_retry")
        if ok:
            logger.info("Ledger resolve (retry): rebase succeeded — sync restored")
            return {"ok": True, "message": "Rebase succeeded — sync restored."}
        logger.warning("Ledger resolve (retry): rebase still conflicts")
        return {"ok": False, "error": "Rebase still conflicts. Try 'Skip' or 'Reset'."}

    elif action == "skip":
        # Abort current rebase, then rebase with --skip for conflicting commits
        _run_ledger_git("rebase", "--abort", project_root=project_root)
        logger.info("Ledger resolve (skip): aborted rebase, starting fresh rebase")

        # Fetch + rebase, but this time if it fails, skip
        _run_ledger_git(
            "fetch", "origin",
            f"+refs/heads/{LEDGER_BRANCH}:refs/remotes/origin/{LEDGER_BRANCH}",
            project_root=project_root,
            timeout=30,
        )
        r = _run_ledger_git(
            "rebase", f"origin/{LEDGER_BRANCH}",
            project_root=project_root, timeout=15,
        )
        if r.returncode != 0:
            logger.info("Ledger resolve (skip): rebase conflict, skipping commit(s)")
            # Skip the conflicting commit(s)
            for i in range(10):  # max 10 skips
                skip_r = _run_ledger_git("rebase", "--skip", project_root=project_root, timeout=10)
                logger.info("Ledger resolve (skip): skip #%d rc=%d", i + 1, skip_r.returncode)
                # Check if rebase is done
                check = _run_ledger_git(
                    "status", project_root=project_root, timeout=5,
                )
                if "rebase in progress" not in check.stdout.lower():
                    logger.info("Ledger resolve (skip): rebase completed after %d skip(s)", i + 1)
                    break

        _rebase_fail_ts = 0
        logger.info("Ledger resolve (skip): done — sync restored")
        return {"ok": True, "message": "Conflicting commit(s) skipped — sync restored."}

    elif action == "reset":
        # Abort any in-progress rebase
        _run_ledger_git("rebase", "--abort", project_root=project_root)
        logger.info("Ledger resolve (reset): aborted rebase, fetching remote")

        # Fetch latest
        _run_ledger_git(
            "fetch", "origin",
            f"+refs/heads/{LEDGER_BRANCH}:refs/remotes/origin/{LEDGER_BRANCH}",
            project_root=project_root,
            timeout=30,
        )

        # Hard reset to remote
        r = _run_ledger_git(
            "reset", "--hard", f"origin/{LEDGER_BRANCH}",
            project_root=project_root, timeout=15,
        )
        _rebase_fail_ts = 0
        if r.returncode == 0:
            logger.info("Ledger resolve (reset): hard reset succeeded — clean state")
            return {"ok": True, "message": "Ledger reset to remote — clean state."}
        msg = f"Reset failed: {r.stderr.strip()[:200]}"
        logger.warning("Ledger resolve (reset): %s", msg)
        return {"ok": False, "error": msg}

    else:
        return {"ok": False, "error": f"Unknown action: {action}"}


# ═══════════════════════════════════════════════════════════════════════
#  Worktree lifecycle
# ═══════════════════════════════════════════════════════════════════════


def worktree_path(project_root: Path) -> Path:
    """Return the worktree directory path: ``<project_root>/.ledger``."""
    return project_root / WORKTREE_DIR


def ensure_worktree(project_root: Path) -> Path:
    """Ensure the ``.ledger`` worktree exists and is healthy.

    Steps:
      1. Try to fetch ``ledger`` from origin (ignore if no remote)
      2. If ``ledger`` branch doesn't exist locally, create it as orphan
      3. If ``.ledger/`` dir doesn't exist, ``git worktree add``
      4. Ensure ``.ledger/`` is in ``.gitignore``
      5. Ensure VS Code ignores the worktree repo

    Idempotent — safe to call on every operation.
    Returns the worktree path.

    Raises nothing — logs errors and returns the path regardless.
    """
    wt = worktree_path(project_root)

    # 1. Ensure local branch exists (may need to fetch first if brand new)
    if not _branch_exists(project_root, LEDGER_BRANCH):
        # Try to fetch from origin before creating orphan
        _run_main_git(
            "fetch", "origin",
            f"{LEDGER_BRANCH}:{LEDGER_BRANCH}",
            project_root=project_root,
        )

    # 2. Ensure local branch exists (create orphan if fetch didn't bring it)
    if not _branch_exists(project_root, LEDGER_BRANCH):
        _create_orphan_branch(project_root, LEDGER_BRANCH)

    # 3. Ensure worktree directory exists
    if not _worktree_is_valid(project_root):
        _attach_worktree(project_root)

    # 4. Fetch + rebase latest from origin into worktree.
    #    We avoid `pull --rebase` because VS Code injects vscode-merge-base
    #    config entries that cause "Cannot rebase onto multiple branches."
    #    Using fetch + rebase bypasses branch tracking config entirely.
    #    Only attempt if auth has been verified — otherwise this hangs for 30s
    #    waiting for SSH passphrase on machines that haven't unlocked yet.
    if wt.is_dir():
        from src.core.services.git_auth import is_auth_ok
        if is_auth_ok():
            r = _run_ledger_git(
                "fetch", "origin",
                f"+refs/heads/{LEDGER_BRANCH}:refs/remotes/origin/{LEDGER_BRANCH}",
                project_root=project_root,
                timeout=30,
            )
            if r.returncode == 0:
                _safe_rebase(project_root, label="ensure_worktree")
            else:
                stderr = r.stderr.strip()
                if not any(s in stderr.lower() for s in (
                    "no tracking", "couldn't find remote", "no such remote",
                    "invalid upstream",
                )):
                    logger.warning("Ledger fetch in ensure_worktree: %s", stderr)
                    from src.core.services.git.gh_api import check_and_notify_github_outage
                    check_and_notify_github_outage(stderr)

    # 5. Ensure .gitignore contains the entry
    _ensure_gitignore(project_root)

    # 6. Ensure VS Code ignores the worktree repository
    _ensure_vscode_git_ignored(project_root)

    # 7. Ensure .gitattributes in worktree for union merge on JSONL
    _ensure_ledger_gitattributes(project_root)

    return wt


def _branch_exists(project_root: Path, branch: str) -> bool:
    """Check if a local branch exists."""
    r = _run_main_git(
        "rev-parse", "--verify", f"refs/heads/{branch}",
        project_root=project_root,
    )
    return r.returncode == 0


def _create_orphan_branch(project_root: Path, branch: str) -> None:
    """Create an orphan branch with an empty initial commit.

    Uses plumbing commands (hash-object + mktree + commit-tree + update-ref)
    to create the branch without touching the worktree or index.
    """
    logger.info("Creating orphan branch '%s'", branch)

    # Create an empty tree (mktree reads from stdin; empty input = empty tree)
    r = subprocess.run(
        ["git", "-C", str(project_root), "mktree"],
        input="",
        capture_output=True,
        text=True,
        timeout=10,
    )
    empty_tree = r.stdout.strip()
    if not empty_tree:
        logger.error("Failed to create empty tree for orphan branch")
        return

    # Create a commit with that empty tree (no parent = orphan)
    r = subprocess.run(
        ["git", "-C", str(project_root), "commit-tree", empty_tree, "-m", "ledger: init"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if r.returncode != 0:
        logger.error("Failed to create initial commit for orphan branch: %s", r.stderr.strip())
        return
    commit_sha = r.stdout.strip()

    # Point the branch ref at the commit
    r = _run_main_git(
        "update-ref", f"refs/heads/{branch}", commit_sha,
        project_root=project_root,
    )
    if r.returncode != 0:
        logger.error("Failed to create branch ref: %s", r.stderr.strip())
        return

    logger.info("Orphan branch '%s' created at %s", branch, commit_sha[:12])


def _worktree_is_valid(project_root: Path) -> bool:
    """Check if the .ledger worktree directory exists and is a valid git worktree."""
    wt = worktree_path(project_root)
    if not wt.is_dir():
        return False
    # Check for .git file (worktree link)
    git_link = wt / ".git"
    return git_link.exists()


def _attach_worktree(project_root: Path) -> None:
    """Attach the .ledger worktree to the ledger branch."""
    wt = worktree_path(project_root)
    logger.info("Attaching worktree at %s", wt)

    # Remove stale worktree registration if directory was deleted
    _run_main_git("worktree", "prune", project_root=project_root)

    r = _run_main_git(
        "worktree", "add",
        "-B", LEDGER_BRANCH,
        str(wt),
        LEDGER_BRANCH,
        project_root=project_root,
    )
    if r.returncode != 0:
        logger.error("Failed to attach worktree: %s", r.stderr.strip())
    else:
        logger.info("Worktree attached at %s", wt)


def _ensure_gitignore(project_root: Path) -> None:
    """Ensure ``.ledger/`` is in ``.gitignore``."""
    gitignore = project_root / ".gitignore"

    if gitignore.is_file():
        content = gitignore.read_text(encoding="utf-8")
        if GITIGNORE_ENTRY in content:
            return  # Already there
        # Ensure trailing newline before appending
        if content and not content.endswith("\n"):
            content += "\n"
    else:
        content = ""

    content += f"\n# SCP Ledger worktree (Phase 1A)\n{GITIGNORE_ENTRY}\n"
    gitignore.write_text(content, encoding="utf-8")
    logger.debug("Added %s to .gitignore", GITIGNORE_ENTRY)


# Content for the ledger .gitattributes — union merge for JSONL
# so that multi-machine chat message appends never conflict.
_LEDGER_GITATTRIBUTES = """# Auto-generated by ensure_worktree — do not edit.
# JSONL files use union merge: when both sides append lines,
# git keeps ALL lines instead of reporting a conflict.
*.jsonl merge=union
"""


def _ensure_ledger_gitattributes(project_root: Path) -> None:
    """Ensure ``.gitattributes`` exists inside the ledger worktree.

    Configures ``*.jsonl merge=union`` so that multi-machine chat
    appends to ``messages.jsonl`` are auto-resolved (keep all lines).

    Commits the file to the ledger branch if newly created or changed.
    """
    wt = worktree_path(project_root)
    ga = wt / ".gitattributes"

    # Already correct — skip
    if ga.is_file():
        existing = ga.read_text(encoding="utf-8")
        if "merge=union" in existing:
            return

    # Write the file
    ga.write_text(_LEDGER_GITATTRIBUTES, encoding="utf-8")
    logger.info("Created .gitattributes in ledger worktree (union merge for JSONL)")

    # Commit to ledger branch
    ledger_add_and_commit(
        project_root,
        paths=[".gitattributes"],
        message="chore: union merge for jsonl (prevent chat conflicts)",
    )


def _ensure_vscode_git_ignored(project_root: Path) -> None:
    """Ensure VS Code ignores the ``.ledger`` worktree in its Git panel.

    Adds ``".ledger"`` to ``git.ignoredRepositories`` in
    ``.vscode/settings.json``.  Idempotent.
    """
    import json

    vscode_dir = project_root / ".vscode"
    settings_file = vscode_dir / "settings.json"

    settings: dict = {}
    if settings_file.is_file():
        try:
            raw = settings_file.read_text(encoding="utf-8")
            settings = json.loads(raw)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not parse .vscode/settings.json: %s", e)
            return  # Don't risk corrupting an existing file

    ignored = settings.get("git.ignoredRepositories", [])
    if not isinstance(ignored, list):
        ignored = []

    entry = ".ledger"
    if entry in ignored:
        return  # Already configured

    ignored.append(entry)
    settings["git.ignoredRepositories"] = ignored

    vscode_dir.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(
        json.dumps(settings, indent=4) + "\n",
        encoding="utf-8",
    )
    logger.debug("Added %s to .vscode/settings.json git.ignoredRepositories", entry)


# ═══════════════════════════════════════════════════════════════════════
#  Tag operations (run against main repo)
# ═══════════════════════════════════════════════════════════════════════


def create_run_tag(
    project_root: Path,
    tag_name: str,
    target_sha: str,
    *,
    message: str,
) -> bool:
    """Create an annotated tag in the main repo.

    Args:
        project_root: Repository root.
        tag_name: Full tag name (e.g. ``scp/run/run_20260217...``).
        target_sha: The commit SHA to tag (usually HEAD on main).
        message: Tag message (compact JSON of the Run model).

    Returns:
        True if tag was created successfully.
    """
    r = _run_main_git(
        "tag", "-a", tag_name,
        target_sha,
        "-m", message,
        project_root=project_root,
    )
    if r.returncode != 0:
        logger.error("Failed to create tag %s: %s", tag_name, r.stderr.strip())
        return False
    return True


def list_run_tags(project_root: Path) -> list[str]:
    """List tags matching ``scp/run/*``, sorted newest-first.

    Uses ``--sort=-creatordate`` to get chronological order.
    """
    r = _run_main_git(
        "tag", "-l", f"{TAG_PREFIX}*",
        "--sort=-creatordate",
        project_root=project_root,
    )
    if r.returncode != 0:
        logger.warning("Failed to list run tags: %s", r.stderr.strip())
        return []
    return [line.strip() for line in r.stdout.splitlines() if line.strip()]


def read_tag_message(project_root: Path, tag_name: str) -> str | None:
    """Read the message of an annotated tag.

    Returns the message body (stripping the tag header), or None if
    the tag doesn't exist.
    """
    r = _run_main_git(
        "tag", "-l", tag_name,
        "--format=%(contents)",
        project_root=project_root,
    )
    if r.returncode != 0 or not r.stdout.strip():
        return None
    return r.stdout.strip()


def current_head_sha(project_root: Path) -> str | None:
    """Get the current HEAD SHA in the main repo. Returns None if no commits."""
    r = _run_main_git("rev-parse", "HEAD", project_root=project_root)
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def current_user(project_root: Path) -> str:
    """Get the git user.name from config, or 'unknown'."""
    r = _run_main_git("config", "user.name", project_root=project_root)
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    return "unknown"


# ═══════════════════════════════════════════════════════════════════════
#  Ledger worktree commit helpers
# ═══════════════════════════════════════════════════════════════════════


def ledger_add_and_commit(project_root: Path, paths: list[str], message: str) -> bool:
    """Stage and commit files in the ledger worktree.

    Args:
        project_root: Main project root.
        paths: Paths relative to the worktree root to stage (e.g. ``ledger/runs/...``).
        message: Commit message.

    Returns:
        True if commit succeeded.

    Raises:
        GitIdentityError: If git user.name/email are not configured.
    """
    for p in paths:
        r = _run_ledger_git("add", p, project_root=project_root)
        if r.returncode != 0:
            logger.warning("git add failed for %s: %s", p, r.stderr.strip())

    r = _run_ledger_git(
        "commit", "-m", message,
        "--allow-empty",          # don't fail if nothing changed
        project_root=project_root,
    )
    if r.returncode != 0:
        stderr = r.stderr.strip()
        # "nothing to commit" is not an error
        if "nothing to commit" in stderr or "nothing to commit" in r.stdout:
            logger.debug("Nothing to commit in ledger worktree")
            return True

        # Git identity not configured — surface to frontend via SSE AND raise
        if "please tell me who you are" in stderr.lower():
            logger.warning("Git identity not configured — commit blocked")
            try:
                from src.core.services.event_bus import bus
                bus.publish("auth:needed", key="git", data={
                    "needs": "git_identity",
                    "error": "Git user.name and user.email are not configured",
                })
            except Exception:
                pass
            raise GitIdentityError(
                "Git identity not configured — please set your name and email."
            )

        logger.error("Ledger commit failed: %s", stderr)
        return False
    return True


# ═══════════════════════════════════════════════════════════════════════
#  Notes operations (for Phase 1B — Chat)
# ═══════════════════════════════════════════════════════════════════════


def notes_append(
    project_root: Path,
    ref: str,
    target: str,
    content: str,
) -> bool:
    """Append content to a git note under the given ref.

    Args:
        project_root: Repository root.
        ref: Notes ref (e.g. ``refs/notes/chat``).
        target: Object to attach the note to (tag SHA, commit SHA).
        content: Content to append.

    Returns:
        True if successful.
    """
    r = subprocess.run(
        ["git", "-C", str(project_root), "notes",
         "--ref", ref, "append", target, "-m", content],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if r.returncode != 0:
        logger.error("notes append failed: %s", r.stderr.strip())
        return False
    return True


def notes_show(
    project_root: Path,
    ref: str,
    target: str,
) -> str | None:
    """Read a git note from a target object.

    Returns the note content, or None if no note exists.
    """
    r = subprocess.run(
        ["git", "-C", str(project_root), "notes",
         "--ref", ref, "show", target],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if r.returncode != 0:
        return None
    return r.stdout


# ═══════════════════════════════════════════════════════════════════════
#  Push / Pull
# ═══════════════════════════════════════════════════════════════════════


def push_ledger_branch(project_root: Path) -> bool:
    """Push ledger branch to origin (with fetch+rebase first).

    Steps:
      1. ``git -C .ledger fetch origin +refs/heads/ledger:refs/remotes/origin/ledger``
      2. ``git -C .ledger rebase origin/ledger``
      3. ``git -C .ledger push origin ledger``
    """
    # Fetch first
    r = _run_ledger_git(
        "fetch", "origin",
        f"+refs/heads/{LEDGER_BRANCH}:refs/remotes/origin/{LEDGER_BRANCH}",
        project_root=project_root,
        timeout=30,
    )
    if r.returncode != 0:
        stderr = r.stderr.strip()
        if "no tracking" not in stderr.lower() and "couldn't find remote" not in stderr.lower():
            logger.warning("Ledger fetch (pre-push) issue: %s", stderr)

    # Rebase (stash-safe to handle local-only files)
    _safe_rebase(project_root, label="pre-push")

    # Push
    r = _run_ledger_git(
        "push", "origin", LEDGER_BRANCH,
        project_root=project_root,
        timeout=30,
    )
    if r.returncode != 0:
        logger.error("Ledger push failed: %s", r.stderr.strip())
        return False
    return True


def push_run_tags(project_root: Path) -> bool:
    """Push scp/run/* tags to origin."""
    r = _run_main_git(
        "push", "origin", "--tags",
        project_root=project_root,
        timeout=30,
    )
    if r.returncode != 0:
        logger.warning("Tag push issue: %s", r.stderr.strip())
        return False
    return True


def pull_ledger_branch(project_root: Path) -> bool:
    """Pull ledger branch from origin (fetch + rebase).

    Uses fetch + rebase instead of pull --rebase to avoid VS Code
    vscode-merge-base config entries that cause "Cannot rebase onto
    multiple branches."

    Steps:
      1. ``git -C .ledger fetch origin ledger``
      2. ``git -C .ledger rebase FETCH_HEAD``
    """
    r = _run_ledger_git(
        "fetch", "origin",
        f"+refs/heads/{LEDGER_BRANCH}:refs/remotes/origin/{LEDGER_BRANCH}",
        project_root=project_root,
        timeout=30,
    )
    if r.returncode != 0:
        stderr = r.stderr.strip()
        if "no tracking" not in stderr.lower() and "couldn't find remote" not in stderr.lower():
            logger.warning("Ledger fetch issue: %s", stderr)
            from src.core.services.git.gh_api import check_and_notify_github_outage
            check_and_notify_github_outage(stderr)
            return False

    if not _safe_rebase(project_root, label="fetch_and_rebase"):
        return False
    return True


def fetch_run_tags(project_root: Path) -> bool:
    """Fetch scp/run/* tags from origin."""
    r = _run_main_git(
        "fetch", "origin",
        f"refs/tags/{TAG_PREFIX}*:refs/tags/{TAG_PREFIX}*",
        project_root=project_root,
        timeout=30,
    )
    if r.returncode != 0:
        logger.warning("Tag fetch issue: %s", r.stderr.strip())
        return False
    return True
