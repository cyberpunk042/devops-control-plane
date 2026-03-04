"""
Release notes generation from git log.

Groups commits by conventional commit prefix:
  feat: → ✨ Features
  fix:  → 🐛 Bug Fixes
  docs: → 📚 Documentation
  other → 🔧 Other Changes
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# Conventional commit prefix → (emoji, section title)
_COMMIT_GROUPS: dict[str, tuple[str, str]] = {
    "feat": ("✨", "Features"),
    "feature": ("✨", "Features"),
    "fix": ("🐛", "Bug Fixes"),
    "bugfix": ("🐛", "Bug Fixes"),
    "docs": ("📚", "Documentation"),
    "doc": ("📚", "Documentation"),
    "refactor": ("♻️", "Refactoring"),
    "perf": ("⚡", "Performance"),
    "test": ("🧪", "Tests"),
    "ci": ("🔄", "CI/CD"),
    "build": ("📦", "Build"),
    "chore": ("🔧", "Chores"),
    "style": ("🎨", "Style"),
}


def generate_release_notes(
    project_root: Path,
    version: str,
    since_tag: str | None = None,
) -> str:
    """Generate release notes from git log.

    Args:
        project_root: Project root.
        version: Version string for the heading.
        since_tag: Generate notes since this tag.
            If None, auto-detects the last tag.

    Returns:
        Markdown-formatted release notes.
    """
    # Find the range
    if since_tag is None:
        since_tag = _find_last_tag(project_root)

    if since_tag:
        log_range = f"{since_tag}..HEAD"
    else:
        log_range = "HEAD~50..HEAD"  # Last 50 commits if no tags

    # Get commits
    commits = _get_commits(project_root, log_range)

    # If no commits since last tag (HEAD is at the tag), try previous tag
    if not commits and since_tag:
        prev_tag = _find_previous_tag(project_root, since_tag)
        if prev_tag:
            commits = _get_commits(project_root, f"{prev_tag}..{since_tag}")
        else:
            # Only one tag — show all commits up to that tag
            commits = _get_commits(project_root, f"{since_tag}~50..{since_tag}")


    if not commits:
        return f"## v{version}\n\nNo changes recorded.\n"

    # Group by prefix
    groups: dict[str, list[str]] = {}
    other: list[str] = []

    for msg in commits:
        matched = False
        for prefix, (emoji, title) in _COMMIT_GROUPS.items():
            # Match "prefix: message" or "prefix(scope): message"
            pattern = rf"^{prefix}(\([^)]*\))?:\s*(.+)"
            m = re.match(pattern, msg, re.IGNORECASE)
            if m:
                clean_msg = m.group(2).strip()
                key = f"{emoji} {title}"
                groups.setdefault(key, []).append(clean_msg)
                matched = True
                break
        if not matched:
            other.append(msg)

    # Build markdown
    lines = [f"## v{version}", ""]

    for section_title, messages in groups.items():
        lines.append(f"### {section_title}")
        for msg in messages:
            lines.append(f"- {msg}")
        lines.append("")

    if other:
        lines.append("### 🔧 Other Changes")
        for msg in other:
            lines.append(f"- {msg}")
        lines.append("")

    # Add stats
    total = len(commits)
    if since_tag:
        lines.append(f"*{total} commit{'s' if total != 1 else ''} since {since_tag}*")
    else:
        lines.append(f"*{total} commit{'s' if total != 1 else ''}*")

    return "\n".join(lines)


def _find_last_tag(project_root: Path) -> str | None:
    """Find the most recent git tag."""
    try:
        r = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=str(project_root),
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _find_previous_tag(project_root: Path, current_tag: str) -> str | None:
    """Find the tag before a given tag."""
    try:
        r = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0", f"{current_tag}^"],
            cwd=str(project_root),
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            prev = r.stdout.strip()
            if prev != current_tag:
                return prev
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _get_commits(project_root: Path, log_range: str) -> list[str]:
    """Get commit messages for a range."""
    try:
        r = subprocess.run(
            ["git", "log", log_range, "--oneline", "--no-merges",
             "--pretty=format:%s"],
            cwd=str(project_root),
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            return [line.strip() for line in r.stdout.strip().splitlines()
                    if line.strip()]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return []
