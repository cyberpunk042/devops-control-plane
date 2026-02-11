"""
Vault API routes — REST endpoints for the secrets vault.

All endpoints return JSON and are prefixed under /api/vault/.
"""

from __future__ import annotations

import logging
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from . import vault

logger = logging.getLogger(__name__)

vault_bp = Blueprint("vault", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


def _env_path() -> Path:
    """Resolve the .env file path from the optional ``?env=`` query param.

    Mapping:
        (no param)       → .env          (single-env mode)
        env=development  → .env.development
        env=production   → .env.production
        env=<name>       → .env.<name>
    """
    env_name = request.args.get("env", "").strip().lower()
    root = _project_root()
    if not env_name:
        return root / ".env"
    return root / f".env.{env_name}"


# ── Status ───────────────────────────────────────────────────────────


@vault_bp.route("/vault/status")
def vault_status():  # type: ignore[no-untyped-def]
    """Get vault status for the default .env."""
    env_path = _env_path()
    status = vault.vault_status(env_path)
    return jsonify(status)


# ── Active environment (file swapping) ───────────────────────────────

_ACTIVE_MARKER = ".env.active"


def _read_active_env(root: Path) -> str:
    """Read which environment is currently active (empty = single-env mode)."""
    marker = root / _ACTIVE_MARKER
    if marker.exists():
        name = marker.read_text(encoding="utf-8").strip().lower()
        return name
    return ""


@vault_bp.route("/vault/active-env")
def vault_active_env():  # type: ignore[no-untyped-def]
    """Return the currently active environment name."""
    root = _project_root()
    return jsonify({"active": _read_active_env(root)})


@vault_bp.route("/vault/activate-env", methods=["POST"])
def vault_activate_env():  # type: ignore[no-untyped-def]
    """Swap .env files to make a different environment active.

    Flow:
        1. Save current .env → .env.<old_active>
        2. Copy .env.<new_active> → .env
        3. Write marker file .env.active
        4. Handles .env.vault files too
    """
    import shutil

    data = request.get_json(silent=True) or {}
    new_env = data.get("env", "").strip().lower()

    if not new_env:
        return jsonify({"error": "Environment name required"}), 400

    root = _project_root()
    current_active = _read_active_env(root)

    if new_env == current_active:
        return jsonify({
            "success": True,
            "active": new_env,
            "message": f"Already active: {new_env}",
        })

    dotenv = root / ".env"
    dotenv_vault = root / ".env.vault"

    # ── Step 1: Stash current .env → .env.<current> ──────────
    stash_path = root / f".env.{current_active}"

    if dotenv.exists():
        shutil.copy2(str(dotenv), str(stash_path))
        logger.info("Stashed .env → %s", stash_path.name)

    if dotenv_vault.exists():
        stash_vault = stash_path.with_suffix(stash_path.suffix + ".vault")
        shutil.copy2(str(dotenv_vault), str(stash_vault))
        logger.info("Stashed .env.vault → %s", stash_vault.name)

    # ── Step 2: Restore .env.<new> → .env ────────────────────
    source = root / f".env.{new_env}"

    source_vault = source.with_suffix(source.suffix + ".vault")

    # Remove current .env / .env.vault before copying
    if dotenv.exists():
        dotenv.unlink()
    if dotenv_vault.exists():
        dotenv_vault.unlink()

    if source.exists():
        shutil.copy2(str(source), str(dotenv))
        logger.info("Activated %s → .env", source.name)
    elif source_vault.exists():
        # Source is locked — copy the vault file instead
        shutil.copy2(str(source_vault), str(dotenv_vault))
        logger.info("Activated %s → .env.vault (locked)", source_vault.name)
    else:
        # No source file exists — .env will be empty
        logger.warning("No %s found — .env will be missing", source.name)

    # ── Step 3: Write marker ─────────────────────────────────
    marker = root / _ACTIVE_MARKER
    marker.write_text(new_env + "\n", encoding="utf-8")

    logger.info("Active environment changed: %s → %s", current_active, new_env)
    return jsonify({
        "success": True,
        "active": new_env,
        "previous": current_active,
        "message": f"Activated: {new_env}",
    })


# ── Lock ─────────────────────────────────────────────────────────────


@vault_bp.route("/vault/lock", methods=["POST"])
def vault_lock():  # type: ignore[no-untyped-def]
    """Lock (encrypt) the .env file."""
    data = request.get_json(silent=True) or {}
    passphrase = data.get("passphrase", "")

    if not passphrase:
        return jsonify({"error": "Missing passphrase"}), 400

    env_path = _env_path()

    try:
        result = vault.lock_vault(env_path, passphrase)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


# ── Unlock ───────────────────────────────────────────────────────────


@vault_bp.route("/vault/unlock", methods=["POST"])
def vault_unlock():  # type: ignore[no-untyped-def]
    """Unlock (decrypt) the .env.vault file."""
    data = request.get_json(silent=True) or {}
    passphrase = data.get("passphrase", "")

    if not passphrase:
        return jsonify({"error": "Missing passphrase"}), 400

    env_path = _env_path()

    try:
        result = vault.unlock_vault(env_path, passphrase)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


# ── Register Passphrase ──────────────────────────────────────────────


@vault_bp.route("/vault/register", methods=["POST"])
def vault_register():  # type: ignore[no-untyped-def]
    """Register passphrase for auto-lock without modifying files."""
    data = request.get_json(silent=True) or {}
    passphrase = data.get("passphrase", "")

    if not passphrase:
        return jsonify({"error": "Missing passphrase"}), 400

    env_path = _env_path()

    try:
        result = vault.register_passphrase(passphrase, env_path)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


# ── Auto-lock Config ─────────────────────────────────────────────────


@vault_bp.route("/vault/auto-lock", methods=["POST"])
def vault_auto_lock():  # type: ignore[no-untyped-def]
    """Configure auto-lock timeout."""
    data = request.get_json(silent=True) or {}
    minutes = data.get("minutes")

    if minutes is None:
        return jsonify({"error": "Missing 'minutes' field"}), 400

    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        return jsonify({"error": "'minutes' must be an integer"}), 400

    vault.set_auto_lock_minutes(minutes)
    return jsonify({
        "success": True,
        "auto_lock_minutes": minutes,
        "message": f"Auto-lock set to {minutes}min"
                   if minutes > 0 else "Auto-lock disabled",
    })


# ── Detect Secret Files ─────────────────────────────────────────────


@vault_bp.route("/vault/secrets")
def vault_secrets():  # type: ignore[no-untyped-def]
    """List detected secret files and their vault status."""
    files = vault.detect_secret_files(_project_root())
    return jsonify({"files": files})


# ── Read .env Keys (masked) ─────────────────────────────────────────


@vault_bp.route("/vault/keys")
def vault_keys():  # type: ignore[no-untyped-def]
    """List .env keys with masked values (no raw secrets exposed).

    Returns state: 'unlocked' (.env exists), 'locked' (.env.vault exists),
    or 'empty' (neither exists).

    Config (non-secret) keys include the raw value for inline editing.
    Secret keys only get masked values.
    """
    env_path = _env_path()
    vault_path = vault._vault_path_for(env_path)

    keys = vault.list_env_keys(env_path)

    # Read raw values for config keys
    raw_values = _read_env_values(env_path)

    # Enrich with kind classification and raw values for config keys
    for k in keys:
        kind = _classify_key(k["key"])
        k["kind"] = kind
        if kind == "config":
            k["value"] = raw_values.get(k["key"], "")

    # Section-based grouping from comments
    sections = vault.list_env_sections(env_path)

    # Content Vault always first
    sections.sort(key=lambda s: 0 if "content vault" in s.get("name", "").lower() else 1)

    for section in sections:
        for k in section["keys"]:
            kind = _classify_key(k["key"])
            k["kind"] = kind
            if kind == "config":
                k["value"] = raw_values.get(k["key"], "")

    if env_path.exists():
        state = "unlocked"
    elif vault_path.exists():
        state = "locked"
    else:
        state = "empty"

    return jsonify({"keys": keys, "sections": sections, "state": state})


# ── .env Template Sections ───────────────────────────────────────────

# Template sections are ordered — Content Vault is always first (special).
# Each section has: id, name, description, keys (list of {key, default, comment})
_ENV_TEMPLATE_SECTIONS = [
    {
        "id": "content_vault",
        "name": "Content Vault",
        "description": "Encryption key for content file protection",
        "special": True,
        "keys": [
            {
                "key": "CONTENT_VAULT_ENC_KEY",
                "default": "__auto_generate__",
                "comment": "Auto-generated AES-256 key for content encryption",
            },
        ],
    },
    {
        "id": "github_ci",
        "name": "GitHub CI",
        "description": "GitHub Actions and CI/CD integration",
        "keys": [
            {"key": "GITHUB_TOKEN", "default": "", "comment": "Auto-provided by GitHub Actions"},
            {"key": "GITHUB_REPOSITORY", "default": "", "comment": "owner/repo — auto-detected from git remote"},
        ],
    },
    {
        "id": "database",
        "name": "Database",
        "description": "Database connection settings",
        "keys": [
            {"key": "DATABASE_URL", "default": "", "comment": "e.g. postgres://localhost:5432/mydb"},
            {"key": "DATABASE_HOST", "default": "localhost", "comment": ""},
            {"key": "DATABASE_PORT", "default": "5432", "comment": ""},
            {"key": "DATABASE_NAME", "default": "", "comment": ""},
            {"key": "DATABASE_USER", "default": "", "comment": ""},
            {"key": "DATABASE_PASSWORD", "default": "", "comment": ""},
        ],
    },
    {
        "id": "api_keys",
        "name": "API Keys",
        "description": "External service API keys and tokens",
        "keys": [
            {"key": "API_KEY", "default": "", "comment": "Primary API key"},
            {"key": "API_SECRET", "default": "", "comment": "Primary API secret"},
            {"key": "OPENAI_API_KEY", "default": "", "comment": "OpenAI API key"},
            {"key": "STRIPE_SECRET_KEY", "default": "", "comment": "Stripe secret key"},
        ],
    },
    {
        "id": "app_config",
        "name": "App Config",
        "description": "Application configuration variables",
        "keys": [
            {"key": "APP_ENV", "default": "development", "comment": "development | staging | production"},
            {"key": "DEBUG", "default": "true", "comment": "Enable debug mode"},
            {"key": "LOG_LEVEL", "default": "info", "comment": "debug | info | warning | error"},
            {"key": "SECRET_KEY", "default": "", "comment": "App secret key for sessions/CSRF"},
            {"key": "PORT", "default": "3000", "comment": "Application port"},
        ],
    },
    {
        "id": "email",
        "name": "Email / SMTP",
        "description": "Email and notification service credentials",
        "keys": [
            {"key": "SMTP_HOST", "default": "", "comment": "SMTP server hostname"},
            {"key": "SMTP_PORT", "default": "587", "comment": ""},
            {"key": "SMTP_USER", "default": "", "comment": ""},
            {"key": "SMTP_PASSWORD", "default": "", "comment": ""},
            {"key": "SMTP_FROM", "default": "", "comment": "Default sender address"},
        ],
    },
    {
        "id": "cloud",
        "name": "Cloud / Storage",
        "description": "Cloud provider and object storage credentials",
        "keys": [
            {"key": "AWS_ACCESS_KEY_ID", "default": "", "comment": ""},
            {"key": "AWS_SECRET_ACCESS_KEY", "default": "", "comment": ""},
            {"key": "AWS_REGION", "default": "us-east-1", "comment": ""},
            {"key": "S3_BUCKET", "default": "", "comment": ""},
        ],
    },
]


@vault_bp.route("/vault/templates")
def vault_templates():  # type: ignore[no-untyped-def]
    """Return available .env template sections."""
    sections = []
    for s in _ENV_TEMPLATE_SECTIONS:
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
    return jsonify({"sections": sections})


# ── Create .env ──────────────────────────────────────────────────────


@vault_bp.route("/vault/create", methods=["POST"])
def vault_create():  # type: ignore[no-untyped-def]
    """Create a new .env file from template sections and/or key-value pairs.

    Request body:
        entries: list of {key, value} — explicit key-value pairs
        template_sections: list of section IDs to include
    """
    import base64
    import os

    data = request.get_json(silent=True) or {}
    entries = data.get("entries", [])
    template_sections = data.get("template_sections", [])

    env_path = _env_path()

    if env_path.exists():
        return jsonify({"error": f"{env_path.name} already exists"}), 400

    # Build .env content
    lines = [
        "# Auto-generated by DevOps Control Plane",
        f"# Created at: {__import__('datetime').datetime.now().isoformat()}",
        "",
    ]

    key_count = 0

    # ── Template sections ────────────────────────────────────────
    if template_sections:
        section_map = {s["id"]: s for s in _ENV_TEMPLATE_SECTIONS}

        # Always put Content Vault first if selected
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

                # Auto-generate encryption key
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

    # ── Explicit entries ─────────────────────────────────────────
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

    # ── Fallback: Content Vault with auto-generated key ──────────
    if not template_sections and not entries:
        raw = os.urandom(32)
        enc_key = base64.urlsafe_b64encode(raw).decode()
        lines.extend([
            "# ── Content Vault ──────────────────────────────────",
            f"CONTENT_VAULT_ENC_KEY={enc_key}  # Auto-generated AES-256 key",
            "",
        ])
        key_count = 1

    lines.append("")  # trailing newline
    env_path.write_text("\n".join(lines), encoding="utf-8")

    logger.info("Created %s with %d entries", env_path.name, key_count)
    return jsonify({
        "success": True,
        "message": f"{env_path.name} created with {key_count} entries",
        "path": str(env_path),
    })


# ── Add Keys to .env ────────────────────────────────────────────────


@vault_bp.route("/vault/add-keys", methods=["POST"])
def vault_add_keys():  # type: ignore[no-untyped-def]
    """Add or update key-value pairs in an existing .env file.

    Optional ``section`` field places new keys under that section comment.
    If the section doesn't exist yet, a comment header is created.
    """
    data = request.get_json(silent=True) or {}
    entries = data.get("entries", [])
    section = data.get("section", "").strip()

    if not entries:
        return jsonify({"error": "No entries provided"}), 400

    env_path = _env_path()

    if not env_path.exists():
        return jsonify({"error": ".env does not exist — create it first"}), 400

    content = env_path.read_text(encoding="utf-8")
    existing_lines = content.splitlines()

    # Build a map of existing keys to their line indices
    key_lines: dict[str, int] = {}
    for i, line in enumerate(existing_lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            # Strip # local-only for key matching
            clean = stripped
            if "# local-only" in clean:
                clean = clean[: clean.index("# local-only")].rstrip()
            k, _, _ = clean.partition("=")
            key_lines[k.strip()] = i

    # Find where to insert new keys for the requested section
    insert_idx = _find_section_end(existing_lines, section) if section else None

    added = 0
    updated = 0

    for entry in entries:
        key = entry.get("key", "").strip()
        value = entry.get("value", "").strip()
        if not key:
            continue

        # Quote values with spaces or special chars
        if " " in value or "#" in value or "=" in value:
            formatted = f'{key}="{value}"'
        else:
            formatted = f"{key}={value}"

        if key in key_lines:
            # Update existing line in-place
            existing_lines[key_lines[key]] = formatted
            updated += 1
        else:
            if insert_idx is not None:
                existing_lines.insert(insert_idx, formatted)
                # Shift indices for subsequent inserts
                insert_idx += 1
                # Shift existing key_lines indices
                for k, idx in key_lines.items():
                    if idx >= insert_idx - 1:
                        key_lines[k] = idx + 1
            else:
                existing_lines.append(formatted)
            added += 1

    # Ensure trailing newline
    final_content = "\n".join(existing_lines)
    if not final_content.endswith("\n"):
        final_content += "\n"

    env_path.write_text(final_content, encoding="utf-8")

    logger.info("Added %d, updated %d keys in .env", added, updated)
    return jsonify({
        "success": True,
        "added": added,
        "updated": updated,
        "message": f"Added {added}, updated {updated} keys",
    })


def _find_section_end(lines: list[str], section: str) -> int:
    """Find the line index where new keys should be inserted for a section.

    If the section exists, returns the index after its last key.
    If not, appends a new section header and returns the index after it.
    """
    import re

    if not section:
        return len(lines)

    section_re = re.compile(
        r"^#\s*(?:[─━═\-=]{2,}\s*)?([A-Za-z][\w\s/()]+?)\s*(?:[─━═\-=]{2,})?\s*$"
    )

    current_section = "General"
    last_key_idx: dict[str, int] = {}  # section → last key line index

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

    # Match case-insensitively
    for name, idx in last_key_idx.items():
        if name.lower() == section.lower():
            return idx + 1

    # Section doesn't exist — create it
    lines.append("")
    lines.append(f"# ── {section} ──")
    return len(lines)


@vault_bp.route("/vault/move-key", methods=["POST"])
def vault_move_key():  # type: ignore[no-untyped-def]
    """Move a key from its current section to a different one.

    Creates the target section if it doesn't exist.
    """
    data = request.get_json(silent=True) or {}
    key = data.get("key", "").strip()
    target_section = data.get("section", "").strip()

    if not key:
        return jsonify({"error": "Missing 'key'"}), 400
    if not target_section:
        return jsonify({"error": "Missing 'section'"}), 400

    env_path = _env_path()
    if not env_path.exists():
        return jsonify({"error": ".env does not exist"}), 400

    content = env_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Find and remove the key line
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
        return jsonify({"error": f"Key '{key}' not found in .env"}), 404

    # Find insert point for target section
    insert_idx = _find_section_end(lines, target_section)
    lines.insert(insert_idx, removed_line)

    final = "\n".join(lines)
    if not final.endswith("\n"):
        final += "\n"
    env_path.write_text(final, encoding="utf-8")

    logger.info("Moved key %s to section %s", key, target_section)
    return jsonify({
        "success": True,
        "key": key,
        "section": target_section,
    })


@vault_bp.route("/vault/rename-section", methods=["POST"])
def vault_rename_section():  # type: ignore[no-untyped-def]
    """Rename a section comment in .env."""
    import re

    data = request.get_json(silent=True) or {}
    old_name = data.get("old_name", "").strip()
    new_name = data.get("new_name", "").strip()

    if not old_name or not new_name:
        return jsonify({"error": "Missing old_name or new_name"}), 400

    env_path = _env_path()
    if not env_path.exists():
        return jsonify({"error": ".env does not exist"}), 400

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

        # Match decorated headers
        m = section_re.match(stripped)
        if m and m.group(1).strip().lower() == old_name.lower():
            # Preserve decoration style by replacing the name part
            lines[i] = f"# ── {new_name} ──"
            found = True
            break

        # Match plain uppercase headers
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
        return jsonify({"error": f"Section '{old_name}' not found"}), 404

    final = "\n".join(lines)
    if not final.endswith("\n"):
        final += "\n"
    env_path.write_text(final, encoding="utf-8")

    logger.info("Renamed section '%s' → '%s'", old_name, new_name)
    return jsonify({
        "success": True,
        "old_name": old_name,
        "new_name": new_name,
    })


# ── Update Key ──────────────────────────────────────────────────────

_SECRET_PATTERNS = {
    "key", "secret", "token", "password", "passwd", "pass",
    "credential", "auth", "api_key", "apikey", "private",
    "jwt", "cert", "certificate", "signing",
}


def _read_env_values(env_path: Path) -> dict[str, str]:
    """Read raw key=value pairs from .env file."""
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        # Strip # local-only marker
        if "# local-only" in line:
            line = line[: line.index("# local-only")].rstrip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip surrounding quotes
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in ('"', "'")
        ):
            value = value[1:-1]
        values[key] = value
    return values


def _classify_key(key_name: str) -> str:
    """Classify a key as 'secret' or 'config' based on name patterns."""
    lower = key_name.lower()
    for pattern in _SECRET_PATTERNS:
        if pattern in lower:
            return "secret"
    return "config"


@vault_bp.route("/vault/update-key", methods=["POST"])
def vault_update_key():  # type: ignore[no-untyped-def]
    """Update a single key's value in the .env file."""
    data = request.get_json(silent=True) or {}
    key = data.get("key", "").strip()
    value = data.get("value", "")

    if not key:
        return jsonify({"error": "Missing 'key'"}), 400

    env_path = _env_path()
    if not env_path.exists():
        return jsonify({"error": ".env does not exist"}), 400

    content = env_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Quote values with spaces or special chars
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
        return jsonify({"error": f"Key '{key}' not found in .env"}), 404

    final = "\n".join(lines)
    if not final.endswith("\n"):
        final += "\n"
    env_path.write_text(final, encoding="utf-8")

    logger.info("Updated key %s in .env", key)
    return jsonify({"success": True, "key": key, "message": f"Updated {key}"})


# ── Delete Key ──────────────────────────────────────────────────────


@vault_bp.route("/vault/delete-key", methods=["POST"])
def vault_delete_key():  # type: ignore[no-untyped-def]
    """Remove a key from the .env file."""
    data = request.get_json(silent=True) or {}
    key = data.get("key", "").strip()

    if not key:
        return jsonify({"error": "Missing 'key'"}), 400

    env_path = _env_path()
    if not env_path.exists():
        return jsonify({"error": ".env does not exist"}), 400

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
        return jsonify({"error": f"Key '{key}' not found in .env"}), 404

    final = "\n".join(new_lines)
    if not final.endswith("\n"):
        final += "\n"
    env_path.write_text(final, encoding="utf-8")

    logger.info("Deleted key %s from .env", key)
    return jsonify({"success": True, "key": key, "message": f"Deleted {key}"})

# ── Get raw value for a single key ───────────────────────────────────


@vault_bp.route("/vault/raw-value", methods=["POST"])
def vault_raw_value():  # type: ignore[no-untyped-def]
    """Return the raw value of a single .env key.

    Body: {"key": "MY_KEY"}
    Returns: {"key": "MY_KEY", "value": "raw_value"}
    """
    data = request.get_json(silent=True) or {}
    key = data.get("key", "").strip()
    if not key:
        return jsonify({"error": "Missing 'key'"}), 400

    env_path = _env_path()
    values = _read_env_values(env_path)

    if key not in values:
        return jsonify({"error": f"Key '{key}' not found"}), 404

    return jsonify({"key": key, "value": values[key]})


# ── Toggle local-only ────────────────────────────────────────────────


@vault_bp.route("/vault/toggle-local-only", methods=["POST"])
def vault_toggle_local_only():  # type: ignore[no-untyped-def]
    """Toggle the # local-only comment on a .env key.

    When local_only=true, appends '# local-only' to the line.
    When local_only=false, strips it.
    """
    data = request.get_json(silent=True) or {}
    key = data.get("key", "").strip()
    local_only = data.get("local_only", True)

    if not key:
        return jsonify({"error": "Missing 'key'"}), 400

    env_path = _env_path()
    if not env_path.exists():
        return jsonify({"error": ".env does not exist"}), 400

    content = env_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    new_lines = []
    found = False
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            # Get the key name (strip # local-only first for matching)
            clean = stripped
            if "# local-only" in clean:
                clean = clean[: clean.index("# local-only")].rstrip()
            k, _, _ = clean.partition("=")
            if k.strip() == key:
                found = True
                # Strip existing marker
                if "# local-only" in line:
                    line = line[: line.index("# local-only")].rstrip()
                # Add marker if requested
                if local_only:
                    line = line + "  # local-only"
        new_lines.append(line)

    if not found:
        return jsonify({"error": f"Key '{key}' not found in .env"}), 404

    final = "\n".join(new_lines)
    if not final.endswith("\n"):
        final += "\n"
    env_path.write_text(final, encoding="utf-8")

    logger.info("Toggled local-only=%s for key %s", local_only, key)
    return jsonify({
        "success": True,
        "key": key,
        "local_only": local_only,
    })


# ── Set metadata tags ────────────────────────────────────────────────


@vault_bp.route("/vault/set-meta", methods=["POST"])
def vault_set_meta():  # type: ignore[no-untyped-def]
    """Set or update @ metadata tags on a .env key.

    Body: {"key": "MY_KEY", "meta_tags": "@encoding:base64 @generated:ssh-ed25519"}

    If a comment line containing @ tags already exists immediately above the key,
    it is replaced.  Otherwise a new comment line is inserted.
    """
    data = request.get_json(silent=True) or {}
    key = data.get("key", "").strip()
    meta_tags = data.get("meta_tags", "").strip()

    if not key:
        return jsonify({"error": "Missing 'key'"}), 400
    if not meta_tags:
        return jsonify({"error": "Missing 'meta_tags'"}), 400

    # Ensure tags start with #
    if not meta_tags.startswith("#"):
        meta_tags = f"# {meta_tags}"

    env_path = _env_path()
    if not env_path.exists():
        return jsonify({"error": ".env does not exist"}), 400

    content = env_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    new_lines = []
    found = False
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        # Check if this line is the target KEY=value
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
                # Check if the previous line is already a meta comment
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
        return jsonify({"error": f"Key '{key}' not found in .env"}), 404

    final = "\n".join(new_lines)
    if not final.endswith("\n"):
        final += "\n"
    env_path.write_text(final, encoding="utf-8")

    logger.info("Set meta tags for key %s: %s", key, meta_tags)
    return jsonify({"success": True, "key": key, "meta_tags": meta_tags})


@vault_bp.route("/vault/export", methods=["POST"])
def vault_export():  # type: ignore[no-untyped-def]
    """Create an encrypted export of a secret file."""
    data = request.get_json(silent=True) or {}
    password = data.get("password", "")
    filename = data.get("filename", ".env")

    if not password:
        return jsonify({"error": "Missing password"}), 400

    file_path = _project_root() / filename

    try:
        envelope = vault.export_vault_file(file_path, password)
        return jsonify({"success": True, "envelope": envelope})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


# ── Import ───────────────────────────────────────────────────────────


@vault_bp.route("/vault/import", methods=["POST"])
def vault_import():  # type: ignore[no-untyped-def]
    """Import and decrypt an exported vault file."""
    data = request.get_json(silent=True) or {}
    password = data.get("password", "")
    vault_data = data.get("vault_data")
    target = data.get("target", ".env")
    dry_run = data.get("dry_run", False)

    if not password:
        return jsonify({"error": "Missing password"}), 400
    if not vault_data:
        return jsonify({"error": "Missing vault_data"}), 400

    target_path = _project_root() / target

    try:
        result = vault.import_vault_file(
            vault_data, target_path, password, dry_run=dry_run,
        )
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
