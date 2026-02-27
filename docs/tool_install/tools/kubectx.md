# kubectx — Full Spectrum Analysis

> **Tool ID:** `kubectx`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | kubectx + kubens — Kubernetes context and namespace switcher |
| Language | Go |
| CLI binary | `kubectx` (also installs `kubens`) |
| Category | `k8s` |
| Verify command | `kubectx --help` |
| Recipe key | `kubectx` |

### Special notes
- Installs **two binaries**: `kubectx` (switch contexts) and `kubens`
  (switch namespaces).
- Originally bash scripts, rewritten in Go since v0.9.0.
- Single static binaries — no runtime deps beyond kubeconfig.
- **Uses `x86_64` in asset names** (not `amd64`!) — no arch_map needed
  for x86_64. Only `aarch64→arm64` and `armv7l→armv7` mapped.
- Tag version **included** in filename: `kubectx_v0.9.5_linux_x86_64.tar.gz`
- NOT in apt, dnf, apk, or zypper repos.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora repos |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ✅ | `kubectx` | Arch community (includes kubens) |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `kubectx` | Standard formula (includes kubens) |
| `snap` | ✅ | `kubectx` | `--classic` confinement |
| `pip` | ❌ | — | Not available |
| `npm` | ❌ | — | Not available |

---

## 3. Binary Download (_default)

| Field | Value |
|-------|-------|
| Source | GitHub releases (`ahmetb/kubectx`) |
| URL pattern | `https://github.com/ahmetb/kubectx/releases/download/{tag}/kubectx_{tag}_{os}_{arch}.tar.gz` |
| Format | `.tar.gz` — separate archives for kubectx and kubens |
| Install location | `/usr/local/bin/kubectx` and `/usr/local/bin/kubens` |
| Dependencies | `curl` |
| needs_sudo | Yes |
| install_via | `github_release` |

### Architecture naming (NON-STANDARD!)

| Architecture | Asset suffix | Notes |
|-------------|-------------|-------|
| x86_64 | `linux_x86_64` | **Uses `x86_64`, NOT `amd64`!** |
| aarch64 (ARM64) | `linux_arm64` | Mapped via `arch_map` |
| armv7l (ARM 32) | `linux_armv7` | Mapped via `arch_map` |

`arch_map` only needs: `aarch64→arm64`, `armv7l→armv7`.
`x86_64` passes through natively — no mapping required.

### Version resolution
Latest version from GitHub API. Tag format: `v0.9.5` (included in filename).

### Dual binary install
The `_default` method downloads **two separate archives**:
1. `kubectx_{tag}_{os}_{arch}.tar.gz` → extracts `kubectx`
2. `kubens_{tag}_{os}_{arch}.tar.gz` → extracts `kubens`

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For binary download and version resolution |
| Runtime | None | Self-contained static binaries |
| Runtime (implied) | kubeconfig | Needs `~/.kube/config` or `KUBECONFIG` env |

---

## 5. Post-install

No PATH additions needed. Binaries installed to `/usr/local/bin/`.

---

## 6. Failure Handlers

### Layer 2b: install_via family (github_release)
| Handler | Category | Trigger |
|---------|----------|---------|
| `github_rate_limit` | environment | GitHub API rate limit exceeded |
| `github_asset_not_found` | environment | No release asset for OS/arch |
| `github_extract_failed` | environment | Archive extraction failed |

### Layer 2a: method-family handlers (shared)
| Family | Handler | Trigger |
|--------|---------|---------|
| `pacman` | `pacman_target_not_found` | Package not found |
| `pacman` | `pacman_locked` | Database locked |
| `brew` | `brew_no_formula` | Formula not found |
| `snap` | `snapd_unavailable` | snapd not running |
| `_default` | `missing_curl` | curl not installed |
| `_default` | `missing_git` | git not installed |
| `_default` | `missing_wget` | wget not installed |
| `_default` | `missing_unzip` | unzip not installed |
| `_default` | `missing_npm_default` | npm not installed |

### Layer 1: INFRA handlers (9 cross-tool)
Network, disk, permissions, OOM, timeout — all standard.

### Layer 3: per-tool on_failure handlers
None needed. Standard GitHub releases, no custom repos.

---

## 7. Recipe Structure

```python
"kubectx": {
    "cli": "kubectx",
    "label": "kubectx + kubens (K8s context/namespace switcher)",
    "category": "k8s",
    "install": {
        "pacman": ["pacman", "-S", "--noconfirm", "kubectx"],
        "brew":   ["brew", "install", "kubectx"],
        "snap":   ["snap", "install", "kubectx", "--classic"],
        "_default": ["bash", "-c", "VERSION=... && curl kubectx.tar.gz | tar ... && curl kubens.tar.gz | tar ..."],
    },
    "needs_sudo": {"pacman": True, "brew": False, "snap": True, "_default": True},
    "install_via": {"_default": "github_release"},
    "requires": {"binaries": ["curl"]},
    "arch_map": {"aarch64": "arm64", "armv7l": "armv7"},
    "prefer": ["pacman", "brew"],
    "verify": ["kubectx", "--help"],
    "update": { ... per-method update commands ... },
}
```

---

## 8. Validation Results

```
Schema:    VALID (recipe + all method-family handlers)
Coverage:  399/399 (100%) — 21 scenarios × 19 presets
Handlers:  2 pacman + 1 brew + 1 snap + 5 _default
           + 3 github_release + 9 INFRA = 21 total
```

---

## 9. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "kubectx"` |
| `data/recipes.py` | Updated label to `"kubectx + kubens (K8s context/namespace switcher)"` |
| `data/recipes.py` | Added `pacman` method (Arch community) |
| `data/recipes.py` | Added `snap` method (`--classic`) |
| `data/recipes.py` | Replaced raw binary `_default` with proper tar.gz GitHub release download |
| `data/recipes.py` | `_default` now downloads BOTH kubectx and kubens archives |
| `data/recipes.py` | Added `arch_map` (`aarch64→arm64`, `armv7l→armv7`) |
| `data/recipes.py` | Added `prefer: ["pacman", "brew"]` |
| `data/recipes.py` | Added per-method `update` commands |

---

## 10. Future Enhancements

- **`fzf` integration**: kubectx supports interactive selection via fzf.
  Could check fzf availability as optional dependency.
- **Krew plugin**: kubectx/kubens also available as kubectl plugins.
