"""
Content crypto ops — high-level encrypt/decrypt with side-effects.

Orchestrates encryption/decryption + side-effects (delete original,
update release artifacts, audit) so routes stay thin.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.core.services.content_crypto import encrypt_file, decrypt_file
from src.core.services.audit_helpers import make_auditor

logger = logging.getLogger(__name__)
_audit = make_auditor("content")


def encrypt_content_file(
    project_root: Path,
    rel_path: str,
    passphrase: str,
    *,
    delete_original: bool = False,
) -> dict:
    """Encrypt a content file and handle all side-effects.

    Orchestrates: encrypt → optionally delete original → update release
    artifact if in .large/ → audit.

    Args:
        project_root: Project root directory.
        rel_path: Relative path to the source file.
        passphrase: Encryption passphrase.
        delete_original: Whether to delete the plaintext after encryption.

    Returns:
        Dict with success info, sizes, and flags.
    """
    import json
    from datetime import datetime, timezone

    source = (project_root / rel_path).resolve()

    # Security: ensure path is within project
    try:
        source.relative_to(project_root)
    except ValueError:
        return {"error": "Invalid path"}

    if not source.is_file():
        return {"error": f"File not found: {rel_path}"}

    if not passphrase:
        return {"error": "CONTENT_VAULT_ENC_KEY is not set in .env", "needs_key": True}

    try:
        output = encrypt_file(source, passphrase)
        result: dict = {
            "success": True,
            "source": rel_path,
            "output": str(output.relative_to(project_root)),
            "original_size": source.stat().st_size,
            "encrypted_size": output.stat().st_size,
        }

        if delete_original:
            source.unlink()
            result["original_deleted"] = True

        # Update release artifact if file is in .large/
        if ".large" in source.parts:
            from src.core.services.content_release import (
                cleanup_release_sidecar,
                upload_to_release_bg,
            )
            cleanup_release_sidecar(source, project_root)
            file_id = output.stem
            upload_to_release_bg(file_id, output, project_root)
            new_meta = output.parent / f"{output.name}.release.json"
            new_meta.write_text(json.dumps({
                "file_id": file_id,
                "asset_name": output.name,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "status": "uploading",
            }, indent=2))
            result["release_updated"] = True

        _audit(
            "🔒 File Encrypted",
            f"{rel_path} encrypted ({result['original_size']:,} → "
            f"{result['encrypted_size']:,} bytes)"
            + (" — original deleted" if delete_original else ""),
            action="encrypted",
            target=rel_path,
            before_state={"size": result["original_size"]},
            after_state={"size": result["encrypted_size"], "encrypted": True},
        )
        return result

    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.exception("Failed to encrypt %s", rel_path)
        _audit(
            "❌ Encrypt Failed",
            f"{rel_path}: {e}",
            detail={"file": rel_path, "error": str(e)},
        )
        return {"error": f"Encryption failed: {e}", "_status": 500}


def decrypt_content_file(
    project_root: Path,
    rel_path: str,
    passphrase: str,
    *,
    delete_encrypted: bool = False,
) -> dict:
    """Decrypt a content file and handle all side-effects.

    Orchestrates: decrypt → optionally delete encrypted → update release
    artifact if in .large/ → audit.

    Args:
        project_root: Project root directory.
        rel_path: Relative path to the .enc file.
        passphrase: Decryption passphrase.
        delete_encrypted: Whether to delete the .enc after decryption.

    Returns:
        Dict with success info, sizes, and flags.
    """
    import json
    from datetime import datetime, timezone

    vault_file = (project_root / rel_path).resolve()

    # Security: ensure path is within project
    try:
        vault_file.relative_to(project_root)
    except ValueError:
        return {"error": "Invalid path"}

    if not vault_file.is_file():
        return {"error": f"File not found: {rel_path}"}

    if not passphrase:
        return {"error": "CONTENT_VAULT_ENC_KEY is not set in .env", "needs_key": True}

    try:
        output = decrypt_file(vault_file, passphrase)
        result: dict = {
            "success": True,
            "source": rel_path,
            "output": str(output.relative_to(project_root)),
            "decrypted_size": output.stat().st_size,
        }

        if delete_encrypted:
            vault_file.unlink()
            result["encrypted_deleted"] = True

        # Update release artifact if file is in .large/
        if ".large" in vault_file.parts:
            from src.core.services.content_release import (
                cleanup_release_sidecar,
                upload_to_release_bg,
            )
            cleanup_release_sidecar(vault_file, project_root)
            file_id = output.stem
            upload_to_release_bg(file_id, output, project_root)
            new_meta = output.parent / f"{output.name}.release.json"
            new_meta.write_text(json.dumps({
                "file_id": file_id,
                "asset_name": output.name,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "status": "uploading",
            }, indent=2))
            result["release_updated"] = True

        _audit(
            "🔓 File Decrypted",
            f"{rel_path} decrypted ({result['decrypted_size']:,} bytes)"
            + (" — encrypted copy deleted" if delete_encrypted else ""),
            action="decrypted",
            target=rel_path,
            before_state={"encrypted": True},
            after_state={"size": result["decrypted_size"], "encrypted": False},
        )
        return result

    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.exception("Failed to decrypt %s", rel_path)
        _audit(
            "❌ Decrypt Failed",
            f"{rel_path}: {e}",
            detail={"file": rel_path, "error": str(e)},
        )
        return {"error": f"Decryption failed: {e}", "_status": 500}
