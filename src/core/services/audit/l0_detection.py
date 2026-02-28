"""
L0 — Detection layer (instant).

System profile, available tools, project module inventory.
No computation — just checks what exists on disk and in PATH.
"""

from __future__ import annotations

import logging
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# ── System tools to probe ───────────────────────────────────────

_TOOLS: list[dict[str, str]] = [
    # ── Core runtimes ───────────────────────────────────────────
    {"id": "python",         "cli": "python3",         "label": "Python",          "category": "runtime",   "install_type": "sudo"},
    {"id": "pip",            "cli": "pip",              "label": "pip",             "category": "runtime",   "install_type": "sudo"},
    {"id": "node",           "cli": "node",             "label": "Node.js",         "category": "runtime",   "install_type": "sudo"},
    {"id": "npm",            "cli": "npm",              "label": "npm",             "category": "runtime",   "install_type": "sudo"},
    {"id": "npx",            "cli": "npx",              "label": "npx",             "category": "runtime",   "install_type": "sudo"},
    {"id": "go",             "cli": "go",               "label": "Go",              "category": "runtime",   "install_type": "sudo"},
    {"id": "cargo",          "cli": "cargo",            "label": "Cargo (Rust)",    "category": "runtime",   "install_type": "sudo"},
    {"id": "rustc",          "cli": "rustc",            "label": "Rust compiler",   "category": "runtime",   "install_type": "sudo"},
    # ── Version control ────────────────────────────────────────
    {"id": "git",            "cli": "git",              "label": "Git",             "category": "vcs",       "install_type": "sudo"},
    {"id": "gh",             "cli": "gh",               "label": "GitHub CLI",      "category": "vcs",       "install_type": "sudo"},
    # ── Containers & orchestration ─────────────────────────────
    {"id": "docker",         "cli": "docker",           "label": "Docker",          "category": "container", "install_type": "sudo"},
    {"id": "docker-compose", "cli": "docker-compose",   "label": "Docker Compose",  "category": "container", "install_type": "sudo"},
    {"id": "kubectl",        "cli": "kubectl",          "label": "kubectl",         "category": "container", "install_type": "sudo"},
    {"id": "helm",           "cli": "helm",             "label": "Helm",            "category": "container", "install_type": "sudo"},
    {"id": "skaffold",       "cli": "skaffold",         "label": "Skaffold",        "category": "container", "install_type": "sudo"},
    # ── Infrastructure ─────────────────────────────────────────
    {"id": "terraform",      "cli": "terraform",        "label": "Terraform",       "category": "infra",     "install_type": "sudo"},
    {"id": "trivy",          "cli": "trivy",            "label": "Trivy",           "category": "security",  "install_type": "sudo"},
    # ── Quality & testing ──────────────────────────────────────
    {"id": "ruff",           "cli": "ruff",             "label": "Ruff",            "category": "quality",   "install_type": "pip"},
    {"id": "mypy",           "cli": "mypy",             "label": "mypy",            "category": "quality",   "install_type": "pip"},
    {"id": "pytest",         "cli": "pytest",           "label": "pytest",          "category": "quality",   "install_type": "pip"},
    {"id": "black",          "cli": "black",            "label": "Black",           "category": "quality",   "install_type": "pip"},
    {"id": "eslint",         "cli": "eslint",           "label": "ESLint",          "category": "quality",   "install_type": "npm"},
    {"id": "prettier",       "cli": "prettier",         "label": "Prettier",        "category": "quality",   "install_type": "npm"},
    # ── Security auditing ──────────────────────────────────────
    {"id": "pip-audit",      "cli": "pip-audit",        "label": "pip-audit",       "category": "security",  "install_type": "pip"},
    {"id": "bandit",         "cli": "bandit",           "label": "Bandit",          "category": "security",  "install_type": "pip"},
    {"id": "safety",         "cli": "safety",           "label": "Safety",          "category": "security",  "install_type": "pip"},
    {"id": "cargo-outdated", "cli": "cargo-outdated",   "label": "cargo-outdated",  "category": "security",  "install_type": "cargo"},
    {"id": "cargo-audit",    "cli": "cargo-audit",      "label": "cargo-audit",     "category": "security",  "install_type": "cargo"},
    # ── Network & DNS ──────────────────────────────────────────
    {"id": "dig",            "cli": "dig",              "label": "dig",             "category": "network",   "install_type": "sudo"},
    {"id": "openssl",        "cli": "openssl",          "label": "OpenSSL",         "category": "network",   "install_type": "sudo"},
    {"id": "curl",           "cli": "curl",             "label": "curl",            "category": "network",   "install_type": "sudo"},
    # ── System utilities ───────────────────────────────────────
    {"id": "ffmpeg",         "cli": "ffmpeg",           "label": "FFmpeg",          "category": "system",    "install_type": "sudo"},
    {"id": "gzip",           "cli": "gzip",             "label": "gzip",            "category": "system",    "install_type": "sudo"},
    {"id": "jq",             "cli": "jq",               "label": "jq",              "category": "system",    "install_type": "sudo"},
    {"id": "make",           "cli": "make",             "label": "Make",            "category": "system",    "install_type": "sudo"},
    {"id": "rsync",          "cli": "rsync",            "label": "rsync",           "category": "system",    "install_type": "sudo"},
]

