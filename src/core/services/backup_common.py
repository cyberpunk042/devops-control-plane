"""
Backup & Restore operations — channel-independent service.

Creates, lists, previews, restores, and manages `.tar.gz` backup
archives. No Flask dependency.

Extracted from ``src/ui/web/routes_backup*.py``.
"""

from __future__ import annotations

import io
import json
import logging
import re
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════════════

SKIP_DIRS = frozenset({
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    ".mypy_cache", ".ruff_cache", ".pytest_cache", ".tox",
    "dist", "build", ".egg-info", ".idea", ".vscode",
    ".gemini", ".agent", "state",
})

MEDIA_EXT = frozenset({
    ".mp4", ".webm", ".mov", ".avi", ".mkv",
    ".mp3", ".wav", ".flac", ".ogg", ".aac",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".tiff",
})

DOC_EXT = frozenset({
    ".md", ".txt", ".pdf", ".json", ".yaml", ".yml", ".xml",
    ".csv", ".docx", ".rst", ".html", ".htm", ".toml", ".ini",
})


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def classify_file(path: Path) -> str:
    """Classify a file by type using the shared content vault classifier."""
    from src.core.services.content_crypto import classify_file as _classify
    return _classify(path)


def backup_dir_for(folder: Path) -> Path:
    """Get / create a .backup/ directory inside the given folder."""
    d = folder / ".backup"
    d.mkdir(exist_ok=True)
    return d


def safe_backup_name(name: str) -> bool:
    """Validate backup filename pattern."""
    return bool(re.match(r"^backup_\d{8}T\d{6}\.tar\.gz(\.enc)?$", name))


def resolve_folder(project_root: Path, rel_path: str) -> Path | None:
    """Resolve a relative folder safely within project root."""
    target = (project_root / rel_path).resolve()
    try:
        target.relative_to(project_root)
    except ValueError:
        return None
    if not target.is_dir():
        return None
    return target


def read_manifest(archive_path: Path) -> dict | None:
    """Read backup_manifest.json from a tar.gz archive."""
    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            try:
                member = tar.getmember("backup_manifest.json")
                fobj = tar.extractfile(member)
                if fobj:
                    return json.loads(fobj.read().decode("utf-8"))
            except KeyError:
                return None
    except Exception:
        return None
    return None


def get_enc_key(project_root: Path) -> str:
    """Read CONTENT_VAULT_ENC_KEY from .env."""
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


def encrypt_archive(archive_path: Path, passphrase: str) -> Path:
    """Encrypt a .tar.gz archive using COVAULT format. Returns path to .tar.gz.enc."""
    from src.core.services.content_crypto import encrypt_file
    enc_path = encrypt_file(archive_path, passphrase)
    archive_path.unlink()
    return enc_path


def decrypt_archive(enc_path: Path, passphrase: str) -> Path:
    """Decrypt a .tar.gz.enc archive to a temp file.

    Caller is responsible for cleaning up the returned temp file.
    """
    from src.core.services.content_crypto import decrypt_file
    tmp_path = Path(tempfile.mktemp(suffix=".tar.gz"))
    dec_path = decrypt_file(enc_path, passphrase, output_path=tmp_path)
    return dec_path
