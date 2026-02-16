"""
Vault .env key CRUD, section management, and metadata operations.

Handles: add/update/delete/get keys, move keys between sections,
rename sections, toggle local-only, set metadata tags.

Channel-independent: no Flask or HTTP dependency.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from src.core.services.audit_helpers import make_auditor
from src.core.services.vault_env_ops import (
    _find_section_end,
    _write_env,
    read_env_values,
)

logger = logging.getLogger(__name__)

_audit = make_auditor("vault")


# ═══════════════════════════════════════════════════════════════════
#  Key CRUD
# ═══════════════════════════════════════════════════════════════════


def add_keys(
    env_path: Path,
    entries: list[dict],
    *,
    section: str = "",
) -> dict:
    """Add or update key-value pairs in an existing .env file."""
    if not entries:
        return {"error": "No entries provided"}

    if not env_path.exists():
        return {"error": ".env does not exist — create it first"}

    content = env_path.read_text(encoding="utf-8")
    existing_lines = content.splitlines()

    key_lines: dict[str, int] = {}
    for i, line in enumerate(existing_lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            clean = stripped
            if "# local-only" in clean:
                clean = clean[: clean.index("# local-only")].rstrip()
            k, _, _ = clean.partition("=")
            key_lines[k.strip()] = i

    insert_idx = _find_section_end(existing_lines, section) if section else None

    added = 0
    updated = 0

    for entry in entries:
        key = entry.get("key", "").strip()
        value = entry.get("value", "").strip()
        if not key:
            continue

        if " " in value or "#" in value or "=" in value:
            formatted = f'{key}="{value}"'
        else:
            formatted = f"{key}={value}"

        if key in key_lines:
            existing_lines[key_lines[key]] = formatted
            updated += 1
        else:
            if insert_idx is not None:
                existing_lines.insert(insert_idx, formatted)
                insert_idx += 1
                for k, idx in key_lines.items():
                    if idx >= insert_idx - 1:
                        key_lines[k] = idx + 1
            else:
                existing_lines.append(formatted)
            added += 1

    _write_env(env_path, existing_lines)

    key_names = [e.get("key", "") for e in entries if e.get("key")]
    logger.info("Added %d, updated %d keys in .env", added, updated)
    _audit(
        "🔑 Keys Added",
        f"{added + updated} keys {'added' if added else 'updated'} in {env_path.name}",
        action="added",
        target=env_path.name,
        detail={
            "file": env_path.name,
            "keys": key_names,
            "section": section or "(end of file)",
            "added": added,
            "updated": updated,
        },
        after_state={
            "keys_added": added,
            "keys_updated": updated,
            "key_names": key_names,
        },
    )
    return {
        "success": True,
        "added": added,
        "updated": updated,
        "message": f"Added {added}, updated {updated} keys",
    }


def update_key(env_path: Path, key: str, value: str) -> dict:
    """Update a single key's value in the .env file."""
    if not key:
        return {"error": "Missing 'key'"}

    if not env_path.exists():
        return {"error": ".env does not exist"}

    content = env_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    if " " in value or "#" in value or "=" in value:
        formatted_val = f'"{value}"'
    else:
        formatted_val = value

    found = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, _, _ = stripped.partition("=")
            if k.strip() == key:
                lines[i] = f"{key}={formatted_val}"
                found = True
                break

    if not found:
        return {"error": f"Key '{key}' not found in .env"}

    _write_env(env_path, lines)

    logger.info("Updated key %s in .env", key)
    _audit(
        "✏️ Key Updated",
        f"{key} updated in {env_path.name}",
        action="updated",
        target=key,
        detail={"file": env_path.name, "key": key},
    )
    return {"success": True, "key": key, "message": f"Updated {key}"}


def delete_key(env_path: Path, key: str) -> dict:
    """Remove a key from the .env file."""
    if not key:
        return {"error": "Missing 'key'"}

    if not env_path.exists():
        return {"error": ".env does not exist"}

    content = env_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    new_lines = []
    removed = False
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, _, _ = stripped.partition("=")
            if k.strip() == key:
                removed = True
                continue
        new_lines.append(line)

    if not removed:
        return {"error": f"Key '{key}' not found in .env"}

    _write_env(env_path, new_lines)

    logger.info("Deleted key %s from .env", key)
    _audit(
        "🗑️ Key Deleted",
        f"{key} removed from {env_path.name}",
        action="deleted",
        target=key,
        detail={"file": env_path.name, "key": key},
    )
    return {"success": True, "key": key, "message": f"Deleted {key}"}


def get_raw_value(env_path: Path, key: str) -> dict:
    """Return the raw value of a single .env key."""
    if not key:
        return {"error": "Missing 'key'"}

    values = read_env_values(env_path)

    if key not in values:
        return {"error": f"Key '{key}' not found"}

    return {"key": key, "value": values[key]}


# ═══════════════════════════════════════════════════════════════════
#  Section management
# ═══════════════════════════════════════════════════════════════════


