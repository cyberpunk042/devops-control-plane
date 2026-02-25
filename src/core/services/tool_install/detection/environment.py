"""
L3 Detection — Environment capabilities.

Read-only probes for sandbox/confinement detection,
version manager (nvm/pyenv) detection, and CPU features.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from pathlib import Path


# ── L3: Sandbox / confinement detection ──────────────────────

def detect_sandbox() -> dict:
    """Detect if the environment is sandboxed or confined.

    Checks for snap, Flatpak, SELinux, AppArmor, chroot, and
    Docker/container confinement. Returns a structured dict
    indicating which confinements are active.

    Returns::

        {
            "is_sandboxed": True,
            "snap": {"active": True, "confinement": "strict"},
            "flatpak": {"active": False},
            "selinux": {"active": True, "mode": "enforcing"},
            "apparmor": {"active": False},
            "chroot": {"active": False},
            "restrictions": ["no_network", "read_only_home"],
        }
    """
    result: dict = {
        "is_sandboxed": False,
        "snap": {"active": False},
        "flatpak": {"active": False},
        "selinux": {"active": False, "mode": None},
        "apparmor": {"active": False, "mode": None},
        "chroot": {"active": False},
        "restrictions": [],
    }

    # ── Snap confinement ──
    if os.environ.get("SNAP"):
        result["snap"]["active"] = True
        result["is_sandboxed"] = True
        confinement = os.environ.get("SNAP_CONFINEMENT", "unknown")
        result["snap"]["confinement"] = confinement
        result["snap"]["snap_name"] = os.environ.get("SNAP_NAME", "")
        if confinement == "strict":
            result["restrictions"].extend(["no_network_bypass", "read_only_system"])

    # ── Flatpak sandbox ──
    if os.environ.get("FLATPAK_ID"):
        result["flatpak"]["active"] = True
        result["is_sandboxed"] = True
        result["flatpak"]["app_id"] = os.environ["FLATPAK_ID"]
        result["restrictions"].append("flatpak_sandbox")

    # ── SELinux ──
    if shutil.which("getenforce"):
        try:
            r = subprocess.run(
                ["getenforce"],
                capture_output=True, text=True, timeout=5,
            )
            mode = r.stdout.strip().lower()
            if mode in ("enforcing", "permissive"):
                result["selinux"]["active"] = True
                result["selinux"]["mode"] = mode
                if mode == "enforcing":
                    result["is_sandboxed"] = True
                    result["restrictions"].append("selinux_enforcing")
        except Exception:
            pass

    # ── AppArmor ──
    if Path("/sys/module/apparmor").exists():
        result["apparmor"]["active"] = True
        try:
            status = Path("/sys/module/apparmor/parameters/enabled").read_text().strip()
            result["apparmor"]["mode"] = "enabled" if status == "Y" else "disabled"
        except (OSError, PermissionError):
            result["apparmor"]["mode"] = "unknown"

    # ── chroot detection ──
    try:
        # root inode != 2 → likely in chroot
        stat_root = os.stat("/")
        if stat_root.st_ino != 2:
            result["chroot"]["active"] = True
            result["is_sandboxed"] = True
            result["restrictions"].append("chroot")
    except OSError:
        pass

    return result


# ── L5: nvm / version manager detection ─────────────────

def detect_nvm() -> dict:
    """Detect nvm (Node Version Manager) installation.

    Checks for NVM_DIR env var and nvm.sh source availability.

    Returns::

        {
            "installed": True,
            "nvm_dir": "/home/user/.nvm",
            "current_node": "v20.11.0",
            "available_versions": ["v18.19.0", "v20.11.0"],
        }
    """
    nvm_dir = os.environ.get("NVM_DIR", "")
    if not nvm_dir:
        # Check default locations
        home = os.path.expanduser("~")
        for candidate in [
            os.path.join(home, ".nvm"),
            os.path.join(home, ".config", "nvm"),
        ]:
            if os.path.isdir(candidate):
                nvm_dir = candidate
                break

    if not nvm_dir or not os.path.isdir(nvm_dir):
        return {"installed": False}

    result: dict = {
        "installed": True,
        "nvm_dir": nvm_dir,
        "current_node": None,
        "available_versions": [],
    }

    # Check available versions
    versions_dir = os.path.join(nvm_dir, "versions", "node")
    if os.path.isdir(versions_dir):
        try:
            versions = sorted(
                [d for d in os.listdir(versions_dir) if d.startswith("v")],
                reverse=True,
            )
            result["available_versions"] = versions[:10]
        except OSError:
            pass

    # Check current node version
    node_path = shutil.which("node")
    if node_path and nvm_dir in node_path:
        try:
            r = subprocess.run(
                ["node", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            result["current_node"] = r.stdout.strip()
        except Exception:
            pass

    return result


# ── L12: CPU feature detection ───────────────────────────

def detect_cpu_features() -> dict:
    """Parse /proc/cpuinfo for CPU instruction set features.

    Detects SIMD extensions (SSE, AVX, etc.), virtualization
    support (VMX/SVM), and other relevant CPU flags.

    Returns::

        {
            "flags": ["sse", "sse2", "avx", "avx2", "aes", ...],
            "has_avx2": True,
            "has_avx512": False,
            "has_vmx": True,
            "has_aes": True,
        }
    """
    flags: list[str] = []

    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("flags"):
                    flags = line.split(":", 1)[1].strip().split()
                    break
    except (FileNotFoundError, IndexError):
        # macOS or non-Linux
        if platform.system() == "Darwin":
            try:
                r = subprocess.run(
                    ["sysctl", "-n", "machdep.cpu.features"],
                    capture_output=True, text=True, timeout=5,
                )
                flags = [f.lower() for f in r.stdout.strip().split()]
            except Exception:
                pass

    flags_set = set(flags)

    return {
        "flags": flags,
        "has_avx2": "avx2" in flags_set,
        "has_avx512": bool(flags_set & {"avx512f", "avx512bw", "avx512cd"}),
        "has_vmx": "vmx" in flags_set,
        "has_svm": "svm" in flags_set,
        "has_aes": "aes" in flags_set,
        "has_sse4_2": "sse4_2" in flags_set,
    }
