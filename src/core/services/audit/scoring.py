"""
Scoring — compute Complexity and Quality master scores.

Scores are computed from L0+L1 data, optionally enriched with L2
analysis when available.  Score history is tracked in
``state/audit_scores.json`` for trend analysis.
"""

from __future__ import annotations

import json
import logging
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _clamp(value: float, low: float = 0.0, high: float = 10.0) -> float:
    return max(low, min(high, value))


# ═══════════════════════════════════════════════════════════════════
#  Complexity Score
# ═══════════════════════════════════════════════════════════════════


def _complexity_score(
    l0: dict,
    l1_deps: dict,
    l1_struct: dict,
    *,
    l2_struct: dict | None = None,
) -> dict:
    """Compute complexity score (1-10).

    Dimensions:
        tech_diversity (25%)   — How many languages/runtimes coexist
        module_count (15%)     — Number of distinct modules
        dependency_count (20%) — Total declared dependencies
        infra_layers (15%)     — Docker + K8s + TF + CI
        integrations (15%)     — External client count
        crossovers (10%)       — Cross-ecosystem patterns

    L2 enrichment (when available):
        - module_count uses L2 module boundary analysis
        - dependency_count factors in actual import usage
    """
    # Tech diversity: count unique ecosystems
    ecosystems = l1_deps.get("ecosystems", {})
    eco_count = len([e for e, c in ecosystems.items() if c > 0])
    tech_diversity = min(eco_count * 2.5, 10.0)

    # Module count — use L2 if available for more accurate count
    if l2_struct and "modules" in l2_struct:
        mod_count = len(l2_struct["modules"])
    else:
        modules = l0.get("modules", [])
        mod_count = len(modules)
    module_score = min(mod_count * 0.5, 10.0)  # 20 modules = 10

    # Dependency count — L2 can tell us actual usage
    total_deps = l1_deps.get("total", 0)
    if l2_struct and "import_graph" in l2_struct:
        # Use actual external dep count from import graph
        actual_deps = len(l2_struct["import_graph"].get("external_deps", {}))
        # Weight: declared deps + actual import diversity
        effective_deps = max(total_deps, actual_deps)
    else:
        effective_deps = total_deps

    if effective_deps <= 5:
        dep_score = 1.0
    elif effective_deps <= 15:
        dep_score = 3.0
    elif effective_deps <= 30:
        dep_score = 5.0
    elif effective_deps <= 60:
        dep_score = 7.0
    else:
        dep_score = min(9.0, 7.0 + (effective_deps - 60) * 0.02)

    # Infrastructure layers
    infra_count = sum(1 for k in ("has_docker", "has_iac", "has_ci") if l1_struct.get(k))
    infra_score = infra_count * 3.3

    # External integrations
    categories = l1_deps.get("categories", {})
    client_count = categories.get("client", 0) + categories.get("database", 0)
    integration_score = min(client_count * 2.0, 10.0)

    # Crossovers
    crossovers = l1_deps.get("crossovers", [])
    crossover_score = min(len(crossovers) * 3.0, 10.0)

    # Weighted total
    total = (
        tech_diversity * 0.25
        + module_score * 0.15
        + dep_score * 0.20
        + infra_score * 0.15
        + integration_score * 0.15
        + crossover_score * 0.10
    )

    return {
        "score": round(_clamp(total), 1),
        "breakdown": {
            "tech_diversity": {"score": round(tech_diversity, 1), "weight": 0.25, "detail": f"{eco_count} ecosystem(s)"},
            "module_count": {"score": round(module_score, 1), "weight": 0.15, "detail": f"{mod_count} module(s)"},
            "dependency_count": {"score": round(dep_score, 1), "weight": 0.20, "detail": f"{effective_deps} dependencies"},
            "infra_layers": {"score": round(infra_score, 1), "weight": 0.15, "detail": f"{infra_count} infra layer(s)"},
            "integrations": {"score": round(integration_score, 1), "weight": 0.15, "detail": f"{client_count} client(s)"},
            "crossovers": {"score": round(crossover_score, 1), "weight": 0.10, "detail": f"{len(crossovers)} crossover(s)"},
        },
    }


