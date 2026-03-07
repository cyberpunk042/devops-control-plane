"""
Wizard data helpers — thin wrappers that collect status from other services.

Each ``_wizard_*`` function calls into its respective service module,
catches exceptions, and returns a safe fallback. These are consumed
by ``wizard_detect()`` to build the one-stop detection snapshot.

Channel-independent: no Flask or HTTP dependency.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Config data ─────────────────────────────────────────────────────


def _wizard_config_data(root: Path) -> dict:
    """Load project config (modules, environments) for wizard use."""
    try:
        from src.core.config.loader import load_project
        proj = load_project(root / "project.yml")
        modules = [{"name": m.name, "path": m.path, "stack": m.stack,
                     "domain": m.domain, "description": m.description}
                    for m in (proj.modules or [])]
        envs = [{"name": e.name, "default": e.default}
                for e in (proj.environments or [])]
        return {"modules": modules, "environments": envs}
    except Exception:
        return {"modules": [], "environments": []}


# ── Infrastructure status ───────────────────────────────────────────


def _wizard_docker_status(root: Path) -> dict:
    """Full docker status (version, daemon, compose) for wizard use."""
    try:
        from src.core.services.docker_ops import docker_status
        return docker_status(root)
    except Exception:
        return {"available": False}


def _wizard_k8s_status(root: Path) -> dict:
    """Full K8s detection (manifests, helm, kustomize, tools) for wizard use."""
    try:
        from src.core.services.k8s.detect import k8s_status
        return k8s_status(root)
    except Exception:
        return {"has_k8s": False, "kubectl": {"available": False, "version": None}}


def _wizard_terraform_status(root: Path) -> dict:
    """Full Terraform detection (CLI, files, providers, modules, backend) for wizard use."""
    try:
        from src.core.services.terraform.ops import terraform_status
        return terraform_status(root)
    except Exception:
        return {"has_terraform": False, "cli": {"available": False, "version": None}}


def _wizard_dns_status(root: Path) -> dict:
    """Full DNS/CDN detection (providers, domains, certs, files) for wizard use."""
    try:
        from src.core.services.dns.cdn_ops import dns_cdn_status
        return dns_cdn_status(root)
    except Exception:
        return {"has_dns": False, "has_cdn": False, "cdn_providers": [], "domains": []}


def _wizard_env_status(root: Path) -> dict:
    """Env var status (files, vars, validation) for wizard use."""
    try:
        from src.core.services.env.ops import env_status
        return env_status(root)
    except Exception:
        return {"files": [], "has_env": False, "has_example": False, "total_vars": 0}


# ── GitHub / Git status ────────────────────────────────────────────


def _wizard_gh_cli_status(root: Path) -> dict:
    """GH CLI status (version, auth, repo) for wizard use."""
    try:
        from src.core.services.git_ops import gh_status
        return gh_status(root)
    except Exception:
        return {"available": False}


def _wizard_gh_environments(root: Path) -> dict:
    """GitHub environments list for wizard use."""
    try:
        r = subprocess.run(
            ["gh", "api", "repos/{owner}/{repo}/environments",
             "--jq", ".environments[].name"],
            cwd=str(root), capture_output=True, timeout=10,
        )
        if r.returncode == 0:
            envs = [
                n.strip()
                for n in r.stdout.decode().strip().split("\n")
                if n.strip()
            ]
            return {"available": True, "environments": envs}
        return {"available": False, "environments": []}
    except Exception:
        return {"available": False, "environments": []}


def _wizard_ci_status(root: Path) -> dict:
    """CI status for wizard use."""
    try:
        from src.core.services.ci_ops import ci_status
        return ci_status(root)
    except Exception:
        return {}


def _wizard_gitignore_analysis(root: Path) -> dict:
    """Gitignore analysis for wizard use."""
    try:
        from src.core.services.security.ops import gitignore_analysis
        return gitignore_analysis(root)
    except Exception:
        return {"exists": False, "coverage": 0, "missing_patterns": []}


def _wizard_gh_user(root: Path) -> dict:
    """Get authenticated GitHub user for wizard use."""
    try:
        from src.core.services.git_ops import gh_user
        return gh_user(root)
    except Exception:
        return {"available": False}


def _wizard_gh_repo_info(root: Path) -> dict:
    """Get repo info (visibility, description) for wizard use."""
    try:
        from src.core.services.git_ops import gh_repo_info
        return gh_repo_info(root)
    except Exception:
        return {"available": False}


def _wizard_git_remotes(root: Path) -> dict:
    """Get all git remotes for wizard use."""
    try:
        from src.core.services.git_ops import git_remotes
        return git_remotes(root)
    except Exception:
        return {"available": True, "remotes": []}


def _wizard_codeowners_content(root: Path) -> str:
    """Read existing CODEOWNERS file content, or empty string if absent."""
    try:
        co_path = root / ".github" / "CODEOWNERS"
        if co_path.is_file():
            return co_path.read_text(encoding="utf-8")
    except Exception:
        pass
    return ""


# ── Pages status ───────────────────────────────────────────────────


def _wizard_pages_status(root: Path) -> dict:
    """Pages status for wizard use — segments, meta, content folders."""
    result: dict = {
        "segments": [],
        "meta": {},
        "content_folders": [],
        "can_auto_init": False,
        "builders_available": [],
    }
    try:
        from src.core.services.pages.engine import get_pages_meta, get_segments
        from src.core.services.pages.discovery import (
            detect_best_builder,
            list_builders_detail,
        )

        # Existing segments (with build status from build.json)
        import json as _json
        segments = get_segments(root)
        pages_dir = root / ".pages"
        result["segments"] = []
        for s in segments:
            seg_data: dict = {
                "name": s.name,
                "builder": s.builder,
                "source": s.source,
                "path": s.path,
                "auto": s.auto,
                "built_at": None,
                "build_duration_ms": None,
                "serve_url": None,
            }
            build_json = pages_dir / s.name / "build.json"
            if build_json.is_file():
                try:
                    bd = _json.loads(build_json.read_text(encoding="utf-8"))
                    seg_data["built_at"] = bd.get("built_at")
                    seg_data["build_duration_ms"] = bd.get("duration_ms")
                    seg_data["serve_url"] = bd.get("serve_url")
                except Exception:
                    pass
            result["segments"].append(seg_data)

        # Pages metadata
        result["meta"] = get_pages_meta(root)

        # Available builders (slim summary)
        builders = list_builders_detail()
        result["builders_available"] = [
            {"name": b["name"], "label": b["label"], "available": b["available"]}
            for b in builders
        ]

        # Content folders — scan directly to avoid circular import
        # with content_listing ↔ content_crypto
        _DEFAULT_DIRS = ["docs", "content", "media", "assets", "archive"]
        dir_names = _DEFAULT_DIRS
        try:
            import yaml as _yaml
            pf = root / "project.yml"
            if pf.is_file():
                data = _yaml.safe_load(pf.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    cf = data.get("content_folders")
                    if isinstance(cf, list) and cf:
                        dir_names = cf
        except Exception:
            pass

        existing_names = {s.name for s in segments}
        for dir_name in dir_names:
            folder_path = root / dir_name
            if not folder_path.is_dir():
                continue
            # Count files (non-recursive, keep it light)
            file_count = sum(1 for f in folder_path.iterdir() if f.is_file())
            builder_name, reason, suggestion = detect_best_builder(folder_path)
            result["content_folders"].append({
                "name": dir_name,
                "file_count": file_count,
                "best_builder": builder_name,
                "reason": reason,
                "suggestion": suggestion,
                "has_segment": dir_name in existing_names,
            })

        # Can auto-init if there are content folders without segments
        uninit = [
            cf for cf in result["content_folders"]
            if not cf["has_segment"]
        ]
        result["can_auto_init"] = len(uninit) > 0

    except Exception:
        logger.exception("_wizard_pages_status failed")
    return result
