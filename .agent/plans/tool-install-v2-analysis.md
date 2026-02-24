# Tool Install v2 — Full Analysis

## 1. What Exists Today (Complete Inventory)

### 1.1 System Detection (`l0_detection.py`)

Already detects:
- `platform.system()` → Linux, Darwin, Windows
- `platform.release()` → kernel version (e.g. `5.15.0-92-generic`)
- `platform.machine()` → x86_64, aarch64, arm64
- WSL detection → reads `/proc/version` for "microsoft" or "wsl"
- Linux distro → via `distro` lib or `/etc/os-release` (e.g. "Ubuntu 22.04.4 LTS")
- Python version, venv status
- 40+ tool binaries via `shutil.which()`

Does NOT detect:
- Distro VERSION as a parseable number (just pretty name string)
- Distro family (Debian-based vs RHEL-based vs Alpine vs Arch)
- Package manager available (apt vs dnf vs yum vs apk vs pacman vs brew)
- Container environment (running inside Docker/K8s pod)
- systemd availability (matters for snap, services)
- Kernel version as parseable tuple
- OpenSSL version
- glibc version (only in `pages_install.py` Hugo binary installer)
- Architecture specifics (musl vs glibc libc)

### 1.2 Tool Registry (`l0_detection.py` lines 20-66)

40+ tools in `_TOOLS` list. Each tool has:
- `id`, `cli`, `label`, `category`, `install_type`

The `install_type` field values: `"sudo"`, `"pip"`, `"npm"`, `"cargo"`, `"none"`

This is the DETECTION registry. Separate from install recipes.

### 1.3 Install Recipes (`tool_install.py`)

Two flat dicts:
- `_NO_SUDO_RECIPES` (12 tools): pip tools, npm tools, cargo tools
- `_SUDO_RECIPES` (25+ tools): apt, snap, bash curl scripts

Each is just `tool_name → [command_list]`. No metadata about:
- What package manager is being used
- What distro/OS the command is for
- What the tool depends on
- What system packages are needed for compilation

### 1.4 Runtime Dependency Check (`tool_install.py` lines 352-383)

Inline in `install_tool()`:
- `_RUNTIME_DEPS`: knows `cargo`, `npm`, `node` as binary requirements
- `_TOOL_REQUIRES`: knows `cargo-audit` and `cargo-outdated` need `cargo`
- Checks via `shutil.which()`

This is a FLAT, 1-level check. No recursion. No system packages.

### 1.5 System Package Check (`tool_install.py` lines 85-104)

- `CARGO_BUILD_DEPS = ["pkg-config", "libssl-dev", "libcurl4-openssl-dev"]`
- `check_system_deps()` — uses `dpkg-query` (Debian/Ubuntu only!)
- Bolted onto remediation options as `system_deps` field

### 1.6 Error Analysis (`tool_install.py` lines 107-271)

Post-failure stderr parsing:
- Rust version mismatch → 3 remediation options
- npm not found → install npm option
- pip not found → install pip option
- Permission denied (EACCES) → retry with sudo

### 1.7 Pages Install (`pages_install.py`)

A SEPARATE install system for page builders (mkdocs, hugo, docusaurus).
Uses its own SSE streaming pattern. Has its own arch/OS detection.
Hugo binary installer: detects platform, downloads correct binary.
This is a PARALLEL implementation of the same pattern.

### 1.8 Frontend Install Flows (`_globals.html`)

6 different modal types:
1. `ops-modal` — sudo password (hand-built DOM, NOT using modalOpen)
2. `modalOpen` remediation — option-grid for error analysis results
3. `deps-modal-overlay` — stacked overlay for system packages (hand-built DOM)
4. `modalOpen` dep-required — "X requires Y" chain
5. `modalOpen` error — raw error display
6. `modalOpen` error — catch block

4 different install execution paths:
1. `installToolFromBanner()` → `/audit/install-tool` (JSON, no streaming)
2. `_doDirectInstall()` → `/audit/install-tool` (JSON, no streaming)
3. `_remExecute()` → `/audit/remediate` (SSE streaming)
4. `_depsInstall()` → `/audit/remediate` (SSE streaming)

