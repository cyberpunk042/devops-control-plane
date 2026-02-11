"""
Secrets Vault — encrypt/decrypt secret files at rest.

When locked, plaintext secret files (e.g. .env) are encrypted into
*.vault using AES-256-GCM with PBKDF2 key derivation from a
user-chosen passphrase.  The plaintext is securely overwritten and
deleted.

When unlocked, the vault file is decrypted back and the encrypted
version is deleted.  The passphrase is held in server memory for
auto-lock.

Ported from: continuity-orchestrator/src/admin/vault.py
Adapted for: devops-control-plane (generalized — any secret file, not
only .env).

Features:
  - AES-256-GCM encryption with PBKDF2-SHA256 key derivation
  - Auto-lock after configurable inactivity (default: 30 min)
  - Rate limiting with exponential backoff on failed unlock attempts
  - Secure delete (3-pass random overwrite before unlink)
  - Export/import portable encrypted backups
  - Session passphrase management (thread-safe)
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from threading import Lock as ThreadLock
from threading import Timer
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Crypto constants ─────────────────────────────────────────────────
KDF_ITERATIONS = 100_000
SALT_BYTES = 16
IV_BYTES = 12
KEY_BYTES = 32
TAG_BYTES = 16

VAULT_SUFFIX = ".vault"

# ── In-memory session state ──────────────────────────────────────────
_session_passphrase: Optional[str] = None
_auto_lock_timer: Optional[Timer] = None
_auto_lock_minutes: int = 30
_lock = ThreadLock()


def get_passphrase() -> Optional[str]:
    """Return the current session passphrase, or None if not set."""
    return _session_passphrase

# ── Rate limiting state ──────────────────────────────────────────────
_failed_attempts: int = 0
_last_failed_time: float = 0
_RATE_LIMIT_TIERS = [
    # (max_attempts, lockout_seconds)
    (3, 30),       # After 3 fails: 30s lockout
    (6, 300),      # After 6 fails: 5min lockout
    (10, 900),     # After 10 fails: 15min lockout
]

# ── Exportable vault format ──────────────────────────────────────────
EXPORT_FORMAT = "dcp-vault-export-v1"
EXPORT_KDF_ITERATIONS = 600_000  # Higher for offline attacks


# ═══════════════════════════════════════════════════════════════════════
#  Internal helpers
# ═══════════════════════════════════════════════════════════════════════

def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """Derive AES-256 key from passphrase using PBKDF2-SHA256."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_BYTES,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    return kdf.derive(passphrase.encode("utf-8"))


def _vault_path_for(secret_path: Path) -> Path:
    """Return the vault file path for a given secret file."""
    return secret_path.with_suffix(secret_path.suffix + VAULT_SUFFIX)


# ── Rate limiting ────────────────────────────────────────────────────

def _check_rate_limit() -> Optional[dict]:
    """Check if unlock attempts are rate-limited.

    Returns:
        None if allowed, or dict with error info if blocked.
    """
    if _failed_attempts == 0:
        return None

    lockout_seconds = 0
    for max_attempts, seconds in _RATE_LIMIT_TIERS:
        if _failed_attempts >= max_attempts:
            lockout_seconds = seconds

    if lockout_seconds == 0:
        return None

    elapsed = time.time() - _last_failed_time
    remaining = lockout_seconds - elapsed

    if remaining > 0:
        return {
            "error": f"Too many failed attempts. Try again in {int(remaining)}s.",
            "retry_after": int(remaining),
            "attempts": _failed_attempts,
        }

    return None


def _record_failed_attempt() -> None:
    global _failed_attempts, _last_failed_time
    _failed_attempts += 1
    _last_failed_time = time.time()
    logger.warning("Vault unlock failed — attempt #%d", _failed_attempts)


def _reset_rate_limit() -> None:
    global _failed_attempts, _last_failed_time
    _failed_attempts = 0
    _last_failed_time = 0


# ── Auto-lock timer ─────────────────────────────────────────────────

def _start_auto_lock_timer() -> None:
    """(Re)start the auto-lock inactivity timer."""
    global _auto_lock_timer

    _cancel_auto_lock_timer()

    if _auto_lock_minutes <= 0:
        return  # Disabled

    def _on_timeout():
        logger.info(
            "Vault auto-lock triggered after %dmin inactivity",
            _auto_lock_minutes,
        )
        try:
            auto_lock()
        except Exception as e:
            logger.error("Auto-lock failed: %s", e)

    _auto_lock_timer = Timer(_auto_lock_minutes * 60, _on_timeout)
    _auto_lock_timer.daemon = True
    _auto_lock_timer.start()
    logger.debug("Auto-lock timer set: %dmin", _auto_lock_minutes)


def _cancel_auto_lock_timer() -> None:
    """Cancel any pending auto-lock timer."""
    global _auto_lock_timer
    if _auto_lock_timer is not None:
        _auto_lock_timer.cancel()
        _auto_lock_timer = None


