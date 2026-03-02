# L3 Detection — System State Readers

> **11 files · 1,670 lines · Read-only system probes.**
>
> Subprocess calls and file reads that return structured dicts.
> Strictly **read-only** — never mutates the system.
> Feeds the resolver (L2), dashboard, and provisioning flows.

---

## How It Works

### Two-Tier Detection Model

```
┌──────────────────────────────────────────────────────────────┐
│ FAST TIER (~120ms)                                            │
│                                                               │
│  Runs on EVERY audit scan. Cached per-scan.                  │
│                                                               │
│  _detect_os() → system profile                               │
│    ├── OS, distro, distro_family, arch                       │
│    ├── Package manager (primary PM, snap_available)          │
│    ├── Container detection (docker, podman, LXC, WSL)        │
│    └── Capabilities (is_root, systemd, init_system)          │
│                                                               │
│  This feeds method selection in L2 Resolver.                 │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ DEEP TIER (~2s)                                               │
│                                                               │
│  Runs on-demand when user enters a provisioning flow.        │
│  Cached per-session (TTL-based).                             │
│                                                               │
│  deep_detect() → comprehensive hardware/network state        │
│    ├── GPU: NVIDIA/AMD/Intel detection, CUDA/ROCm versions   │
│    ├── Hardware: CPU model, RAM, disk, build toolchain        │
│    ├── Kernel: version, headers, DKMS, Secure Boot           │
│    ├── Network: registry reachability, proxy detection        │
│    └── Environment: sandbox, NVM, CPU features               │
│                                                               │
│  This feeds GPU-gated choices and resource checking.         │
└──────────────────────────────────────────────────────────────┘
```

### Detection Orchestration

```
deep_detect(checks=["gpu", "hardware", "kernel", "build", "network", "environment"])
     │
     ├── "gpu"        → detect_gpu() + check_cuda_driver_compat()
     ├── "hardware"   → detect_hardware()
     ├── "kernel"     → detect_kernel()
     ├── "build"      → detect_build_toolchain()
     ├── "network"    → check_all_registries() + detect_proxy() + check_alpine_community_repo()
     └── "environment" → detect_nvm() + detect_sandbox() + detect_cpu_features()

Each category:
  - Runs in a try/except → returns {error: str} on failure
  - Returns a structured dict on success
  - Can be requested individually or all at once
```

---

## File Map

```
detection/
├── __init__.py          63 lines   — re-exports all public + private symbols
├── deep.py             106 lines   — deep-tier orchestrator (runs all probes)
├── hardware.py         446 lines   — GPU, kernel, CPU, RAM, disk, build tools
├── environment.py      219 lines   — sandbox, NVM, CPU features
├── tool_version.py     178 lines   — tool --version parsing for 35+ tools
├── network.py          174 lines   — registry reachability, proxy, Alpine repos
├── system_deps.py      159 lines   — system package installed checks (7 PMs)
├── service_status.py   140 lines   — systemd/init service state, data pack freshness
├── install_failure.py  108 lines   — failed install analysis → remediation
├── condition.py         51 lines   — recipe step condition evaluator
├── recipe_deps.py       26 lines   — recipe system dependency extraction
└── README.md                       — this file
```

---

## Per-File Documentation

### `__init__.py` — Re-exports (63 lines)

Re-exports every public and private symbol from all detection modules.
Allows callers to import from the package root:

```python
from src.core.services.tool_install.detection import detect_gpu, check_system_deps
```

### `deep.py` — Deep Detection Orchestrator (106 lines)

Orchestrates all deep-tier detection modules into a single result dict.
Takes ~2s, called on-demand before provisioning flows.

| Function | What It Does |
|----------|-------------|
| `deep_detect(checks)` | Run selected or all deep detection categories, returns `{gpu: {...}, hardware: {...}, ...}` |

Lazy-imports all detection functions inside the function body to avoid
circular imports and keep the module lightweight.

### `hardware.py` — Hardware Detection (446 lines)

The largest detection module. GPU, kernel, CPU, RAM, disk, and build
toolchain detection.

