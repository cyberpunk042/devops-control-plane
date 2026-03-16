"""
Virtual environment detection and installed package resolution.

Detects all Python venvs in the project, identifies which one is
active, and queries installed packages per venv.

Usage::

    info = detect_venvs(project_root)
    # info = {
    #     "active": ".venv-ft",
    #     "active_python": "3.14.3",
    #     "venvs": [
    #         {"path": ".venv-ft", "python": "3.14.3", "active": True, "free_threaded": True},
    #         {"path": ".venv", "python": "3.12.8", "active": False, "free_threaded": False},
    #     ],
    # }

    installed = get_installed_packages(project_root, venv_path=".venv-ft")
    # installed = {"flask": "3.0.3", "click": "8.1.7", ...}
"""

from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Venv directory names to scan (in priority order)
_VENV_DIRS = [".venv-ft", ".venv", "venv", ".env", "env"]


def detect_venvs(project_root: Path) -> dict[str, Any]:
    """Detect all Python virtual environments in the project.

    Scans known venv directory names, detects Python version in each,
    identifies which one (if any) the current process is running in.

    Returns:
        Dict with ``active``, ``active_python``, ``active_free_threaded``,
        and ``venvs`` list.
    """
    venvs: list[dict[str, Any]] = []

    for name in _VENV_DIRS:
        venv_dir = project_root / name
        python_bin = venv_dir / "bin" / "python"
        if not python_bin.exists():
            continue

        # Get Python version from this venv
        py_version = _get_python_version(python_bin)
        free_threaded = "t" in name or _is_free_threaded(python_bin)

        # Is this venv active? (is sys.executable inside it?)
        active = _is_active_venv(venv_dir)

        venvs.append({
            "path": name,
            "abs_path": str(venv_dir),
            "python": py_version,
            "python_bin": str(python_bin),
            "active": active,
            "free_threaded": free_threaded,
        })

    # Current process info
    active_name = ""
    active_python = platform.python_version()
    active_ft = hasattr(sys, "_is_gil_enabled") or "t" in getattr(sys, "abiflags", "")

    for v in venvs:
        if v["active"]:
            active_name = v["path"]
            break

    # System Python — find the real system binary, not the venv's
    system_python_bin = _find_system_python()
    system_version = _get_python_version(Path(system_python_bin)) if system_python_bin else "unknown"
    system_pep668 = _check_pep668_for(system_python_bin) if system_python_bin else False

    # System target risk assessment — ALWAYS risky to some degree:
    # - PEP 668 = hard lock (modern Ubuntu/Debian/Fedora)
    # - Venvs exist = medium risk (you HAVE better options)
    # - No venvs = still risky (system Python is shared with OS)
    has_venvs = len(venvs) > 0
    system_risky = True  # System Python is ALWAYS risky for project deps

    if system_pep668:
        system_risk_reason = "pep668"
        system_risk_detail = "This system's Python is EXTERNALLY-MANAGED (PEP 668). Installing packages globally will require --break-system-packages and may break system tools."
        system_risk_severity = "high"
    elif has_venvs:
        system_risk_reason = "venvs_available"
        system_risk_detail = "Virtual environments are available. Installing into system Python is not recommended — it can conflict with OS packages and break system tools. Use a venv instead."
        system_risk_severity = "medium"
    else:
        system_risk_reason = "no_isolation"
        system_risk_detail = "No virtual environment found. Installing into system Python can conflict with OS packages. Create a venv first: python3 -m venv .venv"
        system_risk_severity = "medium"

    system_target = {
        "path": "system",
        "abs_path": "",
        "python": system_version,
        "python_bin": system_python_bin or "",
        "active": not active_name,
        "free_threaded": False,
        "pep668": system_pep668,
        "is_system": True,
        "risky": system_risky,
        "risk_reason": system_risk_reason,
        "risk_detail": system_risk_detail,
        "risk_severity": system_risk_severity,
    }

    return {
        "active": active_name or "system",
        "active_python": active_python,
        "active_free_threaded": active_ft,
        "system_python": system_python_bin or sys.executable,
        "system_pep668": system_pep668,
        "venvs": venvs,
        "system": system_target,
        "targets": venvs + [system_target],
    }


