"""
Changelog engine — load, save, and manipulate CHANGELOG.md.

Operates on the Keep a Changelog format:
    https://keepachangelog.com/en/1.1.0/

All functions are channel-independent (no Flask, no HTTP).
"""

from __future__ import annotations

import logging
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from src.core.services.changelog.models import (
    Changelog,
    ChangelogEntry,
    ChangelogSection,
)
from src.core.services.changelog.parser import (
    SECTION_ORDER,
    cc_section,
    normalize_type,
    parse_cc_message,
)

logger = logging.getLogger(__name__)

_CHANGELOG_FILE = "CHANGELOG.md"

# ── Standard header for new changelogs ──────────────────────────

_DEFAULT_HEADER = """\
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
"""

# ── Regex patterns for parsing ──────────────────────────────────

# ## [Unreleased]
# ## [0.2.0] - 2026-03-03
_VERSION_HEADING_RE = re.compile(
    r"^##\s+\[(?P<version>[^\]]+)\]"
    r"(?:\s*-\s*(?P<date>\d{4}-\d{2}-\d{2}))?\s*$",
)

# ### ✨ Features
# ### 🐛 Bug Fixes
_SECTION_HEADING_RE = re.compile(
    r"^###\s+(?P<emoji>\S+)\s+(?P<title>.+)$",
)

# - entry text
# - entry text ⚠️ **BREAKING**
_ENTRY_RE = re.compile(
    r"^-\s+(?P<text>.+)$",
)

# Reverse lookup: (emoji, title) → canonical type key
_SECTION_REVERSE: dict[str, str] = {}
for _key in SECTION_ORDER:
    _emoji, _title = cc_section(_key)
    _section_label = f"{_emoji} {_title}"
    _SECTION_REVERSE[_section_label] = _key
    # Also map just the title (for flexibility)
    _SECTION_REVERSE[_title] = _key
# Handle "Other Changes" fallback
_SECTION_REVERSE["📋 Other Changes"] = "other"
_SECTION_REVERSE["Other Changes"] = "other"


# ═══════════════════════════════════════════════════════════════════
#  Load / Parse
# ═══════════════════════════════════════════════════════════════════


def load_changelog(project_root: Path) -> Changelog:
    """Parse CHANGELOG.md into a structured ``Changelog`` object.

    If the file doesn't exist, returns an empty Changelog with the
    standard header and an empty ``[Unreleased]`` section.

    Args:
        project_root: Project root directory.

    Returns:
        A ``Changelog`` object with header, unreleased, and releases.
    """
    path = project_root / _CHANGELOG_FILE
    if not path.is_file():
        return Changelog(header=_DEFAULT_HEADER)

    content = path.read_text(encoding="utf-8")
    return _parse_changelog(content)


def _parse_changelog(content: str) -> Changelog:
    """Parse raw CHANGELOG.md content into structured form."""
    lines = content.splitlines()
    header_lines: list[str] = []
    sections: list[ChangelogSection] = []
    current_section: ChangelogSection | None = None
    current_section_key: str = ""

    for line in lines:
        # ── Version heading? ────────────────────────────────────
        vm = _VERSION_HEADING_RE.match(line)
        if vm:
            if current_section is not None:
                sections.append(current_section)
            current_section = ChangelogSection(
                version=vm.group("version"),
                date=vm.group("date") or "",
            )
            current_section_key = ""
            continue

        # ── Section heading? (### emoji Title) ──────────────────
        sm = _SECTION_HEADING_RE.match(line)
        if sm and current_section is not None:
            label = f"{sm.group('emoji')} {sm.group('title')}"
            current_section_key = _SECTION_REVERSE.get(
                label,
                _SECTION_REVERSE.get(sm.group("title"), "other"),
            )
            if current_section_key not in current_section.entries:
                current_section.entries[current_section_key] = []
            continue

        # ── Entry? (- text) ─────────────────────────────────────
        em = _ENTRY_RE.match(line)
        if em and current_section is not None and current_section_key:
            text = em.group("text")
            breaking = "⚠️" in text or "**BREAKING**" in text

            # Extract scope from text if present (e.g. "**scope:** text")
            scope = ""
            scope_match = re.match(r"\*\*([^*]+)\*\*:\s*(.*)", text)
            if scope_match:
                scope = scope_match.group(1)

            entry = ChangelogEntry(
                text=text,
                breaking=breaking,
                scope=scope,
                section_key=current_section_key,
            )
            current_section.entries.setdefault(current_section_key, []).append(entry)
            continue

        # ── Header (before first ## []) ─────────────────────────
        if current_section is None:
            header_lines.append(line)
        # Other lines (blank lines, notes) are silently absorbed

    # Don't forget the last section
    if current_section is not None:
        sections.append(current_section)

    # Separate unreleased from releases
    header = "\n".join(header_lines).rstrip() + "\n"
    unreleased = ChangelogSection(version="Unreleased")
    releases: list[ChangelogSection] = []

    for sec in sections:
        if sec.is_unreleased:
            unreleased = sec
        else:
            releases.append(sec)

    # Ensure header exists
    if not header.strip():
        header = _DEFAULT_HEADER

    return Changelog(
        header=header,
        unreleased=unreleased,
        releases=releases,
    )