**GPU detection pipeline:**

```
detect_gpu()
     ├── _lspci_gpu() → parse lspci for VGA/3D controllers
     ├── _nvidia_smi() → NVIDIA driver + CUDA version
     ├── _rocminfo() → AMD ROCm version
     └── _list_gpu_modules() → loaded kernel modules (nvidia, amdgpu, i915)
```

| Function | What It Does |
|----------|-------------|
| `detect_gpu()` | Full GPU detection: vendor, model, driver, CUDA/ROCm, kernel modules |
| `detect_kernel()` | Kernel version, headers, DKMS, Secure Boot, GPU module state |
| `detect_hardware()` | CPU model, RAM total/available, disk free, GPU, kernel (full profile) |
| `detect_build_toolchain()` | GCC, Clang, rustc, Make, CMake, Ninja, Meson, Go, Cargo versions |
| `check_cuda_driver_compat(cuda, driver)` | CUDA/driver version compatibility matrix lookup |
| `_lspci_gpu()` | Parse `lspci` output for GPU info |
| `_nvidia_smi()` | Parse `nvidia-smi` for driver/CUDA version |
| `_rocminfo()` | Parse `rocminfo` for AMD ROCm version |
| `_list_gpu_modules()` | Read `/proc/modules` for loaded GPU kernel modules |
| `_extract_gpu_model(line)` | Extract GPU model name from lspci line |
| `_extract_pci_id(line)` | Extract PCI vendor:device ID from lspci line |
| `_detect_secure_boot()` | Check `mokutil` for Secure Boot state |
| `_read_cpu_model()` | Read CPU model from `/proc/cpuinfo` |
| `_read_total_ram_mb()` | Read total RAM from `/proc/meminfo` |
| `_read_available_ram_mb()` | Read available RAM from `/proc/meminfo` |
| `_read_disk_free_mb(path)` | Read free disk space via `os.statvfs` |

### `environment.py` — Environment Capabilities (219 lines)

Sandbox/confinement detection, version manager detection, CPU features.

| Function | What It Does |
|----------|-------------|
| `detect_sandbox()` | Detect Snap, Flatpak, SELinux, AppArmor, chroot, container confinement |
| `detect_nvm()` | Detect NVM installation, current Node version, available versions |
| `detect_cpu_features()` | Parse `/proc/cpuinfo` for SIMD extensions (SSE, AVX, AVX-512) |

### `tool_version.py` — Tool Version Detection (178 lines)

Runs `tool --version` and parses output with regex patterns.
Covers 35+ tools across pip, npm, cargo, and infrastructure categories.

| Symbol | What It Does |
|--------|-------------|
| `VERSION_COMMANDS` | Dict mapping tool ID → `(command, regex_pattern)` for 35+ tools |
| `get_tool_version(tool)` | Run version command, parse output → version string or `None` |
| `check_updates(tools)` | Check all recipe tools for installed versions, returns status list |
| `_is_linux_binary(path)` | Check if binary is Linux ELF (not a Windows .exe on WSL) |

### `network.py` — Network & Registry Probing (174 lines)

Checks registry reachability, proxy configuration, and Alpine community repos.

| Function | What It Does |
|----------|-------------|
| `check_registry_reachable(registry, timeout)` | HTTP HEAD probe to a registry, returns `{reachable, url, latency_ms}` |
| `check_all_registries(timeout)` | Probe all 5 known registries (pypi, npm, crates, github, dockerhub) |
| `check_alpine_community_repo()` | Check `/etc/apk/repositories` for commented-out community repo |
| `detect_proxy()` | Detect HTTP/HTTPS proxy from env vars + custom CA bundles |

### `system_deps.py` — System Package Detection (159 lines)

Checks whether system packages are installed via the system PM.

| Function | What It Does |
|----------|-------------|
| `check_system_deps(packages, pm)` | Check package list against system PM, returns `{missing, installed}` |
| `_is_pkg_installed(pkg, pm)` | Check one package using apt/dnf/yum/zypper/apk/pacman/brew |
| `_check_brew_batch(packages)` | Batch-check brew packages in a single `brew ls --versions` call |

