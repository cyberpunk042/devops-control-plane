"""
Git authentication management.

Handles SSH key passphrase and HTTPS credential management
for git network operations.

Design:
  - Detects remote type (SSH vs HTTPS) from ``git remote get-url origin``
  - For SSH: starts ssh-agent, adds key with passphrase via SSH_ASKPASS
  - For HTTPS: stores token via git credential helper
  - Provides env dict that all git subprocess calls should inject
  - Auth state is cached for the server's lifetime

Usage by git runners::

    from src.core.services.git_auth import git_env
    subprocess.run(cmd, env=git_env(), ...)
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# ─── Module-level state (cached for server lifetime) ────────────────

_ssh_agent_env: dict[str, str] = {}
_auth_tested: bool = False
_auth_ok: bool = False


# ═══════════════════════════════════════════════════════════════════
#  Detection
# ═══════════════════════════════════════════════════════════════════


def detect_remote_type(project_root: Path) -> str:
    """Detect if origin remote uses SSH or HTTPS.

    Returns:
        ``'ssh'``, ``'https'``, or ``'unknown'``
    """
    url = get_remote_url(project_root)
    if url.startswith("git@") or url.startswith("ssh://"):
        return "ssh"
    if url.startswith("https://") or url.startswith("http://"):
        return "https"
    return "unknown"


def get_remote_url(project_root: Path) -> str:
    """Get the origin remote URL (empty string if no remote)."""
    try:
        r = subprocess.run(
            ["git", "-C", str(project_root), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def find_ssh_key() -> Path | None:
    """Find the primary SSH private key in ``~/.ssh/``."""
    ssh_dir = Path.home() / ".ssh"
    for name in ("id_ed25519", "id_rsa", "id_ecdsa", "id_dsa"):
        key = ssh_dir / name
        if key.is_file():
            return key
    return None


def key_has_passphrase(key_path: Path) -> bool:
    """Check if an SSH key is encrypted (has a passphrase).

    Tries ``ssh-keygen -y -P "" -f <key>``; if it succeeds with
    an empty passphrase, the key is unprotected.
    """
    try:
        r = subprocess.run(
            ["ssh-keygen", "-y", "-P", "", "-f", str(key_path)],
            capture_output=True, text=True, timeout=5,
        )
        return r.returncode != 0
    except Exception:
        return True  # assume passphrase if we can't check


# ═══════════════════════════════════════════════════════════════════
#  Auth check
# ═══════════════════════════════════════════════════════════════════


def check_auth(project_root: Path) -> dict:
    """Check if git network operations are working.

    For SSH remotes: instant local check (ssh-agent key status).
    For HTTPS remotes: quick ``git ls-remote`` with short timeout.

    Returns dict::

        {
            "ok": bool,
            "remote_type": "ssh" | "https" | "unknown",
            "remote_url": str,
            "needs": "ssh_passphrase" | "https_credentials" | None,
            "ssh_key": str | None,        # key filename if SSH
            "error": str | None,
        }
    """
    global _auth_tested, _auth_ok

    remote_type = detect_remote_type(project_root)
    remote_url = get_remote_url(project_root)
    ssh_key = None

    # ── SSH: instant local detection (no network call) ──────────
    if remote_type == "ssh":
        kp = find_ssh_key()
        ssh_key = kp.name if kp else None

        # 1. Check if ssh-agent already has keys loaded
        if _agent_has_keys():
            _auth_tested = True
            _auth_ok = True
            return {
                "ok": True,
                "remote_type": remote_type,
                "remote_url": remote_url,
                "ssh_key": ssh_key,
                "needs": None,
                "error": None,
            }

        # 2. If we've already added the key this session, it's OK
        if _ssh_agent_env and _auth_ok:
            return {
                "ok": True,
                "remote_type": remote_type,
                "remote_url": remote_url,
                "ssh_key": ssh_key,
                "needs": None,
                "error": None,
            }

        # 3. No agent keys — check if the key needs a passphrase
        if kp and not key_has_passphrase(kp):
            # Key has no passphrase — should work without agent
            _auth_tested = True
            _auth_ok = True
            return {
                "ok": True,
                "remote_type": remote_type,
                "remote_url": remote_url,
                "ssh_key": ssh_key,
                "needs": None,
                "error": None,
            }

        # 4. Key needs passphrase and no agent → prompt immediately
        _auth_tested = True
        _auth_ok = False
        return {
            "ok": False,
            "remote_type": remote_type,
            "remote_url": remote_url,
            "ssh_key": ssh_key,
            "needs": "ssh_passphrase",
            "error": "SSH key requires passphrase (no loaded agent key found)",
        }

    # ── HTTPS: quick network check ──────────────────────────────
    if remote_type == "https":
        env = git_env()
        try:
            r = subprocess.run(
                ["git", "-C", str(project_root),
                 "ls-remote", "--exit-code", "origin", "HEAD"],
                capture_output=True, text=True, timeout=8,
                env=env,
            )
            if r.returncode == 0:
                _auth_tested = True
                _auth_ok = True
                return {
                    "ok": True,
                    "remote_type": remote_type,
                    "remote_url": remote_url,
                    "ssh_key": None,
                    "needs": None,
                    "error": None,
                }
            return _classify_error(r.stderr, remote_type, remote_url, None)

        except subprocess.TimeoutExpired:
            _auth_tested = True
            _auth_ok = False
            return {
                "ok": False,
                "remote_type": remote_type,
                "remote_url": remote_url,
                "ssh_key": None,
                "needs": "https_credentials",
                "error": "Connection timed out (credential prompt likely hanging)",
            }

    # ── Unknown remote type ─────────────────────────────────────
    _auth_tested = True
    return {
        "ok": False,
        "remote_type": remote_type,
        "remote_url": remote_url,
        "ssh_key": None,
        "needs": None,
        "error": "Unknown remote type",
    }


def _agent_has_keys() -> bool:
    """Quick check: does the current ssh-agent have any keys loaded?

    Checks both the inherited env and our managed agent.
    """
    # Check our managed agent first
    if _ssh_agent_env:
        try:
            env = {**os.environ, **_ssh_agent_env}
            r = subprocess.run(
                ["ssh-add", "-l"],
                capture_output=True, text=True, timeout=3,
                env=env,
            )
            if r.returncode == 0 and r.stdout.strip():
                return True
        except Exception:
            pass

    # Check inherited agent from environment
    sock = os.environ.get("SSH_AUTH_SOCK")
    if not sock:
        return False
    try:
        r = subprocess.run(
            ["ssh-add", "-l"],
            capture_output=True, text=True, timeout=3,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def _classify_error(
    stderr: str,
    remote_type: str,
    remote_url: str,
    ssh_key: str | None,
) -> dict:
    """Classify a git network error to determine what the user needs."""
    global _auth_tested, _auth_ok
    _auth_tested = True
    _auth_ok = False
    lower = stderr.lower()

    if remote_type == "ssh":
        if any(s in lower for s in (
            "permission denied", "publickey", "host key",
            "could not read", "no such identity",
        )):
            return {
                "ok": False,
                "remote_type": remote_type,
                "remote_url": remote_url,
                "ssh_key": ssh_key,
                "needs": "ssh_passphrase",
                "error": stderr.strip(),
            }
    elif remote_type == "https":
        if any(s in lower for s in (
            "authentication", "403", "401", "credential",
            "could not read username",
        )):
            return {
                "ok": False,
                "remote_type": remote_type,
                "remote_url": remote_url,
                "ssh_key": ssh_key,
                "needs": "https_credentials",
                "error": stderr.strip(),
            }

    return {
        "ok": False,
        "remote_type": remote_type,
        "remote_url": remote_url,
        "ssh_key": ssh_key,
        "needs": None,
        "error": stderr.strip(),
    }


# ═══════════════════════════════════════════════════════════════════
#  SSH agent management
# ═══════════════════════════════════════════════════════════════════


def _detect_existing_agent() -> dict[str, str]:
    """Check if an ssh-agent is already running with keys loaded."""
    sock = os.environ.get("SSH_AUTH_SOCK")
    if not sock:
        return {}

    try:
        r = subprocess.run(
            ["ssh-add", "-l"],
            capture_output=True, text=True, timeout=5,
            env=os.environ,
        )
        if r.returncode == 0 and r.stdout.strip():
            # Keys are loaded — use the existing agent
            env: dict[str, str] = {"SSH_AUTH_SOCK": sock}
            pid = os.environ.get("SSH_AGENT_PID")
            if pid:
                env["SSH_AGENT_PID"] = pid
            logger.info("Using existing ssh-agent with loaded keys")
            return env
    except Exception:
        pass
    return {}


def _start_ssh_agent() -> dict[str, str]:
    """Start a new ssh-agent and return its env vars."""
    try:
        r = subprocess.run(
            ["ssh-agent", "-s"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            logger.error("Failed to start ssh-agent: %s", r.stderr)
            return {}

        env: dict[str, str] = {}
        for line in r.stdout.splitlines():
            # Parse: SSH_AUTH_SOCK=/tmp/...; export SSH_AUTH_SOCK;
            if "=" in line and ";" in line:
                part = line.split(";")[0]
                key, val = part.split("=", 1)
                env[key.strip()] = val.strip()

        logger.info(
            "Started ssh-agent (PID: %s)", env.get("SSH_AGENT_PID", "?"),
        )
        return env
    except Exception as e:
        logger.error("Failed to start ssh-agent: %s", e)
        return {}


def add_ssh_key(project_root: Path, passphrase: str) -> dict:
    """Add SSH key to ssh-agent with the given passphrase.

    Starts ssh-agent if not running. Uses ``SSH_ASKPASS`` to provide
    the passphrase non-interactively.

    Returns::

        {"ok": True} or {"ok": False, "error": "..."}
    """
    global _ssh_agent_env, _auth_ok, _auth_tested

    key_path = find_ssh_key()
    if not key_path:
        return {"ok": False, "error": "No SSH key found in ~/.ssh/"}

    # Try existing agent first
    if not _ssh_agent_env:
        _ssh_agent_env = _detect_existing_agent()

    # Start a new agent if needed
    if not _ssh_agent_env:
        _ssh_agent_env = _start_ssh_agent()
        if not _ssh_agent_env:
            return {"ok": False, "error": "Failed to start ssh-agent"}

    # Create a temporary askpass script that echoes the passphrase
    askpass_fd, askpass_path = tempfile.mkstemp(
        suffix=".sh", prefix="scp_askpass_",
    )
    try:
        with os.fdopen(askpass_fd, "w") as f:
            # Safely escape single quotes in passphrase
            safe_pp = passphrase.replace("'", "'\\''")
            f.write(f"#!/bin/sh\necho '{safe_pp}'\n")
        os.chmod(askpass_path, 0o700)

        env = {**os.environ, **_ssh_agent_env}
        env["SSH_ASKPASS"] = askpass_path
        env["SSH_ASKPASS_REQUIRE"] = "force"
        env["DISPLAY"] = os.environ.get("DISPLAY", ":0")

        r = subprocess.run(
            ["ssh-add", str(key_path)],
            capture_output=True, text=True, timeout=10,
            env=env,
            stdin=subprocess.DEVNULL,  # force SSH_ASKPASS usage
        )

        if r.returncode == 0:
            _auth_ok = True
            _auth_tested = True
            logger.info("SSH key added to agent: %s", key_path.name)
            return {"ok": True}

        stderr = r.stderr.strip().lower()
        if "bad passphrase" in stderr or "incorrect passphrase" in stderr:
            return {"ok": False, "error": "Wrong passphrase"}
        return {"ok": False, "error": r.stderr.strip()}

    finally:
        try:
            os.unlink(askpass_path)
        except OSError:
            pass


# ═══════════════════════════════════════════════════════════════════
#  HTTPS credential management
# ═══════════════════════════════════════════════════════════════════


def add_https_credentials(project_root: Path, token: str) -> dict:
    """Store HTTPS credentials (PAT / token) via git credential helper.

    Returns::

        {"ok": True} or {"ok": False, "error": "..."}
    """
    global _auth_ok, _auth_tested

    remote_url = get_remote_url(project_root)
    if not remote_url:
        return {"ok": False, "error": "No origin remote configured"}

    try:
        from urllib.parse import urlparse
        parsed = urlparse(remote_url)
        host = parsed.hostname or "github.com"
    except Exception:
        host = "github.com"

    # Ensure credential helper is configured
    subprocess.run(
        ["git", "-C", str(project_root),
         "config", "credential.helper", "store"],
        capture_output=True, text=True, timeout=5,
    )

    # Store the credential
    credential_input = (
        f"protocol=https\n"
        f"host={host}\n"
        f"username=x-access-token\n"
        f"password={token}\n\n"
    )
    r = subprocess.run(
        ["git", "-C", str(project_root), "credential", "approve"],
        input=credential_input,
        capture_output=True, text=True, timeout=5,
    )

    if r.returncode == 0:
        _auth_ok = True
        _auth_tested = True
        logger.info("HTTPS credentials stored for %s", host)
        return {"ok": True}

    return {"ok": False, "error": r.stderr.strip()}


# ═══════════════════════════════════════════════════════════════════
#  Environment for subprocess calls
# ═══════════════════════════════════════════════════════════════════


def git_env() -> dict[str, str]:
    """Get the environment dict for git subprocess calls.

    Includes ssh-agent vars if an agent is running.
    All git runners (``_run_main_git``, ``_run_ledger_git``) should
    pass this as ``env=git_env()``.
    """
    env = {**os.environ}
    if _ssh_agent_env:
        env.update(_ssh_agent_env)
    return env


def is_auth_ok() -> bool:
    """Check if auth has been verified this session."""
    return _auth_ok


def is_auth_tested() -> bool:
    """Check if auth has been tested at all this session."""
    return _auth_tested
