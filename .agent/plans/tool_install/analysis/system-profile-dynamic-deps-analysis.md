---
description: Analysis — Rich system profiles + dynamic dep resolver for the tool install layer
---

# Analysis: System Profile Evolution & Dynamic Dep Resolver

## Current State

### System Profile (`_detect_os()`)

The real `_detect_os()` in `l0_detection.py` already captures a **rich** profile:

```python
{
    "system": "Linux",
    "release": "6.1.0-...",
    "machine": "x86_64",
    "arch": "amd64",               # normalized
    "wsl": False,
    "distro": {
        "id": "ubuntu",
        "name": "Ubuntu 22.04.4 LTS",
        "version": "22.04",
        "version_tuple": [22, 4],  # ← already parsed!
        "family": "debian",
        "codename": "jammy",
    },
    "container": {"in_container": False, ...},
    "capabilities": {
        "has_systemd": True,
        "has_sudo": True,
        "passwordless_sudo": False,
        "is_root": False,
    },
    "package_manager": {
        "primary": "apt",
        "available": ["apt"],
        "snap_available": True,
    },
    "libraries": {...},
    "hardware": {
        "cpu_cores": 16,
        "arch": "amd64",
        "ram_total_mb": 32768,
        "disk_free_gb": 120.5,
    },
}
```

**What's good:** The real detection is already detailed. It has `version_tuple`,
`codename`, `arch`, `wsl`, container detection, hardware info.

**What's broken:** The scenario **SYSTEM_PRESETS** are thin stubs that don't
carry most of this information. And more importantly, **nothing in the
remediation layer uses version-specific logic** — it only checks `family` and
`primary` package manager. Ubuntu 20.04 vs 24.04 produce the same remediation
options even though PEP 668 enforcement differs.

### Dep Resolution

Currently deps are resolved through two paths:

1. **Recipe-based** (`_collect_deps` in `dependency_collection.py`):
   - Looks up `TOOL_RECIPES[dep_id]`
   - Uses `requires.binaries` for recursive deps
   - Uses `requires.packages` keyed by family for system packages
   - If dep has no recipe → `logger.warning` and skip

2. **Remediation-based** (`_check_dep_availability` in `remediation_planning.py`):
   - Looks up `TOOL_RECIPES[dep]`
   - If no recipe → **was** impossible, now falls back to system package check
   - No actual install logic for recipe-less deps

3. **Library mapping** (`LIB_TO_PACKAGE_MAP` in `remediation_handlers.py`):
   - Maps library short names (ssl, curl, ffi) → package names per family
   - Used only for `install_packages` remediation options
   - **Static and incomplete** — only 14 libraries mapped

**What's missing:**
- No way to install a dep that has no recipe and no library mapping
- No dynamic package name resolution (dep `unzip` → which package on Alpine?)
- No respect for package manager configs (.npmrc, pip.conf, etc.)

---

## Part A: Rich System Profiles

### A1. Problem

The SYSTEM_PRESETS are used for:
1. Scenario generation (testing handler behavior per system)
2. Dev override (system profile switcher in Stage Debugger)
3. Future: per-version remediation logic

Currently they carry: `system`, `distro.{id,family,version,name}`,
`package_manager.primary`, `capabilities.{has_sudo,has_systemd}`.

They DON'T carry: `arch`, `version_tuple`, `codename`, `container`,
`wsl`, `snap_available`, `libraries`, `hardware`, or version-specific
capability flags.

### A2. Version-specific differences that matter

| Field | Ubuntu 20.04 | Ubuntu 22.04 | Ubuntu 24.04 |
|-------|-------------|-------------|-------------|
| Python default | 3.8 | 3.10 | 3.12 |
| PEP 668 enforced | ❌ | ❌ | ✅ |
| snap default | classic | classic | strict |
| Node.js (apt) | 10.x | 12.x | 18.x |
| apt-key | works | deprecated | removed |
| kernel | 5.4 | 5.15 | 6.8 |
| codename | focal | jammy | noble |

| Field | Debian 11 | Debian 12 |
|-------|-----------|-----------|
| Python default | 3.9 | 3.11 |
| PEP 668 enforced | ❌ | ✅ |
| codename | bullseye | bookworm |

| Field | Fedora 38 | Fedora 39 | Fedora 41 |
|-------|-----------|-----------|-----------|
| Python default | 3.11 | 3.12 | 3.13 |
| DNF version | 4.x | 4.x | 5.x |
| Package groups | ✅ | ✅ | changed names |

| Field | x86_64 | aarch64 (RPi) | arm64 (macOS) |
|-------|--------|---------------|---------------|
| Binary downloads | most tools | fewer tools | most tools |
| Docker images | all | fewer | most |
| Snap support | full | limited | N/A |
| Homebrew | linuxbrew | not common | native |

### A3. Proposed preset structure

