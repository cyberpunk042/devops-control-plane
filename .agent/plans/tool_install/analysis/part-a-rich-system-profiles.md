---
description: Part A — Rich system profiles for the tool install layer
---

# Part A: Rich System Profiles

## Goal

Replace the thin 8-entry `SYSTEM_PRESETS` dict with a comprehensive matrix that
matches the **real shape** of `_detect_os()` output, encodes **version-specific
differences** that affect tool installation, and covers the systems our users
actually run on.

---

## 1. Real `_detect_os()` shape (ground truth)

This is the exact output from the current machine (Ubuntu 20.04 on WSL2).
Every preset MUST match this structure:

```python
{
    "system": "Linux",                          # "Linux" | "Darwin"
    "release": "5.15.167.4-...",                # kernel/OS release
    "machine": "x86_64",                        # raw machine string
    "arch": "amd64",                            # normalized: amd64 | arm64 | armv7l
    "wsl": True,                                # bool
    "wsl_version": 2,                           # None | 1 | 2
    "distro": {
        "id": "ubuntu",                         # from /etc/os-release ID
        "name": "Ubuntu 20.04.6 LTS",           # PRETTY_NAME
        "version": "20.04",                     # VERSION_ID
        "version_tuple": [20, 4],               # parsed int list
        "family": "debian",                     # from _FAMILY_MAP
        "codename": "focal",                    # VERSION_CODENAME
    },
    "container": {
        "in_container": False,
        "runtime": None,                        # "docker" | "podman" | "lxc" | None
        "in_k8s": False,
        "read_only_rootfs": False,
    },
    "capabilities": {
        "has_systemd": True,
        "systemd_state": "degraded",            # "running" | "degraded" | None
        "has_sudo": True,
        "passwordless_sudo": False,
        "is_root": False,
    },
    "package_manager": {
        "primary": "apt",
        "available": ["apt"],                   # list of all detected PMs
        "snap_available": True,
    },
    "libraries": {
        "openssl_version": "3.6.1",
        "glibc_version": "2.31",
        "libc_type": "glibc",                   # "glibc" | "musl"
    },
    "hardware": {
        "cpu_cores": 4,
        "arch": "amd64",
        "ram_total_mb": 7947,
        "ram_available_mb": 756,
        "disk_free_gb": 190.0,
        "disk_total_gb": 250.9,
    },
}
```

---

## 2. Version-specific differences that affect tool installation

### 2.1 PEP 668 (externally-managed-environment)

| Distro | Version | PEP 668 | Effect |
|--------|---------|---------|--------|
| Ubuntu | 20.04 | ❌ | `pip install` works system-wide |
| Ubuntu | 22.04 | ❌ | Same |
| Ubuntu | 23.04+ | ✅ | `pip install` blocked, needs `--break-system-packages` or venv |
| Ubuntu | 24.04 | ✅ | Same, enforced |
| Debian | 11 | ❌ | `pip install` works |
| Debian | 12 | ✅ | Blocked |
| Fedora | 38+ | ✅ | Blocked |
| Arch | rolling | ✅ | Blocked |
| Alpine | all | ❌ | Not enforced (uses apk python packages) |
| macOS | all | ❌ | Homebrew Python doesn't enforce |

**Impact on remediation:** PEP 668 handlers should only show "use --break-system-packages"
on systems that enforce it. On Ubuntu 20.04, the PEP 668 error won't happen, so that
handler is irrelevant.

### 2.2 Default Python version

| Distro | Version | Python |
|--------|---------|--------|
| Ubuntu 20.04 | focal | 3.8 |
| Ubuntu 22.04 | jammy | 3.10 |
| Ubuntu 24.04 | noble | 3.12 |
| Debian 11 | bullseye | 3.9 |
| Debian 12 | bookworm | 3.11 |
| Fedora 39 | — | 3.12 |
| Fedora 41 | — | 3.13 |
| Alpine 3.18 | — | 3.11 |
| Alpine 3.20 | — | 3.12 |
| Arch | rolling | 3.12+ |
| macOS 14 | — | 3.9 (system) / 3.12 (brew) |

### 2.3 Snap behavior

| System | Snap support | Notes |
|--------|-------------|-------|
| Ubuntu 20.04+ | ✅ classic | snap is default for many tools |
| Ubuntu 24.04 | ✅ strict default | classic requires `--classic` flag |
| Debian 12 | ⚠️ optional | not installed by default |
| Fedora | ⚠️ optional | copr needed |
| Alpine | ❌ | no snapd |
| Arch | ⚠️ AUR | snapd-git in AUR |
| macOS | ❌ | not available |
| Raspberry Pi | ✅ | same as Debian/Ubuntu |
| Containers | ❌ | no snapd in containers |

