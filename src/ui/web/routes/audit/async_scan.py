"""
Async audit scan — background L2 analysis with SSE progress.

Routes registered on ``audit_bp`` from the parent package.

Endpoints:
    POST /audit/scan              — start background audit scan
    GET  /audit/scan/<task_id>    — query scan status / result

The scan runs all L2 layers (structure, quality, risks, scores) in a
background thread.  Progress is published via EventBus as ``audit:progress``
events and the final result as ``audit:complete``.

Frontend can either poll GET /audit/scan/<task_id> or subscribe to SSE
events for real-time updates.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from flask import jsonify, request

from src.core.services.devops import cache as devops_cache
from src.core.services.event_bus import bus
from src.ui.web.helpers import project_root as _project_root

from . import audit_bp

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  Task Registry
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ScanTask:
    """In-memory state for a background audit scan."""

    task_id: str
    status: str = "pending"          # pending → running → done | error
    progress: float = 0.0            # 0.0 → 1.0
    phase: str = ""                  # current phase label
    phase_detail: str = ""           # e.g. "python 150/681"
    started_at: float = 0.0
    completed_at: float = 0.0
    duration_ms: int = 0
    result: dict = field(default_factory=dict)
    error: str = ""


# Global task registry: task_id → ScanTask
# Protected by _registry_lock for thread-safe access.
_registry: dict[str, ScanTask] = {}
_registry_lock = threading.Lock()

# Maximum number of completed tasks to keep (auto-cleanup)
_MAX_COMPLETED = 10
# Time after which completed tasks are eligible for cleanup (seconds)
_CLEANUP_AGE_S = 300


def _register_task() -> ScanTask:
    """Create and register a new scan task."""
    task = ScanTask(task_id=uuid.uuid4().hex[:12])
    with _registry_lock:
        _registry[task.task_id] = task
        _cleanup_old_tasks()
    return task


def _get_task(task_id: str) -> ScanTask | None:
    """Retrieve a task by ID."""
    with _registry_lock:
        return _registry.get(task_id)


def _cleanup_old_tasks() -> None:
    """Remove completed tasks older than _CLEANUP_AGE_S. Must hold lock."""
    now = time.time()
    to_remove = []
    completed = [
        t for t in _registry.values()
        if t.status in ("done", "error")
    ]
    # Sort by completion time, keep newest _MAX_COMPLETED
    completed.sort(key=lambda t: t.completed_at, reverse=True)
    for task in completed[_MAX_COMPLETED:]:
        if now - task.completed_at > _CLEANUP_AGE_S:
            to_remove.append(task.task_id)
    for tid in to_remove:
        del _registry[tid]


# ═══════════════════════════════════════════════════════════════════
#  Background Scan Worker
# ═══════════════════════════════════════════════════════════════════

def _run_scan(task: ScanTask, root: Path, force: bool) -> None:
    """Execute all L2 audit layers in sequence, publishing progress."""

    task.status = "running"
    task.started_at = time.time()

    # Define the scan phases and their weights (for progress calculation)
    phases = [
        ("structure",  "audit:l2:structure",  0.15),
        ("quality",    "audit:l2:quality",    0.30),
        ("repo",       "audit:l2:repo",       0.10),
        ("risks",      "audit:l2:risks",      0.25),
        ("scores",     "audit:scores",        0.10),
        ("enriched",   "audit:scores:enriched", 0.10),
    ]

    cumulative = 0.0
    results: dict[str, Any] = {}

    try:
        for phase_name, cache_key, weight in phases:
            task.phase = phase_name
            task.phase_detail = ""
            task.progress = cumulative

            # Publish progress event
            bus.publish(
                "audit:progress",
                key=task.task_id,
                data={
                    "task_id": task.task_id,
                    "phase": phase_name,
                    "progress": round(cumulative, 2),
                    "detail": "",
                },
            )

            # Import the compute function lazily
            compute_fn = _get_compute_fn(phase_name, root)
            if compute_fn is None:
                log.warning("No compute function for phase %s", phase_name)
                cumulative += weight
                continue

            # Run through the cache system (force=True to get fresh data)
            t0 = time.time()
            try:
                result = devops_cache.get_cached(
                    root, cache_key, compute_fn, force=force,
                )
                results[phase_name] = result
                elapsed = round((time.time() - t0) * 1000)
                task.phase_detail = f"done in {elapsed}ms"
            except Exception as exc:
                log.error("Phase %s failed: %s", phase_name, exc)
                results[phase_name] = {"error": str(exc)}

            cumulative += weight

        # ── Complete ──
        task.progress = 1.0
        task.status = "done"
        task.completed_at = time.time()
        task.duration_ms = int((task.completed_at - task.started_at) * 1000)
        task.result = {
            "phases_completed": list(results.keys()),
            "duration_ms": task.duration_ms,
        }

        bus.publish(
            "audit:complete",
            key=task.task_id,
            data={
                "task_id": task.task_id,
                "duration_ms": task.duration_ms,
                "phases_completed": list(results.keys()),
            },
        )

        log.info(
            "Audit scan %s completed in %dms (%d phases)",
            task.task_id, task.duration_ms, len(results),
        )

    except Exception as exc:
        task.status = "error"
        task.error = str(exc)
        task.completed_at = time.time()
        task.duration_ms = int((task.completed_at - task.started_at) * 1000)

        bus.publish(
            "audit:complete",
            key=task.task_id,
            data={
                "task_id": task.task_id,
                "error": str(exc),
                "duration_ms": task.duration_ms,
            },
        )

        log.error("Audit scan %s failed: %s", task.task_id, exc)


def _get_compute_fn(phase: str, root: Path):
    """Return the appropriate compute callable for a scan phase."""
    from src.core.services.audit import (
        audit_scores,
        audit_scores_enriched,
        l2_quality,
        l2_repo,
        l2_risks,
        l2_structure,
    )
    return {
        "structure": lambda: l2_structure(root),
        "quality":   lambda: l2_quality(root),
        "repo":      lambda: l2_repo(root),
        "risks":     lambda: l2_risks(root),
        "scores":    lambda: audit_scores(root),
        "enriched":  lambda: audit_scores_enriched(root),
    }.get(phase)


# ═══════════════════════════════════════════════════════════════════
#  HTTP Endpoints
# ═══════════════════════════════════════════════════════════════════

@audit_bp.route("/audit/scan", methods=["POST"])
def audit_scan_start():
    """Start a background audit scan.

    Request body (optional JSON):
        force (bool): If true, bust all caches and recompute. Default: true.

    Returns:
        {task_id, status: "started"}
    """
    root = _project_root()
    body = request.get_json(silent=True) or {}
    force = body.get("force", True)

    # Check if there's already a scan running
    with _registry_lock:
        running = [
            t for t in _registry.values()
            if t.status == "running"
        ]
    if running:
        task = running[0]
        return jsonify({
            "task_id": task.task_id,
            "status": "already_running",
            "progress": round(task.progress, 2),
            "phase": task.phase,
        }), 409

    task = _register_task()

    thread = threading.Thread(
        target=_run_scan,
        args=(task, root, force),
        name=f"audit-scan-{task.task_id}",
        daemon=True,
    )
    thread.start()

    log.info("Started audit scan %s (force=%s)", task.task_id, force)

    return jsonify({
        "task_id": task.task_id,
        "status": "started",
    }), 202


@audit_bp.route("/audit/scan/<task_id>")
def audit_scan_status(task_id: str):
    """Query status of a background audit scan.

    Returns:
        {task_id, status, progress, phase, phase_detail, duration_ms, result?, error?}
    """
    task = _get_task(task_id)
    if task is None:
        return jsonify({"error": "Task not found", "task_id": task_id}), 404

    resp: dict[str, Any] = {
        "task_id": task.task_id,
        "status": task.status,
        "progress": round(task.progress, 2),
        "phase": task.phase,
        "phase_detail": task.phase_detail,
        "duration_ms": task.duration_ms,
    }
    if task.status == "done":
        resp["result"] = task.result
    if task.error:
        resp["error"] = task.error

    return jsonify(resp)