def move_key(env_path: Path, key: str, target_section: str) -> dict:
    """Move a key from its current section to a different one."""
    if not key:
        return {"error": "Missing 'key'"}
    if not target_section:
        return {"error": "Missing 'section'"}

    if not env_path.exists():
        return {"error": ".env does not exist"}

    content = env_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    removed_line = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            clean = stripped
            if "# local-only" in clean:
                clean = clean[: clean.index("# local-only")].rstrip()
            k, _, _ = clean.partition("=")
            if k.strip() == key:
                removed_line = lines.pop(i)
                break

    if removed_line is None:
        return {"error": f"Key '{key}' not found in .env"}

    insert_idx = _find_section_end(lines, target_section)
    lines.insert(insert_idx, removed_line)

    _write_env(env_path, lines)

    logger.info("Moved key %s to section %s", key, target_section)
    _audit(
        "📦 Key Moved",
        f"{key} → section '{target_section}' in {env_path.name}",
        action="moved",
        target=key,
        detail={"file": env_path.name, "key": key, "target_section": target_section},
        after_state={"section": target_section, "file": env_path.name},
    )
    return {"success": True, "key": key, "section": target_section}


def rename_section(env_path: Path, old_name: str, new_name: str) -> dict:
    """Rename a section comment in .env."""
    if not old_name or not new_name:
        return {"error": "Missing old_name or new_name"}

    if not env_path.exists():
        return {"error": ".env does not exist"}

    content = env_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    section_re = re.compile(
        r"^#\s*(?:[─━═\-=]{2,}\s*)?([A-Za-z][\w\s/()]+?)\s*(?:[─━═\-=]{2,})?\s*$"
    )

    found = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue

        comment_body = stripped.lstrip("#").strip()

        m = section_re.match(stripped)
        if m and m.group(1).strip().lower() == old_name.lower():
            lines[i] = f"# ── {new_name} ──"
            found = True
            break

        if (
            comment_body
            and comment_body == comment_body.upper()
            and len(comment_body) > 3
            and comment_body.title().lower() == old_name.lower()
        ):
            lines[i] = f"# ── {new_name} ──"
            found = True
            break

    if not found:
        return {"error": f"Section '{old_name}' not found"}

    _write_env(env_path, lines)

    logger.info("Renamed section '%s' → '%s'", old_name, new_name)
    _audit(
        "✏️ Section Renamed",
        f"'{old_name}' → '{new_name}' in {env_path.name}",
        action="renamed",
        target=env_path.name,
        detail={"file": env_path.name, "old_name": old_name, "new_name": new_name},
        before_state={"section": old_name},
        after_state={"section": new_name},
    )
    return {"success": True, "old_name": old_name, "new_name": new_name}


# ═══════════════════════════════════════════════════════════════════
#  Markers & metadata
# ═══════════════════════════════════════════════════════════════════


def toggle_local_only(env_path: Path, key: str, *, local_only: bool = True) -> dict:
    """Toggle the # local-only comment on a .env key."""
    if not key:
        return {"error": "Missing 'key'"}

    if not env_path.exists():
        return {"error": ".env does not exist"}

    content = env_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    new_lines = []
    found = False
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            clean = stripped
            if "# local-only" in clean:
                clean = clean[: clean.index("# local-only")].rstrip()
            k, _, _ = clean.partition("=")
            if k.strip() == key:
                found = True
                if "# local-only" in line:
                    line = line[: line.index("# local-only")].rstrip()
                if local_only:
                    line = line + "  # local-only"
        new_lines.append(line)

    if not found:
        return {"error": f"Key '{key}' not found in .env"}

    _write_env(env_path, new_lines)

    logger.info("Toggled local-only=%s for key %s", local_only, key)
    _audit(
        "🏠 Local-Only Toggled",
        f"{key} {'marked' if local_only else 'unmarked'} as local-only in {env_path.name}",
        action="configured",
        target=key,
        detail={"file": env_path.name, "key": key, "local_only": local_only},
        after_state={"local_only": local_only},
    )
    return {"success": True, "key": key, "local_only": local_only}


def set_meta(env_path: Path, key: str, meta_tags: str) -> dict:
    """Set or update @ metadata tags on a .env key."""
    if not key:
        return {"error": "Missing 'key'"}
    if not meta_tags:
        return {"error": "Missing 'meta_tags'"}

    if not meta_tags.startswith("#"):
        meta_tags = f"# {meta_tags}"

    if not env_path.exists():
        return {"error": ".env does not exist"}

    content = env_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    new_lines: list[str] = []
    found = False
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        if (
            stripped
            and not stripped.startswith("#")
            and "=" in stripped
        ):
            clean = stripped
            if "# local-only" in clean:
                clean = clean[: clean.index("# local-only")].rstrip()
            k, _, _ = clean.partition("=")
            if k.strip() == key:
                found = True
                if new_lines and new_lines[-1].strip().startswith("#") and "@" in new_lines[-1]:
                    new_lines[-1] = meta_tags
                else:
                    new_lines.append(meta_tags)
                new_lines.append(lines[i])
                i += 1
                continue

        new_lines.append(lines[i])
        i += 1

    if not found:
        return {"error": f"Key '{key}' not found in .env"}

    _write_env(env_path, new_lines)

    logger.info("Set meta tags for key %s: %s", key, meta_tags)
    _audit(
        "🏷️ Key Metadata Set",
        f"{key} metadata updated in {env_path.name}",
        action="updated",
        target=key,
        detail={"file": env_path.name, "key": key, "tags": meta_tags},
        after_state={"meta_tags": meta_tags},
    )
    return {"success": True, "key": key, "meta_tags": meta_tags}
