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


# ── Architecture normalization ──────────────────────────────────

_ARCH_MAP: dict[str, str] = {
    "x86_64": "amd64", "amd64": "amd64",
    "aarch64": "arm64", "arm64": "arm64",
    "armv7l": "armv7",
}

# ── Distro family mapping ──────────────────────────────────────

_FAMILY_MAP: dict[str, str] = {
    # Debian family
    "ubuntu": "debian", "debian": "debian", "linuxmint": "debian",
    "pop": "debian", "elementary": "debian", "zorin": "debian",
    "kali": "debian", "raspbian": "debian", "deepin": "debian",
    # RHEL family
    "fedora": "rhel", "centos": "rhel", "rhel": "rhel",
    "rocky": "rhel", "almalinux": "rhel", "oracle": "rhel",
    "amzn": "rhel",
    # Alpine
    "alpine": "alpine",
    # Arch family
    "arch": "arch", "manjaro": "arch", "endeavouros": "arch",
    # SUSE family
    "opensuse-leap": "suse", "opensuse-tumbleweed": "suse", "sles": "suse",
}


def _parse_os_release() -> dict[str, str]:
    """Parse /etc/os-release into a dict of key=value pairs."""
    data: dict[str, str] = {}
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line:
                    key, val = line.split("=", 1)
                    data[key] = val.strip('"')
    except (FileNotFoundError, OSError):
        pass
    return data


def _get_distro_family(distro_id: str, id_like: str) -> str:
    """Determine distro family from ID and ID_LIKE fields."""
    if distro_id in _FAMILY_MAP:
        return _FAMILY_MAP[distro_id]
    for parent in id_like.split():
        if parent in _FAMILY_MAP:
            return _FAMILY_MAP[parent]
    return "unknown"


def _parse_version_tuple(version_str: str) -> list[int]:
    """Parse '20.04' → [20, 4], '39' → [39]."""
    parts: list[int] = []
    for p in version_str.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            break
    return parts


def _detect_container() -> dict:
    """Detect if running inside a container (Docker, K8s, podman)."""
    result: dict[str, object] = {
        "in_container": False,
        "runtime": None,
        "in_k8s": False,
    }

    # Method 1: /.dockerenv file
    if os.path.isfile("/.dockerenv"):
        result["in_container"] = True
        result["runtime"] = "docker"

    # Method 2: /proc/1/cgroup contains docker/kubepods/containerd
    try:
        with open("/proc/1/cgroup", encoding="utf-8") as f:
            cgroup = f.read().lower()
            if "docker" in cgroup:
                result["in_container"] = True
                result["runtime"] = result["runtime"] or "docker"
            elif "kubepods" in cgroup:
                result["in_container"] = True
                result["runtime"] = "containerd"
                result["in_k8s"] = True
            elif "containerd" in cgroup:
                result["in_container"] = True
                result["runtime"] = "containerd"
    except (FileNotFoundError, OSError, PermissionError):
        pass

    # Method 3: /proc/1/environ contains container=
    try:
        with open("/proc/1/environ", encoding="utf-8", errors="replace") as f:
            env = f.read()
            if "container=" in env:
                result["in_container"] = True
    except (FileNotFoundError, OSError, PermissionError):
        pass

    # Method 4: KUBERNETES_SERVICE_HOST env var
    if os.environ.get("KUBERNETES_SERVICE_HOST"):
        result["in_k8s"] = True
        result["in_container"] = True

    # ── Read-only filesystem detection ──
    result["read_only_rootfs"] = False
    if result["in_container"]:
        try:
            probe = "/tmp/.dcp_ro_probe"
            with open(probe, "w") as f:
                f.write("probe")
            os.unlink(probe)
        except (OSError, PermissionError):
            result["read_only_rootfs"] = True

    # ── K8s ephemeral install warning ──
    if result["in_k8s"]:
        result["ephemeral_warning"] = (
            "Running in a Kubernetes pod. Installed tools will be lost "
            "when the pod restarts. Consider building a custom image instead."
        )

    return result


