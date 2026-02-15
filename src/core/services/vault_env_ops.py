"""
Vault .env file operations — channel-independent service.

Manages .env file CRUD: key listing with classification, template-based
creation, section management, key add/update/delete/move, metadata tags,
local-only markers, and environment activation (file swapping).

Extracted from ``src/ui/web/routes_vault.py``.
No Flask dependency — every function takes explicit ``env_path``
or ``project_root`` parameters.
"""

from __future__ import annotations

import base64
import logging
import os
import re
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════════════

_ACTIVE_MARKER = ".env.active"


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


# Re-export from the data layer — single source of truth.
from src.core.data import classify_key  # noqa: E402
from src.core.data import get_registry as _registry  # noqa: E402



# Module-level alias so existing ``ENV_TEMPLATE_SECTIONS`` references
# keep working.  It's now a thin wrapper around the registry.
ENV_TEMPLATE_SECTIONS: list[dict] = []  # populated on first use


def _ensure_templates() -> list[dict]:
    """Return env template sections, loading from registry on first call."""
    global ENV_TEMPLATE_SECTIONS  # noqa: PLW0603
    if not ENV_TEMPLATE_SECTIONS:
        ENV_TEMPLATE_SECTIONS = _registry().env_templates
    return ENV_TEMPLATE_SECTIONS


def read_env_values(env_path: Path) -> dict[str, str]:
    """Read raw key=value pairs from .env file."""
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if "# local-only" in line:
            line = line[: line.index("# local-only")].rstrip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in ('"', "'")
        ):
            value = value[1:-1]
        values[key] = value
    return values


def _find_section_end(lines: list[str], section: str) -> int:
    """Find the line index where new keys should be inserted for a section.

    If the section exists, returns the index after its last key.
    If not, appends a new section header and returns the index after it.
    """
    if not section:
        return len(lines)

    section_re = re.compile(
        r"^#\s*(?:[─━═\-=]{2,}\s*)?([A-Za-z][\w\s/()]+?)\s*(?:[─━═\-=]{2,})?\s*$"
    )

    current_section = "General"
    last_key_idx: dict[str, int] = {}

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#"):
            comment_body = stripped.lstrip("#").strip()
            m = section_re.match(stripped)
            if m:
                current_section = m.group(1).strip()
                last_key_idx.setdefault(current_section, i)
                continue
            if (
                comment_body
                and comment_body == comment_body.upper()
                and len(comment_body) > 3
                and not comment_body.startswith("!")
                and "=" not in comment_body
            ):
                current_section = comment_body.title()
                last_key_idx.setdefault(current_section, i)
                continue
            continue

        if stripped and "=" in stripped:
            last_key_idx[current_section] = i

    for name, idx in last_key_idx.items():
        if name.lower() == section.lower():
            return idx + 1

    lines.append("")
    lines.append(f"# ── {section} ──")
    return len(lines)