3 different SSE reading implementations:
1. `streamCommand()` inside `_remExecute`
2. Stream reader inside `_depsInstall`
3. `pages_install.py` has its own stream format (`{type, line}` vs `{line}`)

### 1.9 Endpoints

| Endpoint | Used by | Returns |
|----------|---------|---------|
| `POST /audit/install-tool` | Banner install, sudo install, dep chain | JSON (not streaming) |
| `POST /audit/remediate` | Remediation modal, deps modal | SSE stream |
| `POST /audit/check-deps` | `_remExecute` pre-check | JSON `{missing, installed}` |
| `GET /tools/status` | Dashboard tool status | JSON (all tools) |

---

## 2. The Real Scope — What Systems Can Run This App

A Python app in a venv can run on:

### 2.1 Operating Systems
- **Linux** (most common for devops)
  - Debian/Ubuntu family → `apt-get`, `dpkg`
  - RHEL/CentOS/Fedora family → `dnf`, `yum`, `rpm`
  - Alpine → `apk`
  - Arch → `pacman`
  - SUSE/openSUSE → `zypper`
- **macOS** → `brew` (Homebrew)
- **Windows** (via WSL or native)
  - WSL1 → Linux userspace, no systemd
  - WSL2 → full Linux kernel, may have systemd
  - Native Windows → `choco`, `scoop`, `winget`

### 2.2 Container Environments
- **Docker container** → usually Debian/Alpine minimal, no systemd, limited perms
- **K8s pod** → same as Docker + network restrictions, ephemeral filesystem
- **Dev container** (VS Code) → Docker-based, may have custom setup

### 2.3 What Each Environment Means for Install

| Factor | What it changes |
|--------|----------------|
| Package manager | `apt-get` vs `dnf` vs `apk` vs `brew` vs `snap` |
| Sudo availability | Containers often run as root. WSL may have passwordless sudo. |
| systemd | Snap requires systemd. No systemd = no snap = different kubectl/terraform recipe |
| Network access | K8s pods may have restricted egress. curl scripts may fail. |
| Persistence | K8s pods are ephemeral. Installing tools is pointless unless into a volume. |
| Architecture | arm64 vs amd64 → different binary downloads |
| glibc vs musl | Alpine uses musl → some binaries won't work |
| OpenSSL version | Affects cargo crate compilation (curl-sys, openssl-sys) |
| Kernel version | Affects Docker, some tools check kernel |
| Dev headers available | Ubuntu server vs desktop vs minimal → different default packages |

### 2.4 Package Name Mapping

The SAME library has DIFFERENT names across distros:

| What | Debian/Ubuntu | Fedora/RHEL | Alpine | macOS (brew) |
|------|--------------|-------------|--------|-------------|
| OpenSSL dev headers | `libssl-dev` | `openssl-devel` | `openssl-dev` | `openssl@3` |
| libcurl dev | `libcurl4-openssl-dev` | `libcurl-devel` | `curl-dev` | `curl` |
| pkg-config | `pkg-config` | `pkgconf-pkg-config` | `pkgconf` | `pkg-config` |
| build tools | `build-essential` | `gcc make` | `build-base` | Xcode CLI tools |
| Python headers | `python3-dev` | `python3-devel` | `python3-dev` | (included) |
| zlib | `zlib1g-dev` | `zlib-devel` | `zlib-dev` | `zlib` |
| Git | `git` | `git` | `git` | `git` |

### 2.5 Install Method Variants

The SAME tool has DIFFERENT install methods per system:

| Tool | Debian/Ubuntu | Fedora | Alpine | macOS | No systemd |
|------|--------------|--------|--------|-------|------------|
| kubectl | snap (classic) | dnf | apk from edge | brew | curl binary download |
| terraform | snap (classic) | dnf (hashicorp repo) | N/A | brew | curl binary |
| helm | curl script | curl script | curl script | brew | curl script |
| docker | apt docker.io | dnf docker-ce | apk docker | brew --cask | N/A in container |

---

## 3. The Detection Model Needed

### 3.1 System Profile (extends current `_detect_os`)

