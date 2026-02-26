"""
L4 Execution — Remediation chain state persistence.

Manages the escalation chain lifecycle:
  create → escalate → de-escalate → save/load/resume

The chain tracks the full remediation path from original failure
to nested fixes. It is serializable for save/resume across
browser disconnects and server restarts.

Separate from plan_state.py: plans track install steps,
chains track remediation escalation. Different lifecycle,
different shape.

See .agent/plans/tool_install/remediation-model.md §5.3-5.6.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import uuid as _uuid_mod
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── State directory ─────────────────────────────────────────────

def _chain_state_dir() -> Path:
    """Resolve and lazily create the chain state directory.

    Uses ``<project_root>/.state/remediation_chains/`` following
    the project's standard ``.state/`` convention.

    Falls back to ``~/.local/share/devops-control-plane/remediation_chains/``.

    Returns:
        Absolute path to the state directory.
    """
    try:
        from flask import current_app
        root = Path(current_app.config["PROJECT_ROOT"])
    except (ImportError, RuntimeError, KeyError):
        import os
        root_env = os.environ.get("DEVOPS_CP_ROOT")
        if root_env:
            root = Path(root_env)
        else:
            root = Path.home() / ".local" / "share" / "devops-control-plane"

    d = root / ".state" / "remediation_chains"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Chain lifecycle ─────────────────────────────────────────────

MAX_CHAIN_DEPTH = 3


def create_chain(
    tool_id: str,
    plan: dict,
    failed_step_idx: int,
) -> dict:
    """Create a new escalation chain for a failed install.

    This is called on the FIRST failure of a tool install.
    The chain starts at depth 0 with an empty escalation stack.

    Args:
        tool_id: The tool that failed.
        plan: The original install plan that failed.
        failed_step_idx: Index of the step that failed.

    Returns:
        New chain dict with ``chain_id``, ``original_goal``,
        empty ``escalation_stack``.
    """
    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    return {
        "chain_id": str(_uuid_mod.uuid4()),
        "original_goal": {
            "tool_id": tool_id,
            "plan": plan,
            "failed_step_idx": failed_step_idx,
        },
        "escalation_stack": [],
        "visited_tools": {tool_id},
        "max_depth": MAX_CHAIN_DEPTH,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
    }


def escalate_chain(
    chain: dict,
    failure_id: str,
    chosen_option_id: str,
    chosen_option: dict | None = None,
) -> dict:
    """Push a new escalation level onto the chain stack.

    Called when the user picks a remediation option that itself
    needs a sub-install (e.g., installing pipx to fix PEP 668).

    Args:
        chain: Existing chain dict.
        failure_id: failure_id from the matched handler.
        chosen_option_id: The option ID the user picked.
        chosen_option: Full option dict (for metadata).

    Returns:
        Updated chain dict (mutated in place AND returned).

    Raises:
        ValueError: If max depth would be exceeded.
        ValueError: If a cycle would be created.
    """
    current_depth = len(chain.get("escalation_stack", []))
    if current_depth >= chain.get("max_depth", MAX_CHAIN_DEPTH):
        raise ValueError(
            f"Max remediation depth ({chain['max_depth']}) reached. "
            f"Cannot escalate further."
        )

    # Cycle detection: check if any dep is already in the chain
    dep = (chosen_option or {}).get("dep", "")
    visited = chain.get("visited_tools", set())
    if isinstance(visited, list):
        visited = set(visited)
        chain["visited_tools"] = visited
    if dep and dep in visited:
        raise ValueError(
            f"Cycle detected: '{dep}' is already in the remediation chain. "
            f"Chain: {' → '.join(visited)}"
        )
    if dep:
        visited.add(dep)

    entry = {
        "depth": current_depth + 1,
        "failure_id": failure_id,
        "chosen_option": chosen_option_id,
        "option_detail": {
            "label": (chosen_option or {}).get("label", ""),
            "strategy": (chosen_option or {}).get("strategy", ""),
            "dep": dep,
        },
        "plan": None,  # resolved later
        "status": "pending",
        "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    }

    chain["escalation_stack"].insert(0, entry)  # Index 0 = deepest
    chain["status"] = "escalating"
    chain["updated_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()

    return chain


def de_escalate_chain(chain: dict) -> dict | None:
    """Pop the top escalation level (mark done).

    Called when a fix at the current depth succeeds.

    Args:
        chain: Chain dict with at least one entry in escalation_stack.

    Returns:
        The now-current entry (one level up), or None if the
        stack is empty (meaning original goal can retry).
    """
    stack = chain.get("escalation_stack", [])
    if not stack:
        return None

    # Pop the top (deepest) entry
    completed = stack.pop(0)
    completed["status"] = "done"
    completed["completed_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()

    chain["updated_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()

    if not stack:
        chain["status"] = "ready_to_retry"
        return None

    # The new top entry becomes "ready" (its deps are now satisfied)
    stack[0]["status"] = "ready"
    chain["status"] = "de_escalating"
    return stack[0]


def mark_chain_executing(chain: dict) -> dict:
    """Mark the current top of stack as executing."""
    stack = chain.get("escalation_stack", [])
    if stack:
        stack[0]["status"] = "executing"
    chain["status"] = "executing"
    chain["updated_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    return chain


def mark_chain_failed(chain: dict, error: str = "") -> dict:
    """Mark the current top of stack as failed."""
    stack = chain.get("escalation_stack", [])
    if stack:
        stack[0]["status"] = "failed"
        stack[0]["error"] = error
    chain["status"] = "failed"
    chain["updated_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    return chain


def mark_chain_done(chain: dict) -> dict:
    """Mark the entire chain as done (original goal completed)."""
    chain["status"] = "done"
    chain["completed_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    chain["updated_at"] = chain["completed_at"]
    return chain


def cancel_chain(chain_id: str) -> bool:
    """Cancel a chain by ID.

    Args:
        chain_id: UUID string identifying the chain.

    Returns:
        True if the chain was found and cancelled.
    """
    chain = load_chain(chain_id)
    if chain is None:
        return False
    chain["status"] = "cancelled"
    chain["cancelled_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    chain["updated_at"] = chain["cancelled_at"]
    save_chain(chain)
    return True


# ── Breadcrumbs ─────────────────────────────────────────────────

def get_breadcrumbs(chain: dict) -> list[dict]:
    """Build the breadcrumb trail for the UI.

    Breadcrumbs show the path from original goal down to the
    current depth:
      🎯 Install ruff → 🔓 Install pipx → 📦 apt install pipx

    Returns:
        List of breadcrumb dicts, from original goal to current.
    """
    crumbs: list[dict] = []

    # Original goal is always the first crumb
    goal = chain.get("original_goal", {})
    crumbs.append({
        "tool_id": goal.get("tool_id", ""),
        "label": f"Install {goal.get('tool_id', '')}",
        "icon": "🎯",
        "status": "waiting",
    })

    # Walk the stack in reverse (deepest is [0], shallowest is [-1])
    stack = chain.get("escalation_stack", [])
    for entry in reversed(stack):
        detail = entry.get("option_detail", {})
        crumbs.append({
            "tool_id": detail.get("dep", ""),
            "label": detail.get("label", entry.get("chosen_option", "")),
            "icon": "🔓" if entry.get("status") == "pending" else "📦",
            "status": entry.get("status", "pending"),
        })

    return crumbs


# ── Persistence ─────────────────────────────────────────────────

def save_chain(chain: dict) -> Path:
    """Persist chain state to disk.

    Sets are converted to lists for JSON serialization.

    Args:
        chain: Chain dict.

    Returns:
        Path to the written JSON file.
    """
    chain_id = chain.get("chain_id", str(_uuid_mod.uuid4()))

    # Convert sets to lists for JSON
    safe = json.loads(json.dumps(chain, default=_json_default))

    path = _chain_state_dir() / f"{chain_id}.json"
    path.write_text(json.dumps(safe, indent=2, default=str))
    logger.info("Chain state saved: %s", path)
    return path


def load_chain(chain_id: str) -> dict | None:
    """Load a chain from disk.

    Sets stored as lists are restored to sets.

    Args:
        chain_id: UUID string identifying the chain.

    Returns:
        Chain dict, or None if not found.
    """
    path = _chain_state_dir() / f"{chain_id}.json"
    if not path.is_file():
        return None
    try:
        chain = json.loads(path.read_text())
        # Restore sets from lists
        if isinstance(chain.get("visited_tools"), list):
            chain["visited_tools"] = set(chain["visited_tools"])
        return chain
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load chain %s: %s", chain_id, exc)
        return None


def list_pending_chains() -> list[dict]:
    """Find all chains that are not done or cancelled.

    Returns:
        List of chain dicts with active status.
    """
    results: list[dict] = []
    state_dir = _chain_state_dir()
    for f in state_dir.glob("*.json"):
        try:
            chain = json.loads(f.read_text())
            status = chain.get("status", "")
            if status not in ("done", "cancelled"):
                # Restore sets
                if isinstance(chain.get("visited_tools"), list):
                    chain["visited_tools"] = set(chain["visited_tools"])
                results.append(chain)
        except (json.JSONDecodeError, OSError):
            logger.debug("Skipping corrupt chain file: %s", f)
    return results


def archive_chain(chain_id: str) -> bool:
    """Move a completed or cancelled chain to the archive subdirectory.

    Args:
        chain_id: UUID string identifying the chain.

    Returns:
        True if the chain was found and archived.
    """
    src = _chain_state_dir() / f"{chain_id}.json"
    if not src.is_file():
        return False
    archive_dir = _chain_state_dir() / "archive"
    archive_dir.mkdir(exist_ok=True)
    dst = archive_dir / f"{chain_id}.json"
    src.rename(dst)
    logger.info("Chain archived: %s → %s", src, dst)
    return True


# ── Helpers ─────────────────────────────────────────────────────

def _json_default(obj: Any) -> Any:
    """JSON serialization helper for sets."""
    if isinstance(obj, set):
        return sorted(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
