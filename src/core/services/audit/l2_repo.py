"""
L2 — Repository health analysis (on-demand).

Aggregates git status, history depth, object weight, large file
detection, and branch hygiene from existing git_ops.

Public API:
    l2_repo(project_root)  → repo health report
"""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

from src.core.services.audit.models import wrap_result

logger = logging.getLogger(__name__)

# Files above this threshold are flagged
_LARGE_FILE_BYTES = 1_000_000   # 1 MB
_BINARY_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico",
    ".mp4", ".webm", ".mov", ".avi", ".mkv",
    ".mp3", ".wav", ".ogg", ".flac",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".pyc", ".pyo", ".class",
    ".db", ".sqlite", ".sqlite3",
})

_SKIP_DIRS = frozenset({
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".mypy_cache", ".ruff_cache", ".pytest_cache", ".tox",
    "dist", "build", ".eggs", ".terraform", ".pages",
    "htmlcov", ".backup", "state",
})


# ═══════════════════════════════════════════════════════════════════
#  Git helpers (lightweight — no dependency on git_ops)
# ═══════════════════════════════════════════════════════════════════


def _run_git(
    *args: str,
    cwd: Path,
    timeout: int = 10,
) -> subprocess.CompletedProcess:
    """Run a git command and return the result. Never raises."""
    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return subprocess.CompletedProcess(
            args=["git", *args], returncode=1,
            stdout="", stderr=str(e),
        )


# ═══════════════════════════════════════════════════════════════════
#  Git object weight
# ═══════════════════════════════════════════════════════════════════


def _git_object_weight(project_root: Path) -> dict:
    """Compute git object database size and pack info.

    Returns:
        {
            "count": int,         # loose objects
            "size_kb": int,       # loose object size
            "packs": int,         # number of packs
            "pack_size_kb": int,  # total pack size
            "total_kb": int,      # combined
        }
    """
    r = _run_git("count-objects", "-v", cwd=project_root)
    if r.returncode != 0:
        return {"error": r.stderr.strip()}

    data = {}
    for line in r.stdout.strip().splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            data[key.strip()] = val.strip()

    count = int(data.get("count", 0))
    size = int(data.get("size", 0))
    packs = int(data.get("in-pack", 0))
    pack_size = int(data.get("size-pack", 0))

    return {
        "count": count,
        "size_kb": size,
        "packs": packs,
        "pack_size_kb": pack_size,
        "total_kb": size + pack_size,
    }


# ═══════════════════════════════════════════════════════════════════
#  History analysis
# ═══════════════════════════════════════════════════════════════════


def _git_history(project_root: Path) -> dict:
    """Analyze git history: commit count, author count, age.

    Returns:
        {
            "total_commits": int,
            "authors": int,
            "first_commit_date": str | None,
            "latest_commit_date": str | None,
            "age_days": int,
            "branch_count": int,
            "tag_count": int,
        }
    """
    # Total commit count
    r_count = _run_git("rev-list", "--count", "HEAD", cwd=project_root)
    total = int(r_count.stdout.strip()) if r_count.returncode == 0 else 0

    # Author count
    r_authors = _run_git(
        "shortlog", "-sn", "--all", "--no-merges",
        cwd=project_root, timeout=15,
    )
    authors = 0
    if r_authors.returncode == 0:
        authors = len([l for l in r_authors.stdout.strip().splitlines() if l.strip()])

    # First commit date
    r_first = _run_git("log", "--reverse", "--format=%aI", "-1", cwd=project_root)
    first_date = r_first.stdout.strip() if r_first.returncode == 0 else None

    # Latest commit date
    r_latest = _run_git("log", "--format=%aI", "-1", cwd=project_root)
    latest_date = r_latest.stdout.strip() if r_latest.returncode == 0 else None

    # Age in days
    age_days = 0
    if first_date and latest_date:
        try:
            from datetime import datetime, timezone
            first = datetime.fromisoformat(first_date)
            now = datetime.now(timezone.utc)
            age_days = max(0, (now - first).days)
        except (ValueError, TypeError):
            pass

    # Branch count
    r_branches = _run_git("branch", "--list", cwd=project_root)
    branches = 0
    if r_branches.returncode == 0:
        branches = len([l for l in r_branches.stdout.strip().splitlines() if l.strip()])

    # Tag count
    r_tags = _run_git("tag", "--list", cwd=project_root)
    tags = 0
    if r_tags.returncode == 0:
        tags = len([l for l in r_tags.stdout.strip().splitlines() if l.strip()])

    return {
        "total_commits": total,
        "authors": authors,
        "first_commit_date": first_date or None,
        "latest_commit_date": latest_date or None,
        "age_days": age_days,
        "branch_count": branches,
        "tag_count": tags,
    }


# ═══════════════════════════════════════════════════════════════════
#  Large file detection
# ═══════════════════════════════════════════════════════════════════