def touch_activity(request_path: str = "", request_method: str = "GET") -> None:
    """Reset auto-lock timer on user activity.

    Only resets for user-initiated requests, NOT background polling.
    """
    if _session_passphrase is None:
        return

    # Ignore background polling endpoints
    _POLLING_ENDPOINTS = {
        "/api/status",
        "/api/health",
        "/api/vault/status",
    }

    if request_path in _POLLING_ENDPOINTS and request_method in ("GET", "POST"):
        return

    if request_path.startswith("/static/"):
        return

    _start_auto_lock_timer()


def _secure_delete(path: Path) -> None:
    """Overwrite file with random data before deleting."""
    try:
        size = path.stat().st_size
        for _ in range(3):
            with open(path, "wb") as f:
                f.write(os.urandom(max(size, 1)))
                f.flush()
                os.fsync(f.fileno())
        path.unlink()
    except Exception:
        try:
            path.unlink()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════
#  Core vault operations
# ═══════════════════════════════════════════════════════════════════════

def vault_status(secret_path: Path) -> dict:
    """Check vault status for a given secret file.

    Args:
        secret_path: Path to the secret file (e.g. /project/.env).

    Returns:
        Dict with 'locked' bool and metadata.
    """
    vault_path = _vault_path_for(secret_path)
    env_exists = secret_path.exists()
    vault_exists = vault_path.exists()

    if vault_exists and not env_exists:
        result: dict[str, Any] = {
            "locked": True,
            "vault_file": vault_path.name,
        }
    elif env_exists:
        result = {
            "locked": False,
            "vault_file": vault_path.name if vault_exists else None,
        }
    else:
        result = {"locked": False, "vault_file": None, "empty": True}

    result["auto_lock_minutes"] = _auto_lock_minutes
    result["has_passphrase"] = _session_passphrase is not None

    rate_info = _check_rate_limit()
    if rate_info:
        result["rate_limited"] = True
        result["retry_after"] = rate_info["retry_after"]

    return result


def lock_vault(secret_path: Path, passphrase: str) -> dict:
    """Encrypt a secret file and securely delete the plaintext.

    Args:
        secret_path: Path to the secret file.
        passphrase: User-chosen passphrase (min 4 chars).

    Returns:
        Success dict.

    Raises:
        ValueError: If file not found, passphrase too short.
    """
    global _session_passphrase

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    vault_path = _vault_path_for(secret_path)

    if not secret_path.exists():
        raise ValueError(f"{secret_path.name} not found — nothing to lock")

    if not passphrase or len(passphrase) < 4:
        raise ValueError("Passphrase must be at least 4 characters")

    plaintext = secret_path.read_bytes()

    salt = os.urandom(SALT_BYTES)
    iv = os.urandom(IV_BYTES)
    key = _derive_key(passphrase, salt)

    aesgcm = AESGCM(key)
    ct_and_tag = aesgcm.encrypt(iv, plaintext, None)
    ciphertext = ct_and_tag[:-TAG_BYTES]
    tag = ct_and_tag[-TAG_BYTES:]

    envelope = {
        "vault": True,
        "version": 1,
        "algorithm": "aes-256-gcm",
        "kdf": "pbkdf2-sha256",
        "kdf_iterations": KDF_ITERATIONS,
        "salt": base64.b64encode(salt).decode("ascii"),
        "iv": base64.b64encode(iv).decode("ascii"),
        "tag": base64.b64encode(tag).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        "original_name": secret_path.name,
    }

    vault_path.write_text(
        json.dumps(envelope, indent=2) + "\n",
        encoding="utf-8",
    )

    _secure_delete(secret_path)

    with _lock:
        _session_passphrase = passphrase

    _cancel_auto_lock_timer()

    logger.info("Vault locked — %s encrypted and deleted", secret_path.name)
    return {"success": True, "message": f"Vault locked ({secret_path.name})"}


def unlock_vault(secret_path: Path, passphrase: str) -> dict:
    """Decrypt a vault file back to its plaintext secret file.

    Args:
        secret_path: Path to the original secret file.
        passphrase: The passphrase used during lock.

    Returns:
        Success dict.

    Raises:
        ValueError: If vault not found, wrong passphrase, rate limited.
    """
    global _session_passphrase

    rate_info = _check_rate_limit()
    if rate_info:
        raise ValueError(rate_info["error"])

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    vault_path = _vault_path_for(secret_path)

    if not vault_path.exists():
        raise ValueError("No vault file found — nothing to unlock")

    if secret_path.exists():
        raise ValueError(
            f"{secret_path.name} already exists — vault is already unlocked"
        )

    envelope = json.loads(vault_path.read_text(encoding="utf-8"))

    if not envelope.get("vault"):
        raise ValueError("Invalid vault file format")

    salt = base64.b64decode(envelope["salt"])
    iv = base64.b64decode(envelope["iv"])
    tag = base64.b64decode(envelope["tag"])
    ciphertext = base64.b64decode(envelope["ciphertext"])

    key = _derive_key(passphrase, salt)
    aesgcm = AESGCM(key)

    try:
        plaintext = aesgcm.decrypt(iv, ciphertext + tag, None)
    except Exception:
        _record_failed_attempt()
        raise ValueError("Wrong passphrase — decryption failed")

    _reset_rate_limit()

    secret_path.write_bytes(plaintext)

    try:
        vault_path.unlink()
    except Exception:
        pass

    with _lock:
        _session_passphrase = passphrase

    _start_auto_lock_timer()

    logger.info("Vault unlocked — %s restored", secret_path.name)
    return {"success": True, "message": "Vault unlocked"}


