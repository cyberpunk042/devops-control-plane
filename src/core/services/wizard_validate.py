"""
Wizard state validation — input validation before generation.

Validates wizard state dicts to catch misconfigurations early with
clear, actionable error messages. Used before any generation step.

Channel-independent: no Flask or HTTP dependency.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path


# ── K8s namespace validation ────────────────────────────────────────
# RFC 1123: lowercase alphanumeric, hyphens allowed (not at start/end)
_K8S_NS_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")

# ── Docker registry URL: scheme://host or just host/path ────────────
_REGISTRY_RE = re.compile(
    r"^([a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?"
    r"(:[0-9]+)?)"     # host:port
    r"(/[a-zA-Z0-9._/-]+)?$"  # path
)


def validate_wizard_state(state: dict, *, project_root: Path | None = None) -> dict:
    """Validate a wizard state dict before generation.

    Returns:
        {"ok": True, "warnings": [...]} on success.
        {"ok": False, "errors": [...], "warnings": [...]} on failure.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # ── K8s namespace ───────────────────────────────────────────
    deploy = state.get("deploy_config", {})
    ns = deploy.get("namespace", "")
    if ns and not _K8S_NS_RE.match(ns):
        errors.append(
            f"Invalid K8s namespace: {ns!r}. "
            "Must be lowercase alphanumeric with hyphens, "
            "1–63 chars, not starting/ending with hyphen."
        )

    # Multi-env namespaces
    for env_name in state.get("environments", []):
        if env_name and not _K8S_NS_RE.match(env_name):
            errors.append(
                f"Invalid environment name (used as namespace): {env_name!r}. "
                "Must be lowercase alphanumeric with hyphens."
            )

    # ── Docker registry URL ─────────────────────────────────────
    for svc in state.get("docker_services", []):
        registry = svc.get("registry", "")
        if registry and not _REGISTRY_RE.match(registry):
            errors.append(
                f"Malformed Docker registry URL: {registry!r}. "
                "Expected format: host[:port][/path] "
                "(e.g. 'ghcr.io/myorg', 'docker.io/library')."
            )

    # ── Deploy method validation ────────────────────────────────
    method = deploy.get("method", "")
    if method and method not in ("kubectl", "skaffold", "helm"):
        errors.append(
            f"Invalid deploy method: {method!r}. "
            "Must be 'kubectl', 'skaffold', or 'helm'."
        )

    # ── Helm chart path ─────────────────────────────────────────
    chart_path = deploy.get("chart_path", "")
    if chart_path and project_root:
        if not (project_root / chart_path).exists():
            warnings.append(
                f"Helm chart path does not exist: {chart_path!r}. "
                "It will be created during generation, or ensure it exists."
            )

    # ── Terraform provider ──────────────────────────────────────
    tf = state.get("terraform_config", {})
    tf_provider = tf.get("provider", "")
    if tf_provider and tf_provider not in ("aws", "google", "azurerm"):
        errors.append(
            f"Unknown Terraform provider: {tf_provider!r}. "
            "Supported: 'aws', 'google', 'azurerm'."
        )

    # ── CI secret references — advisory warnings ────────────────
    # We can't verify secrets exist, but we can flag common ones
    if deploy.get("method") and not state.get("_skip_secret_warnings"):
        warnings.append(
            "CI deploy jobs will reference ${{ secrets.KUBECONFIG }}. "
            "Ensure this secret is configured in your GitHub repository."
        )

    if tf_provider == "aws":
        warnings.append(
            "Terraform AWS jobs reference ${{ secrets.AWS_ACCESS_KEY_ID }} "
            "and ${{ secrets.AWS_SECRET_ACCESS_KEY }}. "
            "Ensure these are configured."
        )

    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}
    return {"ok": True, "warnings": warnings}


def check_required_tools(state: dict) -> dict:
    """Check if required CLI tools are installed for the given wizard state.

    Returns:
        {
            "ok": True/False,
            "tools": {
                "docker": {"installed": True, "required": True},
                ...
            },
            "missing": ["docker", "skaffold"],
            "install_available": ["docker", "skaffold"],
        }
    """
    from src.core.services.tool_install import _NO_SUDO_RECIPES, _SUDO_RECIPES

    # Determine which tools are required based on state
    required: dict[str, str] = {}  # tool_name → reason

    if state.get("docker_services"):
        required["docker"] = "Docker services configured"

    deploy = state.get("deploy_config", {})
    method = deploy.get("method", "")
    if method == "kubectl" or deploy:
        required["kubectl"] = "Kubernetes deployment configured"
    if method == "skaffold":
        required["skaffold"] = "Skaffold deployment method selected"
    if method == "helm":
        required["helm"] = "Helm deployment method selected"

    if state.get("terraform_config"):
        required["terraform"] = "Terraform infrastructure configured"

    # Check each tool
    tools: dict[str, dict] = {}
    missing: list[str] = []
    install_available: list[str] = []

    for tool_name, reason in required.items():
        installed = shutil.which(tool_name) is not None
        has_recipe = tool_name in _NO_SUDO_RECIPES or tool_name in _SUDO_RECIPES

        tools[tool_name] = {
            "installed": installed,
            "required": True,
            "reason": reason,
            "install_available": has_recipe,
        }

        if not installed:
            missing.append(tool_name)
            if has_recipe:
                install_available.append(tool_name)

    return {
        "ok": len(missing) == 0,
        "tools": tools,
        "missing": missing,
        "install_available": install_available,
    }
