"""
L4 Execution — Build-from-source helpers.

Functions for validating toolchains, planning builds, and
executing source/build/install steps.
"""

from __future__ import annotations

import logging
import os
import platform
import re
import shutil
from pathlib import Path
from typing import Any

from src.core.services.tool_install.data.constants import BUILD_TIMEOUT_TIERS
from src.core.services.tool_install.detection.hardware import (
    detect_build_toolchain,
    _read_available_ram_mb,
    _read_disk_free_mb,
)
from src.core.services.tool_install.execution.subprocess_runner import _run_subprocess

logger = logging.getLogger(__name__)


def _validate_toolchain(
    requires_toolchain: list[str],
) -> dict:
    """Validate that required build tools are installed.

    Checks each tool in ``requires_toolchain`` against the system
    PATH.  Returns missing tools with install suggestions.

    Args:
        requires_toolchain: List of required tool names, e.g.
            ``["gcc", "make", "cmake"]``.

    Returns:
        ``{"ok": True, "available": [...]}`` if all tools present,
        ``{"ok": False, "missing": [...], "suggestion": "..."}`` otherwise.
    """
    available: list[str] = []
    missing: list[str] = []

    for tool in requires_toolchain:
        if shutil.which(tool):
            available.append(tool)
        else:
            missing.append(tool)

    if not missing:
        return {"ok": True, "available": available}

    # Build install suggestion
    suggestion_parts = []
    # Check if build-essential would cover it
    essential_tools = {"gcc", "g++", "make", "libc-dev", "dpkg-dev"}
    if missing and set(missing) & essential_tools:
        suggestion_parts.append("Install build-essential: apt-get install -y build-essential")

    other_missing = [t for t in missing if t not in essential_tools]
    if other_missing:
        suggestion_parts.append(
            f"Install: {', '.join(other_missing)}"
        )

    return {
        "ok": False,
        "missing": missing,
        "available": available,
        "suggestion": " | ".join(suggestion_parts) if suggestion_parts else f"Install: {', '.join(missing)}",
    }


def _check_build_resources(
    disk_estimate_mb: int = 500,
    ram_estimate_mb: int = 512,
    build_dir: str = "/tmp",
) -> dict:
    """Check if system has sufficient resources for a build.

    Checks available disk space in the build directory and available
    RAM.  Returns a status dict with any issues found.

    Args:
        disk_estimate_mb: Estimated disk space needed (MB).
        ram_estimate_mb: Estimated RAM needed (MB).
        build_dir: Directory where the build will happen.

    Returns::

        {"ok": True, "disk_free_mb": N, "ram_free_mb": N}
        or
        {"ok": False, "issues": [...], ...}
    """
    import shutil as sh

    issues: list[str] = []

    # Disk check
    disk_free_mb = 0
    try:
        disk = sh.disk_usage(build_dir)
        disk_free_mb = disk.free // (1024 * 1024)
        if disk_free_mb < disk_estimate_mb:
            issues.append(
                f"Need {disk_estimate_mb}MB disk, have {disk_free_mb}MB"
            )
    except OSError:
        issues.append(f"Cannot check disk at {build_dir}")

    # RAM check
    ram_free_mb = 0
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    ram_free_mb = int(line.split()[1]) // 1024
                    break
        if ram_free_mb < ram_estimate_mb:
            issues.append(
                f"Need {ram_estimate_mb}MB RAM, have {ram_free_mb}MB"
            )
    except (OSError, ValueError):
        pass  # /proc/meminfo not available (macOS, container)

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "disk_free_mb": disk_free_mb,
        "ram_free_mb": ram_free_mb,
    }


def _substitute_build_vars(
    command: list[str],
    variables: dict[str, str],
) -> list[str]:
    """Replace ``{var}`` placeholders in a command array.

    Handles the standard build variables (``{nproc}``,
    ``{build_dir}``) plus any recipe-specific input values
    (``{cuda_flag}``, ``{build_type}``, etc.).

    Args:
        command: Command array with possible ``{var}`` tokens.
        variables: Mapping of variable names to their values.

    Returns:
        New list with all ``{key}`` tokens substituted.
    """
    result: list[str] = []
    for token in command:
        for key, value in variables.items():
            token = token.replace(f"{{{key}}}", str(value))
        result.append(token)
    return result