```python
{
    "system": "Linux",                    # platform.system()
    "kernel": "5.15.0-92-generic",        # platform.release()
    "kernel_tuple": [5, 15, 0],           # parsed
    "machine": "x86_64",                  # platform.machine()
    "arch": "amd64",                      # normalized (x86_64→amd64, aarch64→arm64)

    "distro": {
        "id": "ubuntu",                   # lowercase ID (ubuntu, fedora, alpine, ...)
        "name": "Ubuntu 22.04.4 LTS",     # pretty name
        "version": "22.04",               # version string
        "version_tuple": [22, 4],         # parsed
        "family": "debian",               # debian | rhel | alpine | arch | suse | unknown
    },

    "wsl": False,                         # WSL1 or WSL2
    "wsl_version": None,                  # 1 or 2 if WSL

    "container": {
        "in_container": False,            # True if running inside Docker/K8s
        "runtime": None,                  # "docker" | "containerd" | "podman" | None
        "in_k8s": False,                  # KUBERNETES_SERVICE_HOST exists
        "ephemeral": False,               # True if filesystem is ephemeral
    },

    "capabilities": {
        "has_systemd": True,              # systemd is running (snap needs this)
        "has_sudo": True,                 # sudo binary exists and user can sudo
        "passwordless_sudo": False,       # sudo works without password
        "is_root": False,                 # running as uid 0
    },

    "package_manager": {
        "primary": "apt",                 # apt | dnf | yum | apk | pacman | zypper | brew | choco | none
        "available": ["apt", "snap"],     # all available package managers
        "snap_available": True,           # snap specifically (needs systemd)
    },

    "libraries": {
        "openssl_version": "1.1.1",       # from `openssl version`
        "glibc_version": "2.35",          # from glibc
        "libc_type": "glibc",             # glibc | musl
    },
}
```

### 3.2 How to Detect Each Field

| Field | How to detect |
|-------|--------------|
| `distro.id` | `/etc/os-release` → `ID=ubuntu` |
| `distro.family` | Map: ubuntu/debian/mint→debian, fedora/centos/rhel→rhel, alpine→alpine |
| `in_container` | `/.dockerenv` exists OR `/proc/1/cgroup` contains "docker"/"kubepods" |
| `in_k8s` | `KUBERNETES_SERVICE_HOST` env var exists |
| `has_systemd` | `shutil.which("systemctl")` and `subprocess.run(["systemctl", "is-system-running"])` |
| `has_sudo` | `shutil.which("sudo")` exists |
| `passwordless_sudo` | `subprocess.run(["sudo", "-n", "true"])` returns 0 |
| `is_root` | `os.getuid() == 0` |
| `primary package_manager` | Check in order: `shutil.which("apt-get")` → `shutil.which("dnf")` → ... |
| `snap_available` | `shutil.which("snap")` AND `has_systemd` |
| `openssl_version` | `subprocess.run(["openssl", "version"])` → parse |
| `glibc_version` | `ctypes.CDLL("libc.so.6").gnu_get_libc_version()` |
| `libc_type` | `ldd --version` → if "musl" in output → musl, else glibc |

---

## 4. The Recipe Model Needed

### 4.1 Recipe Structure

Each tool recipe is a dict with install commands PER PLATFORM:

