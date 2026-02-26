# Tool Install v2 — Phase 6: Hardware Detection & Kernel Management

## Context

Phases 2-5 install software (packages, binaries, builds). Phase 6
extends the system profile to detect GPU hardware, kernel config,
and hardware capabilities — then provides recipes that install
drivers, CUDA toolkits, kernel modules, and hardware-dependent
software.

### Dependencies

```
Phase 1 (detection)    ── provides: basic system profile
Phase 4 (choices)      ── provides: GPU driver version choice UI
Phase 5 (build)        ── provides: build-from-source for custom kernels
Phase 6 (THIS)         ── provides: GPU/kernel detection, driver recipes
```

### Domains consumed

| Domain | What Phase 6 uses |
|--------|------------------|
| domain-gpu | GPU detection, driver matrix, CUDA/ROCm install |
| domain-kernel | Kernel version, module management, DKMS |
| domain-hardware-detect | RAM, disk, CPU, architecture |

---

## System Profile Expansion

### New fields added to fast profile

```python
def detect_hardware() -> dict:
    """Detect hardware capabilities."""
    return {
        # CPU
        "cpu_arch": platform.machine(),           # x86_64, aarch64
        "cpu_count": os.cpu_count(),              # 8
        "cpu_model": _read_cpu_model(),           # "Intel Core i7-12700K"

        # RAM
        "ram_total_mb": _read_total_ram_mb(),     # 16384
        "ram_available_mb": _read_avail_ram_mb(), # 12288

        # Disk
        "disk_free_mb": _read_disk_free_mb("/"),  # 50000

        # GPU
        "gpu": detect_gpu(),                      # see below

        # Kernel
        "kernel": detect_kernel(),                # see below
    }
```

### GPU detection

```python
def detect_gpu() -> dict:
    """Detect GPU hardware and driver state."""
    result = {
        "has_gpu": False,
        "vendor": None,        # "nvidia", "amd", "intel"
        "model": None,         # "NVIDIA GeForce RTX 4090"
        "pci_id": None,        # "10de:2684"
        "driver_loaded": False,
        "driver_version": None,
        "cuda_version": None,
        "rocm_version": None,
    }

    # Method 1: lspci
    gpu_info = _lspci_gpu()
    if gpu_info:
        result["has_gpu"] = True
        result["vendor"] = gpu_info["vendor"]
        result["model"] = gpu_info["model"]
        result["pci_id"] = gpu_info["pci_id"]

    # Method 2: nvidia-smi (if NVIDIA)
    if result["vendor"] == "nvidia":
        nvidia = _nvidia_smi()
        if nvidia:
            result["driver_loaded"] = True
            result["driver_version"] = nvidia["driver_version"]
            result["cuda_version"] = nvidia["cuda_version"]

    # Method 3: ROCm (if AMD)
    if result["vendor"] == "amd":
        rocm = _rocminfo()
        if rocm:
            result["driver_loaded"] = True
            result["rocm_version"] = rocm["version"]

    # Method 4: Check loaded kernel modules
    if not result["driver_loaded"]:
        result["driver_loaded"] = _check_gpu_modules(result["vendor"])

    return result


def _lspci_gpu() -> dict | None:
    """Parse lspci for GPU info."""
    try:
        r = subprocess.run(
            ["lspci", "-nn"],
            capture_output=True, text=True, timeout=5,
        )
        for line in r.stdout.splitlines():
            if "VGA" in line or "3D controller" in line:
                if "NVIDIA" in line.upper() or "10de:" in line:
                    return {"vendor": "nvidia", "model": _extract_model(line),
                            "pci_id": _extract_pci_id(line)}
                if "AMD" in line.upper() or "ATI" in line.upper() or "1002:" in line:
                    return {"vendor": "amd", "model": _extract_model(line),
                            "pci_id": _extract_pci_id(line)}
                if "Intel" in line:
                    return {"vendor": "intel", "model": _extract_model(line),
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
        if r.returncode == 0:
            parts = r.stdout.strip().split(",")
            driver_ver = parts[0].strip()

            # Get CUDA version
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
```

### Kernel detection

