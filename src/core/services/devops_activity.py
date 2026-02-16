"""
DevOps activity log — scan history and user-initiated event recording.

Maintains a JSON-based activity log at ``.state/audit_activity.json``
for the Debugging → Audit Log tab.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_ACTIVITY_FILE = ".state/audit_activity.json"
_ACTIVITY_MAX = 200  # keep last N entries


# ── Helpers ─────────────────────────────────────────────────────────


def _card_label(key: str) -> str:
    """Look up the display label for a card key."""
    from src.core.data import get_registry
    return get_registry().card_labels.get(key, key)


def _activity_path(project_root: Path) -> Path:
    return project_root / _ACTIVITY_FILE


def _extract_summary(card_key: str, data: dict) -> str:
    """Extract a one-line summary from the scan result for display."""
    if "error" in data and isinstance(data["error"], str):
        return f"Error: {data['error'][:100]}"

    # Audit-specific summaries
    if card_key == "audit:l2:risks":
        findings = data.get("findings", [])
        by_sev = {}
        for f in findings:
            s = f.get("severity", "info")
            by_sev[s] = by_sev.get(s, 0) + 1
        parts = [f"{c} {s}" for s, c in sorted(by_sev.items(), key=lambda x: {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get(x[0], 5))]
        return f"{len(findings)} findings ({', '.join(parts)})" if parts else f"{len(findings)} findings"

    if card_key == "audit:scores" or card_key == "audit:scores:enriched":
        scores = data.get("scores", {})
        if isinstance(scores, dict):
            overall = scores.get("overall", scores.get("total"))
            if overall is not None:
                return f"Overall score: {overall}"

    if card_key == "audit:system":
        return f"{data.get('os', '?')} · Python {data.get('python_version', '?')}"

    if card_key == "audit:deps":
        deps = data.get("dependencies", data.get("packages", []))
        if isinstance(deps, list):
            return f"{len(deps)} dependencies found"

    if card_key == "audit:l2:quality":
        hotspots = data.get("hotspots", [])
        return f"{len(hotspots)} hotspots" if hotspots else "No hotspots"

    # DevOps card summaries
    if card_key == "security":
        score = data.get("score")
        issues = data.get("issues", [])
        return f"Score: {score}, {len(issues)} issues" if score is not None else f"{len(issues)} issues"

    if card_key == "testing":
        total = data.get("test_files", data.get("total_files", 0))
        funcs = data.get("test_functions", data.get("total_functions", 0))
        return f"{total} test files, {funcs} functions"

    if card_key == "packages":
        managers = data.get("managers", [])
        return f"{len(managers)} package managers" if managers else "No package managers"

    # Generic — try to find any count-like key
    for key in ("total", "count", "items"):
        if key in data:
            return f"{data[key]} {key}"

    return "completed"


# ── Recording ───────────────────────────────────────────────────────


def record_scan_activity(
    project_root: Path,
    card_key: str,
    status: str,
    elapsed_s: float,
    data: dict,
    error_msg: str = "",
    *,
    bust: bool = False,
) -> None:
    """Record a scan computation in the activity log."""
    import datetime

    entry = {
        "ts": time.time(),
        "iso": datetime.datetime.now(datetime.UTC).isoformat(),
        "card": card_key,
        "label": _card_label(card_key),
        "status": status,
        "duration_s": elapsed_s,
        "summary": _extract_summary(card_key, data) if status == "ok" else error_msg,
        "bust": bust,
    }

    path = _activity_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing
    entries: list[dict] = []
    if path.exists():
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            entries = []

    entries.append(entry)

    # Trim to max
    if len(entries) > _ACTIVITY_MAX:
        entries = entries[-_ACTIVITY_MAX:]

    try:
        path.write_text(json.dumps(entries, default=str), encoding="utf-8")
    except IOError as e:
        logger.warning("Failed to write audit activity: %s", e)


def record_event(
    project_root: Path,
    label: str,
    summary: str,
    *,
    detail: dict | None = None,
    card: str = "event",
    action: str | None = None,
    target: str | None = None,
    before_state: dict | None = None,
    after_state: dict | None = None,
) -> None:
    """Record a user-initiated action in the audit activity log.

    Unlike ``record_scan_activity`` (scan computations), this logs
    arbitrary events like finding dismissals, so they appear
    in the Debugging → Audit Log tab.

    Optional audit fields (when provided, enrich the log entry):
        action       — verb: created, modified, deleted, renamed, etc.
        target       — what was acted on (file path, resource name)
        before_state — state before the change (size, lines, hash, etc.)
        after_state  — state after the change
    """
    import datetime

    entry = {
        "ts": time.time(),
        "iso": datetime.datetime.now(datetime.UTC).isoformat(),
        "card": card,
        "label": label,
        "status": "ok",
        "duration_s": 0,
        "summary": summary,
        "bust": False,
    }
    if detail:
        entry["detail"] = detail
    if action:
        entry["action"] = action
    if target:
        entry["target"] = target
    if before_state:
        entry["before"] = before_state
    if after_state:
        entry["after"] = after_state

    path = _activity_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    entries: list[dict] = []
    if path.exists():
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            entries = []

    entries.append(entry)
    if len(entries) > _ACTIVITY_MAX:
        entries = entries[-_ACTIVITY_MAX:]

    try:
        path.write_text(json.dumps(entries, default=str), encoding="utf-8")
    except IOError as e:
        logger.warning("Failed to write audit event: %s", e)


# ── Loading ─────────────────────────────────────────────────────────


def load_activity(project_root: Path, n: int = 50) -> list[dict]:
    """Load the latest N audit scan activity entries.

    If no activity file exists yet but cached data does, seed
    the activity log from existing cache metadata so the user
    sees historical scan info rather than an empty log.
    """
    import datetime

    path = _activity_path(project_root)
    entries: list[dict] = []

    if path.exists():
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            entries = []

    # ── Seed from cache if empty ────────────────────────────────
    if not entries:
        from src.core.services.devops_cache import _load_cache

        cache = _load_cache(project_root)
        if cache:
            for card_key, entry in cache.items():
                cached_at = entry.get("cached_at", 0)
                elapsed = entry.get("elapsed_s", 0)
                if not cached_at:
                    continue
                iso = datetime.datetime.fromtimestamp(
                    cached_at, tz=datetime.UTC
                ).isoformat()
                entries.append({
                    "ts": cached_at,
                    "iso": iso,
                    "card": card_key,
                    "label": _card_label(card_key),
                    "status": "ok",
                    "duration_s": elapsed,
                    "summary": "loaded from cache (historical)",
                    "bust": False,
                })
            # Sort by timestamp
            entries.sort(key=lambda e: e.get("ts", 0))
            # Persist the seeded data
            if entries:
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(
                        json.dumps(entries, default=str), encoding="utf-8"
                    )
                except IOError:
                    pass

    return entries[-n:]