```python
TOOL_RECIPES = {
    "kubectl": {
        "label": "kubectl",
        "install": {
            "apt":  ["apt-get", "install", "-y", "kubectl"],  # or from k8s repo
            "snap": ["snap", "install", "kubectl", "--classic"],
            "dnf":  ["dnf", "install", "-y", "kubectl"],
            "brew": ["brew", "install", "kubectl"],
            "apk":  ["apk", "add", "kubectl"],
            "binary": {  # fallback: direct binary download
                "url_template": "https://dl.k8s.io/release/{version}/bin/{os}/{arch}/kubectl",
                "dest": "/usr/local/bin/kubectl",
            },
        },
        "needs_sudo": {
            "apt": True, "snap": True, "dnf": True,
            "brew": False, "apk": True, "binary": True,
        },
        "requires": {},  # no special deps
    },

    "cargo-outdated": {
        "label": "cargo-outdated",
        "install": {
            "_default": ["cargo", "install", "cargo-outdated"],
        },
        "needs_sudo": {"_default": False},
        "requires": {
            "binaries": ["cargo"],
            "packages": {
                "debian": ["pkg-config", "libssl-dev", "libcurl4-openssl-dev"],
                "rhel":   ["pkgconf-pkg-config", "openssl-devel", "libcurl-devel"],
                "alpine": ["pkgconf", "openssl-dev", "curl-dev"],
                "brew":   ["pkg-config", "openssl@3", "curl"],
            },
        },
        "post_env": 'export PATH="$HOME/.cargo/bin:$PATH"',
    },

    "cargo": {
        "label": "Cargo (Rust)",
        "install": {
            "_default": ["bash", "-c", "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y"],
        },
        "needs_sudo": {"_default": False},
        "requires": {
            "binaries": ["curl"],
        },
        "post_env": 'export PATH="$HOME/.cargo/bin:$PATH"',
    },

    "pkg-config": {
        "label": "pkg-config",
        "install": {
            "apt": ["apt-get", "install", "-y", "pkg-config"],
            "dnf": ["dnf", "install", "-y", "pkgconf-pkg-config"],
            "apk": ["apk", "add", "pkgconf"],
            "brew": ["brew", "install", "pkg-config"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True, "brew": False},
        "requires": {},
    },

    # ... every tool
}
```

### 4.2 Key Design Points

1. **`install` is a dict keyed by package manager** (not a single command list).
   The resolver picks the right one based on system profile.

2. **`_default`** means "works on any system" (e.g. cargo install, pip install).

3. **`requires.packages` is keyed by distro FAMILY** (debian, rhel, alpine, brew).
   Each family has its own package names.

4. **`requires.binaries`** are tool IDs that must exist on PATH.
   Each binary ID points to another recipe in `TOOL_RECIPES` → recursion.

5. **`needs_sudo` is per-package-manager.** apt needs sudo. brew doesn't.

6. **`post_env`** is shell commands to set after install (e.g. PATH update for cargo).

---

## 5. The Resolver

### 5.1 Input/Output

```python
def resolve_install_plan(tool: str, system_profile: dict) -> list[dict]:
    """
    Walk the dependency tree for `tool` given the detected `system_profile`.
    
    Returns an ordered list of install steps:
    [
        {"id": "system-pkgs", "type": "packages", "label": "Install system packages",
         "packages": ["pkg-config", "libssl-dev", "libcurl4-openssl-dev"],
         "command": ["apt-get", "install", "-y", "pkg-config", "libssl-dev", "libcurl4-openssl-dev"],
         "needs_sudo": True},

        {"id": "cargo", "type": "tool", "label": "Install Cargo (Rust)",
         "command": ["bash", "-c", "curl ... | sh -s -- -y"],
         "needs_sudo": False,
         "post_env": "export PATH=..."},

        {"id": "cargo-outdated", "type": "tool", "label": "Install cargo-outdated",
         "command": ["bash", "-c", "export PATH=... && cargo install cargo-outdated"],
         "needs_sudo": False},
    ]
    
    Empty list if tool is already installed.
    Each step only appears if not already satisfied.
    System packages are BATCHED into one step per package manager.
    Steps are topologically sorted (deps first).
    """
```

### 5.2 Algorithm

```
1. Look up recipe for `tool`
2. If tool binary already installed → return []
3. Collect all requires.binaries (recursive)
4. Collect all requires.packages (mapped to current distro family)
5. Filter out already-installed binaries (shutil.which)
6. Filter out already-installed packages (dpkg-query / rpm -q / etc.)
7. Batch system packages into one step
8. Order: system packages first, then binary deps (topological), then target tool
9. For each step, pick the install command for the detected package manager
10. Return ordered steps
```

### 5.3 Package Manager Selection

```
For system packages (apt packages, dev headers):
  → use system_profile.package_manager.primary

For snaps (kubectl, terraform...):
  → use snap IF system_profile.package_manager.snap_available
  → ELSE fall back to binary download or alternative

For pip tools (ruff, mypy...):
  → always use [sys.executable, "-m", "pip", "install", ...]
  → no system dependency needed

For cargo tools:
  → always use ["cargo", "install", ...]
  → requires cargo binary + compilation deps

For npm tools:
  → always use ["npm", "install", "-g", ...]
  → requires npm binary
```

