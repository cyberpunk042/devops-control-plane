"""
Secrets Vault — export/import and env-file detection/parsing.

Split from vault.py. Contains:
  - Portable vault export (encrypt secret → JSON envelope for download)
  - Portable vault import (decrypt JSON envelope → write plaintext)
  - Secret file detection (scan for known secret files)
  - .env parsing (keys, sections, masked values)
  - Project root registration (for auto-lock)
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Optional

from src.core.services.vault import (
    KEY_BYTES,
    SALT_BYTES,
    IV_BYTES,
    TAG_BYTES,
    EXPORT_FORMAT,
    EXPORT_KDF_ITERATIONS,
    _vault_path_for,
)

logger = logging.getLogger(__name__)


from src.core.services.audit_helpers import make_auditor

_audit = make_auditor("vault")


# ═══════════════════════════════════════════════════════════════════════
#  Export / Import (portable encrypted backups)
# ═══════════════════════════════════════════════════════════════════════


def export_vault_file(secret_path: Path, passphrase: str) -> dict:
    """Encrypt a secret file into a downloadable vault envelope.

    Different from lock_vault: creates a portable file for backup;
    the original stays untouched.

    Args:
        secret_path: Path to the secret file.
        passphrase: User-chosen password (min 8 chars).

    Returns:
        Dict envelope ready to serialize as JSON.
    """
    from datetime import datetime, timezone

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not passphrase or len(passphrase) < 8:
        raise ValueError("Password must be at least 8 characters")

    if not secret_path.exists():
        raise ValueError(f"{secret_path.name} not found — nothing to export")

    plaintext = secret_path.read_bytes()

    salt = os.urandom(SALT_BYTES)
    iv = os.urandom(IV_BYTES)

    key = hashlib.pbkdf2_hmac(
        "sha256",
        passphrase.encode("utf-8"),
        salt,
        EXPORT_KDF_ITERATIONS,
        dklen=KEY_BYTES,
    )

    aesgcm = AESGCM(key)
    ct_and_tag = aesgcm.encrypt(iv, plaintext, None)
    ciphertext = ct_and_tag[:-TAG_BYTES]
    tag = ct_and_tag[-TAG_BYTES:]

    envelope = {
        "format": EXPORT_FORMAT,
        "original_name": secret_path.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "kdf": "pbkdf2-sha256",
        "kdf_iterations": EXPORT_KDF_ITERATIONS,
        "salt": base64.b64encode(salt).decode("ascii"),
        "iv": base64.b64encode(iv).decode("ascii"),
        "tag": base64.b64encode(tag).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }
    _audit(
        "📤 Vault Exported",
        f"{secret_path.name} exported as encrypted envelope",
        action="exported",
        target=secret_path.name,
        detail={"file": secret_path.name},
    )
    return envelope


def import_vault_file(
    vault_data: dict,
    target_path: Path,
    passphrase: str,
    *,
    dry_run: bool = False,
) -> dict:
    """Decrypt an exported vault and optionally write to disk.

    Args:
        vault_data: Parsed JSON envelope.
        target_path: Where to write the decrypted file.
        passphrase: Password used to encrypt.
        dry_run: If True, just validate without writing.

    Returns:
        Dict with success info and change summary.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    fmt = vault_data.get("format")
    if fmt != EXPORT_FORMAT:
        raise ValueError(f"Unknown vault format: {fmt}")

    try:
        salt = base64.b64decode(vault_data["salt"])
        iv = base64.b64decode(vault_data["iv"])
        tag = base64.b64decode(vault_data["tag"])
        ciphertext = base64.b64decode(vault_data["ciphertext"])
        iterations = vault_data.get("kdf_iterations", EXPORT_KDF_ITERATIONS)
    except (KeyError, ValueError) as e:
        raise ValueError(f"Invalid vault envelope: {e}")

    key = hashlib.pbkdf2_hmac(
        "sha256",
        passphrase.encode("utf-8"),
        salt,
        iterations,
        dklen=KEY_BYTES,
    )

    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(iv, ciphertext + tag, None)
    except Exception:
        raise ValueError("Wrong password or corrupted vault file")

    new_content = plaintext.decode("utf-8")

    # Diff against current file if it's an .env
    changes: list[dict] = []
    if target_path.name == ".env":
        new_env = _parse_env_lines(new_content)
        current_env = {}
        if target_path.exists():
            current_env = _parse_env_lines(target_path.read_text("utf-8"))

        all_keys = sorted(set(list(new_env.keys()) + list(current_env.keys())))
        for k in all_keys:
            if k in new_env and k not in current_env:
                changes.append({"key": k, "action": "added"})
            elif k in new_env and k in current_env:
                action = "unchanged" if new_env[k] == current_env[k] else "changed"
                changes.append({"key": k, "action": action})
            else:
                changes.append({"key": k, "action": "kept"})

    if not dry_run:
        target_path.write_text(new_content, encoding="utf-8")
        logger.info("Vault imported — written to %s", target_path.name)
        _audit(
            "📥 Vault Imported",
            f"Encrypted envelope imported to {target_path.name}",
            action="imported",
            target=target_path.name,
            detail={"target": target_path.name},
        )

    return {
        "success": True,
        "changes": changes,
        "size": len(new_content),
    }


