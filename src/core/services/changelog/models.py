"""
Data models for the changelog & versioning system.

Structured representations of:
    - Conventional Commit messages (parsed)
    - Individual changelog entries
    - Grouped changelog sections (per-version)
    - The full CHANGELOG.md document
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════════
#  Conventional Commit message (parsed)
# ═══════════════════════════════════════════════════════════════════


@dataclass
class CCMessage:
    """A parsed Conventional Commit message.

    Handles the full spec::

        <type>[optional scope][optional !]: <description>

        [optional body]

        [optional footer(s)]
        BREAKING CHANGE: <note>

    Attributes:
        type: The commit type (feat, fix, docs, …).
        scope: Optional scope in parentheses (e.g. "k8s", "ui").
        description: The short description after the colon.
        body: Optional multi-line body (paragraph after blank line).
        breaking: Whether this is a breaking change (``!`` or footer).
        breaking_note: The breaking change description (from ``!`` note
            or ``BREAKING CHANGE:`` footer).  Empty string if not breaking.
        footers: All parsed footers as a dict (key → value).
        raw: The original unparsed message string.
    """

    type: str
    scope: str
    description: str
    body: str = ""
    breaking: bool = False
    breaking_note: str = ""
    footers: dict[str, str] = field(default_factory=dict)
    raw: str = ""

    @property
    def header(self) -> str:
        """Reconstruct the CC header line.

        Examples::

            feat(k8s)!: add multi-cluster support
            fix: correct mobile overflow
        """
        h = self.type
        if self.scope:
            h += f"({self.scope})"
        if self.breaking:
            h += "!"
        h += f": {self.description}"
        return h

    @property
    def full_message(self) -> str:
        """Reconstruct the full commit message (header + body + footers).

        Suitable for passing to ``git commit -m``.
        """
        parts = [self.header]

        if self.body:
            parts.append("")  # blank line separator
            parts.append(self.body)

        # Reconstruct footers
        footer_lines: list[str] = []
        for key, value in self.footers.items():
            # BREAKING CHANGE is already indicated by the ! — but we
            # include the footer if there's an explicit note
            footer_lines.append(f"{key}: {value}")

        if footer_lines:
            parts.append("")  # blank line separator
            parts.extend(footer_lines)

        return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════
#  Changelog entries and sections
# ═══════════════════════════════════════════════════════════════════


@dataclass
class ChangelogEntry:
    """A single line item in a changelog section.

    Attributes:
        text: The entry text (without the leading ``- ``).
        breaking: Whether this entry is a breaking change.
        scope: Optional scope (preserved for display).
        section_key: The CC type this belongs to (e.g. "feat", "fix").
            Used to determine which subsection heading it goes under.
    """

    text: str
    breaking: bool = False
    scope: str = ""
    section_key: str = ""


@dataclass
class ChangelogSection:
    """A version section in the changelog.

    For ``[Unreleased]``, version is ``"Unreleased"`` and date is ``""``.
    For released versions: version is ``"0.2.0"`` and date is ``"2026-03-03"``.

    Attributes:
        version: Version string or ``"Unreleased"``.
        date: Release date as ``YYYY-MM-DD`` string, or empty string.
        entries: Dict mapping section_key → list of entries.
            Keys are CC types: "feat", "fix", "docs", etc.
            The order of keys determines rendering order.
    """

    version: str
    date: str = ""
    entries: dict[str, list[ChangelogEntry]] = field(default_factory=dict)

    @property
    def is_unreleased(self) -> bool:
        return self.version.lower() == "unreleased"

    @property
    def is_empty(self) -> bool:
        return not any(self.entries.values())

    @property
    def entry_count(self) -> int:
        return sum(len(items) for items in self.entries.values())

    @property
    def has_breaking(self) -> bool:
        return any(
            e.breaking
            for items in self.entries.values()
            for e in items
        )

    @property
    def has_features(self) -> bool:
        return bool(self.entries.get("feat"))


@dataclass
class Changelog:
    """The full CHANGELOG.md document, parsed.

    Attributes:
        header: The lines before the first ``## [...]`` heading.
            Includes the title, description, format reference.
        unreleased: The ``[Unreleased]`` section (always present).
        releases: Past releases, newest first.
    """

    header: str = ""
    unreleased: ChangelogSection = field(
        default_factory=lambda: ChangelogSection(version="Unreleased"),
    )
    releases: list[ChangelogSection] = field(default_factory=list)

    @property
    def all_sections(self) -> list[ChangelogSection]:
        """All sections in order: Unreleased first, then releases."""
        return [self.unreleased, *self.releases]

    @property
    def latest_version(self) -> str | None:
        """The most recent released version, or None."""
        if self.releases:
            return self.releases[0].version
        return None