def _detect_large_files(project_root: Path) -> dict:
    """Find large checked-in files and binary blobs.

    Returns:
        {
            "large_files": [{path, size_kb, is_binary}, ...],
            "binary_files": [{path, size_kb, ext}, ...],
            "total_large": int,
            "total_binary": int,
            "suggestions": [str, ...],
        }
    """
    large = []
    binaries = []

    for f in sorted(project_root.rglob("*")):
        # Skip excluded dirs
        parts = f.relative_to(project_root).parts
        if any(d in _SKIP_DIRS for d in parts):
            continue
        if not f.is_file():
            continue

        try:
            size = f.stat().st_size
        except OSError:
            continue

        ext = f.suffix.lower()
        rel = str(f.relative_to(project_root))
        is_binary = ext in _BINARY_EXTENSIONS

        if is_binary:
            binaries.append({
                "path": rel,
                "size_kb": round(size / 1024, 1),
                "ext": ext,
            })

        if size > _LARGE_FILE_BYTES:
            large.append({
                "path": rel,
                "size_kb": round(size / 1024, 1),
                "is_binary": is_binary,
            })

    # Sort by size descending
    large.sort(key=lambda x: x["size_kb"], reverse=True)
    binaries.sort(key=lambda x: x["size_kb"], reverse=True)

    # Generate suggestions
    suggestions = []
    if large:
        total_mb = sum(f["size_kb"] for f in large) / 1024
        suggestions.append(
            f"{len(large)} files over 1MB ({total_mb:.1f}MB total)"
        )
        binary_large = [f for f in large if f["is_binary"]]
        if binary_large:
            suggestions.append(
                f"Consider Git LFS for {len(binary_large)} large binary files"
            )
    if binaries:
        suggestions.append(
            f"{len(binaries)} binary files tracked — ensure they belong in the repo"
        )

    return {
        "large_files": large[:30],       # Cap for UI
        "binary_files": binaries[:30],
        "total_large": len(large),
        "total_binary": len(binaries),
        "suggestions": suggestions,
    }


# ═══════════════════════════════════════════════════════════════════
#  Repo health score
# ═══════════════════════════════════════════════════════════════════


def _repo_health_score(
    objects: dict,
    history: dict,
    large_files: dict,
) -> dict:
    """Compute a repo health score (0-10).

    Dimensions:
        1. Object DB size     (30%) — smaller is healthier
        2. Binary hygiene     (25%) — fewer tracked binaries
        3. History depth      (15%) — reasonable commit count
        4. Branch hygiene     (15%) — not too many stale branches
        5. Tag usage          (15%) — tags indicate good release practice
    """
    # 1. Object DB size
    total_kb = objects.get("total_kb", 0)
    if total_kb < 5_000:       # < 5MB
        obj_score = 10.0
    elif total_kb < 50_000:    # < 50MB
        obj_score = 10.0 - (total_kb - 5_000) / 5_000
    elif total_kb < 200_000:   # < 200MB
        obj_score = max(2.0, 1.0)
    else:
        obj_score = 1.0

    # 2. Binary hygiene
    total_binary = large_files.get("total_binary", 0)
    if total_binary == 0:
        bin_score = 10.0
    elif total_binary <= 5:
        bin_score = 8.0
    elif total_binary <= 20:
        bin_score = 6.0 - (total_binary - 5) * 0.2
    else:
        bin_score = max(2.0, 2.0)

    # 3. History depth — having history is good
    commits = history.get("total_commits", 0)
    if commits == 0:
        hist_score = 5.0
    elif commits < 10:
        hist_score = 6.0
    elif commits < 100:
        hist_score = 8.0
    elif commits < 1000:
        hist_score = 10.0
    else:
        hist_score = 9.0  # Lots of history is fine

    # 4. Branch hygiene
    branches = history.get("branch_count", 1)
    if branches <= 5:
        branch_score = 10.0
    elif branches <= 15:
        branch_score = 8.0
    elif branches <= 30:
        branch_score = 6.0
    else:
        branch_score = max(3.0, 5.0 - (branches - 30) * 0.1)

    # 5. Tag usage
    tags = history.get("tag_count", 0)
    if tags == 0:
        tag_score = 5.0  # No tags = neutral
    elif tags < 5:
        tag_score = 7.0
    else:
        tag_score = 10.0

    weights = {
        "object_size": 0.30,
        "binary_hygiene": 0.25,
        "history_depth": 0.15,
        "branch_hygiene": 0.15,
        "tag_usage": 0.15,
    }
    scores = {
        "object_size": round(obj_score, 1),
        "binary_hygiene": round(bin_score, 1),
        "history_depth": round(hist_score, 1),
        "branch_hygiene": round(branch_score, 1),
        "tag_usage": round(tag_score, 1),
    }
    overall = sum(scores[k] * weights[k] for k in weights)

    return {
        "score": round(overall, 1),
        "breakdown": scores,
    }


# ═══════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════


def l2_repo(project_root: Path) -> dict:
    """L2: Repository health analysis.

    On-demand — typically takes 1-3s depending on repo size.

    Returns:
        {
            "_meta": AuditMeta,
            "git_objects": {count, size_kb, packs, pack_size_kb, total_kb},
            "history": {total_commits, authors, age_days, branch_count, tag_count},
            "large_files": {large_files, binary_files, total_large, total_binary, suggestions},
            "health": {score, breakdown},
        }
    """
    started = time.time()

    objects = _git_object_weight(project_root)
    history = _git_history(project_root)
    large = _detect_large_files(project_root)
    health = _repo_health_score(objects, history, large)

    data = {
        "git_objects": objects,
        "history": history,
        "large_files": large,
        "health": health,
    }
    return wrap_result(data, "L2", "repo", started)