def get_installed_packages(
    project_root: Path,
    venv_path: str | None = None,
) -> dict[str, str]:
    """Get installed packages from a venv (or current environment).

    Args:
        project_root: Project root directory.
        venv_path: Venv directory name (e.g. ``.venv-ft``).
            ``None`` = use current ``sys.executable``.

    Returns:
        Dict mapping package name (lowercase) → installed version.
        Empty dict on failure.
    """
    if venv_path == "system":
        # Use the actual system Python, not the venv
        python_bin = _find_system_python() or sys.executable
    elif venv_path:
        python_bin = str(project_root / venv_path / "bin" / "python")
    else:
        python_bin = sys.executable

    try:
        # Try pip list --format json
        result = subprocess.run(
            [python_bin, "-m", "pip", "list", "--format", "json"],
            capture_output=True, text=True, timeout=15,
            cwd=str(project_root),
        )
        if result.returncode == 0 and result.stdout.strip():
            packages = json.loads(result.stdout)
            return {
                p.get("name", "").lower(): p.get("version", "")
                for p in packages
                if p.get("name")
            }
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        pass

    # Fallback: try uv pip list (for free-threaded envs without pip)
    try:
        env = os.environ.copy()
        # Determine the VIRTUAL_ENV for uv
        if venv_path and venv_path != "system":
            env["VIRTUAL_ENV"] = str(project_root / venv_path)
        elif not venv_path:
            # No explicit venv — detect from sys.prefix if we're inside a venv
            prefix = Path(sys.prefix)
            if prefix != Path(sys.base_prefix):
                env["VIRTUAL_ENV"] = str(prefix)
            # Also check if VIRTUAL_ENV is already set in the environment
            elif "VIRTUAL_ENV" not in env:
                # Try to derive from python_bin path
                bin_dir = Path(python_bin).parent
                venv_dir = bin_dir.parent
                if (venv_dir / "pyvenv.cfg").is_file():
                    env["VIRTUAL_ENV"] = str(venv_dir)

        result = subprocess.run(
            ["uv", "pip", "list", "--format", "json"],
            capture_output=True, text=True, timeout=15,
            cwd=str(project_root), env=env,
        )
        if result.returncode == 0 and result.stdout.strip():
            packages = json.loads(result.stdout)
            return {
                p.get("name", "").lower(): p.get("version", "")
                for p in packages
                if p.get("name")
            }
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError, FileNotFoundError):
        pass

    return {}


