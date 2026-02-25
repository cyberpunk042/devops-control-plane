# Domain: Platforms

> This document catalogs every platform the tool install system
> supports, what makes each one different, and what the recipes
> and resolver must account for.
>
> SOURCE DOCS: phase1 §3.1-3.8, phase2.2 §1-3 (tool tables),
>              scope-expansion §2.5/2.7, arch-system-model (fast tier)
>
> SOURCE CODE: l0_detection.py (_FAMILY_MAP, _ARCH_MAP, _detect_os)

---

## Platform Model

The system classifies platforms along THREE dimensions:

| Dimension | Values | Detected by |
|-----------|--------|-------------|
| **OS** | Linux, Darwin (macOS) | `platform.system()` |
| **Architecture** | amd64, arm64, armv7 | `platform.machine()` → `_ARCH_MAP` |
| **Family** | debian, rhel, alpine, arch, suse, macos | `/etc/os-release` → `_FAMILY_MAP` |

These three together determine:
- Which package manager is primary
- Which package NAMES to use (`requires.packages` key)
- Which install methods are available
- Which post-install conditions apply

---

## Distro Families

### Family: `debian`

**Members:** Ubuntu, Debian, Linux Mint, Pop!_OS, elementary OS,
Zorin OS, Kali, Raspbian, Deepin

**Mapping in code:**
```python
_FAMILY_MAP = {
    "ubuntu": "debian", "debian": "debian", "linuxmint": "debian",
    "pop": "debian", "elementary": "debian", "zorin": "debian",
    "kali": "debian", "raspbian": "debian", "deepin": "debian",
}
```

| Property | Value |
|----------|-------|
| Primary PM | `apt` → `apt-get` |
| Install flags | `apt-get install -y` |
| Update command | `apt-get install --only-upgrade -y PKG` |
| Package index | `apt-get update` (must run before install if stale) |
| Dev package convention | `libfoo-dev` |
| snap support | Yes (Ubuntu default), requires systemd |
| Default shell | bash |
| Init system | systemd (Ubuntu 15.04+, Debian 8+) |
| Sudo | Typically available |

**Package name examples:**

| Concept | Package name |
|---------|-------------|
| OpenSSL headers | `libssl-dev` |
| libcurl headers | `libcurl4-openssl-dev` |
| pkg-config | `pkg-config` |
| Python 3 | `python3` |
| pip | `python3-pip` |
| DNS tools | `dnsutils` |
| Docker | `docker.io` (community) or `docker-ce` (official repo) |
| Docker Compose v2 | `docker-compose-v2` |
| Node.js | `nodejs` |
| Build toolchain | `build-essential` (meta-package: gcc, g++, make, dpkg-dev) |

**WSL note:** Ubuntu is the most common WSL distro. WSL1 has no
real Linux kernel (translation layer), WSL2 has a real kernel.
Both detected via `/proc/version` containing "microsoft".

**Repo setup:** APT repos require GPG key + sources.list entry.
Example pipeline: install prerequisites → add GPG key → add repo
source → apt-get update → install package.

### Family: `rhel`

**Members:** Fedora, CentOS, RHEL, Rocky Linux, AlmaLinux,
Oracle Linux, Amazon Linux (amzn)

**Mapping in code:**
```python
_FAMILY_MAP = {
    "fedora": "rhel", "centos": "rhel", "rhel": "rhel",
    "rocky": "rhel", "almalinux": "rhel", "oracle": "rhel",
    "amzn": "rhel",
}
```

| Property | Value |
|----------|-------|
| Primary PM | `dnf` (Fedora 22+, RHEL 8+) or `yum` (older) |
| Install flags | `dnf install -y` |
| Update command | `dnf upgrade -y PKG` |
| Package index | `dnf makecache` (auto-refreshed) |
| Dev package convention | `foo-devel` |
| snap support | Not default, can be installed |
| Default shell | bash |
| Init system | systemd |
| Sudo | Typically available |

**Package name examples:**

