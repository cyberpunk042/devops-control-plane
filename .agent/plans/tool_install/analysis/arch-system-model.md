# Architecture: System Model

> ⚠️ **PHASE LABELS MAY BE STALE** — As of 2026-02-25, code has evolved far beyond
> what the phase roadmaps suggest. Many features labeled "Phase 4-8 future" are
> ALREADY IMPLEMENTED. See `audit-domain-docs.md` and `audit-missing-pieces.md`
> for the verified truth. Code is the source of truth, not these phase labels.


> This document defines the COMPLETE schema of the system profile —
> every field, its type, how it's detected, which tier it belongs to,
> and which phases consume it.
>
> This is the INPUT CONTRACT for the resolver. Every decision the
> resolver makes about what to install and how is based on the data
> defined here. If a field doesn't exist in this model, the resolver
> can't use it.
>
> Obeys: arch-principles §9 (two-tier detection), §6 (extensibility)

---

## Overview

The system profile is a dict returned by `_detect_os()` in
`l0_detection.py`. It flows through:

```
_detect_os()
  → l0_system_profile(root)   # wraps _detect_os() + tool scan + module scan
    → cache["audit:system"]    # cached in memory, invalidated per scan
      → /api/audit/system      # served as JSON to frontend
        → audit card           # rendered in System Profile card
        → resolver             # input for install plan generation
```

The profile is a SINGLE dict. All consumers read from the same dict.
Adding a new field to the dict is safe — existing consumers ignore
fields they don't know about (Principle §6: extensibility by addition).

---

## Tier Model

Detection runs in TWO tiers (Principle §9):

| Tier | Budget | When | Cache |
|------|--------|------|-------|
| **Fast** | <200ms | Every L0 audit scan | In-memory, per scan |
| **Deep** | <2s | On demand (install modal opened) | Session-scoped, with TTL |

Fast tier detections use ONLY:
- File reads (/etc/os-release, /proc/version, /proc/1/cgroup)
- `shutil.which()` calls
- `os.getuid()`, `os.environ` reads
- A few subprocesses with timeout=5s (systemctl, sudo -n, openssl)

Deep tier detections may use:
- Expensive subprocesses (lspci, nvidia-smi, lsmod, df)
- Network probes (curl with timeout)
- Multiple sequential subprocesses

---

## Fast Tier: Complete Schema (Phase 1 — IMPLEMENTED)

This is what `_detect_os()` returns TODAY in production code.

```python
{
    # ── OS basics ─────────────────────────────────────────────
    "system": str,           # "Linux" | "Darwin" | "Windows"
    "release": str,          # kernel release string
    "machine": str,          # raw machine type: "x86_64", "aarch64"

    # ── Normalized architecture ───────────────────────────────
    "arch": str,             # "amd64" | "arm64" | "armv7" | raw
                             # x86_64→amd64, aarch64/arm64→arm64

    # ── Distro identity ───────────────────────────────────────
    "distro": {
        "id": str,           # "ubuntu", "fedora", "alpine", "macos"
                             # from ID in /etc/os-release (lowercase)
        "name": str,         # "Ubuntu 20.04.6 LTS" (PRETTY_NAME)
        "version": str,      # "20.04", "39", "3.19" (VERSION_ID)
        "version_tuple": list[int],  # [20, 4] — parsed for comparison
        "family": str,       # "debian" | "rhel" | "alpine" | "arch"
                             # | "suse" | "macos" | "unknown"
                             # Derived from ID or ID_LIKE
        "codename": str | None,  # "focal", "bookworm", None
    },

    # ── WSL ───────────────────────────────────────────────────
    "wsl": bool,             # /proc/version contains "microsoft"
    "wsl_version": int | None,  # 1 or 2 (kernel string has "WSL2")

    # ── Container environment ─────────────────────────────────
    "container": {
        "in_container": bool,    # any container signal detected
        "runtime": str | None,   # "docker" | "containerd" | "podman" | None
        "in_k8s": bool,          # kubepods in cgroup OR KUBERNETES_SERVICE_HOST
    },

    # ── System capabilities ───────────────────────────────────
    "capabilities": {
        "has_systemd": bool,        # systemctl exists AND state is running|degraded
        "systemd_state": str | None,  # "running" | "degraded" | "offline" | None
        "has_sudo": bool,           # sudo binary exists
        "passwordless_sudo": bool,  # sudo -n true returns 0
        "is_root": bool,            # os.getuid() == 0
    },

    # ── Package managers ──────────────────────────────────────
    "package_manager": {
        "primary": str,          # first available: "apt"|"dnf"|"yum"|"apk"
                                 # |"pacman"|"zypper"|"brew"|"none"
        "available": list[str],  # all detected PMs
        "snap_available": bool,  # snap binary exists AND has_systemd
    },

    # ── Library versions ──────────────────────────────────────
    "libraries": {
        "openssl_version": str | None,  # "3.6.1" from `openssl version`
        "glibc_version": str | None,    # "2.31" from ctypes or ldd
        "libc_type": str,               # "glibc" | "musl" | "unknown"
    },
}
```

