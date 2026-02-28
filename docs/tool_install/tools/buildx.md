# buildx — Full Spectrum Analysis

> **Tool ID:** `buildx`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Docker Buildx — extended build capabilities |
| Language | Go |
| CLI binary | `docker` (plugin — cli_verify_args: buildx version) |
| Category | `container` |
| Verify command | `docker buildx version` |
| Recipe key | `buildx` |

### Special notes
- **Docker CLI plugin** — NOT a standalone binary.
- Installs to `~/.docker/cli-plugins/docker-buildx`.
- Provides multi-platform builds and BuildKit integration.
- cli is `docker`, verified via `docker buildx version`.
- Requires Docker as runtime dependency.
- Available in apt/dnf (`docker-buildx-plugin`), pacman (`docker-buildx`),
  brew (`docker-buildx`), and GitHub releases.
- Original `_default` was broken: nested `{"linux": [...]}` with hardcoded `amd64`.
- Fixed to flat list with GitHub raw binary download.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `docker-buildx-plugin` | Docker official repo |
| `dnf` | ✅ | `docker-buildx-plugin` | Docker official repo |
| `pacman` | ✅ | `docker-buildx` | Arch extra |
| `brew` | ✅ | `docker-buildx` | Standard formula |
| `apk` | ❌ | — | Not available |
| `zypper` | ❌ | — | Not in standard repos |
| `snap` | ❌ | — | Part of docker snap |

---

## 3. Installation (_default via GitHub raw binary)

| Field | Value |
|-------|-------|
| Method | Raw binary download + install to cli-plugins dir |
| URL pattern | `github.com/docker/buildx/releases/latest/download/buildx-v{ver}.{os}-{arch}` |
| Install location | `~/.docker/cli-plugins/docker-buildx` |
| Arch naming | `amd64`, `arm64` (Go-standard) |
| OS naming | `linux`, `darwin` |
| Archive format | None — raw binary |
| needs_sudo | No (user-level plugin dir) |
| install_via | `binary_download` |

### Asset naming detail
```
buildx-v0.31.1.linux-amd64    — note the DOT separator!
buildx-v0.31.1.linux-arm64
buildx-v0.31.1.darwin-amd64
buildx-v0.31.1.darwin-arm64
```

### What was broken
- Original: nested `_default.linux` — not a flat list
- Hardcoded `amd64` — no ARM64 support
- Used `curl -sSL` not `curl -sSfL` (no fail on HTTP errors)
- No `{os}` or `{arch}` placeholders

### Platform considerations
- **macOS**: brew preferred (formula: `docker-buildx`).
- **Raspbian ARM (aarch64)**: apt preferred (if Docker repo configured).
  _default with `{arch}=arm64` works.
- **Alpine**: _default only — no apk package.
- **Arch**: pacman `docker-buildx`.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Runtime | `docker` | **Required** — buildx is a Docker plugin |
| Download | `curl` | For _default method |

---

## 5. Post-install

Plugin directory `~/.docker/cli-plugins/` is created automatically by
the install command. No PATH changes needed — Docker discovers plugins
in this directory.

---

## 6. Failure Handlers

### Layer 2a: method-family handlers
| Family | Handler | Trigger |
|--------|---------|---------|
| `apt` | `apt_stale_index` | Package not found — stale index |
| `apt` | `apt_locked` | Package manager locked |
| `dnf` | `dnf_no_match` | Package not found |
| `pacman` | `pacman_target_not_found` | Package not found |
| `pacman` | `pacman_locked` | Database locked |
| `brew` | `brew_no_formula` | Formula not found |
| `_default` | `missing_curl` | curl not installed |
| `_default` | `missing_git` | git not installed |
| `_default` | `missing_wget` | wget not installed |
| `_default` | `missing_unzip` | unzip not installed |
| `_default` | `missing_npm_default` | npm not installed |

### Layer 1: INFRA handlers (9 cross-tool)
Network, disk, permissions, OOM, timeout — all standard.

### Layer 3: per-tool on_failure handlers
None needed. Standard PM + binary download.

---

## 7. Recipe Structure

```python
"buildx": {
    "cli": "docker",
    "label": "Docker Buildx (extended build capabilities)",
    "category": "container",
    "cli_verify_args": ["buildx", "version"],
    "install": {
        "apt":     ["apt-get", "install", "-y", "docker-buildx-plugin"],
        "dnf":     ["dnf", "install", "-y", "docker-buildx-plugin"],
        "pacman":  ["pacman", "-S", "--noconfirm", "docker-buildx"],
        "brew":    ["brew", "install", "docker-buildx"],
        "_default": [
            "bash", "-c",
            "mkdir -p ~/.docker/cli-plugins"
            " && curl -sSfL .../buildx-v0.31.1.{os}-{arch}"
            " -o ~/.docker/cli-plugins/docker-buildx"
            " && chmod +x ~/.docker/cli-plugins/docker-buildx",
        ],
    },
    "needs_sudo": {
        "apt": True, "dnf": True, "pacman": True,
        "brew": False, "_default": False,
    },
    "install_via": {"_default": "binary_download"},
    "requires": {"binaries": ["docker", "curl"]},
    "arch_map": {"x86_64": "amd64", "aarch64": "arm64"},
    "prefer": ["apt", "dnf", "pacman", "brew"],
    "verify": ["docker", "buildx", "version"],
    "update": { ... },  # per-method update commands
}
```

---

## 8. Validation Results

```
Schema:    VALID (recipe + all method-family handlers)
Coverage:  380/380 (100%) — 20 scenarios × 19 presets
Handlers:  2 apt + 1 dnf + 2 pacman + 1 brew + 5 _default + 9 INFRA = 20
```

---

## 9. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Fixed broken nested `_default.linux` → flat list |
| `data/recipes.py` | Fixed hardcoded `amd64` → `{os}-{arch}` placeholders |
| `data/recipes.py` | Changed `install_via` from `github_release` → `binary_download` |
| `data/recipes.py` | Added `pacman` method (Arch `docker-buildx`) |
| `data/recipes.py` | Added `brew` method |
| `data/recipes.py` | Added `arch_map`, `prefer`, `update` |
| `data/recipes.py` | Added `curl` to `requires.binaries` |
| `data/recipes.py` | Updated label with description |

---

## 10. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS (arm64/Intel)** | brew | Standard formula |
| **Raspbian (aarch64)** | apt or _default | Docker repo needed for apt |
| **Debian/Ubuntu** | apt | `docker-buildx-plugin` |
| **Fedora/RHEL** | dnf | `docker-buildx-plugin` |
| **Alpine** | _default | Raw binary download |
| **Arch** | pacman | `docker-buildx` |

---

## 11. Future Enhancements

- **Dynamic version**: Replace hardcoded `v0.31.1` with API-resolved
  latest version.
- **Docker check**: Could verify Docker is running before install.
