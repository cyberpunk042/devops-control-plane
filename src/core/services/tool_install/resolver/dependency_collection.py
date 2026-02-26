"""
L2 Resolver — Dependency collection.

Collects and orders tool dependencies from recipes.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from typing import Any

from src.core.services.tool_install.data.recipes import TOOL_RECIPES
from src.core.services.tool_install.detection.system_deps import _is_pkg_installed
from src.core.services.tool_install.resolver.method_selection import (
    _extract_packages_from_cmd,
    _is_batchable,
    _pick_install_method,
)

logger = logging.getLogger(__name__)

# Cache for _can_reach() network probes (host → {ok, ts})
_REACH_CACHE: dict[str, dict] = {}


def _collect_deps(
    tool_id: str,
    system_profile: dict,
    visited: set[str],
    batch_packages: list[str],
    tool_steps: list[dict],
    batched_tools: list[str],
    post_env_map: dict[str, str],
) -> None:
    """Walk the dependency tree depth-first, collecting steps.

    Mutates *batch_packages*, *tool_steps*, *batched_tools*, and
    *post_env_map* in place.

    Args:
        tool_id: Tool to resolve.
        system_profile: Phase 1 system detection output.
        visited: Set of already-processed tool IDs (cycle guard).
        batch_packages: Accumulator for batchable system packages.
        tool_steps: Accumulator for non-batchable tool install steps.
        batched_tools: Accumulator for tool IDs installed via batch
                       (needed for post_install / verify even when batched).
        post_env_map: Maps tool_id → post_env string.
    """
    if tool_id in visited:
        return
    visited.add(tool_id)

    recipe = TOOL_RECIPES.get(tool_id)
    if not recipe:
        # ── Dynamic fallback: resolve without a full recipe ────
        from src.core.services.tool_install.resolver.dynamic_dep_resolver import (
            resolve_dep_install,
        )

        # Already installed?
        if shutil.which(tool_id):
            return

        resolution = resolve_dep_install(tool_id, system_profile)
        if resolution is None:
            logger.warning(
                "Dependency '%s' not found in TOOL_RECIPES and "
                "could not be dynamically resolved",
                tool_id,
            )
            return

        source = resolution["source"]

        if source == "recipe":
            # Resolver found it in TOOL_RECIPES after all (shouldn't happen
            # since we just checked, but guard against race)
            pass
        elif source == "special_installer":
            # Standalone installer script (rustup, nvm, etc.)
            tool_steps.append({
                "tool_id": tool_id,
                "recipe": {
                    "cli": tool_id,
                    "label": tool_id,
                    "install": {"_default": resolution["install_cmd"]},
                },
                "method": "_default",
                "_dynamic": True,
            })
        else:
            # System package (known_package, lib_mapping, or identity)
            for pkg in resolution["package_names"]:
                pm = system_profile.get("package_manager", {}).get("primary", "apt")
                if not _is_pkg_installed(pkg, pm) and pkg not in batch_packages:
                    batch_packages.append(pkg)
            batched_tools.append(tool_id)

        return

    cli = recipe.get("cli", tool_id)

    # Skip if already installed
    if shutil.which(cli):
        return

    pm = system_profile.get("package_manager", {}).get("primary", "apt")
    family = system_profile.get("distro", {}).get("family", "debian")
    snap_ok = system_profile.get("package_manager", {}).get("snap_available", False)

    # 1. Recurse into binary deps first (depth-first)
    for dep_id in recipe.get("requires", {}).get("binaries", []):
        _collect_deps(
            dep_id, system_profile, visited,
            batch_packages, tool_steps, batched_tools, post_env_map,
        )

    # 2. Collect system packages for this tool
    pkg_map = recipe.get("requires", {}).get("packages", {})
    family_pkgs = pkg_map.get(family, [])
    for pkg in family_pkgs:
        if not _is_pkg_installed(pkg, pm) and pkg not in batch_packages:
            batch_packages.append(pkg)

    # 3. Pick install method
    method = _pick_install_method(recipe, pm, snap_ok)
    if method is None:
        logger.warning(
            "No install method for '%s' on pm=%s", tool_id, pm,
        )
        return

    # 4. Batchable or not?
    if _is_batchable(method, pm):
        pkgs = _extract_packages_from_cmd(recipe["install"][method], pm)
        for pkg in pkgs:
            if not _is_pkg_installed(pkg, pm) and pkg not in batch_packages:
                batch_packages.append(pkg)
        batched_tools.append(tool_id)
    else:
        tool_steps.append({
            "tool_id": tool_id,
            "recipe": recipe,
            "method": method,
        })

    # 5. Track post_env
    pe = recipe.get("post_env", "")
    if pe:
        post_env_map[tool_id] = pe


def _can_reach(endpoint: str, *, timeout: int = 5) -> bool:
    """Probe if a network endpoint is reachable.

    Uses an HTTP HEAD request with a short timeout. Results are
    cached for 60 seconds to avoid hammering the same host.

    Args:
        endpoint: URL or hostname (e.g. ``"https://pypi.org"``
                  or ``"registry.npmjs.org"``).
        timeout: Probe timeout in seconds.

    Returns:
        True if reachable, False if not.
    """
    import urllib.request

    # Normalize to URL
    url = endpoint if endpoint.startswith("http") else f"https://{endpoint}"
    host = url.split("//")[-1].split("/")[0]

    # Check cache
    cached = _REACH_CACHE.get(host)
    if cached and (time.time() - cached["ts"]) < 60:
        return cached["ok"]

    try:
        req = urllib.request.Request(
            url, method="HEAD",
            headers={"User-Agent": "devops-cp/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout):
            pass
        _REACH_CACHE[host] = {"ok": True, "ts": time.time()}
        return True
    except Exception:
        _REACH_CACHE[host] = {"ok": False, "ts": time.time()}
        return False
