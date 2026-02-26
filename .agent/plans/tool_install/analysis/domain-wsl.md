# Domain: WSL (Windows Subsystem for Linux)

> ⚠️ **PHASE LABELS MAY BE STALE** — As of 2026-02-25, code has evolved far beyond
> what the phase roadmaps suggest. Many features labeled "Phase 4-8 future" are
> ALREADY IMPLEMENTED. See `audit-domain-docs.md` and `audit-missing-pieces.md`
> for the verified truth. Code is the source of truth, not these phase labels.


> This document catalogs WSL1 and WSL2, how each is detected,
> what differs from native Linux, and what the recipes and
> resolver must account for.
>
> SOURCE CODE: l0_detection.py `_detect_os()` WSL section (implemented)
> SOURCE DOCS: arch-system-model (fast: wsl/wsl_version, deep: wsl_interop),
>              scope-expansion §2.5 (WSL kernel), §2.7 (sandboxed),
>              phase2.3-scenarios S35-S36

---

## Detection

WSL detection is part of the FAST TIER (< 1ms).

### Current detection (implemented)

```python
# Read /proc/version
with open("/proc/version", encoding="utf-8") as f:
    version_str = f.read().lower()
    wsl = "microsoft" in version_str or "wsl" in version_str

# Distinguish WSL1 vs WSL2
if wsl:
    wsl_version = 2 if "wsl2" in version_str else 1
else:
    wsl_version = None
```

**System profile output:**
```python
{
    "wsl": bool,             # True on any WSL instance
    "wsl_version": int | None,  # 1 or 2 (None if not WSL)
}
```

### Why /proc/version?

The Linux kernel version string on WSL contains "microsoft":
```
WSL1: 4.4.0-19041-Microsoft
WSL2: 5.15.153.1-microsoft-standard-WSL2
```

- "Microsoft" (capital M) → WSL1
- "microsoft-standard-WSL2" → WSL2
- Detection uses `.lower()` so both match "microsoft"
- "wsl2" in the lowered string distinguishes version 2

### Other WSL indicators (not currently used)

| Indicator | WSL1 | WSL2 | Native Linux |
|-----------|------|------|-------------|
| `/proc/version` contains "microsoft" | ✅ | ✅ | ❌ |
| `/proc/sys/fs/binfmt_misc/WSLInterop` exists | ✅ | ✅ | ❌ |
| `$WSL_DISTRO_NAME` env var set | ✅ | ✅ | ❌ |
| `$WSLENV` env var set | ✅ | ✅ | ❌ |
| `uname -r` contains "Microsoft" | ✅ | ✅ | ❌ |
| Real Linux kernel | ❌ | ✅ | ✅ |
| `/dev/sda` block devices | ❌ | ✅ | ✅ |
| `systemd` possible | ❌ | ✅* | ✅ |

*WSL2 with `[boot] systemd=true` in `/etc/wsl.conf`

---

## WSL1 vs WSL2: Architecture Differences

| Aspect | WSL1 | WSL2 |
|--------|------|------|
| **Kernel** | Translation layer (no real Linux kernel) | Real Linux kernel (Microsoft-maintained) |
| **Performance** | Slower syscall translation | Native Linux performance |
| **Filesystem** | NTFS pass-through | ext4 in virtual disk (VHD) |
| **Windows FS access** | Fast (`/mnt/c/`) | Slow (9P protocol) |
| **Networking** | Shares Windows network stack | NAT'd virtual network |
| **systemd** | ❌ Never | ✅ With `wsl.conf` config |
| **Docker** | ❌ (use Docker Desktop) | ✅ (native or Docker Desktop) |
| **GPU** | ❌ | ✅ (GPU paravirtualization) |
| **USB** | ❌ | ⚠️ (usbipd required) |
| **Linux kernel modules** | ❌ | ⚠️ (custom kernel needed) |
| **GUI apps** | ❌ | ✅ (WSLg) |

---

## Impact on Tool Installation

### What works the same as native Linux

Most tool installation operations are identical on WSL:

