"""
Content Vault — binary file encryption/decryption.

Implements the COVAULT binary envelope format (.enc files):

    COVAULT_v1 | filename_len(2) | filename | mime_len(2) | mime |
    sha256(32) | salt(16) | iv(12) | tag(16) | ciphertext

Key derivation: PBKDF2-SHA256, 480_000 iterations (600_000 for exports).
Encryption: AES-256-GCM.

All lengths are little-endian unsigned 16-bit integers.
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
import struct
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

logger = logging.getLogger(__name__)

# Extension → MIME lookup (stdlib misses .webp, .mkv, .m4a, etc.)
_EXT_MIME: dict[str, str] = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
    ".bmp": "image/bmp", ".ico": "image/x-icon", ".avif": "image/avif",
    ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
    ".avi": "video/x-msvideo", ".mkv": "video/x-matroska",
    ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac",
    ".ogg": "audio/ogg", ".wav": "audio/wav", ".flac": "audio/flac",
    ".opus": "audio/opus", ".wma": "audio/x-ms-wma",
    ".pdf": "application/pdf", ".md": "text/markdown",
    ".json": "application/json", ".csv": "text/csv", ".txt": "text/plain",
}


def _guess_mime(filename: str) -> str:
    """Resolve MIME type from filename, stripping .enc if present."""
    name = filename
    if name.lower().endswith(".enc"):
        name = name[:-4]
    ext = Path(name).suffix.lower()
    if ext in _EXT_MIME:
        return _EXT_MIME[ext]
    return mimetypes.guess_type(name)[0] or "application/octet-stream"

# ── Constants ────────────────────────────────────────────────────────

MAGIC = b"COVAULT_v1"
MAGIC_LEN = len(MAGIC)

KDF_ITERATIONS = 480_000
KDF_ITERATIONS_EXPORT = 600_000

SALT_LEN = 16
IV_LEN = 12
TAG_LEN = 16
SHA256_LEN = 32
LEN_FIELD = 2  # uint16 little-endian

# Allowed extensions for media types
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".ico"}
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".avi", ".mkv"}
AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".aac"}
DOC_EXTS = {".pdf", ".docx", ".doc", ".txt", ".md", ".rst", ".xlsx", ".rtf"}
CODE_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".h", ".hpp",
    ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".scala", ".r",
    ".lua", ".dart", ".vue", ".svelte", ".zig", ".nim", ".ex", ".exs",
    ".clj", ".erl", ".hs", ".ml", ".fs", ".v", ".vhdl",
    ".html", ".htm", ".css", ".scss", ".less", ".sass", ".wasm",
}
SCRIPT_EXTS = {
    ".sh", ".bash", ".zsh", ".fish", ".bat", ".cmd", ".ps1", ".psm1",
    ".pl", ".awk", ".sed",
}
CONFIG_EXTS = {
    ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".conf",
    ".env", ".properties", ".xml", ".plist",
}
DATA_EXTS = {
    ".csv", ".tsv", ".sql", ".sqlite", ".db", ".parquet", ".ndjson",
    ".jsonl", ".avro", ".feather",
}
ARCHIVE_EXTS = {".zip", ".tar", ".gz", ".7z", ".rar", ".bz2", ".xz"}

# Special filenames that are configs regardless of extension
_CONFIG_FILENAMES = {
    "Makefile", "Dockerfile", "Vagrantfile", "Procfile",
    ".gitignore", ".gitattributes", ".editorconfig",
    ".dockerignore", ".eslintrc", ".prettierrc",
    "docker-compose.yml", "docker-compose.yaml",
    "project.yml", "pyproject.toml", "setup.cfg",
    "package.json", "tsconfig.json", "Cargo.toml", "go.mod",
}


# ── Key derivation ───────────────────────────────────────────────────

def _derive_key(passphrase: str, salt: bytes, iterations: int = KDF_ITERATIONS) -> bytes:
    """Derive a 256-bit key from passphrase using PBKDF2-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(passphrase.encode("utf-8"))


# ── Encrypt ──────────────────────────────────────────────────────────

