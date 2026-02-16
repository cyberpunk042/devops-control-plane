"""
Advanced content file operations — release restore, folder listing,
release sidecar check, encrypted save.

Channel-independent: no Flask or HTTP dependency.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.core.services.audit_helpers import make_auditor

logger = logging.getLogger(__name__)

_audit = make_auditor("content")


# ── Restore Large Files ─────────────────────────────────────────


def restore_large_files_from_release(project_root: Path) -> dict:
    """Download missing large files from the 'content-vault' GitHub Release.

    Returns:
        {"success": True, "restored": N, "skipped": N, "failed": N}.
    """
    from src.core.services.content_release import restore_large_files

    result = restore_large_files(project_root)

    _audit(
        "⬇️ Large Files Restored",
        f"{result.get('restored', 0)} large files downloaded from release",
        action="restored",
        target="content-vault",
        detail={
            "restored": result.get("restored", 0),
            "skipped": result.get("skipped", 0),
            "failed": result.get("failed", 0),
        },
        after_state={
            "restored": result.get("restored", 0),
            "skipped": result.get("skipped", 0),
            "failed": result.get("failed", 0),
        },
    )

    return {"success": True, **result}


# ── List all project directories ────────────────────────────────

_EXCLUDED_DIRS = {
    ".git", ".github", ".vscode", ".idea", ".proj", ".agent", ".gemini",
    "__pycache__", "node_modules", ".venv", "venv", "env",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "build", "dist", ".tox", ".eggs",
}


def list_all_project_folders(project_root: Path) -> list[dict[str, str]]:
    """List all top-level directories in the project.

    Hidden/build/cache directories are excluded.
    Used by the "Explore All" feature.
    """
    folders: list[dict[str, str]] = []
    try:
        for entry in sorted(project_root.iterdir()):
            if not entry.is_dir():
                continue
            name = entry.name
            if name.startswith(".") and name not in (".backup",):
                continue
            if name in _EXCLUDED_DIRS:
                continue
            folders.append({"name": name, "path": name})
    except OSError:
        pass
    return folders


# ── Release sidecar check ──────────────────────────────────────


def check_release_sidecar(
    target: Path,
    project_root: Path,
) -> dict[str, object]:
    """Check for a release sidecar and detect stale/orphaned states.

    Args:
        target: Absolute path to the content file.
        project_root: Project root directory.

    Returns:
        {"has_release": bool, "release_status": str, "release_orphaned": bool}
    """
    meta_path = target.parent / f"{target.name}.release.json"
    has_release = meta_path.exists()
    release_orphaned = False
    release_status = ""

    if not has_release:
        return {
            "has_release": False,
            "release_status": "",
            "release_orphaned": False,
        }

    try:
        sidecar = json.loads(meta_path.read_text())
        release_status = sidecar.get("status", "unknown")

        # Detect stale "uploading" — no active upload thread
        if release_status == "uploading":
            _fid = sidecar.get("file_id", "")
            try:
                from src.core.services.content_release import (
                    _release_upload_status,
                )

                live = _release_upload_status.get(_fid, {})
                if not live or live.get("status") not in (
                    "uploading",
                    "queued",
                ):
                    release_status = "stale"
            except ImportError:
                release_status = "stale"

        # Orphan check: skip only genuinely active uploads
        if release_status != "uploading":
            asset_name = (
                sidecar.get("old_asset_name")
                or sidecar.get("asset_name")
                or target.name
            )
            from src.core.services.content_release import list_release_assets

            remote = list_release_assets(project_root)
            if remote.get("available"):
                remote_names = {a["name"] for a in remote["assets"]}
                if asset_name not in remote_names:
                    release_orphaned = True
            else:
                # Release tag doesn't exist → sidecar is orphaned
                release_orphaned = True
    except Exception:
        pass

    return {
        "has_release": has_release,
        "release_status": release_status,
        "release_orphaned": release_orphaned,
    }


# ── Save encrypted file (re-encrypt edited content) ────────────


def save_encrypted_content(
    target: Path,
    content: str,
    passphrase: str,
    rel_path: str,
) -> dict[str, object]:
    """Decrypt, re-encrypt with new content, compute diff and audit.

    Args:
        target: Absolute path to the .enc file.
        content: Edited plaintext content.
        passphrase: Encryption passphrase.
        rel_path: Relative path (for audit logging).

    Returns:
        {"success": True, "size": int} on success.

    Raises:
        ValueError: On decryption failure or wrong key.
    """
    import difflib
    import tempfile

    from src.core.services.content_crypto import (
        decrypt_file_to_memory,
        encrypt_file,
    )

    # Decrypt to get old content + metadata
    old_plaintext, meta = decrypt_file_to_memory(target, passphrase)
    original_name = meta["filename"]

    old_text = old_plaintext.decode("utf-8", errors="replace")
    old_size = len(old_plaintext)
    old_lines = old_text.count("\n") + (1 if old_text else 0)

    # Re-encrypt the edited content
    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=Path(original_name).suffix,
        prefix=Path(original_name).stem + "_",
    ) as tmp:
        tmp.write(content.encode("utf-8"))
        tmp_path = Path(tmp.name)

    try:
        encrypt_file(
            tmp_path,
            passphrase,
            output_path=target,
            original_filename=original_name,
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    new_enc_size = target.stat().st_size
    new_size = len(content.encode("utf-8"))
    new_lines = content.count("\n") + (1 if content else 0)

    # Compute unified diff
    old_lines_list = old_text.splitlines()
    new_lines_list = content.splitlines()
    diff_lines = list(
        difflib.unified_diff(
            old_lines_list,
            new_lines_list,
            fromfile=f"a/{rel_path}",
            tofile=f"b/{rel_path}",
            lineterm="",
        )
    )
    added = sum(
        1 for ln in diff_lines if ln.startswith("+") and not ln.startswith("+++")
    )
    removed = sum(
        1 for ln in diff_lines if ln.startswith("-") and not ln.startswith("---")
    )
    diff_text = "\n".join(diff_lines[:50])
    if len(diff_lines) > 50:
        diff_text += f"\n... ({len(diff_lines) - 50} more lines)"

    # Audit
    _audit(
        "📝 File Modified",
        f"{rel_path}: +{added} -{removed} lines"
        f" ({old_size:,} → {new_size:,} bytes, encrypted)",
        action="modified",
        target=rel_path,
        detail={
            "file": rel_path,
            "original_name": original_name,
            "encrypted": True,
            "lines_added": added,
            "lines_removed": removed,
            "diff": diff_text,
        },
        before_state={"lines": old_lines, "size": old_size},
        after_state={"lines": new_lines, "size": new_size, "enc_size": new_enc_size},
    )

    logger.info(
        "Saved encrypted file: %s (%d bytes, +%d -%d lines)",
        rel_path,
        new_size,
        added,
        removed,
    )
    return {"success": True, "size": new_enc_size}