# ═══════════════════════════════════════════════════════════════════════
#  Secret file detection and parsing
# ═══════════════════════════════════════════════════════════════════════

# Known secret file patterns
SECRET_FILE_PATTERNS = [
    ".env",
    ".env.local",
    ".env.production",
    ".env.staging",
    "secrets.yml",
    "secrets.yaml",
    "credentials.json",
    ".secrets",
]


def detect_secret_files(project_root: Path) -> list[dict]:
    """Scan project root for known secret files.

    Includes static patterns plus dynamic ``.env.<envname>`` files
    for each environment configured in ``project.yml``.

    Returns a list of dicts with file info and vault status.
    """
    # Build the pattern list — start with static patterns
    patterns = list(SECRET_FILE_PATTERNS)

    # Add dynamic .env.<envname> from project.yml environments
    config_file = project_root / "project.yml"
    if config_file.is_file():
        try:
            import yaml

            raw = config_file.read_text(encoding="utf-8")
            data = yaml.safe_load(raw)
            if isinstance(data, dict):
                for env in data.get("environments", []):
                    name = env.get("name", "") if isinstance(env, dict) else str(env)
                    name = name.strip().lower()
                    if name and name != "dev":  # dev maps to .env (already listed)
                        env_file = f".env.{name}"
                        if env_file not in patterns:
                            patterns.append(env_file)
        except Exception:
            pass

    results = []

    for pattern in patterns:
        file_path = project_root / pattern
        vault_path = _vault_path_for(file_path)

        if file_path.exists():
            stat = file_path.stat()
            results.append({
                "name": pattern,
                "path": str(file_path),
                "exists": True,
                "locked": False,
                "size": stat.st_size,
                "modified": stat.st_mtime,
                "vault_exists": vault_path.exists(),
            })
        elif vault_path.exists():
            stat = vault_path.stat()
            results.append({
                "name": pattern,
                "path": str(file_path),
                "exists": False,
                "locked": True,
                "vault_size": stat.st_size,
                "vault_modified": stat.st_mtime,
                "vault_exists": True,
            })

    return results


def _parse_meta_tags(comment_line: str) -> dict:
    """Parse structured metadata tags from a comment line.

    Tags use ``@`` prefix:  ``# @type:toggle @encoding:base64 @options:a,b,c``

    Supported tags:
        @local-only            → {"local_only": True}
        @type:<t>              → {"type": "toggle"|"select"|"password"|"multiline"}
        @options:<csv>         → {"options": ["a","b","c"]}
        @encoding:<enc>        → {"encoding": "base64"}
        @generated:<gen>       → {"generated": "password"|"ssh-ed25519"|...}
        @length:<n>            → {"length": 32}

    Returns dict of parsed metadata (empty if no tags found).
    """
    import re

    if not comment_line or not comment_line.strip().startswith("#"):
        return {}

    body = comment_line.strip().lstrip("#").strip()
    if not body or "@" not in body:
        return {}

    meta: dict = {}
    # Match @key or @key:value tokens
    for m in re.finditer(r"@([\w-]+)(?::([^\s]+))?", body):
        tag = m.group(1).lower().replace("-", "_")
        val = m.group(2) or True

        if tag == "local_only":
            meta["local_only"] = True
        elif tag == "type":
            meta["type"] = val
        elif tag == "options":
            meta["options"] = [o.strip() for o in val.split(",") if o.strip()] if isinstance(val, str) else []
        elif tag == "encoding":
            meta["encoding"] = val
        elif tag == "generated":
            meta["generated"] = val
        elif tag == "length":
            try:
                meta["length"] = int(val) if isinstance(val, str) else val
            except (ValueError, TypeError):
                pass

    return meta


