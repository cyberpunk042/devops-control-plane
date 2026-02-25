"""
L3 Detection — Tool version checking.

Read-only probes: runs ``--version`` commands and parses output.
Also provides ``check_updates`` (local version scan).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys

from src.core.services.tool_install.data.recipes import TOOL_RECIPES

_PIP: list[str] = [sys.executable, "-m", "pip"]

VERSION_COMMANDS: dict[str, tuple[list[str], str]] = {
    # pip tools
    "ruff":         (["ruff", "--version"],           r"ruff\s+(\d+\.\d+\.\d+)"),
    "black":        (["black", "--version"],           r"black.*?(\d+\.\d+\.\d+)"),
    "mypy":         (["mypy", "--version"],            r"mypy\s+(\d+\.\d+(?:\.\d+)?)"),
    "pytest":       (["pytest", "--version"],          r"pytest\s+(\d+\.\d+\.\d+)"),
    "pip-audit":    (["pip-audit", "--version"],       r"pip-audit\s+(\d+\.\d+\.\d+)"),
    "safety":       (["safety", "--version"],          r"(\d+\.\d+\.\d+)"),
    "bandit":       (["bandit", "--version"],          r"bandit\s+(\d+\.\d+\.\d+)"),
    # npm tools
    "eslint":       (["eslint", "--version"],          r"v?(\d+\.\d+\.\d+)"),
    "prettier":     (["prettier", "--version"],        r"(\d+\.\d+\.\d+)"),
    # cargo tools
    "cargo-audit":  (["cargo", "audit", "--version"],  r"cargo-audit\s+(\d+\.\d+\.\d+)"),
    "cargo-outdated": (["cargo", "outdated", "--version"], r"cargo-outdated\s+v?(\d+\.\d+\.\d+)"),
    # devops / infra
    "docker":       (["docker", "--version"],          r"Docker version\s+(\d+\.\d+\.\d+)"),
    "kubectl":      (["kubectl", "version", "--client=true"],
                                                       r"v(\d+\.\d+\.\d+)"),
    "helm":         (["helm", "version", "--short"],   r"v(\d+\.\d+\.\d+)"),
    "terraform":    (["terraform", "version"],         r"Terraform\s+v(\d+\.\d+\.\d+)"),
    "git":          (["git", "--version"],              r"git version\s+(\d+\.\d+\.\d+)"),
    "go":           (["go", "version"],                 r"go(\d+\.\d+\.\d+)"),
    "node":         (["node", "--version"],              r"v(\d+\.\d+\.\d+)"),
    "cargo":        (["cargo", "--version"],             r"cargo\s+(\d+\.\d+\.\d+)"),
    "rustc":        (["rustc", "--version"],             r"rustc\s+(\d+\.\d+\.\d+)"),
    "gh":           (["gh", "--version"],                r"gh version\s+(\d+\.\d+\.\d+)"),
    "trivy":        (["trivy", "version"],               r"Version:\s+(\d+\.\d+\.\d+)"),
    "hugo":         (["hugo", "version"],                r"v(\d+\.\d+\.\d+)"),
    "k9s":          (["k9s", "version", "--short"],     r"v(\d+\.\d+\.\d+)"),
    "argocd":       (["argocd", "version", "--client"], r"v(\d+\.\d+\.\d+)"),
    "ansible":      (["ansible", "--version"],          r"ansible.*?(\d+\.\d+\.\d+)"),
    "minikube":     (["minikube", "version", "--short"], r"v(\d+\.\d+\.\d+)"),
    "k3s":          (["k3s", "--version"],               r"v(\d+\.\d+\.\d+)"),
    "skaffold":     (["skaffold", "version"],            r"v(\d+\.\d+\.\d+)"),
    "kustomize":    (["kustomize", "version"],           r"v(\d+\.\d+\.\d+)"),
    "lazydocker":   (["lazydocker", "--version"],        r"Version:\s*(\d+\.\d+\.\d+)"),
    "containerd":   (["containerd", "--version"],        r"containerd\s+v?(\d+\.\d+\.\d+)"),
    "cri-o":        (["crio", "--version"],              r"Version:\s+(\d+\.\d+\.\d+)"),
    "podman":       (["podman", "--version"],            r"podman version\s+(\d+\.\d+\.\d+)"),
    "nerdctl":      (["nerdctl", "--version"],           r"nerdctl version\s+(\d+\.\d+\.\d+)"),
    "act":          (["act", "--version"],               r"version\s+(\d+\.\d+\.\d+)"),
    "pip":          (_PIP + ["--version"],               r"pip\s+(\d+\.\d+\.\d+)"),
    "npm":          (["npm", "--version"],               r"(\d+\.\d+\.\d+)"),
}


def get_tool_version(tool: str) -> str | None:
    """Get the installed version of a tool.

    Uses ``VERSION_COMMANDS`` to look up the command and regex pattern.
    Falls back to recipe's ``version_command`` / ``version_pattern``
    fields if the tool isn't in ``VERSION_COMMANDS``.

    Returns:
        Semver string (e.g. ``"0.5.1"``) or ``None`` if the tool
        is not installed or version can't be determined.
    """
    # Look up from the static table first
    entry = VERSION_COMMANDS.get(tool)

    # Fall back to recipe override
    if not entry:
        recipe = TOOL_RECIPES.get(tool, {})
        vcmd = recipe.get("version_command")
        vpat = recipe.get("version_pattern")
        if vcmd and vpat:
            entry = (vcmd, vpat)
        else:
            return None

    cmd, pattern = entry
    cli = cmd[0]
    if not shutil.which(cli):
        return None

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
        )
        # Some tools write version to stderr (e.g. mypy in some versions)
        output = (result.stdout or "") + (result.stderr or "")
        match = re.search(pattern, output)
        if match:
            return match.group(1)
    except (subprocess.TimeoutExpired, Exception):
        pass

    return None


def check_updates(
    tools: list[str] | None = None,
) -> list[dict]:
    """Check installed tools for their current version.

    Returns a list of status dicts per installed tool.

    Note: Latest-version fetching (comparing with PyPI, apt-cache, etc.)
    is deferred to a later phase — requires network calls and separate
    caching strategy.  This function returns what the system CAN detect
    locally and cheaply.

    Args:
        tools: Specific tools to check.  Defaults to all TOOL_RECIPES.

    Returns:
        List of ``{"tool": "...", "installed": True, "version": "..."}``
        dicts for installed tools.
    """
    if tools is None:
        tools = list(TOOL_RECIPES.keys())

    results = []
    for tool_id in tools:
        recipe = TOOL_RECIPES.get(tool_id, {})
        cli = recipe.get("cli", tool_id)
        installed = shutil.which(cli) is not None

        if not installed:
            continue

        version = get_tool_version(tool_id)
        has_update_cmd = bool(recipe.get("update"))

        results.append({
            "tool": tool_id,
            "installed": True,
            "version": version,
            "has_update": has_update_cmd,
        })

    return results
