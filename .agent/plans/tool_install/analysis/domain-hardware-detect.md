# Domain: Hardware Detection

> ⚠️ **PHASE LABELS MAY BE STALE** — As of 2026-02-25, code has evolved far beyond
> what the phase roadmaps suggest. Many features labeled "Phase 4-8 future" are
> ALREADY IMPLEMENTED. See `audit-domain-docs.md` and `audit-missing-pieces.md`
> for the verified truth. Code is the source of truth, not these phase labels.


> This document catalogs general hardware detection relevant to
> tool installation: CPU architecture and features, RAM, disk space,
> network interfaces, and IOMMU groups. What hardware properties
> matter for installation decisions and build tuning.
>
> SOURCE DOCS: arch-system-model §Fast profile (arch, machine),
>              arch-system-model §Build environment (cpu_cores, disk),
>              arch-system-model §Kernel state (iommu_groups),
>              scope-expansion §Phase 6 (hardware detection),
>              domain-build-from-source §disk space requirements,
>              domain-compilers §libc detection

---

## Overview

Hardware detection answers three questions for tool installation:

1. **What architecture am I on?** — Determines binary downloads,
   package availability, build targets.
2. **Do I have enough resources?** — CPU cores, RAM, disk space
   determine build parallelism and whether builds can proceed.
3. **What special hardware is present?** — GPU (covered in domain-gpu),
   IOMMU groups (for passthrough), network interfaces.

### Tiered detection

| Tier | Hardware info | When collected | Phase |
|------|-------------|----------------|-------|
| Fast | arch, machine, cpu_count | Every scan | Phase 2 |
| Build | cpu_cores, disk_free_gb, tmp_free_gb | Before builds | Phase 5 |
| Deep | GPU, IOMMU, CPU features, network | On demand | Phase 6 |

---

## CPU Architecture

### Detection

```python
import platform

machine = platform.machine()  # "x86_64", "aarch64", "armv7l"
system = platform.system()    # "Linux", "Darwin", "Windows"
```

### Architecture normalization

The system normalizes raw machine strings to consistent IDs:

| Raw value | Normalized | Notes |
|-----------|-----------|-------|
| `x86_64` | `amd64` | Standard 64-bit Intel/AMD |
| `AMD64` | `amd64` | Windows reports this |
| `aarch64` | `arm64` | Linux ARM 64-bit |
| `arm64` | `arm64` | macOS ARM (Apple Silicon) |
| `armv7l` | `armv7` | 32-bit ARM (Raspberry Pi) |
| `i686` | `i386` | 32-bit x86 (rare) |
| Other | Raw value | Pass through unchanged |

```python
_ARCH_MAP = {
    "x86_64": "amd64",
    "AMD64": "amd64",
    "aarch64": "arm64",
    "arm64": "arm64",
    "armv7l": "armv7",
    "i686": "i386",
}
arch = _ARCH_MAP.get(machine, machine)
```

### Why architecture matters

| System component | How arch affects it |
|-----------------|--------------------| 
| Binary downloads | URL contains arch: `kubectl-linux-amd64` vs `kubectl-linux-arm64` |
| System packages | Same package name, different arch behind the scenes |
| pip wheels | `manylinux_x86_64` vs `manylinux_aarch64` |
| cargo install | Compiles for current arch (transparent) |
| Docker images | Multi-arch manifests handle it |
| snap | Auto-selects correct arch |

### Phase 2 limitation

Binary download URLs are currently HARDCODED to `amd64`:
```python
# kubectl recipe (Phase 2 — hardcoded)
"curl -LO https://dl.k8s.io/release/.../{arch}/kubectl"
# {arch} is NOT interpolated — it's literal "amd64"
```

Phase 4+ architecture interpolation in URLs IS IMPLEMENTED.
See `_render_template()` in `tool_install.py`.

---

## CPU Features

### What CPU features matter