### `service_status.py` — Service & Data Pack Status (140 lines)

Systemd/init service state and data pack freshness tracking.

| Symbol | What It Does |
|--------|-------------|
| `get_service_status(service)` | Get systemd service state (active, sub-state, loaded) or init fallback |
| `check_data_freshness(pack_id)` | Check if data pack needs updating (timestamp vs schedule TTL) |
| `get_data_pack_usage()` | Report disk usage of known data pack directories |
| `_detect_init_system()` | Detect init system type (systemd, openrc, initd, unknown) |
| `DATA_DIRS` | Dict mapping data pack types → storage paths |
| `DATA_UPDATE_SCHEDULES` | Dict mapping schedule names → TTL seconds |

### `install_failure.py` — Failure Analysis (108 lines)

When a step fails, delegates to the domain remediation layer.

| Function | What It Does |
|----------|-------------|
| `_analyse_install_failure(tool, cli, stderr, ...)` | Parse stderr → structured remediation (delegates to domain layer) |
| `_infer_method(stderr)` | Best-effort method inference from stderr keywords (cargo/pip/npm/apt) |

### `condition.py` — Recipe Condition Evaluator (51 lines)

Evaluates `when:` conditions in recipe steps against the system profile.

| Function | What It Does |
|----------|-------------|
| `_evaluate_condition(condition, profile)` | Evaluate conditions: `has_systemd`, `not_root`, `not_container`, `has_docker`, `file_exists:...` |

Supported conditions:

| Condition | What It Checks |
|-----------|---------------|
| `has_systemd` | `capabilities.systemd` in profile |
| `has_openrc` | `init_system.type == "openrc"` |
| `not_root` | NOT `capabilities.is_root` |
| `is_root` | `capabilities.is_root` |
| `not_container` | NOT `container.in_container` |
| `has_docker` | `shutil.which("docker")` exists |
| `file_exists:<path>` | `os.path.isfile(path)` |

### `recipe_deps.py` — Recipe Dependency Extraction (26 lines)

Extracts system dependency lists from recipe declarations.

| Function | What It Does |
|----------|-------------|
| `_get_system_deps(tool)` | Look up `requires.packages` in TOOL_RECIPES, keyed by distro family |

---

## Dependency Graph

```
__init__.py          ← re-exports from all modules below

deep.py              ← orchestrator: lazy-imports hardware, network, environment
   │
   ├── hardware.py   ← standalone (subprocess, /proc, lspci, nvidia-smi)
   │     └── data/cuda_matrix._CUDA_DRIVER_COMPAT
   │
   ├── network.py    ← standalone (urllib.request, /etc/apk/repositories)
   │
   └── environment.py ← standalone (os, shutil, subprocess, /proc/cpuinfo)

tool_version.py      ← data.recipes.TOOL_RECIPES + resolver.method_selection.get_update_map
system_deps.py       ← standalone (subprocess: dpkg-query, rpm, apk, pacman, brew)
service_status.py    ← data.recipes.TOOL_RECIPES + domain.download_helpers._fmt_size
install_failure.py   ← domain.remediation_planning (build_remediation_response, to_legacy_remediation)
condition.py         ← standalone (shutil, os)
recipe_deps.py       ← data.recipes.TOOL_RECIPES + audit.l0_detection._detect_os
```

---

## Key Data Shapes

### detect_gpu() response

```python
{
    "nvidia": {
        "model": "NVIDIA GeForce RTX 3080",
        "pci_id": "10de:2206",
        "driver_version": "535.183",
        "cuda_version": "12.2",
        "driver_loaded": True,
    },
    "amd": {"model": None},
    "intel": {"model": "Intel UHD Graphics 630"},
    "modules": ["nvidia", "nvidia_uvm", "nvidia_modeset", "i915"],
}
```

### detect_hardware() response

