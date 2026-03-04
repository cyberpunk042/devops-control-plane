"""
Changelog & versioning system — Conventional Commits, Keep a Changelog.

Public API:
    parse_cc_message     — parse a Conventional Commit message string
    cc_section           — (emoji, title) for a CC type
    cc_bump_type         — determine semver bump from a list of CC messages

    load_changelog       — parse CHANGELOG.md into structured object
    save_changelog       — write structured object back to CHANGELOG.md
    add_entry            — insert a CC commit into [Unreleased]
    remove_entry         — remove an entry from [Unreleased]
    edit_entry           — replace an entry in [Unreleased]
    cut_release          — move [Unreleased] → [x.y.z] section
    bootstrap_changelog  — generate initial CHANGELOG.md from git history
"""

from src.core.services.changelog.parser import (
    cc_bump_type,
    cc_section,
    parse_cc_message,
)
from src.core.services.changelog.engine import (
    add_entry,
    bootstrap_changelog,
    cut_release,
    edit_entry,
    load_changelog,
    remove_entry,
    save_changelog,
)

__all__ = [
    "parse_cc_message",
    "cc_section",
    "cc_bump_type",
    "load_changelog",
    "save_changelog",
    "add_entry",
    "remove_entry",
    "edit_entry",
    "cut_release",
    "bootstrap_changelog",
]
