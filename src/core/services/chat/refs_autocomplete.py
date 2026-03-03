"""
Chat @-reference autocomplete — suggest matching references for partial input.

Given a partial reference like ``@run:``, ``@run:run_2026``, or ``@thr``,
this module queries the appropriate data sources and returns rich suggestion
dicts for the frontend autocomplete dropdown.

Each entity type has its own internal autocompleter that knows how to query
its backing store (runs.jsonl, threads, traces, git log, content vault, etc.)
and format results with labels, details, and icons.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.core.services.chat.refs_parse import _relative_time, _VALID_TYPES

logger = logging.getLogger(__name__)

_MAX_SUGGESTIONS = 50


def autocomplete(prefix: str, project_root: Path) -> list[dict | str]:
    """Return matching @-references for a partial input.

    Args:
        prefix: Partial reference, e.g. "@run:", "@run:run_2026", "@thr".
        project_root: Repository root.

    Returns:
        List of suggestion dicts (rich) or strings (legacy).
        Rich dicts have: ref, label, detail, icon.
        Legacy strings are bare "@type:id" references.
    """
    if not prefix.startswith("@"):
        return []

    # Parse the prefix
    rest = prefix[1:]  # strip @
    if ":" in rest:
        ref_type, partial_id = rest.split(":", 1)
    else:
        # No colon yet — suggest matching types
        return [f"@{t}:" for t in sorted(_VALID_TYPES) if t.startswith(rest)]

    if ref_type not in _VALID_TYPES:
        return []

    _autocompleters: dict = {
        "run": _autocomplete_runs,
        "thread": _autocomplete_threads,
        "trace": _autocomplete_traces,
        "commit": _autocomplete_commits,
        "branch": _autocomplete_branches,
        "audit": _autocomplete_audits,
        "user": _autocomplete_users,
        "code": _autocomplete_code,
        "doc": _autocomplete_docs,
        "media": _autocomplete_media,
        "release": _autocomplete_releases,
        "file": _autocomplete_files,
    }

    ac = _autocompleters.get(ref_type)
    if ac is None:
        return []
    return ac(partial_id, project_root)


# ═══════════════════════════════════════════════════════════════════════
#  Internal autocompleters
# ═══════════════════════════════════════════════════════════════════════


def _autocomplete_runs(partial_id: str, project_root: Path) -> list[dict]:
    """Autocomplete run references from local ephemeral storage."""
    try:
        from src.core.services.run_tracker import load_runs
        runs = load_runs(project_root, n=50)
    except Exception as e:
        logger.debug("Failed to autocomplete runs: %s", e)
        return []

    results: list[dict] = []
    partial_lower = partial_id.lower() if partial_id else ""

    for run in runs:
        run_id = run.get("run_id", "")
        if partial_id:
            hit = (
                run_id.startswith(partial_id)
                or partial_lower in run.get("summary", "").lower()
                or partial_lower in run.get("type", "").lower()
                or partial_lower in run.get("subtype", "").lower()
            )
            if not hit:
                continue

        run_type = run.get("subtype") or run.get("type") or "run"
        label = run_type
        summary = run.get("summary", "")
        if summary:
            label += " \u2014 " + summary

        status = run.get("status", "")
        status_icons = {"ok": "\u2705", "failed": "\u274c", "partial": "\u26a0\ufe0f"}
        status_icon = status_icons.get(status, "")

        detail_parts = []
        if status_icon:
            detail_parts.append(f"{status_icon} {status}")
        if run.get("user"):
            detail_parts.append(run["user"])
        if run.get("started_at"):
            detail_parts.append(_relative_time(run["started_at"]))
        detail = " \u00b7 ".join(detail_parts)

        results.append({
            "ref": f"@run:{run_id}",
            "label": label,
            "detail": detail,
            "icon": "\U0001f680",
            "status": status,
        })
        if len(results) >= _MAX_SUGGESTIONS:
            break

    return results


def _autocomplete_threads(partial_id: str, project_root: Path) -> list[dict]:
    """Autocomplete thread references with rich metadata.

    Returns dicts with: ref, label (title), detail (tags + creator + time), icon.
    Supports keyword match on title and tags.
    """
    try:
        from src.core.services.chat.chat_ops import list_threads
        threads = list_threads(project_root)
    except Exception as e:
        logger.debug("Failed to autocomplete threads: %s", e)
        return []

    results: list[dict] = []
    partial_lower = partial_id.lower() if partial_id else ""

    for t in threads:
        if partial_id:
            hit = (
                t.thread_id.startswith(partial_id)
                or partial_lower in t.title.lower()
                or any(partial_lower in tag.lower() for tag in t.tags)
            )
            if not hit:
                continue

        label = t.title or t.thread_id

        detail_parts = []
        if t.tags:
            detail_parts.append(" ".join(f"\U0001f3f7 {tag}" for tag in t.tags[:3]))
        if t.created_by:
            detail_parts.append(t.created_by)
        if t.created_at:
            detail_parts.append(_relative_time(t.created_at))
        if t.anchor_run:
            detail_parts.append(f"\U0001f517 run")
        detail = " \u00b7 ".join(detail_parts)

        results.append({
            "ref": f"@thread:{t.thread_id}",
            "label": label,
            "detail": detail,
            "icon": "\U0001f4ac",
        })
        if len(results) >= _MAX_SUGGESTIONS:
            break

    return results


def _autocomplete_traces(partial_id: str, project_root: Path) -> list[dict]:
    """Autocomplete trace references with rich metadata.

    Returns dicts with: ref, label (name), detail (classification + summary + time),
    icon.  Supports keyword match on name and classification.
    """
    try:
        from src.core.services.trace.trace_recorder import list_traces
        traces = list_traces(project_root, n=50)
    except Exception as e:
        logger.debug("Failed to autocomplete traces: %s", e)
        return []

    results: list[dict] = []
    partial_lower = partial_id.lower() if partial_id else ""

    for t in traces:
        if partial_id:
            hit = (
                t.trace_id.startswith(partial_id)
                or partial_lower in t.name.lower()
                or partial_lower in t.classification.lower()
            )
            if not hit:
                continue

        label = t.name or t.trace_id

        detail_parts = []
        if t.classification:
            detail_parts.append(f"\U0001f3f7 {t.classification}")
        if t.auto_summary:
            snippet = t.auto_summary[:60]
            if len(t.auto_summary) > 60:
                snippet += "..."
            detail_parts.append(f'"{snippet}"')
        if t.event_count:
            detail_parts.append(f"{t.event_count} events")
        if t.started_at:
            detail_parts.append(_relative_time(t.started_at))
        detail = " \u00b7 ".join(detail_parts)

        results.append({
            "ref": f"@trace:{t.trace_id}",
            "label": label,
            "detail": detail,
            "icon": "\U0001f4cb",
        })
        if len(results) >= _MAX_SUGGESTIONS:
            break

    return results


def _autocomplete_commits(partial_id: str, project_root: Path) -> list[dict]:
    """Autocomplete commit references with rich metadata.

    Returns dicts with: ref, label (subject), detail (author · date),
    icon, hash.

    If partial_id looks like a hex hash prefix, filter by hash.
    Otherwise treat it as a keyword and search commit messages.
    """
    import subprocess

    is_hash = (
        all(c in "0123456789abcdef" for c in partial_id)
        if partial_id
        else True
    )

    if partial_id and not is_hash:
        # Keyword search in commit messages
        cmd = [
            "git", "-C", str(project_root), "log", "-30",
            "--grep", partial_id, "-i",
            "--format=%h%x00%s%x00%an%x00%ar",
        ]
    else:
        # Show recent commits (optionally filtered by hash prefix)
        cmd = [
            "git", "-C", str(project_root), "log", "-30",
            "--format=%h%x00%s%x00%an%x00%ar",
        ]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            return []
    except Exception as e:
        logger.debug("Failed to autocomplete commits: %s", e)
        return []

    results: list[dict] = []
    for line in r.stdout.strip().splitlines():
        parts = line.split("\x00")
        if len(parts) < 4:
            continue
        short_hash, subject, author, date_rel = (
            parts[0], parts[1], parts[2], parts[3],
        )
        # Hash prefix filter
        if partial_id and is_hash and not short_hash.startswith(partial_id):
            continue
        results.append({
            "ref": f"@commit:{short_hash}",
            "label": subject,
            "detail": f"{author} \u00b7 {date_rel}",
            "icon": "\U0001f4dd",
            "hash": short_hash,
        })
        if len(results) >= _MAX_SUGGESTIONS:
            break

    return results


def _autocomplete_branches(partial_id: str, project_root: Path) -> list[dict]:
    """Autocomplete branch references with rich metadata.

    Returns dicts with: ref, label (branch name), detail (last commit + date),
    icon.  Sorted by most recent committer date.
    """
    import subprocess

    cmd = [
        "git", "-C", str(project_root), "for-each-ref",
        "--sort=-committerdate",
        "--format=%(refname:short)%00%(subject)%00%(committerdate:relative)",
        "refs/heads/",
    ]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            return []
    except Exception as e:
        logger.debug("Failed to autocomplete branches: %s", e)
        return []

    results: list[dict] = []
    for line in r.stdout.strip().splitlines():
        parts = line.split("\x00")
        if len(parts) < 3:
            continue
        name, subject, date_rel = parts[0], parts[1], parts[2]
        if partial_id and not name.lower().startswith(partial_id.lower()):
            continue
        results.append({
            "ref": f"@branch:{name}",
            "label": name,
            "detail": f'"{subject}" \u00b7 {date_rel}',
            "icon": "\U0001f500",
        })
        if len(results) >= _MAX_SUGGESTIONS:
            break

    return results


def _autocomplete_audits(partial_id: str, project_root: Path) -> list[dict]:
    """Autocomplete audit references with rich metadata.

    Sources (in order):
      1. Saved scan snapshots from the ledger branch → section='saved'
      2. Unsaved (pending) audit snapshots → section='unsaved'
      3. Activity log entries (audit logs) → section='log'

    Audits and audit logs are separate data types with separate caps.
    """
    _MAX_AUDIT = 30   # saved + unsaved budget
    _MAX_LOG = 20     # audit log budget
    results: list[dict] = []
    audit_count = 0
    log_count = 0
    seen_ids: set[str] = set()
    partial_lower = partial_id.lower() if partial_id else ""

    # ── 1. Saved scan snapshots from ledger ─────────────────────
    try:
        from src.core.services.ledger.ledger_ops import list_saved_audits
        for snap in list_saved_audits(project_root, n=30):
            sid = snap.get("snapshot_id", "")
            if not sid:
                continue
            if partial_id:
                hit = (
                    partial_lower in sid.lower()
                    or partial_lower in (snap.get("card_key", "")).lower()
                    or partial_lower in (snap.get("summary", "")).lower()
                )
                if not hit:
                    continue

            card_key = snap.get("card_key", "?")
            summary = snap.get("summary", "")
            status = snap.get("status", "")
            iso = snap.get("iso", "")

            status_icon = "\u2705" if status == "ok" else "\u274c"
            detail_parts = [f"{status_icon} {status}"]
            if iso:
                detail_parts.append(_relative_time(iso))
            detail = " \u00b7 ".join(detail_parts)

            results.append({
                "ref": f"@audit:{sid}",
                "label": f"{card_key} \u2014 {summary}" if summary else card_key,
                "detail": detail,
                "icon": "\U0001f4cb",  # 📋 clipboard for saved snapshots
                "status": status,
                "section": "saved",
            })
            seen_ids.add(sid)
            audit_count += 1
            if audit_count >= _MAX_AUDIT:
                break
    except Exception as e:
        logger.debug("Ledger audit autocomplete failed: %s", e)

    # ── 2. Unsaved (pending) audit snapshots ─────────────────────
    try:
        from src.core.services.audit_staging import list_pending
        for snap in list_pending(project_root):
            sid = snap.get("snapshot_id", "")
            if not sid or sid in seen_ids:
                continue
            if partial_id:
                hit = (
                    partial_lower in sid.lower()
                    or partial_lower in (snap.get("card_key", "")).lower()
                    or partial_lower in (snap.get("summary", "")).lower()
                )
                if not hit:
                    continue

            card_key = snap.get("card_key", "?")
            summary = snap.get("summary", "")
            status = snap.get("status", "")
            audit_type = snap.get("audit_type", "devops")

            status_icon = "\u2705" if status == "ok" else "\u274c"
            type_label = "\U0001f4ca" if audit_type == "project" else "\U0001f6e0\ufe0f"
            detail_parts = [f"{status_icon} {status}", f"{type_label} {audit_type}", "unsaved"]
            detail = " \u00b7 ".join(detail_parts)

            results.append({
                "ref": f"@audit:{sid}",
                "label": f"{card_key} \u2014 {summary}" if summary else card_key,
                "detail": detail,
                "icon": "\u23f3",  # ⏳ hourglass for unsaved
                "status": status,
                "section": "unsaved",
            })
            seen_ids.add(sid)
            audit_count += 1
            if audit_count >= _MAX_AUDIT:
                break
    except Exception as e:
        logger.debug("Pending audit autocomplete failed: %s", e)

    # ── 3. Activity log entries (scan history) ─────────────────────
    try:
        from src.core.services.devops.activity import load_activity
        activities = load_activity(project_root, n=100)
        # Reverse so newest-first
        activities = list(reversed(activities))
    except Exception as e:
        logger.debug("Failed to load activity log for autocomplete: %s", e)
        return results

    for act in activities:
        card = act.get("card", "")
        ts = act.get("ts", 0)
        if not card or not ts:
            continue
        # Build a unique ID for this activity entry
        act_id = f"{card}_{int(ts)}"
        if act_id in seen_ids:
            continue
        if partial_id:
            hit = (
                partial_lower in card.lower()
                or partial_lower in act.get("label", "").lower()
                or partial_lower in act.get("summary", "").lower()
                or partial_lower in "log"
            )
            if not hit:
                continue

        label = act.get("label", card)
        summary = act.get("summary", "")
        status = act.get("status", "")
        iso = act.get("iso", "")
        dur = act.get("duration_s", 0)

        status_icon = "\u2705" if status == "ok" else "\u274c"
        detail_parts = [f"{status_icon} {status}"]
        if dur:
            detail_parts.append(f"{dur:.1f}s")
        if iso:
            detail_parts.append(_relative_time(iso))
        detail = " \u00b7 ".join(detail_parts)

        full_label = f"{label} \u2014 {summary}" if summary else label

        results.append({
            "ref": f"@audit:{act_id}",
            "label": full_label,
            "detail": detail,
            "icon": "\U0001f4ca",  # 📊 chart for activity log
            "status": status,
            "section": "log",
        })
        seen_ids.add(act_id)
        log_count += 1
        if log_count >= _MAX_LOG:
            break

    return results


def _autocomplete_users(partial_id: str, project_root: Path) -> list[dict]:
    """Autocomplete user references from git authors.

    Returns dicts with: ref, label (name), detail (commit count), icon.
    Uses git shortlog for deduplicated authors with commit counts.
    """
    import subprocess

    try:
        r = subprocess.run(
            ["git", "-C", str(project_root), "shortlog", "-sn", "--all", "--no-merges"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return []
    except Exception as e:
        logger.debug("Failed to autocomplete users: %s", e)
        return []

    results: list[dict] = []
    partial_lower = partial_id.lower() if partial_id else ""

    for line in r.stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 1)
        if len(parts) < 2:
            continue
        count_str, name = parts[0].strip(), parts[1].strip()
        if not name:
            continue
        if partial_lower and not name.lower().startswith(partial_lower):
            continue

        try:
            count = int(count_str)
        except ValueError:
            count = 0

        results.append({
            "ref": f"@user:{name}",
            "label": name,
            "detail": f"{count} commit{'s' if count != 1 else ''}",
            "icon": "\U0001f464",
        })
        if len(results) >= _MAX_SUGGESTIONS:
            break

    return results


_CODE_EXT_ICONS = {
    ".py": "\U0001f40d",
    ".js": "\U0001f4dc",
    ".ts": "\U0001f4dc",
    ".yaml": "\u2699\ufe0f",
    ".yml": "\u2699\ufe0f",
    ".sh": "\U0001f527",
    ".json": "\U0001f4cb",
    ".css": "\U0001f3a8",
    ".html": "\U0001f3a8",
    ".go": "\U0001f4dc",
    ".rs": "\U0001f4dc",
    ".toml": "\u2699\ufe0f",
    ".cfg": "\u2699\ufe0f",
    ".ini": "\u2699\ufe0f",
    ".sql": "\U0001f4cb",
    ".dockerfile": "\U0001f4e6",
}

_CODE_EXTS = frozenset(
    _CODE_EXT_ICONS.keys()
    | {".jsx", ".tsx", ".vue", ".rb", ".pl", ".php", ".java", ".c", ".cpp",
       ".h", ".hpp", ".cs", ".swift", ".kt", ".r", ".lua", ".ex", ".exs",
       ".tf", ".hcl", ".xml", ".env", ".bat", ".ps1", ".mk", ".makefile"}
)


def _autocomplete_code(partial_id: str, project_root: Path) -> list[dict]:
    """Autocomplete code file references via git ls-files.

    Only returns files with code/script/config extensions.
    Returns dicts with: ref, label (filename), detail (directory), icon.
    """
    import subprocess

    cmd = ["git", "-C", str(project_root), "ls-files"]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            return []
    except Exception as e:
        logger.debug("Failed to autocomplete code: %s", e)
        return []

    results: list[dict] = []
    partial_lower = partial_id.lower() if partial_id else ""

    for filepath in r.stdout.strip().splitlines():
        filepath = filepath.strip()
        if not filepath:
            continue

        p = Path(filepath)
        ext = p.suffix.lower()

        if ext not in _CODE_EXTS:
            continue

        if partial_lower and partial_lower not in filepath.lower():
            continue

        icon = _CODE_EXT_ICONS.get(ext, "\U0001f4c4")

        results.append({
            "ref": f"@code:{filepath}",
            "label": p.name,
            "detail": str(p.parent) + "/",
            "icon": icon,
            "extension": ext,
        })
        if len(results) >= _MAX_SUGGESTIONS:
            break

    return results


# ── Content vault helpers ───────────────────────────────────────────

_DOC_CATEGORIES = frozenset({"document"})
_MEDIA_CATEGORIES = frozenset({"image", "video", "audio"})

_CATEGORY_ICONS = {
    "document": "\U0001f4c4",
    "image": "\U0001f5bc\ufe0f",
    "video": "\U0001f3ac",
    "audio": "\U0001f3b5",
    "code": "\U0001f4bb",
    "script": "\U0001f527",
    "config": "\u2699\ufe0f",
    "data": "\U0001f4ca",
    "archive": "\U0001f4e6",
    "encrypted": "\U0001f512",
    "other": "\U0001f4c1",
}


def _content_vault_files(
    project_root: Path,
    partial_id: str,
    categories: frozenset[str] | None = None,
) -> list[dict]:
    """Shared scanner for doc/media/file ref types.

    Walks content vault dirs and returns rich dicts for files
    matching the given categories (or all if None).
    """
    from src.core.services.content.listing import (
        DEFAULT_CONTENT_DIRS,
        detect_content_folders,
    )
    from src.core.services.content.crypto import classify_file

    folders = detect_content_folders(project_root)
    if not folders:
        return []

    partial_lower = partial_id.lower() if partial_id else ""
    results: list[dict] = []

    for folder_info in folders:
        folder_path = project_root / folder_info["path"]
        if not folder_path.is_dir():
            continue

        for f in sorted(folder_path.rglob("*")):
            if not f.is_file():
                continue
            if f.name.startswith("."):
                continue

            cat = classify_file(f)
            if categories and cat not in categories:
                continue

            rel_path = str(f.relative_to(project_root))
            display_name = f.name
            if f.suffix.lower() == ".enc":
                inner = Path(f.stem).suffix.lower()
                if inner:
                    display_name = f.stem

            if partial_lower and partial_lower not in rel_path.lower():
                continue

            icon = _CATEGORY_ICONS.get(cat, "\U0001f4c1")
            parent = str(f.parent.relative_to(project_root))

            is_enc = f.suffix.lower() == ".enc"
            detail_parts = [parent + "/"]
            if is_enc:
                detail_parts.append("\U0001f512 encrypted")

            results.append({
                "ref": f"@file:{rel_path}",
                "label": display_name,
                "detail": " \u00b7 ".join(detail_parts),
                "icon": icon,
                "category": cat,
            })
            if len(results) >= _MAX_SUGGESTIONS:
                return results

    return results


def _autocomplete_docs(partial_id: str, project_root: Path) -> list[dict]:
    """Autocomplete doc references — documents in the content vault.

    Filters for document-category files (.md, .pdf, .txt, etc.)
    Returns dicts with: ref, label, detail, icon, category.
    """
    results = _content_vault_files(project_root, partial_id, _DOC_CATEGORIES)
    for r in results:
        r["ref"] = r["ref"].replace("@file:", "@doc:", 1)
    return results


def _autocomplete_media(partial_id: str, project_root: Path) -> list[dict]:
    """Autocomplete media references — images/video/audio in content vault.

    Filters for media-category files.
    Returns dicts with: ref, label, detail, icon, category.
    """
    results = _content_vault_files(project_root, partial_id, _MEDIA_CATEGORIES)
    for r in results:
        r["ref"] = r["ref"].replace("@file:", "@media:", 1)
    return results


def _autocomplete_files(partial_id: str, project_root: Path) -> list[dict]:
    """Autocomplete file references — all content vault files.

    Umbrella type: returns all content vault files regardless of category.
    Returns dicts with: ref, label, detail, icon, category.
    """
    return _content_vault_files(project_root, partial_id, None)


def _autocomplete_releases(partial_id: str, project_root: Path) -> list[dict]:
    """Autocomplete release references — two-layer drill-down.

    Layer 1 — ``@release:``  or ``@release:cont``
        Lists git tags (releases) with annotation + date.

    Layer 2 — ``@release:content-vault/`` or ``@release:content-vault/foo``
        Lists assets attached to that GitHub release.

    Returns dicts with: ref, label, detail, icon.
    """
    import subprocess

    # ── Layer 2: if partial_id contains '/', drill into release assets ──
    if "/" in partial_id:
        tag_name, asset_filter = partial_id.split("/", 1)
        return _autocomplete_release_assets(tag_name, asset_filter, project_root)

    # ── Layer 1: list git tags ──
    cmd = [
        "git", "-C", str(project_root), "for-each-ref",
        "--sort=-creatordate",
        "--format=%(refname:short)%00%(subject)%00%(creatordate:relative)%00%(objecttype)",
        "refs/tags/",
    ]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            return []
    except Exception as e:
        logger.debug("Failed to autocomplete releases: %s", e)
        return []

    results: list[dict] = []
    partial_lower = partial_id.lower() if partial_id else ""

    for line in r.stdout.strip().splitlines():
        parts = line.split("\x00")
        if len(parts) < 4:
            continue
        tag_name, subject, date_rel, obj_type = parts[0], parts[1], parts[2], parts[3]

        # Skip internal tags (run-tracking, ledger, etc.)
        if tag_name.startswith("scp/"):
            continue

        if partial_lower and partial_lower not in tag_name.lower():
            continue

        detail_parts = []
        if subject:
            snippet = subject[:60]
            if len(subject) > 60:
                snippet += "..."
            detail_parts.append(f'"{snippet}"')
        if date_rel:
            detail_parts.append(date_rel)
        if obj_type == "tag":
            detail_parts.append("annotated")
        detail_parts.append("\u2192 type / to browse assets")
        detail = " \u00b7 ".join(detail_parts)

        results.append({
            "ref": f"@release:{tag_name}/",
            "label": "\U0001f4e6 " + tag_name,
            "detail": detail,
            "icon": "\U0001f4e6",
        })
        if len(results) >= _MAX_SUGGESTIONS:
            break

    return results


def _autocomplete_release_assets(
    tag_name: str, asset_filter: str, project_root: Path
) -> list[dict]:
    """List assets attached to a specific GitHub release tag."""
    try:
        from src.core.services.content.release_sync import list_release_assets
        data = list_release_assets(project_root)
    except Exception as e:
        logger.debug("Failed to list release assets: %s", e)
        return [{"ref": "", "label": "Error", "detail": str(e), "icon": "\u274c"}]

    if not data.get("available"):
        return [{
            "ref": "",
            "label": "Release unavailable",
            "detail": data.get("error", ""),
            "icon": "\u274c",
        }]

    assets = data.get("assets", [])
    filter_lower = asset_filter.lower() if asset_filter else ""
    results: list[dict] = []

    for asset in assets:
        name = asset.get("name", "")
        size = asset.get("size", 0)
        if not name:
            continue
        if filter_lower and filter_lower not in name.lower():
            continue

        size_str = _format_size(size)

        results.append({
            "ref": f"@release:{tag_name}/{name}",
            "label": name,
            "detail": f"{size_str} \u00b7 {tag_name}",
            "icon": "\U0001f4ce",
        })
        if len(results) >= _MAX_SUGGESTIONS:
            break

    return results


def _format_size(size_bytes: int) -> str:
    """Format bytes into human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