```python
def detect_kernel() -> dict:
    """Detect kernel version and capabilities."""
    import platform

    result = {
        "version": platform.release(),        # "6.5.0-44-generic"
        "major": None,                         # 6
        "minor": None,                         # 5
        "arch": platform.machine(),            # x86_64
        "headers_installed": False,
        "dkms_available": False,
        "secure_boot": None,                   # True/False/None
        "modules_loaded": [],                   # relevant modules
    }

    # Parse version
    m = re.match(r"(\d+)\.(\d+)\.", result["version"])
    if m:
        result["major"] = int(m.group(1))
        result["minor"] = int(m.group(2))

    # Kernel headers
    headers_pkg = f"linux-headers-{result['version']}"
    result["headers_installed"] = Path(
        f"/lib/modules/{result['version']}/build"
    ).exists()

    # DKMS
    result["dkms_available"] = shutil.which("dkms") is not None

    # Secure Boot
    result["secure_boot"] = _detect_secure_boot()

    # Relevant kernel modules
    result["modules_loaded"] = _list_gpu_modules()

    return result


def _detect_secure_boot() -> bool | None:
    """Detect if Secure Boot is enabled."""
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


def _list_gpu_modules() -> list[str]:
    """List loaded GPU-related kernel modules."""
    relevant = {"nvidia", "nvidia_drm", "nvidia_modeset", "nvidia_uvm",
                "nouveau", "amdgpu", "radeon", "i915"}
    try:
        with open("/proc/modules") as f:
            loaded = {line.split()[0] for line in f}
        return sorted(relevant & loaded)
    except FileNotFoundError:
        return []
```

---

## NVIDIA Driver Recipes

### Driver option matrix

```python
"nvidia-driver": {
    "label": "NVIDIA Driver",
    "category": "gpu",
    "risk": "high",
    "choices": [
        {
            "id": "driver_version",
            "type": "select_one",
            "label": "Driver Version",
            "options": [
                {
                    "value": "recommended",
                    "label": "Recommended (auto-detect)",
                    "default": True,
                },
                {
                    "value": "latest",
                    "label": "Latest (535+)",
                    "requires": {"kernel": ">=5.4"},
                },
                {
                    "value": "470",
                    "label": "470 (legacy)",
                    "description": "For older GPUs (Kepler)",
                },
            ],
        },
        {
            "id": "method",
            "type": "select_one",
            "label": "Install Method",
            "options": [
                {"value": "apt", "label": "Package manager (recommended)"},
                {"value": "runfile", "label": ".run file (advanced)",
                 "risk": "high"},
            ],
        },
    ],
    "install": {
        "apt": {
            "debian": {
                "repo_setup": [
                    {"command": ["add-apt-repository", "-y", "ppa:graphics-drivers/ppa"],
                     "needs_sudo": True},
                    {"command": ["apt-get", "update"],
                     "needs_sudo": True},
                ],
                "command": ["apt-get", "install", "-y", "nvidia-driver-{version}"],
            },
        },
    },
    "post_install": [
        {"label": "Load nvidia module",
         "command": ["modprobe", "nvidia"],
         "needs_sudo": True,
         "condition": {"secure_boot": False}},
    ],
    "verify": ["nvidia-smi"],
    "requires": {
        "hardware": {"gpu_vendor": "nvidia"},
        "packages": {
            "debian": ["linux-headers-{kernel_version}"],
        },
    },
    "rollback": {
        "command": ["apt-get", "purge", "-y", "nvidia-driver-*"],
        "post": ["modprobe", "nouveau"],
    },
}
```

### CUDA toolkit

```python
"cuda-toolkit": {
    "label": "CUDA Toolkit",
    "category": "gpu",
    "choices": [
        {
            "id": "cuda_version",
            "type": "select_version",
            "label": "CUDA Version",
            "version_source": {
                "type": "static",
                "versions": ["12.4", "12.3", "12.2", "12.1",
                              "11.8", "11.7"],
            },
            "constraint": {
                "type": "driver_compat",
                "rule": "CUDA version must match driver support",
            },
            "default_strategy": "latest_compatible",
        },
    ],
    "requires": {
        "hardware": {"gpu_vendor": "nvidia"},
        "tools": ["nvidia-smi"],  # driver must be installed first
    },
}
```

---

## Kernel Module Management

### DKMS recipes

