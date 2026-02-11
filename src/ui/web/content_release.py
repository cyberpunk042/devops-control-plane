"""
Content vault — GitHub Release sync for large files.

When a file is placed in a `large/` subfolder (> 2 MB after optimization),
it's gitignored and would be lost if the repo is cloned elsewhere.

This module uploads those files to a GitHub Release (`content-vault` tag)
as assets, and can restore them later.

Functions:
    upload_to_release_bg  — background thread: `gh release upload`
    restore_large_files   — download missing large files from release
    delete_release_asset  — fire-and-forget deletion of a release asset
    get_release_status    — poll upload status for a given file_id
    cancel_release_upload — cancel a running upload

Ported from continuity-orchestrator/src/admin/routes_media_vault.py
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Release tag used for large content file backup
CONTENT_RELEASE_TAG = "content-vault"

# In-memory upload status tracking
# { file_id: { "status": ..., "message": ..., "started_at": ..., "size_mb": ... } }
_release_upload_status: dict[str, dict] = {}
# Active subprocess references for cancellation
_release_active_procs: dict[str, subprocess.Popen] = {}


# ── Sidecar cleanup helper ──────────────────────────────────────


def cleanup_release_sidecar(
    file_path: Path,
    project_root: Path,
) -> bool:
    """Remove a file's .release.json sidecar and its GitHub Release asset.

    Call this whenever deleting a file that might have a release attachment.
    Safe to call even if no sidecar exists — returns False in that case.

    Args:
        file_path: Path to the content/backup file being deleted.
        project_root: Project root (for `gh` CWD).

    Returns:
        True if a sidecar was found and cleaned up.
    """
    import json

    meta_path = file_path.parent / f"{file_path.name}.release.json"
    if not meta_path.exists():
        return False

    try:
        meta = json.loads(meta_path.read_text())
        asset_name = (
            meta.get("old_asset_name")
            or meta.get("asset_name")
            or file_path.name
        )
        delete_release_asset(asset_name, project_root)
    except Exception:
        pass  # best-effort

    meta_path.unlink(missing_ok=True)
    return True


# ── Sidecar helpers ─────────────────────────────────────────


def _update_sidecar(file_path: Path, status: str) -> None:
    """Update the on-disk .release.json sidecar status field."""
    meta_path = file_path.parent / f"{file_path.name}.release.json"
    if not meta_path.exists():
        return
    try:
        import json
        meta = json.loads(meta_path.read_text())
        meta["status"] = status
        meta_path.write_text(json.dumps(meta, indent=2))
    except Exception:
        pass


# ── Upload ──────────────────────────────────────────────────────


def upload_to_release_bg(
    file_id: str,
    file_path: Path,
    project_root: Path,
) -> None:
    """Upload a large file to a GitHub Release in the background.

    Uses the `gh` CLI to attach the file as a release asset to the
    'content-vault' release. Creates the release if it doesn't exist.
    Runs as a daemon thread so progress can be tracked and cancelled.

    Args:
        file_id: Unique identifier for this upload (used for status tracking)
        file_path: Absolute path to the file to upload
        project_root: Project root directory (for `gh` CWD)
    """
    if not shutil.which("gh"):
        logger.warning("[content-release] gh CLI not found — skipping release upload")
        _release_upload_status[file_id] = {
            "status": "failed",
            "message": "gh CLI not installed",
        }
        return

    if not file_path.exists():
        _release_upload_status[file_id] = {
            "status": "failed",
            "message": f"File not found: {file_path.name}",
        }
        return

    size_mb = file_path.stat().st_size / (1024 * 1024)

    _release_upload_status[file_id] = {
        "status": "pending",
        "message": f"Queued ({size_mb:.1f} MB)",
        "started_at": time.time(),
        "size_mb": round(size_mb, 1),
    }

    def _do_upload() -> None:
        proc = None
        try:
            # Check if cancelled before starting
            if _release_upload_status.get(file_id, {}).get("status") == "cancelled":
                return

            _release_upload_status[file_id].update({
                "status": "uploading",
                "message": "Ensuring release exists...",
                "phase": "setup",
                "progress_pct": 0,
            })

            # Step 1: Ensure release exists
            check = subprocess.run(
                ["gh", "release", "view", CONTENT_RELEASE_TAG],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if _release_upload_status.get(file_id, {}).get("status") == "cancelled":
                return

            if check.returncode != 0:
                _release_upload_status[file_id]["message"] = "Creating release..."
                create = subprocess.run(
                    [
                        "gh", "release", "create", CONTENT_RELEASE_TAG,
                        "--title", "Content Vault",
                        "--notes",
                        "Large content files. Auto-managed by the admin panel.",
                        "--latest=false",
                    ],
                    cwd=str(project_root),
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if create.returncode != 0:
                    raise RuntimeError(
                        f"Failed to create release: {create.stderr[:200]}"
                    )

            if _release_upload_status.get(file_id, {}).get("status") == "cancelled":
                return

            # Step 2: Upload asset (Popen so we can kill on cancel)
            upload_start = time.time()
            _release_upload_status[file_id].update({
                "message": f"Uploading {size_mb:.1f} MB...",
                "phase": "uploading",
                "upload_started_at": upload_start,
                "progress_pct": 2,
            })
            logger.info(
                "[content-release] Uploading %s (%s, %.1f MB)...",
                file_id,
                file_path.name,
                size_mb,
            )

            proc = subprocess.Popen(
                [
                    "gh", "release", "upload", CONTENT_RELEASE_TAG,
                    str(file_path), "--clobber",
                ],
                cwd=str(project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            _release_active_procs[file_id] = proc

            # Poll subprocess for completion while updating progress
            # (gh CLI doesn't output progress, so estimate from elapsed time)
            # Assume ~2 MB/s upload speed for estimation
            assumed_speed_mbps = 2.0
            estimated_total_sec = max(size_mb / assumed_speed_mbps, 5)

            while proc.poll() is None:
                # Check for cancellation
                if _release_upload_status.get(file_id, {}).get("status") == "cancelled":
                    proc.kill()
                    _release_active_procs.pop(file_id, None)
                    return

                elapsed = time.time() - upload_start
                # Estimate progress (cap at 95% — we only know it's done when proc exits)
                est_pct = min(95, int((elapsed / estimated_total_sec) * 100))

                # Compute speed estimate based on elapsed time
                if elapsed > 2:
                    speed_str = f"{size_mb / elapsed:.1f} MB/s est."
                else:
                    speed_str = "starting..."

                eta_sec = max(0, estimated_total_sec - elapsed)
                if eta_sec > 60:
                    eta_str = f"~{int(eta_sec / 60)}m {int(eta_sec % 60)}s left"
                elif eta_sec > 5:
                    eta_str = f"~{int(eta_sec)}s left"
                else:
                    eta_str = "almost done..."

                _release_upload_status[file_id].update({
                    "message": f"Uploading {size_mb:.1f} MB… {est_pct}%",
                    "progress_pct": est_pct,
                    "elapsed_sec": round(elapsed, 1),
                    "speed": speed_str,
                    "eta": eta_str,
                })

                time.sleep(1)

            # Process exited — get output
            stdout, stderr = proc.communicate(timeout=5)
            _release_active_procs.pop(file_id, None)

            # Check if we were cancelled while waiting
            if _release_upload_status.get(file_id, {}).get("status") == "cancelled":
                return

            elapsed = time.time() - _release_upload_status[file_id].get(
                "started_at", time.time()
            )

            if proc.returncode == 0:
                speed = size_mb / elapsed if elapsed > 0 else 0
                _release_upload_status[file_id] = {
                    "status": "done",
                    "message": f"Uploaded in {elapsed:.0f}s ({speed:.1f} MB/s)",
                    "progress_pct": 100,
                    "elapsed_sec": round(elapsed, 1),
                }
                # Update sidecar on disk → status: done
                _update_sidecar(file_path, "done")
                logger.info(
                    "[content-release] ✅ %s uploaded (%s, %.1f MB, %.0fs)",
                    file_id,
                    file_path.name,
                    size_mb,
                    elapsed,
                )
            else:
                err = (
                    stderr.decode(errors="replace")[:300]
                    if stderr
                    else "unknown error"
                )
                _release_upload_status[file_id] = {
                    "status": "failed",
                    "message": f"gh upload failed: {err}",
                    "progress_pct": 0,
                }
                _update_sidecar(file_path, "failed")
                logger.warning(
                    "[content-release] ❌ %s failed: %s", file_id, err
                )

        except subprocess.TimeoutExpired:
            _release_active_procs.pop(file_id, None)
            if proc and proc.poll() is None:
                proc.kill()
            _release_upload_status[file_id] = {
                "status": "failed",
                "message": "Upload timed out (>1 hour)",
                "progress_pct": 0,
            }
            _update_sidecar(file_path, "failed")
            logger.warning("[content-release] ❌ %s timed out", file_id)

        except Exception as e:
            _release_active_procs.pop(file_id, None)
            _release_upload_status[file_id] = {
                "status": "failed",
                "message": str(e),
                "progress_pct": 0,
            }
            _update_sidecar(file_path, "failed")
            logger.error(
                "[content-release] ❌ %s error: %s", file_id, e, exc_info=True
            )

    logger.info("[content-release] Queueing background upload: %s", file_id)
    thread = threading.Thread(
        target=_do_upload, name=f"release-{file_id}", daemon=True
    )
    thread.start()


# ── Status / Cancel ─────────────────────────────────────────────


def get_release_status(file_id: str) -> dict | None:
    """Get the upload status for a given file_id."""
    return _release_upload_status.get(file_id)


def get_all_release_statuses() -> dict:
    """Get all tracked upload statuses."""
    return dict(_release_upload_status)


def cancel_release_upload(file_id: str) -> dict:
    """Cancel a running release upload."""
    status = _release_upload_status.get(file_id)
    if not status:
        return {"success": False, "message": "No upload tracked"}

    if status.get("status") in ("done", "failed", "cancelled"):
        return {"success": True, "message": f"Already {status['status']}"}

    # Mark as cancelled
    _release_upload_status[file_id] = {
        "status": "cancelled",
        "message": "Cancelled by user",
    }

    # Kill active subprocess if running
    proc = _release_active_procs.pop(file_id, None)
    if proc and proc.poll() is None:
        proc.kill()
        logger.info(
            "[content-release] Killed upload process for %s", file_id
        )

    logger.info("[content-release] ⚠️ %s cancelled by user", file_id)
    return {"success": True, "message": "Upload cancelled"}


# ── Restore ─────────────────────────────────────────────────────


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


# ── Release asset inventory ─────────────────────────────────────


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

        import json

        # Each line is a JSON object
        assets = []
        for line in proc.stdout.strip().splitlines():
            line = line.strip()
            if line:
                try:
                    assets.append(json.loads(line))
                except json.JSONDecodeError:
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
    import json as _json

    # 1. Fetch remote assets
    remote = list_release_assets(project_root)
    remote_names: set[str] = set()
    if remote.get("available"):
        remote_names = {a["name"] for a in remote["assets"]}

    # 2. Scan local sidecars
    local_sidecars: list[dict] = []

    # Scan content dirs + backup dirs for .release.json files
    from .content_crypto import DEFAULT_CONTENT_DIRS

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


# ── Delete ──────────────────────────────────────────────────────


def delete_release_asset(
    asset_name: str,
    project_root: Path,
) -> None:
    """Delete a content asset from the GitHub Release (fire-and-forget)."""
    if not shutil.which("gh"):
        return

    try:
        subprocess.Popen(
            [
                "gh", "release", "delete-asset", CONTENT_RELEASE_TAG,
                asset_name, "--yes",
            ],
            cwd=str(project_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info(
            "[content-release] Queued asset deletion: %s", asset_name
        )
    except Exception as e:
        logger.warning("[content-release] Could not delete asset: %s", e)
