"""
L0 — Detection layer (instant).

System profile, available tools, project module inventory.
No computation — just checks what exists on disk and in PATH.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
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


def _detect_os() -> dict:
    """Detect operating system details."""
    info: dict[str, str | bool] = {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
    }
    # Detect WSL
    try:
        with open("/proc/version", encoding="utf-8") as f:
            version_str = f.read().lower()
            info["wsl"] = "microsoft" in version_str or "wsl" in version_str
    except (FileNotFoundError, OSError):
        info["wsl"] = False

    # Detect distro on Linux
    if platform.system() == "Linux":
        try:
            import distro  # type: ignore[import-untyped]
            info["distro"] = distro.name(pretty=True)
        except ImportError:
            # Fallback: parse /etc/os-release
            try:
                with open("/etc/os-release", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("PRETTY_NAME="):
                            info["distro"] = line.split("=", 1)[1].strip().strip('"')
                            break
            except (FileNotFoundError, OSError):
                info["distro"] = "Linux (unknown)"

    return info


def _detect_python() -> dict:
    """Detect Python runtime details."""
    return {
        "version": platform.python_version(),
        "implementation": platform.python_implementation(),
        "executable": sys.executable,
        "prefix": sys.prefix,
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


# ── Public API ──────────────────────────────────────────────────

# Public aliases for the canonical tool registry
TOOL_REGISTRY = _TOOLS
detect_tools = _detect_tools


def l0_system_profile(project_root: Path) -> dict:
    """L0: Full system profile — OS, runtime, tools, modules, manifests.

    This is designed to be fast (< 200ms) and is auto-loaded.
    """
    import time

    from src.core.services.audit.models import wrap_result

    started = time.time()
    data = {
        "os": _detect_os(),
        "python": _detect_python(),
        "venv": _detect_venv(project_root),
        "tools": _detect_tools(),
        "modules": _detect_modules(project_root),
        "manifests": _detect_manifests(project_root),
        "project_root": str(project_root),
    }
    return wrap_result(data, "L0", "system", started)
