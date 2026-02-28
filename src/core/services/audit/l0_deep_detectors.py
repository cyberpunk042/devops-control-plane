"""
L0 — Deep-tier detection functions.

Expensive OS/hardware probes (shell, init system, network, build
toolchain, GPU, kernel, WSL interop, filesystem, security, services).

Each function is self-contained and returns a dict matching the
arch-system-model schema for its phase.  All are registered in
``_DEEP_DETECTORS`` and called by the orchestrator in l0_detection.py.

Split from ``l0_detection.py`` — that file kept the fast-tier
detectors and the public API entry point.
"""

from __future__ import annotations

import logging
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  Phase 4 — Shell, Init System, Network
# ═══════════════════════════════════════════════════════════════════


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
    import time as _time

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


# ═══════════════════════════════════════════════════════════════════
#  Phase 5 — Build Toolchain
# ═══════════════════════════════════════════════════════════════════


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

# ═══════════════════════════════════════════════════════════════════
#  Phase 6 — GPU, Kernel, WSL Interop  (split to l0_hw_detectors.py)
# ═══════════════════════════════════════════════════════════════════

from src.core.services.audit.l0_hw_detectors import (  # noqa: E402
    _detect_gpu_profile,
    _detect_kernel_profile,
    _detect_wsl_interop,
)


# ═══════════════════════════════════════════════════════════════════
#  Phase 8 — Filesystem, Security, Services
# ═══════════════════════════════════════════════════════════════════


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


# ═══════════════════════════════════════════════════════════════════
#  Detector registry
# ═══════════════════════════════════════════════════════════════════

DEEP_DETECTORS: dict[str, callable] = {
    # Phase 4
    "shell": _detect_shell,
    "init_system": _detect_init_system_profile,
    "network": _detect_network,
    # Phase 5
    "build": _detect_build_profile,
    # Phase 6 (from l0_hw_detectors)
    "gpu": _detect_gpu_profile,
    "kernel": _detect_kernel_profile,
    "wsl_interop": _detect_wsl_interop,
    # Phase 8
    "services": _detect_services,
    "filesystem": _detect_filesystem,
    "security": _detect_security,
}
