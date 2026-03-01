"""
CLI commands for Security operations.

Thin wrappers over ``src.core.services.security_ops``.

Sub-modules:
    detect.py   — scan, sensitive files
    observe.py  — gitignore analysis, posture
    generate.py — gitignore generation
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


def _detect_stack_names(project_root: Path) -> list[str]:
    """Detect programming stacks in the project for .gitignore generation."""
    try:
        from src.core.services.env_ops import detect_stacks

        stacks = detect_stacks(project_root)
        return [s["name"] for s in stacks if s.get("name")]
    except Exception:
        return []


@click.group()
def security() -> None:
    """Security — secret scanning, .gitignore management, posture analysis."""


from . import detect, observe, generate  # noqa: E402, F401