def encrypt_file(
    source_path: Path,
    passphrase: str,
    output_path: Path | None = None,
    iterations: int = KDF_ITERATIONS,
) -> Path:
    """Encrypt a file into COVAULT binary envelope.

    Args:
        source_path: Path to the plaintext file.
        passphrase: Encryption passphrase.
        output_path: Where to write the encrypted file.
                     Defaults to ``source_path`` + ``.enc`` appended.
        iterations: KDF iteration count.

    Returns:
        Path to the encrypted file.

    Raises:
        FileNotFoundError: Source file doesn't exist.
        ValueError: Passphrase too short.
    """
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    if not passphrase or len(passphrase) < 4:
        raise ValueError("Passphrase must be at least 4 characters")

    if output_path is None:
        output_path = source_path.parent / (source_path.name + ".enc")

    # Read source
    plaintext = source_path.read_bytes()

    # Metadata
    filename = source_path.name.encode("utf-8")
    mime_type = _guess_mime(source_path.name).encode("utf-8")

    # Integrity
    sha256 = hashlib.sha256(plaintext).digest()

    # Crypto
    salt = os.urandom(SALT_LEN)
    iv = os.urandom(IV_LEN)
    key = _derive_key(passphrase, salt, iterations)
    aesgcm = AESGCM(key)

    # AES-GCM encrypt — returns ciphertext + tag appended
    ct_with_tag = aesgcm.encrypt(iv, plaintext, None)
    ciphertext = ct_with_tag[:-TAG_LEN]
    tag = ct_with_tag[-TAG_LEN:]

    # Build envelope
    envelope = bytearray()
    envelope.extend(MAGIC)
    envelope.extend(struct.pack("<H", len(filename)))
    envelope.extend(filename)
    envelope.extend(struct.pack("<H", len(mime_type)))
    envelope.extend(mime_type)
    envelope.extend(sha256)
    envelope.extend(salt)
    envelope.extend(iv)
    envelope.extend(tag)
    envelope.extend(ciphertext)

    output_path.write_bytes(bytes(envelope))

    logger.info(
        "Encrypted %s → %s (%d bytes → %d bytes)",
        source_path.name, output_path.name, len(plaintext), len(envelope),
    )
    return output_path


# ── Decrypt ──────────────────────────────────────────────────────────

def decrypt_file(
    vault_path: Path,
    passphrase: str,
    output_path: Path | None = None,
    iterations: int = KDF_ITERATIONS,
) -> Path:
    """Decrypt a COVAULT envelope back to the original file.

    Args:
        vault_path: Path to the .covault file.
        passphrase: Decryption passphrase.
        output_path: Where to write the decrypted file.
                     Defaults to original filename in same directory.
        iterations: KDF iteration count.

    Returns:
        Path to the decrypted file.

    Raises:
        FileNotFoundError: Vault file doesn't exist.
        ValueError: Invalid format, wrong passphrase, or integrity failure.
    """
    if not vault_path.exists():
        raise FileNotFoundError(f"Vault file not found: {vault_path}")

    data = vault_path.read_bytes()
    meta = _parse_envelope(data)

    # Decrypt
    salt = meta["salt"]
    iv = meta["iv"]
    tag = meta["tag"]
    ciphertext = meta["ciphertext"]

    key = _derive_key(passphrase, salt, iterations)
    aesgcm = AESGCM(key)

    try:
        plaintext = aesgcm.decrypt(iv, ciphertext + tag, None)
    except Exception:
        raise ValueError("Wrong passphrase — decryption failed")

    # Integrity check
    actual_hash = hashlib.sha256(plaintext).digest()
    if actual_hash != meta["sha256"]:
        raise ValueError("Integrity check failed — file may be corrupted")

    # Write output
    if output_path is None:
        output_path = vault_path.parent / meta["filename"]

    output_path.write_bytes(plaintext)

    logger.info(
        "Decrypted %s → %s (%d bytes)",
        vault_path.name, output_path.name, len(plaintext),
    )
    return output_path


def decrypt_file_to_memory(
    vault_path: Path,
    passphrase: str,
    iterations: int = KDF_ITERATIONS,
) -> tuple[bytes, dict]:
    """Decrypt a COVAULT envelope in memory (no file written).

    Args:
        vault_path: Path to the .enc file.
        passphrase: Decryption passphrase.
        iterations: KDF iteration count.

    Returns:
        Tuple of (plaintext_bytes, metadata_dict).
        metadata_dict has: filename, mime_type, sha256.

    Raises:
        FileNotFoundError: Vault file doesn't exist.
        ValueError: Invalid format, wrong passphrase, or integrity failure.
    """
    if not vault_path.exists():
        raise FileNotFoundError(f"Vault file not found: {vault_path}")

    data = vault_path.read_bytes()
    meta = _parse_envelope(data)

    key = _derive_key(passphrase, meta["salt"], iterations)
    aesgcm = AESGCM(key)

    try:
        plaintext = aesgcm.decrypt(meta["iv"], meta["ciphertext"] + meta["tag"], None)
    except Exception:
        raise ValueError("Wrong key — decryption failed")

    actual_hash = hashlib.sha256(plaintext).digest()
    if actual_hash != meta["sha256"]:
        raise ValueError("Integrity check failed — file may be corrupted")

    return plaintext, {
        "filename": meta["filename"],
        "mime_type": meta["mime_type"],
    }


