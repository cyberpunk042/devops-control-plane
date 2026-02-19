"""
Run tracking — decorator + context manager for wrapping any action as a Run.

Provides two patterns:
  1. @run_tracked("type", "type:subtype") — decorator for route handlers
  2. with tracked_run(root, "type", "type:subtype") as run: — context manager

Both ensure:
  - A Run model is created with timestamps
  - SSE event emitted at start (run:started) and end (run:completed)
  - Run is recorded to local ephemeral storage (.state/runs.jsonl)
  - run_id is available for referencing

Fail-safe: tracking failures never break the wrapped action.
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ── Run type taxonomy ───────────────────────────────────────────────

RUN_TYPES = {
    # Lifecycle operations
    "install":   "Package/tool installation",
    "build":     "Build artifacts (images, sites, binaries)",
    "deploy":    "Deploy to target (cluster, cloud, pages)",
    "destroy":   "Tear down resources",

    # Maintenance operations
    "setup":     "Initial setup/configuration of an integration",
    "plan":      "Dry-run / preview (terraform plan, helm template)",
    "validate":  "Validation / linting",
    "format":    "Code/config formatting",

    # Execution operations
    "test":      "Test execution",
    "scan":      "Security / audit scans",
    "generate":  "Generate configs, templates, scaffolding",

    # Data operations
    "backup":    "Backup / export",
    "restore":   "Restore / import",

    # Git operations
    "git":       "Git operations (commit, push, pull)",
    "ci":        "CI/CD workflow operations",
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


_RUNS_MAX = 200  # keep last N runs


def _runs_path(project_root: Path) -> Path:
    return project_root / ".state" / "runs.jsonl"


def _append_run_local(project_root: Path, run_model) -> None:
    """Append a completed run to .state/runs.jsonl."""
    path = _runs_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = run_model.model_dump(mode="json")
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")

    # Trim to max entries
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > _RUNS_MAX:
            path.write_text(
                "\n".join(lines[-_RUNS_MAX:]) + "\n",
                encoding="utf-8",
            )
    except Exception:
        pass


def load_runs(project_root: Path, n: int = 50) -> list[dict]:
    """Load the latest N runs from .state/runs.jsonl, newest-first."""
    path = _runs_path(project_root)
    if not path.is_file():
        return []

    entries: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    except OSError:
        return []

    # Newest-first
    entries.reverse()
    return entries[:n]


def get_run_local(project_root: Path, run_id: str) -> dict | None:
    """Get a single run by ID from .state/runs.jsonl."""
    for entry in load_runs(project_root, n=_RUNS_MAX):
        if entry.get("run_id") == run_id:
            return entry
    return None


def _publish_event(event_type: str, run_data: dict) -> None:
    """Publish an SSE event for a run lifecycle change.

    Fail-safe — never raises.
    """
    try:
        from src.core.services.event_bus import bus

        bus.publish(event_type, key=run_data.get("run_id", ""), data=run_data)
    except Exception:
        pass  # SSE failure must never break run tracking


# ═══════════════════════════════════════════════════════════════════════
#  Context Manager — tracked_run()
# ═══════════════════════════════════════════════════════════════════════


@contextmanager
def tracked_run(
    project_root: Path,
    run_type: str,
    subtype: str,
    *,
    summary: str = "",
    **metadata: Any,
):
    """Context manager — creates, tracks, and records a Run.

    Usage::

        with tracked_run(root, "deploy", "deploy:k8s", summary="Apply manifests") as run:
            result = k8s_ops.k8s_apply(root, path)
            run["summary"] = result.get("summary", "")
            run["status"] = "ok" if result.get("ok") else "failed"

    The run dict is a mutable bag — set ``status``, ``summary``, or any
    other fields before the ``with`` block exits.  On exit the Run is
    recorded to the ledger and an SSE event fires.
    """
    from src.core.services.ledger.models import Run
    from src.core.services.ledger.worktree import current_head_sha, current_user

    # Fill user and code_ref
    try:
        user = current_user(project_root)
    except Exception:
        user = ""
    try:
        code_ref = current_head_sha(project_root) or ""
    except Exception:
        code_ref = ""

    run_model = Run(
        type=run_type,
        subtype=subtype,
        summary=summary,
        user=user,
        code_ref=code_ref,
        metadata=metadata if metadata else {},
    )
    run_model.ensure_id()

    # Mutable dict that the caller can update
    run_bag: dict[str, Any] = {
        "run_id": run_model.run_id,
        "type": run_type,
        "subtype": subtype,
        "summary": summary,
        "status": "ok",
        "started_at": _now_iso(),
    }

    t0 = time.time()

    # Emit start event
    _publish_event("run:started", {
        "run_id": run_model.run_id,
        "type": run_type,
        "subtype": subtype,
        "summary": summary,
    })

    try:
        yield run_bag
    except Exception as exc:
        run_bag["status"] = "failed"
        run_bag.setdefault("summary", str(exc))
        raise
    finally:
        duration_ms = int((time.time() - t0) * 1000)
        run_bag["duration_ms"] = duration_ms
        run_bag["ended_at"] = _now_iso()

        # Sync bag values back to the model
        run_model.status = run_bag.get("status", "ok")
        run_model.summary = run_bag.get("summary", summary)
        run_model.duration_ms = duration_ms
        run_model.ended_at = run_bag["ended_at"]

        # Record to local ephemeral storage
        try:
            _append_run_local(project_root, run_model)
        except Exception as e:
            logger.warning("Failed to record run %s locally: %s", run_model.run_id, e)

        # Emit completed event
        _publish_event("run:completed", {
            "run_id": run_model.run_id,
            "type": run_type,
            "subtype": subtype,
            "status": run_bag.get("status", "ok"),
            "summary": run_bag.get("summary", ""),
            "duration_ms": duration_ms,
        })


# ═══════════════════════════════════════════════════════════════════════
#  Decorator — run_tracked()
# ═══════════════════════════════════════════════════════════════════════


def run_tracked(
    run_type: str,
    subtype: str,
    *,
    summary_key: str = "summary",
    ok_key: str = "ok",
):
    """Decorator for Flask route handlers that should create a Run.

    Usage::

        @bp.route("/k8s/apply", methods=["POST"])
        @run_tracked("deploy", "deploy:k8s")
        def k8s_apply():
            ...
            return jsonify(result)

    The decorator:
      1. Wraps the route function
      2. Creates a Run with type/subtype
      3. Calls the original handler
      4. Inspects the Flask response to extract result data
      5. Sets status from result (ok/failed)
      6. Records to ledger
      7. Adds ``run_id`` to the response JSON

    Fail-safe: if Run tracking fails at any point, the original
    response is returned unmodified.
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            from flask import current_app

            # Get project root
            try:
                project_root = Path(current_app.config["PROJECT_ROOT"])
            except Exception:
                # Can't get project root — skip tracking, run handler normally
                return fn(*args, **kwargs)

            with tracked_run(project_root, run_type, subtype) as run:
                # Call the original handler
                response = fn(*args, **kwargs)

                # Inspect response to set Run metadata
                # Flask handlers return either:
                #   jsonify(dict)           → Response object
                #   jsonify(dict), 400      → (Response, int) tuple
                try:
                    _extract_run_metadata(response, run, summary_key, ok_key)
                except Exception:
                    pass  # metadata extraction failure is non-fatal

                # Inject run_id into the response JSON
                try:
                    response = _inject_run_id(response, run["run_id"])
                except Exception:
                    pass  # injection failure is non-fatal

                return response

        return wrapper
    return decorator


