"""
Tool installation service — install missing devops tools.

Provides install recipes for common tools and handles subprocess
execution with optional sudo password piping.

Channel-independent: no Flask or HTTP dependency.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Any

logger = logging.getLogger(__name__)


from src.core.services.audit_helpers import make_auditor

_audit = make_auditor("audit")


# ── Install Recipes ─────────────────────────────────────────────

import sys

# Resolve pip via the current interpreter — avoids "pip not found" when
# running inside a venv where bare `pip` isn't on the system PATH.
_PIP = [sys.executable, "-m", "pip"]

# Commands that DON'T need sudo
_NO_SUDO_RECIPES: dict[str, list[str]] = {
    "ruff":       _PIP + ["install", "ruff"],
    "mypy":       _PIP + ["install", "mypy"],
    "pytest":     _PIP + ["install", "pytest"],
    "black":      _PIP + ["install", "black"],
    "pip-audit":  _PIP + ["install", "pip-audit"],
    "safety":     _PIP + ["install", "safety"],
    "bandit":     _PIP + ["install", "bandit"],
    "eslint":     ["npm", "install", "-g", "eslint"],
    "prettier":   ["npm", "install", "-g", "prettier"],
}

# Commands that NEED sudo
_SUDO_RECIPES: dict[str, list[str]] = {
    "helm":           ["bash", "-c", "curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash"],
    "kubectl":        ["snap", "install", "kubectl", "--classic"],
    "terraform":      ["snap", "install", "terraform", "--classic"],
    "docker":         ["apt-get", "install", "-y", "docker.io"],
    "docker-compose": ["apt-get", "install", "-y", "docker-compose-v2"],
    "trivy":          ["bash", "-c", "curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin"],
    "git":            ["apt-get", "install", "-y", "git"],
    "gh":             ["snap", "install", "gh"],
    "ffmpeg":         ["apt-get", "install", "-y", "ffmpeg"],
    "gzip":           ["apt-get", "install", "-y", "gzip"],
    "curl":           ["apt-get", "install", "-y", "curl"],
    "jq":             ["apt-get", "install", "-y", "jq"],
    "make":           ["apt-get", "install", "-y", "make"],
    "python":         ["apt-get", "install", "-y", "python3"],
    "pip":            ["apt-get", "install", "-y", "python3-pip"],
    "node":           ["snap", "install", "node", "--classic"],
    "npm":            ["apt-get", "install", "-y", "npm"],
    "npx":            ["apt-get", "install", "-y", "npm"],
    "go":             ["snap", "install", "go", "--classic"],
    "cargo":          ["bash", "-c", "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y"],
    "rustc":          ["bash", "-c", "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y"],
    "skaffold":       ["bash", "-c", "curl -Lo /usr/local/bin/skaffold https://storage.googleapis.com/skaffold/releases/latest/skaffold-linux-amd64 && chmod +x /usr/local/bin/skaffold"],
    "dig":            ["apt-get", "install", "-y", "dnsutils"],
    "openssl":        ["apt-get", "install", "-y", "openssl"],
    "rsync":          ["apt-get", "install", "-y", "rsync"],
    # ── Terminal emulators (for interactive spawn) ──
    "xterm":          ["apt-get", "install", "-y", "xterm"],
    "gnome-terminal": ["apt-get", "install", "-y", "gnome-terminal"],
    "xfce4-terminal": ["apt-get", "install", "-y", "xfce4-terminal"],
    "konsole":        ["apt-get", "install", "-y", "konsole"],
    "kitty":          ["apt-get", "install", "-y", "kitty"],
    # ── Utilities ──
    "expect":         ["apt-get", "install", "-y", "expect"],
}


# ── Public API ──────────────────────────────────────────────────


def install_tool(
    tool: str,
    *,
    cli: str = "",
    sudo_password: str = "",
) -> dict[str, Any]:
    """Install a missing devops tool.

    Args:
        tool: Tool name (e.g. "helm", "ruff").
        cli: CLI binary name to check (defaults to *tool*).
        sudo_password: Password for sudo, required for system packages.

    Returns:
        {"ok": True, "message": "...", ...} on success,
        {"ok": False, "error": "...", ...} on failure,
        {"ok": False, "needs_sudo": True, ...} when password is required.
    """
    tool = tool.lower().strip()
    cli = (cli or tool).strip()

    if not tool:
        return {"ok": False, "error": "No tool specified"}

    # Already installed?
    if shutil.which(cli):
        _audit(
            "🔧 Tool Already Installed",
            f"{tool} is already available",
            action="checked",
            target=tool,
        )
        return {
            "ok": True,
            "message": f"{tool} is already installed",
            "already_installed": True,
        }

    # Find install recipe
    if tool in _NO_SUDO_RECIPES:
        cmd = _NO_SUDO_RECIPES[tool]
        needs_sudo = False
    elif tool in _SUDO_RECIPES:
        needs_sudo = True
        if not sudo_password:
            _audit(
                "🔧 Tool Install — Sudo Required",
                f"{tool} requires sudo password",
                action="blocked",
                target=tool,
            )
            return {
                "ok": False,
                "needs_sudo": True,
                "error": "This tool requires sudo. Please enter your password.",
            }
        cmd = ["sudo", "-S", "-k"] + _SUDO_RECIPES[tool]
    else:
        _audit(
            "🔧 Tool Install — No Recipe",
            f"No install recipe for '{tool}'",
            action="failed",
            target=tool,
        )
        return {
            "ok": False,
            "error": f"No install recipe for '{tool}'. Install manually.",
        }

    # Execute
    try:
        stdin_data = (sudo_password + "\n") if needs_sudo else None
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            input=stdin_data,
        )

        if result.returncode == 0:
            installed = shutil.which(cli) is not None
            msg = (
                f"{tool} installed successfully"
                if installed
                else f"Command succeeded but '{cli}' not found in PATH yet"
                " — you may need to restart your shell"
            )
            _audit(
                "✅ Tool Installed",
                msg,
                action="installed",
                target=tool,
                detail={"tool": tool, "cli": cli, "installed": installed},
            )
            return {
                "ok": True,
                "message": msg,
                "installed": installed,
                "stdout": result.stdout[-2000:] if result.stdout else "",
            }

        stderr = result.stderr[-2000:] if result.stderr else ""

        # Wrong password?
        if "incorrect password" in stderr.lower() or "sorry" in stderr.lower():
            _audit(
                "🔧 Tool Install — Wrong Password",
                f"Wrong sudo password for {tool}",
                action="failed",
                target=tool,
            )
            return {
                "ok": False,
                "needs_sudo": True,
                "error": "Wrong password. Try again.",
            }

        error_msg = f"Install failed (exit {result.returncode})"
        _audit(
            "❌ Tool Install Failed",
            f"{tool}: {error_msg}",
            action="failed",
            target=tool,
            detail={"tool": tool, "exit_code": result.returncode, "stderr": stderr[:500]},
        )
        return {
            "ok": False,
            "error": error_msg,
            "stderr": stderr,
            "stdout": result.stdout[-2000:] if result.stdout else "",
        }

    except subprocess.TimeoutExpired:
        _audit(
            "❌ Tool Install Timeout",
            f"{tool}: install timed out (120s)",
            action="failed",
            target=tool,
        )
        return {"ok": False, "error": "Install timed out (120s)"}
    except Exception as e:
        logger.exception("Tool install error for %s", tool)
        _audit(
            "❌ Tool Install Error",
            f"{tool}: {e}",
            action="failed",
            target=tool,
        )
        return {"ok": False, "error": str(e)}