def auto_lock() -> dict:
    """Auto-lock using the stored passphrase.

    Called by the inactivity timer. Requires that a project root
    has been registered via set_project_root().
    """
    with _lock:
        passphrase = _session_passphrase

    if not passphrase:
        logger.warning("Auto-lock skipped — no passphrase in memory")
        return {"success": False, "message": "No passphrase stored"}

    # Auto-lock targets the default .env
    project_root = _project_root_ref
    if project_root is None:
        logger.warning("Auto-lock skipped — no project root set")
        return {"success": False, "message": "No project root configured"}

    env_path = project_root / ".env"
    if not env_path.exists():
        logger.debug("Auto-lock skipped — .env doesn't exist (already locked?)")
        return {"success": False, "message": "Already locked"}

    return lock_vault(env_path, passphrase)


def register_passphrase(passphrase: str, secret_path: Path) -> dict:
    """Store a vault passphrase in memory without locking.

    Used when the vault is unlocked but the server has no passphrase
    in memory — auto-lock can't fire.

    Args:
        passphrase: The user's existing vault passphrase.
        secret_path: Path to the secret file (for validation).

    Returns:
        Success dict.

    Raises:
        ValueError: If passphrase is empty or wrong.
    """
    global _session_passphrase

    if not passphrase or not passphrase.strip():
        raise ValueError("Passphrase cannot be empty")

    rate_info = _check_rate_limit()
    if rate_info:
        raise ValueError(rate_info["error"])

    vault_path = _vault_path_for(secret_path)

    if not secret_path.exists():
        raise ValueError("Vault is locked — use unlock instead")

    # Validate passphrase against vault file if it exists
    if vault_path.exists():
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        try:
            envelope = json.loads(vault_path.read_text(encoding="utf-8"))
            if not envelope.get("vault"):
                raise ValueError("Invalid vault file format")

            salt = base64.b64decode(envelope["salt"])
            iv = base64.b64decode(envelope["iv"])
            tag = base64.b64decode(envelope["tag"])
            ciphertext = base64.b64decode(envelope["ciphertext"])

            key = _derive_key(passphrase, salt)
            aesgcm = AESGCM(key)
            aesgcm.decrypt(iv, ciphertext + tag, None)  # Validate only

        except (KeyError, json.JSONDecodeError):
            raise ValueError("Invalid vault file — cannot validate passphrase")
        except ValueError:
            raise
        except Exception:
            _record_failed_attempt()
            raise ValueError("Wrong passphrase")

        _reset_rate_limit()

    with _lock:
        _session_passphrase = passphrase

    _start_auto_lock_timer()

    logger.info("Passphrase registered — auto-lock enabled")
    return {"success": True, "message": "Passphrase registered — auto-lock enabled"}


def set_auto_lock_minutes(minutes: int) -> None:
    """Configure the auto-lock timeout.

    Args:
        minutes: Minutes of inactivity before auto-lock. 0 to disable.
    """
    global _auto_lock_minutes
    _auto_lock_minutes = max(0, minutes)

    if _session_passphrase is not None:
        _start_auto_lock_timer()

    logger.info(
        "Auto-lock timeout set to %dmin%s",
        _auto_lock_minutes,
        " (disabled)" if _auto_lock_minutes == 0 else "",
    )


# ═══════════════════════════════════════════════════════════════════════
#  Project root registration (for auto-lock)
# ═══════════════════════════════════════════════════════════════════════

_project_root_ref: Optional[Path] = None


def set_project_root(root: Path) -> None:
    """Register the project root for auto-lock operations."""
    global _project_root_ref
    _project_root_ref = root


def get_project_root() -> Optional[Path]:
    """Return the registered project root."""
    return _project_root_ref


# ── Re-exports from vault_io ────────────────────────────────────────
# (callers use `vault.xxx` — these proxy transparently)

from .vault_io import (  # noqa: E402, F401
    export_vault_file,
    import_vault_file,
    detect_secret_files,
    list_env_keys,
    list_env_sections,
    SECRET_FILE_PATTERNS,
    _parse_env_lines,
)