```python
{
    "cpu": "AMD Ryzen 9 5900X 12-Core Processor",
    "ram_total_mb": 32768,
    "ram_available_mb": 24576,
    "disk_free_mb": 120000,
    "gpu": { ... },     # detect_gpu() output
    "kernel": { ... },  # detect_kernel() output
}
```

### check_system_deps() response

```python
{
    "missing": ["libssl-dev", "pkg-config"],
    "installed": ["build-essential"],
}
```

### deep_detect() response

```python
{
    "gpu": { ... },            # detect_gpu() + cuda_driver_compat
    "hardware": { ... },       # detect_hardware()
    "kernel": { ... },         # detect_kernel()
    "build_toolchain": { ... }, # detect_build_toolchain()
    "network": {
        "registries": { ... }, # check_all_registries()
        "proxy": { ... },      # detect_proxy()
        "alpine_community": { ... },  # if Alpine
    },
    "environment": {
        "nvm": { ... },        # detect_nvm()
        "sandbox": { ... },    # detect_sandbox()
        "cpu_features": { ... }, # detect_cpu_features()
    },
}
```

---

## Design Decisions

### Why separate deep.py from the individual detection modules?

`deep_detect()` is the entry point for the provisioning UI — it runs
all deep checks in one call and returns a unified result. The individual
modules (`hardware.py`, `network.py`, `environment.py`) are used
independently by the resolver and step executors. The orchestrator
lazy-imports everything to keep the detection module bootstrappable
even if optional system tools are missing.

### Why _is_linux_binary() exists

On WSL (Windows Subsystem for Linux), `shutil.which()` can find
Windows `.exe` files via the interop PATH. When the tool installer
detects a binary, it needs to verify it's actually a Linux ELF
executable, not a Windows PE binary. The function reads the first
4 bytes and checks for the ELF magic number (`\x7fELF`).

### Why _check_brew_batch() is separate

Homebrew's `brew ls --versions` can check multiple packages in a
single call, which is significantly faster than calling it N times.
The batch optimization is transparently used when `pkg_manager == "brew"`
and there are multiple packages to check.

### Why conditions are evaluated in detection, not domain

Conditions like `has_systemd` and `not_container` require reading
system state — checking `/run/systemd/system`, reading env vars,
running `shutil.which()`. This is detection behavior, not pure
domain logic. Domain logic (risk, DAG, validation) operates on
already-detected state.

### Why install_failure delegates to domain

`_analyse_install_failure` is a thin adapter: it calls
`build_remediation_response()` from the domain layer, which
evaluates all registered handlers against the stderr output.
This keeps the detection layer read-only (it reads stderr) while
the domain layer contains the pure matching logic.

---

## Advanced Feature Showcase

### 1. Multi-Vendor GPU Detection with CUDA Compatibility Matrix

```python
# hardware.py — detect_gpu() orchestrates vendor-specific probes
gpu_info = detect_gpu()
# {
#     "nvidia": {"model": "RTX 3080", "driver_version": "535.183",
#                "cuda_version": "12.2", "driver_loaded": True},
#     "amd": {"model": None},
#     "intel": {"model": "UHD 630"},
#     "modules": ["nvidia", "nvidia_uvm"]
# }

# Then deep.py auto-checks CUDA/driver compat when both are present:
if nvidia.get("cuda_version") and nvidia.get("driver_version"):
    compat = check_cuda_driver_compat(
        nvidia["cuda_version"], nvidia["driver_version"]
    )
    # → {"compatible": True} or
    # → {"compatible": False, "min_driver": "520.61", "message": "..."}
```

### 2. WSL Binary Filtering

```python
# tool_version.py — _is_linux_binary() prevents WSL false positives
#
# On WSL, shutil.which("docker") might find docker.exe from Windows.
# Before reporting a tool as installed, we check the ELF magic:
def _is_linux_binary(path: str) -> bool:
    if "microsoft" not in platform.release().lower():
        return True  # Not WSL → always a Linux binary
    try:
        with open(path, "rb") as f:
            magic = f.read(4)
        return magic == b"\x7fELF"  # ELF magic number
    except (OSError, PermissionError):
        return True  # Can't read → assume Linux
```