# ═══════════════════════════════════════════════════════════════════
#  Save / Render
# ═══════════════════════════════════════════════════════════════════


def save_changelog(project_root: Path, changelog: Changelog) -> None:
    """Write a ``Changelog`` object back to CHANGELOG.md.

    Args:
        project_root: Project root directory.
        changelog: The changelog to write.
    """
    path = project_root / _CHANGELOG_FILE
    content = _render_changelog(changelog)
    path.write_text(content, encoding="utf-8")
    logger.info("Saved %s (%d bytes)", path.name, len(content))


def _render_changelog(changelog: Changelog) -> str:
    """Render a Changelog object to markdown."""
    lines: list[str] = []

    # Header
    lines.append(changelog.header.rstrip())
    lines.append("")

    # Render all sections (Unreleased first, then releases)
    for section in changelog.all_sections:
        lines.extend(_render_section(section))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _render_section(section: ChangelogSection) -> list[str]:
    """Render a single version section."""
    lines: list[str] = []

    # Version heading
    if section.is_unreleased:
        lines.append("## [Unreleased]")
    else:
        if section.date:
            lines.append(f"## [{section.version}] - {section.date}")
        else:
            lines.append(f"## [{section.version}]")

    lines.append("")

    if section.is_empty:
        return lines

    # Render subsections in canonical order
    rendered_keys: set[str] = set()
    for key in SECTION_ORDER:
        entries = section.entries.get(key)
        if not entries:
            continue
        rendered_keys.add(key)

        emoji, title = cc_section(key)
        lines.append(f"### {emoji} {title}")
        for entry in entries:
            lines.append(f"- {entry.text}")
        lines.append("")

    # Render any remaining keys not in SECTION_ORDER (e.g. "other")
    for key, entries in section.entries.items():
        if key in rendered_keys or not entries:
            continue
        emoji, title = cc_section(key)
        lines.append(f"### {emoji} {title}")
        for entry in entries:
            lines.append(f"- {entry.text}")
        lines.append("")

    return lines


# ═══════════════════════════════════════════════════════════════════
#  Entry manipulation
# ═══════════════════════════════════════════════════════════════════


def format_entry_text(
    description: str,
    *,
    scope: str = "",
    breaking: bool = False,
) -> str:
    """Format a changelog entry line (without the leading ``- ``).

    Args:
        description: The change description.
        scope: Optional scope to prefix.
        breaking: Whether to append the breaking change marker.

    Returns:
        Formatted entry text.

    Examples::

        >>> format_entry_text("add multi-cluster", scope="k8s", breaking=True)
        '**k8s:** add multi-cluster ⚠️ **BREAKING**'
        >>> format_entry_text("fix overflow")
        'fix overflow'
    """
    text = description
    if scope:
        text = f"**{scope}:** {text}"
    if breaking:
        text += " ⚠️ **BREAKING**"
    return text


def add_entry(
    changelog: Changelog,
    message: str,
    *,
    custom_text: str = "",
) -> str:
    """Add a Conventional Commit to the ``[Unreleased]`` section.

    Parses the CC message, formats a changelog entry, and inserts it
    into the correct subsection of ``[Unreleased]``.

    Args:
        changelog: The changelog to modify (mutated in place).
        message: The full CC commit message string.
        custom_text: If provided, overrides the auto-generated entry text.
            The user can customize what appears in the changelog.

    Returns:
        The formatted entry text that was added.
    """
    parsed = parse_cc_message(message)
    section_key = parsed.type if parsed.type != "other" else "chore"

    if custom_text:
        text = custom_text
        breaking = parsed.breaking
    else:
        text = format_entry_text(
            parsed.description,
            scope=parsed.scope,
            breaking=parsed.breaking,
        )
        breaking = parsed.breaking

    entry = ChangelogEntry(
        text=text,
        breaking=breaking,
        scope=parsed.scope,
        section_key=section_key,
    )

    changelog.unreleased.entries.setdefault(section_key, []).append(entry)
    return text


