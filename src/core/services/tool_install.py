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
    "eslint":         ["npm", "install", "-g", "eslint"],
    "prettier":       ["npm", "install", "-g", "prettier"],
    "cargo-audit":    ["cargo", "install", "cargo-audit"],
    "cargo-outdated": ["cargo", "install", "cargo-outdated"],
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

# ── System dependency checks ───────────────────────────────────────

# Packages needed to compile Rust crates that vendor native libs (curl-sys, openssl-sys)
CARGO_BUILD_DEPS = ["pkg-config", "libssl-dev", "libcurl4-openssl-dev"]


def check_system_deps(packages: list[str]) -> dict:
    """Check which apt packages are installed. Returns {missing: [...], installed: [...]}."""
    missing = []
    installed = []
    for pkg in packages:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Status}", pkg],
            capture_output=True, text=True,
        )
        if "install ok installed" in result.stdout:
            installed.append(pkg)
        else:
            missing.append(pkg)
    return {"missing": missing, "installed": installed}


# ── Error analysis — parse failures into actionable remediation ─────

import re

def _analyse_install_failure(
    tool: str, cli: str, stderr: str,
) -> dict[str, Any] | None:
    """Parse stderr from a failed install and return structured remediation.

    Returns None if no known pattern matched.
    Returns a dict with:
      - reason: human-readable explanation
      - options: list of actionable remediation paths
    """
    if not stderr:
        return None

    # ── Rust version mismatch ──
    # Pattern: "it requires rustc X.Y or newer, while the currently active
    #           rustc version is Z.W"
    # Hint:    "package_name X.Y.Z supports rustc A.B.C"
    rustc_req = re.search(
        r"requires rustc (\d+\.\d+(?:\.\d+)?)\s+or newer.*?"
        r"currently active rustc version is (\d+\.\d+(?:\.\d+)?)",
        stderr,
        re.DOTALL,
    )
    if rustc_req:
        required = rustc_req.group(1)
        current = rustc_req.group(2)

        # Try to extract the compatible fallback version
        compat = re.search(
            rf"`?{re.escape(tool)}\s+(\d+\.\d+\.\d+)`?\s+supports\s+rustc",
            stderr,
        )
        compat_ver = compat.group(1) if compat else None

        options: list[dict[str, Any]] = []

        # Option 1: Install compatible version
        if compat_ver:
            options.append({
                "id": "compatible-version",
                "label": "Compatible Version",
                "icon": "📦",
                "description": (
                    f"Install {tool}@{compat_ver} "
                    f"(works with your rustc {current})"
                ),
                "command": ["cargo", "install", f"{tool}@{compat_ver}"],
                "needs_sudo": False,
                "system_deps": CARGO_BUILD_DEPS,
            })

        # Option 2: Upgrade Rust via rustup
        options.append({
            "id": "upgrade-dep",
            "label": "Upgrade Rust",
            "icon": "⬆️",
            "description": (
                f"Install rustup + Rust {required}+, "
                f"then install latest {tool}"
            ),
            "system_deps": CARGO_BUILD_DEPS,
            "steps": [
                {
                    "label": "Install rustup + latest Rust",
                    "command": [
                        "bash", "-c",
                        "curl --proto '=https' --tlsv1.2 -sSf "
                        "https://sh.rustup.rs | sh -s -- -y",
                    ],
                    "needs_sudo": False,
                },
                {
                    "label": f"Install {tool}",
                    "command": [
                        "bash", "-c",
                        f'export PATH="$HOME/.cargo/bin:$PATH" && cargo install {tool}',
                    ],
                    "needs_sudo": False,
                },
            ],
        })

        # Option 3: Build from source
        # Cargo can build older commits that support the system rustc
        options.append({
            "id": "build-source",
            "label": "Build from Source",
            "icon": "🔧",
            "description": (
                f"Build {tool} from source using system rustc {current}"
            ),
            "command": [
                "bash", "-c",
                f"cargo install {tool} --locked 2>/dev/null "
                f"|| cargo install {tool}@{compat_ver}" if compat_ver
                else f"cargo install {tool} --locked",
            ],
            "needs_sudo": False,
            "system_deps": CARGO_BUILD_DEPS,
        })

        return {
            "type": "version_mismatch",
            "reason": (
                f"{tool} requires rustc {required}+ "
                f"(you have {current})"
            ),
            "options": options,
        }

    # ── npm / node not found ──
    if "npm: command not found" in stderr or "npm: not found" in stderr:
        return {
            "type": "missing_runtime",
            "reason": "npm is not installed",
            "options": [
                {
                    "id": "install-npm",
                    "label": "Install npm",
                    "icon": "📦",
                    "description": "Install npm via system packages",
                    "tool": "npm",
                    "needs_sudo": True,
                },
            ],
        }

    # ── pip not found ──
    if "No module named pip" in stderr or "pip: command not found" in stderr:
        return {
            "type": "missing_runtime",
            "reason": "pip is not installed",
            "options": [
                {
                    "id": "install-pip",
                    "label": "Install pip",
                    "icon": "📦",
                    "description": "Install pip via system packages",
                    "tool": "pip",
                    "needs_sudo": True,
                },
            ],
        }

    # ── Permission denied (npm global) ──
    if "EACCES" in stderr and "permission denied" in stderr.lower():
        return {
            "type": "permissions",
            "reason": "Permission denied — try with sudo",
            "options": [
                {
                    "id": "retry-sudo",
                    "label": "Retry with sudo",
                    "icon": "🔒",
                    "description": "Re-run the install with sudo privileges",
                    "retry_sudo": True,
                },
            ],
        }

    return None


