# docker — Full Spectrum Analysis

> **Tool ID:** `docker`
> **Last audited:** 2026-02-26
> **Status:** ✅ Complete

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Docker — container runtime and CLI |
| Language | Go |
| CLI binary | `docker` |
| Category | `container` |
| Verify command | `docker --version` |
| Recipe key | `docker` |

### Special notes
- Docker is composed of multiple components: the **daemon** (`dockerd`), the
  **CLI** (`docker`), and the **container runtime** (`containerd`).
- Package managers typically bundle all three, but `brew` on macOS installs
  the CLI only — the daemon runs via Docker Desktop (a separate cask).
- The `_default` install method uses Docker's official convenience script
  (`get.docker.com`), which auto-detects the OS, architecture, and distro.
  This works on Raspbian/Raspberry Pi OS (arm64) and all supported Linux distros.
- Docker v28 is the last major version to support Raspberry Pi OS 32-bit (armhf).
  Docker v29+ drops armhf support for Raspberry Pi OS (Debian armhf is still supported).

---

## 2. Package Availability

| PM | Available | Package name | Source |
|----|-----------|--------------|--------|
| `apt` | ✅ | `docker.io` | Debian/Ubuntu distro repos (NOT Docker's `docker-ce`) |
| `dnf` | ✅ | `docker` | Fedora repos (`moby-engine` white-label, equivalent) |
| `apk` | ✅ | `docker` | Alpine community repo |
| `pacman` | ✅ | `docker` | Arch extra repo |
| `zypper` | ✅ | `docker` | openSUSE repos |
| `brew` | ✅ | `docker` | formulae.brew.sh (CLI only, no daemon) |
| `snap` | ✅ | `docker` | snapcraft.io — available but NOT in recipe (snap Docker has networking/storage limitations) |
| `pip` | ❌ | — | Not available |
| `npm` | ❌ | — | Not available |
| `cargo` | ❌ | — | Not available |
| `go` | ❌ | — | Not available (internal Go binary) |

### Package name notes
- **apt:** `docker.io` is the Debian-maintained package. Docker's official repo
  provides `docker-ce` + `docker-ce-cli` + `containerd.io` but requires adding
  Docker's apt repository first. Our recipe uses `docker.io` for simplicity —
  it's always available in default Debian/Ubuntu repos without repo setup.
- **dnf:** On Fedora, `docker` resolves to `moby-engine` which is the OSS
  equivalent of Docker CE. Docker's official repo provides `docker-ce` on
  Fedora/RHEL but requires repo setup.
- **brew:** Installs CLI tools only. Docker Desktop (the macOS daemon) is
  `brew install --cask docker` — a separate concern.
- **snap:** Docker snap exists and works but has known limitations with
  volume mounts and networking. Not included in the recipe.

---

## 3. Binary Download (_default)

| Field | Value |
|-------|-------|
| Installer | https://get.docker.com (convenience script) |
| Method | `curl -fsSL https://get.docker.com | sudo sh` |
| Arch detection | Auto-detected by the script (no `{arch}` substitution needed) |
| Supported archs | `x86_64`, `aarch64` (arm64), `armv7l` (armhf, Docker ≤ v28) |
| Dependencies | `curl` (download) |
| needs_sudo | Yes (the script calls `apt-get`/`dnf`/`apk` internally with sudo) |

### How get.docker.com works
The convenience script:
1. Detects the OS, distro, version, and architecture
2. Adds Docker's official apt/dnf/zypper repository
3. Installs `docker-ce`, `docker-ce-cli`, `containerd.io`, `docker-buildx-plugin`, `docker-compose-plugin`
4. This means `_default` actually installs from Docker's official repo, NOT distro packages

### Raspbian / Raspberry Pi OS
The `get.docker.com` script explicitly supports Raspbian:
- Detects `raspbian` from `/etc/os-release`
- Maps to Docker's Debian arm64 repository
- Fully functional on Raspberry Pi 4/5 with 64-bit OS

---

## 4. Build from Source

| Field | Value |
|-------|-------|
| Build system | Go (`make`) |
| Git repo | https://github.com/moby/moby.git (engine), https://github.com/docker/cli.git (CLI) |
| Build deps | `go` (1.21+), `make`, `git`, `btrfs-progs-dev`, `libseccomp-dev` |
| Complexity | Very high — multiple repos, complex dependency chain |

Not included in recipe — Docker is too complex to build from source reliably.
The official convenience script is the recommended alternative.

---

## 5. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For `_default` install method |
| Runtime | `containerd` | Container runtime (bundled in all standard installs) |
| Runtime | `iptables` | Network isolation (usually pre-installed on Linux) |

### Reverse deps
- `docker-compose` — requires `docker` (compose is a CLI plugin)
- `buildx` — Docker Buildx plugin
- Tools using Docker: `act`, `trivy`, `lazydocker`

---

## 6. Post-install

### 6.1 Post-install steps (in recipe)
| Step | Command | Condition |
|------|---------|-----------|
| Start Docker daemon | `systemctl start docker` | `has_systemd` |
| Enable Docker on boot | `systemctl enable docker` | `has_systemd` |
| Add user to docker group | `usermod -aG docker $USER` | `not_root` |

### 6.2 Notes
- After adding user to docker group, a **logout/login** (or `newgrp docker`)
  is required for the change to take effect.
- On Alpine (OpenRC), the equivalent is `rc-update add docker default` +
  `service docker start`. This is handled by the `docker_daemon_not_running`
  failure handler.

---

## 7. Failure Surface

### 7.1 Per-install-method failures
All PM-based install methods have dedicated Layer 2 METHOD_FAMILY_HANDLERS:

| PM | Handlers | IDs |
|----|---------|-----|
| `apt` | Package not found, DB locked | `apt_stale_index`, `apt_locked` |
| `dnf` | Package not found | `dnf_no_match` |
| `apk` | Unsatisfiable constraints, DB locked | `apk_unsatisfiable`, `apk_locked` |
| `pacman` | Target not found, DB locked | `pacman_target_not_found`, `pacman_locked` |
| `zypper` | Package not found, PM locked | `zypper_not_found`, `zypper_locked` |
| `brew` | Formula not found | `brew_no_formula` |
| `_default` | Missing curl/git/wget/unzip/npm | 5 dependency handlers |

All methods also inherit Layer 1 INFRA_HANDLERS (network, disk, permissions,
timeout, OOM — 9 total).

### 7.2 Tool-specific failures (Layer 3 on_failure)

| Failure | Pattern | Category | Handler ID |
|---------|---------|----------|-----------|
| Daemon not running | `Cannot connect to the Docker daemon` | environment | `docker_daemon_not_running` |
| Socket permission denied | `permission denied.*docker.sock` | permissions | `docker_socket_permission` |
| Docker not installed | `docker: command not found` | dependency | `docker_not_installed` |
| containerd not running | `containerd is not running` | environment | `docker_containerd_down` |
| Storage driver error | `error initializing graphdriver` | environment | `docker_storage_driver` |
| API version mismatch | `client version .* is too old` | compatibility | `docker_version_mismatch` |
| Port already allocated | `port is already allocated` | environment | `docker_port_conflict` |
| cgroup v2 incompatibility | `OCI runtime create failed.*cgroup` | compatibility | `docker_cgroup_v2` |

---

## 8. Handler Layers

### Layer 1: INFRA_HANDLERS (existing)
9 cross-tool handlers apply. No changes needed.

### Layer 2: METHOD_FAMILY_HANDLERS
- `apt` family: `apt_stale_index`, `apt_locked` — existing
- `dnf` family: `dnf_no_match` — existing
- `apk` family: `apk_unsatisfiable`, `apk_locked` — existing
- `pacman` family: `pacman_target_not_found`, `pacman_locked` — existing
- `zypper` family: `zypper_not_found`, `zypper_locked` — existing
- `brew` family: `brew_no_formula` — existing
- `_default` family: 5 handlers (missing_curl, missing_git, etc.) — existing

### Layer 3: Recipe on_failure
8 handlers. See §7.2.

### Handler detail: docker_daemon_not_running
4 options covering all init systems and platforms:
- `start-docker-systemd` — systemd (most Linux distros)
- `start-docker-openrc` — OpenRC (Alpine, Raspbian variants)
- `start-dockerd-manual` — raw dockerd (WSL, containers)
- `start-docker-desktop` — macOS

### Handler detail: docker_socket_permission
2 options:
- `add-docker-group` — permanent fix (requires logout)
- `use-sudo` — temporary workaround

### Handler detail: docker_containerd_down
3 options:
- `start-containerd` — systemd
- `reinstall-containerd` — per-distro packages
- `restart-docker-desktop-containerd` — macOS

### Handler detail: docker_storage_driver
3 options:
- `reset-storage` — destructive reset (high risk)
- `switch-overlay2` — manual daemon.json edit
- `reset-docker-desktop-storage` — macOS

---

## 9. Availability Gates

No new capability gates needed. Docker handlers use:
- `env_fix` with `fix_commands` — systemctl, usermod, etc.
- `install_dep` with `dep: "docker"` — self-referencing for upgrades
- `install_packages` with per-distro packages — containerd reinstall
- `cleanup_retry` — storage reset
- `manual` — macOS instructions, port investigation
- `retry_with_modifier` — sudo workaround

System-specific `requires` gates used:
- `has_systemd` — systemd-based options
- `is_linux` — Linux-only options
- `not_root` — user group addition
- `not_container` — cgroup kernel parameter changes
- `writable_rootfs` — storage cleanup

---

## 10. Resolver Data

### KNOWN_PACKAGES
Already present:
```python
"docker": {
    "apt": "docker.io", "dnf": "docker",
    "apk": "docker", "pacman": "docker",
    "zypper": "docker", "brew": "docker",
},
```

### LIB_TO_PACKAGE_MAP
No C library dependencies. No changes needed.

### Special installers
Uses `get.docker.com` convenience script in `_default` — no special installer entry needed.

---

## 11. Recipe — After

```python
"docker": {
    "cli": "docker",
    "label": "Docker",
    "category": "container",
    "install": {
        "apt":    ["apt-get", "install", "-y", "docker.io"],
        "dnf":    ["dnf", "install", "-y", "docker"],
        "apk":    ["apk", "add", "docker"],
        "pacman": ["pacman", "-S", "--noconfirm", "docker"],
        "zypper": ["zypper", "install", "-y", "docker"],
        "brew":   ["brew", "install", "docker"],
        "_default": ["bash", "-c", "curl -fsSL https://get.docker.com | sudo sh"],
    },
    "needs_sudo": {
        "apt": True, "dnf": True, "apk": True,
        "pacman": True, "zypper": True, "brew": False,
        "_default": True,
    },
    "requires": {"binaries": ["curl"]},
    "post_install": [
        {"label": "Start Docker daemon", "command": [...], "condition": "has_systemd"},
        {"label": "Enable Docker on boot", "command": [...], "condition": "has_systemd"},
        {"label": "Add user to docker group", "command": [...], "condition": "not_root"},
    ],
    "verify": ["docker", "--version"],
    "update": {
        "apt":    [..., "docker.io"],
        "dnf":    [..., "docker"],
        "apk":    [..., "docker"],
        "pacman": [..., "docker"],
        "zypper": [..., "docker"],
        "brew":   ["brew", "upgrade", "docker"],
        "_default": [..., "curl -fsSL https://get.docker.com | sudo sh"],
    },
    "on_failure": [
        # docker_daemon_not_running — 4 options (systemd, openrc, manual, macos)
        # docker_socket_permission — 2 options (add-docker-group, use-sudo)
        # docker_not_installed — 1 option (install_dep)
        # docker_containerd_down — 3 options (start, reinstall, macos)
        # docker_storage_driver — 3 options (reset, overlay2, macos)
        # docker_version_mismatch — 1 option (upgrade)
        # docker_port_conflict — 1 option (manual investigation)
        # docker_cgroup_v2 — 2 options (upgrade, kernel param)
    ],
},
```

---

## 12. Validation Results

```
Schema:    VALID (recipe + 8 on_failure handlers + 10 PM family handlers)
Coverage:  608/608 (100%) — 32 scenarios × 19 presets
Zero-opts: PASSED — every handler has ≥1 ready option on every system
Regression: PASSED — full suite exit code 0, no new errors
```

---

## 13. Changes Applied

| File | Change | Line |
|------|--------|------|
| `data/recipes.py` | Added `brew` install method | 766 |
| `data/recipes.py` | Added `brew: False` to `needs_sudo` | 773 |
| `data/recipes.py` | Added `brew` update method | 805 |
| `data/recipes.py` | Added `_default` update method (re-runs get.docker.com) | 806-809 |
| `resolver/dynamic_dep_resolver.py` | `brew: "docker"` already present in KNOWN_PACKAGES | 233 |

### Pre-existing (no changes needed)
| Component | Status |
|-----------|--------|
| `cli` field | ✅ Present (`docker`) |
| `category` field | ✅ Present (`container`) |
| `label` field | ✅ Present (`Docker`) |
| `post_install` | ✅ 3 steps (daemon start, boot enable, group add) |
| `on_failure` | ✅ 8 handlers with 17 total options |
| KNOWN_PACKAGES | ✅ Already present with correct per-PM names |
| LIB_TO_PACKAGE_MAP | ✅ Not needed (no C library deps) |
| INFRA_HANDLERS | ✅ 9 cross-tool handlers apply |
| METHOD_FAMILY_HANDLERS | ✅ All 10 PM families covered |

---

## 14. Raspbian / ARM Notes

| Aspect | Status |
|--------|--------|
| `_default` (get.docker.com) | ✅ Supports Raspbian arm64 natively |
| `apt` (docker.io) | ✅ Available in Raspbian repos |
| `post_install` (systemd) | ✅ Raspbian uses systemd |
| Architecture mapping | ✅ Not an issue — no `{arch}` in Docker's _default method |
| armhf (32-bit) | ⚠️ Docker v29+ drops Raspberry Pi OS armhf support |