# ── Metadata (no decryption) ─────────────────────────────────────────

def read_metadata(vault_path: Path) -> dict:
    """Read metadata from a COVAULT envelope without decrypting.

    Returns:
        Dict with: filename, mime_type, encrypted_size, original_hash
    """
    data = vault_path.read_bytes()
    meta = _parse_envelope(data)
    return {
        "filename": meta["filename"],
        "mime_type": meta["mime_type"],
        "encrypted_size": len(data),
        "original_hash": meta["sha256"].hex(),
    }


# ── Envelope parsing ────────────────────────────────────────────────

def _parse_envelope(data: bytes) -> dict:
    """Parse a COVAULT binary envelope, returning all components."""
    if len(data) < MAGIC_LEN:
        raise ValueError("File too small to be a COVAULT envelope")

    if data[:MAGIC_LEN] != MAGIC:
        raise ValueError("Not a COVAULT file — magic bytes mismatch")

    pos = MAGIC_LEN

    # Filename
    if pos + LEN_FIELD > len(data):
        raise ValueError("Truncated envelope: missing filename length")
    fn_len = struct.unpack("<H", data[pos:pos + LEN_FIELD])[0]
    pos += LEN_FIELD

    if pos + fn_len > len(data):
        raise ValueError("Truncated envelope: missing filename")
    filename = data[pos:pos + fn_len].decode("utf-8")
    pos += fn_len

    # MIME type
    if pos + LEN_FIELD > len(data):
        raise ValueError("Truncated envelope: missing MIME length")
    mime_len = struct.unpack("<H", data[pos:pos + LEN_FIELD])[0]
    pos += LEN_FIELD

    if pos + mime_len > len(data):
        raise ValueError("Truncated envelope: missing MIME type")
    mime_type = data[pos:pos + mime_len].decode("utf-8")
    pos += mime_len

    # SHA-256 hash
    if pos + SHA256_LEN > len(data):
        raise ValueError("Truncated envelope: missing SHA-256")
    sha256 = data[pos:pos + SHA256_LEN]
    pos += SHA256_LEN

    # Salt
    if pos + SALT_LEN > len(data):
        raise ValueError("Truncated envelope: missing salt")
    salt = data[pos:pos + SALT_LEN]
    pos += SALT_LEN

    # IV
    if pos + IV_LEN > len(data):
        raise ValueError("Truncated envelope: missing IV")
    iv = data[pos:pos + IV_LEN]
    pos += IV_LEN

    # Tag
    if pos + TAG_LEN > len(data):
        raise ValueError("Truncated envelope: missing tag")
    tag = data[pos:pos + TAG_LEN]
    pos += TAG_LEN

    # Ciphertext (rest of file)
    ciphertext = data[pos:]

    return {
        "filename": filename,
        "mime_type": mime_type,
        "sha256": sha256,
        "salt": salt,
        "iv": iv,
        "tag": tag,
        "ciphertext": ciphertext,
    }


# ── File classification ─────────────────────────────────────────────

def classify_file(path: Path) -> str:
    """Classify a file into a content category.

    Returns one of: 'image', 'video', 'audio', 'document', 'code', 'script',
    'config', 'data', 'archive', 'encrypted', 'other'

    For ``.enc`` files, classification is based on the inner extension
    (e.g. ``foo.md.enc`` → 'document').  Bare ``.enc`` → 'encrypted'.
    """
    name = path.name
    suffix = path.suffix.lower()

    # If it ends with .enc, classify by the inner extension
    if suffix == ".enc":
        inner = Path(path.stem).suffix.lower()  # e.g. Path("foo.md").suffix → ".md"
        if not inner:
            return "encrypted"  # bare .enc
        suffix = inner  # use inner extension for classification below
        name = path.stem  # use inner name for filename checks

    # Check special config filenames first
    if name in _CONFIG_FILENAMES:
        return "config"

    if suffix in IMAGE_EXTS:
        return "image"
    if suffix in VIDEO_EXTS:
        return "video"
    if suffix in AUDIO_EXTS:
        return "audio"
    if suffix in CODE_EXTS:
        return "code"
    if suffix in SCRIPT_EXTS:
        return "script"
    if suffix in CONFIG_EXTS:
        return "config"
    if suffix in DOC_EXTS:
        return "document"
    if suffix in DATA_EXTS:
        return "data"
    if suffix in ARCHIVE_EXTS:
        return "archive"
    return "other"