def _get_python_version(python_bin: Path) -> str:
    """Get Python version string from a binary."""
    try:
        result = subprocess.run(
            [str(python_bin), "--version"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            # "Python 3.14.3" → "3.14.3"
            parts = result.stdout.strip().split()
            return parts[1] if len(parts) >= 2 else parts[0]
    except (subprocess.TimeoutExpired, OSError):
        pass
    return "unknown"


def _is_active_venv(venv_dir: Path) -> bool:
    """Check if the current process is running inside this venv."""
    try:
        venv_resolved = str(venv_dir.resolve())
        exe_resolved = str(Path(sys.executable).resolve())
        prefix_resolved = str(Path(sys.prefix).resolve())
        return (
            exe_resolved.startswith(venv_resolved)
            or prefix_resolved.startswith(venv_resolved)
        )
    except Exception:
        return False


def check_venv_health(project_root: Path) -> None:
    """Check venv health and create notifications if needed.

    Triggers:
    - No venvs exist but project has Python deps → "Create a virtual environment"
    - Venvs exist but none is active → "Activate a virtual environment"

    Notifications are deduped — only created once until dismissed.
    Fail-safe: never raises.
    """
    try:
        info = detect_venvs(project_root)
        venvs = info.get("venvs", [])
        active = info.get("active", "")
        has_python_deps = _project_has_python_deps(project_root)

        if not has_python_deps:
            return  # No Python deps — venv isn't relevant

        from src.core.services.notifications import create_notification

        if not venvs:
            # No venvs at all — project needs one
            system_info = info.get("system", {})
            is_pep668 = system_info.get("pep668", False)
            system_ver = system_info.get("python", "unknown")

            create_notification(
                project_root,
                notif_type="no_python_venv",
                title="No Python virtual environment",
                message="This project has Python dependencies but no virtual environment.",
                meta={
                    "action": "open_venv_modal",
                    "severity": "high" if is_pep668 else "medium",
                    "variant": "no_venv",
                    "pep668": is_pep668,
                    "system_python": system_ver,
                    "explanation": (
                        "Virtual environments isolate your project's dependencies from the system Python. "
                        "Without one, installing packages can conflict with OS-managed packages and break system tools."
                        + (" This system uses PEP 668 (EXTERNALLY-MANAGED) — pip will refuse to install without --break-system-packages." if is_pep668 else "")
                    ),
                    "options": [
                        {
                            "label": "Create standard venv (.venv)",
                            "description": f"Python {system_ver} virtual environment in .venv/",
                            "commands": ["python3 -m venv .venv", ".venv/bin/pip install -e '.[dev]'"],
                            "recommended": True,
                        },
                        {
                            "label": "Create free-threaded venv (.venv-ft)",
                            "description": "Python 3.14+ no-GIL build via uv",
                            "commands": ["uv venv --clear -p 3.14t .venv-ft", "uv pip install -e '.[dev]' --python .venv-ft/bin/python"],
                            "recommended": False,
                            "requires": ["uv"],
                        },
                    ],
                },
            )

        else:
            # Venvs exist — auto-dismiss "no venv" notification if it was active
            from src.core.services.notifications import dismiss_notification_by_type
            try:
                dismiss_notification_by_type(project_root, "no_python_venv")
            except Exception:
                pass

        if active == "system" and venvs:
            # Venvs exist but none is active — server running on system Python
            venv_options = []
            for v in venvs:
                ft_label = " (free-threaded)" if v.get("free_threaded") else ""
                venv_options.append({
                    "label": f"Activate {v['path']}",
                    "description": f"Python {v['python']}{ft_label}",
                    "commands": [f"source {v['path']}/bin/activate", "controlplane serve"],
                })

            create_notification(
                project_root,
                notif_type="venv_not_active",
                title="Virtual environment not active",
                message="The server is running on system Python instead of a virtual environment.",
                meta={
                    "action": "open_venv_modal",
                    "severity": "medium",
                    "variant": "not_active",
                    "explanation": (
                        "Virtual environments exist but the server process is using system Python. "
                        "Dependencies installed via the platform will go into the system, not your project's venv. "
                        "Stop the server and restart it from inside a virtual environment."
                    ),
                    "options": venv_options,
                },
            )

    except Exception:
        logger.debug("check_venv_health failed", exc_info=True)


def _project_has_python_deps(project_root: Path) -> bool:
    """Quick check: does the project have any Python dependency manifest?"""
    for name in ("requirements.txt", "pyproject.toml", "Pipfile", "setup.py", "setup.cfg"):
        if (project_root / name).is_file():
            return True
    return False


def _find_system_python() -> str | None:
    """Find the system Python binary (not a venv Python).

    Looks for python3 / python in standard system locations,
    skipping any that resolve to a venv.
    """
    import shutil

    # Check common system locations first
    for candidate in ("/usr/bin/python3", "/usr/bin/python", "/usr/local/bin/python3"):
        if os.path.isfile(candidate):
            # Verify it's not a symlink into a venv
            try:
                resolved = os.path.realpath(candidate)
                if "/.venv" not in resolved and "/venv/" not in resolved:
                    return candidate
            except Exception:
                return candidate

    # Fallback: shutil.which, but verify it's not a venv binary
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found:
            try:
                resolved = os.path.realpath(found)
                if "/.venv" not in resolved and "/venv/" not in resolved:
                    return found
            except Exception:
                return found

    return None


def _check_pep668_for(python_bin: str | None) -> bool:
    """Check PEP 668 EXTERNALLY-MANAGED marker for a specific Python binary."""
    if not python_bin:
        return False
    try:
        # Get the Python's version to find the stdlib dir
        result = subprocess.run(
            [python_bin, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return False
        ver = result.stdout.strip()
        # Get the base prefix
        result2 = subprocess.run(
            [python_bin, "-c", "import sys; print(sys.base_prefix)"],
            capture_output=True, text=True, timeout=5,
        )
        base_prefix = result2.stdout.strip() if result2.returncode == 0 else ""
        # Check for marker
        for stdlib_dir in (
            os.path.join(base_prefix, "lib", f"python{ver}") if base_prefix else "",
            f"/usr/lib/python{ver}",
        ):
            if stdlib_dir:
                marker = os.path.join(stdlib_dir, "EXTERNALLY-MANAGED")
                if os.path.isfile(marker):
                    return True
    except (subprocess.TimeoutExpired, OSError):
        pass
    return False


def _check_pep668() -> bool:
    """Check if the system Python has the EXTERNALLY-MANAGED marker (PEP 668).

    Modern Ubuntu/Debian/Fedora mark system Python to prevent global pip installs.
    """
    for stdlib_dir in (
        os.path.join(sys.base_prefix, "lib",
                     f"python{sys.version_info.major}.{sys.version_info.minor}"),
        f"/usr/lib/python{sys.version_info.major}.{sys.version_info.minor}",
    ):
        marker = os.path.join(stdlib_dir, "EXTERNALLY-MANAGED")
        if os.path.isfile(marker):
            return True
    return False


def _is_free_threaded(python_bin: Path) -> bool:
    """Check if a Python binary is free-threaded (no GIL)."""
    try:
        result = subprocess.run(
            [str(python_bin), "-c", "import sys; print(hasattr(sys, '_is_gil_enabled'))"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0 and "True" in result.stdout
    except (subprocess.TimeoutExpired, OSError):
        return False
