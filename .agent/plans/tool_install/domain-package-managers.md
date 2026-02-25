# Domain: Package Managers (System)

> ⚠️ **PHASE LABELS MAY BE STALE** — As of 2026-02-25, code has evolved far beyond
> what the phase roadmaps suggest. Many features labeled "Phase 4-8 future" are
> ALREADY IMPLEMENTED. See `audit-domain-docs.md` and `audit-missing-pieces.md`
> for the verified truth. Code is the source of truth, not these phase labels.


> This document catalogs every system-level package manager the
> tool install system handles, how each is detected, its commands,
> flags, naming conventions, repo setup, update, and remove mechanics.
>
> SOURCE CODE: l0_detection.py `_detect_package_managers()` (implemented),
>              tool_install.py `check_system_deps()` (implemented)
> SOURCE DOCS: phase2.1 (full PM analysis), phase2.2 (recipe format),
>              phase2.3 (resolver method selection, batching),
>              domain-platforms (family×PM mapping)

---

## Detection

PM detection is part of the FAST TIER (< 5ms total).
Implemented in `_detect_package_managers()`:

```python
"package_manager": {
    "primary": str,          # first available: "apt"|"dnf"|"yum"|"apk"
                             #   |"pacman"|"zypper"|"brew"|"none"
    "available": list[str],  # all detected PMs on this system
    "snap_available": bool,  # snap binary exists AND has_systemd
}
```

### Detection order (priority)

```python
_PM_BINARIES = [
    ("apt",    "apt-get"),
    ("dnf",    "dnf"),
    ("yum",    "yum"),
    ("apk",    "apk"),
    ("pacman", "pacman"),
    ("zypper", "zypper"),
    ("brew",   "brew"),
]
```

First found = primary. All found = available list.

**Why this order?**
- apt first: most common Linux (Debian/Ubuntu dominant)
- dnf before yum: modern RHEL systems have both (yum→dnf symlink)
- brew last: only relevant if no native PM found (macOS) or
  user installed Linuxbrew alongside native PM

### Snap detection

Snap requires special handling:
```python
snap_available = shutil.which("snap") is not None and has_systemd
```

Snap BINARY may exist but snap DAEMON (snapd) needs systemd.
Without systemd, snap install commands fail. This includes:
- WSL1 (no systemd)
- WSL2 without `systemd=true`
- Docker containers
- Alpine (no systemd)

---

## Package Manager Reference

### apt (Debian family)

| Property | Value |
|----------|-------|
| **Family** | debian |
| **Distros** | Ubuntu, Debian, Mint, Pop!_OS, Kali, Raspbian, Deepin, Zorin, Elementary |
| **Binary** | `apt-get` (for scripting; `apt` is for interactive use) |
| **Install** | `apt-get install -y PKG1 PKG2 ...` |
| **Check** | `dpkg-query -W -f='${Status}' PKG` → "install ok installed" |
| **Update pkg** | `apt-get install --only-upgrade -y PKG` |
| **Remove** | `apt-get remove -y PKG` (keeps config), `apt-get purge -y PKG` (removes config) |
| **Refresh index** | `apt-get update` |
| **Needs sudo** | Yes (unless root) |
| **Auto-yes flag** | `-y` |
| **Performance** | Check: ~5ms/pkg, Install: depends on download |

**Specific behaviors:**
- `apt-get` is preferred over `apt` for scripting (stable output format)
- Package index (`/var/lib/apt/lists/`) can go stale in containers
- May need `apt-get update` before install in fresh containers
- Current decision: don't auto-update; suggest on failure
- Resolves own dependencies (installing libssl-dev pulls libssl3, perl, etc.)
- Exit codes: 0=success, 100=package not found

**Check edge cases:**
- `deinstall ok config-files` → removed but config remains → NOT installed ✅
- `install ok half-configured` → broken install → NOT installed ✅
- Virtual packages → `dpkg-query` doesn't resolve them → NOT found ✅
  (We use concrete package names in recipes, never virtuals)

### dnf (RHEL family — modern)