def is_covault_file(path: Path) -> bool:
    """Check if a file is a COVAULT encrypted file (by magic bytes)."""
    if not path.exists() or path.stat().st_size < MAGIC_LEN:
        return False
    with open(path, "rb") as f:
        return f.read(MAGIC_LEN) == MAGIC


# ── Content folder detection ────────────────────────────────────────

DEFAULT_CONTENT_DIRS = ["docs", "content", "media", "assets", "archive"]


def detect_content_folders(project_root: Path) -> list[dict]:
    """Auto-detect content folders in a project.

    Scans for known folder names and returns metadata about each.

    Returns:
        List of dicts: {name, path, file_count, total_size, categories}
    """
    folders = []

    for dir_name in DEFAULT_CONTENT_DIRS:
        folder = project_root / dir_name
        if folder.is_dir():
            info = _scan_folder(folder, project_root)
            folders.append(info)

    return folders


def _scan_folder(folder: Path, project_root: Path) -> dict:
    """Scan a folder and return summary metadata."""
    file_count = 0
    total_size = 0
    categories: dict[str, int] = {}
    encrypted_count = 0

    for f in folder.rglob("*"):
        if f.is_file():
            # Skip hidden files and __pycache__
            if any(part.startswith(".") or part == "__pycache__" for part in f.parts):
                continue
            file_count += 1
            total_size += f.stat().st_size
            cat = classify_file(f)
            categories[cat] = categories.get(cat, 0) + 1
            if cat == "encrypted":
                encrypted_count += 1

    return {
        "name": folder.name,
        "path": str(folder.relative_to(project_root)),
        "file_count": file_count,
        "total_size": total_size,
        "encrypted_count": encrypted_count,
        "categories": categories,
    }


def list_folder_contents(
    folder: Path,
    project_root: Path,
    include_hidden: bool = False,
    remote_assets: set[str] | None = None,
) -> list[dict]:
    """List files in a content folder with metadata.

    Files inside a `.large/` subdirectory are merged into the parent listing
    as if they lived in the parent folder. They keep their real path (for
    preview/download) but gain a ``tier: "large"`` flag.

    Hidden dot-dirs like ``.backup/`` are excluded from the listing entirely;
    their contents are managed through dedicated archive endpoints.

    Returns:
        List of dicts: {name, path, size, category, mime_type, encrypted, covault_meta}
    """
    if not folder.is_dir():
        return []

    files: list[dict] = []

    def _add_file(f: Path, *, tier: str = "git") -> None:
        """Append a single file entry."""
        if not include_hidden and f.name.startswith("."):
            return
        # Skip release metadata sidecars
        if f.name.endswith(".release.json"):
            return

        is_enc = f.suffix.lower() == ".enc" and is_covault_file(f)

        # Display name: strip .enc suffix for files like foo.md.enc
        display_name = f.name
        if is_enc:
            inner_name = f.stem  # "foo.md.enc" → "foo.md"
            if Path(inner_name).suffix:  # has inner extension
                display_name = inner_name
            # else bare .enc — keep as-is

        entry: dict = {
            "name": display_name,
            "path": str(f.relative_to(project_root)),
            "is_dir": False,
            "size": f.stat().st_size,
            "category": classify_file(f),
            "mime_type": _guess_mime(display_name),
            "encrypted": is_enc,
            "tier": tier,
        }

        # Read envelope metadata for encrypted files
        if is_enc:
            try:
                meta = read_metadata(f)
                entry["covault_meta"] = meta
            except Exception:
                entry["covault_meta"] = None

        # Check for release metadata sidecar
        release_meta_path = f.parent / f"{f.name}.release.json"
        if release_meta_path.exists():
            entry["has_release"] = True
            import json as _json
            try:
                _meta = _json.loads(release_meta_path.read_text())
                _status = _meta.get("status", "unknown")
                # Detect stale "uploading" — no active upload thread
                if _status == "uploading":
                    _fid = _meta.get("file_id", "")
                    try:
                        from .content_release import _release_upload_status
                        live = _release_upload_status.get(_fid, {})
                        if not live or live.get("status") not in ("uploading", "queued"):
                            _status = "stale"
                    except ImportError:
                        _status = "stale"
                entry["release_status"] = _status
                # Orphan check: skip only genuinely in-progress uploads
                if remote_assets is not None and _status not in ("uploading",):
                    _asset = (
                        _meta.get("old_asset_name")
                        or _meta.get("asset_name")
                        or f.name
                    )
                    if _asset not in remote_assets:
                        entry["release_orphaned"] = True
            except Exception:
                entry["release_status"] = "unknown"

        files.append(entry)

    for f in sorted(folder.iterdir()):
        if f.is_dir():
            # .large/ is virtual — merge its contents into this listing
            if f.name == ".large":
                for lf in sorted(f.iterdir()):
                    if lf.is_file():
                        _add_file(lf, tier="large")
                continue

            # Skip all hidden dirs (.backup, .git, etc.)
            if f.name.startswith("."):
                continue

            # Regular subdirectories — include as entries
            sub_count = sum(1 for _ in f.rglob("*") if _.is_file())
            files.append({
                "name": f.name,
                "path": str(f.relative_to(project_root)),
                "is_dir": True,
                "file_count": sub_count,
                "size": sum(x.stat().st_size for x in f.rglob("*") if x.is_file()),
            })
            continue

        _add_file(f)

    return files