def _substitute_install_vars(
    command: list[str],
    profile: dict,
    *,
    version: str = "",
    extra: dict[str, str] | None = None,
) -> list[str]:
    """Replace ``{var}`` placeholders in install commands and URLs.

    Standard variables available:
    - ``{arch}`` — normalized architecture (``amd64``, ``arm64``)
    - ``{version}`` — selected version (if supplied)
    - ``{user}`` — current username
    - ``{home}`` — home directory
    - ``{distro}`` — distro id (``ubuntu``, ``fedora``, etc.)
    - ``{nproc}`` — CPU core count

    Also accepts ``extra`` for recipe-specific variables.

    Args:
        command: Command array with possible ``{var}`` tokens.
        profile: System profile from l0_system_profile().
        version: Selected version string (may be empty).
        extra: Additional key-value substitutions.

    Returns:
        New list with tokens substituted.
    """
    machine = platform.machine().lower()
    variables: dict[str, str] = {
        "arch": _IARCH_MAP.get(machine, machine),
        "user": os.getenv("USER", os.getenv("LOGNAME", "unknown")),
        "home": str(Path.home()),
        "nproc": str(os.cpu_count() or 1),
    }
    # Distro from profile or fallback
    distro_info = profile.get("distro", {})
    variables["distro"] = distro_info.get("id", platform.system().lower())
    variables["distro_family"] = distro_info.get("family", "unknown")

    if version:
        variables["version"] = version

    # Recipe arch map (e.g. x86_64 → amd64 for Hugo)
    arch_map = profile.get("_arch_map", {})
    if arch_map:
        raw_arch = platform.machine().lower()
        variables["arch"] = arch_map.get(raw_arch, variables["arch"])

    if extra:
        variables.update(extra)

    return _substitute_build_vars(command, variables)


def _autotools_plan(
    recipe: dict,
    profile: dict,
    build_dir: str,
) -> list[dict]:
    """Generate plan steps for an autotools (./configure && make) build.

    Produces three steps:
        1. ``./configure`` with optional recipe args
        2. ``make`` with parallel flag from CPU count
        3. ``make install`` with sudo

    Args:
        recipe: Build recipe with optional ``configure_args``,
                ``install_prefix``, ``disk_estimate_mb``.
        profile: System profile from ``l0_system_profile()``.
        build_dir: Absolute path to the source directory.

    Returns:
        Ordered list of step dicts ready for ``execute_plan_step()``.
    """
    nproc = str(profile.get("resources", {}).get("cpu_count", 1))
    configure_args = list(recipe.get("configure_args", []))
    prefix = recipe.get("install_prefix", "/usr/local")

    # Build variable map for substitution
    variables = {"nproc": nproc, "build_dir": build_dir}
    variables.update(recipe.get("input_values", {}))

    # Configure step
    configure_cmd = ["./configure", f"--prefix={prefix}"] + configure_args
    configure_cmd = _substitute_build_vars(configure_cmd, variables)

    steps: list[dict] = [
        {
            "type": "build",
            "label": "Configure (autotools)",
            "command": configure_cmd,
            "cwd": build_dir,
            "needs_sudo": False,
            "timeout": recipe.get("configure_timeout", 120),
        },
        {
            "type": "build",
            "label": f"Compile ({nproc} cores)",
            "command": ["make", f"-j{nproc}"],
            "cwd": build_dir,
            "needs_sudo": False,
            "parallel": True,
            "timeout": BUILD_TIMEOUT_TIERS.get(
                recipe.get("build_size", "medium"), 600,
            ),
        },
        {
            "type": "install",
            "label": "Install (make install)",
            "command": ["make", "install"],
            "cwd": build_dir,
            "needs_sudo": recipe.get("install_needs_sudo", True),
            "timeout": 60,
        },
    ]

    return steps


def _cmake_plan(
    recipe: dict,
    profile: dict,
    build_dir: str,
) -> list[dict]:
    """Generate plan steps for a CMake build.

    Produces three steps:
        1. ``cmake -B build`` with build type and optional flags
        2. ``cmake --build build`` with parallel jobs
        3. ``cmake --install build`` with sudo

    Args:
        recipe: Build recipe with optional ``cmake_args``,
                ``build_type``, ``disk_estimate_mb``.
        profile: System profile from ``l0_system_profile()``.
        build_dir: Absolute path to the source directory.

    Returns:
        Ordered list of step dicts ready for ``execute_plan_step()``.
    """
    nproc = str(profile.get("resources", {}).get("cpu_count", 1))
    cmake_args = list(recipe.get("cmake_args", []))
    build_type = recipe.get("build_type", "Release")
    prefix = recipe.get("install_prefix", "/usr/local")

    # Build variable map
    variables = {"nproc": nproc, "build_dir": build_dir}
    variables.update(recipe.get("input_values", {}))

    # Configure step — cmake generates the build system
    configure_cmd = [
        "cmake", "-B", "build",
        f"-DCMAKE_BUILD_TYPE={build_type}",
        f"-DCMAKE_INSTALL_PREFIX={prefix}",
    ] + cmake_args
    configure_cmd = _substitute_build_vars(configure_cmd, variables)

    steps: list[dict] = [
        {
            "type": "build",
            "label": "CMake configure",
            "command": configure_cmd,
            "cwd": build_dir,
            "needs_sudo": False,
            "timeout": recipe.get("configure_timeout", 60),
        },
        {
            "type": "build",
            "label": f"CMake build ({nproc} cores)",
            "command": ["cmake", "--build", "build", "-j", nproc],
            "cwd": build_dir,
            "needs_sudo": False,
            "parallel": True,
            "timeout": BUILD_TIMEOUT_TIERS.get(
                recipe.get("build_size", "medium"), 600,
            ),
        },
        {
            "type": "install",
            "label": "CMake install",
            "command": ["cmake", "--install", "build"],
            "cwd": build_dir,
            "needs_sudo": recipe.get("install_needs_sudo", True),
            "timeout": 60,
        },
    ]

    return steps