def list_env_keys(env_path: Path) -> list[dict]:
    """Parse a .env file and return keys with masked values and metadata.

    Args:
        env_path: Path to the .env file.

    Returns:
        List of dicts: {"key": str, "has_value": bool, "masked": str,
                        "local_only": bool, "meta": dict}
    """
    if not env_path.exists():
        return []

    content = env_path.read_text(encoding="utf-8")
    result = []
    pending_meta: dict = {}

    for line in content.splitlines():
        line = line.strip()
        if not line:
            pending_meta = {}
            continue

        # Comment line — check for metadata tags
        if line.startswith("#"):
            tags = _parse_meta_tags(line)
            if tags:
                pending_meta.update(tags)
            continue

        if "=" not in line:
            pending_meta = {}
            continue

        # Detect # local-only marker at end of line (legacy)
        local_only = False
        if "# local-only" in line:
            local_only = True
            line = line[: line.index("# local-only")].rstrip()

        # Also pick up @local-only from meta comment
        if pending_meta.get("local_only"):
            local_only = True

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()

        # Strip quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]

        has_value = bool(value)
        if has_value and len(value) > 3:
            masked = value[:2] + "•" * min(len(value) - 3, 20) + value[-1:]
        elif has_value:
            masked = "•" * len(value)
        else:
            masked = "(empty)"

        result.append({
            "key": key,
            "has_value": has_value,
            "masked": masked,
            "local_only": local_only,
            "meta": pending_meta if pending_meta else {},
        })
        pending_meta = {}

    return result


def list_env_sections(env_path: Path) -> list[dict]:
    """Parse a .env file into sections based on comment headers.

    Section headers are lines like:
        # ── Section Name ──
        # === SECTION ===
        # --- section ---
    Or simply uppercase comments like:
        # MY SECTION

    Returns list of dicts:
        {
            "name": str,
            "keys": [{key, has_value, masked, local_only, meta}, ...],
        }
    """
    if not env_path.exists():
        return []

    import re

    content = env_path.read_text(encoding="utf-8")
    sections: list[dict] = []
    current_section = "General"
    current_keys: list[dict] = []
    pending_meta: dict = {}

    section_re = re.compile(
        r"^#\s*(?:[─━═\-=]{2,}\s*)?([A-Za-z][\w\s/()]+?)\s*(?:[─━═\-=]{2,})?\s*$"
    )

    for line in content.splitlines():
        stripped = line.strip()

        if not stripped:
            pending_meta = {}
            continue

        # Try to match a section header or metadata comment
        if stripped.startswith("#"):
            comment_body = stripped.lstrip("#").strip()
            m = section_re.match(stripped)
            if m:
                # Save previous section if it has keys
                if current_keys:
                    sections.append(
                        {"name": current_section, "keys": current_keys}
                    )
                    current_keys = []
                current_section = m.group(1).strip()
                pending_meta = {}
                continue
            # Also catch plain uppercase comment section headers
            if (
                comment_body
                and comment_body == comment_body.upper()
                and len(comment_body) > 3
                and not comment_body.startswith("!")
                and "=" not in comment_body
                and "@" not in comment_body
            ):
                if current_keys:
                    sections.append(
                        {"name": current_section, "keys": current_keys}
                    )
                    current_keys = []
                current_section = comment_body.title()
                pending_meta = {}
                continue

            # Check for metadata tags
            tags = _parse_meta_tags(stripped)
            if tags:
                pending_meta.update(tags)
            continue

        if "=" not in stripped:
            pending_meta = {}
            continue

        # Detect # local-only marker at end of line (legacy)
        local_only = False
        if "# local-only" in stripped:
            local_only = True
            stripped = stripped[: stripped.index("# local-only")].rstrip()

        if pending_meta.get("local_only"):
            local_only = True

        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()

        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]

        has_value = bool(value)
        if has_value and len(value) > 3:
            masked = value[:2] + "•" * min(len(value) - 3, 20) + value[-1:]
        elif has_value:
            masked = "•" * len(value)
        else:
            masked = "(empty)"

        current_keys.append({
            "key": key,
            "has_value": has_value,
            "masked": masked,
            "local_only": local_only,
            "meta": pending_meta if pending_meta else {},
        })
        pending_meta = {}

    # Don't forget the last section
    if current_keys:
        sections.append({"name": current_section, "keys": current_keys})

    return sections


def _parse_env_lines(content: str) -> dict:
    """Parse .env content into key→value dict."""
    result = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
            v = v[1:-1]
        result[k] = v
    return result
