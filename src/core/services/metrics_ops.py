"""
Metrics & project health — channel-independent service.

Aggregates health signals from ALL integrations into a unified
project score and actionable recommendations. This is the
"Total Solution Intelligence" layer.

Integrations consumed:
- Git (git_ops)
- Docker (docker_ops)
- CI/CD (ci_ops)
- Packages (package_ops)
- Environment (env_ops)
- Quality (quality_ops)
"""

from __future__ import annotations

import logging
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Scoring weights ─────────────────────────────────────────────

_WEIGHTS = {
    "git": 15,
    "docker": 10,
    "ci": 20,
    "packages": 15,
    "env": 10,
    "quality": 20,
    "structure": 10,
}

_MAX_SCORE = sum(_WEIGHTS.values())  # 100


# ═══════════════════════════════════════════════════════════════════
#  Probes — each returns a score (0-1) and findings
# ═══════════════════════════════════════════════════════════════════


def _probe_git(project_root: Path) -> dict:
    """Git health: is repo clean? on main? has remote?"""
    try:
        from src.core.services.git_ops import git_status

        result = git_status(project_root)

        score = 1.0
        findings: list[str] = []
        recommendations: list[str] = []

        if result.get("error"):
            return {"score": 0, "findings": ["Not a git repository"], "recommendations": ["Initialize git: git init"]}

        if result.get("dirty"):
            score -= 0.3
            findings.append("Working tree has uncommitted changes")
            recommendations.append("Commit or stash changes")

        if not result.get("remote"):
            score -= 0.3
            findings.append("No remote configured")
            recommendations.append("Add GitHub remote: git remote add origin <url>")

        if result.get("branch") not in ("main", "master"):
            score -= 0.1
            findings.append(f"On branch '{result.get('branch')}' (not main)")

        if not findings:
            findings.append("Clean, on main, remote configured")

        return {"score": max(0, score), "findings": findings, "recommendations": recommendations}

    except Exception as e:
        logger.debug("Git probe failed: %s", e)
        return {"score": 0, "findings": [f"Git probe error: {e}"], "recommendations": []}


def _probe_docker(project_root: Path) -> dict:
    """Docker health: Dockerfile exists? compose? daemon running?"""
    try:
        from src.core.services.docker_ops import docker_status

        result = docker_status(project_root)

        score = 0.0
        findings: list[str] = []
        recommendations: list[str] = []

        if result.get("available"):
            score += 0.3
            findings.append(f"Docker {result.get('version', '?')} available")
        else:
            findings.append("Docker not available")
            recommendations.append("Install Docker")
            return {"score": 0, "findings": findings, "recommendations": recommendations}

        if result.get("daemon_running"):
            score += 0.2
        else:
            findings.append("Docker daemon not running")
            recommendations.append("Start Docker daemon")

        if result.get("dockerfiles"):
            score += 0.3
            findings.append(f"{len(result['dockerfiles'])} Dockerfile(s)")
        else:
            recommendations.append("Generate Dockerfile: controlplane docker generate dockerfile <stack>")

        if result.get("compose_file"):
            score += 0.2
            findings.append("Compose file found")
        else:
            recommendations.append("Generate compose: controlplane docker generate compose")

        return {"score": min(1.0, score), "findings": findings, "recommendations": recommendations}

    except Exception as e:
        logger.debug("Docker probe failed: %s", e)
        return {"score": 0, "findings": [f"Docker probe error: {e}"], "recommendations": []}


def _probe_ci(project_root: Path) -> dict:
    """CI health: has CI? workflows valid? coverage?"""
    try:
        from src.core.services.ci_ops import ci_status, ci_workflows

        status = ci_status(project_root)

        score = 0.0
        findings: list[str] = []
        recommendations: list[str] = []

        if not status.get("has_ci"):
            findings.append("No CI/CD configured")
            recommendations.append("Generate CI: controlplane ci generate ci")
            return {"score": 0, "findings": findings, "recommendations": recommendations}

        score += 0.4
        providers = status.get("providers", [])
        for p in providers:
            findings.append(f"{p['name']}: {p['workflows']} workflow(s)")

        # Check workflow quality
        wf_result = ci_workflows(project_root)
        total_issues = 0
        for wf in wf_result.get("workflows", []):
            issues = wf.get("issues", [])
            total_issues += len(issues)

        if total_issues == 0:
            score += 0.4
            findings.append("All workflows pass audit")
        else:
            score += 0.2
            findings.append(f"{total_issues} workflow issue(s) detected")
            recommendations.append("Run: controlplane ci workflows (to see details)")

        # Has both push and PR triggers?
        all_triggers: set[str] = set()
        for wf in wf_result.get("workflows", []):
            all_triggers.update(wf.get("triggers", []))

        if "push" in all_triggers and "pull_request" in all_triggers:
            score += 0.2
            findings.append("CI triggers on push + PR")
        elif all_triggers:
            score += 0.1
            findings.append(f"CI triggers: {', '.join(all_triggers)}")

        return {"score": min(1.0, score), "findings": findings, "recommendations": recommendations}

    except Exception as e:
        logger.debug("CI probe failed: %s", e)
        return {"score": 0, "findings": [f"CI probe error: {e}"], "recommendations": []}