### 2.4 Architecture availability

| Tool type | x86_64 | aarch64 (RPi/Graviton) | arm64 (macOS) |
|-----------|--------|------------------------|---------------|
| System packages (apt/dnf) | ✅ full | ✅ full | N/A |
| Homebrew | ✅ (/home/linuxbrew) | ⚠️ limited | ✅ (/opt/homebrew) |
| Binary downloads (_default) | ✅ most tools | ⚠️ many miss ARM | ✅ most tools |
| Snap packages | ✅ full | ⚠️ limited | N/A |
| pip/npm/cargo | ✅ | ✅ (pure) / ⚠️ (native) | ✅ |

### 2.5 Container differences

| Field | Bare metal | Docker | K8s pod |
|-------|-----------|--------|---------|
| systemd | ✅ | ❌ | ❌ |
| sudo | ✅ | ❌ (usually root) | varies |
| snap | maybe | ❌ | ❌ |
| disk space | large | constrained | ephemeral |
| read-only rootfs | ❌ | ❌ | maybe |

### 2.6 WSL differences

| Field | Native Linux | WSL2 |
|-------|-------------|------|
| systemd | ✅ | ⚠️ must enable |
| snap | ✅ | ⚠️ needs systemd |
| Docker | ✅ | ⚠️ Docker Desktop or native |
| /proc/version | normal | contains "microsoft" |

### 2.7 glibc vs musl

| Family | libc | Affects |
|--------|------|---------|
| Debian/RHEL/Arch/SUSE | glibc | Most binaries work |
| Alpine | musl | Many pre-built binaries won't work, need musl builds or compile from source |

---

## 3. Full preset matrix

### 3.1 Debian family (7 presets)

```python
"ubuntu_2004": {
    "system": "Linux",
    "arch": "amd64",
    "wsl": False,
    "wsl_version": None,
    "distro": {
        "id": "ubuntu", "family": "debian",
        "version": "20.04", "version_tuple": [20, 4],
        "name": "Ubuntu 20.04.6 LTS", "codename": "focal",
    },
    "container": {"in_container": False, "runtime": None, "in_k8s": False, "read_only_rootfs": False},
    "capabilities": {"has_systemd": True, "systemd_state": "running", "has_sudo": True, "passwordless_sudo": False, "is_root": False},
    "package_manager": {"primary": "apt", "available": ["apt"], "snap_available": True},
    "libraries": {"glibc_version": "2.31", "libc_type": "glibc"},
    "hardware": {"arch": "amd64", "cpu_cores": 4},
    "python": {"default_version": [3, 8], "pep668": False},
},
"ubuntu_2204": {
    # ... codename="jammy", version_tuple=[22,4], glibc=2.35, python=[3,10], pep668=False
},
"ubuntu_2404": {
    # ... codename="noble", version_tuple=[24,4], glibc=2.39, python=[3,12], pep668=True
},
"debian_11": {
    # ... codename="bullseye", version_tuple=[11], glibc=2.31, python=[3,9], pep668=False,
    #     snap_available=False (not installed by default)
},
"debian_12": {
    # ... codename="bookworm", version_tuple=[12], glibc=2.36, python=[3,11], pep668=True,
    #     snap_available=False
},
"raspbian_bookworm": {
    # ... same as debian_12 but arch="arm64", id="raspbian", snap limited
},
"wsl2_ubuntu_2204": {
    # ... same as ubuntu_2204 but wsl=True, wsl_version=2, systemd_state="degraded"
},
```

### 3.2 RHEL family (4 presets)

```python
"fedora_39": {
    # ... dnf, glibc=2.38, python=[3,12], pep668=True
},
"fedora_41": {
    # ... dnf 5.x, glibc=2.40, python=[3,13], pep668=True
},
"centos_stream9": {
    # ... dnf, glibc=2.34, python=[3,9], EPEL available
},
"rocky_9": {
    # ... same family as centos_stream9, dnf
},
```

### 3.3 Alpine (2 presets)

```python
"alpine_318": {
    # ... apk, musl 1.2.4, python=[3,11], NO systemd, NO sudo default,
    #     libc_type="musl", snap_available=False
},
"alpine_320": {
    # ... apk, musl 1.2.5, python=[3,12]
},
```

### 3.4 Arch / SUSE (2 presets)

```python
"arch_latest": {
    # ... pacman, glibc current, python=[3,12], pep668=True, snap_available=False
},
"opensuse_15": {
    # ... zypper, glibc=2.31, python=[3,6], pep668=False
},
```