| Feature | What it is | When relevant |
|---------|-----------|---------------|
| AVX | Advanced Vector Extensions | ML frameworks, scientific computing |
| AVX2 | AVX version 2 | Optimized TensorFlow builds |
| AVX-512 | 512-bit vector operations | HPC, Intel Xeon |
| SSE4.2 | Streaming SIMD Extensions | General optimization |
| AES-NI | Hardware AES encryption | Cryptographic tools |
| FMA | Fused Multiply-Add | ML training performance |

### Detection

```bash
# Check CPU flags
grep -o 'avx\|avx2\|avx512\|sse4_2\|aes\|fma' /proc/cpuinfo | sort -u
```

```python
# Python detection
def _detect_cpu_features() -> list[str]:
    """Read CPU feature flags from /proc/cpuinfo."""
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("flags"):
                    flags = line.split(":")[1].strip().split()
                    return [f for f in flags if f in
                            {"avx", "avx2", "avx512f", "sse4_2",
                             "aes", "fma"}]
    except FileNotFoundError:
        pass  # macOS, container without /proc
    return []
```

### macOS CPU features

macOS doesn't have `/proc/cpuinfo`:
```bash
sysctl -a | grep machdep.cpu.features
# machdep.cpu.features: FPU VME ... SSE4.2 ... AVX2
```

### Phase 6 schema

```python
"cpu": {
    "arch": "amd64",
    "cores": 8,
    "model": "Intel(R) Core(TM) i7-12700K",
    "features": ["avx", "avx2", "sse4_2", "aes", "fma"],
}
```

### Impact on tool installation

| Scenario | CPU feature needed | Impact |
|----------|-------------------|--------|
| TensorFlow pre-built | AVX | TF binary crashes without AVX |
| TF from source | AVX2 (optional) | Faster training if available |
| OpenSSL | AES-NI (optional) | 10x faster encryption |
| MongoDB | AVX (since 5.0) | Won't start without AVX |

**Phase 2:** CPU features ARE NOW DETECTED via `detect_cpu_features()` in `detection/environment.py`.
None of the 30 tools have CPU feature requirements.

---

## RAM

### Detection

```python
import os

# Total RAM (bytes)
total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
total_gb = total / (1024**3)

# Available RAM (Linux)
with open("/proc/meminfo") as f:
    for line in f:
        if line.startswith("MemAvailable:"):
            available_kb = int(line.split()[1])
            available_gb = available_kb / (1024**2)

# Or via psutil (if available)
import psutil
mem = psutil.virtual_memory()
total_gb = mem.total / (1024**3)
available_gb = mem.available / (1024**3)
```

### macOS RAM

```bash
sysctl hw.memsize
# hw.memsize: 17179869184  (16 GB)
```

### Why RAM matters

| Component | RAM impact |
|-----------|-----------|
| Build parallelism (`-j`) | Each gcc process uses ~200-400 MB |
| cargo install | Rust compilation is memory-hungry (~500 MB per process) |
| pip wheel builds | Native extensions need compiler RAM |
| System stability | OS needs ~500 MB minimum free |

### Recommended `-j` based on RAM

| Available RAM | Safe `-j` | Reasoning |
|--------------|-----------|-----------|
| < 1 GB | 1 | Avoid OOM killer |
| 1-2 GB | 2 | 500 MB per process |
| 2-4 GB | 4 | Comfortable |
| 4-8 GB | min(cores, 8) | RAM not the bottleneck |
| 8+ GB | cores | Full parallel |

### Phase 5 schema

```python
"resources": {
    "cpu_cores": int,         # os.cpu_count()
    "ram_total_gb": float,
    "ram_available_gb": float,
    "disk_free_gb": float,    # shutil.disk_usage("/").free / 1e9
    "tmp_free_gb": float,     # shutil.disk_usage("/tmp").free / 1e9
}
```

---

## Disk Space

### Detection