```python
# Tools that install kernel modules via DKMS
"wireguard": {
    "install": {
        "debian": ["apt-get", "install", "-y", "wireguard"],
    },
    "requires": {
        "kernel": {"modules_build": True},  # needs headers + dkms
        "packages": {
            "debian": ["linux-headers-{kernel_version}", "dkms"],
        },
    },
    "risk": "medium",
    "post_install": [
        {"label": "Load wireguard module",
         "command": ["modprobe", "wireguard"],
         "needs_sudo": True},
    ],
}
```

### Secure Boot impact

```python
def _check_secure_boot_impact(step: dict, kernel: dict) -> dict | None:
    """Check if Secure Boot blocks a kernel module operation."""
    if not kernel.get("secure_boot"):
        return None  # Secure Boot off — no issue

    if step.get("type") == "post_install":
        cmd = step.get("command", [])
        if cmd and cmd[0] == "modprobe":
            return {
                "warning": "Secure Boot is enabled",
                "impact": f"Cannot load unsigned module '{cmd[1]}'",
                "options": [
                    "Disable Secure Boot in BIOS",
                    "Sign the module with MOK (Machine Owner Key)",
                    "Use DKMS with automatic signing",
                ],
            }
    return None
```

---

## Hardware-Gated Options

### In choice resolution

```python
def _resolve_choice(choice, profile):
    for opt in choice["options"]:
        # Check hardware requirements
        hw_req = opt.get("requires", {}).get("hardware", {})
        if hw_req:
            gpu = profile.get("gpu", {})
            if hw_req.get("gpu_vendor") and gpu.get("vendor") != hw_req["gpu_vendor"]:
                opt["available"] = False
                opt["disabled_reason"] = f"Requires {hw_req['gpu_vendor']} GPU"
                opt["enable_hint"] = "This option requires different hardware"

            if hw_req.get("gpu_vendor") == "nvidia" and not gpu.get("has_gpu"):
                opt["available"] = False
                opt["disabled_reason"] = "No NVIDIA GPU detected"
```

---

## Container Awareness

### GPU in containers

```python
# Containers may have GPU access via nvidia-container-toolkit
if profile["in_container"]:
    # Check for GPU device files
    has_gpu_device = Path("/dev/nvidia0").exists()
    has_nvidia_smi = shutil.which("nvidia-smi") is not None

    if has_gpu_device and has_nvidia_smi:
        # GPU available in container
        # Skip driver install — driver is on HOST
        # Only install CUDA toolkit / cuDNN
        pass
    else:
        # No GPU in container
        # Disable all GPU options
        pass
```

---

## Files Touched

| File | Changes |
|------|---------|
| `tool_install.py` | Add detect_gpu(), detect_kernel(), detect_hardware(). Add GPU/kernel recipes to TOOL_RECIPES. |
| `system_detect.py` | Expand fast profile with hardware fields. |
| `routes_audit.py` | Include hardware in system profile response. |

---

## Edge Cases

| Case | Impact | Handling |
|------|--------|---------|
| No lspci binary | Can't detect GPU | Fall back to /proc/driver/nvidia, sysfs |
| GPU in container (passthrough) | nvidia-smi works, no driver install needed | Detect container + GPU device |
| Secure Boot + unsigned module | modprobe fails | Warn user, suggest signing or BIOS change |
| Kernel headers missing | DKMS build fails | Auto-install headers as prerequisite |
| Wayland + NVIDIA | Driver complications | Note in disabled_reason |
| Multiple GPUs | Which to detect? | Report all, user chooses |
| ARM GPU (Mali, etc.) | Different detection | Out of scope (x86/ARM64 NVIDIA/AMD/Intel only) |
| WSL2 GPU | Host driver, guest CUDA | Detect WSL, skip driver install, install toolkit only |
| VM without GPU passthrough | No GPU detected | Disable GPU options cleanly |

---

## Traceability

| Topic | Source |
|-------|--------|
| GPU detection methods | domain-gpu §detection |
| Driver version matrix | domain-gpu §driver matrix |
| CUDA/driver compat table | domain-gpu §CUDA versions |
| Kernel version parsing | domain-kernel §version |
| DKMS workflow | domain-kernel §DKMS |
| Secure Boot detection | domain-kernel §secure boot |
| Hardware profile fields | domain-hardware-detect §profile |
| Risk levels for drivers | domain-risk-levels §high risk |
| Container GPU passthrough | domain-containers §GPU |
| Choice UI for driver version | Phase 4 choice modal |