def _detect_capabilities() -> dict:
    """Detect system capabilities: systemd, sudo, root."""
    result: dict[str, object] = {
        "has_systemd": False,
        "systemd_state": None,
        "has_sudo": shutil.which("sudo") is not None,
        "passwordless_sudo": False,
        "is_root": os.getuid() == 0 if hasattr(os, "getuid") else False,
    }

    # systemd detection
    if shutil.which("systemctl"):
        try:
            r = subprocess.run(
                ["systemctl", "is-system-running"],
                capture_output=True, text=True, timeout=5,
            )
            state = r.stdout.strip()
            result["systemd_state"] = state
            result["has_systemd"] = state in ("running", "degraded")
        except (subprocess.TimeoutExpired, OSError):
            pass

    # Passwordless sudo
    if result["has_sudo"] and not result["is_root"]:
        try:
            r = subprocess.run(
                ["sudo", "-n", "true"],
                capture_output=True, timeout=5,
            )
            result["passwordless_sudo"] = r.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            pass

    return result


def _detect_package_managers(has_systemd: bool) -> dict:
    """Detect available package managers and pick the primary one."""
    _PM_BINARIES = [
        ("apt", "apt-get"),
        ("dnf", "dnf"),
        ("yum", "yum"),
        ("apk", "apk"),
        ("pacman", "pacman"),
        ("zypper", "zypper"),
        ("brew", "brew"),
    ]

    available: list[str] = []
    primary: str | None = None
    for pm_id, binary in _PM_BINARIES:
        if shutil.which(binary):
            available.append(pm_id)
            if primary is None:
                primary = pm_id

    snap_available = shutil.which("snap") is not None and has_systemd

    return {
        "primary": primary or "none",
        "available": available,
        "snap_available": snap_available,
    }


