"""Changelog API routes — view, edit, manage entries, bootstrap, cut release."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from src.ui.web.helpers import project_root as _project_root

changelog_bp = Blueprint("changelog", __name__)


# ═══════════════════════════════════════════════════════════════════
#  Read
# ═══════════════════════════════════════════════════════════════════


@changelog_bp.route("/changelog")
def changelog_get():  # type: ignore[no-untyped-def]
    """Return the parsed CHANGELOG.md structure.

    Response:
        {
            "ok": true,
            "exists": true,
            "unreleased": { entries: { "feat": [...], "fix": [...] }, entry_count: N, has_breaking: bool },
            "releases": [ { version, date, entries, entry_count }, ... ],
            "suggested_bump": "minor"
        }
    """
    from src.core.services.changelog.engine import load_changelog
    from src.core.services.changelog.parser import cc_bump_type, cc_section, parse_cc_message

    root = _project_root()
    path = root / "CHANGELOG.md"

    changelog = load_changelog(root)

    def _serialize_section(section):  # type: ignore[no-untyped-def]
        """Convert a ChangelogSection to JSON-safe dict."""
        entries_out = {}
        for key, items in section.entries.items():
            emoji, title = cc_section(key)
            entries_out[key] = {
                "emoji": emoji,
                "title": title,
                "label": f"{emoji} {title}",
                "items": [
                    {
                        "text": e.text,
                        "breaking": e.breaking,
                        "scope": e.scope,
                    }
                    for e in items
                ],
            }
        return {
            "version": section.version,
            "date": section.date,
            "entries": entries_out,
            "entry_count": section.entry_count,
            "has_breaking": section.has_breaking,
            "has_features": section.has_features,
            "is_empty": section.is_empty,
        }

    # Determine suggested bump from unreleased entries
    suggested_bump = "patch"
    if not changelog.unreleased.is_empty:
        # Build CCMessage equivalents from entry metadata
        from src.core.services.changelog.models import CCMessage
        cc_msgs = []
        for key, items in changelog.unreleased.entries.items():
            for entry in items:
                cc_msgs.append(CCMessage(
                    type=key,
                    scope=entry.scope,
                    description=entry.text,
                    breaking=entry.breaking,
                ))
        suggested_bump = cc_bump_type(cc_msgs)

    return jsonify({
        "ok": True,
        "exists": path.is_file(),
        "unreleased": _serialize_section(changelog.unreleased),
        "releases": [_serialize_section(r) for r in changelog.releases],
        "latest_version": changelog.latest_version,
        "suggested_bump": suggested_bump,
    })


# ═══════════════════════════════════════════════════════════════════
#  Entry management
# ═══════════════════════════════════════════════════════════════════


@changelog_bp.route("/changelog/entry", methods=["POST"])
def changelog_add_entry():  # type: ignore[no-untyped-def]
    """Add a manual entry to [Unreleased].

    JSON body:
        section: CC type key (e.g. "feat", "fix")
        text: entry text
        breaking: optional bool (default false)
    """
    from src.core.services.changelog.engine import (
        load_changelog,
        save_changelog,
    )
    from src.core.services.changelog.models import ChangelogEntry

    data = request.get_json(silent=True) or {}
    section_key = data.get("section", "").strip()
    text = data.get("text", "").strip()
    breaking = data.get("breaking", False)

    if not text:
        return jsonify({"error": "Entry text is required"}), 400
    if not section_key:
        return jsonify({"error": "Section key is required (e.g. 'feat', 'fix')"}), 400

    root = _project_root()
    changelog = load_changelog(root)

    entry = ChangelogEntry(
        text=text,
        breaking=breaking,
        section_key=section_key,
    )
    if breaking and "⚠️" not in text and "**BREAKING**" not in text:
        entry.text += " ⚠️ **BREAKING**"

    changelog.unreleased.entries.setdefault(section_key, []).append(entry)
    save_changelog(root, changelog)

    return jsonify({"ok": True, "entry_count": changelog.unreleased.entry_count})


@changelog_bp.route("/changelog/entry", methods=["PUT"])
def changelog_edit_entry():  # type: ignore[no-untyped-def]
    """Edit an entry in [Unreleased].

    JSON body:
        old_text: current entry text (exact match)
        new_text: replacement text
    """
    from src.core.services.changelog.engine import (
        edit_entry,
        load_changelog,
        save_changelog,
    )

    data = request.get_json(silent=True) or {}
    old_text = data.get("old_text", "").strip()
    new_text = data.get("new_text", "").strip()

    if not old_text or not new_text:
        return jsonify({"error": "Both old_text and new_text are required"}), 400

    root = _project_root()
    changelog = load_changelog(root)

    ok = edit_entry(changelog, old_text, new_text)
    if not ok:
        return jsonify({"error": "Entry not found"}), 404

    save_changelog(root, changelog)
    return jsonify({"ok": True})


@changelog_bp.route("/changelog/entry", methods=["DELETE"])
def changelog_delete_entry():  # type: ignore[no-untyped-def]
    """Remove an entry from [Unreleased].

    JSON body:
        text: entry text to remove (exact match)
    """
    from src.core.services.changelog.engine import (
        load_changelog,
        remove_entry,
        save_changelog,
    )

    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()

    if not text:
        return jsonify({"error": "Entry text is required"}), 400

    root = _project_root()
    changelog = load_changelog(root)

    ok = remove_entry(changelog, text)
    if not ok:
        return jsonify({"error": "Entry not found"}), 404

    save_changelog(root, changelog)
    return jsonify({"ok": True, "entry_count": changelog.unreleased.entry_count})


# ═══════════════════════════════════════════════════════════════════
#  Bootstrap — generate initial CHANGELOG.md from git history
# ═══════════════════════════════════════════════════════════════════


@changelog_bp.route("/changelog/bootstrap", methods=["POST"])
def changelog_bootstrap():  # type: ignore[no-untyped-def]
    """Generate initial CHANGELOG.md from git history.

    JSON body (optional):
        since_tag: only include commits after this tag
        max_commits: max commits to scan (default 200)
        save: whether to save immediately (default false — returns preview)
    """
    from src.core.services.changelog.engine import (
        bootstrap_changelog,
        save_changelog,
    )
    from src.core.services.changelog.engine import _render_changelog

    data = request.get_json(silent=True) or {}
    since_tag = data.get("since_tag")
    max_commits = data.get("max_commits", 200)
    save = data.get("save", False)

    root = _project_root()
    changelog = bootstrap_changelog(root, since_tag=since_tag, max_commits=max_commits)

    if save:
        save_changelog(root, changelog)

    preview = _render_changelog(changelog)

    return jsonify({
        "ok": True,
        "entry_count": changelog.unreleased.entry_count,
        "preview": preview,
        "saved": save,
    })


# ═══════════════════════════════════════════════════════════════════
#  Cut release — move [Unreleased] → [x.y.z]
# ═══════════════════════════════════════════════════════════════════


@changelog_bp.route("/changelog/release", methods=["POST"])
def changelog_cut_release():  # type: ignore[no-untyped-def]
    """Cut a release: move [Unreleased] → [version], bump pyproject.toml, tag.

    JSON body:
        version: version string (e.g. "0.2.0") — required
        date: optional release date (YYYY-MM-DD), defaults to today
        bump_pyproject: whether to bump pyproject.toml (default true)
        create_tag: whether to create a git tag (default true)
        commit: whether to auto-commit the changes (default true)
    """
    from src.core.services.changelog.engine import (
        cut_release,
        load_changelog,
        save_changelog,
    )

    data = request.get_json(silent=True) or {}
    version = data.get("version", "").strip()
    if not version:
        return jsonify({"error": "Version is required"}), 400

    date = data.get("date", "")
    bump_pyproject = data.get("bump_pyproject", True)
    create_tag = data.get("create_tag", True)
    commit = data.get("commit", True)

    root = _project_root()
    changelog = load_changelog(root)

    if changelog.unreleased.is_empty:
        return jsonify({"error": "No unreleased entries to release"}), 400

    # Cut the release
    release = cut_release(changelog, version, date=date)
    save_changelog(root, changelog)

    result = {
        "ok": True,
        "version": version,
        "date": release.date,
        "entry_count": release.entry_count,
        "files_changed": ["CHANGELOG.md"],
    }

    # Bump pyproject.toml if requested
    if bump_pyproject:
        try:
            _bump_pyproject_version(root, version)
            result["files_changed"].append("pyproject.toml")
        except Exception as e:
            result["pyproject_error"] = str(e)

    # Auto-commit
    if commit:
        try:
            from src.core.services.git.ops import run_git
            for f in result["files_changed"]:
                run_git("add", f, cwd=root)
            tag_name = f"v{version}" if not version.startswith("v") else version
            run_git("commit", "-m", f"chore(release): {tag_name}", cwd=root)

            r_hash = run_git("rev-parse", "--short", "HEAD", cwd=root)
            result["commit_hash"] = r_hash.stdout.strip() if r_hash.returncode == 0 else "?"
        except Exception as e:
            result["commit_error"] = str(e)

    # Create tag
    if create_tag:
        try:
            from src.core.services.git.ops import run_git
            tag_name = f"v{version}" if not version.startswith("v") else version
            r = run_git("tag", "-a", tag_name, "-m", f"Release {tag_name}", cwd=root)
            if r.returncode == 0:
                result["tag"] = tag_name
            else:
                result["tag_error"] = r.stderr.strip()
        except Exception as e:
            result["tag_error"] = str(e)

    return jsonify(result)


def _bump_pyproject_version(project_root, version):  # type: ignore[no-untyped-def]
    """Update the version in pyproject.toml."""
    import re

    path = project_root / "pyproject.toml"
    if not path.is_file():
        raise FileNotFoundError("pyproject.toml not found")

    content = path.read_text(encoding="utf-8")
    new_content = re.sub(
        r'^version\s*=\s*"[^"]*"',
        f'version = "{version}"',
        content,
        count=1,
        flags=re.MULTILINE,
    )

    if new_content == content:
        raise ValueError("Could not find version field in pyproject.toml")

    path.write_text(new_content, encoding="utf-8")
