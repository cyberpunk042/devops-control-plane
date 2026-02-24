# Phase 2.1 — Multi-Distro Package Checking — Full Analysis

## What This Sub-Phase Delivers

Three things:
1. **Check if a system package is installed** on any distro (not just Debian)
2. **Build the install command** for a list of packages on any distro
3. **Expose this** through the existing `/audit/check-deps` endpoint

---

## 1. What Exists Today

### 1.1 `check_system_deps()` — lines 91-104 of `tool_install.py`

```python
def check_system_deps(packages: list[str]) -> dict:
    """Check which apt packages are installed. Returns {missing: [...], installed: [...]}."""
    missing = []
    installed = []
    for pkg in packages:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Status}", pkg],
            capture_output=True, text=True,
        )
        if "install ok installed" in result.stdout:
            installed.append(pkg)
        else:
            missing.append(pkg)
    return {"missing": missing, "installed": installed}
```

Problems:
- Uses `dpkg-query` — Debian/Ubuntu ONLY
- No timeout — could hang on broken dpkg database
- No error handling for `dpkg-query` not being on PATH
- Called from `_remExecute` in `_globals.html` via `/audit/check-deps`
- Called from `_analyse_install_failure()` to populate `system_deps` on remediation options

### 1.2 `CARGO_BUILD_DEPS` — line 88

```python
CARGO_BUILD_DEPS = ["pkg-config", "libssl-dev", "libcurl4-openssl-dev"]
```

These are **Debian package names**. On Fedora they're `pkgconf-pkg-config`,
`openssl-devel`, `libcurl-devel`. On Alpine they're `pkgconf`, `openssl-dev`,
`curl-dev`. This constant is used in `_analyse_install_failure()` to
populate the `system_deps` field of remediation options.

### 1.3 `/audit/check-deps` endpoint — routes_audit.py lines 295-305

```python
@audit_bp.route("/audit/check-deps", methods=["POST"])
def audit_check_deps():
    body = request.get_json(silent=True) or {}
    packages = body.get("packages", [])
    if not packages:
        return jsonify({"missing": [], "installed": []}), 200
    result = check_system_deps(packages)
    return jsonify(result), 200
```

Frontend call (from `_remExecute` in `_globals.html` line ~1122):
```javascript
var depRes = await fetch('/api/audit/check-deps', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ packages: opt.system_deps }),
});
```

The frontend sends Debian package names (because `CARGO_BUILD_DEPS`
has Debian names) and the backend checks with `dpkg-query`.

### 1.4 Who calls what — complete call chain

```
Frontend: _remExecute()
  → opt.system_deps (from remediation options)
    → these come from _analyse_install_failure()
      → which uses CARGO_BUILD_DEPS (Debian names)
  → POST /api/audit/check-deps { packages: ["pkg-config", "libssl-dev", ...] }
    → check_system_deps(packages)
      → dpkg-query for each package
  → if missing: show _showDepsModal()
    → user clicks install
      → POST /api/audit/remediate { override_command: "apt-get install -y ..." }
```

Everything in this chain is Debian-specific:
- Package NAMES are Debian names
- Package CHECK uses dpkg-query
- Package INSTALL uses apt-get

---

## 2. How Package Checking Works Per Package Manager

### 2.1 apt (Debian, Ubuntu, Mint, Pop!_OS, Kali, Raspberry Pi OS)

**Check command:** `dpkg-query -W -f='${Status}' PACKAGE`

**Output on installed:**
```
install ok installed
```
Exit code: 0

**Output on NOT installed:**
```
dpkg-query: no packages found matching PACKAGE
```
Exit code: 1

**Edge cases:**
- Package might be in state `deinstall ok config-files` — this means it was
  removed but config files remain. It is NOT functionally installed.
  The string "install ok installed" correctly excludes this case.
- Package might be in state `install ok half-configured` — broken install.
  The status string won't match "install ok installed" — correct behavior,
  treats it as missing.
- Virtual packages (e.g. `libgl-dev` provided by `libgl1-mesa-dev`):
  `dpkg-query` does NOT resolve virtual packages. It will say "not found"
  even if a provider is installed. For our use case this is acceptable
  because we always specify concrete package names in recipes.