from src.core.services.audit.l0_os_detection import _detect_os  # noqa: E402




def _detect_python() -> dict:
    """Detect Python runtime details and environment context.

    Returns:
        version: str — Python version (e.g. "3.12.1")
        version_tuple: list[int] — [3, 12, 1]
        implementation: str — "CPython", "PyPy", etc.
        executable: str — path to python binary
        prefix: str — sys.prefix
        base_prefix: str — sys.base_prefix

        env_type: str — "system" | "venv" | "conda" | "uv" | "pyenv" | "virtualenv"
        in_managed_env: bool — True if running in any managed environment
        pep668: bool — True if system Python has EXTERNALLY-MANAGED marker

        env_managers: dict — available Python environment managers:
            uv: bool — uv binary found
            conda: bool — conda binary found
            pyenv: bool — pyenv binary found
            virtualenv: bool — virtualenv binary found
            pipx: bool — pipx binary found

        system_python_warning: bool — True when operating on bare system Python
    """
    version = platform.python_version()
    version_parts = []
    for p in version.split("."):
        try:
            version_parts.append(int(p))
        except ValueError:
            break

    # ── Environment type detection ────────────────────────────
    # Priority: conda > uv > pyenv > venv > virtualenv > system
    env_type = "system"
    in_managed_env = False

    # Check conda first (CONDA_DEFAULT_ENV or CONDA_PREFIX)
    conda_prefix = os.environ.get("CONDA_PREFIX", "")
    conda_env = os.environ.get("CONDA_DEFAULT_ENV", "")
    if conda_prefix or conda_env:
        env_type = "conda"
        in_managed_env = True
    # Check uv (UV_VIRTUAL_ENV or .uv marker in prefix)
    elif os.environ.get("UV_VIRTUAL_ENV", ""):
        env_type = "uv"
        in_managed_env = True
    # Check pyenv (PYENV_ROOT set and prefix inside it)
    elif os.environ.get("PYENV_ROOT", "") and (
        os.environ["PYENV_ROOT"] in sys.prefix
    ):
        env_type = "pyenv"
        in_managed_env = True
    # Check standard venv (sys.prefix != sys.base_prefix)
    elif sys.prefix != sys.base_prefix:
        # Could be venv or virtualenv — check for pyvenv.cfg
        pyvenv_cfg = os.path.join(sys.prefix, "pyvenv.cfg")
        if os.path.isfile(pyvenv_cfg):
            env_type = "venv"
        else:
            env_type = "virtualenv"
        in_managed_env = True

    # ── PEP 668 detection ─────────────────────────────────────
    # Check if the system Python has the EXTERNALLY-MANAGED marker
    pep668 = False
    if not in_managed_env:
        # Check in the stdlib path for the marker file
        for stdlib_dir in (
            os.path.join(sys.base_prefix, "lib",
                         f"python{sys.version_info.major}.{sys.version_info.minor}"),
            f"/usr/lib/python{sys.version_info.major}.{sys.version_info.minor}",
            f"/usr/lib/python{sys.version_info.major}",
        ):
            marker = os.path.join(stdlib_dir, "EXTERNALLY-MANAGED")
            if os.path.isfile(marker):
                pep668 = True
                break

    # ── Available environment managers ─────────────────────────
    env_managers = {
        "uv": shutil.which("uv") is not None,
        "conda": shutil.which("conda") is not None,
        "pyenv": shutil.which("pyenv") is not None,
        "virtualenv": shutil.which("virtualenv") is not None,
        "pipx": shutil.which("pipx") is not None,
    }

    # ── System Python warning ─────────────────────────────────
    # True when running on bare system Python (no env, not root container)
    system_python_warning = (
        not in_managed_env
        and env_type == "system"
    )

    return {
        "version": version,
        "version_tuple": version_parts,
        "implementation": platform.python_implementation(),
        "executable": sys.executable,
        "prefix": sys.prefix,
        "base_prefix": sys.base_prefix,
        "env_type": env_type,
        "in_managed_env": in_managed_env,
        "pep668": pep668,
        "env_managers": env_managers,
        "system_python_warning": system_python_warning,
    }


