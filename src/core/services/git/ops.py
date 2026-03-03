"""
Git core operations — status, log, commit, pull, push, low-level runners.

Channel-independent: no Flask or HTTP dependency.

Provides the low-level ``run_git`` and ``run_gh`` runners used by
all other git submodules, plus the porcelain git operations
(status, log, commit, pull, push).
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

from src.core.services.audit_helpers import make_auditor

_audit = make_auditor("git")


# ═══════════════════════════════════════════════════════════════════
#  GH token management — fallback for systems where gh v2.40+
#  config migration is broken (headless, no dbus-launch, etc).
#  On normal systems _gh_migration_broken stays False and none of
#  this is used — run_gh() behaves exactly as before.
#
#  Token is stored in:
#    - os.environ["GH_TOKEN"] (hot-reloaded, immediate effect)
#    - .env file (persisted, survives server restart)
# ═══════════════════════════════════════════════════════════════════

_gh_migration_broken: bool = False


def gh_migration_is_broken() -> bool:
    """Return True if gh v2.40+ config migration has been detected as broken."""
    return _gh_migration_broken


def set_gh_migration_broken(broken: bool) -> None:
    """Set/clear the migration-broken flag."""
    global _gh_migration_broken
    _gh_migration_broken = broken
    if broken:
        logger.warning("gh config migration is broken on this system — "
                       "using GH_TOKEN fallback for all gh commands")


def get_stored_gh_token() -> str | None:
    """Return GH_TOKEN from os.environ (which includes .env on startup)."""
    import os
    token = os.environ.get("GH_TOKEN", "").strip()
    if token:
        return token
    # Fallback: read .env directly in case os.environ is stale
    return _read_gh_token_from_dotenv()


def _read_gh_token_from_dotenv() -> str | None:
    """Read GH_TOKEN directly from the project .env file."""
    try:
        # Find project root — look for .env relative to this package
        # src/core/services/git/ops.py → 4 levels up → project root
        ops_dir = Path(__file__).resolve().parent
        project_root = ops_dir.parent.parent.parent.parent
        env_file = project_root / ".env"
        if not env_file.exists():
            return None
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("GH_TOKEN="):
                    value = line.partition("=")[2].strip()
                    # Strip surrounding quotes
                    if (
                        len(value) >= 2
                        and value[0] == value[-1]
                        and value[0] in ('"', "'")
                    ):
                        value = value[1:-1]
                    if value:
                        return value
    except Exception:
        pass
    return None


def store_gh_token(token: str, project_root: Path | None = None) -> None:
    """Store token in os.environ AND persist to .env file.

    Args:
        token: The GitHub OAuth token.
        project_root: Project root directory (for .env file).
                      If None, derived from this file's location.
    """
    import os

    # 1. Hot-reload into os.environ — immediate effect
    os.environ["GH_TOKEN"] = token
    logger.info("Set GH_TOKEN in os.environ")

    # 2. Persist to .env file
    if project_root is None:
        ops_dir = Path(__file__).resolve().parent
        project_root = ops_dir.parent.parent.parent.parent

    env_file = project_root / ".env"
    try:
        if env_file.exists():
            # Read existing content, replace or append GH_TOKEN
            lines = env_file.read_text().splitlines()
            found = False
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("GH_TOKEN="):
                    lines[i] = f"GH_TOKEN={token}"
                    found = True
                    break
            if not found:
                # Append under a comment section
                lines.append("")
                lines.append("# ── GitHub Token (auto-managed) ──")
                lines.append(f"GH_TOKEN={token}")
            env_file.write_text("\n".join(lines) + "\n")
        else:
            # Create .env with just the token
            env_file.write_text(
                "# ── GitHub Token (auto-managed) ──\n"
                f"GH_TOKEN={token}\n"
            )
        logger.info("Persisted GH_TOKEN to %s", env_file)
    except Exception as exc:
        logger.warning("Could not persist GH_TOKEN to .env: %s", exc)


# ═══════════════════════════════════════════════════════════════════
#  Low-level runners
# ═══════════════════════════════════════════════════════════════════


def run_git(
    *args: str,
    cwd: Path,
    timeout: int = 15,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a git command and return the result.

    Uses ``git_env()`` from the auth module so that SSH agent
    variables (SSH_AUTH_SOCK, SSH_AGENT_PID) and HTTPS askpass
    scripts reach the subprocess.
    """
    from src.core.services.git.auth import git_env

    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        env=git_env(),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=check,
    )


