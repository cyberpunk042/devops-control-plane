"""
Chat encryption — encrypt/decrypt message text using CONTENT_VAULT_ENC_KEY.

Uses AES-256-GCM with PBKDF2-SHA256 key derivation, same crypto primitives
as vault.py but applied to short text strings instead of files.

Format: ``ENC:v1:<base64-salt>:<base64-iv>:<base64-ciphertext+tag>``
"""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

# Same constants as vault.py
KDF_ITERATIONS = 100_000
SALT_BYTES = 16
IV_BYTES = 12
KEY_BYTES = 32

ENC_PREFIX = "ENC:v1:"


def _get_enc_key(project_root: Path) -> str:
    """Read CONTENT_VAULT_ENC_KEY from .env.

    Reuses the same logic as backup_common.get_enc_key but inlined
    to avoid circular imports.
    """
    env_path = project_root / ".env"
    if not env_path.is_file():
        return ""
    try:
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("CONTENT_VAULT_ENC_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """Derive AES-256 key from passphrase using PBKDF2-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_BYTES,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    return kdf.derive(passphrase.encode("utf-8"))


def encrypt_text(plaintext: str, project_root: Path) -> str:
    """Encrypt text using CONTENT_VAULT_ENC_KEY.

    Args:
        plaintext: The text to encrypt.
        project_root: Project root (to find .env).

    Returns:
        Encrypted string in format ``ENC:v1:<salt>:<iv>:<ciphertext+tag>``.

    Raises:
        ValueError: If CONTENT_VAULT_ENC_KEY is not set.
    """
    passphrase = _get_enc_key(project_root)
    if not passphrase:
        raise ValueError("CONTENT_VAULT_ENC_KEY is not set in .env — cannot encrypt")

    salt = os.urandom(SALT_BYTES)
    iv = os.urandom(IV_BYTES)
    key = _derive_key(passphrase, salt)

    aesgcm = AESGCM(key)
    ciphertext_and_tag = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)

    parts = [
        base64.b64encode(salt).decode(),
        base64.b64encode(iv).decode(),
        base64.b64encode(ciphertext_and_tag).decode(),
    ]
    return ENC_PREFIX + ":".join(parts)


def decrypt_text(enc_text: str, project_root: Path) -> str:
    """Decrypt an ``ENC:v1:...`` string back to plaintext.

    Args:
        enc_text: Encrypted string in ``ENC:v1:<salt>:<iv>:<ct>`` format.
        project_root: Project root (to find .env).

    Returns:
        Decrypted plaintext.

    Raises:
        ValueError: If key is not set, format is invalid, or decryption fails.
    """
    passphrase = _get_enc_key(project_root)
    if not passphrase:
        raise ValueError("CONTENT_VAULT_ENC_KEY is not set in .env — cannot decrypt")

    if not enc_text.startswith(ENC_PREFIX):
        raise ValueError(f"Not an encrypted string (missing {ENC_PREFIX} prefix)")

    payload = enc_text[len(ENC_PREFIX):]
    parts = payload.split(":")
    if len(parts) != 3:
        raise ValueError("Invalid ENC:v1 format — expected salt:iv:ciphertext")

    try:
        salt = base64.b64decode(parts[0])
        iv = base64.b64decode(parts[1])
        ciphertext_and_tag = base64.b64decode(parts[2])
    except Exception as e:
        raise ValueError(f"Invalid base64 in encrypted text: {e}") from e

    key = _derive_key(passphrase, salt)
    aesgcm = AESGCM(key)

    try:
        plaintext_bytes = aesgcm.decrypt(iv, ciphertext_and_tag, None)
    except Exception as e:
        raise ValueError(f"Decryption failed (wrong key or corrupted data): {e}") from e

    return plaintext_bytes.decode("utf-8")


def is_encrypted(text: str) -> bool:
    """Check if text is in ENC:v1:... format."""
    return text.startswith(ENC_PREFIX)