def _probe_packages(project_root: Path) -> dict:
    """Package health: has lock file? outdated count?"""
    try:
        from src.core.services.package_ops import package_status, package_outdated

        status = package_status(project_root)

        score = 0.0
        findings: list[str] = []
        recommendations: list[str] = []

        if not status.get("has_packages"):
            findings.append("No package managers detected")
            return {"score": 0.5, "findings": findings, "recommendations": recommendations}

        score += 0.3
        for pm in status.get("managers", []):
            findings.append(f"{pm['name']}: {', '.join(pm['dependency_files'])}")

            if pm["has_lock"]:
                score += 0.2
                findings.append(f"  Lock file: {', '.join(pm['lock_files'])}")
            else:
                recommendations.append(f"Generate lock file for {pm['name']}")

        # Check outdated (quick, non-blocking)
        try:
            outdated = package_outdated(project_root)
            if outdated.get("ok"):
                count = outdated.get("count", 0)
                if count == 0:
                    score += 0.3
                    findings.append("All packages up to date")
                elif count <= 3:
                    score += 0.2
                    findings.append(f"{count} outdated package(s)")
                else:
                    score += 0.1
                    findings.append(f"{count} outdated packages")
                    recommendations.append("Run: controlplane packages outdated")
        except Exception:
            score += 0.1  # Couldn't check, give partial credit

        return {"score": min(1.0, score), "findings": findings, "recommendations": recommendations}

    except Exception as e:
        logger.debug("Packages probe failed: %s", e)
        return {"score": 0, "findings": [f"Packages probe error: {e}"], "recommendations": []}


def _probe_env(project_root: Path) -> dict:
    """Environment health: has .env? has .env.example? in sync?"""
    try:
        from src.core.services.env_ops import env_status, env_diff

        status = env_status(project_root)

        score = 0.0
        findings: list[str] = []
        recommendations: list[str] = []

        files = status.get("files", [])
        if not files:
            findings.append("No .env files")
            recommendations.append("Create .env for local configuration")
            return {"score": 0.5, "findings": findings, "recommendations": recommendations}

        score += 0.3
        for f in files:
            findings.append(f"{f['name']}: {f['var_count']} variables")

        if status.get("has_env"):
            score += 0.2
        else:
            recommendations.append("Create .env file")

        if status.get("has_example"):
            score += 0.2
            # Check sync
            try:
                diff = env_diff(project_root)
                if diff.get("ok") and diff.get("in_sync"):
                    score += 0.3
                    findings.append(".env ↔ .env.example: in sync")
                elif diff.get("ok"):
                    missing = diff.get("missing", [])
                    if missing:
                        findings.append(f".env missing {len(missing)} var(s) from .env.example")
                        recommendations.append("Run: controlplane infra env diff")
            except Exception:
                pass
        else:
            recommendations.append("Generate .env.example: controlplane infra env generate-example")

        return {"score": min(1.0, score), "findings": findings, "recommendations": recommendations}

    except Exception as e:
        logger.debug("Env probe failed: %s", e)
        return {"score": 0, "findings": [f"Env probe error: {e}"], "recommendations": []}


def _probe_quality(project_root: Path) -> dict:
    """Quality health: has lint/type/test tools? configured?"""
    try:
        from src.core.services.quality_ops import quality_status

        # Detect stacks for relevance filtering
        stack_names: list[str] = []
        try:
            from src.core.config.loader import load_project
            from src.core.config.stack_loader import discover_stacks
            from src.core.services.detection import detect_modules

            project = load_project(project_root / "project.yml")
            stacks = discover_stacks(project_root / "stacks")
            detection = detect_modules(project, project_root, stacks)
            stack_names = list({m.effective_stack for m in detection.modules if m.effective_stack})
        except Exception:
            pass

        status = quality_status(project_root, stack_names=stack_names or None)

        score = 0.0
        findings: list[str] = []
        recommendations: list[str] = []

        if not status.get("has_quality"):
            findings.append("No quality tools available")
            recommendations.append("Install quality tools: pip install ruff mypy pytest")
            return {"score": 0, "findings": findings, "recommendations": recommendations}

        categories = status.get("categories", {})

        if categories.get("lint", 0) > 0:
            score += 0.3
            findings.append("Linter available")
        else:
            recommendations.append("Add linter (ruff, eslint)")

        if categories.get("typecheck", 0) > 0:
            score += 0.25
            findings.append("Type-checker available")
        else:
            recommendations.append("Add type-checker (mypy, tsc)")

        if categories.get("test", 0) > 0:
            score += 0.25
            findings.append("Test framework available")
        else:
            recommendations.append("Add test framework (pytest, jest)")

        if categories.get("format", 0) > 0:
            score += 0.2
            findings.append("Formatter available")

        return {"score": min(1.0, score), "findings": findings, "recommendations": recommendations}

    except Exception as e:
        logger.debug("Quality probe failed: %s", e)
        return {"score": 0, "findings": [f"Quality probe error: {e}"], "recommendations": []}


