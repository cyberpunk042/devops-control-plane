"""
L3 Detection — GPU, kernel, and hardware detection.

Read-only system probes: lspci, nvidia-smi, rocminfo,
/proc/cpuinfo, /proc/meminfo, mokutil.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

from src.core.services.tool_install.data.cuda_matrix import _CUDA_DRIVER_COMPAT


# ── GPU helpers ────────────────────────────────────────────

def _extract_gpu_model(line: str) -> str:
    """Extract GPU model from an lspci line."""
    # e.g. "01:00.0 VGA compatible controller [0300]: NVIDIA Corporation ... [10de:2684]"
    # Strip PCI address and classification, keep the device name
    parts = line.split(":", 2)
    if len(parts) >= 3:
        # Remove PCI ID brackets at end
        model = re.sub(r"\s*\[[0-9a-f:]+\]\s*$", "", parts[2].strip())
        return model
    return line.strip()


def _extract_pci_id(line: str) -> str | None:
    """Extract PCI vendor:device ID from an lspci line."""
    m = re.search(r"\[([0-9a-f]{4}:[0-9a-f]{4})\]", line, re.IGNORECASE)
    return m.group(1) if m else None


def _lspci_gpu() -> dict | None:
    """Parse lspci for GPU info."""
    try:
        r = subprocess.run(
            ["lspci", "-nn"],
            capture_output=True, text=True, timeout=5,
        )
        for line in r.stdout.splitlines():
            if "VGA" in line or "3D controller" in line:
                upper = line.upper()
                if "NVIDIA" in upper or "10DE:" in upper:
                    return {"vendor": "nvidia",
                            "model": _extract_gpu_model(line),
                            "pci_id": _extract_pci_id(line)}
                if "AMD" in upper or "ATI" in upper or "1002:" in upper:
                    return {"vendor": "amd",
                            "model": _extract_gpu_model(line),
                            "pci_id": _extract_pci_id(line)}
                if "INTEL" in upper:
                    return {"vendor": "intel",
                            "model": _extract_gpu_model(line),
                            "pci_id": _extract_pci_id(line)}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _nvidia_smi() -> dict | None:
    """Get NVIDIA driver and CUDA info from nvidia-smi."""
    if not shutil.which("nvidia-smi"):
        return None
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version,name",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            parts = r.stdout.strip().split(",")
            driver_ver = parts[0].strip()

            # Get CUDA version from the header nvidia-smi output
            r2 = subprocess.run(
                ["nvidia-smi"],
                capture_output=True, text=True, timeout=5,
            )
            cuda_ver = None
            m = re.search(r"CUDA Version:\s+(\d+\.\d+)", r2.stdout)
            if m:
                cuda_ver = m.group(1)

            return {"driver_version": driver_ver, "cuda_version": cuda_ver}
    except Exception:
        pass
    return None


def _rocminfo() -> dict | None:
    """Get AMD ROCm info."""
    if not shutil.which("rocminfo"):
        return None
    try:
        r = subprocess.run(
            ["rocminfo"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            m = re.search(r"Runtime Version:\s+(\d+\.\d+)", r.stdout)
            return {"version": m.group(1)} if m else {"version": "unknown"}
    except Exception:
        pass
    return None


def _list_gpu_modules() -> list[str]:
    """List loaded GPU-related kernel modules."""
    relevant = {"nvidia", "nvidia_drm", "nvidia_modeset", "nvidia_uvm",
                "nouveau", "amdgpu", "radeon", "i915", "vfio_pci"}
    try:
        with open("/proc/modules") as f:
            loaded = {line.split()[0] for line in f}
        return sorted(relevant & loaded)
    except FileNotFoundError:
        return []


def detect_gpu() -> dict:
    """Detect GPU hardware and driver state.

    Returns a structured dict with:
      - Per-vendor GPU info (nvidia, amd, intel)
      - Driver version and loaded status
      - CUDA/ROCm version if applicable
      - Loaded kernel modules

    This feeds into Phase 4 choice constraint evaluation for
    hardware-gated options (CUDA, ROCm, OpenCL).
    """
    result: dict = {
        "has_gpu": False,
        "nvidia": {"present": False, "model": None, "driver_version": None,
                   "cuda_version": None, "driver_loaded": False},
        "amd": {"present": False, "model": None, "rocm_version": None,
                "driver_loaded": False},
        "intel": {"present": False, "model": None,
                  "driver_loaded": False},
        "modules_loaded": [],
    }

    # Detect via lspci
    gpu_info = _lspci_gpu()
    if gpu_info:
        result["has_gpu"] = True
        vendor = gpu_info["vendor"]

        if vendor == "nvidia":
            result["nvidia"]["present"] = True
            result["nvidia"]["model"] = gpu_info["model"]
            result["nvidia"]["pci_id"] = gpu_info.get("pci_id")
            # nvidia-smi for driver + CUDA
            nvsmi = _nvidia_smi()
            if nvsmi:
                result["nvidia"]["driver_loaded"] = True
                result["nvidia"]["driver_version"] = nvsmi["driver_version"]
                result["nvidia"]["cuda_version"] = nvsmi["cuda_version"]

        elif vendor == "amd":
            result["amd"]["present"] = True
            result["amd"]["model"] = gpu_info["model"]
            result["amd"]["pci_id"] = gpu_info.get("pci_id")
            # ROCm info
            rocm = _rocminfo()
            if rocm:
                result["amd"]["driver_loaded"] = True
                result["amd"]["rocm_version"] = rocm["version"]

        elif vendor == "intel":
            result["intel"]["present"] = True
            result["intel"]["model"] = gpu_info["model"]
            result["intel"]["pci_id"] = gpu_info.get("pci_id")

    # Check loaded modules
    result["modules_loaded"] = _list_gpu_modules()

    # Infer driver_loaded from modules if not set via tool
    if not result["nvidia"]["driver_loaded"]:
        result["nvidia"]["driver_loaded"] = "nvidia" in result["modules_loaded"]
    if not result["amd"]["driver_loaded"]:
        result["amd"]["driver_loaded"] = "amdgpu" in result["modules_loaded"]
    if not result["intel"]["driver_loaded"]:
        result["intel"]["driver_loaded"] = "i915" in result["modules_loaded"]

    # ── Container GPU passthrough detection ──
    result["container_gpu"] = {"passthrough_detected": False, "method": None}
    # Check for NVIDIA device nodes (Docker --gpus or k8s GPU plugin)
    if os.path.exists("/dev/nvidia0"):
        result["container_gpu"]["passthrough_detected"] = True
        result["container_gpu"]["method"] = "nvidia-device"
        result["nvidia"]["present"] = True
    # Check NVIDIA_VISIBLE_DEVICES env var (Docker --gpus flag)
    if os.environ.get("NVIDIA_VISIBLE_DEVICES"):
        result["container_gpu"]["passthrough_detected"] = True
        result["container_gpu"]["method"] = "nvidia-docker"
        result["container_gpu"]["visible_devices"] = os.environ["NVIDIA_VISIBLE_DEVICES"]
        result["nvidia"]["present"] = True
    # Check for AMD/Intel render nodes
    if os.path.exists("/dev/dri/renderD128"):
        if not result["container_gpu"]["passthrough_detected"]:
            result["container_gpu"]["passthrough_detected"] = True
            result["container_gpu"]["method"] = "dri-render-node"

    return result


def check_cuda_driver_compat(
    cuda_version: str,
    driver_version: str,
) -> dict:
    """Check if a driver version is compatible with a CUDA toolkit version.

    Args:
        cuda_version: Installed or target CUDA version, e.g. ``"12.4"``.
        driver_version: Installed NVIDIA driver version, e.g. ``"535.183"``.

    Returns:
        ``{"compatible": True}`` or
        ``{"compatible": False, "min_driver": "...", "message": "..."}``
    """
    # Normalize cuda_version to major.minor
    parts = cuda_version.split(".")
    cuda_mm = f"{parts[0]}.{parts[1]}" if len(parts) >= 2 else cuda_version

    min_driver = None
    for cv, md in _CUDA_DRIVER_COMPAT:
        if cv == cuda_mm:
            min_driver = md
            break

    if min_driver is None:
        # Unknown CUDA version — can't validate
        return {"compatible": True, "unknown_cuda": cuda_mm}

    try:
        drv_parts = [int(x) for x in driver_version.split(".")]
        min_parts = [int(x) for x in min_driver.split(".")]

        # Compare major.minor
        drv_tuple = tuple(drv_parts[:2]) if len(drv_parts) >= 2 else (drv_parts[0], 0)
        min_tuple = tuple(min_parts[:2]) if len(min_parts) >= 2 else (min_parts[0], 0)

        if drv_tuple >= min_tuple:
            return {"compatible": True}
        else:
            return {
                "compatible": False,
                "min_driver": min_driver,
                "message": (
                    f"CUDA {cuda_mm} requires driver >= {min_driver}, "
                    f"but installed driver is {driver_version}. "
                    f"Update the NVIDIA driver first."
                ),
            }
    except (ValueError, IndexError):
        return {"compatible": True, "parse_error": True}


# ── Secure Boot detection ──

def _detect_secure_boot() -> bool | None:
    """Detect if Secure Boot is enabled.

    Returns True if enabled, False if disabled, None if detection fails
    (no mokutil, not applicable for the platform).
    """
    try:
        r = subprocess.run(
            ["mokutil", "--sb-state"],
            capture_output=True, text=True, timeout=5,
        )
        if "SecureBoot enabled" in r.stdout:
            return True
        if "SecureBoot disabled" in r.stdout:
            return False
    except FileNotFoundError:
        pass
    return None


def detect_kernel() -> dict:
    """Detect kernel version, headers, DKMS, Secure Boot, and GPU modules.

    Returns:
        Dict with kernel details for driver/module install decisions.
    """
    version = platform.release()
    result: dict = {
        "version": version,
        "major": None,
        "minor": None,
        "arch": platform.machine(),
        "headers_installed": False,
        "dkms_available": False,
        "secure_boot": None,
        "modules_loaded": [],
    }

    # Parse version
    m = re.match(r"(\d+)\.(\d+)\.", version)
    if m:
        result["major"] = int(m.group(1))
        result["minor"] = int(m.group(2))

    # Kernel headers
    result["headers_installed"] = Path(
        f"/lib/modules/{version}/build"
    ).exists()

    # DKMS
    result["dkms_available"] = shutil.which("dkms") is not None

    # Secure Boot
    result["secure_boot"] = _detect_secure_boot()

    # GPU-related loaded modules
    result["modules_loaded"] = _list_gpu_modules()

    return result


# ── Hardware detection helpers ──

def _read_cpu_model() -> str:
    """Read CPU model name from /proc/cpuinfo."""
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except (FileNotFoundError, IndexError):
        pass
    return platform.processor() or "unknown"


def _read_total_ram_mb() -> int:
    """Read total RAM in MB from /proc/meminfo."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
    except (FileNotFoundError, ValueError):
        pass
    return 0


