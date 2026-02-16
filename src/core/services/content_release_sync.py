"""
Content vault — restore & inventory for GitHub Release assets.

Extracted from content_release.py. Handles:
- restore_large_files: download missing large files from release
- list_release_assets: fetch remote asset list
- release_inventory: cross-reference local sidecars with remote

Channel-independent.
"""

from __future__ import annotations

import json as _json
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Release tag — shared constant (must match content_release.py)
CONTENT_RELEASE_TAG = "content-vault"


# ═══════════════════════════════════════════════════════════════════
#  Restore
# ═══════════════════════════════════════════════════════════════════


def restore_large_files(project_root: Path) -> dict:
    """Download missing large files from the 'content-vault' GitHub Release.

    Scans all content folders for `large/` subdirectories and checks
    whether each file exists locally. Uses `gh release download` to
    restore missing assets.

    Returns:
        Dict with 'restored', 'failed', 'skipped', 'already_present' lists
        and 'gh_available' bool.
    """
    result: dict = {
        "gh_available": bool(shutil.which("gh")),
        "restored": [],
        "failed": [],
        "already_present": [],
    }

    if not result["gh_available"]:
        logger.warning("[content-restore] gh CLI not found — cannot restore")
        return result

    # Find all large/ directories under the project
    content_dirs = list(project_root.glob("**/.large"))
    for large_dir in content_dirs:
        if not large_dir.is_dir():
            continue

        for asset_file in large_dir.iterdir():
            if asset_file.name == ".gitignore" or asset_file.is_dir():
                continue
            result["already_present"].append(str(asset_file.name))

    # Try to download assets from the release that we don't have locally
    try:
        # List release assets
        list_proc = subprocess.run(
            [
                "gh", "release", "view", CONTENT_RELEASE_TAG,
                "--json", "assets",
                "--jq", ".[].name",
            ],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if list_proc.returncode != 0:
            logger.warning(
                "[content-restore] Release '%s' not found or gh error",
                CONTENT_RELEASE_TAG,
            )
            return result

        remote_assets = [
            a.strip() for a in list_proc.stdout.strip().split("\n") if a.strip()
        ]

        for asset_name in remote_assets:
            if asset_name in result["already_present"]:
                continue

            # Download to the first large/ directory we find
            # (or create one in content/)
            if content_dirs:
                target_dir = content_dirs[0]
            else:
                target_dir = project_root / "content" / ".large"
                target_dir.mkdir(parents=True, exist_ok=True)

            try:
                dl_proc = subprocess.run(
                    [
                        "gh", "release", "download", CONTENT_RELEASE_TAG,
                        "--pattern", asset_name,
                        "--dir", str(target_dir),
                        "--clobber",
                    ],
                    cwd=str(project_root),
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if dl_proc.returncode == 0:
                    result["restored"].append(asset_name)
                    logger.info(
                        "[content-restore] Restored %s from release", asset_name
                    )
                else:
                    result["failed"].append({
                        "name": asset_name,
                        "error": dl_proc.stderr.strip()[:200] or "Download failed",
                    })
                    logger.warning(
                        "[content-restore] Failed to restore %s: %s",
                        asset_name,
                        dl_proc.stderr.strip()[:100],
                    )
            except subprocess.TimeoutExpired:
                result["failed"].append({
                    "name": asset_name,
                    "error": "Download timed out (300s)",
                })

    except Exception as e:
        logger.error("[content-restore] Error during restore: %s", e)

    return result


# ═══════════════════════════════════════════════════════════════════
#  Release asset inventory
# ═══════════════════════════════════════════════════════════════════


def list_release_assets(project_root: Path) -> dict:
    """Fetch the list of assets currently on the content-vault release.

    Returns:
        {"available": True, "assets": [{"name": ..., "size": ...}, ...]}
        or {"available": False, "error": "..."}
    """
    if not shutil.which("gh"):
        return {"available": False, "error": "gh CLI not installed"}

    try:
        proc = subprocess.run(
            [
                "gh", "release", "view", CONTENT_RELEASE_TAG,
                "--json", "assets",
                "--jq", '.assets[] | {name: .name, size: .size}',
            ],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            return {
                "available": False,
                "error": f"Release '{CONTENT_RELEASE_TAG}' not found",
            }

        # Each line is a JSON object
        assets = []
        for line in proc.stdout.strip().splitlines():
            line = line.strip()
            if line:
                try:
                    assets.append(_json.loads(line))
                except _json.JSONDecodeError:
                    pass

        return {"available": True, "assets": assets}

    except subprocess.TimeoutExpired:
        return {"available": False, "error": "gh timed out"}
    except Exception as e:
        return {"available": False, "error": str(e)}


def release_inventory(project_root: Path) -> dict:
    """Cross-reference local release sidecars with actual GitHub assets.

    Scans all content folders for `.release.json` sidecars and compares
    with the remote asset list to find:
    - **orphaned**: local sidecar exists but GitHub asset is missing
      (someone manually deleted the release asset)
    - **synced**: local sidecar exists and GitHub asset exists
    - **extra_remote**: GitHub asset exists but no local sidecar
      (could be from another workflow or manual upload)

    Returns:
        {
            "gh_available": bool,
            "remote_assets": ["name", ...],
            "local_sidecars": [{"name": ..., "path": ..., "asset_name": ...}, ...],
            "orphaned": [{"name": ..., "path": ..., "asset_name": ...}, ...],
            "synced": [{"name": ..., "asset_name": ...}, ...],
            "extra_remote": ["name", ...],
        }
    """
    # 1. Fetch remote assets
    remote = list_release_assets(project_root)
    remote_names: set[str] = set()
    if remote.get("available"):
        remote_names = {a["name"] for a in remote["assets"]}

    # 2. Scan local sidecars
    local_sidecars: list[dict] = []

    # Scan content dirs + backup dirs for .release.json files
    from src.core.services.content_crypto import DEFAULT_CONTENT_DIRS

    scan_dirs = [project_root / d for d in DEFAULT_CONTENT_DIRS]
    # Also check backup directories (they live under .backup/)
    for d in scan_dirs[:]:
        backup_dir = d / ".backup"
        if backup_dir.is_dir():
            scan_dirs.append(backup_dir)

    for scan_dir in scan_dirs:
        if not scan_dir.is_dir():
            continue
        for meta_file in scan_dir.rglob("*.release.json"):
            try:
                meta = _json.loads(meta_file.read_text())
                # The file this sidecar refers to
                ref_name = meta_file.name.replace(".release.json", "")
                asset_name = (
                    meta.get("old_asset_name")
                    or meta.get("asset_name")
                    or ref_name
                )
                local_sidecars.append({
                    "name": ref_name,
                    "path": str(meta_file.relative_to(project_root)),
                    "asset_name": asset_name,
                    "meta": meta,
                })
            except Exception:
                pass

    # 3. Cross-reference
    sidecar_asset_names: set[str] = {s["asset_name"] for s in local_sidecars}

    orphaned = [
        s for s in local_sidecars if s["asset_name"] not in remote_names
    ]
    synced = [
        s for s in local_sidecars if s["asset_name"] in remote_names
    ]
    extra_remote = sorted(remote_names - sidecar_asset_names)

    return {
        "gh_available": remote.get("available", False),
        "remote_assets": sorted(remote_names),
        "local_sidecars": local_sidecars,
        "orphaned": orphaned,
        "synced": synced,
        "extra_remote": extra_remote,
    }
