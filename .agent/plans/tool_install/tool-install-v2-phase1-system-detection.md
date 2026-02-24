# Phase 1: System Detection Enhancement — Implementation Plan

## Goal

Extend `_detect_os()` in `l0_detection.py` so the system profile contains every
piece of information the install resolver (Phase 2) will need to pick the
correct install command for the detected platform.

**No other file changes.** Phase 1 is purely detection. The existing consumers
(`audit:system` cache, `/api/audit/system` endpoint, System Profile audit card)
will automatically expose the new data with zero wiring changes.

---

## 1. Current State of `_detect_os()` (lines 69-100)

Returns:
```python
{
    "system": "Linux",                       # platform.system()
    "release": "5.15.167.4-microsoft-...",   # platform.release()
    "machine": "x86_64",                     # platform.machine()
    "wsl": True,                             # /proc/version contains "microsoft"
    "distro": "Ubuntu 20.04.6 LTS",         # PRETTY_NAME from /etc/os-release
}
```

**Problems:**
- `distro` is a display string. Can't compare versions or detect family.
- No distro ID (`ubuntu`, `fedora`, `alpine`).
- No distro family (`debian`, `rhel`, `alpine`, `arch`, `suse`).
- No version as tuple (needed for: "does this distro version support X?").
- WSL is bool, no WSL version (1 vs 2 matters for systemd).
- No container detection.
- No package manager detection.
- No capabilities (systemd, sudo, root).
- No library versions (openssl, glibc, libc type).
- No normalized architecture (x86_64→amd64, aarch64→arm64).

---

## 2. Target Output

After Phase 1, `_detect_os()` returns:

```python
{
    # ── Existing (unchanged) ──────────────────────────────────
    "system": "Linux",
    "release": "5.15.167.4-microsoft-standard-WSL2",
    "machine": "x86_64",

    # ── Normalized architecture ───────────────────────────────
    "arch": "amd64",             # x86_64→amd64, aarch64/arm64→arm64

    # ── Distro (replaces flat "distro" string) ────────────────
    "distro": {
        "id": "ubuntu",          # ID from /etc/os-release (lowercase)
        "name": "Ubuntu 20.04.6 LTS",  # PRETTY_NAME
        "version": "20.04",      # VERSION_ID
        "version_tuple": [20, 4],       # parsed
        "family": "debian",      # mapped from ID_LIKE or ID
        "codename": "focal",     # VERSION_CODENAME
    },

    # ── WSL (extended) ────────────────────────────────────────
    "wsl": True,
    "wsl_version": 2,            # 1 or 2, parsed from kernel string

    # ── Container environment ─────────────────────────────────
    "container": {
        "in_container": False,
        "runtime": None,         # "docker" | "containerd" | "podman" | None
        "in_k8s": False,
    },

    # ── System capabilities ───────────────────────────────────
    "capabilities": {
        "has_systemd": True,     # systemctl exists AND is-system-running != "offline"
        "systemd_state": "degraded",   # running | degraded | offline | None
        "has_sudo": True,        # sudo binary exists
        "passwordless_sudo": False,    # sudo -n true returns 0
        "is_root": False,        # os.getuid() == 0
    },

    # ── Available package managers ────────────────────────────
    "package_manager": {
        "primary": "apt",        # first available from priority list
        "available": ["apt", "snap", "brew"],  # all detected
        "snap_available": True,  # snap exists AND systemd is running/degraded
    },

    # ── Library versions ──────────────────────────────────────
    "libraries": {
        "openssl_version": "3.6.1",      # from `openssl version`
        "glibc_version": "2.31",         # from glibc
        "libc_type": "glibc",            # "glibc" | "musl"
    },
}
```

---

## 3. Detection Methods — Exactly How Each Field Is Obtained

### 3.1 `arch` — Normalized architecture

```python
_ARCH_MAP = {
    "x86_64": "amd64", "amd64": "amd64",
    "aarch64": "arm64", "arm64": "arm64",
    "armv7l": "armv7",
}
arch = _ARCH_MAP.get(platform.machine().lower(), platform.machine().lower())
```

### 3.2 `distro` — Structured distro info

Parse `/etc/os-release` fully (not just PRETTY_NAME):