def _extract_run_metadata(
    response: Any,
    run: dict,
    summary_key: str,
    ok_key: str,
) -> None:
    """Extract metadata from a Flask response into the run bag.

    Handles both ``Response`` objects and ``(Response, status_code)`` tuples.
    """
    from flask import Response

    resp_obj = response
    status_code = 200

    if isinstance(response, tuple):
        resp_obj = response[0]
        status_code = response[1] if len(response) > 1 else 200

    if isinstance(resp_obj, Response) and resp_obj.content_type and \
       "json" in resp_obj.content_type:
        data = resp_obj.get_json(silent=True) or {}
    else:
        data = {}

    # Set status
    if status_code >= 400:
        run["status"] = "failed"
    elif ok_key in data and not data[ok_key]:
        run["status"] = "failed"
    else:
        run["status"] = "ok"

    # Set summary
    if summary_key in data and data[summary_key]:
        run["summary"] = str(data[summary_key])
    elif summary_key != "message" and "message" in data and data["message"]:
        run["summary"] = str(data["message"])
    elif "error" in data:
        run["summary"] = str(data["error"])


def _inject_run_id(response: Any, run_id: str) -> Any:
    """Inject run_id into the JSON response body.

    Handles both ``Response`` and ``(Response, status_code)`` tuples.
    Returns the modified response in the same form.
    """
    from flask import Response

    resp_obj = response
    status_code = None

    if isinstance(response, tuple):
        resp_obj = response[0]
        status_code = response[1] if len(response) > 1 else None

    if isinstance(resp_obj, Response) and resp_obj.content_type and \
       "json" in resp_obj.content_type:
        data = resp_obj.get_json(silent=True)
        if isinstance(data, dict):
            data["run_id"] = run_id
            resp_obj.set_data(json.dumps(data, ensure_ascii=False))

    if status_code is not None:
        return (resp_obj, status_code)
    return resp_obj
