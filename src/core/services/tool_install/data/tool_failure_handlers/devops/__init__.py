"""
Tool-specific failure handlers — DevOps / Infrastructure tools.

Merges handlers from: containers, k8s, cloud
"""

from __future__ import annotations

from .containers import _DOCKER_HANDLERS, _DOCKER_COMPOSE_HANDLERS
from .k8s import _HELM_HANDLERS, _KUBECTL_HANDLERS
from .cloud import _GH_HANDLERS, _TERRAFORM_HANDLERS

DEVOPS_TOOL_HANDLERS: dict[str, list[dict]] = {
    "docker": _DOCKER_HANDLERS,
    "docker-compose": _DOCKER_COMPOSE_HANDLERS,
    "helm": _HELM_HANDLERS,
    "kubectl": _KUBECTL_HANDLERS,
    "gh": _GH_HANDLERS,
    "terraform": _TERRAFORM_HANDLERS,
}