def _cargo_git_plan(
    recipe: dict,
    profile: dict,
) -> list[dict]:
    """Generate plan steps for ``cargo install --git``.

    This is the simplest adapter: a single step that cargo handles
    end-to-end (download → compile → install to ``~/.cargo/bin/``).

    Args:
        recipe: Build recipe with ``git_repo`` (required) and
                optional ``branch``, ``features``.
        profile: System profile (unused but kept for signature
                 consistency with other adapters).

    Returns:
        Single-step list ready for ``execute_plan_step()``.
    """
    git_repo = recipe["git_repo"]
    cmd = ["cargo", "install", "--git", git_repo]

    branch = recipe.get("branch")
    if branch:
        cmd += ["--branch", branch]

    features = recipe.get("features")
    if features:
        cmd += ["--features", ",".join(features)]

    return [{
        "type": "tool",
        "label": f"Build from git ({git_repo.split('/')[-1]})",
        "command": cmd,
        "needs_sudo": False,
        "timeout": BUILD_TIMEOUT_TIERS.get(
            recipe.get("build_size", "medium"), 600,
        ),
    }]


def _build_tarball_download_cmd(
    url: str,
    dest: str,
) -> list[str] | None:
    """Build a shell command to download and extract a tarball.

    Tries download backends in order of preference:
      1. ``curl``  — most common, streams efficiently
      2. ``wget``  — independent of libcurl, true fallback
      3. ``python3`` — uses stdlib urllib, no external deps

    This cascade exists because of circular dependencies:
    building curl from source requires downloading the source,
    but curl might not be installed yet.  wget and python3 urllib
    do NOT depend on libcurl, so they work independently.

    Args:
        url: The tarball URL to download.
        dest: Directory to extract into.

    Returns:
        Shell command list for ``_run_subprocess()``, or ``None``
        if no download backend is available.
    """
    if shutil.which("curl"):
        return [
            "bash", "-c",
            f"curl -fsSL '{url}' | tar xz -C '{dest}' --strip-components=1",
        ]

    if shutil.which("wget"):
        return [
            "bash", "-c",
            f"wget -qO- '{url}' | tar xz -C '{dest}' --strip-components=1",
        ]

    if shutil.which("python3"):
        # Use Python's urllib — no libcurl dependency.
        # Download to a temp file, then extract.
        return [
            "bash", "-c",
            (
                f"python3 -c \""
                f"import urllib.request, tempfile, os; "
                f"tf = tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False); "
                f"urllib.request.urlretrieve('{url}', tf.name); "
                f"tf.close(); "
                f"os.system('tar xzf ' + tf.name + ' -C {dest} --strip-components=1'); "
                f"os.unlink(tf.name)"
                f"\""
            ),
        ]

    return None


