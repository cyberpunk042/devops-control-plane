"""
Content listing — folder detection, scanning, and file listing.

Detects content folders, scans file metadata, lists folder contents
with encryption status and release artifact tracking.
"""

from __future__ import annotations

from pathlib import Path

from src.core.services.content_crypto import (
    _guess_mime,
    classify_file,
    is_covault_file,
    read_metadata,
)


DEFAULT_CONTENT_DIRS = ["docs", "content", "media", "assets", "archive"]


def detect_content_folders(project_root: Path) -> list[dict]:
    """Auto-detect content folders in a project.

    Checks project.yml for a ``content_folders`` list first.
    Falls back to DEFAULT_CONTENT_DIRS if not configured.

    Returns:
        List of dicts: {name, path, file_count, total_size, categories}
    """
    # Try to load configured folders from project.yml
    dir_names = None
    config_file = project_root / "project.yml"
    if config_file.is_file():
        try:
            import yaml

            raw = config_file.read_text(encoding="utf-8")
            data = yaml.safe_load(raw)
            if isinstance(data, dict):
                configured = data.get("content_folders")
                if isinstance(configured, list) and configured:
                    dir_names = configured
        except Exception:
            pass  # Fall back to defaults

    if dir_names is None:
        dir_names = DEFAULT_CONTENT_DIRS

    folders = []

    for dir_name in dir_names:
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
                        from src.core.services.content_release import _release_upload_status
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
                        from src.core.services.content_release import _release_upload_status
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