def list_folder_contents_recursive(
    folder: Path,
    project_root: Path,
    include_hidden: bool = False,
    remote_assets: set[str] | None = None,
) -> list[dict]:
    """Recursively list all files under a folder, plus immediate subdirs.

    Returns immediate child directories (as ``is_dir: True`` entries) so the
    UI can still render folder cards for navigation.  All files in the entire
    subtree are collected into a flat list with a ``subfolder`` field
    indicating their relative location.

    Returns:
        List of dicts: dirs + files
    """
    if not folder.is_dir():
        return []

    files: list[dict] = []

    def _add_file(f: Path, *, tier: str = "git", subfolder: str = "") -> None:
        if not include_hidden and f.name.startswith("."):
            return
        if f.name.endswith(".release.json"):
            return

        is_enc = f.suffix.lower() == ".enc" and is_covault_file(f)

        display_name = f.name
        if is_enc:
            inner_name = f.stem
            if Path(inner_name).suffix:
                display_name = inner_name

        entry: dict = {
            "name": display_name,
            "path": str(f.relative_to(project_root)),
            "is_dir": False,
            "size": f.stat().st_size,
            "category": classify_file(f),
            "mime_type": _guess_mime(display_name),
            "encrypted": is_enc,
            "tier": tier,
            "subfolder": subfolder,
        }

        if is_enc:
            try:
                meta = read_metadata(f)
                entry["covault_meta"] = meta
            except Exception:
                entry["covault_meta"] = None

        release_meta_path = f.parent / f"{f.name}.release.json"
        if release_meta_path.exists():
            entry["has_release"] = True
            import json as _json
            try:
                _meta = _json.loads(release_meta_path.read_text())
                _status = _meta.get("status", "unknown")
                # Detect stale "uploading" — no active upload thread
                if _status == "uploading":
                    _fid = _meta.get("file_id", "")
                    try:
                        from .content_release import _release_upload_status
                        live = _release_upload_status.get(_fid, {})
                        if not live or live.get("status") not in ("uploading", "queued"):
                            _status = "stale"
                    except ImportError:
                        _status = "stale"
                entry["release_status"] = _status
                # Orphan check: skip only genuinely in-progress uploads
                if remote_assets is not None and _status not in ("uploading",):
                    _asset = (
                        _meta.get("old_asset_name")
                        or _meta.get("asset_name")
                        or f.name
                    )
                    if _asset not in remote_assets:
                        entry["release_orphaned"] = True
            except Exception:
                entry["release_status"] = "unknown"

        files.append(entry)

    def _walk(current: Path, rel_prefix: str = "") -> None:
        for item in sorted(current.iterdir()):
            if item.is_dir():
                if item.name.startswith(".") and item.name != ".large":
                    continue
                if item.name == ".large":
                    for lf in sorted(item.iterdir()):
                        if lf.is_file():
                            _add_file(lf, tier="large", subfolder=rel_prefix)
                else:
                    # Include immediate child dirs as navigable entries
                    if rel_prefix == "":
                        sub_count = sum(1 for _ in item.rglob("*") if _.is_file())
                        files.append({
                            "name": item.name,
                            "path": str(item.relative_to(project_root)),
                            "is_dir": True,
                            "file_count": sub_count,
                            "size": sum(
                                x.stat().st_size
                                for x in item.rglob("*") if x.is_file()
                            ),
                        })
                    sub = (rel_prefix + "/" + item.name) if rel_prefix else item.name
                    _walk(item, sub)
            elif item.is_file():
                _add_file(item, subfolder=rel_prefix)

    _walk(folder)
    return files

def format_size(size_bytes: int) -> str:
    """Format bytes into a human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
