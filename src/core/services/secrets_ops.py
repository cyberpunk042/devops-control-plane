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

# Re-exports — backward compatibility
# ═══════════════════════════════════════════════════════════════════

from src.core.services.secrets_env_ops import (  # noqa: F401, E402
    list_environments,
    create_environment,
    cleanup_environment,
    seed_environments,
)

from src.core.services.secrets_gh_ops import (  # noqa: F401, E402
    list_gh_secrets,
    set_secret,
    remove_secret,
    push_secrets,
)