### 3. Brew Batch Optimization

```python
# system_deps.py — single brew call instead of N individual calls
#
# Instead of running `brew ls --versions pkg` N times:
cmd = ["brew", "ls", "--versions"] + list(packages)  # One call
r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
# Parse output: each line is "pkgname version(s)"
# Missing packages produce no output line
```

### 4. Version Command Registry (35+ tools)

```python
# tool_version.py — VERSION_COMMANDS covers 35+ tools with regex parsing
VERSION_COMMANDS = {
    "ruff":         (["ruff", "--version"],           r"ruff\s+(\d+\.\d+\.\d+)"),
    "docker":       (["docker", "--version"],          r"Docker version\s+(\d+\.\d+\.\d+)"),
    "kubectl":      (["kubectl", "version", "--client=true"], r"v(\d+\.\d+\.\d+)"),
    # ... 32 more entries
}
# Falls back to recipe's version_command/version_pattern if tool not in table
```

### 5. Sandbox Confinement Detection (6 isolation types)

```python
# environment.py — detect_sandbox() checks 6 isolation mechanisms
# Snap confinement → os.environ["SNAP"] + SNAP_CONFINEMENT
# Flatpak sandbox → os.environ["FLATPAK_ID"]
# SELinux → getenforce command
# AppArmor → /sys/module/apparmor/parameters/enabled
# chroot → os.stat("/").st_ino != 2
# Container → checked elsewhere (fast tier)
```

### 6. Multi-PM Package Checking (7 package managers)

```python
# system_deps.py — _is_pkg_installed supports 7 binary PMs
# apt    → dpkg-query -W -f='${Status}' PKG
# dnf    → rpm -q PKG
# yum    → rpm -q PKG
# zypper → rpm -q PKG
# apk    → apk info -e PKG
# pacman → pacman -Q PKG
# brew   → brew ls --versions PKG (batch-optimized)
```

### 7. Alpine Community Repo Detection

```python
# network.py — check_alpine_community_repo()
# In Alpine containers, community packages (python3, build-base) may be
# unavailable because the community repo is commented out.
# Reads /etc/apk/repositories and checks for commented lines:
# → {"is_alpine": True, "community_enabled": False,
#    "commented_line": "#http://...", "fix_hint": "Uncomment and run apk update"}
```

### 8. Deep Detection with Selective Categories

```python
# deep.py — run only the checks you need
result = deep_detect(checks=["gpu", "network"])
# Only GPU + network probes run (~1s instead of ~2s)
#
# Or run everything:
result = deep_detect()
# All 6 categories: gpu, hardware, kernel, build, network, environment
```

---

## Coverage Summary

| Capability | File | Tools/Items Covered |
|-----------|------|-------------------|
| GPU detection | `hardware.py` | NVIDIA (nvidia-smi), AMD (rocminfo), Intel (lspci) |
| Kernel analysis | `hardware.py` | Version, headers, DKMS, Secure Boot, GPU modules |
| Tool versions | `tool_version.py` | 35+ tools: ruff, docker, kubectl, helm, terraform, go, node, cargo, etc. |
| System packages | `system_deps.py` | 7 PMs: apt, dnf, yum, zypper, apk, pacman, brew |
| Registries | `network.py` | 5 registries: PyPI, npm, crates.io, GitHub API, Docker Hub |
| Sandbox types | `environment.py` | 6 types: Snap, Flatpak, SELinux, AppArmor, chroot, container |
| Init systems | `service_status.py` | 3 types: systemd, openrc, initd |
| Conditions | `condition.py` | 7 conditions: has_systemd, has_openrc, not_root, is_root, not_container, has_docker, file_exists |
| CPU features | `environment.py` | SSE, SSE2, AVX, AVX2, AVX-512, VMX, SVM, AES |
| Method inference | `install_failure.py` | 7 methods: cargo, pip, npm, apt, dnf, snap, brew |
