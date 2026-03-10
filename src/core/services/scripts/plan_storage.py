"""
Execution Plan storage — JSON file CRUD for plans and run results.

File layout::

    .state/
        cdp-plans/
            plans/
                <plan-id>.json          # ExecutionPlan serialized
            results/
                <run-id>.json           # PlanRunResult serialized

Thread-safe: all file I/O is guarded by a module-level lock.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from src.core.services.scripts.plans import (
    ExecutionPlan,
    PlanRunResult,
)

logger = logging.getLogger(__name__)

_lock = threading.Lock()


# ── Paths ──────────────────────────────────────────────────────


def _plans_dir(project_root: Path) -> Path:
    """Return (and create) the plans directory."""
    d = project_root / ".state" / "cdp-plans" / "plans"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _results_dir(project_root: Path) -> Path:
    """Return (and create) the results directory."""
    d = project_root / ".state" / "cdp-plans" / "results"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Plan CRUD ──────────────────────────────────────────────────


def list_plans(project_root: Path) -> list[dict]:
    """List all execution plans (summary — no step details).

    Returns a list of dicts with plan metadata (id, name, step count,
    mode, last run status, etc.) sorted by updated_at descending.
    """
    plans_path = _plans_dir(project_root)
    summaries: list[dict] = []

    with _lock:
        for f in plans_path.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                summaries.append({
                    "id": data.get("id", f.stem),
                    "name": data.get("name", ""),
                    "description": data.get("description", ""),
                    "mode": data.get("mode", "fully_automated"),
                    "step_count": len(data.get("steps", [])),
                    "browser_mode": (
                        data.get("browser_config", {}).get("mode", "")
                        if data.get("browser_config") else "none"
                    ),
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                    "last_run_at": data.get("last_run_at", ""),
                    "last_run_status": data.get("last_run_status", ""),
                    "run_count": data.get("run_count", 0),
                })
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to read plan %s: %s", f.name, exc)

    # Sort by updated_at descending (newest first)
    summaries.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
    return summaries


def get_plan(project_root: Path, plan_id: str) -> ExecutionPlan | None:
    """Load a full execution plan by ID."""
    path = _plans_dir(project_root) / f"{plan_id}.json"
    with _lock:
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return ExecutionPlan.from_dict(data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read plan %s: %s", plan_id, exc)
            return None


def save_plan(project_root: Path, plan: ExecutionPlan) -> None:
    """Save (create or update) an execution plan."""
    from src.core.services.scripts.plans import _now_iso

    plan.updated_at = _now_iso()
    path = _plans_dir(project_root) / f"{plan.id}.json"
    with _lock:
        path.write_text(
            json.dumps(plan.to_dict(), indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
    logger.info("Saved plan %s (%s)", plan.id, plan.name)


def delete_plan(project_root: Path, plan_id: str) -> bool:
    """Delete an execution plan.  Returns True if it existed."""
    path = _plans_dir(project_root) / f"{plan_id}.json"
    with _lock:
        if path.is_file():
            path.unlink()
            logger.info("Deleted plan %s", plan_id)
            return True
    return False


# ── Result CRUD ────────────────────────────────────────────────


def list_results(
    project_root: Path,
    *,
    plan_id: str | None = None,
    last: int = 20,
) -> list[dict]:
    """List plan run results (newest first).

    Optionally filter by plan_id.
    """
    results_path = _results_dir(project_root)
    items: list[dict] = []

    with _lock:
        for f in results_path.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if plan_id and data.get("plan_id") != plan_id:
                    continue
                items.append(data)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to read result %s: %s", f.name, exc)

    # Sort by started_at descending
    items.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return items[:last]


def get_result(project_root: Path, run_id: str) -> PlanRunResult | None:
    """Load a single plan run result by ID."""
    path = _results_dir(project_root) / f"{run_id}.json"
    with _lock:
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return PlanRunResult.from_dict(data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read result %s: %s", run_id, exc)
            return None


def save_result(project_root: Path, result: PlanRunResult) -> None:
    """Save a plan run result."""
    path = _results_dir(project_root) / f"{result.id}.json"
    with _lock:
        path.write_text(
            json.dumps(result.to_dict(), indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
    logger.info(
        "Saved plan result %s (plan=%s, status=%s)",
        result.id, result.plan_id, result.status,
    )