def _probe_structure(project_root: Path) -> dict:
    """Project structure health: has project.yml? README? .gitignore?"""
    score = 0.0
    findings: list[str] = []
    recommendations: list[str] = []

    checks = [
        ("project.yml", 0.3, "Project configuration"),
        ("README.md", 0.2, "README documentation"),
        (".gitignore", 0.2, ".gitignore"),
        ("LICENSE", 0.1, "License file"),
        ("pyproject.toml", 0.1, "pyproject.toml"),
        ("Dockerfile", 0.1, "Dockerfile"),
    ]

    for filename, weight, label in checks:
        if (project_root / filename).is_file():
            score += weight
            findings.append(f"✓ {label}")
        else:
            recommendations.append(f"Add {filename}")

    return {"score": min(1.0, score), "findings": findings, "recommendations": recommendations}


# ═══════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════


def project_health(project_root: Path) -> dict:
    """Run all health probes and compute a unified project score.

    Returns:
        {
            "score": float (0-100),
            "grade": str (A/B/C/D/F),
            "timestamp": str,
            "probes": {
                "git": {score, findings, recommendations},
                "docker": {...},
                ...
            },
            "recommendations": [str, ...],   # top recommendations
        }
    """
    probes: dict[str, dict] = {}

    probe_fns = {
        "git": _probe_git,
        "docker": _probe_docker,
        "ci": _probe_ci,
        "packages": _probe_packages,
        "env": _probe_env,
        "quality": _probe_quality,
        "structure": _probe_structure,
    }

    total_score = 0.0

    for probe_id, fn in probe_fns.items():
        try:
            result = fn(project_root)
            probes[probe_id] = result
            weighted = result.get("score", 0) * _WEIGHTS.get(probe_id, 0)
            total_score += weighted
        except Exception as e:
            logger.debug("Probe %s failed: %s", probe_id, e)
            probes[probe_id] = {"score": 0, "findings": [f"Error: {e}"], "recommendations": []}

    # Compute grade
    if total_score >= 90:
        grade = "A"
    elif total_score >= 75:
        grade = "B"
    elif total_score >= 60:
        grade = "C"
    elif total_score >= 40:
        grade = "D"
    else:
        grade = "F"

    # Gather all recommendations, sorted by probe weight
    all_recs: list[str] = []
    for probe_id in sorted(_WEIGHTS, key=lambda k: _WEIGHTS[k], reverse=True):
        probe = probes.get(probe_id, {})
        for rec in probe.get("recommendations", []):
            if rec not in all_recs:
                all_recs.append(rec)

    return {
        "score": round(total_score, 1),
        "max_score": _MAX_SCORE,
        "grade": grade,
        "timestamp": datetime.now(UTC).isoformat(),
        "probes": probes,
        "recommendations": all_recs[:10],  # Top 10
    }


def project_summary(project_root: Path) -> dict:
    """Quick project summary without running the expensive probes.

    Returns:
        {
            "name": str,
            "root": str,
            "stacks": [str],
            "modules": int,
            "integrations": {name: available}
        }
    """
    name = "Unknown"
    stacks: list[str] = []
    module_count = 0

    try:
        from src.core.config.loader import load_project
        from src.core.config.stack_loader import discover_stacks
        from src.core.services.detection import detect_modules

        project = load_project(project_root / "project.yml")
        name = project.name
        all_stacks = discover_stacks(project_root / "stacks")
        detection = detect_modules(project, project_root, all_stacks)
        module_count = len(detection.modules)
        stacks = list({m.effective_stack for m in detection.modules if m.effective_stack})
    except Exception:
        pass

    # Quick integration availability check
    integrations: dict[str, bool] = {
        "git": (project_root / ".git").is_dir(),
        "docker": (project_root / "Dockerfile").is_file(),
        "ci": (project_root / ".github" / "workflows").is_dir(),
        "packages": any(
            (project_root / f).is_file()
            for f in ("pyproject.toml", "package.json", "Cargo.toml", "go.mod")
        ),
        "env": any(
            (project_root / f).is_file()
            for f in (".env", ".env.example")
        ),
    }

    return {
        "name": name,
        "root": str(project_root),
        "stacks": stacks,
        "modules": module_count,
        "integrations": integrations,
    }