def _read_available_ram_mb() -> int:
    """Read available RAM in MB from /proc/meminfo."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except (FileNotFoundError, ValueError):
        pass
    return 0


def _read_disk_free_mb(path: str = "/") -> int:
    """Read free disk space in MB."""
    try:
        import shutil as sh
        disk = sh.disk_usage(path)
        return disk.free // (1024 * 1024)
    except OSError:
        return 0


def detect_hardware() -> dict:
    """Detect hardware capabilities — CPU, RAM, disk, GPU, kernel.

    Assembles a full hardware profile that feeds into Phase 4 choice
    constraint evaluation and Phase 5 resource checking.

    Returns::

        {
            "cpu_arch": "x86_64",
            "cpu_count": 8,
            "cpu_model": "Intel Core i7-12700K",
            "ram_total_mb": 16384,
            "ram_available_mb": 12288,
            "disk_free_mb": 50000,
            "gpu": { ... },
            "kernel": { ... },
        }
    """
    return {
        "cpu_arch": platform.machine(),
        "cpu_count": os.cpu_count(),
        "cpu_model": _read_cpu_model(),
        "ram_total_mb": _read_total_ram_mb(),
        "ram_available_mb": _read_available_ram_mb(),
        "disk_free_mb": _read_disk_free_mb("/"),
        "gpu": detect_gpu(),
        "kernel": detect_kernel(),
    }


def detect_build_toolchain() -> dict[str, str | None]:
    """Detect available build tools and their versions.

    Checks compilers (gcc, clang, rustc), build systems (make, cmake,
    ninja, meson, autotools), and language toolchains (cargo, go).

    Returns:
        Dict mapping tool name → version string (or None if not found).
        Only includes tools that are actually installed.
    """
    _patterns = {
        "gcc": r"(\d+\.\d+\.\d+)",
        "g++": r"(\d+\.\d+\.\d+)",
        "clang": r"(\d+\.\d+\.\d+)",
        "make": r"(\d+\.\d+)",
        "cmake": r"(\d+\.\d+\.\d+)",
        "ninja": r"(\d+\.\d+\.\d+)",
        "meson": r"(\d+\.\d+\.\d+)",
        "autoconf": r"(\d+\.\d+)",
        "automake": r"(\d+\.\d+)",
        "pkg-config": r"(\d+\.\d+)",
        "rustc": r"(\d+\.\d+\.\d+)",
        "cargo": r"(\d+\.\d+\.\d+)",
        "go": r"go(\d+\.\d+\.\d+)",
    }
    found: dict[str, str | None] = {}
    for binary, pattern in _patterns.items():
        if not shutil.which(binary):
            continue
        try:
            r = subprocess.run(
                [binary, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            m = re.search(pattern, r.stdout + r.stderr)
            found[binary] = m.group(1) if m else "unknown"
        except Exception:
            found[binary] = "unknown"
    return found