### Detection methods (fast tier)

| Field | Method | Latency |
|-------|--------|---------|
| system, release, machine | `platform.system()`, `.release()`, `.machine()` | <1ms |
| arch | Lookup table from machine | <1ms |
| distro | Parse `/etc/os-release` (Linux) or `platform.mac_ver()` (macOS) | <1ms |
| distro.family | Lookup table from distro.id → family, fallback to ID_LIKE | <1ms |
| wsl, wsl_version | Read `/proc/version`, check for "microsoft"/"WSL2" | <1ms |
| container | Read `/.dockerenv`, `/proc/1/cgroup`, `/proc/1/environ`, `$KUBERNETES_SERVICE_HOST` | <2ms |
| capabilities.has_systemd | `shutil.which("systemctl")` + `systemctl is-system-running` | ~50ms |
| capabilities.has_sudo | `shutil.which("sudo")` | <1ms |
| capabilities.passwordless_sudo | `sudo -n true` | ~50ms |
| capabilities.is_root | `os.getuid() == 0` | <1ms |
| package_manager | `shutil.which()` for each PM binary, priority order | ~5ms |
| libraries.openssl_version | `openssl version` | ~10ms |
| libraries.glibc_version | `ctypes.CDLL("libc.so.6")` or `ldd --version` fallback | ~1ms |

**Total fast tier: ~120ms worst case.**

### Family mapping

| distro.id | distro.family | Package naming |
|-----------|--------------|----------------|
| ubuntu, debian, linuxmint, pop, kali, raspbian | debian | libfoo-dev |
| fedora, centos, rhel, rocky, almalinux, amzn | rhel | foo-devel |
| alpine | alpine | foo-dev |
| arch, manjaro, endeavouros | arch | foo |
| opensuse-leap, opensuse-tumbleweed, sles | suse | foo-devel |
| macos | macos | via brew formula name |

### Package manager priority

Detection order (first found = primary):
```
apt-get → dnf → yum → apk → pacman → zypper → brew
```

Snap is special: detected separately, requires systemd.

### macOS specifics

