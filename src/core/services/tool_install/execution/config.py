"""
L4 Execution — Template rendering and config generation.

Renders templates with environment-sourced built-in variables
and generates shell config lines.
"""

from __future__ import annotations

import os
import platform
import re
from pathlib import Path

from src.core.services.tool_install.data.profile_maps import _PROFILE_MAP

logger = __import__('logging').getLogger(__name__)


def _render_template(template: str, inputs: dict) -> str:
    """Substitute ``{var}`` placeholders with input values.

    Simple string replacement — no Jinja, no escaping.

    **Built-in variables** are auto-populated from the environment
    and merged under user-provided inputs (user inputs take priority):

    - ``{user}`` — current username
    - ``{home}`` — home directory
    - ``{arch}`` — machine architecture (``amd64``, ``arm64``)
    - ``{distro}`` — distro ID (``ubuntu``, ``fedora``, etc.)
    - ``{tool_name}`` — tool being installed (if in inputs)
    - ``{nproc}`` — CPU core count

    Args:
        template: Template string with ``{key}`` tokens.
        inputs: Mapping of input IDs to their resolved values.

    Returns:
        Rendered string.
    """
    # Built-in variables (environment-sourced)
    machine = platform.machine().lower()
    _ARCH_MAP = {"x86_64": "amd64", "aarch64": "arm64", "armv7l": "armhf"}
    builtins = {
        "user": os.getenv("USER", os.getenv("LOGNAME", "unknown")),
        "home": str(Path.home()),
        "arch": _ARCH_MAP.get(machine, machine),
        "nproc": str(os.cpu_count() or 1),
    }
    # Distro detection (lightweight)
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            for line in f:
                if line.startswith("ID="):
                    builtins["distro"] = line.strip().split("=", 1)[1].strip('"')
                    break
    except (FileNotFoundError, OSError):
        builtins["distro"] = platform.system().lower()

    # Merge: builtins first, then user inputs override
    merged = {**builtins, **inputs}

    result = template
    for key, value in merged.items():
        result = result.replace(f"{{{key}}}", str(value))
    return result


def _shell_config_line(
    shell_type: str,
    *,
    path_entry: str | None = None,
    env_var: tuple[str, str] | None = None,
) -> str:
    """Generate shell-specific PATH or env export line.

    Args:
        shell_type: ``"bash"`` | ``"zsh"`` | ``"fish"`` | etc.
        path_entry: Directory to add to PATH, e.g. ``"$HOME/.cargo/bin"``.
        env_var: Tuple of ``(name, value)`` e.g. ``("GOPATH", "$HOME/go")``.

    Returns:
        Shell-specific export line.
    """
    if shell_type == "fish":
        if path_entry:
            return f"set -gx PATH {path_entry} $PATH"
        if env_var:
            return f"set -gx {env_var[0]} {env_var[1]}"
    else:
        # POSIX (bash, zsh, sh, dash, ash)
        if path_entry:
            return f'export PATH="{path_entry}:$PATH"'
        if env_var:
            return f'export {env_var[0]}="{env_var[1]}"'
    return ""
