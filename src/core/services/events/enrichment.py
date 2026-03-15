"""
Event enrichment — derives semantic types, summaries, and deltas.

Transforms raw mediator computation data into rich timeline events.
Reuses _extract_summary() and _extract_detail() from devops/activity.py.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ── Path → card key (reuses activity subscriber mapping) ─────────────

def _path_to_card_key(path: str) -> str:
    """Convert mediator path to the card key used by _extract_summary."""
    _MAP = {
        "devops.docker": "docker", "devops.k8s": "k8s",
        "devops.git": "git", "devops.github": "github",
        "devops.ci": "ci", "devops.terraform": "terraform",
        "devops.env": "env", "devops.security": "security",
        "devops.packages": "packages", "devops.quality": "quality",
        "devops.testing": "testing", "devops.docs": "docs",
        "devops.dns": "dns", "devops.status": "project-status",
        "github.pulls": "gh-pulls", "github.runs": "gh-runs",
        "github.workflows": "gh-workflows",
        "audit.scores": "audit:scores", "audit.system": "audit:system",
        "audit.deps": "audit:deps", "audit.structure": "audit:structure",
        "audit.clients": "audit:clients",
        "audit.system_deep": "audit:system:deep",
        "audit.l2_structure": "audit:l2:structure",
        "audit.l2_quality": "audit:l2:quality",
        "audit.l2_repo": "audit:l2:repo",
        "audit.l2_risks": "audit:l2:risks",
        "audit.scores_enriched": "audit:scores:enriched",
        "catalog.tools": "tools", "catalog.builders": "builders",
        "catalog.scripts": "scripts", "catalog.pages": "pages",
        "posture.summary": "posture:summary",
        "posture.full": "posture:full",
    }
    if path in _MAP:
        return _MAP[path]
    parts = path.split(".", 1)
    return parts[1] if len(parts) > 1 else path


# ── Semantic event type derivation ───────────────────────────────────

_ACTION_MAP = {
    # Index
    "index.scan": "index.scanned",
    "index.delta": "index.delta.computed",
    "index.files": "index.files.mapped",
    "index.dirs": "index.dirs.mapped",
    "index.paths": "index.paths.mapped",
    "index.classify": "index.classified",
    "index.symbols": "index.symbols.indexed",
    "index.stats": "index.stats.computed",
    "index.view": "index.view.built",
    "index.peek": "index.peek.cached",
    # DevOps
    "devops.docker": "docker.scanned",
    "devops.k8s": "k8s.scanned",
    "devops.terraform": "terraform.scanned",
    "devops.git": "git.status.scanned",
    "devops.github": "github.status.scanned",
    "devops.ci": "ci.scanned",
    "devops.env": "env.scanned",
    "devops.security": "security.scanned",
    "devops.packages": "packages.scanned",
    "devops.quality": "quality.scanned",
    "devops.testing": "testing.scanned",
    "devops.docs": "docs.scanned",
    "devops.dns": "dns.scanned",
    "devops.status": "project.status.computed",
    # Audit
    "audit.scores": "audit.scores.computed",
    "audit.system": "audit.system.scanned",
    "audit.deps": "audit.deps.scanned",
    "audit.structure": "audit.structure.scanned",
    "audit.clients": "audit.clients.scanned",
    "audit.system_deep": "audit.system.deep_scanned",
    "audit.l2_structure": "audit.l2.structure.analyzed",
    "audit.l2_quality": "audit.l2.quality.analyzed",
    "audit.l2_repo": "audit.l2.repo.analyzed",
    "audit.l2_risks": "audit.l2.risks.analyzed",
    "audit.scores_enriched": "audit.scores.enriched",
    # Posture
    "posture.full": "posture.assessed",
    "posture.summary": "posture.scored",
    "posture.platform": "posture.platform.scanned",
    "posture.project": "posture.project.assessed",
    "posture.toolchain": "posture.toolchain.scanned",
    "posture.runtime": "posture.runtime.checked",
    # GitHub
    "github.pulls": "github.pulls.fetched",
    "github.runs": "github.runs.fetched",
    "github.workflows": "github.workflows.fetched",
    # Catalog
    "catalog.tools": "catalog.tools.scanned",
    "catalog.builders": "catalog.builders.scanned",
    "catalog.scripts": "catalog.scripts.scanned",
    "catalog.pages": "pages.scanned",
}


def derive_event_type(path: str) -> str:
    """Derive semantic event type from a mediator path."""
    if path in _ACTION_MAP:
        return _ACTION_MAP[path]
    # Fallback: domain.suffix.computed
    if "." in path:
        return f"{path}.computed"
    return f"{path}.computed"


# ── Summary extraction ───────────────────────────────────────────────

def extract_summary(path: str, data: Any) -> str:
    """Extract a human-readable summary from resolver result.

    Reuses _extract_summary from devops/activity.py which already
    handles every card key with rich formatting.
    """
    if not isinstance(data, dict):
        if isinstance(data, list):
            return f"{path.split('.')[-1]}: {len(data)} entries"
        return path.split(".")[-1]

    try:
        from src.core.services.devops.activity import _extract_summary
        card_key = _path_to_card_key(path)
        result = _extract_summary(card_key, data)
        if result and result != "completed":
            return result
    except Exception:
        pass

    # Fallback: try common fields
    for key in ("summary", "label", "message"):
        val = data.get(key)
        if isinstance(val, str) and val:
            return val[:120]

    return path.split(".")[-1]


# ── Result summary extraction ────────────────────────────────────────

def extract_result_summary(path: str, data: Any) -> dict:
    """Extract key metrics from resolver result as a compact dict."""
    if not isinstance(data, dict):
        if isinstance(data, list):
            return {"count": len(data)}
        return {}

    try:
        from src.core.services.devops.activity import _extract_detail
        card_key = _path_to_card_key(path)
        detail = _extract_detail(card_key, data)
        if detail:
            return detail
    except Exception:
        pass

    # Fallback: extract count-like fields
    result = {}
    for key in ("total", "count", "findings", "score"):
        if key in data:
            val = data[key]
            if isinstance(val, (int, float)):
                result[key] = val
            elif isinstance(val, list):
                result[f"{key}_count"] = len(val)
    return result


# ── Delta detection ──────────────────────────────────────────────────

def compute_delta(path: str, new_data: Any, old_entry: Any) -> dict | None:
    """Compare old cached result vs new result. Returns delta or None.

    old_entry is a CacheEntry object with .data attribute, or None.
    """
    if old_entry is None:
        return {"status": "new"}  # first computation

    old_data = old_entry.data if hasattr(old_entry, "data") else old_entry

    if not isinstance(new_data, dict) or not isinstance(old_data, dict):
        return None

    delta = {}

    # Index delta — use ScanDelta directly if available
    if path == "index.delta":
        if hasattr(new_data, "added"):
            added = len(new_data.added) if hasattr(new_data.added, "__len__") else 0
            removed = len(new_data.removed) if hasattr(new_data.removed, "__len__") else 0
            modified = len(new_data.modified) if hasattr(new_data.modified, "__len__") else 0
            if added or removed or modified:
                return {"added": added, "removed": removed, "modified": modified}
        return None

    # Audit scores — compare scores
    if path in ("audit.scores", "audit.scores_enriched"):
        old_cx = old_data.get("complexity", {}).get("score")
        new_cx = new_data.get("complexity", {}).get("score")
        old_qu = old_data.get("quality", {}).get("score")
        new_qu = new_data.get("quality", {}).get("score")
        if old_cx is not None and new_cx is not None and old_cx != new_cx:
            delta["complexity"] = {"was": old_cx, "now": new_cx, "delta": round(new_cx - old_cx, 2)}
        if old_qu is not None and new_qu is not None and old_qu != new_qu:
            delta["quality"] = {"was": old_qu, "now": new_qu, "delta": round(new_qu - old_qu, 2)}
        return delta or None

    # Security — compare finding count
    if path == "devops.security":
        old_count = old_data.get("finding_count", len(old_data.get("findings", [])))
        new_count = new_data.get("finding_count", len(new_data.get("findings", [])))
        if old_count != new_count:
            return {"findings": {"was": old_count, "now": new_count, "delta": new_count - old_count}}
        return None

    # Docker — compare container/image count
    if path == "devops.docker":
        for key in ("dockerfiles", "compose_services"):
            old_val = old_data.get(key, [])
            new_val = new_data.get(key, [])
            if isinstance(old_val, list) and isinstance(new_val, list):
                if len(old_val) != len(new_val):
                    delta[key] = {"was": len(old_val), "now": len(new_val)}
        return delta or None

    # Catalog tools — compare available/missing
    if path == "catalog.tools":
        old_avail = old_data.get("available", 0)
        new_avail = new_data.get("available", 0)
        if old_avail != new_avail:
            return {"available": {"was": old_avail, "now": new_avail}}
        return None

    # Generic: compare top-level counts
    for key in ("total", "count", "file_count", "dir_count"):
        if key in old_data and key in new_data:
            if old_data[key] != new_data[key]:
                delta[key] = {"was": old_data[key], "now": new_data[key]}
    return delta or None