```python
import shutil

# Root filesystem
usage = shutil.disk_usage("/")
free_gb = usage.free / (1024**3)

# /tmp (may be tmpfs — different from root)
tmp_usage = shutil.disk_usage("/tmp")
tmp_free_gb = tmp_usage.free / (1024**3)

# Home directory (for user-space installs)
home_usage = shutil.disk_usage(os.path.expanduser("~"))
home_free_gb = home_usage.free / (1024**3)
```

### Why disk space matters

| Operation | Disk needed | Filesystem |
|-----------|-----------|-----------|
| System package install | 10-500 MB | `/` |
| pip install | 10-2000 MB | `/` or `~/.local/` or venv |
| cargo install | 200-500 MB (temp) | `~/.cargo/` |
| Source build (OpenCV) | 2-5 GB (temp) | `/tmp` or build dir |
| Source build (kernel) | 5-7 GB (temp) | `/usr/src/` |
| CUDA toolkit | 1.5-3 GB | `/usr/local/cuda/` |
| Docker images | 100 MB - 5 GB each | `/var/lib/docker/` |
| snap packages | 50-500 MB each | `/snap/` |

### Pre-install check

```python
def _check_disk_space(required_gb: float, path: str = "/") -> bool:
    """Check if enough disk space is available."""
    usage = shutil.disk_usage(path)
    free_gb = usage.free / (1024**3)
    return free_gb >= required_gb
```

### Container disk space

In containers, disk space depends on:
- Docker storage driver (overlay2, btrfs)
- Docker daemon `--storage-opt dm.basesize` limit
- Kubernetes `ephemeral-storage` resource limits

```python
# Container may show host disk space via shutil.disk_usage
# This can be MISLEADING — actual limit may be lower
# No reliable way to detect container storage limits from inside
```

### Tmpfs (/tmp)

On many systems, `/tmp` is a tmpfs (in-memory filesystem):
```bash
df -h /tmp
# tmpfs    2.0G  0  2.0G  0% /tmp
```

If `/tmp` is tmpfs:
- Size is limited to half of RAM by default
- Large builds need a different build directory
- Recipe should use `--tmpdir` or `TMPDIR` override

---

## Network Interfaces

### Detection

```bash
# List interfaces
ip link show
# OR:
ls /sys/class/net/

# Interface details
ip addr show eth0
```

```python
import socket

# Hostname
hostname = socket.gethostname()

# All interfaces (Python 3.3+)
import netifaces  # optional dep
interfaces = netifaces.interfaces()
```

### Why network matters

| Scenario | Network requirement |
|----------|-------------------|
| Package download | Internet connectivity |
| pip/npm/cargo install | Registry reachable |
| Proxy environments | HTTP_PROXY/HTTPS_PROXY configured |
| Air-gapped | No internet — need local repos/mirrors |
| Docker pull | Docker registry reachable |

### Connectivity testing

```python
def _test_connectivity(host: str = "pypi.org",
                       port: int = 443,
                       timeout: float = 5.0) -> bool:
    """Test if a host is reachable."""
    try:
        socket.create_connection((host, port), timeout=timeout)
        return True
    except (socket.timeout, OSError):
        return False
```

### Phase 2 stance

Network detection is NOT done in Phase 2. We assume internet
access is available. Failures during downloads are handled by
the error recovery in each install method.

---

## IOMMU Groups

### What IOMMU groups are

IOMMU groups are hardware isolation boundaries for PCI devices.
They determine which devices can be passed through to VMs.

### Why they matter

For GPU passthrough (VFIO), the ENTIRE IOMMU group must be
passed through. If the GPU shares a group with other devices
(USB controller, audio device), all must be passed.

### Detection

```bash
# List IOMMU groups
for g in /sys/kernel/iommu_groups/*/devices/*; do
    echo "IOMMU Group $(basename $(dirname $(dirname $g))): $(lspci -nns $(basename $g))"
done
```

### Schema