| Operation | WSL1 | WSL2 | Notes |
|-----------|------|------|-------|
| `apt-get install` | ✅ | ✅ | Ubuntu is default WSL distro |
| `pip install` | ✅ | ✅ | Python works normally |
| `npm install` | ✅ | ✅ | Node.js works normally |
| `cargo install` | ✅ | ✅ | Rust works normally |
| `snap install` | ❌ | ⚠️ | Needs systemd |
| `brew install` | ⚠️ | ✅ | Linuxbrew works on WSL2 |
| Binary downloads (curl) | ✅ | ✅ | Network access works |
| Compile from source | ⚠️ | ✅ | WSL1 slower, WSL2 native speed |
| `shutil.which()` | ✅ | ✅ | PATH works normally |
| Verify (`--version`) | ✅ | ✅ | All CLIs work normally |

### What differs: systemd

This is the MOST impactful difference for recipes.

**WSL1:** systemd is NEVER available.
- `capabilities.has_systemd == False`
- All `condition: "has_systemd"` post-install steps excluded
- Docker cannot be managed via systemctl
- No service start/enable

**WSL2 without systemd config:** Same as WSL1.
- `capabilities.has_systemd == False`
- systemd not running even though real kernel exists

**WSL2 with systemd enabled:**
```ini
# /etc/wsl.conf
[boot]
systemd=true
```
- `capabilities.has_systemd == True`
- Full systemd functionality
- Docker daemon can be managed normally
- systemctl start/enable/status all work

**Detection from the resolver's perspective:**
The resolver does NOT check `wsl` or `wsl_version` for systemd decisions.
It checks `capabilities.has_systemd`. This is CORRECT — the condition
matches reality whether systemd is absent because of WSL1, WSL2 without
config, or Alpine, or a container.

### What differs: Docker

Docker on WSL has THREE options:

| Approach | WSL1 | WSL2 | How |
|----------|------|------|-----|
| Docker Desktop + WSL backend | ✅ | ✅ | Install Docker Desktop on Windows, enable WSL integration |
| Native Docker in WSL2 + systemd | ❌ | ✅ | `apt install docker.io` + systemd enabled |
| Manual dockerd | ❌ | ⚠️ | `sudo dockerd &` (no auto-start) |

**Scenario S35: Docker on WSL1**
```
Profile: family=debian, pm=apt, wsl=True, wsl_version=1,
         systemd=no, root=no

Plan: pkg(docker.io)
    → post(usermod -aG docker $USER) [not_root=True → included]
    → verify(docker --version)
Steps: 3

Note: systemctl start/enable excluded due to no systemd.
Docker binary installed but daemon won't run.
User needs Docker Desktop or manual dockerd.
```

**Scenario S36: Docker on WSL2 with systemd**
```
Profile: family=debian, pm=apt, wsl=True, wsl_version=2,
         systemd=yes, root=no

Same as native Ubuntu desktop (S34):
Plan: pkg(docker.io)
    → post(systemctl start docker) [has_systemd → included]
    → post(systemctl enable docker) [has_systemd → included]
    → post(usermod -aG docker $USER) [not_root → included]
    → verify(docker --version)
Steps: 5
```

### What differs: snap

Snap requires systemd. On WSL:
- WSL1: snap never works
- WSL2 without systemd: snap doesn't work
- WSL2 with systemd: snap works

**Detection:** `package_manager.snap_available` already accounts for
this. Snap is marked available only when both `shutil.which("snap")`
returns a path AND `has_systemd` is True.

**Impact on method selection:**
```python
# kubectl recipe: prefer = ["snap", "brew", "_default"]
# WSL1 or WSL2 without systemd: snap_available = False
# → skip snap → try brew → try _default (binary download)
```

### What differs: PATH and Windows interop

WSL automatically adds Windows directories to the Linux PATH:
```
/mnt/c/Windows/system32:/mnt/c/Windows:...:/mnt/c/Users/USER/...
```

**Impact:**
- `shutil.which()` may find Windows executables (e.g., `code.exe`)
- Commands like `powershell.exe` and `cmd.exe` are callable from WSL
- This can cause false positives for tool detection if a Windows .exe
  is found instead of a Linux binary
- Example: `docker.exe` on PATH from Docker Desktop ≠ Linux `docker`

