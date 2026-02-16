"""
GitHub environment management — list, create, cleanup, seed.

Channel-independent: no Flask or HTTP dependency.
Requires ``gh`` CLI for GitHub API operations.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from src.core.services.audit_helpers import make_auditor
from src.core.services.secrets_ops import gh_repo_flag, env_path_for

logger = logging.getLogger(__name__)

_audit = make_auditor("secrets")


def list_environments(project_root: Path) -> dict:
    """List GitHub deployment environments for the current repo."""
    result: dict = {"available": False, "environments": [], "reason": None}

    if not shutil.which("gh"):
        result["reason"] = "gh CLI not installed"
        return result

    repo_flag = gh_repo_flag(project_root)
    if not repo_flag:
        result["reason"] = "GITHUB_REPOSITORY not configured"
        return result

    repo = repo_flag[1]

    try:
        api_result = subprocess.run(
            ["gh", "api", f"repos/{repo}/environments",
             "--jq", ".environments[].name"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if api_result.returncode == 0:
            names = [
                n.strip()
                for n in api_result.stdout.strip().split("\n")
                if n.strip()
            ]
            result["available"] = True
            result["environments"] = names
        else:
            if "404" in api_result.stderr:
                result["available"] = True
                result["environments"] = []
            else:
                result["reason"] = api_result.stderr.strip()
    except Exception as e:
        result["reason"] = str(e)

    return result


def create_environment(project_root: Path, env_name: str) -> dict:
    """Create a deployment environment on GitHub."""
    if not env_name:
        return {"error": "Environment name required"}

    if not shutil.which("gh"):
        return {"error": "gh CLI not installed"}

    repo_flag = gh_repo_flag(project_root)
    if not repo_flag:
        return {"error": "GITHUB_REPOSITORY not configured"}

    repo = repo_flag[1]

    try:
        result = subprocess.run(
            ["gh", "api", "-X", "PUT",
             f"repos/{repo}/environments/{env_name}"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            logger.info("Created GitHub environment: %s", env_name)
            _audit(
                "🌱 Environment Created",
                f"GitHub environment '{env_name}' created",
                action="created", target=env_name,
            )
            return {"success": True, "name": env_name}
        else:
            return {"error": f"Failed to create environment: {result.stderr.strip()}"}
    except Exception as e:
        return {"error": str(e)}


def cleanup_environment(
    project_root: Path,
    env_name: str,
    *,
    delete_files: bool = True,
    delete_github: bool = False,
) -> dict:
    """Clean up an environment: delete local .env files and optionally GitHub env."""
    if not env_name:
        return {"error": "Environment name required"}

    results: dict = {"name": env_name, "files": [], "github": None}

    if delete_files:
        for suffix in ["", ".vault"]:
            fpath = project_root / f".env.{env_name}{suffix}"
            if fpath.exists():
                fpath.unlink()
                results["files"].append(fpath.name)
                logger.info("Deleted %s", fpath.name)

    if delete_github:
        repo_flag = gh_repo_flag(project_root)
        if repo_flag and shutil.which("gh"):
            repo = repo_flag[1]
            try:
                result = subprocess.run(
                    ["gh", "api", "-X", "DELETE",
                     f"repos/{repo}/environments/{env_name}"],
                    cwd=str(project_root),
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                results["github"] = {
                    "success": result.returncode == 0,
                    "error": (
                        result.stderr.strip()
                        if result.returncode != 0
                        else None
                    ),
                }
                if result.returncode == 0:
                    logger.info("Deleted GitHub environment: %s", env_name)
            except Exception as e:
                results["github"] = {"success": False, "error": str(e)}
        else:
            results["github"] = {
                "success": False,
                "error": "gh CLI unavailable or GITHUB_REPOSITORY not set",
            }

    _audit(
        "🧹 Environment Cleaned",
        f"Environment '{env_name}' cleaned up",
        action="cleaned", target=env_name,
        before_state={"existed": True},
    )
    return results


def seed_environments(
    project_root: Path,
    env_names: list[str],
    default: str = "",
) -> dict:
    """Seed environment files when transitioning from single-env to multi-env."""
    dotenv = project_root / ".env"
    dotenv_vault = project_root / ".env.vault"
    results: dict = {"seeded": [], "skipped": [], "active": None}

    for name in env_names:
        name = name.strip().lower()
        if not name:
            continue
        target = project_root / f".env.{name}"
        if target.exists():
            results["skipped"].append(name)
            continue
        if dotenv.exists():
            shutil.copy2(str(dotenv), str(target))
            logger.info("Seeded .env -> .env.%s", name)
            results["seeded"].append(name)
            target_vault = target.with_suffix(target.suffix + ".vault")
            if dotenv_vault.exists() and not target_vault.exists():
                shutil.copy2(str(dotenv_vault), str(target_vault))
                logger.info("Seeded .env.vault -> %s", target_vault.name)

    if default:
        marker = project_root / ".env.active"
        marker.write_text(default.strip().lower(), encoding="utf-8")
        results["active"] = default.strip().lower()
        logger.info("Set active env -> %s", default)

    _audit(
        "🌱 Environments Seeded",
        f"{len(env_names)} environment(s) seeded",
        action="seeded", target="environments",
        after_state={"count": len(env_names), "names": env_names},
    )
    return results
