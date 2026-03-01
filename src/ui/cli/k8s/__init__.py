"""
CLI commands for Kubernetes integration.

Thin wrappers over ``src.core.services.k8s_ops``.

Sub-modules:
    detect.py   — status, validate
    observe.py  — cluster, get resources
    generate.py — manifest generation
"""

from __future__ import annotations

import sys
from pathlib import Path

import click


def _resolve_project_root(ctx: click.Context) -> Path:
    """Resolve project root from context or CWD."""
    config_path: Path | None = ctx.obj.get("config_path")
    if config_path is None:
        from src.core.config.loader import find_project_file

        config_path = find_project_file()
    return config_path.parent.resolve() if config_path else Path.cwd()


@click.group("k8s")
def k8s() -> None:
    """Kubernetes — manifests, validation, cluster status, generation."""


from . import detect, observe, generate  # noqa: E402, F401
