"""
Admin API — GitHub CLI and secrets management endpoints.

Blueprint: secrets_bp
Prefix: /api
Routes:
    /api/gh/status
    /api/gh/auto
    /api/gh/secrets          (?env= for environment-scoped)
    /api/gh/environments
    /api/gh/environment/create
    /api/secret/set
    /api/secret/remove       (?env= for environment-scoped)
    /api/secrets/push        (?env= for environment-scoped)
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


def _env_path():
    """Resolve .env file path from optional ``?env=`` query param.

    No param (single-env mode) → .env
    ?env=development           → .env.development
    ?env=production            → .env.production
    """
    from pathlib import Path

    env_name = request.args.get("env", "").strip().lower()
    root = Path(_project_root())
    if not env_name:
        return root / ".env"
    return root / f".env.{env_name}"


def _gh_env_flag() -> list:
    """Return ``['--env', name]`` for environment-scoped gh commands.

    No param (single-env mode) → [] (repo-level secrets).
    Any env name               → ['--env', name] (environment-scoped).
    """
    env_name = request.args.get("env", "").strip().lower()
    if not env_name:
        return []
    return ["--env", env_name]


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


# ── List GitHub environments ─────────────────────────────────────────


@secrets_bp.route("/gh/environments")
def api_gh_environments():
    """List GitHub deployment environments for the current repo."""
    from pathlib import Path
    import shutil
    import json as _json

    project_root = Path(_project_root())
    result = {"available": False, "environments": [], "reason": None}

    if not shutil.which("gh"):
        result["reason"] = "gh CLI not installed"
        return jsonify(result)

    repo_flag = gh_repo_flag(project_root)
    if not repo_flag:
        result["reason"] = "GITHUB_REPOSITORY not configured"
        return jsonify(result)

    repo = repo_flag[1]  # e.g. "owner/repo"

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
            # 404 means no environments configured — that's fine
            if "404" in api_result.stderr:
                result["available"] = True
                result["environments"] = []
            else:
                result["reason"] = api_result.stderr.strip()
    except Exception as e:
        result["reason"] = str(e)

    return jsonify(result)


# ── Key generators ───────────────────────────────────────────────────


@secrets_bp.route("/keys/generate", methods=["POST"])
def api_keys_generate():
    """Generate a secret value (password, token, SSH key, certificate).

    Body: {"type": "password"|"token"|"ssh-ed25519"|"ssh-rsa"|"cert-selfsigned",
           "length": 32, "cn": "localhost"}

    Returns: {"value": str, "public_value"?: str, "base64": bool,
              "type": str, "meta_tags": str}
    """
    import base64
    import secrets
    import string
    import tempfile

    data = request.json or {}
    gen_type = data.get("type", "password").strip().lower()
    length = data.get("length", 32)
    cn = data.get("cn", "localhost")

    try:
        length = max(8, min(int(length), 256))
    except (ValueError, TypeError):
        length = 32

    result = {"type": gen_type, "base64": False}

    if gen_type == "password":
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        value = "".join(secrets.choice(alphabet) for _ in range(length))
        result["value"] = value
        result["meta_tags"] = f"@type:password @generated:password @length:{length}"

    elif gen_type == "token":
        value = secrets.token_urlsafe(length)
        result["value"] = value
        result["meta_tags"] = f"@generated:token @length:{length}"

    elif gen_type in ("ssh-ed25519", "ssh-rsa"):
        key_type = "ed25519" if gen_type == "ssh-ed25519" else "rsa"
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = f"{tmpdir}/id_{key_type}"
            cmd = ["ssh-keygen", "-t", key_type, "-f", key_path,
                   "-N", "", "-C", "generated-by-devops-control-plane"]
            if key_type == "rsa":
                cmd.extend(["-b", "4096"])

            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if proc.returncode != 0:
                return jsonify({"error": f"ssh-keygen failed: {proc.stderr.strip()}"}), 500

            from pathlib import Path
            private_key = Path(key_path).read_text(encoding="utf-8").strip()
            public_key = Path(f"{key_path}.pub").read_text(encoding="utf-8").strip()

            # Base64-encode the private key for .env storage
            b64_private = base64.b64encode(private_key.encode()).decode()

            result["value"] = b64_private
            result["public_value"] = public_key
            result["base64"] = True
            result["meta_tags"] = f"@encoding:base64 @generated:{gen_type}"

    elif gen_type == "cert-selfsigned":
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = f"{tmpdir}/cert.key"
            cert_path = f"{tmpdir}/cert.pem"

            proc = subprocess.run(
                ["openssl", "req", "-x509", "-newkey", "ec",
                 "-pkeyopt", "ec_paramgen_curve:prime256v1",
                 "-keyout", key_path, "-out", cert_path,
                 "-days", "365", "-nodes",
                 "-subj", f"/CN={cn}"],
                capture_output=True, text=True, timeout=30,
            )
            if proc.returncode != 0:
                return jsonify({"error": f"openssl failed: {proc.stderr.strip()}"}), 500

            from pathlib import Path
            private_key = Path(key_path).read_text(encoding="utf-8").strip()
            certificate = Path(cert_path).read_text(encoding="utf-8").strip()

            b64_key = base64.b64encode(private_key.encode()).decode()
            b64_cert = base64.b64encode(certificate.encode()).decode()

            result["value"] = b64_cert
            result["private_key"] = b64_key
            result["base64"] = True
            result["meta_tags"] = f"@encoding:base64 @generated:cert-selfsigned"

    else:
        return jsonify({"error": f"Unknown generator type: {gen_type}"}), 400

    return jsonify(result)


# ── Create GitHub environment ────────────────────────────────────────


@secrets_bp.route("/gh/environment/create", methods=["POST"])
def api_gh_environment_create():
    """Create a deployment environment on GitHub."""
    from pathlib import Path
    import shutil

    project_root = Path(_project_root())
    data = request.json or {}
    env_name = data.get("name", "").strip()

    if not env_name:
        return jsonify({"error": "Environment name required"}), 400

    if not shutil.which("gh"):
        return jsonify({"error": "gh CLI not installed"}), 500

    repo_flag = gh_repo_flag(project_root)
    if not repo_flag:
        return jsonify({"error": "GITHUB_REPOSITORY not configured"}), 400

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
            return jsonify({"success": True, "name": env_name})
        else:
            return jsonify(
                {"error": f"Failed to create environment: {result.stderr.strip()}"}
            ), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@secrets_bp.route("/env/cleanup", methods=["POST"])
def api_env_cleanup():
    """Clean up an environment: delete local .env files and optionally GitHub env.

    Body: { "name": "production", "delete_files": true, "delete_github": true }
    """
    from pathlib import Path
    import shutil

    project_root = Path(_project_root())
    data = request.json or {}
    env_name = data.get("name", "").strip().lower()
    delete_files = data.get("delete_files", True)
    delete_github = data.get("delete_github", False)

    if not env_name:
        return jsonify({"error": "Environment name required"}), 400

    results = {"name": env_name, "files": [], "github": None}

    # ── Delete local .env files ──────────────────────────────
    if delete_files:
        for suffix in ["", ".vault"]:
            fpath = project_root / f".env.{env_name}{suffix}"
            if fpath.exists():
                fpath.unlink()
                results["files"].append(fpath.name)
                logger.info("Deleted %s", fpath.name)

    # ── Delete GitHub environment ────────────────────────────
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
            results["github"] = {"success": False, "error": "gh CLI unavailable or GITHUB_REPOSITORY not set"}

    return jsonify(results)


@secrets_bp.route("/env/seed", methods=["POST"])
def api_env_seed():
    """Seed environment files when transitioning from single-env to multi-env.

    For each environment name, if .env.<name> does not exist but .env does,
    copy .env -> .env.<name>.  Also sets .env.active to the default env.

    Body: { "environments": ["development", "production"], "default": "development" }
    """
    from pathlib import Path
    import shutil

    project_root = Path(_project_root())
    data = request.json or {}
    env_names = data.get("environments", [])
    default_env = data.get("default", "")

    dotenv = project_root / ".env"
    dotenv_vault = project_root / ".env.vault"
    results = {"seeded": [], "skipped": [], "active": None}

    for name in env_names:
        name = name.strip().lower()
        if not name:
            continue
        target = project_root / f".env.{name}"
        if target.exists():
            results["skipped"].append(name)
            continue
        # Seed from .env if it exists
        if dotenv.exists():
            shutil.copy2(str(dotenv), str(target))
            logger.info("Seeded .env -> .env.%s", name)
            results["seeded"].append(name)
            # Also copy vault file if present
            target_vault = target.with_suffix(target.suffix + ".vault")
            if dotenv_vault.exists() and not target_vault.exists():
                shutil.copy2(str(dotenv_vault), str(target_vault))
                logger.info("Seeded .env.vault -> %s", target_vault.name)

    # Set active marker
    if default_env:
        marker = project_root / ".env.active"
        marker.write_text(default_env.strip().lower(), encoding="utf-8")
        results["active"] = default_env.strip().lower()
        logger.info("Set active env -> %s", default_env)

    return jsonify(results)


# ── List GitHub secrets & variables ──────────────────────────────────


@secrets_bp.route("/gh/secrets")
def api_gh_secrets():
    """Get list of secrets AND variables set in GitHub.

    Supports ``?env=<name>`` to list environment-scoped secrets.
    For ``dev`` or no param, lists repo-level secrets.
    """
    from pathlib import Path

    project_root = Path(_project_root())
    env_flag = _gh_env_flag()

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

        # Get list of secrets from GitHub (repo-level or env-scoped)
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

        # Get list of variables from GitHub
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

        return jsonify(
            {
                "available": True,
                "secrets": secret_names,
                "variables": variable_names,
                "scoped_to": env_flag[1] if env_flag else "repo",
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
            env_file = _env_path()
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
        env_flag = _gh_env_flag()
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
            env_file = _env_path()
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
        env_flag = _gh_env_flag()
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
        env_path = _env_path()
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
        env_file = _env_path()

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
        env_flag = _gh_env_flag()

        # Push secrets via gh secret set (env-scoped if ?env= provided)
        for name, value in secrets.items():
            if not value:
                continue
            if name.startswith("GITHUB_") or name in exclude_from_github:
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
                    + env_flag + repo_flag,
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
