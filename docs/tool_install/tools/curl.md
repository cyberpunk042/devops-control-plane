# Tool Spec Sheet: curl

> **Tool #1** | **Category:** `system` | **CLI binary:** `curl`
> **Date audited:** 2026-02-26
> **Workflows completed:** `/tool-coverage-audit` ✅ | `/tool-remediation-audit` ✅

---

## 1. Identity

| Field | Value |
|-------|-------|
| **Tool name** | curl |
| **Description** | Command-line tool and library for transferring data with URLs (HTTP, HTTPS, FTP, SCP, SFTP, etc.) |
| **Written in** | C |
| **CLI binary** | `curl` |
| **Upstream** | https://curl.se / https://github.com/curl/curl |
| **License** | MIT/X (curl license) |
| **Category** | `system` |
| **Importance** | Critical — dependency for virtually every `_default` install method in the recipe system. ~40+ recipes list `curl` in `requires.binaries`. |

---

## 2. Package Availability (`/tool-coverage-audit` Phase 2.2)

### 2.1 System package managers

| PM | Available | Package name | Dev package (libcurl) | Notes |
|----|-----------|-------------|----------------------|-------|
| `apt` | ✅ | `curl` | `libcurl4-openssl-dev` | Standard in all Debian/Ubuntu repos. Pre-installed on most full installs, NOT on minimal/Docker images. |
| `dnf` | ✅ | `curl` | `libcurl-devel` | Standard in all RHEL/Fedora repos. Pre-installed on full installs. |
| `apk` | ✅ | `curl` | `curl-dev` | NOT pre-installed on Alpine (it's a minimal distro). Also requires `ca-certificates` for HTTPS to work — Alpine does not ship CA certs by default. |
| `pacman` | ✅ | `curl` | Part of `curl` package | Pre-installed on Arch (core dependency of pacman itself). |
| `zypper` | ✅ | `curl` | `libcurl-devel` | Standard in openSUSE repos. |
| `brew` | ✅ | `curl` | N/A (headers in keg) | **Keg-only** — Homebrew installs to Cellar but does NOT symlink to PATH because macOS ships its own system curl. Homebrew curl lives at `/opt/homebrew/opt/curl/bin/curl` (ARM) or `/usr/local/opt/curl/bin/curl` (Intel). For most use cases, system curl is sufficient. |

### 2.2 Snap

| Available | Package | Confinement | Notes |
|-----------|---------|-------------|-------|
| ✅ | `curl` | **strict** | Strict confinement means snap curl can ONLY access non-hidden files in `$HOME`. Cannot write to arbitrary paths, cannot access dotfiles like `.curlrc`. Classic confinement request was denied upstream. **Not recommended as primary install method** — file system restrictions make it unsuitable for running `_default` install scripts that write to `/usr/local/bin` etc. |

### 2.3 Language ecosystem PMs

| PM | Available | Notes |
|----|-----------|-------|
| `pip` | ❌ | Not a Python package |
| `npm` | ❌ | Not a Node package (node-libcurl exists but is a different thing) |
| `cargo` | ❌ | Not a Rust crate |
| `go` | ❌ | Not a Go module |

### 2.4 Binary download — `_default` (`/tool-coverage-audit` Phase 2.3)

- curl does not publish pre-built binaries on GitHub — only source tarballs
- There is no installer script (curl itself is the download tool used by other installer scripts' `curl | bash` patterns)
- curl is available in every system PM across all 19 presets, so the native PM method is the primary install path on every system
- When curl is missing and another tool's `_default` install fails, the `missing_curl` handler in `METHOD_FAMILY_HANDLERS["_default"]` (line 542) detects this and offers to install curl automatically via the system PM

### 2.5 Build from source (`/tool-coverage-audit` Phase 2.4)

curl can be built from source using autotools.

| Field | Value |
|-------|-------|
| Build system | `autotools` (`./configure && make && make install`) |
| Git repo | https://github.com/curl/curl.git |
| Source tarballs | https://curl.se/download/curl-X.Y.Z.tar.gz |
| Branch | `master` (releases tagged as `curl-X_Y_Z`) |
| Build deps (binaries) | `make`, `gcc`, `autoconf`, `automake`, `libtool`, `pkg-config` |
| Build deps (libraries) | `openssl` (libssl-dev/openssl-devel/openssl-dev), `zlib` (zlib1g-dev/zlib-devel/zlib-dev) |
| Optional build deps | `libbrotli`, `libnghttp2`, `libssh2`, `zstd` |
| Install location | `/usr/local/bin/curl` (default prefix) |

#### ⚠️ Circular dependency: downloading the source

Building curl from source requires downloading the source code. This creates a chicken-and-egg problem:

| Download method | Requires | Problem |
|----------------|----------|---------|
| `git clone https://github.com/curl/curl.git` | `git` | git uses `libcurl` as its HTTPS transport on most Linux systems. If curl/libcurl is missing, `git clone https://` will fail. |
| `wget https://curl.se/download/curl-X.Y.Z.tar.gz` | `wget` | wget is independent of libcurl but is NOT available on all systems (missing on macOS, Alpine minimal, Arch minimal, many Docker images). |
| `python3 -c "urllib.request.urlretrieve(...)"` | `python3` | python3 urllib is independent of libcurl but is NOT available on all systems (missing on bare Alpine). |
| `curl -O https://curl.se/download/curl-X.Y.Z.tar.gz` | `curl` | This IS what we're trying to install. Not available. |

This is NOT a curl-specific problem. It applies to every tool that needs to download source or binaries. The solution is at the **infrastructure level** — a download backend cascade that tries available backends in order and uses the native PM as the base case to install missing backends.

See: `tool-install-v2-scope-expansion.md` section 9 — Download Backend Cascade.

The source method in the recipe uses `tarball_url` (instead of `git_repo`) to avoid the git→libcurl circular dependency. The actual download tool (curl/wget/python3) is resolved at execution time by the download backend infrastructure, not hardcoded in the recipe.

#### Source method recipe structure
```python
"source": {
    "build_system": "autotools",
    "tarball_url": "https://curl.se/download/curl-{version}.tar.gz",
    "default_version": "8.18.0",
    "requires_toolchain": ["make", "gcc", "autoconf", "automake", "libtool", "pkg-config"],
    "configure_args": ["--with-openssl", "--with-zlib"],
},
```

#### Required library dev packages for source build

| Family | Packages |
|--------|----------|
| `debian` | `libssl-dev`, `zlib1g-dev` |
| `rhel` | `openssl-devel`, `zlib-devel` |
| `alpine` | `openssl-dev`, `zlib-dev` |
| `arch` | `openssl`, `zlib` |
| `suse` | `libopenssl-devel`, `zlib-devel` |
| `macos` | `openssl@3`, `zlib` (via brew) |

---

## 3. Dependencies (`/tool-coverage-audit` Phase 2.5)

### 3.1 Runtime binary deps
None. curl is self-contained once installed.

### 3.2 Implicit runtime deps (system-level)

| Dep | Package (apt) | Package (apk) | Notes |
|-----|--------------|---------------|-------|
| `ca-certificates` | `ca-certificates` | `ca-certificates` | Required for HTTPS. On Alpine this is NOT pre-installed. On Debian/RHEL/Arch it IS. On macOS it's built into the system. This affects ALL tools using curl for `_default` downloads on bare Alpine containers. |
| `libcurl` | auto-pulled | auto-pulled | Shared library linked at package install time. Managed by the PM. |

### 3.3 Who depends on curl (reverse dependency)
curl is listed as a binary dependency (`requires.binaries`) by approximately 40+ other recipes for their `_default` install methods. It is the single most depended-upon tool in the entire recipe system.

---

## 4. Post-install (`/tool-coverage-audit` Phase 2.6)

| Item | Value |
|------|-------|
| PATH additions | None — PM puts it in `/usr/bin/curl` or equivalent |
| Shell config | None |
| Verify command | `curl --version` |

### macOS brew exception
Brew curl is keg-only. `curl --version` will still succeed because macOS system curl exists at `/usr/bin/curl`. The brew version at `/opt/homebrew/opt/curl/bin/curl` is only useful if the user explicitly wants a newer version. For verification purposes, system curl is sufficient — we verify `curl` on PATH, not brew's specific curl.

---

## 5. Per-system behavior across 19 presets

| Preset | Family | PM | curl method | Pre-installed? | Edge cases |
|--------|--------|-----|------------|----------------|------------|
| `debian_11` | debian | apt | `apt` | Yes (full), No (minimal) | |
| `debian_12` | debian | apt | `apt` | Yes (full), No (minimal) | |
| `docker_debian_12` | debian | apt | `apt` | **No** — Docker images are minimal | Must install explicitly |
| `ubuntu_2004` | debian | apt | `apt` or `snap` | Yes | snap strict confinement limits usage |
| `ubuntu_2204` | debian | apt | `apt` or `snap` | Yes | snap strict confinement limits usage |
| `ubuntu_2404` | debian | apt | `apt` or `snap` | Yes | snap strict confinement limits usage |
| `raspbian_bookworm` | debian | apt | `apt` | Yes | ARM — package is arch-universal |
| `wsl2_ubuntu_2204` | debian | apt | `apt` | Yes | |
| `fedora_39` | rhel | dnf | `dnf` | Yes | |
| `fedora_41` | rhel | dnf | `dnf` | Yes | |
| `centos_stream9` | rhel | dnf | `dnf` | Yes | |
| `rocky_9` | rhel | dnf | `dnf` | Yes | |
| `alpine_318` | alpine | apk | `apk` | **No** | Needs `ca-certificates` for HTTPS |
| `alpine_320` | alpine | apk | `apk` | **No** | Needs `ca-certificates` for HTTPS |
| `k8s_alpine_318` | alpine | apk | `apk` | **No** | Same as alpine_318 + read-only rootfs may block install |
| `opensuse_15` | suse | zypper | `zypper` | Yes | |
| `arch_latest` | arch | pacman | `pacman` | Yes (pacman depends on curl) | |
| `macos_13_x86` | macos | brew | `brew` (keg-only) | Yes — system curl at `/usr/bin/curl` | |
| `macos_14_arm` | macos | brew | `brew` (keg-only) | Yes — system curl at `/usr/bin/curl` | |

**Expected availability:** `ready` on all 19 presets via the primary PM. No `impossible` states. snap would show as `locked` on presets without snap, but the native PM method is always available.

---

## 6. Failure surface (`/tool-remediation-audit` Phase 1)

### 6.1 Install methods in recipe
- System PMs: `apt`, `dnf`, `apk`, `pacman`, `zypper`, `brew`, `snap`
- Source build: `source` (autotools — `./configure && make && make install`)
- No `_default` (no pre-built binaries published)
- No language ecosystem PMs (`pip`, `npm`, `cargo`, `go`)

### 6.2 Realistic failure scenarios

#### System PM failures

| Install method | Failure scenario | Stderr pattern |
|---------------|-----------------|----------------|
| `apt` | Package not found | `E: Unable to locate package curl` |
| `apt` | No sudo | `E: Could not open lock file /var/lib/dpkg/lock-frontend - open (13: Permission denied)` |
| `apt` | Network down | `Err:1 http://archive.ubuntu.com/ubuntu ... Could not resolve 'archive.ubuntu.com'` |
| `apt` | Disk full | `E: Write error - write (28: No space left on device)` |
| `apt` | Locked by another process | `E: Could not get lock /var/lib/dpkg/lock-frontend. It is held by process…` |
| `dnf` | Package not found | `No match for argument: curl` / `Error: Unable to find a match: curl` |
| `dnf` | No sudo | `Error: This command has to be run with superuser privileges` |
| `dnf` | Network down | `Error: Failed to download metadata for repo` / `Could not resolve host` |
| `dnf` | Disk full | `No space left on device` |
| `apk` | Package not found | `ERROR: unable to select packages: curl (no such package)` |
| `apk` | Unsatisfiable constraints | `ERROR: unsatisfiable constraints: curl-X.Y.Z-rN:` |
| `apk` | Network down | `ERROR: http://dl-cdn.alpinelinux.org/alpine/…: network error` / `temporary error (try again later)` |
| `apk` | Disk full | `No space left on device` |
| `apk` | Missing ca-certificates | `ERROR: http://dl-cdn.alpinelinux.org/… UNTRUSTED signature` (when HTTPS repos fail) |
| `pacman` | Package not found | `error: target not found: curl` |
| `pacman` | No sudo | `error: you cannot perform this operation unless you are root` |
| `pacman` | Network down | `error: failed to retrieve some files` / `Could not resolve host` |
| `pacman` | Dependency conflict | `error: failed to prepare transaction (could not satisfy dependencies)` |
| `pacman` | Disk full | `error: Partition / too full` / `No space left on device` |
| `zypper` | Package not found | `'curl' not found in package names.` / `No provider of 'curl' found.` |
| `zypper` | No sudo | `Root privileges are required for installing packages.` |
| `zypper` | Network down | `Download (curl) failed` / `Could not resolve host` |
| `zypper` | Disk full | `No space left on device` |
| `brew` | Formula not found | `Error: No available formula with the name "curl"` / `Error: No formulae found in taps.` |
| `brew` | Network down | `Error: Failure while executing; … curl: … Could not resolve host` |
| `brew` | Disk full | `No space left on device` |

#### Snap failures

| Failure scenario | Stderr pattern |
|-----------------|----------------|
| No systemd | `error: system does not fully support snapd: cannot mount squashfs image` |
| snapd not installed | `snap: command not found` / `error: the snapd daemon is not running` |
| Strict confinement blocks write | `Permission denied` (when snap curl tries to write outside `$HOME`) |
| Network down | `error: unable to contact snap store` |

#### Source build failures

| Failure scenario | Stderr pattern |
|-----------------|----------------|
| Missing C compiler | `cc: not found` / `gcc: not found` / `g++: not found` |
| Missing header (openssl) | `fatal error: openssl/ssl.h: No such file or directory` |
| Missing header (zlib) | `fatal error: zlib.h: No such file or directory` |
| configure fails (missing lib) | `configure: error: OpenSSL libs and/or directories were not found` |
| configure fails (missing tool) | `configure: error: cannot find required program: pkg-config` |
| make fails (link error) | `ld: cannot find -lssl` / `ld: cannot find -lz` |
| Disk full during build | `No space left on device` |
| Read-only rootfs (k8s) | `Read-only file system` (make install fails) |

#### Cross-method failures (all methods)

| Failure scenario | Stderr pattern |
|-----------------|----------------|
| Read-only rootfs | `Read-only file system` |
| Disk full | `No space left on device` |

---

## 7. Handler coverage (`/tool-remediation-audit` Phase 2)

### 7.1 Layer 1 — INFRA_HANDLERS (cross-method)

| Failure | Handler exists? | failure_id | Location |
|---------|----------------|------------|----------|
| Network unreachable | ✅ | `network_offline` | Line 720 |
| Download blocked (SSL/proxy) | ✅ | `network_blocked` | Line 757 |
| No sudo/permissions | ✅ | `no_sudo` | (in INFRA_HANDLERS) |
| Disk full | ✅ | `disk_full` | Line 788 |
| Read-only rootfs | ✅ | `read_only_rootfs` | (in INFRA_HANDLERS) |

All generic failures are covered by INFRA_HANDLERS.

### 7.2 Layer 2 — METHOD_FAMILY_HANDLERS

#### System PMs (`apt`, `dnf`, `apk`, `pacman`, `zypper`, `brew`)
All PM-specific failures (package not found, locked by another process, repo errors) are covered by INFRA_HANDLERS patterns that apply across all methods. No PM has curl-specific failures that would need a separate handler.

#### `snap`
snap failures (no systemd, snapd not running) are covered by the snap availability gate at the planning level. Strict confinement `Permission denied` errors are NOT explicitly handled — this is a known limitation documented in section 11.

#### `source`
Source build failures are handled by `METHOD_FAMILY_HANDLERS["source"]` (line 628-706):

| Failure | Handler | failure_id | Status |
|---------|---------|------------|--------|
| Missing C header | ✅ `missing_header` | `missing_header` | Line 632 — pattern: `fatal error:.*\.h:.*No such file` |
| Missing C compiler | ✅ `missing_compiler_source` | `missing_compiler_source` | Line 651 — pattern: `cc:.*not found\|g\+\+:.*not found\|gcc:.*not found` |
| CMake package missing | ✅ `cmake_package_not_found` | `cmake_package_not_found` | Line 676 — pattern: `could not find.*?package` |
| configure: error (missing lib) | ❌ **No handler** | — | `configure: error:` pattern not matched by any existing handler |
| Link error (ld: cannot find) | ❌ **No handler** | — | `ld: cannot find -l` pattern not matched |

**Gaps found:**
1. `missing_compiler_source` handler packages (line 665-671) are missing `macos` entry — should be `["gcc"]` (Xcode CLT provides gcc via brew or system)
2. No handler for `configure: error:` pattern — autotools configure failures fall through to unmatched
3. No handler for linker errors (`ld: cannot find -l`) — compilation link failures fall through

#### `_default` (curl as a dependency)
curl's role as a dependency for `_default` methods of OTHER tools is handled:
- `missing_curl` handler in `METHOD_FAMILY_HANDLERS["_default"]` (line 542)
- Options: "Install curl" (`install_dep`, dep=curl) or "Use wget instead" (`retry_with_modifier`)

### 7.3 Layer 3 — Recipe `on_failure`

curl has no unique tool-specific failure patterns that aren't covered by infrastructure or method-family handlers. No `on_failure` needed in recipe.

### 7.4 Handler summary

| Area | Status |
|------|--------|
| INFRA_HANDLERS | ✅ All generic failures covered |
| System PM handlers | ✅ Covered by INFRA_HANDLERS |
| `_default` dep handler | ✅ `missing_curl` exists |
| `source` handlers | ⚠️ 3 gaps (see below) |
| Recipe `on_failure` | ✅ Not needed |

#### Gaps to fix
| # | Gap | Fix | File |
|---|-----|-----|------|
| G1 | `missing_compiler_source` packages missing `macos` | Add `"macos": ["gcc"]` | `remediation_handlers.py` line 665 |
| G2 | No `configure: error:` handler in source family | Add handler with pattern `configure: error:` | `remediation_handlers.py` |
| G3 | No linker error handler in source family | Add handler with pattern `ld: cannot find -l` | `remediation_handlers.py` |

---

## 8. Availability gates (`/tool-remediation-audit` Phase 4)

### Current gates that apply to curl's methods

| Gate | Applies to | Behavior for curl |
|------|-----------|-------------------|
| Native PM gate | `apt`, `dnf`, `apk`, `pacman`, `zypper` | `impossible` if system doesn't have this PM → correct |
| Installable PM gate | `brew` | `locked` if brew not installed → correct |
| snap systemd gate | `snap` | `impossible` if no systemd → correct |
| Source toolchain gate | `source` | `locked` if any tool in `requires_toolchain` is not on PATH → correct (line 164-176 in `remediation_planning.py`) |

### New gates needed?
No new capability gates needed. curl's source method uses standard autotools toolchain which is already covered by the existing source toolchain gate. The requires_toolchain check in `_compute_availability()` will correctly flag `locked` when `make`, `gcc`, `autoconf`, `automake`, `libtool`, or `pkg-config` are missing.

---

## 9. Resolver data

### 9.1 KNOWN_PACKAGES (`dynamic_dep_resolver.py`)

| Entry | Status | Content |
|-------|--------|---------|
| `curl` | ✅ Exists (line 66-68) | `apt`=curl, `dnf`=curl, `apk`=curl, `pacman`=curl, `zypper`=curl, `brew`=curl |

No changes needed — package name is `curl` everywhere.

### 9.2 LIB_TO_PACKAGE_MAP (`remediation_handlers.py`)

| Entry | Status | Content |
|-------|--------|---------|
| `curl` | ✅ Complete (line 1080-1087) | `debian`=libcurl4-openssl-dev, `rhel`=libcurl-devel, `alpine`=curl-dev, `arch`=curl, `suse`=libcurl-devel, `macos`=curl |

`macos` entry was missing — added during this audit.

### 9.3 Special installers
None needed.

---

## 10. Recipe — before and after

### Before (partial)
```python
"curl": {
    "label": "curl",
    # MISSING: cli, category
    "install": {
        # MISSING: snap
        "apt": ..., "dnf": ..., "apk": ..., "pacman": ..., "zypper": ..., "brew": ...,
    },
    "needs_sudo": {
        # MISSING: snap
        "apt": True, "dnf": True, "apk": True,
        "pacman": True, "zypper": True, "brew": False,
    },
    "verify": ["curl", "--version"],
    "update": { ... },
}
```

### After (audited)
```python
"curl": {
    "cli": "curl",
    "label": "curl (URL transfer tool)",
    "category": "system",
    "install": {
        "apt":    ["apt-get", "install", "-y", "curl"],
        "dnf":    ["dnf", "install", "-y", "curl"],
        "apk":    ["apk", "add", "curl"],
        "pacman": ["pacman", "-S", "--noconfirm", "curl"],
        "zypper": ["zypper", "install", "-y", "curl"],
        "brew":   ["brew", "install", "curl"],
        "snap":   ["snap", "install", "curl"],
        "source": {
            "build_system": "autotools",
            "tarball_url": "https://curl.se/download/curl-{version}.tar.gz",
            "default_version": "8.18.0",
            "requires_toolchain": ["make", "gcc", "autoconf", "automake", "libtool", "pkg-config"],
            "configure_args": ["--with-openssl", "--with-zlib"],
        },
    },
    "needs_sudo": {
        "apt": True, "dnf": True, "apk": True,
        "pacman": True, "zypper": True, "brew": False,
        "snap": True, "source": True,
    },
    "requires": {
        "packages": {
            "debian": ["libssl-dev", "zlib1g-dev"],
            "rhel": ["openssl-devel", "zlib-devel"],
            "alpine": ["openssl-dev", "zlib-dev", "ca-certificates"],
            "arch": ["openssl", "zlib"],
            "suse": ["libopenssl-devel", "zlib-devel"],
            "macos": ["openssl@3"],
        },
    },
    "verify": ["curl", "--version"],
    "update": {
        "apt":    ["apt-get", "install", "--only-upgrade", "-y", "curl"],
        "dnf":    ["dnf", "upgrade", "-y", "curl"],
        "apk":    ["apk", "upgrade", "curl"],
        "pacman": ["pacman", "-S", "--noconfirm", "curl"],
        "zypper": ["zypper", "update", "-y", "curl"],
        "brew":   ["brew", "upgrade", "curl"],
    },
}
```

### Changes applied
| # | What | File |
|---|------|------|
| 1 | Added `"cli": "curl"` | `recipes.py` |
| 2 | Added `"category": "system"` | `recipes.py` |
| 3 | Updated `"label"` to be descriptive | `recipes.py` |
| 4 | Added `"snap"` install method | `recipes.py` |
| 5 | Added `"snap": True` to `needs_sudo` | `recipes.py` |
| 6 | Added `"source"` install method with autotools config | `recipes.py` |
| 7 | Added `"source": True` to `needs_sudo` | `recipes.py` |
| 8 | Added `"requires.packages"` for source build deps per family | `recipes.py` |
| 9 | Added `ca-certificates` to Alpine `requires.packages` | `recipes.py` |
| 10 | Added `"macos": "curl"` to LIB_TO_PACKAGE_MAP for curl | `remediation_handlers.py` |
| 11 | Added `"macos": ["gcc"]` to `missing_compiler_source` packages | `remediation_handlers.py` |
| 12 | Added `configure_error` handler to `METHOD_FAMILY_HANDLERS["source"]` | `remediation_handlers.py` |
| 13 | Added `linker_error` handler to `METHOD_FAMILY_HANDLERS["source"]` | `remediation_handlers.py` |

---

## 11. Outstanding items for future consideration

| Item | Priority | Notes |
|------|----------|-------|
| Alpine `ca-certificates` dep (system-wide) | Medium | Curl on Alpine requires `ca-certificates` for HTTPS. Added to Alpine `requires.packages` for this recipe. This same dependency applies to ALL tools that make HTTPS connections on bare Alpine — may warrant an infrastructure-level gate or prerequisite check that applies system-wide, not just in the curl recipe. |
| Snap strict confinement | Medium | Snap curl has strict confinement: can only access non-hidden files in `$HOME`. When snap curl is used by another tool's `_default` install script that writes to `/usr/local/bin`, it will get `Permission denied`. No handler exists for this specific error — it falls through to generic `Permission denied`. The remediation system offers snap as an install method but the native PM method will always be available alongside it. |

---

## 12. Validation results (resweep 2026-02-26)

### 12.1 Recipe schema validation

```
curl recipe: VALID
```

Recipe passes all new validators:
- Source method sub-schema (build_system, tarball_url, default_version, requires_toolchain, configure_args)
- Per-strategy option validation on all handler registries
- No unknown fields, no missing required fields

### 12.2 Method availability across 19 presets

Every preset has at least ONE ready native PM + source as fallback:

| Preset | Ready PM | snap | brew | source |
|--------|----------|------|------|--------|
| ubuntu_2004/2204/2404 | apt | ✅ ready | 🔒 locked | ✅ ready |
| debian_11/12 | apt | 🔒 locked | 🔒 locked | ✅ ready |
| raspbian_bookworm | apt | ✅ ready | 🔒 locked | ✅ ready |
| wsl2_ubuntu_2204 | apt | ✅ ready | 🔒 locked | ✅ ready |
| fedora_39/41 | dnf | 🔒 locked | 🔒 locked | ✅ ready |
| centos_stream9 | dnf | 🔒 locked | 🔒 locked | ✅ ready |
| rocky_9 | dnf | 🔒 locked | 🔒 locked | ✅ ready |
| alpine_318/320 | apk | ❌ impossible | 🔒 locked | ✅ ready |
| arch_latest | pacman | 🔒 locked | 🔒 locked | ✅ ready |
| opensuse_15 | zypper | 🔒 locked | 🔒 locked | ✅ ready |
| macos_13_x86/14_arm | brew | ❌ impossible | ✅ ready | ✅ ready |
| docker_debian_12 | apt | ❌ impossible | 🔒 locked | ✅ ready |
| k8s_alpine_318 | apk | ❌ impossible | 🔒 locked | ✅ ready |

No false impossibles. No missing methods.

### 12.3 Remediation handler coverage (6 failure scenarios × 8 presets)

| Scenario | Stderr | Handler | Options (ready) |
|----------|--------|---------|-----------------|
| Missing compiler | `cc: not found` | `missing_compiler_source` | Install build tools |
| Missing header | `fatal error: openssl/ssl.h: No such file` | `missing_header` | Install development packages |
| Configure error | `configure: error: OpenSSL libs…` | `configure_error` | Install dev libraries, Check config.log |
| Linker error | `ld: cannot find -lssl` | `linker_error` | Install library dev package |
| Network offline | `Could not resolve host` | `network_offline` | Check connectivity, Retry |
| Disk full | `No space left on device` | `disk_full` | Clean caches, Prune Docker, Check disk |

All 6 scenarios matched handlers on all 8 representative presets.
k8s_alpine_318 correctly shows empty ready list for install_packages (read-only rootfs).

### 12.4 Chain model / unlock preview

Tested: helm → missing curl on docker_debian_12.
- 3 ready options: Install curl, Use wget, Use python3 urllib
- Chain depth 0, max_depth 5
- `requires_binary` gates work: wget and python3 options correctly gated
- Unlock preview appears on locked options only (not on ready ones — correct)
- Cycle detection: if curl already in chain breadcrumbs, circular dep detected

### 12.5 Gaps resolved (from section 7.4)

| Gap | Status |
|-----|--------|
| G1: `missing_compiler_source` missing `macos` | ✅ Fixed — `"macos": ["gcc"]` at line 685 |
| G2: No `configure: error:` handler | ✅ Fixed — `configure_error` handler at line 722 |
| G3: No linker error handler | ✅ Fixed — `linker_error` handler at line 765 |

### 12.6 Doc consistency

| Field | Recipe | Doc (section 10) | Match? |
|-------|--------|-------------------|--------|
| `configure_args` | ✅ `configure_args` | ✅ `configure_args` | **Fixed** — was `configure_flags`, corrected during resweep |

All doc examples now match the actual recipe and schema.