# ═══════════════════════════════════════════════════════════════════
#  Quality Score
# ═══════════════════════════════════════════════════════════════════


def _quality_score(
    l0: dict,
    l1_deps: dict,
    l1_struct: dict,
    *,
    l2_quality: dict | None = None,
    l2_repo: dict | None = None,
    l2_risks: dict | None = None,
) -> dict:
    """Compute quality score (1-10).

    Base dimensions (L0+L1):
        documentation (15%)    — docs/ exists, README present
        testing (15%)          — test framework detected, tests/ exists
        tooling (15%)          — linters, formatters, type checkers
        security (15%)         — security tools available
        structure (10%)        — clean module boundaries, venv setup

    L2-enriched dimensions (when available):
        code_health (15%)      — from l2_quality overall score
        repo_health (5%)       — from l2_repo health score
        risk_posture (10%)     — from l2_risks posture score
    """
    # ── Documentation ───────────────────────────────────────
    doc_score = 0.0
    if l1_struct.get("has_docs"):
        doc_score += 5.0
    modules = l0.get("modules", [])
    if any("docs" in m.get("name", "").lower() for m in modules):
        doc_score += 2.0
    manifests = l0.get("manifests", [])
    if manifests:
        doc_score += 1.0
    doc_score = min(doc_score, 10.0)

    # ── Testing ─────────────────────────────────────────────
    test_score = 0.0
    if l1_struct.get("has_tests"):
        test_score += 5.0
    categories = l1_deps.get("categories", {})
    if categories.get("testing", 0) > 0:
        test_score += 3.0
    if categories.get("testing", 0) > 2:
        test_score += 2.0
    test_score = min(test_score, 10.0)

    # ── Tooling ─────────────────────────────────────────────
    tool_score = 0.0
    tools = l0.get("tools", [])
    tool_ids = {t["id"] for t in tools if t.get("available")}
    if "ruff" in tool_ids or "eslint" in tool_ids:
        tool_score += 3.0
    if "black" in tool_ids or "prettier" in tool_ids:
        tool_score += 2.0
    if "mypy" in tool_ids:
        tool_score += 3.0
    if categories.get("devtool", 0) > 0:
        tool_score += 2.0
    tool_score = min(tool_score, 10.0)

    # ── Security ────────────────────────────────────────────
    sec_score = 0.0
    if categories.get("security", 0) > 0:
        sec_score += 4.0
    sec_tools = {"bandit", "safety", "pip-audit"}
    dep_names = {d["name"].lower() for d in l1_deps.get("dependencies", [])}
    if dep_names & sec_tools:
        sec_score += 3.0
    project_root = Path(l0.get("project_root", "."))
    if (project_root / ".gitignore").is_file():
        sec_score += 2.0
    sec_score = min(sec_score, 10.0)

    # ── Structure ───────────────────────────────────────────
    struct_score = 0.0
    venv = l0.get("venv", {})
    if venv.get("in_venv"):
        struct_score += 3.0
    if len(modules) > 1:
        struct_score += 2.0
    if l1_struct.get("has_ci"):
        struct_score += 2.0
    if l1_struct.get("entrypoints"):
        struct_score += 2.0
    struct_score = min(struct_score, 10.0)

    # ── L2-enriched dimensions ──────────────────────────────
    has_l2 = any(x is not None for x in (l2_quality, l2_repo, l2_risks))

    if has_l2:
        # Code health from L2 quality analysis
        code_health = 5.0  # default fallback
        if l2_quality:
            summary = l2_quality.get("summary", {})
            code_health = summary.get("overall_score", 5.0)

        # Repo health from L2 repo analysis
        repo_health = 5.0
        if l2_repo:
            health = l2_repo.get("health", {})
            repo_health = health.get("score", 5.0)

        # Risk posture from L2 risk analysis
        risk_score = 5.0
        if l2_risks:
            posture = l2_risks.get("posture", {})
            risk_score = posture.get("score", 5.0)

        # L2-enriched weights
        total = (
            doc_score * 0.15
            + test_score * 0.15
            + tool_score * 0.15
            + sec_score * 0.10
            + struct_score * 0.10
            + code_health * 0.15
            + repo_health * 0.05
            + risk_score * 0.15
        )

        breakdown = {
            "documentation": {"score": round(doc_score, 1), "weight": 0.15, "detail": "Docs & README"},
            "testing": {"score": round(test_score, 1), "weight": 0.15, "detail": "Test framework & coverage"},
            "tooling": {"score": round(tool_score, 1), "weight": 0.15, "detail": "Linters, formatters, types"},
            "security": {"score": round(sec_score, 1), "weight": 0.10, "detail": "Security tooling & posture"},
            "structure": {"score": round(struct_score, 1), "weight": 0.10, "detail": "Project organization"},
            "code_health": {"score": round(code_health, 1), "weight": 0.15, "detail": "AST-based code quality", "source": "L2"},
            "repo_health": {"score": round(repo_health, 1), "weight": 0.05, "detail": "Git history & hygiene", "source": "L2"},
            "risk_posture": {"score": round(risk_score, 1), "weight": 0.15, "detail": "Aggregated risk level", "source": "L2"},
        }
    else:
        # L0+L1 only weights (equal)
        total = (
            doc_score * 0.20
            + test_score * 0.20
            + tool_score * 0.20
            + sec_score * 0.20
            + struct_score * 0.20
        )
        breakdown = {
            "documentation": {"score": round(doc_score, 1), "weight": 0.20, "detail": "Docs & README"},
            "testing": {"score": round(test_score, 1), "weight": 0.20, "detail": "Test framework & coverage"},
            "tooling": {"score": round(tool_score, 1), "weight": 0.20, "detail": "Linters, formatters, types"},
            "security": {"score": round(sec_score, 1), "weight": 0.20, "detail": "Security tooling & posture"},
            "structure": {"score": round(struct_score, 1), "weight": 0.20, "detail": "Project organization"},
        }

    return {
        "score": round(_clamp(total), 1),
        "enriched": has_l2,
        "breakdown": breakdown,
    }