---

## 6. The System Package Check (per distro)

Current `check_system_deps()` uses `dpkg-query` — Debian/Ubuntu only.

Needs to support:

| Distro family | Check command | Check output |
|---------------|--------------|-------------|
| debian (apt) | `dpkg-query -W -f='${Status}' PKG` | "install ok installed" |
| rhel (dnf) | `rpm -q PKG` | exit code 0 = installed |
| alpine (apk) | `apk info -e PKG` | exit code 0 = installed |
| arch (pacman) | `pacman -Qi PKG` | exit code 0 = installed |
| suse (zypper) | `rpm -q PKG` | exit code 0 = installed |
| macos (brew) | `brew list PKG` | exit code 0 = installed |

The function becomes:

```python
def check_system_deps(packages: list[str], pkg_manager: str) -> dict:
    """Check which packages are installed using the given package manager."""
    checkers = {
        "apt":    lambda pkg: _run_check(["dpkg-query", "-W", "-f=${Status}", pkg], "install ok installed"),
        "dnf":    lambda pkg: _run_check(["rpm", "-q", pkg]),
        "apk":    lambda pkg: _run_check(["apk", "info", "-e", pkg]),
        "pacman": lambda pkg: _run_check(["pacman", "-Qi", pkg]),
        "brew":   lambda pkg: _run_check(["brew", "list", pkg]),
    }
    # ...
```

---

## 7. The Frontend

### 7.1 Stacked Modal Executor

One function: `executeInstallPlan(steps, onAllDone)`

```
executeInstallPlan(steps, onAllDone):
    stepIndex = 0
    
    function runNextStep():
        if stepIndex >= steps.length:
            onAllDone()
            return
        
        step = steps[stepIndex]
        showStepModal(step, stepIndex+1, steps.length, function onStepDone():
            stepIndex++
            runNextStep()
        )
    
    runNextStep()
```

### 7.2 StepModal — One Function for All Types

`showStepModal(step, currentNum, totalNum, onSuccess)`:

- Creates a stacked overlay (z-index: 10001 + depth)
- Header: "📦 Step 1/3 — Install system packages"
- Body depends on `needs_sudo`:
  - YES: password input + Install button
  - NO: just Install button
- Log area: `<pre>` for streaming output
- Calls `/api/audit/remediate` with streaming
- On success: removes overlay, calls onSuccess
- On failure: shows error in label, Retry button

### 7.3 streamSSE Helper

One reusable function:

```javascript
async function streamSSE(url, body, logEl) {
    var res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    var reader = res.body.getReader();
    var decoder = new TextDecoder();
    var result = { ok: false };
    var buf = '';
    while (true) {
        var chunk = await reader.read();
        if (chunk.done) break;
        buf += decoder.decode(chunk.value, { stream: true });
        var lines = buf.split('\n');
        buf = lines.pop() || '';
        for (var i = 0; i < lines.length; i++) {
            var ln = lines[i];
            if (!ln.startsWith('data: ')) continue;
            try {
                var evt = JSON.parse(ln.slice(6));
                if (evt.line !== undefined && logEl) {
                    logEl.textContent += evt.line + '\n';
                    logEl.scrollTop = logEl.scrollHeight;
                }
                if (evt.done) result = evt;
            } catch (_) {}
        }
    }
    return result;
}
```

### 7.4 Entry Point Change

`installToolFromBanner()` becomes:

```
1. fetch /api/audit/install-plan { tool: toolId }
2. if plan.steps.length === 0 → already installed, toast ✅
3. if plan.steps.length === 1 and !needs_sudo → direct install (simple path)
4. else → executeInstallPlan(plan.steps, refreshUI)
```

---

## 8. Endpoint Summary