| Property | Value |
|----------|-------|
| **Family** | rhel |
| **Distros** | Fedora (22+), RHEL (8+), Rocky, Alma, Amazon Linux 2023 |
| **Binary** | `dnf` |
| **Install** | `dnf install -y PKG1 PKG2 ...` |
| **Check** | `rpm -q PKG` → exit 0 if installed |
| **Update pkg** | `dnf upgrade -y PKG` |
| **Remove** | `dnf remove -y PKG` |
| **Refresh index** | Auto-refreshes if stale (unlike apt) |
| **Needs sudo** | Yes (unless root) |
| **Auto-yes flag** | `-y` |
| **Performance** | Check: ~3ms/pkg |

**Specific behaviors:**
- dnf automatically refreshes metadata when stale
- Uses rpm database underneath (check always via `rpm -q`)
- dnf5 (Fedora 39+) is a C++ rewrite, same CLI interface
- Module streams: some packages have multiple versions via dnf modules
  (e.g., `dnf module enable nodejs:18`). Not used in Phase 2 recipes.

### yum (RHEL family — legacy)

| Property | Value |
|----------|-------|
| **Family** | rhel |
| **Distros** | CentOS 7, RHEL 7, Amazon Linux 2 |
| **Binary** | `yum` |
| **Install** | `yum install -y PKG1 PKG2 ...` |
| **Check** | `rpm -q PKG` (same as dnf) |
| **Update pkg** | `yum update -y PKG` |
| **Needs sudo** | Yes |
| **Auto-yes flag** | `-y` |

**Specific behaviors:**
- On modern systems (Fedora 22+, RHEL 8+), `yum` is a symlink to `dnf`
- Detection priority: dnf before yum ensures we use dnf when available
- Yum is Python 2-based, slower than dnf
- Package names identical to dnf (same RHEL family naming)

### apk (Alpine)

