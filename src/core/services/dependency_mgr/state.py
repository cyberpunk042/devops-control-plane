"""
State layer — snapshots, notes, and atomic JSON persistence.

Snapshots are pre-operation backups of manifest and lock files,
stored in ``.state/dependency_snapshots/<timestamp>/``.
Restored on rollback.

Notes are user annotations on package versions (e.g. "Staying on
celery 5.3.6 because kombu compat").  Stored in a single JSON file:
``.state/dependency_notes.json``.

Follows the project's existing ``.state/`` patterns:
  - ``notifications.py``: simple JSON load/save
  - ``mediator/persistence.py``: atomic tmp+rename for critical data
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Snapshot

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════
#  Constants
# ═════════════════════════════════════════════════════════════════

SNAPSHOT_DIR = ".state/dependency_snapshots"
NOTES_FILE = ".state/dependency_notes.json"
MAX_SNAPSHOTS = 10


# ═════════════════════════════════════════════════════════════════
#  Atomic JSON I/O
# ═════════════════════════════════════════════════════════════════


def _atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON atomically — tmp file + rename.

    Same pattern as ``mediator/persistence.py:persist_node()``.
    Never corrupts on crash.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        tmp.rename(path)
    except Exception:
        # Clean up tmp on failure
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def _load_json(path: Path) -> Any:
    """Load a JSON file.  Returns ``None`` if missing or corrupt."""
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError) as exc:
        logger.warning("Failed to load %s: %s", path, exc)
        return None


# ═════════════════════════════════════════════════════════════════
#  Snapshots
# ═════════════════════════════════════════════════════════════════


def create_snapshot(
    project_root: Path,
    scope: str,
    ecosystems: list[str],
    files_to_snap: list[Path],
) -> Snapshot:
    """Backup files before an operation.

    Creates a timestamped directory under ``.state/dependency_snapshots/``,
    copies each file, and writes a ``manifest.json``.
    Auto-prunes oldest snapshots beyond ``MAX_SNAPSHOTS``.

    Args:
        project_root: Project root (absolute).
        scope: TreeNode.id that triggered the operation.
        ecosystems: Ecosystem IDs included in this snapshot.
        files_to_snap: Absolute paths to manifest/lock files to backup.

    Returns:
        ``Snapshot`` record describing what was backed up.
    """
    snap_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    snap_dir = project_root / SNAPSHOT_DIR / snap_id
    snap_dir.mkdir(parents=True, exist_ok=True)

    file_pairs: list[tuple[str, str]] = []

    for src_abs in files_to_snap:
        if not src_abs.is_file():
            continue
        # Relative path from project root for the original
        try:
            rel = src_abs.relative_to(project_root)
        except ValueError:
            continue

        # Mirror the directory structure inside the snapshot
        dst = snap_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_abs, dst)
        file_pairs.append((str(rel), str(rel)))

    snapshot = Snapshot(
        id=snap_id,
        ts=time.time(),
        operation="",  # Caller sets this — we don't know install vs update here
        scope=scope,
        ecosystems=tuple(ecosystems),
        files=tuple(file_pairs),
    )

    # Write manifest
    _atomic_write_json(snap_dir / "manifest.json", snapshot.to_dict())

    # Auto-prune
    prune_snapshots(project_root)

    logger.debug("Snapshot created: %s (%d files)", snap_id, len(file_pairs))
    return snapshot


def restore_snapshot(project_root: Path, snapshot_id: str) -> Snapshot | None:
    """Restore files from a snapshot to their original locations.

    Copies backed-up files back to the project root.
    Does NOT run any install command — the caller handles that
    via ``adapter.restore_cmd()``.

    Returns:
        The ``Snapshot`` record, or ``None`` if not found.
    """
    snap_dir = project_root / SNAPSHOT_DIR / snapshot_id
    manifest_path = snap_dir / "manifest.json"

    data = _load_json(manifest_path)
    if data is None:
        logger.warning("Snapshot not found: %s", snapshot_id)
        return None

    snapshot = Snapshot.from_dict(data)

    for src_rel, _dst_rel in snapshot.files:
        backed_up = snap_dir / src_rel
        original = project_root / src_rel
        if backed_up.is_file():
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backed_up, original)
            logger.debug("Restored: %s", src_rel)

    return snapshot


def list_snapshots(project_root: Path) -> list[Snapshot]:
    """List available snapshots, newest first."""
    snap_root = project_root / SNAPSHOT_DIR
    if not snap_root.is_dir():
        return []

    snapshots: list[Snapshot] = []
    for child in sorted(snap_root.iterdir(), reverse=True):
        if not child.is_dir():
            continue
        manifest = child / "manifest.json"
        data = _load_json(manifest)
        if data is not None:
            try:
                snapshots.append(Snapshot.from_dict(data))
            except Exception:
                logger.debug("Skipping corrupt snapshot: %s", child.name)

    return snapshots


def prune_snapshots(project_root: Path) -> int:
    """Remove snapshots beyond ``MAX_SNAPSHOTS``.  Returns count removed."""
    snap_root = project_root / SNAPSHOT_DIR
    if not snap_root.is_dir():
        return 0

    dirs = sorted(
        [d for d in snap_root.iterdir() if d.is_dir()],
        key=lambda d: d.name,
        reverse=True,
    )

    removed = 0
    for old_dir in dirs[MAX_SNAPSHOTS:]:
        try:
            shutil.rmtree(old_dir)
            removed += 1
            logger.debug("Pruned snapshot: %s", old_dir.name)
        except Exception as exc:
            logger.warning("Failed to prune %s: %s", old_dir.name, exc)

    return removed


# ═════════════════════════════════════════════════════════════════
#  Notes
# ═════════════════════════════════════════════════════════════════


def _notes_path(project_root: Path) -> Path:
    return project_root / NOTES_FILE


def _load_notes(project_root: Path) -> dict[str, dict[str, Any]]:
    """Load all notes from disk.

    Returns:
        Dict keyed by ``'{ecosystem}:{package}:{version}'``.
    """
    data = _load_json(_notes_path(project_root))
    if isinstance(data, dict):
        return data
    return {}


def _save_notes(project_root: Path, notes: dict[str, dict[str, Any]]) -> None:
    """Write all notes to disk (atomic)."""
    _atomic_write_json(_notes_path(project_root), notes)


def _note_key(ecosystem: str, package: str, version: str) -> str:
    """Build the dict key for a note."""
    return f"{ecosystem}:{package}:{version}"


def get_notes(project_root: Path) -> dict[str, dict[str, Any]]:
    """Load all notes.  Key format: ``'{ecosystem}:{package}:{version}'``."""
    return _load_notes(project_root)


def get_active_notes(project_root: Path) -> dict[str, dict[str, Any]]:
    """Notes that haven't expired (``dismiss_until`` not yet passed).

    Expired notes are still in the file — they just don't suppress
    warnings anymore.
    """
    now = time.time()
    active: dict[str, dict[str, Any]] = {}
    for key, note in _load_notes(project_root).items():
        dismiss_until = note.get("dismiss_until")
        if dismiss_until:
            try:
                # Parse ISO date → epoch
                from datetime import datetime as _dt
                dt = _dt.fromisoformat(dismiss_until)
                if dt.timestamp() < now:
                    continue  # Expired
            except (ValueError, TypeError):
                pass
        active[key] = note
    return active


def set_note(
    project_root: Path,
    ecosystem: str,
    package: str,
    version: str,
    note: str,
    dismiss_until: str | None = None,
) -> None:
    """Add or update a note on a package version.

    Args:
        project_root: Project root.
        ecosystem: Ecosystem ID (e.g. ``'pip'``).
        package: Package name.
        version: Package version the note applies to.
        note: User's note text.
        dismiss_until: Optional ISO date — note auto-expires after this.
    """
    notes = _load_notes(project_root)
    key = _note_key(ecosystem, package, version)
    notes[key] = {
        "note": note,
        "author": "user",
        "ts": datetime.now(timezone.utc).isoformat(),
        "dismiss_until": dismiss_until,
        "status": "acknowledged",
    }
    _save_notes(project_root, notes)


def remove_note(
    project_root: Path,
    ecosystem: str,
    package: str,
    version: str,
) -> bool:
    """Remove a note.  Returns ``True`` if it existed."""
    notes = _load_notes(project_root)
    key = _note_key(ecosystem, package, version)
    if key not in notes:
        return False
    del notes[key]
    _save_notes(project_root, notes)
    return True