def _execute_source_step(
    step: dict,
    *,
    sudo_password: str = "",
) -> dict[str, Any]:
    """Obtain source code — git clone, tarball download, or local path.

    Step format::

        {
            "type": "source",
            "source": {
                "type": "git",
                "repo": "https://github.com/...",
                "branch": "stable",
                "depth": 1,
            },
            "dest": "/tmp/build-dir",
        }
    """
    source = step.get("source", {})
    dest = step.get("dest", step.get("cwd", "/tmp/build"))
    source_type = source.get("type", "git")

    if source_type == "git":
        cmd: list[str] = ["git", "clone"]
        if source.get("branch"):
            cmd += ["--branch", source["branch"]]
        if source.get("depth"):
            cmd += ["--depth", str(source["depth"])]
        cmd += [source["repo"], dest]
        return _run_subprocess(
            cmd,
            timeout=step.get("timeout", 1800),  # M3: builds can take 30+ min
            needs_sudo=step.get("needs_sudo", False),
            sudo_password=sudo_password,
        )

    elif source_type == "tarball":
        url = source.get("url", "")
        if not url:
            return {"ok": False, "error": "No tarball URL specified"}
        # Download and extract — use the best available download backend.
        # This cascade handles the circular dependency problem: when
        # building curl from source, curl itself is not available, so
        # we fall back to wget or python3 urllib.
        Path(dest).mkdir(parents=True, exist_ok=True)
        dl_cmd = _build_tarball_download_cmd(url, dest)
        if dl_cmd is None:
            return {
                "ok": False,
                "error": (
                    "No download tool available (curl, wget, python3). "
                    "Install one via your package manager first."
                ),
            }
        return _run_subprocess(
            dl_cmd,
            timeout=step.get("timeout", 1800),
            needs_sudo=step.get("needs_sudo", False),
            sudo_password=sudo_password,
        )

    elif source_type == "local":
        if not Path(dest).exists():
            return {"ok": False, "error": f"Source not found: {dest}"}
        return {"ok": True, "message": "Source already present"}

    else:
        return {"ok": False, "error": f"Unknown source type: {source_type}"}


def _execute_build_step(
    step: dict,
    *,
    sudo_password: str = "",
    env_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run a build command (make, cmake --build, ninja).

    Supports:
      - ``parallel: true`` — auto-detect CPU count for ``-j`` flag
      - ``jobs: N`` — override parallel job count
      - ``cwd`` — build directory
      - Extended timeout (default 600s for builds)
      - **Progress parsing** from build output
      - **Failure analysis** on build errors
    """
    import multiprocessing

    cmd = list(step["command"])
    cwd = step.get("cwd")

    # ── M4/M5: Pre-build resource check ──
    disk_req = step.get("disk_estimate_mb", 500)
    ram_req = step.get("ram_estimate_mb", 512)
    resources = _check_build_resources(
        disk_estimate_mb=disk_req,
        ram_estimate_mb=ram_req,
        build_dir=cwd or "/tmp",
    )
    if not resources["ok"]:
        issues_str = "; ".join(resources["issues"])
        if resources["disk_free_mb"] < disk_req // 2:
            # Critical shortage — block the build
            return {"ok": False, "error": f"Insufficient resources: {issues_str}"}
        # Marginal — warn but proceed
        logger.warning("Build resource warning: %s", issues_str)

    # Auto-parallel: add -j flag if parallel requested
    if step.get("parallel", True):  # builds default to parallel
        jobs = step.get("jobs", multiprocessing.cpu_count())
        # Only add -j if not already present and command supports it
        has_j = any(a.startswith("-j") for a in cmd)
        if not has_j:
            if cmd[0] in ("make", "ninja"):
                cmd.append(f"-j{jobs}")
            elif cmd[0] == "cmake" and "--build" in cmd:
                cmd += ["--", f"-j{jobs}"]

    # ── ccache integration ──
    if step.get("ccache", True) and shutil.which("ccache"):
        # Inject ccache wrapper via env vars (non-invasive)
        build_env = dict(env_overrides or {})
        if "CC" not in build_env:
            # Detect actual compiler
            cc = shutil.which("gcc") or shutil.which("cc")
            if cc:
                build_env["CC"] = f"ccache {os.path.basename(cc)}"
        if "CXX" not in build_env:
            cxx = shutil.which("g++") or shutil.which("c++")
            if cxx:
                build_env["CXX"] = f"ccache {os.path.basename(cxx)}"
        env_overrides = build_env

    result = _run_subprocess(
        cmd,
        needs_sudo=step.get("needs_sudo", False),
        sudo_password=sudo_password,
        timeout=step.get("timeout", 600),
        env_overrides=env_overrides,
        cwd=cwd,
    )

    # Report ccache stats if available
    if step.get("ccache", True) and shutil.which("ccache") and result.get("ok"):
        try:
            stats = subprocess.run(
                ["ccache", "-s"],
                capture_output=True, text=True, timeout=5,
            )
            if stats.returncode == 0:
                result["ccache_stats"] = stats.stdout.strip()[:500]
        except Exception:
            pass

    # Parse progress from output
    output = result.get("stdout", "") + result.get("stderr", "")
    progress = _parse_build_progress(output)
    if progress:
        result["build_progress"] = progress

    # Failure analysis
    if not result["ok"]:
        build_system = cmd[0] if cmd else ""
        tool_name = step.get("tool", step.get("label", "unknown"))
        analysis = _analyse_build_failure(
            tool_name, result.get("stderr", ""), build_system,
        )
        if analysis:
            result["build_failure_analysis"] = analysis

    return result
