"""
CLI commands for the Secrets Vault.

Thin wrappers over ``src.core.services.vault``, ``vault_io``,
and ``vault_env_ops``.

Sub-modules:
    crypto.py   — lock, unlock, status, export
    detect.py   — detect secret files
    env_mgmt.py — keys, templates, create, add/update/delete key, activate
"""

from __future__ import annotations

from pathlib import Path

import click


def _resolve_project_root(ctx: click.Context) -> Path:
    """Resolve project root from context or CWD."""
    config_path: Path | None = ctx.obj.get("config_path")
    if config_path is None:
        from src.core.config.loader import find_project_file

        config_path = find_project_file()
    return config_path.parent.resolve() if config_path else Path.cwd()


def _env_path(project_root: Path, env_name: str = "") -> Path:
    """Resolve .env file path from optional env name."""
    if env_name:
        return project_root / f".env.{env_name}"
    return project_root / ".env"


@click.group()
def vault() -> None:
    """Secrets Vault — encrypt, decrypt, and manage secrets."""


from . import crypto, detect, env_mgmt  # noqa: E402, F401