```python
def _parse_os_release() -> dict:
    """Parse /etc/os-release into a dict of key=value pairs."""
    data = {}
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line:
                    key, val = line.split("=", 1)
                    data[key] = val.strip('"')
    except (FileNotFoundError, OSError):
        pass
    return data
```

Fields extracted:
- `ID` → `distro.id` (e.g. "ubuntu", "fedora", "alpine", "arch", "opensuse-leap")
- `PRETTY_NAME` → `distro.name`
- `VERSION_ID` → `distro.version` (e.g. "20.04", "39", "3.19")
- `VERSION_CODENAME` → `distro.codename` (e.g. "focal", "bookworm")
- `ID_LIKE` → used to derive `distro.family`

Family mapping:

```python
_FAMILY_MAP = {
    # Direct ID matches
    "ubuntu": "debian", "debian": "debian", "linuxmint": "debian",
    "pop": "debian", "elementary": "debian", "zorin": "debian",
    "kali": "debian", "raspbian": "debian", "deepin": "debian",

    "fedora": "rhel", "centos": "rhel", "rhel": "rhel",
    "rocky": "rhel", "almalinux": "rhel", "oracle": "rhel",
    "amzn": "rhel",  # Amazon Linux

    "alpine": "alpine",

    "arch": "arch", "manjaro": "arch", "endeavouros": "arch",

    "opensuse-leap": "suse", "opensuse-tumbleweed": "suse", "sles": "suse",
}

def _get_distro_family(distro_id: str, id_like: str) -> str:
    """Determine distro family from ID and ID_LIKE fields."""
    # Direct match first
    if distro_id in _FAMILY_MAP:
        return _FAMILY_MAP[distro_id]
    # Check ID_LIKE (space-separated list of parent distros)
    for parent in id_like.split():
        if parent in _FAMILY_MAP:
            return _FAMILY_MAP[parent]
    return "unknown"
```

Version tuple:

```python
def _parse_version_tuple(version_str: str) -> list[int]:
    """Parse "20.04" → [20, 4], "39" → [39]."""
    parts = []
    for p in version_str.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            break
    return parts
```

### 3.3 `wsl_version` — WSL 1 vs 2

```python
# Already reading /proc/version. Parse the kernel string:
# WSL2: "5.15.167.4-microsoft-standard-WSL2" → contains "WSL2"
# WSL1: kernel string contains "microsoft" but NOT "WSL2"
if info["wsl"]:
    info["wsl_version"] = 2 if "wsl2" in version_str else 1
```

### 3.4 `container` — Container detection

```python
def _detect_container() -> dict:
    result = {
        "in_container": False,
        "runtime": None,
        "in_k8s": False,
    }

    # Method 1: /.dockerenv file
    if os.path.isfile("/.dockerenv"):
        result["in_container"] = True
        result["runtime"] = "docker"

    # Method 2: /proc/1/cgroup contains docker/kubepods/containerd
    try:
        with open("/proc/1/cgroup", encoding="utf-8") as f:
            cgroup = f.read().lower()
            if "docker" in cgroup:
                result["in_container"] = True
                result["runtime"] = result["runtime"] or "docker"
            elif "kubepods" in cgroup:
                result["in_container"] = True
                result["runtime"] = "containerd"
                result["in_k8s"] = True
            elif "containerd" in cgroup:
                result["in_container"] = True
                result["runtime"] = "containerd"
    except (FileNotFoundError, OSError):
        pass

    # Method 3: /proc/1/environ contains container= (systemd-nspawn, podman)
    try:
        with open("/proc/1/environ", encoding="utf-8", errors="replace") as f:
            env = f.read()
            if "container=" in env:
                result["in_container"] = True
    except (FileNotFoundError, OSError, PermissionError):
        pass

    # Method 4: KUBERNETES_SERVICE_HOST env var
    if os.environ.get("KUBERNETES_SERVICE_HOST"):
        result["in_k8s"] = True
        result["in_container"] = True

    return result
```

### 3.5 `capabilities` — System capabilities

