"""
L0 — Hardware-level deep detectors (Phase 6).

GPU hardware enrichment, kernel state profiling, and WSL interop
detection.  These are the most expensive probes in the deep tier,
each potentially shelling out to system tools.

Split from ``l0_deep_detectors.py`` — that file kept Phase 4
(shell, init, network), Phase 5 (build), and Phase 8 (filesystem,
security, services).
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
#  GPU hardware
# ═══════════════════════════════════════════════════════════════════


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
                    major = re.search(r"CUDNN_MAJOR\s+(\d+)", content)
                    minor = re.search(r"CUDNN_MINOR\s+(\d+)", content)
                    patch = re.search(r"CUDNN_PATCHLEVEL\s+(\d+)", content)
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
                        m = re.search(r"libcudnn\.so\.(\d+\.\d+\.\d+)", line)
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


# ═══════════════════════════════════════════════════════════════════
#  Kernel state
# ═══════════════════════════════════════════════════════════════════


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


# ═══════════════════════════════════════════════════════════════════
#  WSL interop
# ═══════════════════════════════════════════════════════════════════


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