| Property | Value |
|----------|-------|
| **Family** | alpine |
| **Distros** | Alpine, postmarketOS |
| **Binary** | `apk` |
| **Install** | `apk add PKG1 PKG2 ...` |
| **Check** | `apk info -e PKG` → exit 0 if installed |
| **Update pkg** | `apk upgrade PKG` |
| **Remove** | `apk del PKG` |
| **Refresh index** | `apk update` |
| **Needs sudo** | Yes (but Alpine containers usually root) |
| **Auto-yes flag** | None needed (apk doesn't prompt) |
| **Performance** | Check: ~2ms/pkg (fastest) |

**Specific behaviors:**
- No `-y` flag because apk never prompts interactively
- Alpine uses musl libc (affects package naming: `musl-dev` not `libc6-dev`)
- Very fast package management (simple text database)
- May need `apk update` in minimal containers
- Virtual packages (`.build-deps`) handled differently, not used here

### pacman (Arch family)

| Property | Value |
|----------|-------|
| **Family** | arch |
| **Distros** | Arch, Manjaro, EndeavourOS |
| **Binary** | `pacman` |
| **Install** | `pacman -S --noconfirm PKG1 PKG2 ...` |
| **Check** | `pacman -Q PKG` → exit 0 if installed |
| **Update pkg** | `pacman -Syu --noconfirm PKG` |
| **Remove** | `pacman -R --noconfirm PKG` |
| **Refresh index** | `pacman -Sy` |
| **Needs sudo** | Yes |
| **Auto-yes flag** | `--noconfirm` |
| **Performance** | Check: ~5ms/pkg |

**Specific behaviors:**
- Package names are case-sensitive
- Arch often bundles headers with main package (no `-dev` split)
  e.g., `openssl` on Arch includes headers, vs `libssl-dev` on Debian
- Rolling release: always latest versions
- AUR (Arch User Repository) is community-maintained; we do NOT use it
  (too risky, requires makepkg, not suitable for automated install)
- Use `-Q` (lighter) not `-Qi` (info) — we only need presence check

### zypper (SUSE family)

| Property | Value |
|----------|-------|
| **Family** | suse |
| **Distros** | openSUSE Leap, openSUSE Tumbleweed, SLES |
| **Binary** | `zypper` |
| **Install** | `zypper install -y PKG1 PKG2 ...` |
| **Check** | `rpm -q PKG` (shares rpm DB with dnf/yum) |
| **Update pkg** | `zypper update -y PKG` |
| **Remove** | `zypper remove -y PKG` |
| **Refresh index** | Auto-refreshes if needed |
| **Needs sudo** | Yes |
| **Auto-yes flag** | `-y` (or `--non-interactive`) |
| **Performance** | Check: ~3ms (rpm DB) |

**Specific behaviors:**
- Uses rpm database (same check as dnf/yum)
- Package names sometimes differ from Fedora:
  `libopenssl-devel` (SUSE) vs `openssl-devel` (Fedora)
- zypper only needed for INSTALLING; checking uses `rpm -q`

### brew (macOS + Linuxbrew)

| Property | Value |
|----------|-------|
| **Family** | macos (also optional on Linux) |
| **Distros** | macOS (primary), any Linux via Linuxbrew |
| **Binary** | `brew` |
| **Install** | `brew install PKG1 PKG2 ...` |
| **Check** | `brew ls --versions PKG` → exit 0 if installed |
| **Update pkg** | `brew upgrade PKG` |
| **Remove** | `brew uninstall PKG` |
| **Refresh index** | `brew update` (auto-runs before install) |
| **Needs sudo** | **No** (brew is user-space) |
| **Auto-yes flag** | None needed |
| **Performance** | Check: 50-500ms/pkg (**10-100x slower** than native PMs) |

**Specific behaviors:**
- brew is a Ruby application → high startup overhead
- `HOMEBREW_NO_AUTO_UPDATE=1` skips auto-update before install (saves 5-30s)
- Formulae (CLI tools) vs Casks (GUI apps): `brew install --cask docker`
- Keg-only packages: installed but not linked to PATH (headers still usable)
- Apple Silicon (arm64): prefix is `/opt/homebrew/` (not `/usr/local/`)
- Intel Mac: prefix is `/usr/local/`
- `brew ls --versions PKG` is faster than `brew list PKG`
- For batch checking: `brew ls --versions pkg1 pkg2` returns per-line;
  exit 0 only if ALL found. Parse per-line for individual status.
- 30s timeout for checks (10s is too aggressive for brew)

### snap

| Property | Value |
|----------|-------|
| **Not a primary PM** | Detected separately, requires systemd |
| **Binary** | `snap` |
| **Install** | `snap install PKG` or `snap install PKG --classic` |
| **Check** | `snap list PKG` → exit 0 if installed |
| **Update pkg** | `snap refresh PKG` |
| **Remove** | `snap remove PKG` |
| **Needs sudo** | Yes |
| **Confinement** | `strict` (sandboxed) or `classic` (full access) |

**Specific behaviors:**
- Requires systemd (snapd daemon)
- Auto-updates in background (no manual refresh needed, but can force)
- `--classic` flag needed for tools that need filesystem access (kubectl, go)
- Snap packages include all dependencies (no dpkg/rpm dep resolution)
- Larger disk usage than native packages
- Can coexist with system PM (both apt and snap on Ubuntu)

**Detection condition:**
```python
snap_available = shutil.which("snap") is not None and has_systemd
```

---

## PM-to-Checker Mapping

The CHECK command is NOT always the same binary as the INSTALL command:

| PM | Checker binary | Check command | Install binary |
|----|---------------|--------------|---------------|
| apt | `dpkg-query` | `dpkg-query -W -f='${Status}' PKG` | `apt-get` |
| dnf | `rpm` | `rpm -q PKG` | `dnf` |
| yum | `rpm` | `rpm -q PKG` | `yum` |
| zypper | `rpm` | `rpm -q PKG` | `zypper` |
| apk | `apk` | `apk info -e PKG` | `apk` |
| pacman | `pacman` | `pacman -Q PKG` | `pacman` |
| brew | `brew` | `brew ls --versions PKG` | `brew` |
| snap | `snap` | `snap list PKG` | `snap` |

**Key insight:** Three PMs (dnf, yum, zypper) share `rpm` for checking.
This means the checker is always available when the PM is installed,
since rpm is a dependency of all three.

---

## PM-to-Install Command Mapping

Used by `_build_pkg_install_cmd()`:

```python
def _build_pkg_install_cmd(packages: list[str], pm: str) -> list[str]:
    if pm == "apt":    return ["apt-get", "install", "-y"] + packages
    if pm == "dnf":    return ["dnf", "install", "-y"] + packages
    if pm == "yum":    return ["yum", "install", "-y"] + packages
    if pm == "zypper": return ["zypper", "install", "-y"] + packages
    if pm == "apk":    return ["apk", "add"] + packages
    if pm == "pacman": return ["pacman", "-S", "--noconfirm"] + packages
    if pm == "brew":   return ["brew", "install"] + packages
```

**Batching:** All PMs support installing multiple packages in one command.
The resolver batches system packages into a single step:
```
apt-get install -y curl pkg-config libssl-dev
```
Not three separate `apt-get install` calls.

---

## Package Naming Across PMs

The SAME library has DIFFERENT names on different distros.
Recipes key names by distro FAMILY (not PM):

| Library | debian | rhel | alpine | arch | suse | macos |
|---------|--------|------|--------|------|------|-------|
| OpenSSL dev | `libssl-dev` | `openssl-devel` | `openssl-dev` | `openssl` | `libopenssl-devel` | `openssl@3` |
| pkg-config | `pkg-config` | `pkgconf-pkg-config` | `pkgconf` | `pkgconf` | `pkg-config` | `pkg-config` |
| curl dev | `libcurl4-openssl-dev` | `libcurl-devel` | `curl-dev` | `curl` | `libcurl-devel` | `curl` |
| DNS tools | `dnsutils` | `bind-utils` | `bind-tools` | `bind` | `bind-utils` | `bind` |
| C library dev | `libc6-dev` | `glibc-devel` | `musl-dev` | `glibc` | `glibc-devel` | (included by Xcode) |

**Naming conventions by family:**

| Family | Dev package pattern | Example |
|--------|-------------------|---------|
| debian | `libFOO-dev` | `libssl-dev`, `libcurl4-openssl-dev` |
| rhel | `FOO-devel` | `openssl-devel`, `libcurl-devel` |
| alpine | `FOO-dev` | `openssl-dev`, `curl-dev` |
| arch | `FOO` (headers included) | `openssl`, `curl` |
| suse | `libFOO-devel` or `FOO-devel` | `libopenssl-devel` |
| macos | brew formula name | `openssl@3`, `pkg-config` |

### Two lookup axes

```
install key  → PM    → HOW to install  (apt-get install vs dnf install)
requires key → family → WHAT to install (libssl-dev vs openssl-devel)
```

These CORRELATE but are NOT the same:

| Family | PM(s) | Recipe install key | Recipe requires key |
|--------|-------|-------------------|-------------------|
| debian | apt | `"apt"` | `"debian"` |
| rhel | dnf, yum | `"dnf"` / `"yum"` | `"rhel"` |
| alpine | apk | `"apk"` | `"alpine"` |
| arch | pacman | `"pacman"` | `"arch"` |
| suse | zypper | `"zypper"` | `"suse"` |
| macos | brew | `"brew"` | `"macos"` |

---

## Update Commands

| PM | Update single package | Update all packages |
|----|----------------------|-------------------|
| apt | `apt-get install --only-upgrade -y PKG` | `apt-get upgrade -y` |
| dnf | `dnf upgrade -y PKG` | `dnf upgrade -y` |
| yum | `yum update -y PKG` | `yum update -y` |
| apk | `apk upgrade PKG` | `apk upgrade` |
| pacman | `pacman -Syu --noconfirm PKG` | `pacman -Syu --noconfirm` |
| zypper | `zypper update -y PKG` | `zypper update -y` |
| brew | `brew upgrade PKG` | `brew upgrade` |
| snap | `snap refresh PKG` | `snap refresh` |

**apt specifics:** `apt-get install --only-upgrade -y PKG` only
upgrades if already installed. It does NOT install if missing.

---

## Repo Setup

Some tools aren't in default repos. Recipe `repo_setup` handles this:

| Tool | PM | Repo setup needed |
|------|-----|-------------------|
| docker-ce | apt | Add Docker GPG key + sources.list entry + `apt-get update` |
| docker-ce | dnf | Add docker-ce repo file |
| gh (GitHub CLI) | apt | Add GitHub GPG key + sources.list entry |
| kubernetes tools | apt | Add Google Cloud GPG key + sources.list entry |

**repo_setup format (from arch-recipe-format):**
```python
"repo_setup": {
    "apt": [
        {"label": "Add Docker GPG key",
         "command": ["bash", "-c", "curl -fsSL ... | gpg --dearmor -o ..."],
         "needs_sudo": True},
        {"label": "Add Docker repo",
         "command": ["bash", "-c", "echo 'deb ...' > /etc/apt/sources.list.d/..."],
         "needs_sudo": True},
        {"label": "Update package index",
         "command": ["apt-get", "update"],
         "needs_sudo": True},
    ],
}
```

Repo setup steps run BEFORE the install command.
Only populated for tools that actually need non-default repos.
Most tools in Phase 2 use default repos.

---

## Sudo Requirements

| PM | Needs sudo? | Exception |
|----|------------|-----------|
| apt | Yes | Running as root → no sudo needed |
| dnf | Yes | Running as root |
| yum | Yes | Running as root |
| apk | Yes | Running as root (Alpine containers usually root) |
| pacman | Yes | Running as root |
| zypper | Yes | Running as root |
| brew | **No** | brew is user-space, NEVER needs sudo |
| snap | Yes | Running as root |

**brew exception:** The resolver sets `needs_sudo: False` for ALL
brew operations. This is hardcoded in recipes.

**Root handling:** The resolver still sets `needs_sudo: True` for
PM install steps (declaring the step needs elevated privileges).
The EXECUTOR strips the sudo prefix when running as root. This
separation is intentional (arch-principles §: resolver declares,
executor adapts).

---

## Error Handling

### Checker errors

```python
try:
    result = subprocess.run(checker_cmd, capture_output=True, timeout=10)
except FileNotFoundError:
    # Checker binary not on PATH (e.g., dpkg-query on Fedora)
    return False  # treat as "not installed"
except subprocess.TimeoutExpired:
    return False  # treat as "not installed"
except OSError:
    return False  # treat as "not installed"
```

**Safe default:** Any error = treat as NOT installed. This means
the resolver may try to install something that's already present,
but that's harmless (PMs handle re-install gracefully).

### Install errors

Common failure modes per PM:

| PM | Common error | Cause | Mitigation |
|----|-------------|-------|-----------|
| apt | "Unable to locate package" | Stale package index | `apt-get update` first |
| apt | "Could not get lock" | Another apt process running | Wait and retry |
| dnf | "No match for argument" | Package name wrong for this distro | Recipe naming error |
| apk | "unsatisfiable constraints" | Package not in repos | Need community repo? |
| pacman | "target not found" | Package name case mismatch | Case-sensitive names |
| brew | "No formulae found" | Typo or private tap needed | Check formula name |

---

## Performance

| PM | Check time (per pkg) | Install overhead | Notes |
|----|---------------------|-----------------|-------|
| apt | ~5ms | 2-30s | dpkg DB is disk-based |
| dnf/yum | ~3ms | 2-30s | rpm DB is binary, fast |
| apk | ~2ms | 1-10s | Alpine is minimal, fast |
| pacman | ~5ms | 2-30s | Local DB query |
| zypper | ~3ms | 2-30s | Same rpm DB |
| brew | **50-500ms** | 5-60s | Ruby startup overhead |

**brew is the outlier.** Checking 6 packages on brew = 300ms-3s.
The resolver uses a 30s timeout for brew checks.

✅ **IMPLEMENTED (L4):** Batch check with
`brew ls --versions pkg1 pkg2 pkg3` in a single call.

---

## Traceability

| Topic | Source |
|-------|--------|
| Detection code | l0_detection.py `_detect_package_managers()` (lines 219-245) |
| Check implementation | phase2.1 §5.1 `_is_pkg_installed()` (designed) |
| Install command builder | phase2.1 §5.3 `_build_pkg_install_cmd()` (designed) |
| PM detection order | l0_detection.py `_PM_BINARIES` (implemented) |
| Snap detection | l0_detection.py line 238 (implemented) |
| Package naming tables | phase2.2 §system packages analysis |
| Resolver method selection | phase2.3 §3 `_pick_install_method()` |
| Batching logic | phase2.3 §7.1 (package batching) |
| Family→PM mapping | domain-platforms (DONE) |
| brew performance | phase2.1 §2.6 (brew analysis) |
| Repo setup format | arch-recipe-format §repo_setup |