```python
def _detect_capabilities() -> dict:
    import subprocess

    result = {
        "has_systemd": False,
        "systemd_state": None,
        "has_sudo": shutil.which("sudo") is not None,
        "passwordless_sudo": False,
        "is_root": os.getuid() == 0,
    }

    # systemd detection
    if shutil.which("systemctl"):
        try:
            r = subprocess.run(
                ["systemctl", "is-system-running"],
                capture_output=True, text=True, timeout=5,
            )
            state = r.stdout.strip()  # running | degraded | offline | ...
            result["systemd_state"] = state
            # "running" and "degraded" both mean systemd IS active
            result["has_systemd"] = state in ("running", "degraded")
        except (subprocess.TimeoutExpired, OSError):
            pass

    # Passwordless sudo
    if result["has_sudo"] and not result["is_root"]:
        try:
            r = subprocess.run(
                ["sudo", "-n", "true"],
                capture_output=True, timeout=5,
            )
            result["passwordless_sudo"] = r.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            pass

    return result
```

### 3.6 `package_manager` — Available package managers

```python
def _detect_package_managers(has_systemd: bool) -> dict:
    # Priority order: first available is "primary"
    _PM_BINARIES = [
        ("apt",    "apt-get"),
        ("dnf",    "dnf"),
        ("yum",    "yum"),
        ("apk",    "apk"),
        ("pacman", "pacman"),
        ("zypper", "zypper"),
        ("brew",   "brew"),
    ]

    available = []
    primary = None
    for pm_id, binary in _PM_BINARIES:
        if shutil.which(binary):
            available.append(pm_id)
            if primary is None:
                primary = pm_id

    # Snap is special: needs systemd
    snap_available = shutil.which("snap") is not None and has_systemd

    return {
        "primary": primary or "none",
        "available": available,
        "snap_available": snap_available,
    }
```

### 3.7 `libraries` — Library versions

```python
def _detect_libraries() -> dict:
    import subprocess

    result = {
        "openssl_version": None,
        "glibc_version": None,
        "libc_type": "unknown",
    }

    # OpenSSL version: `openssl version` → "OpenSSL 3.6.1 27 Jan 2026 ..."
    if shutil.which("openssl"):
        try:
            r = subprocess.run(
                ["openssl", "version"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                # Parse: "OpenSSL 3.6.1 ..." or "LibreSSL 3.8.2"
                parts = r.stdout.strip().split()
                if len(parts) >= 2:
                    result["openssl_version"] = parts[1]
        except (subprocess.TimeoutExpired, OSError):
            pass

    # glibc version via ctypes
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6")
        libc.gnu_get_libc_version.restype = ctypes.c_char_p
        result["glibc_version"] = libc.gnu_get_libc_version().decode()
        result["libc_type"] = "glibc"
    except (OSError, AttributeError):
        # Might be musl — check via ldd
        try:
            r = subprocess.run(
                ["ldd", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            output = (r.stdout + r.stderr).lower()
            if "musl" in output:
                result["libc_type"] = "musl"
                # musl ldd version output: "musl libc (x86_64)\nVersion 1.2.4"
                import re
                ver = re.search(r"version\s+([\d.]+)", output)
                if ver:
                    result["glibc_version"] = ver.group(1)  # musl version, not glibc
        except (subprocess.TimeoutExpired, OSError):
            pass

    return result
```

### 3.8 macOS handling