### 3.5 macOS (2 presets)

```python
"macos_14_arm": {
    # ... brew, arm64, no systemd, no snap, python via brew
},
"macos_13_x86": {
    # ... brew, amd64, different Homebrew prefix (/usr/local vs /opt/homebrew)
},
```

### 3.6 Container edge cases (2 presets)

```python
"docker_debian_12": {
    # ... in_container=True, runtime="docker", NO systemd, is_root=True,
    #     has_sudo=False, snap_available=False
},
"k8s_alpine_318": {
    # ... in_container=True, in_k8s=True, runtime="containerd",
    #     NO systemd, read_only_rootfs possible, musl
},
```

### Total: 19 presets

---

## 4. The `python` extension field

This is new metadata not in the current `_detect_os()` output. We add it to
SYSTEM_PRESETS only (scenarios need it), and later can add detection to
`_detect_os()` via `python3 --version` probing.

```python
"python": {
    "default_version": [3, 12],     # Major.minor as tuple
    "pep668": True,                 # PEP 668 enforced on this system
}
```

**Why it matters for remediation:**
- PEP 668 handlers should only trigger on systems with `pep668=True`
- Python version affects which tools are compatible (e.g., ruff needs 3.7+)
- virtualenv behavior differs by Python version

---

## 5. Consumers to update

| File | What to change | Why |
|------|----------------|-----|
| `dev_scenarios.py` | Replace `SYSTEM_PRESETS` with 19 rich presets | This is the primary change |
| `dev_overrides.py` | No change needed | Already returns preset as-is |
| `tests/test_remediation_coverage.py` | Update preset list, add preset structure validation | Test all 19 presets |
| `remediation_planning.py` | **Future (Part A step 2)** — version-aware availability | Use `python.pep668`, `libraries.libc_type` |

---

## 6. Implementation steps

### Step A1: Write the 19 presets (data change only)
- File: `dev_scenarios.py` → `SYSTEM_PRESETS`
- Replace current 8 presets with 19 presets matching `_detect_os()` shape
- Each preset is a complete, realistic system profile
- No consumer code changes yet — just richer data

### Step A2: Update test to validate preset structure
- File: `tests/test_remediation_coverage.py`
- Add `check_preset_structure()` — verify every preset has all required fields
- Run all 19 presets through scenario generation
- Verify no crashes or false impossibles from the richer profiles

### Step A3 (future): Version-aware availability checks
- File: `remediation_planning.py`
- Use `python.pep668` to gate PEP 668 handlers
- Use `libraries.libc_type` to flag musl binary issues
- Use `arch` to flag ARM binary availability
- This is a separate PR after presets land

---

## 7. Fields required per preset

Checklist for every preset entry:

```
system            ✅ "Linux" or "Darwin"
arch              ✅ "amd64" or "arm64" or "armv7l"
wsl               ✅ bool
wsl_version       ✅ None | 1 | 2
distro.id         ✅ matches _FAMILY_MAP key
distro.family     ✅ debian | rhel | alpine | arch | suse | macos
distro.version    ✅ string
distro.version_tuple ✅ list[int]
distro.name       ✅ human-readable
distro.codename   ✅ string or None
container.in_container    ✅ bool
container.runtime         ✅ None | "docker" | "podman" | "containerd"
container.in_k8s          ✅ bool
container.read_only_rootfs ✅ bool
capabilities.has_systemd       ✅ bool
capabilities.systemd_state     ✅ None | "running" | "degraded"
capabilities.has_sudo          ✅ bool
capabilities.passwordless_sudo ✅ bool
capabilities.is_root           ✅ bool
package_manager.primary        ✅ apt | dnf | apk | zypper | brew | pacman
package_manager.available      ✅ list[str]
package_manager.snap_available ✅ bool
libraries.glibc_version       ✅ string (or None for musl/macOS)
libraries.libc_type            ✅ "glibc" | "musl" | None
hardware.arch                  ✅ same as top-level arch
hardware.cpu_cores             ✅ int
python.default_version         ✅ list[int] — [major, minor]
python.pep668                  ✅ bool
```

---

## 8. Risk assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| More presets = slower test | Low (19 × ~0.5s = ~10s) | Acceptable |
| Preset data inaccuracy | Medium — wrong version/pep668 info | Research each carefully |
| Consumer code reads unexpected field | Low — consumers use `.get()` with defaults | Verified in analysis |
| Breaking existing scenario generation | Medium | Run test before/after, compare counts |