def _detect_libraries() -> dict:
    """Detect library versions: OpenSSL, glibc/musl."""
    result: dict[str, str | None] = {
        "openssl_version": None,
        "glibc_version": None,
        "libc_type": "unknown",
    }

    # OpenSSL version
    if shutil.which("openssl"):
        try:
            r = subprocess.run(
                ["openssl", "version"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                parts = r.stdout.strip().split()
                if len(parts) >= 2:
                    result["openssl_version"] = parts[1]
        except (subprocess.TimeoutExpired, OSError):
            pass

    # glibc version via ctypes
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6")
        libc.gnu_get_libc_version.restype = ctypes.c_char_p
        result["glibc_version"] = libc.gnu_get_libc_version().decode()
        result["libc_type"] = "glibc"
    except (OSError, AttributeError):
        # Might be musl — check via ldd
        try:
            r = subprocess.run(
                ["ldd", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            output = (r.stdout + r.stderr).lower()
            if "musl" in output:
                result["libc_type"] = "musl"
                ver = re.search(r"version\s+([\d.]+)", output)
                if ver:
                    result["glibc_version"] = ver.group(1)
        except (subprocess.TimeoutExpired, OSError):
            pass

    return result


# ── Main OS detection ──────────────────────────────────────────

def _detect_os() -> dict:
    """Detect full operating system profile.

    Returns a comprehensive dict covering: OS basics, architecture,
    distro identity and family, WSL, container environment,
    system capabilities, package managers, and library versions.
    """
    system = platform.system()
    machine = platform.machine()

    info: dict[str, object] = {
        "system": system,
        "release": platform.release(),
        "machine": machine,
        "arch": _ARCH_MAP.get(machine.lower(), machine.lower()),
    }

    # ── WSL detection ──────────────────────────────────────────
    version_str = ""
    try:
        with open("/proc/version", encoding="utf-8") as f:
            version_str = f.read().lower()
            info["wsl"] = "microsoft" in version_str or "wsl" in version_str
    except (FileNotFoundError, OSError):
        info["wsl"] = False

    if info["wsl"]:
        info["wsl_version"] = 2 if "wsl2" in version_str else 1
    else:
        info["wsl_version"] = None

    # ── Distro detection ───────────────────────────────────────
    if system == "Linux":
        osr = _parse_os_release()
        distro_id = osr.get("ID", "linux").lower()
        id_like = osr.get("ID_LIKE", "")
        version_id = osr.get("VERSION_ID", "")
        info["distro"] = {
            "id": distro_id,
            "name": osr.get("PRETTY_NAME", f"Linux ({distro_id})"),
            "version": version_id,
            "version_tuple": _parse_version_tuple(version_id) if version_id else [],
            "family": _get_distro_family(distro_id, id_like),
            "codename": osr.get("VERSION_CODENAME"),
        }
    elif system == "Darwin":
        mac_ver = platform.mac_ver()[0] or ""
        info["distro"] = {
            "id": "macos",
            "name": f"macOS {mac_ver}" if mac_ver else "macOS",
            "version": mac_ver,
            "version_tuple": _parse_version_tuple(mac_ver) if mac_ver else [],
            "family": "macos",
            "codename": None,
        }
    else:
        info["distro"] = {
            "id": system.lower(),
            "name": system,
            "version": "",
            "version_tuple": [],
            "family": "unknown",
            "codename": None,
        }

    # ── Container detection ────────────────────────────────────
    info["container"] = _detect_container()

    # ── System capabilities ────────────────────────────────────
    capabilities = _detect_capabilities()
    info["capabilities"] = capabilities

    # ── Package managers ───────────────────────────────────────
    info["package_manager"] = _detect_package_managers(
        bool(capabilities["has_systemd"]),
    )

    # ── Library versions ───────────────────────────────────────
    info["libraries"] = _detect_libraries()

    # ── Hardware basics (fast tier) ────────────────────────────
    hw: dict[str, object] = {
        "cpu_cores": os.cpu_count() or 1,
        "arch": info["arch"],
    }
    # RAM detection
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    hw["ram_total_mb"] = round(kb / 1024)
                elif line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    hw["ram_available_mb"] = round(kb / 1024)
    except (FileNotFoundError, OSError, ValueError):
        # Fallback for non-Linux or restricted containers
        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            if pages > 0 and page_size > 0:
                hw["ram_total_mb"] = round((pages * page_size) / (1024 * 1024))
        except (ValueError, OSError, AttributeError):
            hw.setdefault("ram_total_mb", None)
        hw.setdefault("ram_available_mb", None)
    # Disk free (root partition)
    try:
        disk_usage = shutil.disk_usage("/")
        hw["disk_free_gb"] = round(disk_usage.free / (1024 ** 3), 1)
        hw["disk_total_gb"] = round(disk_usage.total / (1024 ** 3), 1)
    except OSError:
        hw["disk_free_gb"] = None
        hw["disk_total_gb"] = None
    info["hardware"] = hw

    return info


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
# Cache: module-level dict with TTL (5 min). Different from the
# devops_cache used for audit cards — this is for deep-tier data
# that doesn't correspond to file changes.

import time as _time  # separate alias; `time` is imported locally in l0_system_profile

_deep_cache: dict[str, object] = {}  # {"data": {...}, "ts": float}
_DEEP_CACHE_TTL = 300  # 5 minutes


def _detect_shell() -> dict:
    """Detect shell environment (type, version, profile files, PATH health).

    Matches arch-system-model §Shell environment (Phase 4).
    """
    shell_path = os.environ.get("SHELL", "")
    shell_type = os.path.basename(shell_path) if shell_path else "unknown"

    # ── Profile / RC file mapping ─────────────────────────────
    _profile_map: dict[str, str] = {
        "bash": "~/.bash_profile",
        "zsh": "~/.zprofile",
        "fish": "~/.config/fish/config.fish",
        "sh": "~/.profile",
        "dash": "~/.profile",
    }
    _rc_map: dict[str, str] = {
        "bash": "~/.bashrc",
        "zsh": "~/.zshrc",
        "fish": "~/.config/fish/config.fish",
        "sh": "~/.profile",
        "dash": "~/.profile",
    }

    result: dict[str, object] = {
        "type": shell_type,
        "version": None,
        "login_profile": _profile_map.get(shell_type, "~/.profile"),
        "rc_file": _rc_map.get(shell_type, "~/.profile"),
        "path_healthy": True,
        "path_login": None,
        "path_nonlogin": None,
        "restricted": shell_type in ("rbash",) or shell_path.endswith("rbash"),
    }

    # ── Shell version ─────────────────────────────────────────
    if shell_path and shutil.which(shell_path):
        try:
            r = subprocess.run(
                [shell_path, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            output = r.stdout + r.stderr
            m = re.search(r"(\d+\.\d+[\.\d]*)", output)
            if m:
                result["version"] = m.group(1)
        except Exception:
            pass

    # ── PATH health check ─────────────────────────────────────
    # Compare login-shell PATH vs non-login PATH for mismatches.
    # Only for bash/zsh — fish has different mechanics.
    if shell_type in ("bash", "zsh") and shell_path:
        try:
            r_login = subprocess.run(
                [shell_path, "-l", "-c", "echo $PATH"],
                capture_output=True, text=True, timeout=5,
                env={**os.environ, "HOME": os.path.expanduser("~")},
            )
            r_nonlogin = subprocess.run(
                [shell_path, "-c", "echo $PATH"],
                capture_output=True, text=True, timeout=5,
                env={**os.environ, "HOME": os.path.expanduser("~")},
            )
            path_login = r_login.stdout.strip()
            path_nonlogin = r_nonlogin.stdout.strip()
            result["path_login"] = path_login
            result["path_nonlogin"] = path_nonlogin
            # PATH is "unhealthy" if login shell adds dirs that
            # non-login shell doesn't have (common .bashrc/.profile
            # misconfiguration that breaks tool visibility).
            if path_login and path_nonlogin:
                login_dirs = set(path_login.split(":"))
                nonlogin_dirs = set(path_nonlogin.split(":"))
                result["path_healthy"] = login_dirs == nonlogin_dirs
        except Exception:
            pass

    return result


def _detect_init_system_profile() -> dict:
    """Detect init system with full profile for service management.

    Matches arch-system-model §Init system (Phase 4).
    Goes beyond _detect_init_system() in tool_install.py by
    adding service manager binary and capability checks.
    """
    result: dict[str, object] = {
        "type": "unknown",
        "service_manager": None,
        "can_enable": False,
        "can_start": False,
    }

    if Path("/run/systemd/system").exists():
        result["type"] = "systemd"
        result["service_manager"] = "systemctl"
        result["can_enable"] = True
        result["can_start"] = True
    elif shutil.which("rc-service"):
        result["type"] = "openrc"
        result["service_manager"] = "rc-service"
        result["can_enable"] = shutil.which("rc-update") is not None
        result["can_start"] = True
    elif shutil.which("launchctl"):
        result["type"] = "launchd"
        result["service_manager"] = "launchctl"
        result["can_enable"] = True
        result["can_start"] = True
    elif Path("/etc/init.d").exists():
        result["type"] = "initd"
        result["service_manager"] = "service"
        # initd can start but enable depends on update-rc.d / chkconfig
        result["can_start"] = shutil.which("service") is not None
        result["can_enable"] = (
            shutil.which("update-rc.d") is not None
            or shutil.which("chkconfig") is not None
        )
    else:
        result["type"] = "none"

    return result


def _detect_build_profile() -> dict:
    """Detect build toolchain with structured output.

    Matches arch-system-model §Build toolchain (Phase 5).
    Reshapes detect_build_toolchain() output from tool_install.py
    into the schema the system model defines.
    """
    # Import here to avoid circular imports
    from src.core.services.tool_install import detect_build_toolchain

    raw = detect_build_toolchain()  # {name: version_or_None, ...}

    # ── Compilers ─────────────────────────────────────────────
    _compiler_names = ("gcc", "g++", "clang", "rustc", "go")
    compilers: dict[str, dict] = {}
    for name in _compiler_names:
        if name in raw:
            compilers[name] = {"available": True, "version": raw[name]}
        else:
            compilers[name] = {"available": False, "version": None}

    # ── Build tools ───────────────────────────────────────────
    _tool_names = ("make", "cmake", "ninja", "meson", "autoconf")
    build_tools: dict[str, bool] = {}
    for name in _tool_names:
        build_tools[name] = name in raw

    # ── Dev packages installed? ───────────────────────────────
    # Heuristic: if gcc AND make are available → likely has
    # build-essential or equivalent installed.
    dev_packages_installed = ("gcc" in raw and "make" in raw)

    # ── Resource info ─────────────────────────────────────────
    cpu_cores = os.cpu_count() or 1
    try:
        disk_usage = shutil.disk_usage("/")
        disk_free_gb = round(disk_usage.free / (1024 ** 3), 1)
    except Exception:
        disk_free_gb = 0.0
    try:
        tmp_usage = shutil.disk_usage("/tmp")
        tmp_free_gb = round(tmp_usage.free / (1024 ** 3), 1)
    except Exception:
        tmp_free_gb = disk_free_gb  # /tmp might be on root

    # ── macOS gcc → clang alias detection ──────────────────────
    gcc_is_clang = False
    if platform.system() == "Darwin" and "gcc" in raw:
        try:
            r = subprocess.run(
                ["gcc", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            if "clang" in r.stdout.lower():
                gcc_is_clang = True
        except Exception:
            pass

    return {
        "compilers": compilers,
        "build_tools": build_tools,
        "dev_packages_installed": dev_packages_installed,
        "cpu_cores": cpu_cores,
        "disk_free_gb": disk_free_gb,
        "tmp_free_gb": tmp_free_gb,
        "gcc_is_clang_alias": gcc_is_clang,
    }


def _detect_gpu_profile() -> dict:
    """Detect GPU hardware with full schema for Phase 6.

    Matches arch-system-model §GPU hardware (Phase 6).
    Wraps detect_gpu() from tool_install.py and adds fields
    the spec requires: nvcc_version, compute_capability, opencl_available.
    """
    from src.core.services.tool_install import detect_gpu

    raw = detect_gpu()

    # ── Enrich NVIDIA with nvcc (CUDA toolkit) version ────────
    nvcc_version = None
    if shutil.which("nvcc"):
        try:
            r = subprocess.run(
                ["nvcc", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            m = re.search(r"release\s+(\d+\.\d+)", r.stdout + r.stderr)
            if m:
                nvcc_version = m.group(1)
        except Exception:
            pass

    # ── Enrich NVIDIA with compute capability ─────────────────
    compute_capability = None
    if raw.get("nvidia", {}).get("driver_loaded") and shutil.which("nvidia-smi"):
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=compute_cap",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            cap = r.stdout.strip()
            if cap and cap != "[N/A]":
                compute_capability = cap
        except Exception:
            pass

    # ── cuDNN detection ────────────────────────────────────────
    cudnn_version = None
    cudnn_path = None
    if raw.get("nvidia", {}).get("present"):
        # Check for cudnn.h in common locations
        cudnn_search_paths = [
            "/usr/include/cudnn.h",
            "/usr/include/cudnn_version.h",
            "/usr/local/cuda/include/cudnn.h",
            "/usr/local/cuda/include/cudnn_version.h",
        ]
        for hdr_path in cudnn_search_paths:
            if os.path.isfile(hdr_path):
                cudnn_path = hdr_path
                try:
                    with open(hdr_path) as f:
                        content = f.read()
                    import re as _re
                    major = _re.search(r"CUDNN_MAJOR\s+(\d+)", content)
                    minor = _re.search(r"CUDNN_MINOR\s+(\d+)", content)
                    patch = _re.search(r"CUDNN_PATCHLEVEL\s+(\d+)", content)
                    if major and minor:
                        cudnn_version = f"{major.group(1)}.{minor.group(1)}"
                        if patch:
                            cudnn_version += f".{patch.group(1)}"
                except Exception:
                    pass
                break

        # Fallback: check ldconfig
        if not cudnn_version and shutil.which("ldconfig"):
            try:
                r = subprocess.run(
                    ["ldconfig", "-p"],
                    capture_output=True, text=True, timeout=5,
                )
                for line in r.stdout.splitlines():
                    if "libcudnn.so" in line:
                        import re as _re
                        m = _re.search(r"libcudnn\.so\.(\d+\.\d+\.\d+)", line)
                        if m:
                            cudnn_version = m.group(1)
                        break
            except Exception:
                pass

    # ── Enrich Intel with opencl_available ─────────────────────
    opencl_available = False
    if raw.get("intel", {}).get("present") and shutil.which("clinfo"):
        try:
            r = subprocess.run(
                ["clinfo"],
                capture_output=True, text=True, timeout=5,
            )
            opencl_available = "intel" in r.stdout.lower()
        except Exception:
            pass

    # ── Reshape to match system model schema ──────────────────
    return {
        "nvidia": {
            "present": raw.get("nvidia", {}).get("present", False),
            "model": raw.get("nvidia", {}).get("model"),
            "driver_version": raw.get("nvidia", {}).get("driver_version"),
            "cuda_version": raw.get("nvidia", {}).get("cuda_version"),
            "nvcc_version": nvcc_version,
            "compute_capability": compute_capability,
            "cudnn_version": cudnn_version,
            "cudnn_path": cudnn_path,
        },
        "amd": {
            "present": raw.get("amd", {}).get("present", False),
            "model": raw.get("amd", {}).get("model"),
            "rocm_version": raw.get("amd", {}).get("rocm_version"),
        },
        "intel": {
            "present": raw.get("intel", {}).get("present", False),
            "model": raw.get("intel", {}).get("model"),
            "opencl_available": opencl_available,
        },
    }


def _detect_kernel_profile() -> dict:
    """Detect kernel state with full schema for Phase 6.

    Matches arch-system-model §Kernel state (Phase 6).
    Wraps detect_kernel() from tool_install.py and adds fields
    the spec requires: config_available, config_path, loaded_modules
    (full lsmod), module_check for DevOps-relevant modules, iommu_groups.
    """
    from src.core.services.tool_install import detect_kernel

    raw = detect_kernel()
    version = raw.get("version", platform.release())

    # ── Kernel config detection ───────────────────────────────
    config_path = None
    config_available = False
    for candidate in [
        f"/boot/config-{version}",
        "/proc/config.gz",
        f"/lib/modules/{version}/config",
    ]:
        if Path(candidate).exists():
            config_path = candidate
            config_available = True
            break

    # ── Full lsmod (all loaded module names) ──────────────────
    loaded_modules: list[str] = []
    try:
        r = subprocess.run(
            ["lsmod"],
            capture_output=True, text=True, timeout=5,
        )
        for line in r.stdout.strip().splitlines()[1:]:  # skip header
            parts = line.split()
            if parts:
                loaded_modules.append(parts[0])
    except Exception:
        # Fallback to /proc/modules
        try:
            with open("/proc/modules", encoding="utf-8") as f:
                for line in f:
                    parts = line.split()
                    if parts:
                        loaded_modules.append(parts[0])
        except (FileNotFoundError, OSError):
            pass

    # ── Module check for DevOps-relevant modules ──────────────
    _MODULES_TO_CHECK = [
        "vfio_pci", "overlay", "br_netfilter",
        "nf_conntrack", "ip_tables",
    ]

    def _check_module(mod_name: str) -> dict:
        loaded = mod_name in loaded_modules
        # Check if .ko exists in /lib/modules
        compiled = False
        try:
            r = subprocess.run(
                ["find", f"/lib/modules/{version}",
                 "-name", f"{mod_name}.ko*", "-maxdepth", "4"],
                capture_output=True, text=True, timeout=5,
            )
            compiled = bool(r.stdout.strip())
        except Exception:
            pass
        # Check kernel config state
        config_state = None
        if config_path and config_path != "/proc/config.gz":
            cfg_key = f"CONFIG_{mod_name.upper().replace('-', '_')}"
            try:
                with open(config_path, encoding="utf-8") as f:
                    for line in f:
                        if line.startswith(cfg_key + "="):
                            config_state = line.strip().split("=", 1)[1]
                            break
            except (FileNotFoundError, OSError):
                pass
        return {
            "loaded": loaded,
            "compiled": compiled,
            "config_state": config_state,
        }

    module_check = {mod: _check_module(mod) for mod in _MODULES_TO_CHECK}

    # ── IOMMU groups ──────────────────────────────────────────
    iommu_groups: list[dict] | None = None
    iommu_base = Path("/sys/kernel/iommu_groups")
    if iommu_base.exists():
        iommu_groups = []
        try:
            for group_dir in sorted(iommu_base.iterdir()):
                if not group_dir.is_dir():
                    continue
                group_id = group_dir.name
                devices_dir = group_dir / "devices"
                devices = []
                if devices_dir.exists():
                    for dev in devices_dir.iterdir():
                        devices.append(dev.name)
                iommu_groups.append({
                    "id": group_id,
                    "devices": devices,
                })
        except (PermissionError, OSError):
            pass

    return {
        "version": version,
        "config_available": config_available,
        "config_path": config_path,
        "loaded_modules": loaded_modules,
        "module_check": module_check,
        "iommu_groups": iommu_groups,
        # Carry forward from detect_kernel() for convenience
        "headers_installed": raw.get("headers_installed", False),
        "dkms_available": raw.get("dkms_available", False),
        "secure_boot": raw.get("secure_boot"),
    }

def _detect_filesystem() -> dict:
    """Detect root filesystem type and free space.

    Matches arch-system-model §Filesystem and security (Phase 8).
    """
    root_type = "unknown"
    try:
        r = subprocess.run(
            ["df", "-T", "/"],
            capture_output=True, text=True, timeout=5,
        )
        # df -T output: Filesystem Type 1K-blocks Used Available Use% Mounted
        # We want the second column of the data row (skip header).
        lines = r.stdout.strip().splitlines()
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 2:
                root_type = parts[1]
    except Exception:
        pass

    root_free_gb = 0.0
    try:
        disk_usage = shutil.disk_usage("/")
        root_free_gb = round(disk_usage.free / (1024 ** 3), 1)
    except Exception:
        pass

    return {
        "root_type": root_type,
        "root_free_gb": root_free_gb,
    }


def _detect_security() -> dict:
    """Detect SELinux and AppArmor security context.

    Matches arch-system-model §Filesystem and security (Phase 8).
    """
    # ── SELinux ────────────────────────────────────────────────
    selinux_installed = shutil.which("getenforce") is not None
    selinux_mode = None
    if selinux_installed:
        try:
            r = subprocess.run(
                ["getenforce"],
                capture_output=True, text=True, timeout=5,
            )
            mode = r.stdout.strip()
            if mode in ("Enforcing", "Permissive", "Disabled"):
                selinux_mode = mode
        except Exception:
            pass

    # ── AppArmor ──────────────────────────────────────────────
    apparmor_path = Path("/sys/kernel/security/apparmor")
    apparmor_installed = apparmor_path.exists()
    apparmor_profiles_loaded = False
    if apparmor_installed:
        profiles_file = apparmor_path / "profiles"
        if profiles_file.exists():
            try:
                content = profiles_file.read_text(encoding="utf-8").strip()
                apparmor_profiles_loaded = len(content) > 0
            except (PermissionError, OSError):
                pass

    return {
        "selinux": {
            "installed": selinux_installed,
            "mode": selinux_mode,
        },
        "apparmor": {
            "installed": apparmor_installed,
            "profiles_loaded": apparmor_profiles_loaded,
        },
    }


def _detect_services() -> dict:
    """Detect system service infrastructure (journald, logrotate, cron).

    Matches arch-system-model §System services (Phase 8).
    """
    # ── journald ──────────────────────────────────────────────
    journald_active = False
    journald_disk_usage = None
    if shutil.which("systemctl"):
        try:
            r = subprocess.run(
                ["systemctl", "is-active", "systemd-journald"],
                capture_output=True, text=True, timeout=5,
            )
            journald_active = r.stdout.strip() == "active"
        except Exception:
            pass
    if journald_active and shutil.which("journalctl"):
        try:
            r = subprocess.run(
                ["journalctl", "--disk-usage"],
                capture_output=True, text=True, timeout=5,
            )
            # Output like: "Archived and active journals take up 1.2G in the file system."
            output = r.stdout.strip()
            if output:
                # Extract the size (e.g., "1.2G", "240.0M")
                m = re.search(r"([\d.]+[KMGTP])", output)
                if m:
                    journald_disk_usage = m.group(1)
        except Exception:
            pass

    return {
        "journald": {
            "active": journald_active,
            "disk_usage": journald_disk_usage,
        },
        "logrotate_installed": shutil.which("logrotate") is not None,
        "cron_available": shutil.which("crontab") is not None,
    }


def _detect_wsl_interop() -> dict:
    """Detect WSL interop capabilities.

    Matches arch-system-model §WSL interop (Phase 6).
    Only meaningful on WSL systems — on native Linux/macOS, returns
    all-false/none values quickly.
    """
    result: dict[str, object] = {
        "available": False,
        "binfmt_registered": False,
        "windows_user": None,
        "wslconfig_path": None,
    }

    # Quick exit if not WSL — check /proc/version first
    try:
        with open("/proc/version", encoding="utf-8") as f:
            version_str = f.read().lower()
        if "microsoft" not in version_str and "wsl" not in version_str:
            return result
    except (FileNotFoundError, OSError):
        return result

    # ── powershell.exe availability ───────────────────────────
    result["available"] = shutil.which("powershell.exe") is not None

    # ── binfmt_misc WSL interop ───────────────────────────────
    result["binfmt_registered"] = Path(
        "/proc/sys/fs/binfmt_misc/WSLInterop"
    ).exists()

    # ── Windows username ──────────────────────────────────────
    if shutil.which("cmd.exe"):
        try:
            r = subprocess.run(
                ["cmd.exe", "/c", "echo", "%USERNAME%"],
                capture_output=True, text=True, timeout=5,
            )
            username = r.stdout.strip()
            if username and username != "%USERNAME%":
                result["windows_user"] = username
        except Exception:
            pass

    # ── .wslconfig path ───────────────────────────────────────
    windows_user = result["windows_user"]
    if windows_user:
        # Standard location: C:\Users\USERNAME\.wslconfig
        # In WSL this is /mnt/c/Users/USERNAME/.wslconfig
        wslconfig_candidate = Path(
            f"/mnt/c/Users/{windows_user}/.wslconfig"
        )
        if wslconfig_candidate.exists():
            result["wslconfig_path"] = str(wslconfig_candidate)

    return result


# ── Network endpoint probes ─────────────────────────────────────

_NETWORK_ENDPOINTS = [
    "pypi.org",
    "github.com",
    "registry.npmjs.org",
]
_NETWORK_CONNECT_TIMEOUT = 3  # seconds


def _probe_endpoint(endpoint: str) -> dict:
    """Probe a single network endpoint for reachability.

    Returns: {"reachable": bool, "latency_ms": int|None, "error": str|None}
    """
    result: dict[str, object] = {
        "reachable": False,
        "latency_ms": None,
        "error": None,
    }

    # Prefer curl (available on most systems, handles HTTPS well)
    if shutil.which("curl"):
        try:
            t0 = _time.time()
            r = subprocess.run(
                [
                    "curl", "-s",
                    "--connect-timeout", str(_NETWORK_CONNECT_TIMEOUT),
                    "-o", "/dev/null",
                    "-w", "%{http_code}",
                    f"https://{endpoint}",
                ],
                capture_output=True, text=True,
                timeout=_NETWORK_CONNECT_TIMEOUT + 2,  # subprocess timeout > curl timeout
            )
            elapsed_ms = int((_time.time() - t0) * 1000)
            http_code = r.stdout.strip()

            if r.returncode == 0 and http_code.isdigit():
                code = int(http_code)
                if code > 0:
                    result["reachable"] = True
                    result["latency_ms"] = elapsed_ms
            else:
                # curl exit codes: 6=DNS, 7=refused, 28=timeout
                if r.returncode == 6:
                    result["error"] = "dns"
                elif r.returncode == 7:
                    result["error"] = "refused"
                elif r.returncode == 28:
                    result["error"] = "timeout"
                else:
                    result["error"] = f"curl_exit_{r.returncode}"
        except subprocess.TimeoutExpired:
            result["error"] = "timeout"
        except Exception as exc:
            result["error"] = str(exc)[:50]
    else:
        # Fallback: try urllib (no curl on some minimal installs)
        import urllib.request
        import urllib.error
        try:
            t0 = _time.time()
            req = urllib.request.Request(
                f"https://{endpoint}",
                method="HEAD",
            )
            urllib.request.urlopen(req, timeout=_NETWORK_CONNECT_TIMEOUT)
            elapsed_ms = int((_time.time() - t0) * 1000)
            result["reachable"] = True
            result["latency_ms"] = elapsed_ms
        except urllib.error.URLError as exc:
            reason = str(exc.reason).lower()
            if "name or service not known" in reason:
                result["error"] = "dns"
            elif "connection refused" in reason:
                result["error"] = "refused"
            elif "timed out" in reason:
                result["error"] = "timeout"
            else:
                result["error"] = str(exc.reason)[:50]
        except Exception as exc:
            result["error"] = str(exc)[:50]

    return result


def _detect_network() -> dict:
    """Detect network connectivity and proxy configuration.

    Matches arch-system-model §Network connectivity (Phase 4).

    Endpoint probes run in parallel using ThreadPoolExecutor so that
    the worst case is 1 × connect_timeout (3s) instead of N × 3s.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # ── Proxy detection (instant, env vars only) ──────────────
    https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    proxy_url = https_proxy or http_proxy
    proxy_detected = proxy_url is not None

    # ── Parallel endpoint probes ──────────────────────────────
    endpoints: dict[str, dict] = {}

    with ThreadPoolExecutor(max_workers=len(_NETWORK_ENDPOINTS)) as pool:
        futures = {
            pool.submit(_probe_endpoint, ep): ep
            for ep in _NETWORK_ENDPOINTS
        }
        for future in as_completed(futures):
            ep = futures[future]
            try:
                endpoints[ep] = future.result()
            except Exception as exc:
                endpoints[ep] = {
                    "reachable": False,
                    "latency_ms": None,
                    "error": str(exc)[:50],
                }

    # ── Online = at least one endpoint reachable ──────────────
    online = any(ep.get("reachable") for ep in endpoints.values())

    return {
        "online": online,
        "proxy_detected": proxy_detected,
        "proxy_url": proxy_url,
        "endpoints": endpoints,
    }


# ── Valid deep tier categories ──────────────────────────────────

_DEEP_DETECTORS: dict[str, callable] = {
    # Phase 4
    "shell": _detect_shell,
    "init_system": _detect_init_system_profile,
    "network": _detect_network,
    # Phase 5
    "build": _detect_build_profile,
    # Phase 6
    "gpu": _detect_gpu_profile,
    "kernel": _detect_kernel_profile,
    "wsl_interop": _detect_wsl_interop,
    # Phase 8
    "services": _detect_services,
    "filesystem": _detect_filesystem,
    "security": _detect_security,
}


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