# ── Public API ──────────────────────────────────────────────────


def install_tool(
    tool: str,
    *,
    cli: str = "",
    sudo_password: str = "",
    override_command: list[str] | None = None,
) -> dict[str, Any]:
    """Install a missing devops tool.

    Args:
        tool: Tool name (e.g. "helm", "ruff").
        cli: CLI binary name to check (defaults to *tool*).
        sudo_password: Password for sudo, required for system packages.
        override_command: If provided, run this command instead of the recipe.
                          Used by remediation options (e.g. install compatible version).

    Returns:
        {"ok": True, "message": "...", ...} on success,
        {"ok": False, "error": "...", ...} on failure,
        {"ok": False, "needs_sudo": True, ...} when password is required.
    """
    tool = tool.lower().strip()
    cli = (cli or tool).strip()

    if not tool:
        return {"ok": False, "error": "No tool specified"}

    # Already installed? (skip for overrides — explicit remediation)
    if not override_command and shutil.which(cli):
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

    # Use override command or find install recipe
    if override_command:
        cmd = override_command
        needs_sudo = False
    elif tool in _NO_SUDO_RECIPES:
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

    # ── Dependency pre-check ──
    # Check if the recipe's runtime binary exists before executing.
    _RUNTIME_DEPS: dict[str, dict[str, str]] = {
        "cargo":  {"tool": "cargo",  "label": "Cargo (Rust)"},
        "npm":    {"tool": "npm",    "label": "npm"},
        "node":   {"tool": "node",   "label": "Node.js"},
    }
    # Tools whose recipes wrap via bash -c but still need a specific runtime
    _TOOL_REQUIRES: dict[str, str] = {
        "cargo-audit": "cargo",
        "cargo-outdated": "cargo",
    }
    # Check by tool name first (for bash -c wrapped recipes), then by cmd[0]
    dep_bin = _TOOL_REQUIRES.get(tool)
    if not dep_bin:
        runtime_bin = cmd[0] if not needs_sudo else cmd[3]
        if runtime_bin not in ("bash", "sudo", sys.executable):
            dep_bin = runtime_bin
    if dep_bin:
        dep_info = _RUNTIME_DEPS.get(dep_bin)
        if dep_info and not shutil.which(dep_bin):
            _audit(
                "🔧 Tool Install — Missing Dependency",
                f"{tool} requires {dep_info['label']} which is not installed",
                action="blocked",
                target=tool,
            )
            return {
                "ok": False,
                "missing_dependency": dep_info,
                "error": f"{tool} requires {dep_info['label']} to be installed first.",
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
        remediation = _analyse_install_failure(tool, cli, stderr)

        _audit(
            "❌ Tool Install Failed",
            f"{tool}: {error_msg}",
            action="failed",
            target=tool,
            detail={"tool": tool, "exit_code": result.returncode, "stderr": stderr[:500]},
        )
        response: dict[str, Any] = {
            "ok": False,
            "error": error_msg,
            "stderr": stderr,
            "stdout": result.stdout[-2000:] if result.stdout else "",
        }
        if remediation:
            response["remediation"] = remediation
        return response

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