- `dpkg-query` binary might not exist if dpkg is somehow missing on a
  Debian system — extremely unlikely but we should handle OSError.

**Performance:** ~5ms per package (reads dpkg database from disk).

**Prerequisite binary:** `dpkg-query` (part of `dpkg`, always present on
any apt-based system).

### 2.2 dnf / yum (Fedora, RHEL, CentOS, Rocky, Alma, Amazon Linux)

**Check command:** `rpm -q PACKAGE`

**Output on installed:**
```
PACKAGE-VERSION-RELEASE.ARCH
```
e.g. `openssl-devel-3.0.7-18.el9.x86_64`
Exit code: 0

**Output on NOT installed:**
```
package PACKAGE is not installed
```
Exit code: 1

**Edge cases:**
- dnf and yum both use the rpm database underneath. The check is the same
  for both: `rpm -q`. The INSTALL command differs (dnf vs yum) but the
  CHECK is always `rpm -q`.
- zypper (openSUSE/SUSE) ALSO uses rpm underneath. Same check command.
- `rpm -q` handles multiple packages: `rpm -q pkg1 pkg2 pkg3` — but exit
  code is 0 only if ALL are found. For per-package checking, we query
  one at a time.
- Virtual packages / "provides": `rpm -q` checks exact package names.
  `rpm -q --whatprovides CAPABILITY` checks provides, but we use exact names.
- `rpm` binary might not exist on a Debian system — must handle OSError.

**Performance:** ~3ms per package (rpm database is binary, fast lookup).

**Prerequisite binary:** `rpm` (always present on any RPM-based system).

### 2.3 apk (Alpine Linux, postmarketOS)

**Check command:** `apk info -e PACKAGE`

**Output on installed:**
```
PACKAGE
```
(just the package name, no version)
Exit code: 0

**Output on NOT installed:**
(empty stdout)
Exit code: 1

**Edge cases:**
- Alpine uses musl libc, not glibc. Some packages have different names
  than their glibc counterparts (e.g. `musl-dev` instead of `libc6-dev`).
  This is a recipe concern, not a checking concern.
- Virtual packages: `apk info -e` checks exact package names. Virtual
  packages like `.build-deps` are handled differently and not relevant here.
- apk is fast — Alpine's package database is simple.
- `apk` binary might not exist on non-Alpine systems — must handle OSError.

**Performance:** ~2ms per package (simple text database).

**Prerequisite binary:** `apk` (only on Alpine).

### 2.4 pacman (Arch Linux, Manjaro, EndeavourOS)

**Check command:** `pacman -Qi PACKAGE`

**Output on installed:**
```
Name            : PACKAGE
Version         : X.Y.Z-N
Description     : ...
... (many fields)
```
Exit code: 0

**Output on NOT installed:**
```
error: package 'PACKAGE' was not found
```
Exit code: 1

**Edge cases:**
- pacman package names are case-sensitive. Recipe names must match exactly.
- Arch sometimes splits packages differently than Debian. For example,
  Debian's `libssl-dev` is `openssl` on Arch (the main package includes
  headers).
- `pacman -Q PACKAGE` (without `i`) is lighter — just checks if installed.
  We should use `-Q` not `-Qi` since we only need presence, not info.

**Performance:** ~5ms per package (local database query).

**Prerequisite binary:** `pacman` (only on Arch-based).

### 2.5 zypper (openSUSE, SUSE Linux Enterprise)

**Check command:** `rpm -q PACKAGE` (same as dnf/yum — uses rpm database)

**Output:** Same as 2.2.

**Edge cases:**
- Same as dnf/yum since they share the rpm database format.
- SUSE package names sometimes differ from Fedora names. For example,
  `libopenssl-devel` on SUSE vs `openssl-devel` on Fedora. This is a
  recipe concern.
- zypper itself is only needed for INSTALLING, not for CHECKING.

**Prerequisite binary:** `rpm` (always present on any SUSE system).

### 2.6 brew (macOS, Linux Homebrew)

**Check command:** `brew list PACKAGE`

**Output on installed:**
```
/usr/local/Cellar/PACKAGE/VERSION/bin/...
... (list of installed files)
```
Exit code: 0