def _write_env(env_path: Path, lines: list[str]) -> None:
    """Write lines back to .env with trailing newline."""
    final = "\n".join(lines)
    if not final.endswith("\n"):
        final += "\n"
    env_path.write_text(final, encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════
#  Environment activation (file swapping)
# ═══════════════════════════════════════════════════════════════════


def read_active_env(project_root: Path) -> str:
    """Read which environment is currently active (empty = single-env mode)."""
    marker = project_root / _ACTIVE_MARKER
    if marker.exists():
        return marker.read_text(encoding="utf-8").strip()
    return ""


def activate_env(
    project_root: Path,
    new_name: str,
    *,
    vault_module: object | None = None,
) -> dict:
    """Swap .env files to make a different environment active.

    Flow:
        1. Save current .env → .env.<old_active>
        2. Copy .env.<new_active> → .env
        3. Write marker file .env.active
        4. Handles .env.vault files too

    Args:
        vault_module: The vault module providing _vault_path_for.
                      Passed in to avoid circular imports.
    """
    if not new_name:
        return {"error": "Missing environment name"}

    new_name = new_name.strip().lower()
    current = read_active_env(project_root)

    if current == new_name:
        return {"error": f"Already active: {new_name}"}

    env_path = project_root / ".env"
    env_vault = project_root / ".env.vault"
    new_env = project_root / f".env.{new_name}"
    new_vault = project_root / f".env.{new_name}.vault"

    # Target environment must exist (as .env.<name> or .env.<name>.vault)
    if not new_env.exists() and not new_vault.exists():
        return {"error": f"No .env.{new_name} or .env.{new_name}.vault found"}

    # Step 1: Save current .env → .env.<current>
    if current and env_path.exists():
        dest = project_root / f".env.{current}"
        shutil.copy2(str(env_path), str(dest))
        logger.info("Saved .env → .env.%s", current)

    if current and env_vault.exists():
        dest_vault = project_root / f".env.{current}.vault"
        shutil.copy2(str(env_vault), str(dest_vault))
        logger.info("Saved .env.vault → .env.%s.vault", current)

    # Step 2: Copy .env.<new> → .env
    if new_env.exists():
        shutil.copy2(str(new_env), str(env_path))
        logger.info("Activated .env.%s → .env", new_name)
    elif env_path.exists():
        env_path.unlink()

    if new_vault.exists():
        shutil.copy2(str(new_vault), str(env_vault))
        logger.info("Activated .env.%s.vault → .env.vault", new_name)
    elif env_vault.exists():
        env_vault.unlink()

    # Step 3: Update marker
    marker = project_root / _ACTIVE_MARKER
    marker.write_text(new_name, encoding="utf-8")

    # Determine resulting state
    if env_path.exists():
        state = "unlocked"
    elif env_vault.exists():
        state = "locked"
    else:
        state = "empty"

    return {
        "success": True,
        "previous": current or "(none)",
        "active": new_name,
        "state": state,
    }


# ═══════════════════════════════════════════════════════════════════
#  Key listing with classification
# ═══════════════════════════════════════════════════════════════════


def list_keys_enriched(env_path: Path, vault_path: Path) -> dict:
    """List .env keys with masked values and classification.

    Returns:
        - keys: flat list enriched with ``kind`` and raw value for config keys
        - sections: grouped by .env comment sections
        - state: 'unlocked', 'locked', or 'empty'
    """
    # Import vault here to use list_env_keys / list_env_sections
    from src.core.services import vault as vault_mod

    keys = vault_mod.list_env_keys(env_path)
    raw_values = read_env_values(env_path)

    for k in keys:
        kind = classify_key(k["key"])
        k["kind"] = kind
        if kind == "config":
            k["value"] = raw_values.get(k["key"], "")

    sections = vault_mod.list_env_sections(env_path)
    sections.sort(key=lambda s: 0 if "content vault" in s.get("name", "").lower() else 1)

    for section in sections:
        for k in section["keys"]:
            kind = classify_key(k["key"])
            k["kind"] = kind
            if kind == "config":
                k["value"] = raw_values.get(k["key"], "")

    if env_path.exists():
        state = "unlocked"
    elif vault_path.exists():
        state = "locked"
    else:
        state = "empty"

    return {"keys": keys, "sections": sections, "state": state}


# ═══════════════════════════════════════════════════════════════════
#  Template operations
# ═══════════════════════════════════════════════════════════════════


def get_templates() -> list[dict]:
    """Return available .env template sections for UI display."""
    sections = []
    for s in _ensure_templates():
        sections.append({
            "id": s["id"],
            "name": s["name"],
            "description": s["description"],
            "special": s.get("special", False),
            "keys": [
                {
                    "key": k["key"],
                    "has_default": bool(k["default"] and k["default"] != "__auto_generate__"),
                    "comment": k.get("comment", ""),
                }
                for k in s["keys"]
            ],
        })
    return sections


# ═══════════════════════════════════════════════════════════════════
#  Create .env
# ═══════════════════════════════════════════════════════════════════


def create_env(
    env_path: Path,
    *,
    entries: list[dict] | None = None,
    template_sections: list[str] | None = None,
) -> dict:
    """Create a new .env file from template sections and/or key-value pairs."""
    from datetime import datetime

    entries = entries or []
    template_sections = template_sections or []

    if env_path.exists():
        return {"error": f"{env_path.name} already exists"}

    lines = [
        "# Auto-generated by DevOps Control Plane",
        f"# Created at: {datetime.now().isoformat()}",
        "",
    ]

    key_count = 0

    if template_sections:
        section_map = {s["id"]: s for s in _ensure_templates()}

        ordered = []
        if "content_vault" in template_sections:
            ordered.append("content_vault")
        for sid in template_sections:
            if sid != "content_vault" and sid in section_map:
                ordered.append(sid)

        for sid in ordered:
            section = section_map[sid]
            dash_len = max(0, 48 - len(section["name"]))
            lines.append(f"# ── {section['name']} {'─' * dash_len}")

            for k in section["keys"]:
                value = k["default"]

                if value == "__auto_generate__":
                    raw = os.urandom(32)
                    value = base64.urlsafe_b64encode(raw).decode()

                comment = f"  # {k['comment']}" if k.get("comment") else ""

                if value:
                    lines.append(f"{k['key']}={value}{comment}")
                else:
                    lines.append(f"# {k['key']}={comment.strip()}")

                key_count += 1

            lines.append("")

    if entries:
        if template_sections:
            lines.append("# ── Custom ─────────────────────────────────────────")

        for entry in entries:
            key = entry.get("key", "").strip()
            value = entry.get("value", "").strip()
            if not key:
                continue
            if " " in value or "#" in value or "=" in value or not value:
                value = f'"{value}"'
            lines.append(f"{key}={value}")
            key_count += 1

        lines.append("")

    if not template_sections and not entries:
        raw = os.urandom(32)
        enc_key = base64.urlsafe_b64encode(raw).decode()
        lines.extend([
            "# ── Content Vault ──────────────────────────────────",
            f"CONTENT_VAULT_ENC_KEY={enc_key}  # Auto-generated AES-256 key",
            "",
        ])
        key_count = 1

    lines.append("")
    env_path.write_text("\n".join(lines), encoding="utf-8")

    logger.info("Created %s with %d entries", env_path.name, key_count)
    return {
        "success": True,
        "message": f"{env_path.name} created with {key_count} entries",
        "path": str(env_path),
    }


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

    logger.info("Added %d, updated %d keys in .env", added, updated)
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
    return {"success": True, "key": key, "meta_tags": meta_tags}