**Current handling:** Phase 1 doesn't distinguish Windows .exe from
Linux binaries in `shutil.which()`. This is a KNOWN LIMITATION.

✅ **IMPLEMENTED (L1):** `_is_linux_binary()` in `detection/tool_version.py` verifies ELF magic bytes. Binary is
a Linux ELF, not a Windows PE:
```python
def _is_linux_binary(path: str) -> bool:
    """Check if a binary is a Linux ELF, not Windows PE or script."""
    with open(path, "rb") as f:
        magic = f.read(4)
    return magic == b"\x7fELF"
```

### What differs: filesystem performance

**Linux files on NTFS (WSL1, /mnt/c on WSL2):**
- Very slow for npm/cargo builds (many small file I/O)
- `npm install` in /mnt/c/ can be 5-10x slower than in ~/

**Linux files on ext4 (WSL2 native):**
- Full speed, same as native Linux
- This is the default home directory on WSL2

**Recommendation for recipes:** Install tools to the Linux filesystem
(~/), not /mnt/c/ or /mnt/d/. This is default behavior — pip, cargo,
and npm all install to Linux-side paths by default. No recipe changes
needed.

---

## WSL Interop (Deep Tier — Phase 6, IMPLEMENTED)

### Detection schema (implemented in `_detect_wsl_interop()`)

```python
"wsl_interop": {
    "available": bool,           # powershell.exe is on PATH
    "binfmt_registered": bool,   # /proc/sys/fs/binfmt_misc/WSLInterop exists
    "windows_user": str | None,  # from cmd.exe /c "echo %USERNAME%"
    "wslconfig_path": str | None,  # C:\Users\USER\.wslconfig
}
```

### Cross-OS commands

WSL interop allows calling Windows executables from Linux:

```bash
# From within WSL:
powershell.exe -Command "Get-Content C:\Users\USER\.wslconfig"
cmd.exe /c "echo %USERNAME%"
explorer.exe .                 # Open Windows Explorer in current dir
wsl.exe --shutdown             # Shutdown WSL from within WSL
```

### Use cases for recipes

1. **Custom WSL2 kernel:** Build and install a custom kernel for
   features like VFIO, GPU passthrough, or custom modules.
   ```
   Build kernel → place vmlinux at known path
   → write .wslconfig via powershell.exe
   → wsl --shutdown + restart
   ```

2. **Docker Desktop integration:** Check if Docker Desktop is installed
   on the Windows side and if WSL integration is enabled.
   ```
   powershell.exe -Command "docker --version"
   → if present, skip Linux docker install
   ```

3. **Path translation:** Converting between Linux and Windows paths.
   ```bash
   wslpath -w ~/project    # → \\wsl$\Ubuntu\home\user\project
   wslpath -u "C:\Users"   # → /mnt/c/Users
   ```

---

## WSL Configuration Files

### /etc/wsl.conf (per-distribution)

```ini
[boot]
systemd=true                    # Enable systemd (WSL2 only)
command=""                      # Custom boot command

[automount]
enabled=true                    # Auto-mount Windows drives
root=/mnt/                      # Mount point prefix
options="metadata,umask=22,fmask=11"  # Mount options

[network]
generateHosts=true              # Auto-generate /etc/hosts
generateResolvConf=true         # Auto-generate /etc/resolv.conf

[interop]
enabled=true                    # Allow running Windows executables
appendWindowsPath=true          # Add Windows PATH to Linux PATH
```

### .wslconfig (global, Windows-side)

Located at `C:\Users\USER\.wslconfig`:
```ini
[wsl2]
memory=8GB                      # RAM limit
processors=4                    # CPU limit
swap=4GB                        # Swap size
kernel=C:\custom\vmlinux        # Custom kernel path
kernelCommandLine=""            # Kernel boot params
```

### Impact on recipes

| Config | What it affects | How recipes use it |
|--------|----------------|-------------------|
| `systemd=true` | Service management | Detected via `has_systemd` |
| `appendWindowsPath=true` | PATH pollution | May cause false positives |
| `kernel=...` | Custom kernel modules | NOT IMPLEMENTED: WSL kernel recipe |
| `memory=...` | Build resource limits | NOT IMPLEMENTED: build toolchain check |