| Concept | Package name |
|---------|-------------|
| OpenSSL headers | `openssl-devel` |
| libcurl headers | `libcurl-devel` |
| pkg-config | `pkgconf-pkg-config` |
| Python 3 | `python3` |
| pip | `python3-pip` |
| DNS tools | `bind-utils` |
| Docker | `docker` or `docker-ce` (from Docker repo) |
| Docker Compose v2 | `docker-compose-plugin` |
| Node.js | `nodejs` |
| Build toolchain | `groupinstall "Development Tools"` |

**Fedora vs RHEL/CentOS:**
- Fedora: latest packages, fast updates, may have newer package names
- RHEL/CentOS: stable but older packages, may need EPEL for extras
- Amazon Linux: RHEL-based but uses `amazon-linux-extras` for some tools

**ffmpeg:** `ffmpeg-free` in standard repos (codec licensing).
Full ffmpeg requires RPMFusion repository.

**yum vs dnf:** On older systems (CentOS 7, RHEL 7) only `yum` is
available. The resolver checks for `dnf` first, falls back to `yum`.
Both have the same install syntax for our purposes.

### Family: `alpine`

**Members:** Alpine Linux only

**Mapping in code:**
```python
_FAMILY_MAP = {"alpine": "alpine"}
```

| Property | Value |
|----------|-------|
| Primary PM | `apk` |
| Install flags | `apk add` |
| Update command | `apk upgrade PKG` |
| Package index | `apk update` |
| Dev package convention | `foo-dev` |
| snap support | No (no systemd) |
| Default shell | `ash` (BusyBox) |
| Init system | OpenRC (no systemd) |
| Sudo | Often absent in containers (runs as root) |
| C library | musl (NOT glibc) |

**Package name examples:**

| Concept | Package name |
|---------|-------------|
| OpenSSL headers | `openssl-dev` |
| libcurl headers | `curl-dev` |
| pkg-config | `pkgconf` |
| Python 3 | `python3` |
| pip | `py3-pip` |
| DNS tools | `bind-tools` |
| Docker | `docker` |
| Node.js | `nodejs` |
| Build toolchain | `build-base` (meta-package: gcc, g++, make, musl-dev) |

**Critical differences from other families:**
1. **musl libc** — not glibc. Pre-built binaries targeting glibc
   will NOT work. Detection: `libraries.libc_type == "musl"`.
   This affects binary downloads (need musl builds or static linking).
2. **No systemd** — uses OpenRC. `capabilities.has_systemd == False`.
   All `condition: "has_systemd"` post-install steps are skipped.
3. **Minimal by default** — many tools not included in base.
   Even `bash` may not be installed (only `ash`/`sh`).
4. **Common in Docker** — Alpine is the most popular Docker base
   image. Container detection + Alpine = very common combo.
5. **No desktop GUI tools** — xterm, gnome-terminal, etc. are
   not available in Alpine repos.

### Family: `arch`

**Members:** Arch Linux, Manjaro, EndeavourOS

**Mapping in code:**
```python
_FAMILY_MAP = {"arch": "arch", "manjaro": "arch", "endeavouros": "arch"}
```

| Property | Value |
|----------|-------|
| Primary PM | `pacman` |
| Install flags | `pacman -S --noconfirm` |
| Update command | `pacman -Syu --noconfirm PKG` |
| Package index | `pacman -Sy` (usually combined with `-u`) |
| Dev package convention | `foo` (headers included in main package) |
| snap support | Not default, can use `snapd` from AUR |
| Default shell | bash |
| Init system | systemd |
| Sudo | Typically available |

**Package name examples:**

| Concept | Package name |
|---------|-------------|
| OpenSSL headers | `openssl` (headers bundled) |
| libcurl headers | `curl` (headers bundled) |
| pkg-config | `pkgconf` |
| Python 3 | `python` (not `python3`) |
| pip | `python-pip` (not `python3-pip`) |
| DNS tools | `bind` (full package, not just tools) |
| Docker | `docker` |
| Node.js | `nodejs` |
| Build toolchain | `base-devel` (meta-group) |

**Arch specifics:**
- Dev headers are bundled in main packages (no `-dev` suffix)
- Python is `python` not `python3` (Arch was early to Python 3 default)
- pip is `python-pip` not `python3-pip`
- AUR (Arch User Repository) provides community packages but requires
  a helper like `yay` or `paru` — not automated by our system in
  Phase 2 (future: Phase 7+)