On macOS:
- No `/etc/os-release` → distro.id = "macos", distro.family = "macos"
- `platform.mac_ver()` → version string
- No `/proc/version` → wsl = False
- No `/proc/1/cgroup` → container detection via env vars only
- No systemd → capabilities.has_systemd = False
- No apt/dnf → package_manager.primary = "brew"
- No glibc → libc_type = "system" (Apple's libSystem)

```python
if platform.system() == "Darwin":
    mac_ver = platform.mac_ver()[0]  # e.g. "14.2.1"
    info["distro"] = {
        "id": "macos",
        "name": f"macOS {mac_ver}",
        "version": mac_ver,
        "version_tuple": _parse_version_tuple(mac_ver),
        "family": "macos",
        "codename": None,
    }
```

---

## 4. Performance Budget

Current `_detect_os()` takes <1ms (reads 1 file, no subprocesses).

New detections add subprocesses:
- `systemctl is-system-running` → ~50ms
- `sudo -n true` → ~50ms
- `openssl version` → ~10ms
- glibc via ctypes → ~1ms (no subprocess)
- `ldd --version` → ~10ms (fallback only if ctypes fails)

**Total added: ~120ms worst case.** This is within the L0 budget
("designed to be fast, <200ms"). All with timeout=5s safety.

Container detection reads files only (no subprocesses) → ~1ms.
Package manager detection uses `shutil.which()` only → ~5ms.

---

## 5. Implementation Steps

### Step 1: Add helper functions (no behavior change)

Add to `l0_detection.py` ABOVE `_detect_os()`:
- `_ARCH_MAP` constant
- `_FAMILY_MAP` constant
- `_parse_os_release()` function
- `_get_distro_family()` function
- `_parse_version_tuple()` function
- `_detect_container()` function
- `_detect_capabilities()` function
- `_detect_package_managers()` function
- `_detect_libraries()` function

### Step 2: Rewrite `_detect_os()` to use the new helpers

Replace the body of `_detect_os()` (lines 69-100):
- Call each helper
- Assemble the full dict
- Keep backward-compatible `distro` field (the `_detect_os` return
  previously had `distro` as a string; now it's a dict with a `name`
  field — consumers must be checked)

### Step 3: Check backward compatibility

The System Profile audit card (`_audit_cards_a.html` line 21) uses:
```javascript
os.distro || os.system
```

This will break because `os.distro` was a string, now it's a dict.
→ Change the card to use `os.distro.name` instead.

Also line 21 uses `os.wsl` which stays the same (bool). ✅

### Step 4: Update the System Profile audit card

In `_audit_cards_a.html`:
- Display the new fields: distro family, package manager, container,
  capabilities, libraries
- Update the OS row to use `os.distro.name`
- Add rows for the new detection data

---

## 6. Files Changed

| File | What changes |
|------|-------------|
| `src/core/services/audit/l0_detection.py` | Add 9 helper functions. Rewrite `_detect_os()` body. |
| `src/ui/web/templates/scripts/_audit_cards_a.html` | Update system profile card to show new fields, fix `distro` access |

**No other files change.** The L0 profile flows through `l0_system_profile()` →
`audit:system` cache → `/api/audit/system` endpoint → audit card. All
automatic.

---

## 7. What This Enables for Phase 2

With the system profile containing:
- `distro.family` → Phase 2 picks the right package names (`libssl-dev` vs `openssl-devel`)
- `package_manager.primary` → Phase 2 picks the right install command (`apt-get` vs `dnf`)
- `package_manager.snap_available` → Phase 2 knows if snap recipes work
- `capabilities.has_sudo` → Phase 2 knows if sudo is available
- `capabilities.passwordless_sudo` → Phase 2 can skip password prompt
- `capabilities.is_root` → Phase 2 can skip sudo entirely
- `container.in_container` → Phase 2 can warn about ephemeral installs
- `container.in_k8s` → Phase 2 can warn about pod installs
- `arch` → Phase 2 picks correct binary download URLs
- `libraries.openssl_version` → Phase 2 knows if openssl-sys will compile
- `libraries.libc_type` → Phase 2 knows if musl binaries are needed

---

## 8. Risk Assessment

| Risk | Mitigation |
|------|-----------|
| `systemctl is-system-running` hangs | timeout=5s on subprocess |
| `sudo -n true` prompts for password | `-n` flag prevents prompting |
| `/proc/1/cgroup` not readable (permissions) | try/except PermissionError |
| `distro` field format change breaks card | Fix card in same PR |
| ctypes.CDLL fails on macOS/musl | Fallback paths in _detect_libraries |
| Performance exceeds 200ms budget | All subprocesses have timeout=5s, typical <120ms |

---

## 9. Test Verification

After implementation, verify via:
1. `curl http://127.0.0.1:8000/api/audit/system?bust` → check new fields in `os` key
2. System Profile card in UI shows new information
3. On this dev machine (WSL2 + Ubuntu 20.04), expect:
   - `distro.id` = "ubuntu", `distro.family` = "debian"
   - `wsl` = True, `wsl_version` = 2
   - `container.in_container` = False
   - `capabilities.has_systemd` = True (degraded counts)
   - `package_manager.primary` = "apt"
   - `package_manager.available` = ["apt", "zypper", "brew"]
   - `libraries.openssl_version` = "3.6.1"
   - `libraries.glibc_version` = "2.31"
