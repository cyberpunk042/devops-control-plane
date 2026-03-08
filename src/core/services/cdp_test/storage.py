"""
CDP Test storage — JSON file CRUD for test suites and run results.

File layout::

    .state/
        cdp-tests/
            suites/
                <suite-id>.json        # TestSuite serialized
            results/
                <run-id>.json          # TestRunResult serialized

Thread-safe: all file I/O is guarded by a module-level lock.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from src.core.services.cdp_test.models import TestRunResult, TestSuite

logger = logging.getLogger(__name__)

_lock = threading.Lock()

# ── Paths ──────────────────────────────────────────────────────


def _suites_dir(project_root: Path) -> Path:
    """Return (and create) the suites directory."""
    d = project_root / ".state" / "cdp-tests" / "suites"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _results_dir(project_root: Path) -> Path:
    """Return (and create) the results directory."""
    d = project_root / ".state" / "cdp-tests" / "results"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Suite CRUD ─────────────────────────────────────────────────


def list_suites(project_root: Path) -> list[dict]:
    """List all test suites (summary — no step details).

    Returns a list of dicts with suite metadata (id, name, category,
    step count, last run status, etc.) sorted by updated_at descending.
    """
    suites_path = _suites_dir(project_root)
    summaries: list[dict] = []

    with _lock:
        for f in suites_path.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                summaries.append({
                    "id": data.get("id", f.stem),
                    "name": data.get("name", ""),
                    "description": data.get("description", ""),
                    "target_url": data.get("target_url", ""),
                    "category": data.get("category", "smoke"),
                    "tags": data.get("tags", []),
                    "step_count": len(data.get("steps", [])),
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                    "created_by": data.get("created_by", ""),
                    "last_run_at": data.get("last_run_at", ""),
                    "last_run_status": data.get("last_run_status", ""),
                    "run_count": data.get("run_count", 0),
                })
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to read suite %s: %s", f.name, exc)

    # Sort by updated_at descending (newest first)
    summaries.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
    return summaries


def get_suite(project_root: Path, suite_id: str) -> TestSuite | None:
    """Load a full test suite by ID."""
    path = _suites_dir(project_root) / f"{suite_id}.json"
    with _lock:
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return TestSuite.from_dict(data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read suite %s: %s", suite_id, exc)
            return None


def save_suite(project_root: Path, suite: TestSuite) -> None:
    """Save (create or update) a test suite."""
    from src.core.services.cdp_test.models import _now_iso

    suite.updated_at = _now_iso()
    path = _suites_dir(project_root) / f"{suite.id}.json"
    with _lock:
        path.write_text(
            json.dumps(suite.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    logger.info("Saved suite %s (%s)", suite.id, suite.name)


def delete_suite(project_root: Path, suite_id: str) -> bool:
    """Delete a test suite.  Returns True if it existed."""
    path = _suites_dir(project_root) / f"{suite_id}.json"
    with _lock:
        if path.is_file():
            path.unlink()
            logger.info("Deleted suite %s", suite_id)
            return True
    return False


# ── Result CRUD ────────────────────────────────────────────────


def list_results(
    project_root: Path,
    *,
    suite_id: str | None = None,
    last: int = 20,
) -> list[dict]:
    """List test run results (newest first).

    Optionally filter by suite_id.
    """
    results_path = _results_dir(project_root)
    items: list[dict] = []

    with _lock:
        for f in results_path.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if suite_id and data.get("suite_id") != suite_id:
                    continue
                items.append(data)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to read result %s: %s", f.name, exc)

    # Sort by started_at descending
    items.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return items[:last]


def get_result(project_root: Path, run_id: str) -> TestRunResult | None:
    """Load a single run result by ID."""
    path = _results_dir(project_root) / f"{run_id}.json"
    with _lock:
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return TestRunResult.from_dict(data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read result %s: %s", run_id, exc)
            return None


def save_result(project_root: Path, result: TestRunResult) -> None:
    """Save a test run result."""
    path = _results_dir(project_root) / f"{result.id}.json"
    with _lock:
        path.write_text(
            json.dumps(result.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    logger.info(
        "Saved result %s (suite=%s, status=%s)",
        result.id, result.suite_id, result.status,
    )