def remove_entry(changelog: Changelog, entry_text: str) -> bool:
    """Remove an entry from ``[Unreleased]`` by its text.

    Args:
        changelog: The changelog to modify (mutated in place).
        entry_text: The exact entry text to remove.

    Returns:
        True if an entry was found and removed, False otherwise.
    """
    for key, entries in changelog.unreleased.entries.items():
        for i, entry in enumerate(entries):
            if entry.text == entry_text:
                entries.pop(i)
                # Clean up empty section key
                if not entries:
                    del changelog.unreleased.entries[key]
                return True
    return False


def edit_entry(
    changelog: Changelog,
    old_text: str,
    new_text: str,
) -> bool:
    """Replace an entry's text in ``[Unreleased]``.

    Args:
        changelog: The changelog to modify (mutated in place).
        old_text: The current entry text to find.
        new_text: The replacement text.

    Returns:
        True if an entry was found and updated, False otherwise.
    """
    for entries in changelog.unreleased.entries.values():
        for entry in entries:
            if entry.text == old_text:
                entry.text = new_text
                # Update breaking flag based on new text
                entry.breaking = "⚠️" in new_text or "**BREAKING**" in new_text
                return True
    return False


# ═══════════════════════════════════════════════════════════════════
#  Release cutting
# ═══════════════════════════════════════════════════════════════════


def cut_release(
    changelog: Changelog,
    version: str,
    *,
    date: str = "",
) -> ChangelogSection:
    """Move ``[Unreleased]`` entries to a new versioned section.

    Creates a new ``[x.y.z] - date`` section with all entries from
    ``[Unreleased]``, then resets ``[Unreleased]`` to empty.

    Args:
        changelog: The changelog to modify (mutated in place).
        version: The version string (e.g. ``"0.2.0"``).
        date: Release date as ``YYYY-MM-DD``.
            Defaults to today (UTC).

    Returns:
        The newly created release section.
    """
    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Create release section from current unreleased
    release = ChangelogSection(
        version=version,
        date=date,
        entries=dict(changelog.unreleased.entries),  # shallow copy
    )

    # Insert at the top of releases (newest first)
    changelog.releases.insert(0, release)

    # Reset unreleased
    changelog.unreleased = ChangelogSection(version="Unreleased")

    logger.info(
        "Cut release %s (%s) — %d entries",
        version, date, release.entry_count,
    )
    return release


# ═══════════════════════════════════════════════════════════════════
#  Bootstrap — generate initial CHANGELOG.md from git history
# ═══════════════════════════════════════════════════════════════════


def bootstrap_changelog(
    project_root: Path,
    *,
    since_tag: str | None = None,
    max_commits: int = 200,
) -> Changelog:
    """Generate an initial ``Changelog`` from git history.

    Scans git log, parses each commit message as CC, and builds
    a complete Changelog structure.  If a ``since_tag`` is provided,
    only commits after that tag are included.  Otherwise, includes
    up to ``max_commits`` from the entire history.

    Args:
        project_root: Project root directory.
        since_tag: Only include commits after this tag.
        max_commits: Maximum number of commits to scan.

    Returns:
        A ``Changelog`` object ready to be saved.
    """
    # ── Get commits from git log ────────────────────────────────
    cmd = [
        "git", "log",
        f"--max-count={max_commits}",
        "--no-merges",
        "--pretty=format:%s",
    ]

    if since_tag:
        cmd.append(f"{since_tag}..HEAD")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.warning("Git unavailable for changelog bootstrap")
        return Changelog(header=_DEFAULT_HEADER)

    if result.returncode != 0:
        logger.warning("Git log failed: %s", result.stderr.strip())
        return Changelog(header=_DEFAULT_HEADER)

    commit_messages = [
        line.strip()
        for line in result.stdout.strip().splitlines()
        if line.strip()
    ]

    if not commit_messages:
        return Changelog(header=_DEFAULT_HEADER)

    # ── Build changelog from commits ────────────────────────────
    changelog = Changelog(header=_DEFAULT_HEADER)

    for msg in commit_messages:
        add_entry(changelog, msg)

    logger.info(
        "Bootstrap changelog: %d commits → %d entries",
        len(commit_messages),
        changelog.unreleased.entry_count,
    )
    return changelog