```python
SYSTEM_PRESETS = {
    "ubuntu_2004": {
        "system": "Linux",
        "arch": "x86_64",
        "distro": {
            "id": "ubuntu", "family": "debian",
            "version": "20.04", "version_tuple": [20, 4],
            "name": "Ubuntu 20.04.6 LTS", "codename": "focal",
        },
        "package_manager": {
            "primary": "apt", "available": ["apt"],
            "snap_available": True,
        },
        "capabilities": {
            "has_sudo": True, "has_systemd": True,
            "is_root": False, "passwordless_sudo": False,
        },
        # Version-specific capability flags
        "python": {"default_version": "3.8", "pep668_enforced": False},
        "container": {"in_container": False},
        "wsl": False,
    },
    "ubuntu_2404": {
        # ... same structure but:
        # "version": "24.04", "codename": "noble",
        # "python": {"default_version": "3.12", "pep668_enforced": True},
    },
    "raspbian_arm64": {
        # ... "arch": "aarch64",
        # limited binary availability, snap limited
    },
}
```

### A4. Required presets (minimum matrix)

**Debian family:**
- `ubuntu_2004` — focal, Python 3.8, no PEP 668
- `ubuntu_2204` — jammy, Python 3.10, no PEP 668
- `ubuntu_2404` — noble, Python 3.12, PEP 668
- `debian_11` — bullseye, Python 3.9
- `debian_12` — bookworm, Python 3.11, PEP 668
- `raspbian_arm64` — bookworm, aarch64, limited snap

**RHEL family:**
- `fedora_39` — dnf 4.x
- `fedora_41` — dnf 5.x
- `centos_stream9` — RHEL-compatible, EPEL
- `rocky_9` — RHEL clone

**Other Linux:**
- `alpine_318` — musl libc, no systemd, no sudo by default
- `alpine_320` — musl, newer packages
- `arch_latest` — rolling release
- `opensuse_15` — zypper

**macOS:**
- `macos_14_arm` — Apple Silicon
- `macos_13_x86` — Intel (different Homebrew prefix)

**Edge cases:**
- `wsl2_ubuntu_2204` — WSL2, has quirks
- `docker_debian_12` — in_container=True, no systemd, root

### A5. Where the presets are consumed

Consumers that need updating when presets become richer:

| Consumer | File | What it reads |
|----------|------|---------------|
| Scenario generator | `dev_scenarios.py` | Everything — drives test matrix |
| Dev override resolver | `dev_overrides.py` | Returns preset as system_profile |
| Availability checker | `remediation_planning.py` | `distro.family`, `package_manager.primary` |
| Method selection | `method_selection.py` | `package_manager.primary`, `snap_available` |
| Dep collection | `dependency_collection.py` | `package_manager.primary`, `distro.family` |
| Condition evaluation | `condition.py` | `capabilities.*`, `container`, `init_system` |
| Choice resolution | `choice_resolution.py` | Deep dot-path into system_profile |

**Key insight:** The availability checker (`_compute_availability`) currently
only uses `distro.family`. To make version-aware decisions (e.g. PEP 668
only matters on Python ≥3.11 + new distros), it needs access to `version_tuple`
and version-specific flags.

---

## Part B: Dynamic Dep Resolver

### B1. Problem

Current flow when a dep is detected but not in TOOL_RECIPES:
```
_collect_deps("unknown_dep")
  → TOOL_RECIPES.get("unknown_dep") → None
  → logger.warning("not found in TOOL_RECIPES")
  → return (silently skip)
```

This means any dep the program detects (via stderr parsing, runtime check,
or user request) that isn't pre-registered is **completely invisible** to
the install system.

**Important:** The dynamic resolver is one of **three dep resolution contexts**
(see Part B plan, section 10):

1. **Manifest-driven** — `package.json`, `requirements.txt`, `Cargo.toml` →
   PM is deterministic, no guessing. Individual/group ops (install all,
   install prod only, audit, update). PM configs (.npmrc, pip.conf) are
   critical here.
2. **Curated stack** — Stacks WE build full support for (Python, Node, Rust,
   Go, Docker). Full recipes, handlers, tested scenarios.
3. **Dynamic fallback** — Everything else: deps we haven't curated, community
   stacks, runtime discoveries. This is what this resolver handles.

### B2. What dynamic resolution needs to do

```
resolve_dynamic_dep("unzip", system_profile)
  1. Check TOOL_RECIPES → not found
  2. Check if binary exists → shutil.which("unzip") → found or not
  3. If not found:
     a. Determine package name for this system
        - "unzip" on apt = "unzip"
        - "unzip" on apk = "unzip"
        - "libssl" on apt = "libssl-dev", on dnf = "openssl-devel"
     b. Build install command using system's primary PM
        - _build_pkg_install_cmd(["unzip"], "apt")
     c. Return a synthetic install step
  4. Respect package manager configs:
     - pip: check pip.conf, venv, --user vs system
     - npm: check .npmrc, global vs local
     - apt: respect sources.list, proxy settings
     - All: respect sudo requirements
```

