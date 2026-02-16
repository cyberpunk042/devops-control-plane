"""
Secrets & GitHub operations — channel-independent service.

Manages GitHub CLI interactions, .env file manipulation,
key generation, and environment management. No Flask dependency.

Extracted from ``src/ui/web/routes_secrets.py``.
"""

from __future__ import annotations

import base64
import logging
import os
import re
import secrets as _secrets
import shutil
import string
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


from src.core.services.audit_helpers import make_auditor

_audit = make_auditor("secrets")


# ═══════════════════════════════════════════════════════════════════
#  Shared helpers
# ═══════════════════════════════════════════════════════════════════

# Re-export from the data layer — single source of truth.
from src.core.data import classify_key  # noqa: E402


def fresh_env(project_root: Path) -> dict:
    """Build subprocess env with fresh .env values."""
    env = {**os.environ, "TERM": "dumb"}
    env_file = project_root / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    if (
                        len(value) >= 2
                        and value[0] == value[-1]
                        and value[0] in ('"', "'")
                    ):
                        value = value[1:-1]
                    env[key] = value
    return env


def gh_repo_flag(project_root: Path) -> list:
    """Get -R repo flag for gh CLI commands."""
    repo = fresh_env(project_root).get("GITHUB_REPOSITORY", "")
    return ["-R", repo] if repo else []


def env_path_for(project_root: Path, env_name: str = "") -> Path:
    """Resolve .env file path.

    No env_name (single-env mode) → .env
    env_name=development           → .env.development
    """
    if not env_name:
        return project_root / ".env"
    return project_root / f".env.{env_name}"


def read_env_values(env_path: Path) -> dict[str, str]:
    """Read raw key=value pairs from .env file."""
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if "# local-only" in line:
            line = line[: line.index("# local-only")].rstrip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in ('"', "'")
        ):
            value = value[1:-1]
        values[key] = value
    return values


# ═══════════════════════════════════════════════════════════════════
#  gh CLI status & auto-detect
# ═══════════════════════════════════════════════════════════════════


def gh_status() -> dict:
    """Get gh CLI status (installed, authenticated)."""
    result = {"installed": False, "authenticated": False}

    if not shutil.which("gh"):
        return result

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

    return result


def gh_auto_detect(project_root: Path) -> dict:
    """Get GitHub token from gh CLI and detect repo from git remote."""
    result: dict = {"token": None, "repo": None}

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

    return result


# ═══════════════════════════════════════════════════════════════════
#  GitHub environments
# ═══════════════════════════════════════════════════════════════════


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


# ═══════════════════════════════════════════════════════════════════
#  Key generators
# ═══════════════════════════════════════════════════════════════════


def generate_key(
    gen_type: str = "password",
    length: int = 32,
    cn: str = "localhost",
) -> dict:
    """Generate a secret value (password, token, SSH key, certificate)."""
    try:
        length = max(8, min(int(length), 256))
    except (ValueError, TypeError):
        length = 32

    result: dict = {"type": gen_type, "base64": False}

    if gen_type == "password":
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        value = "".join(_secrets.choice(alphabet) for _ in range(length))
        result["value"] = value
        result["meta_tags"] = f"@type:password @generated:password @length:{length}"

    elif gen_type == "token":
        value = _secrets.token_urlsafe(length)
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
                return {"error": f"ssh-keygen failed: {proc.stderr.strip()}"}

            private_key = Path(key_path).read_text(encoding="utf-8").strip()
            public_key = Path(f"{key_path}.pub").read_text(encoding="utf-8").strip()

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
                return {"error": f"openssl failed: {proc.stderr.strip()}"}

            private_key = Path(key_path).read_text(encoding="utf-8").strip()
            certificate = Path(cert_path).read_text(encoding="utf-8").strip()

            b64_key = base64.b64encode(private_key.encode()).decode()
            b64_cert = base64.b64encode(certificate.encode()).decode()

            result["value"] = b64_cert
            result["private_key"] = b64_key
            result["base64"] = True
            result["meta_tags"] = "@encoding:base64 @generated:cert-selfsigned"

    else:
        return {"error": f"Unknown generator type: {gen_type}"}

    _audit(
        "🔑 Key Generated",
        f"{gen_type} key generated",
        action="generated", target=gen_type,
    )
    return result


# ═══════════════════════════════════════════════════════════════════
#  GitHub secrets & variables
# ═══════════════════════════════════════════════════════════════════


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