**Output on NOT installed:**
```
Error: No such keg: /usr/local/Cellar/PACKAGE
```
Exit code: 1

**Edge cases:**
- brew distinguishes formulae (CLI tools) from casks (GUI apps).
  `brew list` checks formulae by default. `brew list --cask` checks casks.
  For system dev libraries (openssl, curl), we use formulae.
- brew packages can be "keg-only" — installed but not linked to PATH.
  `brew list` still returns 0 for keg-only packages (they ARE installed,
  just not linked). For compile-time deps this is fine (the headers exist
  in the Cellar).
- On Apple Silicon Macs, brew prefix is `/opt/homebrew` not `/usr/local`.
  This doesn't affect `brew list` (it knows its own prefix).
- `brew list` is SLOW compared to dpkg/rpm. First call may take 200-500ms
  because brew is a Ruby application that loads its full framework.
  Subsequent calls are faster (~50ms) due to OS-level caching.
- `brew` binary might not exist on Linux systems without Homebrew.

**Performance:** 50-500ms per package (Ruby overhead). This is 10-100x
slower than native package managers. If we need to check 6 packages,
that's 300ms-3s. Consider batching: `brew list pkg1 pkg2 pkg3` returns
0 only if ALL are installed, but we can parse per-line output.

**Alternative:** `brew ls --versions PACKAGE` is slightly faster and
gives version info too. Output on installed: `PACKAGE VERSION`. Output
on not installed: empty, exit 1.

**Prerequisite binary:** `brew` (optional, installed by Homebrew setup).

---

## 3. How Package Install Commands Work Per Package Manager

### 3.1 apt

```
apt-get install -y PKG1 PKG2 PKG3
```

- `-y` = auto-yes to prompts
- Needs sudo (unless running as root)
- Resolves its own dependencies (installing libssl-dev also pulls in
  libssl3, perl, etc.)
- May need `apt-get update` first if the package index is stale
- Exit code 0 = success, 100 = package not found, other = various failures

**Should we run `apt-get update` first?**

If the package index hasn't been updated recently (or ever, in a fresh
container), `apt-get install` will fail with "Unable to locate package".
The current system does NOT run apt-get update. This is a potential
failure on fresh containers.

Options:
- Always run `apt-get update` before install → adds 5-15 seconds
- Run `apt-get update` only if apt cache is older than X hours
- Run `apt-get update` only on first failure (retry logic)
- Let it be a remediation option if install fails

**Decision needed:** For now, don't auto-update. If install fails with
"Unable to locate package", the error analysis can suggest running
`apt-get update` first. This preserves current behavior and keeps
installs fast.

### 3.2 dnf

```
dnf install -y PKG1 PKG2 PKG3
```

- `-y` = auto-yes
- Needs sudo (unless root)
- dnf automatically refreshes metadata if stale (unlike apt)
- Exit code 0 = success, 1 = error

### 3.3 yum (legacy RHEL/CentOS 7)

```
yum install -y PKG1 PKG2 PKG3
```

- Same interface as dnf for our purposes
- yum is the predecessor to dnf, still present on CentOS 7 / RHEL 7
- On modern systems (Fedora 22+, RHEL 8+), yum is a symlink to dnf

### 3.4 apk

```
apk add PKG1 PKG2 PKG3
```

