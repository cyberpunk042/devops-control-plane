"""
Chat @-reference parsing, resolution, and autocomplete.

Supports references like:
    @run:run_20260217T120000Z_detect_a1b2
    @thread:thread_20260217T120000Z_c3d4
    @trace:trace_20260217T120000Z_e5f6
    @user:JohnDoe

Parsing extracts these from message text.
Resolution looks up the referenced entity and returns metadata.
Autocomplete suggests completions for a partial reference.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Reference pattern ───────────────────────────────────────────
#
#   @<type>:<id>
#
# Type must be one of: run, thread, trace, user
# ID is a non-whitespace string of alphanumeric + underscore + dash
#
_REF_PATTERN = re.compile(
    r"@(run|thread|trace|user|commit|branch|audit|code):([A-Za-z0-9_\-/.]+)"
)

# Valid reference types
_VALID_TYPES = frozenset({
    "run", "thread", "trace", "user",
    "commit", "branch", "audit", "code",
})


def parse_refs(text: str) -> list[str]:
    """Extract @-references from message text.

    Args:
        text: Message text to scan.

    Returns:
        List of unique reference strings (e.g. ["@run:run_xxx", "@thread:thread_yyy"]).
        Order is preserved (first occurrence).

    Examples:
        >>> parse_refs("Deployed @run:run_123 to staging")
        ['@run:run_123']
        >>> parse_refs("See @thread:t1 and @trace:tr1")
        ['@thread:t1', '@trace:tr1']
        >>> parse_refs("No references here")
        []
    """
    seen: set[str] = set()
    refs: list[str] = []
    for match in _REF_PATTERN.finditer(text):
        ref = f"@{match.group(1)}:{match.group(2)}"
        if ref not in seen:
            seen.add(ref)
            refs.append(ref)
    return refs


def parse_ref_parts(ref: str) -> tuple[str, str] | None:
    """Parse a reference string into (type, id).

    Args:
        ref: Reference string like "@run:run_123".

    Returns:
        Tuple of (type, id) or None if invalid.
    """
    if not ref.startswith("@"):
        return None
    match = _REF_PATTERN.fullmatch(ref)
    if not match:
        return None
    return match.group(1), match.group(2)


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
        "code": _resolve_code,
    }

    if ref_type == "user":
        return {"type": "user", "id": ref_id, "exists": True, "name": ref_id}

    resolver = _resolvers.get(ref_type)
    if resolver is None:
        return None
    return resolver(ref_id, project_root)


def autocomplete(prefix: str, project_root: Path) -> list[str]:
    """Return matching @-references for a partial input.

    Args:
        prefix: Partial reference, e.g. "@run:", "@run:run_2026", "@thr".
        project_root: Repository root.

    Returns:
        List of matching complete reference strings, up to 20 results.
    """
    if not prefix.startswith("@"):
        return []

    # Parse the prefix
    rest = prefix[1:]  # strip @
    if ":" in rest:
        ref_type, partial_id = rest.split(":", 1)
    else:
        # No colon yet — suggest matching types
        return [f"@{t}:" for t in sorted(_VALID_TYPES) if t.startswith(rest)]

    if ref_type not in _VALID_TYPES:
        return []

    _autocompleters = {
        "run": _autocomplete_runs,
        "thread": _autocomplete_threads,
        "trace": _autocomplete_traces,
        "commit": _autocomplete_commits,
        "branch": _autocomplete_branches,
        "audit": _autocomplete_audits,
    }

    if ref_type == "user":
        # User autocomplete is minimal — just return the partial as-is
        return [f"@user:{partial_id}"] if partial_id else []
    if ref_type == "code":
        # Code autocomplete is path-based, not practical without more context
        return [f"@code:{partial_id}"] if partial_id else []

    ac = _autocompleters.get(ref_type)
    if ac is None:
        return []
    return ac(partial_id, project_root)


# ═══════════════════════════════════════════════════════════════════════
#  Internal resolvers
# ═══════════════════════════════════════════════════════════════════════


def _resolve_run(run_id: str, project_root: Path) -> dict | None:
    """Resolve a run reference."""
    try:
        from src.core.services.ledger.ledger_ops import get_run
        run = get_run(project_root, run_id)
        if run is None:
            return {"type": "run", "id": run_id, "exists": False}
        return {
            "type": "run",
            "id": run_id,
            "exists": True,
            "run_type": run.type,
            "summary": run.summary,
            "status": run.status,
            "started_at": run.started_at,
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
    """Resolve an audit log entry by operation_id."""
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
            "operation_type": found.operation_type,
            "status": found.status,
            "timestamp": found.timestamp,
            "automation": found.automation,
        }
    except Exception as e:
        logger.debug("Failed to resolve audit %s: %s", operation_id, e)
        return {"type": "audit", "id": operation_id, "exists": False}


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


# ═══════════════════════════════════════════════════════════════════════
#  Internal autocompleters
# ═══════════════════════════════════════════════════════════════════════

_MAX_SUGGESTIONS = 20


def _autocomplete_runs(partial_id: str, project_root: Path) -> list[str]:
    """Autocomplete run references."""
    try:
        from src.core.services.ledger.ledger_ops import list_runs
        runs = list_runs(project_root, n=50)
        matches = [
            f"@run:{r.run_id}" for r in runs
            if r.run_id.startswith(partial_id) or not partial_id
        ]
        return matches[:_MAX_SUGGESTIONS]
    except Exception as e:
        logger.debug("Failed to autocomplete runs: %s", e)
        return []


def _autocomplete_threads(partial_id: str, project_root: Path) -> list[str]:
    """Autocomplete thread references."""
    try:
        from src.core.services.chat.chat_ops import list_threads
        threads = list_threads(project_root)
        matches = [
            f"@thread:{t.thread_id}" for t in threads
            if t.thread_id.startswith(partial_id) or not partial_id
        ]
        return matches[:_MAX_SUGGESTIONS]
    except Exception as e:
        logger.debug("Failed to autocomplete threads: %s", e)
        return []


def _autocomplete_traces(partial_id: str, project_root: Path) -> list[str]:
    """Autocomplete trace references."""
    try:
        from src.core.services.trace.trace_recorder import list_traces
        traces = list_traces(project_root, n=50)
        matches = [
            f"@trace:{t.trace_id}" for t in traces
            if t.trace_id.startswith(partial_id) or not partial_id
        ]
        return matches[:_MAX_SUGGESTIONS]
    except Exception as e:
        logger.debug("Failed to autocomplete traces: %s", e)
        return []


def _autocomplete_commits(partial_id: str, project_root: Path) -> list[str]:
    """Autocomplete commit references (recent commits)."""
    try:
        import subprocess
        r = subprocess.run(
            ["git", "-C", str(project_root), "log", "-20", "--format=%h"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return []
        hashes = r.stdout.strip().splitlines()
        matches = [
            f"@commit:{h}" for h in hashes
            if h.startswith(partial_id) or not partial_id
        ]
        return matches[:_MAX_SUGGESTIONS]
    except Exception as e:
        logger.debug("Failed to autocomplete commits: %s", e)
        return []


def _autocomplete_branches(partial_id: str, project_root: Path) -> list[str]:
    """Autocomplete branch references."""
    try:
        import subprocess
        r = subprocess.run(
            ["git", "-C", str(project_root), "branch", "--format=%(refname:short)"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return []
        branches = r.stdout.strip().splitlines()
        matches = [
            f"@branch:{b}" for b in branches
            if b.startswith(partial_id) or not partial_id
        ]
        return matches[:_MAX_SUGGESTIONS]
    except Exception as e:
        logger.debug("Failed to autocomplete branches: %s", e)
        return []


def _autocomplete_audits(partial_id: str, project_root: Path) -> list[str]:
    """Autocomplete audit log references."""
    try:
        from src.core.persistence.audit import AuditWriter
        writer = AuditWriter(project_root=project_root)
        entries = writer.read_recent(n=50)
        matches = [
            f"@audit:{e.operation_id}" for e in entries
            if e.operation_id
            and (e.operation_id.startswith(partial_id) or not partial_id)
        ]
        return matches[:_MAX_SUGGESTIONS]
    except Exception as e:
        logger.debug("Failed to autocomplete audits: %s", e)
        return []