def run_gh(
    *args: str,
    cwd: Path,
    timeout: int = 30,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a gh CLI command and return the result.

    On systems where ``gh auth status`` fails due to the migration error,
    ``GH_TOKEN`` is injected into the subprocess env so gh commands
    authenticate without needing hosts.yml / keyring.
    On normal systems this is never activated — run_gh() behaves as before.
    """
    # Build env — only inject GH_TOKEN when migration is broken
    env = None
    if _gh_migration_broken:
        token = get_stored_gh_token()
        if token:
            import os
            env = {**os.environ, "GH_TOKEN": token}

    try:
        return subprocess.run(
            ["gh", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            input=stdin,
            env=env,
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(
            args=["gh", *args],
            returncode=127,
            stdout="",
            stderr="gh CLI not found — install it first",
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            args=["gh", *args],
            returncode=124,
            stdout="",
            stderr=f"gh command timed out after {timeout}s",
        )


def repo_slug(project_root: Path) -> str | None:
    """Get the GitHub owner/repo slug from git remote."""
    r = run_git("remote", "get-url", "origin", cwd=project_root)
    if r.returncode != 0:
        return None
    url = r.stdout.strip()
    # Handle SSH: git@github.com:owner/repo.git
    if url.startswith("git@"):
        url = url.split(":", 1)[1]
    # Handle HTTPS: https://github.com/owner/repo.git
    elif "github.com/" in url:
        url = url.split("github.com/", 1)[1]
    else:
        return None
    return url.removesuffix(".git")


# ═══════════════════════════════════════════════════════════════════
#  Git operations
# ═══════════════════════════════════════════════════════════════════


def git_status(project_root: Path) -> dict:
    """Git repository status: branch, dirty files, ahead/behind tracking."""
    root = project_root

    # Current branch
    r_branch = run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=root)
    branch = r_branch.stdout.strip() if r_branch.returncode == 0 else None

    if branch is None:
        from src.core.services.tool_requirements import check_required_tools
        return {
            "error": "Not a git repository",
            "available": False,
            "missing_tools": check_required_tools(["git"]),
        }

    # Commit hash
    r_hash = run_git("rev-parse", "--short", "HEAD", cwd=root)
    commit_hash = r_hash.stdout.strip() if r_hash.returncode == 0 else None

    # Dirty state — porcelain v1 for reliable parsing
    r_status = run_git("status", "--porcelain", cwd=root)
    status_lines = [
        ln for ln in r_status.stdout.strip().splitlines() if ln.strip()
    ] if r_status.returncode == 0 else []

    staged = []
    modified = []
    untracked = []
    for line in status_lines:
        if len(line) < 3:
            continue
        idx = line[0]  # index status
        wt = line[1]   # worktree status
        fname = line[3:]
        if idx in ("A", "M", "D", "R", "C"):
            staged.append(fname)
        if wt == "M":
            modified.append(fname)
        elif wt == "?":
            untracked.append(fname)

    dirty = len(status_lines) > 0

    # Ahead/behind remote tracking branch
    ahead = 0
    behind = 0
    r_ab = run_git(
        "rev-list", "--left-right", "--count", "HEAD...@{u}", cwd=root,
    )
    if r_ab.returncode == 0:
        parts = r_ab.stdout.strip().split()
        if len(parts) == 2:
            ahead = int(parts[0])
            behind = int(parts[1])

    # Last commit info
    r_last = run_git(
        "log", "-1", "--format=%H%n%h%n%s%n%an%n%aI", cwd=root,
    )
    last_commit = None
    if r_last.returncode == 0:
        lines = r_last.stdout.strip().splitlines()
        if len(lines) >= 5:
            last_commit = {
                "hash": lines[0],
                "short_hash": lines[1],
                "message": lines[2],
                "author": lines[3],
                "date": lines[4],
            }

    # Remote URL
    r_remote = run_git("remote", "get-url", "origin", cwd=root)
    remote_url = r_remote.stdout.strip() if r_remote.returncode == 0 else None

    from src.core.services.tool_requirements import check_required_tools

    return {
        "available": True,
        "branch": branch,
        "commit": commit_hash,
        "dirty": dirty,
        "staged_count": len(staged),
        "modified_count": len(modified),
        "untracked_count": len(untracked),
        "total_changes": len(status_lines),
        "staged": staged[:20],         # cap for UI
        "modified": modified[:20],
        "untracked": untracked[:20],
        "ahead": ahead,
        "behind": behind,
        "last_commit": last_commit,
        "remote_url": remote_url,
        "missing_tools": check_required_tools(["git"]),
    }


def git_log(project_root: Path, *, n: int = 10) -> dict:
    """Recent commit history."""
    n = min(n, 50)  # cap

    r = run_git(
        "log", f"-{n}", "--format=%H%n%h%n%s%n%an%n%aI%n---",
        cwd=project_root,
    )
    if r.returncode != 0:
        return {"error": "Failed to read git log", "commits": []}

    commits = []
    entries = r.stdout.strip().split("\n---\n")
    for entry in entries:
        lines = entry.strip().splitlines()
        if len(lines) >= 5:
            commits.append({
                "hash": lines[0],
                "short_hash": lines[1],
                "message": lines[2],
                "author": lines[3],
                "date": lines[4],
            })

    return {"commits": commits}


def git_commit(
    project_root: Path,
    message: str,
    *,
    files: list[str] | None = None,
) -> dict:
    """Stage and commit changes.

    Args:
        project_root: Repository root.
        message: Commit message.
        files: Optional list of files to stage (default: all).

    Returns:
        {"ok": True, "hash": ..., "message": ...} on success,
        {"error": ...} on failure.
    """
    if not message.strip():
        return {"error": "Commit message is required"}

    root = project_root

    # Stage
    if files:
        for f in files:
            run_git("add", f, cwd=root)
    else:
        run_git("add", "-A", cwd=root)

    # Check if there's anything to commit
    r_diff = run_git("diff", "--cached", "--quiet", cwd=root)
    if r_diff.returncode == 0:
        return {"error": "Nothing to commit (no staged changes)"}

    # Commit
    r = run_git("commit", "-m", message, cwd=root, timeout=30)
    if r.returncode != 0:
        return {"error": f"Commit failed: {r.stderr.strip()}"}

    # Get the new commit hash
    r_hash = run_git("rev-parse", "--short", "HEAD", cwd=root)
    new_hash = r_hash.stdout.strip() if r_hash.returncode == 0 else "?"

    return {"ok": True, "hash": new_hash, "message": message}


def git_pull(project_root: Path, *, rebase: bool = False) -> dict:
    """Pull from remote."""
    args = ["pull"]
    if rebase:
        args.append("--rebase")

    r = run_git(*args, cwd=project_root, timeout=60)
    if r.returncode != 0:
        return {"error": f"Pull failed: {r.stderr.strip()}"}

    return {"ok": True, "output": r.stdout.strip()}


def git_push(project_root: Path, *, force: bool = False) -> dict:
    """Push to remote."""
    root = project_root
    args = ["push"]
    if force:
        args.append("--force-with-lease")

    r = run_git(*args, cwd=root, timeout=60)
    if r.returncode != 0:
        stderr = r.stderr.strip()
        # Common case: no upstream configured
        if "no upstream branch" in stderr.lower() or "has no upstream" in stderr.lower():
            # Get current branch and set upstream
            r_branch = run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=root)
            branch = r_branch.stdout.strip()
            r2 = run_git("push", "--set-upstream", "origin", branch, cwd=root, timeout=60)
            if r2.returncode != 0:
                return {"error": f"Push failed: {r2.stderr.strip()}"}
            return {"ok": True, "output": r2.stdout.strip() or r2.stderr.strip()}
        return {"error": f"Push failed: {stderr}"}

    return {"ok": True, "output": r.stdout.strip() or r.stderr.strip()}


# ═══════════════════════════════════════════════════════════════════
#  Diff operations
# ═══════════════════════════════════════════════════════════════════


def git_diff(project_root: Path) -> dict:
    """Per-file diff summary for staged + unstaged + untracked changes.

    Returns::

        {
            "files": [
                {"path": "src/foo.py", "status": "M", "staged": True,
                 "insertions": 12, "deletions": 3},
                ...
            ],
            "total_insertions": ...,
            "total_deletions": ...,
        }
    """
    root = project_root
    files: dict[str, dict] = {}

    # 1) Staged changes — numstat
    r_staged = run_git("diff", "--cached", "--numstat", cwd=root)
    if r_staged.returncode == 0:
        for line in r_staged.stdout.strip().splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            ins, dels, path = parts[0], parts[1], parts[2]
            is_binary = ins == "-" and dels == "-"
            files[path] = {
                "path": path,
                "status": "M",
                "staged": True,
                "insertions": 0 if is_binary else int(ins),
                "deletions": 0 if is_binary else int(dels),
                "is_binary": is_binary,
            }

    # 2) Get staged file statuses (to distinguish A/M/D/R)
    r_staged_status = run_git("diff", "--cached", "--name-status", cwd=root)
    if r_staged_status.returncode == 0:
        for line in r_staged_status.stdout.strip().splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            status_char = parts[0][0]  # First char (R100 → R)
            path = parts[-1]          # Last part (handles renames)
            if path in files:
                files[path]["status"] = status_char

    # 3) Unstaged changes — numstat
    r_unstaged = run_git("diff", "--numstat", cwd=root)
    if r_unstaged.returncode == 0:
        for line in r_unstaged.stdout.strip().splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            ins, dels, path = parts[0], parts[1], parts[2]
            is_binary = ins == "-" and dels == "-"
            if path not in files:
                files[path] = {
                    "path": path,
                    "status": "M",
                    "staged": False,
                    "insertions": 0 if is_binary else int(ins),
                    "deletions": 0 if is_binary else int(dels),
                    "is_binary": is_binary,
                }
            else:
                # File is both staged and has unstaged modifications
                # Mark as staged (the staged version will be committed)
                pass

    # 4) Untracked files
    r_untracked = run_git("ls-files", "--others", "--exclude-standard", cwd=root)
    if r_untracked.returncode == 0:
        for line in r_untracked.stdout.strip().splitlines():
            path = line.strip()
            if not path or path in files:
                continue
            # Count lines for untracked files
            line_count = 0
            try:
                full_path = root / path
                if full_path.is_file() and full_path.stat().st_size < 500_000:
                    line_count = len(full_path.read_text(errors="replace").splitlines())
            except Exception:
                pass
            files[path] = {
                "path": path,
                "status": "?",
                "staged": False,
                "insertions": line_count,
                "deletions": 0,
                "is_binary": False,
            }

    file_list = sorted(files.values(), key=lambda f: (
        {"?": 2, "A": 0, "M": 1, "D": 1, "R": 1}.get(f["status"], 1),
        not f["staged"],
        f["path"],
    ))

    total_ins = sum(f["insertions"] for f in file_list)
    total_dels = sum(f["deletions"] for f in file_list)

    return {
        "files": file_list,
        "total_insertions": total_ins,
        "total_deletions": total_dels,
    }


def git_diff_file(
    project_root: Path, path: str, *, staged: bool = False,
) -> dict:
    """Full diff content for a single file.

    Returns::

        {
            "path": "src/foo.py",
            "diff": "--- a/src/foo.py\\n+++ b/src/foo.py\\n@@ ...",
            "is_binary": False,
            "is_new": False,
        }
    """
    root = project_root
    max_lines = 500

    # Check if it's an untracked file
    r_ls = run_git("ls-files", "--others", "--exclude-standard", "--", path, cwd=root)
    is_untracked = (
        r_ls.returncode == 0
        and path in r_ls.stdout.strip().splitlines()
    )

    if is_untracked:
        full_path = root / path
        if not full_path.is_file():
            return {"path": path, "diff": "", "is_binary": False, "is_new": True}
        try:
            content = full_path.read_text(errors="replace")
        except Exception:
            return {"path": path, "diff": "(cannot read file)", "is_binary": True, "is_new": True}

        lines = content.splitlines()
        truncated = len(lines) > max_lines
        if truncated:
            lines = lines[:max_lines]

        diff_lines = [f"--- /dev/null", f"+++ b/{path}", f"@@ -0,0 +1,{len(lines)} @@"]
        diff_lines.extend(f"+{ln}" for ln in lines)
        if truncated:
            diff_lines.append(f"\\ ... truncated ({len(content.splitlines())} total lines)")

        return {"path": path, "diff": "\n".join(diff_lines), "is_binary": False, "is_new": True}

    # Staged or unstaged diff
    args = ["diff"]
    if staged:
        args.append("--cached")
    args.extend(["--", path])

    r = run_git(*args, cwd=root, timeout=15)
    if r.returncode != 0:
        return {"path": path, "diff": "", "is_binary": False, "is_new": False}

    diff_text = r.stdout
    is_binary = "Binary files" in diff_text[:200]

    if not is_binary:
        lines = diff_text.splitlines()
        if len(lines) > max_lines:
            diff_text = "\n".join(lines[:max_lines])
            diff_text += f"\n\\ ... truncated ({len(lines)} total lines)"

    return {
        "path": path,
        "diff": diff_text,
        "is_binary": is_binary,
        "is_new": "new file mode" in diff_text[:200],
    }


# ═══════════════════════════════════════════════════════════════════
#  Stash operations
# ═══════════════════════════════════════════════════════════════════


def git_stash(project_root: Path, message: str | None = None) -> dict:
    """Stash working directory changes.

    Returns::

        {"ok": True, "ref": "stash@{0}", "message": "..."}
        or {"error": "Nothing to stash"} if worktree is clean.
    """
    root = project_root
    args = ["stash", "push"]
    if message:
        args.extend(["-m", message])

    r = run_git(*args, cwd=root, timeout=15)
    if r.returncode != 0:
        return {"error": f"Stash failed: {r.stderr.strip()}"}

    output = r.stdout.strip()
    if "No local changes" in output:
        return {"error": "Nothing to stash"}

    return {"ok": True, "ref": "stash@{0}", "message": message or output}


def git_stash_pop(project_root: Path) -> dict:
    """Pop the most recent stash.

    Returns::

        {"ok": True}
        or {"error": "...", "conflicts": True} if pop causes conflicts.
    """
    root = project_root
    r = run_git("stash", "pop", cwd=root, timeout=15)

    if r.returncode != 0:
        stderr = r.stderr.strip()
        has_conflicts = "conflict" in stderr.lower() or "CONFLICT" in stderr
        return {"error": f"Stash pop failed: {stderr}", "conflicts": has_conflicts}

    return {"ok": True}


def git_stash_list(project_root: Path) -> dict:
    """List stash entries.

    Returns::

        {"stashes": [{"ref": "stash@{0}", "message": "...", "date": "..."}]}
    """
    root = project_root
    r = run_git(
        "stash", "list", "--format=%gd%x00%gs%x00%ar", cwd=root,
    )
    if r.returncode != 0:
        return {"stashes": []}

    stashes = []
    for line in r.stdout.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("\x00")
        if len(parts) < 3:
            continue
        stashes.append({
            "ref": parts[0],
            "message": parts[1],
            "date": parts[2],
        })

    return {"stashes": stashes}


# ═══════════════════════════════════════════════════════════════════
#  Merge / conflict operations
# ═══════════════════════════════════════════════════════════════════


def git_merge_status(project_root: Path) -> dict:
    """Detect ongoing merge/rebase and list conflicted files.

    Returns::

        {
            "in_progress": True/False,
            "type": "merge" | "rebase" | None,
            "conflicted_files": ["src/foo.py", ...],
        }
    """
    root = project_root

    # Detect merge or rebase in progress
    git_dir = root / ".git"
    merge_head = git_dir / "MERGE_HEAD"
    rebase_merge = git_dir / "rebase-merge"
    rebase_apply = git_dir / "rebase-apply"

    in_progress = False
    merge_type = None

    if merge_head.exists():
        in_progress = True
        merge_type = "merge"
    elif rebase_merge.exists() or rebase_apply.exists():
        in_progress = True
        merge_type = "rebase"

    # List conflicted files (unmerged)
    conflicted: list[str] = []
    r = run_git("diff", "--name-only", "--diff-filter=U", cwd=root)
    if r.returncode == 0:
        conflicted = [
            ln.strip() for ln in r.stdout.strip().splitlines() if ln.strip()
        ]

    return {
        "in_progress": in_progress,
        "type": merge_type,
        "conflicted_files": conflicted,
    }


def git_merge_abort(project_root: Path) -> dict:
    """Abort a merge or rebase in progress.

    Returns ``{"ok": True}`` or ``{"error": "..."}``.
    """
    root = project_root
    status = git_merge_status(root)

    if not status["in_progress"]:
        return {"error": "No merge or rebase in progress"}

    if status["type"] == "rebase":
        r = run_git("rebase", "--abort", cwd=root, timeout=15)
    else:
        r = run_git("merge", "--abort", cwd=root, timeout=15)

    if r.returncode != 0:
        return {"error": f"Abort failed: {r.stderr.strip()}"}

    return {"ok": True}


def git_checkout_file(
    project_root: Path, path: str, strategy: str,
) -> dict:
    """Resolve a single conflicted file.

    Args:
        path: File path relative to project root.
        strategy: ``"ours"`` or ``"theirs"``.

    Returns ``{"ok": True}`` or ``{"error": "..."}``.
    """
    if strategy not in ("ours", "theirs"):
        return {"error": f"Invalid strategy: {strategy!r} (must be ours|theirs)"}

    root = project_root
    r = run_git("checkout", f"--{strategy}", "--", path, cwd=root)
    if r.returncode != 0:
        return {"error": f"Checkout failed: {r.stderr.strip()}"}

    # Stage the resolved file
    r_add = run_git("add", "--", path, cwd=root)
    if r_add.returncode != 0:
        return {"error": f"Stage failed: {r_add.stderr.strip()}"}

    return {"ok": True}