---

## WSL-Specific Conditions

### Current condition set (Phase 2)

The existing conditions handle WSL correctly WITHOUT WSL-specific logic:

| Condition | WSL1 | WSL2 (no systemd) | WSL2 (systemd) |
|-----------|------|-------------------|----------------|
| `has_systemd` | False | False | True |
| `not_root` | True (usually) | True (usually) | True (usually) |
| `not_container` | True | True | True |

WSL is NOT a container. `container.in_container == False` on WSL.

### NOT IMPLEMENTED conditions (Phase 6)

| Condition | Purpose |
|-----------|---------|
| `is_wsl` | Distinguish WSL from native Linux |
| `is_wsl1` | WSL1-specific limitations (no real kernel) |
| `is_wsl2` | WSL2 capabilities (real kernel, GPU) |
| `has_wsl_interop` | Can run Windows commands |
| `has_docker_desktop` | Docker Desktop available via WSL integration |

---

## Common WSL Distributions

| Distribution | Source | Default PM | Notes |
|-------------|--------|-----------|-------|
| Ubuntu | Microsoft Store | apt | Default WSL distro |
| Debian | Microsoft Store | apt | Minimal |
| Kali Linux | Microsoft Store | apt | Security tools |
| openSUSE | Microsoft Store | zypper | Tumbleweed variant |
| Alpine | Community | apk | Minimal, musl libc |
| Fedora | Community | dnf | Not in Store, manual install |
| Arch | Community | pacman | Not in Store, manual install |

**The most common case:** Ubuntu on WSL2 with systemd disabled.
This means: `family=debian, pm=apt, wsl=True, wsl_version=2,
has_systemd=False, snap_available=False`.

---

## Edge Cases

### WSL1 to WSL2 conversion

Users may convert distributions between WSL1 and WSL2:
```powershell
wsl --set-version Ubuntu 2
```

After conversion:
- kernel string changes (removes "Microsoft", adds "microsoft-standard-WSL2")
- Real Linux kernel available
- systemd possible (with config)

**Impact:** System profile must be re-scanned after conversion.
The existing cache-bust mechanism handles this.

### Multiple WSL distributions

A user can have Ubuntu (WSL2), Debian (WSL1), and Alpine (WSL2)
installed simultaneously. Each has its own `/etc/wsl.conf`,
own package state, and own systemd status.

**Impact:** The system profile is per-instance. Each distribution
runs its own detection independently.

### WSL with Docker Desktop integration

Docker Desktop for Windows can expose the Docker daemon to WSL
distributions without installing Docker inside WSL.

**Detection clue:** `docker` is on PATH via Windows interop
(`/mnt/c/Program Files/Docker/Docker/resources/bin/docker`).

**Impact:** `shutil.which("docker")` returns a path → tool detected
as installed → plan says `already_installed: True`. This is CORRECT
behavior — Docker is functional even though it's the Windows binary.

### Nested scenarios: WSL inside container

Theoretically impossible — WSL is a Windows feature, containers
run on Linux. Not a real scenario.

### GPU in WSL2

WSL2 supports GPU paravirtualization (DirectX → Linux DRM):
- NVIDIA CUDA works via `/usr/lib/wsl/lib/` (WSL-specific path)
- `nvidia-smi` available but output differs from native
- ROCm support limited

**Impact on GPU recipes (Phase 6):** WSL2 GPU detection needs
WSL-specific paths. `nvidia-smi` may show different output format.

---

## Traceability

| Topic | Source |
|-------|--------|
| Detection code | l0_detection.py lines 315-327 (implemented) |
| System profile fields | arch-system-model: wsl, wsl_version (fast), wsl_interop (deep) |
| WSL kernel customization | scope-expansion §2.5 (Phase 6) |
| Docker scenarios on WSL | phase2.3-scenarios S35, S36 |
| Snap + systemd | phase2.3-scenarios S7 resolution logic |
| Interop detection schema | arch-system-model §WSL interop (Phase 6) |
| .wslconfig for kernel | scope-expansion §2.5 lines 360-371 |
