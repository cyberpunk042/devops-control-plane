"""
Conventional Commits parser and section mapping.

This module is the **single source of truth** for:
    - Parsing CC message strings into structured ``CCMessage`` objects
    - Mapping CC types → (emoji, section title)
    - Determining semver bump type from a set of CC messages

Replaces the duplicated mappings that previously lived in:
    - ``docs_svc/generate.py`` → ``_commit_icon()``
    - ``artifacts/release_notes.py`` → ``_COMMIT_GROUPS``
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from src.core.services.changelog.models import CCMessage


# ═══════════════════════════════════════════════════════════════════
#  CC type → (emoji, section title)
#
#  This is the canonical mapping.  Every module that needs to
#  categorise or display CC types should call ``cc_section()``.
# ═══════════════════════════════════════════════════════════════════

_CC_SECTIONS: dict[str, tuple[str, str]] = {
    "feat":     ("✨", "Features"),
    "feature":  ("✨", "Features"),
    "fix":      ("🐛", "Bug Fixes"),
    "bugfix":   ("🐛", "Bug Fixes"),
    "docs":     ("📝", "Documentation"),
    "doc":      ("📝", "Documentation"),
    "style":    ("🎨", "Style"),
    "refactor": ("♻️", "Refactoring"),
    "perf":     ("⚡", "Performance"),
    "test":     ("🧪", "Tests"),
    "tests":    ("🧪", "Tests"),
    "build":    ("📦", "Build"),
    "ci":       ("⚙️", "CI/CD"),
    "chore":    ("🔧", "Chores"),
    "revert":   ("⏪", "Reverts"),
}

# Canonical type normalization — aliases → primary key
_TYPE_NORMALIZE: dict[str, str] = {
    "feature":  "feat",
    "bugfix":   "fix",
    "doc":      "docs",
    "tests":    "test",
}

# Section rendering order (determines the order in CHANGELOG.md)
SECTION_ORDER: list[str] = [
    "feat",
    "fix",
    "perf",
    "refactor",
    "docs",
    "style",
    "test",
    "build",
    "ci",
    "chore",
    "revert",
]

# Bump impact per CC type
_BUMP_IMPACT: dict[str, str] = {
    "feat":     "minor",
    "fix":      "patch",
    "perf":     "patch",
    "refactor": "patch",
    "docs":     "patch",
    "style":    "patch",
    "test":     "patch",
    "build":    "patch",
    "ci":       "patch",
    "chore":    "patch",
    "revert":   "patch",
}

# Default section for unrecognized types
_DEFAULT_SECTION: tuple[str, str] = ("📋", "Other Changes")
_DEFAULT_TYPE = "other"


# ═══════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════


def cc_section(cc_type: str) -> tuple[str, str]:
    """Return ``(emoji, section_title)`` for a Conventional Commit type.

    Args:
        cc_type: The CC type string (e.g. ``"feat"``, ``"fix"``).
            Case-insensitive.  Aliases are resolved.

    Returns:
        Tuple of ``(emoji, title)`` — e.g. ``("✨", "Features")``.
        Falls back to ``("📋", "Other Changes")`` for unrecognized types.

    Examples::

        >>> cc_section("feat")
        ("✨", "Features")
        >>> cc_section("bugfix")
        ("🐛", "Bug Fixes")
        >>> cc_section("unknown")
        ("📋", "Other Changes")
    """
    return _CC_SECTIONS.get(cc_type.lower(), _DEFAULT_SECTION)


def normalize_type(cc_type: str) -> str:
    """Normalize a CC type to its canonical form.

    E.g. ``"feature"`` → ``"feat"``, ``"bugfix"`` → ``"fix"``.
    Unrecognized types are returned as-is (lowercased).
    """
    lower = cc_type.lower()
    return _TYPE_NORMALIZE.get(lower, lower)


# ═══════════════════════════════════════════════════════════════════
#  CC message parser
# ═══════════════════════════════════════════════════════════════════

# Regex for the CC header line:
#   type(scope)!: description
#   type!: description
#   type(scope): description
#   type: description
_CC_HEADER_RE = re.compile(
    r"^(?P<type>[a-zA-Z]+)"       # type (letters only)
    r"(?:\((?P<scope>[^)]*)\))?"  # optional (scope)
    r"(?P<breaking>!)?"           # optional ! for breaking
    r":\s*"                       # colon + space
    r"(?P<desc>.+)$",             # description (rest of line)
)

# Footer patterns per CC spec:
#   BREAKING CHANGE: description
#   BREAKING-CHANGE: description
#   Reviewed-by: Name
#   Closes #123
_FOOTER_RE = re.compile(
    r"^(?P<token>[A-Za-z][A-Za-z0-9 -]*[A-Za-z0-9]|BREAKING CHANGE|BREAKING-CHANGE)"
    r"(?::\s*|\s+#)(?P<value>.+)$",
)


def parse_cc_message(message: str) -> CCMessage:
    """Parse a Conventional Commit message into structured form.

    Handles the full CC spec::

        <type>[optional scope][optional !]: <description>
        ← blank line →
        [optional body]
        ← blank line →
        [optional footer(s)]

    If the message does not match CC format, returns a ``CCMessage``
    with ``type="other"`` and the full message as ``description``.

    Args:
        message: The full commit message string (may be multi-line).

    Returns:
        A ``CCMessage`` with all fields populated.

    Examples::

        >>> m = parse_cc_message("feat(k8s)!: add multi-cluster support")
        >>> m.type, m.scope, m.breaking, m.description
        ('feat', 'k8s', True, 'add multi-cluster support')

        >>> m = parse_cc_message("fix: correct overflow\\n\\nBREAKING CHANGE: API removed")
        >>> m.breaking, m.breaking_note
        (True, 'API removed')
    """
    raw = message
    lines = message.split("\n")
    header_line = lines[0].strip()

    # ── Try to match CC header ──────────────────────────────────
    match = _CC_HEADER_RE.match(header_line)
    if not match:
        # Not a CC message — treat entire first line as description
        return CCMessage(
            type=_DEFAULT_TYPE,
            scope="",
            description=header_line,
            body="\n".join(lines[1:]).strip() if len(lines) > 1 else "",
            breaking=False,
            breaking_note="",
            footers={},
            raw=raw,
        )

    cc_type = normalize_type(match.group("type"))
    scope = (match.group("scope") or "").strip()
    breaking_bang = bool(match.group("breaking"))
    description = match.group("desc").strip()

    # ── Parse body and footers ──────────────────────────────────
    body_lines: list[str] = []
    footers: dict[str, str] = {}
    breaking_note = ""

    if len(lines) > 1:
        # Everything after the header, split by blank lines
        rest = "\n".join(lines[1:])

        # Split into paragraphs by double newline
        # The last paragraph(s) that match footer format are footers
        # Everything else is body
        paragraphs = rest.split("\n\n")

        # Walk from the end to find footer paragraphs
        footer_start = len(paragraphs)
        for i in range(len(paragraphs) - 1, -1, -1):
            para = paragraphs[i].strip()
            if not para:
                continue

            # Check if ALL lines in this paragraph are footer lines
            para_lines = para.splitlines()
            all_footer = all(
                _FOOTER_RE.match(pl.strip()) for pl in para_lines if pl.strip()
            )
            if all_footer and para_lines:
                footer_start = i
            else:
                break

        # Parse identified footer paragraphs
        for i in range(footer_start, len(paragraphs)):
            para = paragraphs[i].strip()
            for fl in para.splitlines():
                fl = fl.strip()
                if not fl:
                    continue
                fm = _FOOTER_RE.match(fl)
                if fm:
                    token = fm.group("token")
                    value = fm.group("value").strip()
                    footers[token] = value

                    # Detect BREAKING CHANGE footer
                    if token.upper().replace("-", " ") == "BREAKING CHANGE":
                        breaking_note = value

        # Body is everything before footer paragraphs
        body_parts = paragraphs[:footer_start]
        body = "\n\n".join(body_parts).strip()

        # Remove the leading blank line that separates header from body
        if body.startswith("\n"):
            body = body[1:]
        body_lines = [body] if body else []

    body = body_lines[0] if body_lines else ""
    breaking = breaking_bang or bool(breaking_note)

    # If breaking via ! but no explicit note, derive from description
    if breaking and not breaking_note and breaking_bang:
        breaking_note = description

    return CCMessage(
        type=cc_type,
        scope=scope,
        description=description,
        body=body,
        breaking=breaking,
        breaking_note=breaking_note,
        footers=footers,
        raw=raw,
    )


# ═══════════════════════════════════════════════════════════════════
#  Bump type determination
# ═══════════════════════════════════════════════════════════════════


def cc_bump_type(messages: Sequence[CCMessage]) -> str:
    """Determine the semver bump type from a collection of CC messages.

    Rules (highest wins):
        1. Any breaking change → ``"major"``
        2. Any ``feat`` → ``"minor"``
        3. Everything else → ``"patch"``

    Args:
        messages: Sequence of parsed CC messages.

    Returns:
        One of ``"major"``, ``"minor"``, ``"patch"``.

    Examples::

        >>> cc_bump_type([parse_cc_message("feat!: breaking feat")])
        'major'
        >>> cc_bump_type([parse_cc_message("feat: new thing")])
        'minor'
        >>> cc_bump_type([parse_cc_message("fix: a bug")])
        'patch'
    """
    has_breaking = False
    has_minor = False

    for msg in messages:
        if msg.breaking:
            has_breaking = True
            break  # Can't go higher than major
        impact = _BUMP_IMPACT.get(msg.type, "patch")
        if impact == "minor":
            has_minor = True

    if has_breaking:
        return "major"
    if has_minor:
        return "minor"
    return "patch"
