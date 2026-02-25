"""
L4 Execution — Plan state persistence.

Save, load, list, cancel, resume, and archive plan state.
"""

from __future__ import annotations

import json
import logging
import time
import uuid as _uuid_mod
from pathlib import Path

logger = logging.getLogger(__name__)


def _plan_state_dir() -> Path:
    """Resolve and lazily create the plan state directory.

    Uses ``<project_root>/.state/install_plans/`` following the
    project's standard ``.state/`` convention for ephemeral data.

    Falls back to ``~/.local/share/devops-control-plane/plans/``
    if no project root can be determined.

    Returns:
        Absolute path to the state directory.
    """
    # Try to resolve project root from Flask app context
    try:
        from flask import current_app
        root = Path(current_app.config["PROJECT_ROOT"])
    except (ImportError, RuntimeError, KeyError):
        # Outside Flask context — try env var or fallback
        import os
        root_env = os.environ.get("DEVOPS_CP_ROOT")
        if root_env:
            root = Path(root_env)
        else:
            root = Path.home() / ".local" / "share" / "devops-control-plane"

    d = root / ".state" / "install_plans"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_plan_state(state: dict) -> Path:
    """Write plan state to disk.

    The ``state`` dict **must** contain ``plan_id`` (string).
    If missing, one is generated.

    **Sensitive fields** (password input values) are stripped before
    persistence — they must never be written to disk in plaintext.

    Args:
        state: Plan state dict matching the schema defined in
               domain-restart §State Persistence.

    Returns:
        Path to the written JSON file.
    """
    if "plan_id" not in state:
        state["plan_id"] = str(_uuid_mod.uuid4())

    import datetime as _dt

    state.setdefault("updated_at", _dt.datetime.now(_dt.timezone.utc).isoformat())

    # Strip sensitive values before persisting
    safe_state = json.loads(json.dumps(state, default=str))
    for step in safe_state.get("plan", {}).get("steps", []):
        if step.get("type") == "config" and step.get("action") == "template":
            for inp in step.get("inputs", []):
                if inp.get("type") == "password":
                    inp_id = inp.get("id", "")
                    iv = step.get("input_values", {})
                    if inp_id in iv:
                        iv[inp_id] = "***REDACTED***"

    path = _plan_state_dir() / f"{safe_state['plan_id']}.json"
    path.write_text(json.dumps(safe_state, indent=2, default=str))
    logger.info("Plan state saved: %s", path)
    return path


def load_plan_state(plan_id: str) -> dict | None:
    """Load a plan state from disk.

    Args:
        plan_id: UUID string identifying the plan.

    Returns:
        Plan state dict, or ``None`` if the file doesn't exist
        or is corrupt.
    """
    path = _plan_state_dir() / f"{plan_id}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load plan state %s: %s", plan_id, exc)
        return None


def list_pending_plans() -> list[dict]:
    """Find all paused or pending plans on disk.

    Returns:
        List of plan state dicts whose status is ``"paused"``
        or ``"running"`` (crashed mid-run).
    """
    results: list[dict] = []
    state_dir = _plan_state_dir()
    for f in state_dir.glob("*.json"):
        try:
            plan = json.loads(f.read_text())
            if plan.get("status") in ("paused", "running", "failed"):
                results.append(plan)
        except (json.JSONDecodeError, OSError):
            logger.debug("Skipping corrupt plan file: %s", f)
    return results


def cancel_plan(plan_id: str) -> bool:
    """Mark a paused plan as cancelled.

    Args:
        plan_id: UUID string identifying the plan.

    Returns:
        True if the plan was found and cancelled.
    """
    import datetime as _dt

    state = load_plan_state(plan_id)
    if state is None:
        return False
    state["status"] = "cancelled"
    state["cancelled_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    save_plan_state(state)
    return True


def resume_plan(plan_id: str) -> dict:
    """Resume a paused or failed plan from its last completed step.

    Loads the saved state, skips already-completed steps, and returns
    a new plan dict containing only the remaining steps. The returned
    plan can be fed directly into ``execute_plan_step()`` or the
    SSE execute endpoint.

    Args:
        plan_id: UUID string identifying the plan.

    Returns:
        Plan dict with ``steps`` containing only unfinished steps,
        plus ``plan_id`` and ``resumed: True``.
        Returns ``{"error": "..."}`` if the plan can't be resumed.
    """
    state = load_plan_state(plan_id)
    if state is None:
        return {"error": f"Plan '{plan_id}' not found"}

    status = state.get("status", "")
    if status == "done":
        return {"error": f"Plan '{plan_id}' already completed"}
    if status == "cancelled":
        return {"error": f"Plan '{plan_id}' was cancelled"}

    all_steps = state.get("steps", [])
    completed = set(state.get("completed_steps", []))

    # Filter to remaining steps
    remaining_steps = [
        s for i, s in enumerate(all_steps)
        if i not in completed
    ]

    if not remaining_steps:
        return {"error": f"Plan '{plan_id}' has no remaining steps"}

    # Mark the state as resuming
    import datetime as _dt
    state["status"] = "running"
    state["resumed_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    save_plan_state(state)

    return {
        "tool": state.get("tool", ""),
        "label": state.get("tool", ""),
        "plan_id": plan_id,
        "resumed": True,
        "steps": remaining_steps,
        "original_total": len(all_steps),
        "completed_count": len(completed),
    }


def archive_plan(plan_id: str) -> bool:
    """Move a completed or cancelled plan to the archive subdirectory.

    Args:
        plan_id: UUID string identifying the plan.

    Returns:
        True if the plan was found and archived.
    """
    src = _plan_state_dir() / f"{plan_id}.json"
    if not src.is_file():
        return False
    archive_dir = _plan_state_dir() / "archive"
    archive_dir.mkdir(exist_ok=True)
    dst = archive_dir / f"{plan_id}.json"
    src.rename(dst)
    logger.info("Plan archived: %s → %s", src, dst)
    return True