- No `-y` flag needed (apk doesn't prompt)
- Needs root (Alpine containers usually run as root)
- Very fast (Alpine's design)
- May need `apk update` first in minimal containers

### 3.5 pacman

```
pacman -S --noconfirm PKG1 PKG2 PKG3
```

- `--noconfirm` = auto-yes
- Needs sudo
- May need `pacman -Sy` first to refresh databases

### 3.6 zypper

```
zypper install -y PKG1 PKG2 PKG3
```

- `-y` = auto-yes (or `--non-interactive`)
- Needs sudo
- Auto-refreshes repos if needed

### 3.7 brew

```
brew install PKG1 PKG2 PKG3
```

- No sudo (brew is user-space on macOS)
- On Linux, `brew` runs as the `linuxbrew` user or regular user
- Automatically updates brew itself before installing (can be slow, 5-30s)
- To skip auto-update: set `HOMEBREW_NO_AUTO_UPDATE=1` env var
- For casks (GUI apps): `brew install --cask PKG`

---

## 4. The Detection Layer — How Does the System Know Which PM to Use?

Phase 1 already provides this. From `_detect_os()`:

```python
system_profile["package_manager"] = {
    "primary": "apt",           # the main pm detected
    "available": ["apt"],       # all detected pms
    "snap_available": True,     # snap specifically
}
```

And the distro family:

```python
system_profile["distro"] = {
    "family": "debian",         # debian | rhel | alpine | arch | suse | unknown
    ...
}
```

The package checking function needs the `primary` package manager.
The recipe system needs the `family` for package name mapping.

These are TWO DIFFERENT things:
- **Package manager** = how to CHECK and INSTALL packages (apt-get vs dnf vs apk)
- **Distro family** = what NAMES to use for packages (libssl-dev vs openssl-devel)

Example: checking on Fedora uses `rpm -q openssl-devel` (pm=dnf but check
uses rpm). Installing on Fedora uses `dnf install -y openssl-devel`.
The package NAME comes from the recipe (keyed by family "rhel").
The CHECK uses rpm. The INSTALL uses dnf.

### 4.1 The pm-to-checker mapping

| Package manager | Checker binary | Checker command |
|----------------|----------------|-----------------|
| apt | dpkg-query | `dpkg-query -W -f='${Status}' PKG` → check for "install ok installed" |
| dnf | rpm | `rpm -q PKG` → check exit code 0 |
| yum | rpm | `rpm -q PKG` → check exit code 0 |
| zypper | rpm | `rpm -q PKG` → check exit code 0 |
| apk | apk | `apk info -e PKG` → check exit code 0 |
| pacman | pacman | `pacman -Q PKG` → check exit code 0 |
| brew | brew | `brew ls --versions PKG` → check exit code 0 |

### 4.2 The pm-to-install-cmd mapping

| Package manager | Install command template |
|----------------|------------------------|
| apt | `apt-get install -y PKG1 PKG2 ...` |
| dnf | `dnf install -y PKG1 PKG2 ...` |
| yum | `yum install -y PKG1 PKG2 ...` |
| zypper | `zypper install -y PKG1 PKG2 ...` |
| apk | `apk add PKG1 PKG2 ...` |
| pacman | `pacman -S --noconfirm PKG1 PKG2 ...` |
| brew | `brew install PKG1 PKG2 ...` |

---

## 5. Implementation — Exact Functions

### 5.1 `_is_pkg_installed(pkg, pkg_manager)` — new function

```python
def _is_pkg_installed(pkg: str, pkg_manager: str) -> bool:
    """Check if a single system package is installed.

    Uses the appropriate checker for the given package manager:
      apt    → dpkg-query -W -f='${Status}' PKG
      dnf    → rpm -q PKG
      yum    → rpm -q PKG
      zypper → rpm -q PKG
      apk    → apk info -e PKG
      pacman → pacman -Q PKG
      brew   → brew ls --versions PKG

    Args:
        pkg: Exact package name (must match the distro's naming).
        pkg_manager: One of: apt, dnf, yum, zypper, apk, pacman, brew.

    Returns:
        True if installed, False if not installed or check failed.
    """
    try:
        if pkg_manager == "apt":
            r = subprocess.run(
                ["dpkg-query", "-W", "-f=${Status}", pkg],
                capture_output=True, text=True, timeout=10,
            )
            return "install ok installed" in r.stdout

        if pkg_manager in ("dnf", "yum", "zypper"):
            r = subprocess.run(
                ["rpm", "-q", pkg],
                capture_output=True, timeout=10,
            )
            return r.returncode == 0

        if pkg_manager == "apk":
            r = subprocess.run(
                ["apk", "info", "-e", pkg],
                capture_output=True, timeout=10,
            )
            return r.returncode == 0

        if pkg_manager == "pacman":
            r = subprocess.run(
                ["pacman", "-Q", pkg],
                capture_output=True, timeout=10,
            )
            return r.returncode == 0

        if pkg_manager == "brew":
            r = subprocess.run(
                ["brew", "ls", "--versions", pkg],
                capture_output=True, timeout=30,  # brew is slow
            )
            return r.returncode == 0

    except FileNotFoundError:
        # Checker binary not on PATH (e.g. dpkg-query on Fedora)
        logger.warning(
            "Package checker not found for pm=%s (checking %s)",
            pkg_manager, pkg,
        )
    except subprocess.TimeoutExpired:
        logger.warning(
            "Timeout checking package %s with pm=%s",
            pkg, pkg_manager,
        )
    except OSError as exc:
        logger.warning(
            "OS error checking package %s with pm=%s: %s",
            pkg, pkg_manager, exc,
        )

    return False
```

Notes:
- 10s timeout for native pms, 30s for brew (brew is slow)
- FileNotFoundError if the checker binary doesn't exist
- We use `pacman -Q` not `pacman -Qi` (lighter, we only need presence)
- We use `brew ls --versions` not `brew list` (faster, gives version info)
- Returns False on any error — this means "we can't confirm it's installed,
  so treat it as missing" which is the safe default

### 5.2 `check_system_deps(packages, pkg_manager)` — replace existing function

```python
def check_system_deps(
    packages: list[str],
    pkg_manager: str = "apt",
) -> dict[str, list[str]]:
    """Check which system packages are installed.

    Args:
        packages: Package names to check. Names must match the target
                  distro's naming convention (e.g. "libssl-dev" for Debian,
                  "openssl-devel" for RHEL).
        pkg_manager: Which package manager to use for checking.
                     Defaults to "apt" for backward compatibility.

    Returns:
        {"missing": ["pkg1", ...], "installed": ["pkg2", ...]}
    """
    missing: list[str] = []
    installed: list[str] = []
    for pkg in packages:
        if _is_pkg_installed(pkg, pkg_manager):
            installed.append(pkg)
        else:
            missing.append(pkg)
    return {"missing": missing, "installed": installed}
```

This is a drop-in replacement. The signature adds `pkg_manager` with
a default of `"apt"`, so all existing callers continue to work unchanged.

### 5.3 `_build_pkg_install_cmd(packages, pm)` — new function

```python
def _build_pkg_install_cmd(packages: list[str], pm: str) -> list[str]:
    """Build a package-install command for a list of packages.

    Args:
        packages: Package names to install.
        pm: Package manager ID.

    Returns:
        Command list suitable for subprocess.run().
    """
    if pm == "apt":
        return ["apt-get", "install", "-y"] + packages
    if pm == "dnf":
        return ["dnf", "install", "-y"] + packages
    if pm == "yum":
        return ["yum", "install", "-y"] + packages
    if pm == "zypper":
        return ["zypper", "install", "-y"] + packages
    if pm == "apk":
        return ["apk", "add"] + packages
    if pm == "pacman":
        return ["pacman", "-S", "--noconfirm"] + packages
    if pm == "brew":
        return ["brew", "install"] + packages
    # Unknown pm — return a no-op that explains the problem
    logger.error("No install command for package manager: %s", pm)
    return ["echo", f"ERROR: no install command for package manager '{pm}'"]
```

### 5.4 Updated `/audit/check-deps` endpoint

```python
@audit_bp.route("/audit/check-deps", methods=["POST"])
def audit_check_deps():
    """Check if system packages are installed.

    Request body:
        {"packages": ["libssl-dev", "pkg-config"]}
        or with explicit pm:
        {"packages": ["openssl-devel"], "pkg_manager": "dnf"}

    If pkg_manager is not provided, auto-detects from system profile.
    """
    from src.core.services.tool_install import check_system_deps

    body = request.get_json(silent=True) or {}
    packages = body.get("packages", [])
    if not packages:
        return jsonify({"missing": [], "installed": []}), 200

    pkg_manager = body.get("pkg_manager")
    if not pkg_manager:
        from src.core.services.audit.l0_detection import _detect_os
        os_info = _detect_os()
        pkg_manager = os_info.get("package_manager", {}).get("primary", "apt")

    result = check_system_deps(packages, pkg_manager)
    return jsonify(result), 200
```

---

## 6. What's NOT in This Sub-Phase

- No new recipe format (that's 2.2)
- No resolver (that's 2.3)
- No change to `install_tool()` (that's 2.4)
- No frontend changes (that's Phase 3)
- `CARGO_BUILD_DEPS` stays as-is (still has Debian names — the name
  mapping is a recipe concern, Phase 2.2)
- `_analyse_install_failure()` stays as-is (it feeds Debian names to
  `check_system_deps()` which now defaults to `pkg_manager="apt"`)

---

## 7. Files Changed — Exact Locations

| File | What changes |
|------|-------------|
| `tool_install.py` line 91-104 | Replace `check_system_deps` body |
| `tool_install.py` before line 91 | Insert `_is_pkg_installed` function |
| `tool_install.py` after line 104 | Insert `_build_pkg_install_cmd` function |
| `routes_audit.py` lines 295-305 | Replace `/audit/check-deps` endpoint |

**Total new code:** ~80 lines (two new functions + endpoint update)

**Total removed code:** ~14 lines (old `check_system_deps` body replaced)

---

## 8. Testing

### 8.1 On the current system (Ubuntu/WSL2 with apt)

```bash
# Check installed package
curl -s -X POST http://127.0.0.1:8000/api/audit/check-deps \
  -H 'Content-Type: application/json' \
  -d '{"packages":["git","curl","libssl-dev"]}' | python3 -m json.tool

# Check missing package
curl -s -X POST http://127.0.0.1:8000/api/audit/check-deps \
  -H 'Content-Type: application/json' \
  -d '{"packages":["nonexistent-package-xyz"]}' | python3 -m json.tool

# Check with explicit pm (should work same as default on this system)
curl -s -X POST http://127.0.0.1:8000/api/audit/check-deps \
  -H 'Content-Type: application/json' \
  -d '{"packages":["git"], "pkg_manager":"apt"}' | python3 -m json.tool

# Check with wrong pm (rpm doesn't exist on Ubuntu — should return all as missing)
curl -s -X POST http://127.0.0.1:8000/api/audit/check-deps \
  -H 'Content-Type: application/json' \
  -d '{"packages":["git"], "pkg_manager":"dnf"}' | python3 -m json.tool

# Auto-detect pm (no pkg_manager in body — should auto-detect "apt")
curl -s -X POST http://127.0.0.1:8000/api/audit/check-deps \
  -H 'Content-Type: application/json' \
  -d '{"packages":["git","curl"]}' | python3 -m json.tool
```

### 8.2 Verify existing frontend flow still works

1. Navigate to audit page
2. Find a tool with remediation options that include system_deps
3. Click through the remediation flow
4. The deps check should use the same dpkg-query path (default pm="apt")
5. No change in behavior

### 8.3 Verify _build_pkg_install_cmd output

This function is not called by anything in Phase 2.1 (it's used by
the resolver in Phase 2.3). But we can test it manually:

```python
from src.core.services.tool_install import _build_pkg_install_cmd
assert _build_pkg_install_cmd(["git", "curl"], "apt") == ["apt-get", "install", "-y", "git", "curl"]
assert _build_pkg_install_cmd(["git", "curl"], "dnf") == ["dnf", "install", "-y", "git", "curl"]
assert _build_pkg_install_cmd(["git", "curl"], "apk") == ["apk", "add", "git", "curl"]
assert _build_pkg_install_cmd(["git", "curl"], "pacman") == ["pacman", "-S", "--noconfirm", "git", "curl"]
assert _build_pkg_install_cmd(["git", "curl"], "brew") == ["brew", "install", "git", "curl"]
```

---

## 9. Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|-----------|
| `dpkg-query` behavior changes between Debian versions | Low — "install ok installed" format is stable across Debian 8+ | None needed |
| `rpm -q` not available on Debian systems | None — `_is_pkg_installed` catches FileNotFoundError, returns False | Handled |
| `brew` is slow (50-500ms per package) | Could make check-deps slow with many packages | brew timeout set to 30s; Phase 2.3 can implement batch checking for brew |
| Existing callers pass Debian names to check_system_deps | No breakage — default pm="apt" preserves behavior | By design |
| New endpoint auto-detect calls `_detect_os()` | ~30ms overhead per call | Acceptable, same as Phase 1 timing |