### B3. Package name resolution strategy

Three tiers, tried in order:

**Tier 1: Exact match** — dep name IS the package name (most common)
- `unzip` → `unzip` on all systems
- `curl` → `curl` on all systems
- `git` → `git` on all systems
- `jq` → `jq` on all systems

**Tier 2: Library mapping** — `LIB_TO_PACKAGE_MAP` (already exists)
- `ssl` → `libssl-dev` (debian) / `openssl-devel` (rhel)
- `ffi` → `libffi-dev` (debian) / `libffi-devel` (rhel)

**Tier 3: Convention-based** — apply system naming conventions
- Debian dev packages: `lib{name}-dev`
- RHEL dev packages: `{name}-devel`
- Alpine dev packages: `{name}-dev`
- Arch: `{name}` (no -dev suffix)
- Brew: `{name}` or `lib{name}`

### B4. Proposed function

```python
def resolve_dep_install(
    dep: str,
    system_profile: dict,
) -> dict | None:
    """Resolve how to install a dependency on this system.

    Tries TOOL_RECIPES first, then dynamic system package resolution.
    Returns None only if truly unresolvable.

    Returns:
        {
            "dep": "unzip",
            "source": "recipe" | "system_package" | "lib_mapping",
            "package_name": "unzip",
            "install_cmd": ["apt-get", "install", "-y", "unzip"],
            "needs_sudo": True,
        }
    """
```

### B5. Package manager config awareness

| PM | Config file | What to respect |
|----|------------|-----------------|
| pip | `pip.conf`, `~/.pip/pip.conf` | `--user` vs venv, index-url, trusted-host |
| npm | `.npmrc`, `~/.npmrc` | registry, scope, proxy |
| apt | `/etc/apt/sources.list`, proxy | repositories, GPG keys |
| dnf | `/etc/dnf/dnf.conf` | repositories, proxy, gpgcheck |
| brew | `HOMEBREW_*` env vars | prefix path, taps |
| cargo | `~/.cargo/config.toml` | registries, proxy |

The dynamic resolver should at minimum:
1. Detect if the PM has custom config that affects installs
2. Warn if custom registries/proxies are configured
3. Not override user's PM settings

### B6. Where to put it

```
src/core/services/tool_install/
├── resolver/
│   ├── dynamic_dep_resolver.py   ← NEW: Tier 1-3 resolution
│   └── dependency_collection.py  ← MODIFY: call dynamic resolver as fallback
├── data/
│   ├── recipes.py                ← existing: 296 recipes
│   ├── remediation_handlers.py   ← existing: LIB_TO_PACKAGE_MAP lives here
│   └── system_packages.py        ← NEW: package name mappings for Tier 1+3
└── domain/
    └── remediation_planning.py   ← MODIFY: use dynamic resolver in availability
```

---

## Implementation Order

### Step 1: Enrich SYSTEM_PRESETS
- Add all version-specific presets (A4 list)
- Add `version_tuple`, `codename`, `python`, `container`, `wsl` fields
- Update test to cover all presets
- **No code changes** to consumers yet — just richer test data

### Step 2: Dynamic dep resolver (Tier 1 — exact match)
- Create `dynamic_dep_resolver.py` with `resolve_dep_install()`
- For Tier 1: dep name = package name → build install command via `_build_pkg_install_cmd`
- Wire into `_check_dep_availability` → locked with install path instead of impossible
- Wire into `_collect_deps` → fallback when recipe not found
- Update test to verify dynamic deps resolve

### Step 3: Dynamic dep resolver (Tier 2+3 — library mapping + conventions)
- Move/expand `LIB_TO_PACKAGE_MAP` into `system_packages.py`
- Add convention-based resolution for dev packages
- Update test with library dep scenarios

### Step 4: Version-aware availability
- Add version checks to `_compute_availability` (PEP 668 gating, etc.)
- Add version-specific handler options (different remediation per version)
- Verify scenarios produce different results for Ubuntu 20 vs 24

### Step 5: PM config awareness
- Detect pip.conf, .npmrc, etc.
- Add config info to system profile
- Use in install command generation (--user, registry, proxy)

---

## Files to create/modify

| File | Action | Step |
|------|--------|------|
| `dev_scenarios.py` → `SYSTEM_PRESETS` | Expand with all presets | 1 |
| `tests/test_remediation_coverage.py` | Add preset validation | 1 |
| `resolver/dynamic_dep_resolver.py` | **CREATE** | 2 |
| `data/system_packages.py` | **CREATE** | 2-3 |
| `domain/remediation_planning.py` | Wire dynamic resolver | 2 |
| `resolver/dependency_collection.py` | Fallback to dynamic resolver | 2 |
| `data/remediation_handlers.py` | Move LIB_TO_PACKAGE_MAP | 3 |
| `domain/remediation_planning.py` | Version-aware checks | 4 |
