"""
Admin API — GitHub CLI and secrets management endpoints.

Blueprint: secrets_bp
Prefix: /api
Routes:
    /api/gh/status
    /api/gh/auto
    /api/gh/secrets
    /api/secret/set
    /api/secret/remove
    /api/secrets/push
"""

from __future__ import annotations

import logging
import subprocess

from flask import Blueprint, current_app, jsonify, request

from .helpers import fresh_env, gh_repo_flag
from .routes_vault import _classify_key

logger = logging.getLogger(__name__)

secrets_bp = Blueprint("secrets", __name__)


def _project_root():
    return current_app.config["PROJECT_ROOT"]


# ── gh CLI status ────────────────────────────────────────────────────


@secrets_bp.route("/gh/status")
def api_gh_status():
    """Get gh CLI status (installed, authenticated)."""
    import shutil

    result = {"installed": False, "authenticated": False}

    if not shutil.which("gh"):
        return jsonify(result)

    result["installed"] = True

    try:
        auth_check = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        result["authenticated"] = auth_check.returncode == 0
    except Exception:
        pass

    return jsonify(result)


# ── gh auto-detect token & repo ──────────────────────────────────────


@secrets_bp.route("/gh/auto")
def api_gh_auto():
    """Get GitHub token from gh CLI and detect repo from git remote."""
    from pathlib import Path
    import re

    project_root = Path(_project_root())
    result = {"token": None, "repo": None}

    # Try to get token from gh auth token
    try:
        token_result = subprocess.run(
            ["gh", "auth", "token"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if token_result.returncode == 0 and token_result.stdout.strip():
            result["token"] = token_result.stdout.strip()
    except Exception:
        pass

    # Try to detect repo from git remote
    try:
        remote_result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if remote_result.returncode == 0 and remote_result.stdout.strip():
            url = remote_result.stdout.strip()
            match = re.search(
                r"github\.com[:/]([^/]+/[^/\s]+?)(?:\.git)?$", url
            )
            if match:
                result["repo"] = match.group(1)
    except Exception:
        pass

    return jsonify(result)


# ── List GitHub secrets & variables ──────────────────────────────────


@secrets_bp.route("/gh/secrets")
def api_gh_secrets():
    """Get list of secrets AND variables set in GitHub repo."""
    from pathlib import Path

    project_root = Path(_project_root())
    try:
        import shutil

        if not shutil.which("gh"):
            return jsonify(
                {
                    "available": False,
                    "reason": "gh CLI not installed",
                    "secrets": [],
                    "variables": [],
                }
            )

        # Check authentication
        auth = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if auth.returncode != 0:
            return jsonify(
                {
                    "available": False,
                    "reason": "gh CLI not authenticated",
                    "secrets": [],
                    "variables": [],
                }
            )

        repo_flag = gh_repo_flag(project_root)

        # Get list of secrets from GitHub
        result = subprocess.run(
            ["gh", "secret", "list"] + repo_flag,
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

        # Get list of variables from GitHub
        var_result = subprocess.run(
            ["gh", "variable", "list"] + repo_flag,
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

        return jsonify(
            {
                "available": True,
                "secrets": secret_names,
                "variables": variable_names,
            }
        )

    except Exception as e:
        return jsonify(
            {
                "available": False,
                "reason": str(e),
                "secrets": [],
                "variables": [],
            }
        )


# ── Set a single secret ─────────────────────────────────────────────


@secrets_bp.route("/secret/set", methods=["POST"])
def api_secret_set():
    """Set a single secret to .env and/or GitHub."""
    from pathlib import Path

    project_root = Path(_project_root())
    data = request.json or {}
    name = data.get("name")
    value = data.get("value")
    target = data.get("target", "both")  # "local", "github", or "both"

    if not name:
        return jsonify({"error": "Secret name required"}), 400

    results = {"name": name, "local": None, "github": None}

    # Save to .env
    if target in ("local", "both") and value:
        try:
            env_file = project_root / ".env"
            existing = {}
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
        try:
            result = subprocess.run(
                ["gh", "secret", "set", name] + repo_flag,
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

    return jsonify(results)


# ── Remove a single secret ──────────────────────────────────────────


@secrets_bp.route("/secret/remove", methods=["POST"])
def api_secret_remove():
    """Remove a secret/variable from .env and/or GitHub."""
    from pathlib import Path

    project_root = Path(_project_root())
    data = request.json or {}
    name = data.get("name")
    target = data.get("target", "both")
    kind = data.get("kind", "secret")

    if not name:
        return jsonify({"error": "Secret name required"}), 400

    results = {"name": name, "local": None, "github": None}

    # Remove from .env
    if target in ("local", "both"):
        try:
            env_file = project_root / ".env"
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

    # Remove from GitHub
    if target in ("github", "both"):
        gh_cmd = "variable" if kind == "variable" else "secret"
        repo_flag = gh_repo_flag(project_root)
        try:
            result = subprocess.run(
                ["gh", gh_cmd, "delete", name] + repo_flag,
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

    return jsonify(results)


# ── Bulk push secrets/variables to GitHub + save to .env ─────────────


@secrets_bp.route("/secrets/push", methods=["POST"])
def api_push_secrets():
    """Push secrets/variables to GitHub AND save to .env file.

    Request body:
        secrets: dict of name->value for GitHub secrets (gh secret set)
        variables: dict of name->value for GitHub variables (gh variable set)
        env_values: dict of name->value for .env saving (all values)
        deletions: list of names to delete from .env
        push_to_github: bool
        save_to_env: bool
        exclude_from_github: list of names to skip for GitHub push
    """
    from pathlib import Path

    project_root = Path(_project_root())
    data = request.json or {}
    secrets = data.get("secrets", {})
    variables = data.get("variables", {})
    env_values = data.get("env_values", {})
    deletions = data.get("deletions", [])
    sync_keys = data.get("sync_keys", [])
    push_to_github = data.get("push_to_github", True)
    save_to_env = data.get("save_to_env", True)
    exclude_from_github = set(data.get("exclude_from_github", []))

    # sync_keys: frontend doesn't have raw values for these (secret-type).
    # Read them from .env and merge into secrets/variables for GitHub push.
    if sync_keys and push_to_github:
        env_path = project_root / ".env"
        raw = fresh_env(project_root)
        for key_name in sync_keys:
            if key_name in exclude_from_github:
                continue
            val = raw.get(key_name, "")
            if not val:
                continue
            kind = _classify_key(key_name)
            if kind == "secret":
                secrets.setdefault(key_name, val)
            else:
                variables.setdefault(key_name, val)

    # For .env saving: use env_values if provided, otherwise fall back
    all_values = env_values if env_values else {**secrets, **variables}
    results = []
    deletions_applied = []

    # First, save to .env file
    if save_to_env and (all_values or deletions):
        env_file = project_root / ".env"

        # Read existing content, preserving comments and structure
        existing_lines = []
        existing_keys = {}
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

        # Update existing keys in-place, append new ones
        appended = []
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

        # Apply deletions
        deleted_indices = set()
        for name in deletions:
            if name in existing_keys:
                deleted_indices.add(existing_keys[name])
                deletions_applied.append(name)

        # Rebuild file: existing lines (minus deletions) + appended
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

    # Then push to GitHub if requested
    if push_to_github:
        import shutil

        if not shutil.which("gh"):
            return jsonify(
                {
                    "env_saved": save_to_env,
                    "error": "gh CLI not installed",
                    "results": [],
                    "all_success": False,
                }
            )

        auth = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if auth.returncode != 0:
            return jsonify(
                {
                    "env_saved": save_to_env,
                    "error": "gh CLI not authenticated — run: gh auth login",
                    "results": [],
                    "all_success": False,
                }
            )

        repo_flag = gh_repo_flag(project_root)

        # Push secrets via gh secret set
        for name, value in secrets.items():
            if not value:
                continue
            if name.startswith("GITHUB_") or name in exclude_from_github:
                continue
            try:
                result = subprocess.run(
                    ["gh", "secret", "set", name, "--body", value]
                    + repo_flag,
                    cwd=str(project_root),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                results.append(
                    {
                        "name": name,
                        "kind": "secret",
                        "success": result.returncode == 0,
                        "error": (
                            result.stderr
                            if result.returncode != 0
                            else None
                        ),
                    }
                )
            except Exception as e:
                results.append(
                    {
                        "name": name,
                        "kind": "secret",
                        "success": False,
                        "error": str(e),
                    }
                )

        # Push variables via gh variable set
        for name, value in variables.items():
            if not value:
                continue
            if name in exclude_from_github:
                continue
            try:
                result = subprocess.run(
                    ["gh", "variable", "set", name, "--body", value]
                    + repo_flag,
                    cwd=str(project_root),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                results.append(
                    {
                        "name": name,
                        "kind": "variable",
                        "success": result.returncode == 0,
                        "error": (
                            result.stderr
                            if result.returncode != 0
                            else None
                        ),
                    }
                )
            except Exception as e:
                results.append(
                    {
                        "name": name,
                        "kind": "variable",
                        "success": False,
                        "error": str(e),
                    }
                )

    all_ok = all(r["success"] for r in results) if results else True

    return jsonify(
        {
            "env_saved": save_to_env,
            "deletions_applied": deletions_applied,
            "results": results,
            "all_success": all_ok,
        }
    )