| Endpoint | Status | Purpose |
|----------|--------|---------|
| `POST /audit/install-plan` | **NEW** | Resolve dependency tree → ordered steps |
| `POST /audit/remediate` | KEEP | Stream command execution (SSE) |
| `POST /audit/check-deps` | KEEP | Check if packages installed |
| `POST /audit/install-tool` | KEEP (backward compat) | Simple installs |
| `GET /tools/status` | KEEP | Dashboard tool status |
| `GET /api/system-profile` | **NEW** (or extend existing) | Full system profile for frontend |

---

## 9. Files Affected

### Backend
| File | Changes |
|------|---------|
| `l0_detection.py` | Extend `_detect_os()` with distro family, container, capabilities, pkg manager, library versions |
| `tool_install.py` | New `TOOL_RECIPES` dict, `resolve_install_plan()`, updated `check_system_deps()` |
| `tool_requirements.py` | Update to use `TOOL_RECIPES` instead of separate recipe dicts |
| `routes_audit.py` | New `/audit/install-plan` endpoint, optional `/api/system-profile` |

### Frontend
| File | Changes |
|------|---------|
| `_globals.html` | New `streamSSE()`, `showStepModal()`, `executeInstallPlan()`. Update `installToolFromBanner()`. |
| `_globals.html` | REMOVE: `_showDepsModal`, `_depsInstall`, duplicate stream readers |
| `_globals.html` | KEEP: `_showRemediationModal` (for error analysis — different concern) |

---

## 10. What Stays vs What's Replaced

| Current piece | Fate | Why |
|---------------|------|-----|
| `_NO_SUDO_RECIPES` | MERGED into `TOOL_RECIPES` | One source of truth |
| `_SUDO_RECIPES` | MERGED into `TOOL_RECIPES` | One source of truth |
| `CARGO_BUILD_DEPS` | MOVED into recipe `requires.packages` | Per-recipe, per-distro |
| `_RUNTIME_DEPS` / `_TOOL_REQUIRES` | REPLACED by recipe `requires.binaries` | Per-recipe |
| `check_system_deps()` | EXTENDED with pkg_manager param | Multi-distro support |
| `_analyse_install_failure()` | STAYS | Fallback for unexpected failures |
| `install_tool()` | STAYS | Backward compat for simple installs |
| `_detect_os()` | EXTENDED | Add family, container, capabilities, pkg_manager |
| `ops-modal` (sudo) | REPLACED by `showStepModal` | One modal pattern |
| `_showDepsModal` | REPLACED by `showStepModal` type=packages | One modal pattern |
| `_showDepInstallModal` | REPLACED by `executeInstallPlan` | Recursive chain |
| `_showRemediationModal` | STAYS | Error analysis options (different concern) |
| `streamCommand()` | REPLACED by `streamSSE()` | One helper |
| `_depsInstall` stream code | REPLACED by `streamSSE()` | One helper |
| `pages_install.py` | FUTURE: could use same pattern | Currently separate |

---

## 11. Migration Path

### Phase 1: System Detection Enhancement
- Extend `_detect_os()` in `l0_detection.py`
- Add distro family, container detection, package manager detection
- Add capabilities (systemd, sudo, root)
- Add library versions (openssl, glibc, libc type)
- Expose via `/api/system-profile` or extend existing endpoint

### Phase 2: Recipe Unification
- Create `TOOL_RECIPES` dict with per-platform install commands
- Create `resolve_install_plan()` function
- Update `check_system_deps()` for multi-distro
- Create `/api/audit/install-plan` endpoint

### Phase 3: Frontend Unification
- Create `streamSSE()` helper
- Create `showStepModal()` — one modal for all step types
- Create `executeInstallPlan()` — recursive stacked modal executor
- Update `installToolFromBanner()` to use plan endpoint

### Phase 4: Cleanup
- Remove old modal functions
- Remove duplicate stream readers
- Remove inline `_RUNTIME_DEPS` / `_TOOL_REQUIRES`
- Keep `_analyse_install_failure()` as fallback
- Keep `install_tool()` for backward compat

### Phase 5: Future
- Extend `pages_install.py` to use same pattern
- Add more distro-specific recipes as needed
- Add binary download fallbacks for tools
- Add PPA/repo addition as a step type (e.g. hashicorp repo for terraform)
