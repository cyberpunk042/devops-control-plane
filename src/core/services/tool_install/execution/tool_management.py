"""
L4 Execution — Tool update and removal.

High-level operations for updating and removing installed tools.
"""

from __future__ import annotations

import logging
import shutil
from typing import Any

from src.core.services.tool_install.data.recipes import TOOL_RECIPES
from src.core.services.tool_install.data.undo_catalog import UNDO_COMMANDS
from src.core.services.tool_install.detection.tool_version import get_tool_version
from src.core.services.tool_install.execution.subprocess_runner import _run_subprocess

logger = logging.getLogger(__name__)


def update_tool(
    tool: str,
    *,
    sudo_password: str = "",
) -> dict[str, Any]:
    """Update an installed tool to the latest version.

    Uses the recipe's ``update`` command map, resolved for the current
    system.  Records version before and after.

    Args:
        tool: Tool ID.
        sudo_password: Sudo password if the update needs root.

    Returns:
        ``{"ok": True, "from_version": "...", "to_version": "..."}``
        on success, or error dict.
    """
    recipe = TOOL_RECIPES.get(tool)
    if not recipe:
        return {"ok": False, "error": f"No recipe for '{tool}'"}

    cli = recipe.get("cli", tool)
    if not shutil.which(cli):
        return {
            "ok": False,
            "error": f"{tool} is not installed. Install it first.",
        }

    update_map = recipe.get("update")
    if not update_map:
        return {"ok": False, "error": f"No update command defined for {tool}"}

    # Resolve command for this system
    resolved = _pick_method_command(update_map)
    if not resolved:
        return {"ok": False, "error": f"No update method available for {tool}"}

    cmd, method = resolved
    needs_sudo = recipe.get("needs_sudo", {}).get(method, False)

    # Record version before update
    version_before = get_tool_version(tool)

    _audit(
        "⬆️ Tool Update",
        f"{tool}: updating via {method}",
        action="started",
        target=tool,
    )

    result = _run_subprocess(
        cmd,
        needs_sudo=needs_sudo,
        sudo_password=sudo_password,
        timeout=300,  # cargo recompiles can be slow
    )

    if not result["ok"]:
        _audit(
            "❌ Tool Update Failed",
            f"{tool}: {result['error']}",
            action="failed",
            target=tool,
        )
        return result

    # Record version after update
    version_after = get_tool_version(tool)

    if version_before and version_after and version_before == version_after:
        msg = f"{tool} is already at the latest version ({version_after})"
        _audit(
            "✅ Tool Already Latest",
            msg,
            action="completed",
            target=tool,
        )
        return {"ok": True, "message": msg, "already_latest": True}

    change = (
        f"{version_before} → {version_after}"
        if version_before and version_after
        else f"updated to {version_after}" if version_after
        else "updated"
    )
    msg = f"{tool} updated: {change}"

    _audit(
        "⬆️ Tool Updated",
        msg,
        action="updated",
        target=tool,
    )

    return {
        "ok": True,
        "message": msg,
        "from_version": version_before,
        "to_version": version_after,
        "invalidates": ["l0_detection", "tool_status"],
    }


def remove_tool(
    tool: str,
    *,
    sudo_password: str = "",
) -> dict[str, Any]:
    """Remove (uninstall) a tool using the appropriate method.

    Resolution order for the remove command:
      1. Recipe's explicit ``remove`` command map (if defined)
      2. ``UNDO_COMMANDS`` catalog based on the install method

    Args:
        tool: Tool ID from TOOL_RECIPES.
        sudo_password: Sudo password if removal needs root.

    Returns:
        ``{"ok": True, "message": "..."}`` on success, or error dict.
    """
    recipe = TOOL_RECIPES.get(tool)
    if not recipe:
        return {"ok": False, "error": f"No recipe for '{tool}'"}

    cli = recipe.get("cli", tool)
    if not shutil.which(cli):
        return {
            "ok": False,
            "error": f"{tool} is not installed.",
        }

    # 1. Try explicit remove command in recipe
    remove_map = recipe.get("remove")
    if remove_map:
        resolved = _pick_method_command(remove_map)
        if resolved:
            cmd, method = resolved
            needs_sudo = recipe.get("needs_sudo", {}).get(method, True)
            _audit(
                "🗑️ Tool Remove",
                f"{tool}: removing via {method}",
                action="started",
                target=tool,
            )
            result = _run_subprocess(
                cmd,
                needs_sudo=needs_sudo,
                sudo_password=sudo_password,
                timeout=120,
            )
            if result["ok"]:
                result["message"] = f"{tool} removed"
                result["invalidates"] = ["l0_detection", "tool_status"]
                _audit(
                    "✅ Tool Removed",
                    f"{tool} removed via {method}",
                    action="completed",
                    target=tool,
                )
            else:
                _audit(
                    "❌ Tool Remove Failed",
                    f"{tool}: {result.get('error', '')}",
                    action="failed",
                    target=tool,
                )
            return result

    # 2. Derive remove command from install method + UNDO_COMMANDS
    install_map = recipe.get("install", {})
    resolved = _pick_method_command(install_map)
    if not resolved:
        return {"ok": False, "error": f"Cannot determine install method for {tool}"}

    _cmd, method = resolved
    # Map method to UNDO_COMMANDS key
    undo_key = method
    if method == "_default":
        # For _default (curl|bash scripts, binary downloads), removal
        # is by deleting the binary from PATH
        binary_path = shutil.which(cli)
        if binary_path:
            undo = UNDO_COMMANDS.get("binary", {})
            cmd = [t.replace("{install_path}", binary_path)
                   for t in undo.get("command", ["rm", binary_path])]
            needs_sudo = undo.get("needs_sudo", True)
        else:
            return {"ok": False, "error": f"Cannot find {cli} binary for removal"}
    elif undo_key in UNDO_COMMANDS:
        undo = UNDO_COMMANDS[undo_key]
        # Substitute {package} with the package name(s)
        # For apt/dnf/pacman: the package name is typically the tool name
        packages = recipe.get("packages", [tool])
        if isinstance(packages, dict):
            packages = packages.get(method, [tool])
        pkg_str = " ".join(packages) if isinstance(packages, list) else str(packages)
        cmd = [t.replace("{package}", pkg_str) for t in undo["command"]]
        needs_sudo = undo.get("needs_sudo", True)
    else:
        return {"ok": False, "error": f"No removal method known for {tool} (method: {method})"}

    _audit(
        "🗑️ Tool Remove",
        f"{tool}: removing via {undo_key}",
        action="started",
        target=tool,
    )

    result = _run_subprocess(
        cmd,
        needs_sudo=needs_sudo,
        sudo_password=sudo_password,
        timeout=120,
    )
    if result["ok"]:
        result["message"] = f"{tool} removed"
        result["invalidates"] = ["l0_detection", "tool_status"]
        _audit(
            "✅ Tool Removed",
            f"{tool} removed via {undo_key}",
            action="completed",
            target=tool,
        )
    else:
        _audit(
            "❌ Tool Remove Failed",
            f"{tool}: {result.get('error', '')}",
            action="failed",
            target=tool,
        )
    return result