```python
"iommu_groups": [
    {
        "group_id": 1,
        "devices": [
            {"slot": "01:00.0", "name": "NVIDIA RTX 4090",
             "type": "VGA compatible controller"},
            {"slot": "01:00.1", "name": "NVIDIA Audio Device",
             "type": "Audio device"},
        ],
    },
],
```

### Phase 6 only

IOMMU group detection is expensive and only needed for GPU
passthrough recipes. Triggered on demand via deep tier detection.

---

## Detection Summary

### What's detected in each phase

| Property | Phase 2 | Phase 5 | Phase 6 |
|----------|---------|---------|---------|
| `arch` (amd64/arm64) | ✅ | ✅ | ✅ |
| `machine` (raw) | ✅ | ✅ | ✅ |
| `cpu_count` | ✅ (`os.cpu_count()`) | ✅ | ✅ |
| `cpu_model` | ❌ | ❌ | ✅ |
| `cpu_features` (AVX) | ❌ | ❌ | ✅ |
| `ram_total_gb` | ❌ | ✅ | ✅ |
| `ram_available_gb` | ❌ | ✅ | ✅ |
| `disk_free_gb` (/) | ❌ | ✅ | ✅ |
| `tmp_free_gb` (/tmp) | ❌ | ✅ | ✅ |
| GPU | ❌ | ❌ | ✅ (domain-gpu) |
| IOMMU groups | ❌ | ❌ | ✅ |
| Network interfaces | ❌ | ❌ | ✅ |

### Detection methods

| Property | Method | Cost |
|----------|--------|------|
| arch | `platform.machine()` | < 1ms |
| cpu_count | `os.cpu_count()` | < 1ms |
| cpu_model | `/proc/cpuinfo` or `sysctl` | < 5ms |
| cpu_features | `/proc/cpuinfo` parse | < 5ms |
| ram_total | `os.sysconf` or `/proc/meminfo` | < 1ms |
| ram_available | `/proc/meminfo` parse | < 1ms |
| disk_free | `shutil.disk_usage()` | < 1ms |
| IOMMU groups | `/sys/kernel/iommu_groups/` | ~50ms |
| Network | `socket.create_connection()` | 1-5s (timeout) |

---

## Hardware Constraints in Recipes

### Phase 6 constraint evaluation

```python
"requires": {
    "hardware": {
        "gpu.nvidia.present": True,
        "gpu.nvidia.compute_capability": ">=7.0",
        "cpu.features": ["avx2"],
        "ram_available_gb": ">=4.0",
        "disk_free_gb": ">=5.0",
    },
},
```

**Constraint evaluation:**
```python
def _evaluate_constraint(profile: dict, constraint: dict) -> bool:
    """Check if hardware meets recipe requirements."""
    for key, required in constraint.items():
        actual = _get_nested(profile, key)
        if isinstance(required, bool):
            if actual != required:
                return False
        elif isinstance(required, str) and required.startswith(">="):
            threshold = float(required[2:])
            if float(actual or 0) < threshold:
                return False
        elif isinstance(required, list):
            # All items must be present
            if not all(f in (actual or []) for f in required):
                return False
    return True
```

---

## Traceability

| Topic | Source |
|-------|--------|
| arch normalization | arch-system-model §Fast profile |
| machine, system | arch-system-model §OS basics |
| Build environment resources | arch-system-model §Build environment (Phase 5) |
| cpu_cores, disk_free_gb | arch-system-model §Build environment |
| IOMMU groups | arch-system-model §Kernel state (Phase 6) |
| GPU detection | domain-gpu (full document) |
| Disk requirements per build | domain-build-from-source §disk space |
| RAM limits for `-j` | domain-build-from-source §parallel compilation |
| libc detection (musl/glibc) | domain-compilers §C library |
| Binary download arch limitation | domain-binary-installers §architecture |
| Phase 6 hardware roadmap | scope-expansion §Phase 6 |
| Hardware constraints in recipes | scope-expansion §2.9 |