# ═══════════════════════════════════════════════════════════════════
#  Score History
# ═══════════════════════════════════════════════════════════════════

_HISTORY_FILE = ".state/audit_scores.json"
_MAX_HISTORY = 100  # Keep last 100 snapshots


def _load_history(project_root: Path) -> list[dict]:
    """Load score history from state file."""
    path = project_root / _HISTORY_FILE
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError) as e:
        logger.debug("Cannot load score history: %s", e)
    return []


def _save_history(project_root: Path, history: list[dict]) -> None:
    """Save score history atomically."""
    path = project_root / _HISTORY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    # Trim to max
    if len(history) > _MAX_HISTORY:
        history = history[-_MAX_HISTORY:]

    content = json.dumps(history, indent=2, ensure_ascii=False) + "\n"

    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=path.parent, prefix=".scores_", suffix=".tmp",
        )
        tmp = Path(tmp_path)
        try:
            tmp.write_text(content, encoding="utf-8")
            tmp.rename(path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
    except Exception as e:
        logger.warning("Cannot save score history: %s", e)


def _record_snapshot(
    project_root: Path,
    complexity: dict,
    quality: dict,
    enriched: bool,
) -> dict:
    """Record a score snapshot in history and return the snapshot."""
    snapshot = {
        "timestamp": time.time(),
        "complexity": complexity["score"],
        "quality": quality["score"],
        "enriched": enriched,
    }

    history = _load_history(project_root)
    history.append(snapshot)
    _save_history(project_root, history)

    return snapshot


def _compute_trend(history: list[dict]) -> dict:
    """Compute score trend from history.

    Returns:
        {
            "snapshots": int,
            "complexity_trend": "up" | "down" | "stable" | "new",
            "quality_trend": "up" | "down" | "stable" | "new",
            "complexity_delta": float,
            "quality_delta": float,
        }
    """
    if len(history) < 2:
        return {
            "snapshots": len(history),
            "complexity_trend": "new",
            "quality_trend": "new",
            "complexity_delta": 0.0,
            "quality_delta": 0.0,
        }

    # Compare latest to previous
    latest = history[-1]
    previous = history[-2]

    c_delta = latest.get("complexity", 0) - previous.get("complexity", 0)
    q_delta = latest.get("quality", 0) - previous.get("quality", 0)

    def _trend(delta: float) -> str:
        if abs(delta) < 0.2:
            return "stable"
        return "up" if delta > 0 else "down"

    return {
        "snapshots": len(history),
        "complexity_trend": _trend(c_delta),
        "quality_trend": _trend(q_delta),
        "complexity_delta": round(c_delta, 1),
        "quality_delta": round(q_delta, 1),
    }


# ═══════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════


def audit_scores(
    project_root: Path,
    l0: dict | None = None,
    l1_deps: dict | None = None,
    l1_struct: dict | None = None,
    *,
    l2_struct: dict | None = None,
    l2_quality_data: dict | None = None,
    l2_repo_data: dict | None = None,
    l2_risks_data: dict | None = None,
    record: bool = True,
) -> dict:
    """Compute master scores from available analysis data.

    If layer results are not provided, computes L0+L1 on the fly.
    L2 data is optional — when provided, the quality score gains
    additional dimensions (code_health, repo_health, risk_posture).

    Args:
        project_root: Project root path.
        l0: Pre-computed L0 result (optional).
        l1_deps: Pre-computed L1 deps result (optional).
        l1_struct: Pre-computed L1 structure result (optional).
        l2_struct: Pre-computed L2 structure result (optional).
        l2_quality_data: Pre-computed L2 quality result (optional).
        l2_repo_data: Pre-computed L2 repo result (optional).
        l2_risks_data: Pre-computed L2 risk result (optional).
        record: Whether to record this score in history.

    Returns:
        {
            "_meta": AuditMeta,
            "complexity": {score, breakdown},
            "quality": {score, enriched, breakdown},
            "trend": {snapshots, complexity_trend, quality_trend, ...},
            "history": [{timestamp, complexity, quality}, ...],
        }
    """
    from src.core.services.audit.l0_detection import l0_system_profile
    from src.core.services.audit.l1_classification import (
        l1_dependencies,
        l1_structure,
    )
    from src.core.services.audit.models import wrap_result

    started = time.time()

    # Compute L0+L1 if not provided
    if l0 is None:
        l0 = l0_system_profile(project_root)
    if l1_deps is None:
        l1_deps = l1_dependencies(project_root)
    if l1_struct is None:
        l1_struct = l1_structure(project_root)

    # Compute scores
    complexity = _complexity_score(
        l0, l1_deps, l1_struct,
        l2_struct=l2_struct,
    )
    quality = _quality_score(
        l0, l1_deps, l1_struct,
        l2_quality=l2_quality_data,
        l2_repo=l2_repo_data,
        l2_risks=l2_risks_data,
    )

    # History tracking
    if record:
        _record_snapshot(
            project_root, complexity, quality,
            enriched=quality.get("enriched", False),
        )

    history = _load_history(project_root)
    trend = _compute_trend(history)

    data = {
        "complexity": complexity,
        "quality": quality,
        "trend": trend,
        "history": history[-20:],  # Last 20 for sparkline rendering
    }
    return wrap_result(data, "L1", "scores", started)


def audit_scores_enriched(project_root: Path) -> dict:
    """Compute fully enriched scores using all available L2 data.

    Convenience function that runs L2 analysis and feeds it into
    the scoring engine.  Heavier than audit_scores() — takes ~5-25s.
    """
    from src.core.services.audit.l0_detection import l0_system_profile
    from src.core.services.audit.l1_classification import (
        l1_dependencies,
        l1_structure,
    )
    from src.core.services.audit.l2_quality import l2_quality
    from src.core.services.audit.l2_repo import l2_repo
    from src.core.services.audit.l2_risk import l2_risks
    from src.core.services.audit.l2_structure import l2_structure

    # Run all layers
    l0 = l0_system_profile(project_root)
    l1_deps = l1_dependencies(project_root)
    l1_struct = l1_structure(project_root)
    l2_s = l2_structure(project_root)
    l2_q = l2_quality(project_root)
    l2_r = l2_repo(project_root)
    l2_ri = l2_risks(project_root)

    return audit_scores(
        project_root,
        l0=l0,
        l1_deps=l1_deps,
        l1_struct=l1_struct,
        l2_struct=l2_s,
        l2_quality_data=l2_q,
        l2_repo_data=l2_r,
        l2_risks_data=l2_ri,
    )