### Family: `suse`

**Members:** openSUSE Leap, openSUSE Tumbleweed, SLES

**Mapping in code:**
```python
_FAMILY_MAP = {
    "opensuse-leap": "suse", "opensuse-tumbleweed": "suse", "sles": "suse",
}
```

| Property | Value |
|----------|-------|
| Primary PM | `zypper` |
| Install flags | `zypper install -y` |
| Update command | `zypper update -y PKG` |
| Package index | `zypper refresh` |
| Dev package convention | `libfoo-devel` |
| snap support | Not default |
| Default shell | bash |
| Init system | systemd |
| Sudo | Typically available |

**Package name examples:**

| Concept | Package name |
|---------|-------------|
| OpenSSL headers | `libopenssl-devel` |
| libcurl headers | `libcurl-devel` |
| pkg-config | `pkg-config` |
| Python 3 | `python3` |
| pip | `python3-pip` |
| DNS tools | `bind-utils` |
| Docker | `docker` |
| Build toolchain | pattern `devel_basis` |

### Family: `macos`

**Members:** macOS (all versions)

| Property | Value |
|----------|-------|
| Primary PM | `brew` (Homebrew) |
| Install flags | `brew install` |
| Update command | `brew upgrade PKG` |
| Package index | `brew update` (auto-runs periodically) |
| Dev package convention | formula name (e.g., `openssl@3`) |
| snap support | No |
| Default shell | `zsh` (since Catalina 10.15) |
| Init system | `launchd` (no systemd) |
| Sudo | Available but brew doesn't need it |
| C library | libSystem (Apple's, not glibc or musl) |

**Package name examples:**

| Concept | Brew formula |
|---------|-------------|
| OpenSSL headers | `openssl@3` (versioned) |
| libcurl headers | `curl` |
| pkg-config | `pkg-config` |
| Python 3 | `python@3` |
| pip | comes with `python@3` |
| DNS tools | `bind` |
| Docker | `--cask docker` (Docker Desktop, GUI) |
| Node.js | `node` (includes npm) |

**macOS specifics:**
1. **No systemd** — all service management via launchd/launchctl.
   `capabilities.has_systemd == False`.
2. **brew doesn't need sudo** — writes to `/opt/homebrew` (ARM) or
   `/usr/local` (Intel). `needs_sudo: False` for all brew installs.
3. **Cask vs formula** — GUI apps use `brew install --cask NAME`.
   CLI tools use `brew install NAME`. Docker is a cask (Docker Desktop).
   kitty is a cask. Most devops tools are formulas.
4. **npm bundled with node** — `brew install node` provides both
   node and npm. No separate npm package.
5. **pip bundled with python** — `brew install python@3` provides pip.
6. **gzip bundled with macOS** — no need to install via brew.
7. **libSystem** — `libraries.libc_type = "system"`. Binary compatibility
   is managed by macOS itself, not by libc version.
8. **Architectures** — Intel (`x86_64` → `amd64`) vs Apple Silicon
   (`arm64`). Brew installs to different prefixes.
9. **Xcode CLI tools** — provides git, make, clang (as `gcc`),
   and other build tools. `xcode-select --install` is the bootstrap.

---

## Architecture Matrix

The `arch` field in the system profile normalizes raw machine strings:

```python
_ARCH_MAP = {
    "x86_64": "amd64", "amd64": "amd64",
    "aarch64": "arm64", "arm64": "arm64",
    "armv7l": "armv7",
}
```

| Architecture | Where it appears | Binary naming convention |
|-------------|-----------------|------------------------|
| `amd64` | Most servers, Intel/AMD desktops | `foo-linux-amd64`, `foo-x86_64` |
| `arm64` | Apple Silicon, AWS Graviton, Raspberry Pi 4+ | `foo-linux-arm64`, `foo-aarch64` |
| `armv7` | Raspberry Pi 3, older ARM boards | `foo-linux-armv7`, `foo-armhf` |

**Impact on recipes:**
- Binary downloads (curl-pipe-bash) are often architecture-hardcoded.
  Example: skaffold downloads `skaffold-linux-amd64`.
  On arm64 this downloads the WRONG binary.
- Phase 5 will add arch interpolation to binary download URLs:
  `https://example.com/tool-linux-{arch}`
- Package managers handle arch transparently (apt/dnf install
  the correct arch automatically).
- Brew on Apple Silicon uses `/opt/homebrew`, Intel uses `/usr/local`.

---

## Platform × Feature Matrix

What works where:

| Feature | debian | rhel | alpine | arch | suse | macos |
|---------|--------|------|--------|------|------|-------|
| systemd | ✅ | ✅ | ❌ (OpenRC) | ✅ | ✅ | ❌ (launchd) |
| snap | ✅ | ⚠️ (installable) | ❌ | ⚠️ (AUR) | ❌ | ❌ |
| sudo | ✅ | ✅ | ⚠️ (often root) | ✅ | ✅ | ✅ |
| glibc | ✅ | ✅ | ❌ (musl) | ✅ | ✅ | ❌ (libSystem) |
| GUI terminals | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ (built-in) |
| pip (venv) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| npm | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ (via node) |
| cargo | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Docker | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ (Desktop) |
| Kernel config | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Pre-built binaries | ✅ | ✅ | ⚠️ (musl) | ✅ | ✅ | ✅ |

Legend: ✅ = full support, ⚠️ = works but with caveats, ❌ = not available

---

## How Recipes Use Platform Data

### Method selection (resolver logic)

```python
# System profile says:
primary_pm = system_profile["package_manager"]["primary"]  # "apt"
snap_ok = system_profile["package_manager"]["snap_available"]  # True
family = system_profile["distro"]["family"]  # "debian"

# Recipe says:
recipe["install"] = {"apt": [...], "snap": [...], "brew": [...]}
recipe["prefer"] = ["snap", "brew"]

# Resolver: _pick_install_method()
# 1. prefer: "snap" → snap_ok=True → pick "snap"
```

### Package name resolution

```python
# System profile says:
family = "debian"

# Recipe says:
recipe["requires"]["packages"] = {
    "debian": ["pkg-config", "libssl-dev"],
    "rhel":   ["pkgconf-pkg-config", "openssl-devel"],
    "alpine": ["pkgconf", "openssl-dev"],
}

# Resolver: use family as key → ["pkg-config", "libssl-dev"]
```

### Condition evaluation

```python
# System profile says:
capabilities = {"has_systemd": True, "is_root": False}
container = {"in_container": False}

# Recipe post_install says:
{"condition": "has_systemd"}  → True  → include step
{"condition": "not_root"}     → True  → include step
{"condition": "not_container"} → True → include step
```

---

## Edge Cases

### Unknown distro

If `distro.id` is not in `_FAMILY_MAP` and none of the `ID_LIKE`
values match, `family = "unknown"`.

The resolver handles this:
- `requires.packages` lookup for "unknown" returns `[]` (no match)
- System packages from recipes that don't have a family key are skipped
- pip/cargo/npm tools still work (they don't depend on family)
- The assistant panel warns: "Unknown distro family — some install
  options may not be available"

### ID_LIKE fallback

Many derivative distros set `ID_LIKE` in `/etc/os-release`:
```
# MX Linux:
ID=mx
ID_LIKE="debian"
```

The `_get_distro_family()` function tries `ID_LIKE` when `ID` isn't
in the map. This correctly maps MX Linux → debian.

### Multiple PM availability

Some systems have multiple PMs installed (e.g., Ubuntu with both
apt and brew). The resolver uses the PRIMARY PM. `prefer` in the
recipe can override this: kubectl prefers snap even when apt is primary.

---

## Traceability

| Section | Source |
|---------|--------|
| Family mapping | l0_detection.py `_FAMILY_MAP` (implemented) |
| Arch mapping | l0_detection.py `_ARCH_MAP` (implemented) |
| Package names per family | phase2.2 §1.3, §3 tool tables (analyzed) |
| Platform × feature matrix | phase1 §3.5-3.8, scope-expansion §2.7 |
| macOS specifics | phase1 §3.8 (implemented) |
| Alpine/musl | phase1 §3.7, scope-expansion §2.7 |
| Condition evaluation | phase2.3 §6 (designed) |
