# podman — Full Spectrum Analysis

> **Tool ID:** `podman`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Podman — daemonless container engine |
| Language | Go |
| CLI binary | `podman` |
| Category | `container` |
| Verify command | `podman --version` |
| Recipe key | `podman` |

### Special notes
- By Red Hat / containers project.
- Drop-in Docker replacement — daemonless, rootless by default.
- OCI-compliant container runtime.
- **Available in ALL native package managers** — widest coverage
  of any tool in the system.
- No `_default` binary download needed.
- snap exists but edge-only (unstable) — not included.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `podman` | Debian 11+, Ubuntu 20.10+ |
| `dnf` | ✅ | `podman` | Fedora, RHEL, CentOS |
| `apk` | ✅ | `podman` | Alpine community |
| `pacman` | ✅ | `podman` | Arch extra |
| `zypper` | ✅ | `podman` | openSUSE repos |
| `brew` | ✅ | `podman` | macOS formula |
| `snap` | ⚠️ | `podman` | Edge channel only — unstable |

---

## 3. Installation

### Via native PM (all platforms)

Every supported platform has podman in its native package manager.
No fallback `_default` method is needed.

| Platform | Method | PM |
|----------|--------|-----|
| Debian/Ubuntu | `apt-get install -y podman` | apt |
| Fedora/RHEL | `dnf install -y podman` | dnf |
| Alpine | `apk add podman` | apk |
| Arch | `pacman -S --noconfirm podman` | pacman |
| openSUSE | `zypper install -y podman` | zypper |
| macOS | `brew install podman` | brew |

All native PM installs require sudo except brew.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Runtime | Linux kernel features | cgroups, namespaces |
| Runtime | conmon | Container monitor (usually auto-installed) |
| Runtime | netavark/CNI | Networking (usually auto-installed) |

All runtime dependencies are handled automatically by package managers.

---

## 5. Post-install

No PATH additions needed — package managers place `podman` in standard
system paths. On macOS, `podman machine init && podman machine start`
is needed to create a Linux VM for containers.

---

## 6. Failure Handlers

### Layer 2a: method-family handlers (per PM)
| Family | Handler | Trigger |
|--------|---------|---------|
| `apt` | `apt_stale_index` | Package not found — stale index |
| `apt` | `apt_locked` | Package manager locked |
| `dnf` | `dnf_no_match` | Package not found |
| `apk` | `apk_unsatisfiable` | Package not found |
| `apk` | `apk_locked` | Database locked |
| `pacman` | `pacman_target_not_found` | Package not found |
| `pacman` | `pacman_locked` | Database locked |
| `zypper` | `zypper_not_found` | Package not found |
| `zypper` | `zypper_locked` | Package manager locked |
| `brew` | `brew_no_formula` | Formula not found |

### Layer 1: INFRA handlers (9 cross-tool)
Network, disk, permissions, OOM, timeout — all standard.

### Layer 3: per-tool on_failure handlers
None needed. Podman uses standard PM installs only.

---

## 7. Recipe Structure

```python
"podman": {
    "cli": "podman",
    "label": "Podman (daemonless container engine)",
    "category": "container",
    "install": {
        "apt":     ["apt-get", "install", "-y", "podman"],
        "dnf":     ["dnf", "install", "-y", "podman"],
        "apk":     ["apk", "add", "podman"],
        "pacman":  ["pacman", "-S", "--noconfirm", "podman"],
        "zypper":  ["zypper", "install", "-y", "podman"],
        "brew":    ["brew", "install", "podman"],
    },
    "needs_sudo": {
        "apt": True, "dnf": True, "apk": True,
        "pacman": True, "zypper": True, "brew": False,
    },
    "prefer": ["apt", "dnf", "apk", "pacman", "zypper", "brew"],
    "verify": ["podman", "--version"],
    "update": { ... },  # per-PM update commands
}
```

---

## 8. Validation Results

```
Schema:    VALID (recipe + all method-family handlers)
Coverage:  361/361 (100%) — 19 scenarios × 19 presets
Handlers:  2 apt + 1 dnf + 2 apk + 2 pacman + 2 zypper + 1 brew + 9 INFRA = 19
```

---

## 9. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "podman"` |
| `data/recipes.py` | Updated label to `"Podman (daemonless container engine)"` |
| `data/recipes.py` | Added `prefer` list |
| `data/recipes.py` | Added missing update commands for apk, pacman, zypper |

---

## 10. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS (arm64/Intel)** | brew | Needs `podman machine` for VM |
| **Raspbian (aarch64)** | apt | Standard repos |
| **Debian/Ubuntu** | apt | Debian 11+, Ubuntu 20.10+ |
| **Fedora/RHEL** | dnf | Native support |
| **Alpine** | apk | Community repos |
| **Arch** | pacman | Extra repos |
| **openSUSE** | zypper | Standard repos |

---

## 11. Future Enhancements

- **Machine init**: Could auto-detect macOS and suggest
  `podman machine init && podman machine start`.
- **Rootless setup**: Could offer `podman system migrate` for
  rootless configuration on Linux.