On macOS the following fields behave differently:
- `distro.id` = "macos", `distro.family` = "macos"
- `distro.version` from `platform.mac_ver()` (e.g., "14.2.1")
- `wsl` = False (no /proc/version)
- `container.in_container` = False (only env var detection works)
- `capabilities.has_systemd` = False (macOS uses launchd)
- `package_manager.primary` = "brew" (if installed) or "none"
- `libraries.libc_type` = "system" (Apple's libSystem, not glibc/musl)

---

## Deep Tier: Schema (Phases 4-8 — IMPLEMENTED)

These fields are part of the system profile, served via `?deep=true`.
Each section notes which phase it belongs to and what triggers detection.

### Shell environment (Phase 4)

Triggered when: resolver needs to write profile files (post_env steps)
or detect broken PATH.

```python
"shell": {
    "type": str,                 # "bash" | "zsh" | "fish" | "sh" | "dash"
                                 # from basename($SHELL)
    "version": str | None,       # from $SHELL --version
    "login_profile": str,        # "~/.bash_profile" | "~/.zprofile" | ...
    "rc_file": str,              # "~/.bashrc" | "~/.zshrc" | "~/.config/fish/config.fish"
    "path_healthy": bool,        # login shell PATH matches non-login
    "path_login": str,           # PATH from: bash -l -c "echo $PATH"
    "path_nonlogin": str,        # PATH from: bash -c "echo $PATH"
    "restricted": bool,          # rbash or other restricted shell detected
}
```

Detection methods:
- `$SHELL` env var → shell type → profile/rc file mapping
- `$SHELL --version` → version string
- `subprocess.run(["bash", "-l", "-c", "echo $PATH"])` vs
  `subprocess.run(["bash", "-c", "echo $PATH"])` → PATH health
- `$SHELL` endswith `rbash` or `$SHELL` is in restricted list → restricted

### Init system (Phase 4)

Triggered when: resolver needs service management beyond systemd.

```python
"init_system": {
    "type": str,             # "systemd" | "openrc" | "initd" | "launchd" | "none"
    "service_manager": str,  # "systemctl" | "rc-service" | "service" | "launchctl"
    "can_enable": bool,      # can services be enabled at boot?
    "can_start": bool,       # can services be started?
}
```

Detection: `shutil.which()` for systemctl, rc-status, launchctl, service.
Priority: systemd > OpenRC > init.d > launchd > none.

### Network connectivity (Phase 4)

Triggered when: resolver needs to know if remote installs will work.

```python
"network": {
    "online": bool,              # at least one endpoint reachable
    "proxy_detected": bool,      # HTTP_PROXY or HTTPS_PROXY set
    "proxy_url": str | None,     # value of HTTPS_PROXY or HTTP_PROXY
    "endpoints": {
        "pypi.org": {
            "reachable": bool,
            "latency_ms": int | None,
            "error": str | None,     # "timeout" | "dns" | "refused" | None
        },
        "github.com": { ... },
        "registry.npmjs.org": { ... },
    },
}
```

Detection: `curl -s --connect-timeout 3 -o /dev/null -w "%{http_code}"`.
Each endpoint tested independently. Runs in parallel (threads or async).

### Build toolchain (Phase 5)

Triggered when: recipe has `install_method: "source"` as an option.

```python
"build": {
    "compilers": {
        "gcc": {"available": bool, "version": str | None},
        "g++": {"available": bool, "version": str | None},
        "clang": {"available": bool, "version": str | None},
        "rustc": {"available": bool, "version": str | None},
    },
    "build_tools": {
        "make": bool,        # shutil.which("make")
        "cmake": bool,       # shutil.which("cmake")
        "ninja": bool,       # shutil.which("ninja")
        "meson": bool,       # shutil.which("meson")
        "autoconf": bool,    # shutil.which("autoconf")
    },
    "dev_packages_installed": bool,  # build-essential (debian) or equiv
    "cpu_cores": int,                # os.cpu_count()
    "disk_free_gb": float,           # shutil.disk_usage("/").free / 1e9
    "tmp_free_gb": float,            # shutil.disk_usage("/tmp").free / 1e9
    "gcc_is_clang_alias": bool,      # macOS: gcc is actually Apple Clang
}
```

Detection: `shutil.which()` for each, `gcc --version` for versions.
`shutil.disk_usage()` for disk space. `os.cpu_count()` for cores.

### GPU hardware (Phase 6)

Triggered when: recipe has GPU-related choices (CUDA, ROCm, OpenCL).

```python
"gpu": {
    "nvidia": {
        "present": bool,             # lspci shows NVIDIA device
        "model": str | None,         # "RTX 4090", "Tesla V100"
        "driver_version": str | None,  # "535.129.03" from nvidia-smi
        "cuda_version": str | None,    # "12.2" from nvidia-smi
        "nvcc_version": str | None,    # "12.4" from nvcc --version (toolkit)
        "compute_capability": str | None,  # "8.9"
        "cudnn_version": str | None,       # "8.9.7" — parsed from cudnn.h or ldconfig
        "cudnn_path": str | None,          # "/usr/include/cudnn.h"
    },
    "amd": {
        "present": bool,             # lspci shows AMD GPU
        "model": str | None,
        "rocm_version": str | None,  # from rocm-smi or /opt/rocm/.info/version
    },
    "intel": {
        "present": bool,             # lspci shows Intel GPU
        "model": str | None,
        "opencl_available": bool,    # clinfo shows Intel platform
    },
}
```

Detection:
- `lspci | grep -i "vga\|3d\|display"` → identify GPU vendor and model
- `nvidia-smi --query-gpu=name,driver_version,compute_cap --format=csv`
- `nvidia-smi` output header contains CUDA version
- `nvcc --version` → CUDA toolkit version
- `rocm-smi` or `/opt/rocm/.info/version` → ROCm version
- `clinfo` for OpenCL platforms (optional, may not be installed)

### Kernel state (Phase 6)

Triggered when: recipe involves kernel modules or kernel config.

```python
"kernel": {
    "version": str,              # uname -r (already available as "release")
    "config_available": bool,    # /boot/config-$(uname -r) exists
    "config_path": str | None,   # path to kernel config file
    "loaded_modules": list[str], # from lsmod (module names only)
    "module_check": {            # specific modules checked on demand
        "vfio_pci": {
            "loaded": bool,      # in loaded_modules
            "compiled": bool,    # .ko file exists in /lib/modules/
            "config_state": str | None,  # "y" (built-in), "m" (module), "n" (disabled), None
        },
        # ... other modules checked as needed by recipe
    },
    "iommu_groups": list[dict] | None,  # from /sys/kernel/iommu_groups/
    "headers_installed": bool,       # linux-headers-$(uname -r) present
    "dkms_available": bool,          # dkms binary on PATH
    "secure_boot": bool | None,      # SecureBoot state (None = unknown)
}
```

Detection:
- `lsmod` → parse loaded module names
- `find /lib/modules/$(uname -r) -name "MODULE.ko*"` → compiled modules
- `grep CONFIG_NAME /boot/config-$(uname -r)` → config state
- `/sys/kernel/iommu_groups/*/devices/*` → IOMMU group listing

### WSL interop (Phase 6)

Triggered when: recipe involves WSL-specific operations.

```python
"wsl_interop": {
    "available": bool,           # powershell.exe is on PATH
    "binfmt_registered": bool,   # /proc/sys/fs/binfmt_misc/WSLInterop exists
    "windows_user": str | None,  # from cmd.exe /c "echo %USERNAME%"
    "wslconfig_path": str | None,  # C:\Users\USER\.wslconfig (if detectable)
}
```

Detection: `shutil.which("powershell.exe")`, file existence checks.

### System services (Phase 8)

Triggered when: recipe involves service configuration or log management.

```python
"services": {
    "journald": {
        "active": bool,          # systemctl is-active systemd-journald
        "disk_usage": str | None,  # from journalctl --disk-usage
    },
    "logrotate_installed": bool,  # shutil.which("logrotate")
    "cron_available": bool,       # shutil.which("crontab")
}
```

### Filesystem and security (Phase 8)

Triggered when: recipe involves filesystem-dependent choices or
security context affects installation.

```python
"filesystem": {
    "root_type": str,            # "ext4" | "btrfs" | "xfs" | "zfs" | ...
                                 # from df -T / (second column)
    "root_free_gb": float,       # from shutil.disk_usage("/")
},

"security": {
    "selinux": {
        "installed": bool,       # shutil.which("getenforce")
        "mode": str | None,      # "Enforcing" | "Permissive" | "Disabled"
    },
    "apparmor": {
        "installed": bool,       # /sys/kernel/security/apparmor/ exists
        "profiles_loaded": bool, # directory is non-empty
    },
}
```

---

## Data Flow

### Current flow (fast tier only)

```
l0_detection.py::_detect_os()
  ↓ returns dict
l0_detection.py::l0_system_profile(root)
  ↓ wraps in {"os": detect_os(), "tools": [...], "modules": [...]}
routes_devops.py::reg("audit:system", ...)
  ↓ cached in data_cache
routes_audit.py::/api/audit/system
  ↓ served as JSON
_audit_cards_a.html
  ↓ renders in System Profile card
```

### Future flow (fast + deep tiers)

```
l0_detection.py::_detect_os()
  ↓ returns fast tier dict (always, <200ms)
l0_detection.py::_detect_deep_profile(fast_profile)
  ↓ returns deep tier dict (on demand, <2s, cached)
l0_detection.py::l0_system_profile(root, deep=False)
  ↓ if deep: merge fast + deep tiers
  ↓ wraps in {"os": {...}, "tools": [...], "modules": [...]}
routes_audit.py::/api/audit/system?deep=true
  ↓ triggers deep scan if ?deep=true
resolver::resolve_install_plan(tool, system_profile)
  ↓ may request deep tier if recipe needs GPU/kernel/build
```

### Cache strategy

| Tier | Cache location | TTL | Invalidation |
|------|---------------|-----|--------------|
| Fast | In-memory (data_cache["audit:system"]) | Per scan (explicit bust) | `?bust` param, after install |
| Deep | In-memory + session storage (frontend) | 5 minutes | Manual re-scan, after hardware change |

---

## Extensibility Rules

1. **Adding a new field**: Add to the dict at the appropriate tier.
   No existing consumer breaks — they don't read unknown keys.

2. **Adding a new tier level**: Not planned. Two tiers (fast/deep)
   cover all known use cases. If a detection is faster than deep
   but slower than fast, it goes in deep.

3. **Platform-specific fields**: Fields that only exist on certain
   platforms use `None` or `False` defaults. Example: `wsl_version`
   is `None` on non-WSL systems. Consumers MUST handle None.

4. **Recipe-driven detection**: The deep tier can be SELECTIVE.
   If a recipe only needs GPU, don't also scan kernel config.
   The `_detect_deep_profile()` function will accept a `needs` param:
   ```python
   _detect_deep_profile(fast_profile, needs=["gpu", "build"])
   ```
   This runs only the requested sub-detections.

---

## Consumers

| Consumer | Tier needed | Fields used |
|----------|------------|-------------|
| System Profile audit card | Fast | All fast-tier fields |
| L0 tool availability check | Fast | package_manager.primary |
| Phase 2 resolver (simple tools) | Fast | distro.family, pm.primary, pm.snap_available, caps.*, arch |
| Phase 4 resolver (choices) | Fast + Deep | + shell, network, init_system |
| Phase 5 resolver (build-from-source) | Fast + Deep | + build.*, disk |
| Phase 6 resolver (GPU/kernel) | Fast + Deep | + gpu, kernel, wsl_interop |
| Phase 8 resolver (config) | Fast + Deep | + services, filesystem, security |
| Scorer | Fast | os.distro, tools count |
| Frontend install modal | Fast | pm, caps (for step display) |
| Assistant panel | Fast + Deep | Everything — explains disabled options |

---

## Traceability

| Field group | Defined in | Implemented in | First consumer |
|-------------|-----------|---------------|----------------|
| OS basics | phase1 §1 | l0_detection.py (done) | Audit card |
| distro | phase1 §3.2 | l0_detection.py (done) | Resolver, card |
| wsl | phase1 §3.3 | l0_detection.py (done) | Card |
| container | phase1 §3.4 | l0_detection.py (done) | Resolver |
| capabilities | phase1 §3.5 | l0_detection.py (done) | Resolver |
| package_manager | phase1 §3.6 | l0_detection.py (done) | Resolver |
| libraries | phase1 §3.7 | l0_detection.py (done) | Resolver |
| shell | phase1 §10 / P4 | l0_detection.py (done) | Resolver |
| init_system | phase1 §10 / P4 | l0_detection.py (done) | Resolver |
| network | scope-expansion §2.16 | l0_detection.py (done) | Phase 4 resolver |
| build | phase1 §10 / P5 | l0_detection.py (done) | Phase 5 resolver |
| gpu | scope-expansion §2.9 | l0_detection.py (done) | Resolver |
| kernel | phase1 §10 / P6 | l0_detection.py (done) | Resolver |
| wsl_interop | phase1 §10 / P6 | l0_detection.py (done) | Phase 6 resolver |
| services | phase1 §10 / P8 | l0_detection.py (done) | Phase 8 resolver |
| filesystem | phase1 §10 / P8 | l0_detection.py (done) | Resolver |
| security | phase1 §10 / P8 | l0_detection.py (done) | Resolver |