def _detect_venv(project_root: Path) -> dict:
    """Detect virtual environment status."""
    # Check if we're currently in a venv
    in_venv = sys.prefix != sys.base_prefix

    # Find venv directories
    venv_dirs = [".venv", "venv", ".env", "env"]
    found: list[dict] = []
    for name in venv_dirs:
        p = project_root / name
        if p.is_dir() and (p / "bin" / "python").exists():
            found.append({
                "path": name,
                "python": str(p / "bin" / "python"),
                "active": str(p.resolve()) in sys.prefix,
            })

    return {
        "in_venv": in_venv,
        "venvs": found,
        "active_prefix": sys.prefix if in_venv else None,
    }


def _detect_tools() -> list[dict]:
    """Check availability of system tools.

    Returns each tool with:
        id, cli, label, category, install_type, available, path

    Handles the common case where the web server runs inside a venv
    but `.venv/bin` is NOT on PATH — falls back to checking the venv
    bin directory directly.
    """
    # Pre-compute venv bin path for fallback lookups
    venv_bin: str | None = None
    if sys.prefix != sys.base_prefix:
        venv_bin = os.path.join(sys.prefix, "bin")

    results = []
    for tool in _TOOLS:
        cli_name = tool["cli"]

        # 1. Standard PATH lookup
        path = shutil.which(cli_name)

        # 2. Venv bin fallback (covers pip-installed tools not on PATH)
        if path is None and venv_bin:
            candidate = os.path.join(venv_bin, cli_name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                path = candidate

        # 3. Special case: pip via python -m pip
        if path is None and tool["id"] == "pip":
            import subprocess
            try:
                r = subprocess.run(
                    [sys.executable, "-m", "pip", "--version"],
                    capture_output=True, timeout=5,
                )
                if r.returncode == 0:
                    path = f"{sys.executable} -m pip"
            except Exception:
                pass

        results.append({
            "id": tool["id"],
            "cli": cli_name,
            "label": tool["label"],
            "category": tool.get("category", "other"),
            "install_type": tool.get("install_type", "none"),
            "available": path is not None,
            "path": path,
        })
    return results


def _detect_modules(project_root: Path) -> list[dict]:
    """Detect project modules from project.yml."""
    try:
        from src.core.config.loader import load_project
        from src.core.config.stack_loader import discover_stacks
        from src.core.services.detection import detect_modules

        project = load_project(project_root / "project.yml")
        stacks = discover_stacks(project_root / "stacks")
        detection = detect_modules(project, project_root, stacks)

        modules = []
        for m in detection.modules:
            mod_path = project_root / m.path
            # Count source files
            file_count = 0
            if mod_path.is_dir():
                for f in mod_path.rglob("*"):
                    if f.is_file() and not any(
                        p in f.parts for p in (
                            "__pycache__", "node_modules", ".git",
                            ".venv", "venv", "dist", "build",
                        )
                    ):
                        file_count += 1

            modules.append({
                "name": m.name,
                "path": m.path,
                "domain": m.domain,
                "stack": m.effective_stack,
                "language": m.language,
                "version": m.version,
                "detected": m.detected,
                "description": m.description,
                "file_count": file_count,
            })
        return modules
    except Exception as e:
        logger.warning("Module detection failed: %s", e)
        return []


def _detect_manifests(project_root: Path) -> list[dict]:
    """Detect dependency manifest files."""
    manifests = [
        ("pyproject.toml", "python", "pip/poetry/flit"),
        ("requirements.txt", "python", "pip"),
        ("requirements-dev.txt", "python", "pip (dev)"),
        ("setup.py", "python", "setuptools"),
        ("setup.cfg", "python", "setuptools"),
        ("Pipfile", "python", "pipenv"),
        ("poetry.lock", "python", "poetry"),
        ("package.json", "node", "npm/yarn"),
        ("package-lock.json", "node", "npm"),
        ("yarn.lock", "node", "yarn"),
        ("pnpm-lock.yaml", "node", "pnpm"),
        ("go.mod", "go", "go mod"),
        ("go.sum", "go", "go mod"),
        ("Cargo.toml", "rust", "cargo"),
        ("Cargo.lock", "rust", "cargo"),
        ("Gemfile", "ruby", "bundler"),
        ("Gemfile.lock", "ruby", "bundler"),
        ("mix.exs", "elixir", "mix"),
        ("mix.lock", "elixir", "mix"),
    ]

    found = []
    for filename, ecosystem, manager in manifests:
        p = project_root / filename
        if p.is_file():
            found.append({
                "file": filename,
                "ecosystem": ecosystem,
                "manager": manager,
                "size": p.stat().st_size,
            })
    return found


# ── Deep tier detection ─────────────────────────────────────────
#
# These detections are MORE expensive than fast tier (may take up
# to ~2s). They run ON DEMAND when the install modal is opened or
# when the resolver needs data for complex recipes.
#
# Each sub-detection is isolated so _detect_deep_profile() can be
# called selectively via the `needs` parameter.
#
# Implementations live in l0_deep_detectors.py (split for size).
# Cache: module-level dict with TTL (5 min). Different from the
# devops_cache used for audit cards — this is for deep-tier data
# that doesn't correspond to file changes.

import time as _time  # separate alias; `time` is imported locally in l0_system_profile

_deep_cache: dict[str, object] = {}  # {"data": {...}, "ts": float}
_DEEP_CACHE_TTL = 300  # 5 minutes

from src.core.services.audit.l0_deep_detectors import (  # noqa: E402
    DEEP_DETECTORS as _DEEP_DETECTORS,
)


def _detect_deep_profile(
    needs: list[str] | None = None,
) -> dict:
    """Run deep-tier detection, optionally selective.

    Args:
        needs: List of category names to detect. If None, detect all.
               Valid names (by phase):
                 Phase 4: "shell", "init_system", "network"
                 Phase 5: "build"
                 Phase 6: "gpu", "kernel", "wsl_interop"
                 Phase 8: "services", "filesystem", "security"

    Returns:
        Dict with one key per detected category. When the cache is
        warm, this may include MORE categories than were requested
        (the full cached dict is returned as a superset). Consumers
        must handle both missing AND extra keys gracefully.

    Cache:
        Results are cached module-level with a 5-minute TTL.
        Selective requests detect only uncached categories and merge
        them into the existing cache dict.
    """
    global _deep_cache

    now = _time.time()
    cached_ts = _deep_cache.get("ts", 0)
    cached_data: dict = _deep_cache.get("data", {})

    # Determine which categories to run
    if needs is None:
        categories = list(_DEEP_DETECTORS.keys())
    else:
        categories = [n for n in needs if n in _DEEP_DETECTORS]

    # Filter out categories already in cache if cache is fresh
    if (now - cached_ts) < _DEEP_CACHE_TTL:
        categories = [c for c in categories if c not in cached_data]
        if not categories:
            logger.debug("deep tier: all %d categories cached", len(needs or _DEEP_DETECTORS))
            return dict(cached_data)

    # Run needed detections
    result = dict(cached_data)
    for cat in categories:
        detector = _DEEP_DETECTORS[cat]
        try:
            result[cat] = detector()
            logger.debug("deep tier: detected '%s'", cat)
        except Exception:
            logger.exception("deep tier: failed to detect '%s'", cat)
            result[cat] = {"error": f"detection failed for {cat}"}

    # Update cache
    _deep_cache = {"data": result, "ts": now}

    return result


# ── Public API ──────────────────────────────────────────────────

# Public aliases for the canonical tool registry
TOOL_REGISTRY = _TOOLS
detect_tools = _detect_tools


def l0_system_profile(project_root: Path, *, deep: bool = False) -> dict:
    """L0: Full system profile — OS, runtime, tools, modules, manifests.

    Fast tier (< 200ms): always runs.
    Deep tier (< 5s): runs when deep=True. Adds 10 categories to the
    OS profile dict: shell, init_system, network, build, gpu, kernel,
    wsl_interop, services, filesystem, security. Cached with 5-min TTL.
    """
    import time

    from src.core.services.audit.models import wrap_result

    started = time.time()
    os_data = _detect_os()

    # ── Deep tier merge ───────────────────────────────────────
    if deep:
        deep_data = _detect_deep_profile()
        for key, value in deep_data.items():
            os_data[key] = value

    data = {
        "os": os_data,
        "python": _detect_python(),
        "venv": _detect_venv(project_root),
        "tools": _detect_tools(),
        "modules": _detect_modules(project_root),
        "manifests": _detect_manifests(project_root),
        "project_root": str(project_root),
        "deep_tier": deep,
    }
    return wrap_result(data, "L0", "system", started)
