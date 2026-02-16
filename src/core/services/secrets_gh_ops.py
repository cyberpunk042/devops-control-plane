"""
GitHub secrets & variables — list, set, remove, push.

Channel-independent: no Flask or HTTP dependency.
Requires ``gh`` CLI for GitHub API operations.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from src.core.services.audit_helpers import make_auditor
from src.core.services.secrets_ops import (
    fresh_env,
    gh_repo_flag,
    env_path_for,
    classify_key,
)

logger = logging.getLogger(__name__)

_audit = make_auditor("secrets")


def list_gh_secrets(
    project_root: Path,
    env_name: str = "",
) -> dict:
    """Get list of secrets AND variables set in GitHub."""
    env_flag = ["--env", env_name] if env_name else []

    if not shutil.which("gh"):
        return {
            "available": False,
            "reason": "gh CLI not installed",
            "secrets": [],
            "variables": [],
        }

    try:
        auth = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if auth.returncode != 0:
            return {
                "available": False,
                "reason": "gh CLI not authenticated",
                "secrets": [],
                "variables": [],
            }
    except Exception:
        return {
            "available": False,
            "reason": "gh auth check failed",
            "secrets": [],
            "variables": [],
        }

    repo_flag = gh_repo_flag(project_root)

    # Secrets
    result = subprocess.run(
        ["gh", "secret", "list"] + env_flag + repo_flag,
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=15,
    )

    secret_names = []
    if result.returncode == 0:
        for line in result.stdout.strip().split("\n"):
            if line:
                parts = line.split("\t")
                if parts:
                    secret_names.append(parts[0])

    # Variables
    var_result = subprocess.run(
        ["gh", "variable", "list"] + env_flag + repo_flag,
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=15,
    )

    variable_names = []
    if var_result.returncode == 0:
        for line in var_result.stdout.strip().split("\n"):
            if line:
                parts = line.split("\t")
                if parts:
                    variable_names.append(parts[0])

    return {
        "available": True,
        "secrets": secret_names,
        "variables": variable_names,
        "scoped_to": env_name if env_name else "repo",
    }


def set_secret(
    project_root: Path,
    name: str,
    value: str,
    *,
    target: str = "both",
    env_name: str = "",
) -> dict:
    """Set a single secret to .env and/or GitHub."""
    if not name:
        return {"error": "Secret name required"}

    results: dict = {"name": name, "local": None, "github": None}

    # Save to .env
    if target in ("local", "both") and value:
        try:
            env_file = env_path_for(project_root, env_name)
            existing: dict[str, str] = {}
            if env_file.exists():
                with open(env_file) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, _, val = line.partition("=")
                            existing[key.strip()] = val.strip()

            existing[name] = (
                f'"{value}"' if " " in value or "=" in value else value
            )

            with open(env_file, "w") as f:
                for key, val in sorted(existing.items()):
                    f.write(f"{key}={val}\n")

            results["local"] = {"success": True}
        except Exception as e:
            results["local"] = {"success": False, "error": str(e)}

    # Push to GitHub
    if target in ("github", "both") and value:
        repo_flag = gh_repo_flag(project_root)
        env_flag = ["--env", env_name] if env_name else []
        try:
            result = subprocess.run(
                ["gh", "secret", "set", name] + env_flag + repo_flag,
                input=value,
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=15,
            )
            results["github"] = {
                "success": result.returncode == 0,
                "error": (
                    result.stderr if result.returncode != 0 else None
                ),
            }
        except Exception as e:
            results["github"] = {"success": False, "error": str(e)}

    _audit(
        "🔐 Secret Set",
        f"Secret '{name}' set (target={target})",
        action="set", target=name,
        after_state={"target": target},
    )
    return results


def remove_secret(
    project_root: Path,
    name: str,
    *,
    target: str = "both",
    kind: str = "secret",
    env_name: str = "",
) -> dict:
    """Remove a secret/variable from .env and/or GitHub."""
    if not name:
        return {"error": "Secret name required"}

    results: dict = {"name": name, "local": None, "github": None}

    if target in ("local", "both"):
        try:
            env_file = env_path_for(project_root, env_name)
            if env_file.exists():
                lines = []
                with open(env_file) as f:
                    for line in f:
                        if not line.strip().startswith(f"{name}="):
                            lines.append(line)
                with open(env_file, "w") as f:
                    f.writelines(lines)
                results["local"] = {"success": True}
            else:
                results["local"] = {"success": True, "note": "File not found"}
        except Exception as e:
            results["local"] = {"success": False, "error": str(e)}

    if target in ("github", "both"):
        gh_cmd = "variable" if kind == "variable" else "secret"
        repo_flag = gh_repo_flag(project_root)
        env_flag = ["--env", env_name] if env_name else []
        try:
            result = subprocess.run(
                ["gh", gh_cmd, "delete", name] + env_flag + repo_flag,
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=15,
            )
            results["github"] = {
                "success": result.returncode == 0,
                "error": (
                    result.stderr if result.returncode != 0 else None
                ),
            }
        except Exception as e:
            results["github"] = {"success": False, "error": str(e)}

    _audit(
        "🗑️ Secret Removed",
        f"Secret '{name}' removed (target={target})",
        action="deleted", target=name,
        before_state={"target": target},
    )
    return results


def push_secrets(
    project_root: Path,
    *,
    secrets_dict: dict[str, str] | None = None,
    variables: dict[str, str] | None = None,
    env_values: dict[str, str] | None = None,
    deletions: list[str] | None = None,
    sync_keys: list[str] | None = None,
    push_to_github: bool = True,
    save_to_env: bool = True,
    exclude_from_github: set[str] | None = None,
    env_name: str = "",
) -> dict:
    """Push secrets/variables to GitHub AND save to .env file."""
    secrets_map = dict(secrets_dict or {})
    vars_map = dict(variables or {})
    all_env = dict(env_values or {})
    del_list = list(deletions or [])
    sync_list = list(sync_keys or [])
    excludes = set(exclude_from_github or set())

    env_flag = ["--env", env_name] if env_name else []

    # sync_keys: read from .env for GitHub push
    if sync_list and push_to_github:
        raw = fresh_env(project_root)
        for key_name in sync_list:
            if key_name in excludes:
                continue
            val = raw.get(key_name, "")
            if not val:
                continue
            kind = classify_key(key_name)
            if kind == "secret":
                secrets_map.setdefault(key_name, val)
            else:
                vars_map.setdefault(key_name, val)

    # For .env, use env_values if provided, otherwise merge dicts
    all_values = all_env if all_env else {**secrets_map, **vars_map}
    results: list[dict] = []
    deletions_applied: list[str] = []

    # Save to .env
    if save_to_env and (all_values or del_list):
        env_file = env_path_for(project_root, env_name)

        existing_lines: list[str] = []
        existing_keys: dict[str, int] = {}
        if env_file.exists():
            with open(env_file) as f:
                for i, line in enumerate(f):
                    existing_lines.append(line.rstrip("\n"))
                    stripped = line.strip()
                    if (
                        stripped
                        and not stripped.startswith("#")
                        and "=" in stripped
                    ):
                        key, _, _ = stripped.partition("=")
                        existing_keys[key.strip()] = i

        appended: list[str] = []
        for name, value in all_values.items():
            if not value:
                continue
            formatted = (
                f'"{value}"' if " " in value or "=" in value else value
            )
            if name in existing_keys:
                existing_lines[existing_keys[name]] = f"{name}={formatted}"
            else:
                appended.append(f"{name}={formatted}")

        deleted_indices: set[int] = set()
        for name in del_list:
            if name in existing_keys:
                deleted_indices.add(existing_keys[name])
                deletions_applied.append(name)

        final_lines = [
            line
            for i, line in enumerate(existing_lines)
            if i not in deleted_indices
        ]
        final_lines.extend(appended)

        with open(env_file, "w") as f:
            f.write("\n".join(final_lines))
            if not final_lines[-1] == "" if final_lines else True:
                f.write("\n")

    # Push to GitHub
    if push_to_github:
        if not shutil.which("gh"):
            return {
                "env_saved": save_to_env,
                "error": "gh CLI not installed",
                "results": [],
                "all_success": False,
            }

        try:
            auth = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if auth.returncode != 0:
                return {
                    "env_saved": save_to_env,
                    "error": "gh CLI not authenticated — run: gh auth login",
                    "results": [],
                    "all_success": False,
                }
        except Exception:
            return {
                "env_saved": save_to_env,
                "error": "gh auth check failed",
                "results": [],
                "all_success": False,
            }

        repo_flag = gh_repo_flag(project_root)

        for name, value in secrets_map.items():
            if not value:
                continue
            if name.startswith("GITHUB_") or name in excludes:
                continue
            try:
                result = subprocess.run(
                    ["gh", "secret", "set", name, "--body", value]
                    + env_flag + repo_flag,
                    cwd=str(project_root),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                results.append({
                    "name": name,
                    "kind": "secret",
                    "success": result.returncode == 0,
                    "error": (
                        result.stderr if result.returncode != 0 else None
                    ),
                })
            except Exception as e:
                results.append({
                    "name": name,
                    "kind": "secret",
                    "success": False,
                    "error": str(e),
                })

        for name, value in vars_map.items():
            if not value:
                continue
            if name in excludes:
                continue
            try:
                result = subprocess.run(
                    ["gh", "variable", "set", name, "--body", value]
                    + env_flag + repo_flag,
                    cwd=str(project_root),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                results.append({
                    "name": name,
                    "kind": "variable",
                    "success": result.returncode == 0,
                    "error": (
                        result.stderr if result.returncode != 0 else None
                    ),
                })
            except Exception as e:
                results.append({
                    "name": name,
                    "kind": "variable",
                    "success": False,
                    "error": str(e),
                })

    all_ok = all(r["success"] for r in results) if results else True

    pushed_count = sum(1 for r in results if r.get("success"))
    _audit(
        "📤 Secrets Pushed",
        f"{pushed_count} secret(s) pushed to GitHub",
        action="pushed", target="github",
        after_state={"pushed_count": pushed_count},
    )
    return {
        "env_saved": save_to_env,
        "deletions_applied": deletions_applied,
        "results": results,
        "all_success": all_ok,
        "pushed": [r["name"] for r in results if r.get("success")],
    }
