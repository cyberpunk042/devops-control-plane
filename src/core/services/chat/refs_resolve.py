"""
Chat @-reference resolution — look up entity metadata for parsed references.

Given a parsed reference string like ``@run:run_123``, this module resolves
it by looking up the referenced entity (run, thread, trace, commit, branch,
audit, release, code file) and returning structured metadata.

Each entity type has its own internal resolver function that knows how to
find and describe that entity.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.core.services.chat.refs_parse import parse_ref_parts

logger = logging.getLogger(__name__)


def resolve_ref(ref: str, project_root: Path) -> dict | None:
    """Resolve an @-reference to entity metadata.

    Args:
        ref: Reference string like "@run:run_123".
        project_root: Repository root.

    Returns:
        Dict with entity metadata, or None if not found.
        Always includes "type", "id", and "exists" keys.
    """
    parts = parse_ref_parts(ref)
    if parts is None:
        return None

    ref_type, ref_id = parts

    _resolvers = {
        "run": _resolve_run,
        "thread": _resolve_thread,
        "trace": _resolve_trace,
        "commit": _resolve_commit,
        "branch": _resolve_branch,
        "audit": _resolve_audit,
        "release": _resolve_release,
        "code": _resolve_code,
    }

    if ref_type == "user":
        return {"type": "user", "id": ref_id, "exists": True, "name": ref_id}

    resolver = _resolvers.get(ref_type)
    if resolver is None:
        return None
    return resolver(ref_id, project_root)


# ═══════════════════════════════════════════════════════════════════════
#  Internal resolvers
# ═══════════════════════════════════════════════════════════════════════


def _resolve_run(run_id: str, project_root: Path) -> dict | None:
    """Resolve a run reference from local ephemeral storage."""
    try:
        from src.core.services.run_tracker import get_run_local
        run = get_run_local(project_root, run_id)
        if run is None:
            return {"type": "run", "id": run_id, "exists": False}
        return {
            "type": "run",
            "id": run_id,
            "exists": True,
            "run_type": run.get("type", ""),
            "subtype": run.get("subtype", ""),
            "summary": run.get("summary", ""),
            "status": run.get("status", ""),
            "started_at": run.get("started_at", ""),
            "ended_at": run.get("ended_at", ""),
            "duration_ms": run.get("duration_ms", 0),
            "code_ref": (run.get("code_ref") or "")[:12],
        }
    except Exception as e:
        logger.debug("Failed to resolve run %s: %s", run_id, e)
        return {"type": "run", "id": run_id, "exists": False}


def _resolve_thread(thread_id: str, project_root: Path) -> dict | None:
    """Resolve a thread reference."""
    try:
        from src.core.services.chat.chat_ops import list_threads
        threads = list_threads(project_root)
        found = next((t for t in threads if t.thread_id == thread_id), None)
        if found is None:
            return {"type": "thread", "id": thread_id, "exists": False}
        return {
            "type": "thread",
            "id": thread_id,
            "exists": True,
            "title": found.title,
            "created_at": found.created_at,
            "created_by": found.created_by,
        }
    except Exception as e:
        logger.debug("Failed to resolve thread %s: %s", thread_id, e)
        return {"type": "thread", "id": thread_id, "exists": False}


def _resolve_trace(trace_id: str, project_root: Path) -> dict | None:
    """Resolve a trace reference."""
    try:
        from src.core.services.trace.trace_recorder import get_trace
        trace = get_trace(project_root, trace_id)
        if trace is None:
            return {"type": "trace", "id": trace_id, "exists": False}
        return {
            "type": "trace",
            "id": trace_id,
            "exists": True,
            "name": trace.name,
            "classification": trace.classification,
            "started_at": trace.started_at,
            "auto_summary": trace.auto_summary,
        }
    except Exception as e:
        logger.debug("Failed to resolve trace %s: %s", trace_id, e)
        return {"type": "trace", "id": trace_id, "exists": False}


def _resolve_commit(commit_ref: str, project_root: Path) -> dict | None:
    """Resolve a commit reference (full or short hash)."""
    try:
        import subprocess
        r = subprocess.run(
            ["git", "-C", str(project_root), "log", "-1",
             "--format=%H%n%h%n%s%n%an%n%aI", commit_ref],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return {"type": "commit", "id": commit_ref, "exists": False}
        lines = r.stdout.strip().splitlines()
        if len(lines) < 5:
            return {"type": "commit", "id": commit_ref, "exists": False}
        return {
            "type": "commit",
            "id": commit_ref,
            "exists": True,
            "hash": lines[0],
            "short_hash": lines[1],
            "message": lines[2],
            "author": lines[3],
            "date": lines[4],
        }
    except Exception as e:
        logger.debug("Failed to resolve commit %s: %s", commit_ref, e)
        return {"type": "commit", "id": commit_ref, "exists": False}


def _resolve_branch(branch_name: str, project_root: Path) -> dict | None:
    """Resolve a branch reference."""
    try:
        import subprocess
        r = subprocess.run(
            ["git", "-C", str(project_root), "rev-parse", "--verify",
             f"refs/heads/{branch_name}"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return {"type": "branch", "id": branch_name, "exists": False}
        return {
            "type": "branch",
            "id": branch_name,
            "exists": True,
            "sha": r.stdout.strip(),
        }
    except Exception as e:
        logger.debug("Failed to resolve branch %s: %s", branch_name, e)
        return {"type": "branch", "id": branch_name, "exists": False}


def _resolve_audit(operation_id: str, project_root: Path) -> dict | None:
    """Resolve an audit reference by ID.

    Resolution order:
      1. Saved scan snapshots on the ledger branch (``.ledger/audits/``)
      2. Execution log (``.state/audit.ndjson``)

    This ensures saved audits (Phase 1) are preferred while maintaining
    backward compatibility with pre-existing execution-log references.
    """
    # ── 1. Try ledger branch (saved scan snapshots) ─────────────
    try:
        from src.core.services.ledger.ledger_ops import get_saved_audit
        snapshot = get_saved_audit(project_root, operation_id)
        if snapshot is not None:
            # Return the full snapshot — every field, no stripping
            snapshot["type"] = "audit"
            snapshot["id"] = operation_id
            snapshot["exists"] = True
            snapshot["source"] = "ledger"
            snapshot["timestamp"] = snapshot.get("iso")
            return snapshot
    except Exception as e:
        logger.debug("Ledger audit lookup failed for %s: %s", operation_id, e)

    # ── 2. Try pending (unsaved) snapshots ──────────────────────
    try:
        from src.core.services.audit_staging import get_pending
        snap = get_pending(project_root, operation_id)
        if snap is not None:
            snap["type"] = "audit"
            snap["id"] = operation_id
            snap["exists"] = True
            snap["source"] = "pending"
            snap["timestamp"] = snap.get("iso")
            return snap
    except Exception as e:
        logger.debug("Pending audit lookup failed for %s: %s", operation_id, e)

    # ── 3. Fall back to execution log (existing behavior) ───────
    try:
        from src.core.persistence.audit import AuditWriter
        writer = AuditWriter(project_root=project_root)
        entries = writer.read_all()
        found = next((e for e in entries if e.operation_id == operation_id), None)
        if found is None:
            return {"type": "audit", "id": operation_id, "exists": False}
        return {
            "type": "audit",
            "id": operation_id,
            "exists": True,
            "source": "ndjson",
            "operation_type": found.operation_type,
            "status": found.status,
            "timestamp": found.timestamp,
            "automation": found.automation,
        }
    except Exception as e:
        logger.debug("Failed to resolve audit %s: %s", operation_id, e)
        return {"type": "audit", "id": operation_id, "exists": False}


def _resolve_release(ref_id: str, project_root: Path) -> dict | None:
    """Resolve a release reference.

    ref_id format: "tag_name/asset_name" (e.g. "content-vault/ADAPTERS.md")
    or just "tag_name" for the release itself.
    """
    if "/" in ref_id:
        tag_name, asset_name = ref_id.split("/", 1)
    else:
        tag_name = ref_id
        asset_name = None

    try:
        from src.core.services.content.release_sync import list_release_assets
        data = list_release_assets(project_root)
    except Exception as e:
        logger.debug("Failed to resolve release %s: %s", ref_id, e)
        return {"type": "release", "id": ref_id, "exists": False,
                "error": str(e)}

    if not data.get("available"):
        return {"type": "release", "id": ref_id, "exists": False,
                "error": data.get("error", "Release unavailable")}

    # If no specific asset, return release-level info
    if not asset_name:
        return {
            "type": "release", "id": ref_id, "exists": True,
            "tag": tag_name,
            "asset_count": len(data.get("assets", [])),
        }

    # Find the specific asset
    for asset in data.get("assets", []):
        if asset.get("name") == asset_name:
            # Search for local copy via .release.json sidecars
            local_path = ""
            import json as _json_
            for sidecar in project_root.rglob(f"{asset_name}.release.json"):
                try:
                    meta = _json_.loads(sidecar.read_text())
                    if meta.get("asset_name") == asset_name:
                        # The local file is the sidecar path minus .release.json
                        local_file = sidecar.parent / asset_name
                        if local_file.exists():
                            local_path = str(local_file.relative_to(project_root))
                            break
                except Exception:
                    pass

            return {
                "type": "release", "id": ref_id, "exists": True,
                "tag": tag_name,
                "asset_name": asset_name,
                "size": asset.get("size", 0),
                "size_str": _format_size(asset.get("size", 0)),
                "download_url": asset.get("url", ""),
                "content_type": asset.get("contentType", ""),
                "local_path": local_path,
            }

    return {"type": "release", "id": ref_id, "exists": False,
            "error": f"Asset '{asset_name}' not found in release '{tag_name}'"}


def _resolve_code(file_path: str, project_root: Path) -> dict | None:
    """Resolve a code file reference.

    Supports plain paths (src/foo.py) — line ranges are future scope.
    """
    full_path = project_root / file_path
    if full_path.is_file():
        stat = full_path.stat()
        return {
            "type": "code",
            "id": file_path,
            "exists": True,
            "size_bytes": stat.st_size,
            "path": str(full_path),
        }
    return {"type": "code", "id": file_path, "exists": False}


def _format_size(size_bytes: int) -> str:
    """Format bytes into human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
