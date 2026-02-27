# istioctl — Full Spectrum Analysis

> **Tool ID:** `istioctl`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | istioctl — Istio service mesh CLI |
| Language | Go |
| CLI binary | `istioctl` |
| Category | `k8s` |
| Verify command | `istioctl version --remote=false` |
| Recipe key | `istioctl` |

### Special notes
- Istio is a CNCF-graduated service mesh for Kubernetes.
- istioctl manages Istio installation, mesh configuration, and debugging.
- Single statically-linked Go binary — no runtime deps.
- **NOT available** in any system PM (apt, dnf, apk, pacman, zypper, snap).
- Only available via brew and GitHub releases.
- **Non-standard OS naming**: macOS uses `osx` (not `darwin`).
- **Tag has NO `v` prefix**: `1.29.0` (not `v1.29.0`).
- GitHub releases have **two asset types**:
  - `istio-{ver}-{os}-{arch}.tar.gz` — full Istio distribution
  - `istioctl-{ver}-{os}-{arch}.tar.gz` — **standalone CLI only** (used)

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora repos |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ❌ | — | AUR only |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `istioctl` | Standard formula |
| `snap` | ❌ | — | Not available |

---

## 3. Binary Download (_default)

| Field | Value |
|-------|-------|
| Source | GitHub releases (`istio/istio`) |
| URL pattern | `https://github.com/istio/istio/releases/download/{version}/istioctl-{version}-{os}-{arch}.tar.gz` |
| Format | `.tar.gz` containing single `istioctl` binary |
| Install location | `/usr/local/bin/istioctl` |
| Dependencies | `curl` |
| needs_sudo | Yes |
| install_via | `github_release` |

### Architecture naming (Go-standard)

| Architecture | Asset suffix |
|-------------|-------------|
| x86_64 | `linux-amd64` |
| aarch64 (ARM64) | `linux-arm64` |
| armv7l (ARM 32) | `linux-armv7` |

Uses `arch_map`: `x86_64→amd64`, `aarch64→arm64`, `armv7l→armv7`.

### OS naming (NON-STANDARD!)

| Platform | Asset name |
|----------|-----------|
| Linux | `linux` |
| macOS | **`osx`** (NOT `darwin`!) |

### Version resolution
Latest version from GitHub API. **No `v` prefix**: `1.29.0`.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For binary download and version resolution |
| Runtime | None | Self-contained static binary |
| Runtime (implied) | kubeconfig | Needs `~/.kube/config` or `KUBECONFIG` env |

---

## 5. Post-install

No PATH additions needed. Binary installed to `/usr/local/bin/`.

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
| `brew` | `brew_no_formula` | Formula not found |
| `_default` | `missing_curl` | curl not installed |
| `_default` | `missing_git` | git not installed |
| `_default` | `missing_wget` | wget not installed |
| `_default` | `missing_unzip` | unzip not installed |
| `_default` | `missing_npm_default` | npm not installed |

### Layer 1: INFRA handlers (9 cross-tool)
Network, disk, permissions, OOM, timeout — all standard.

### Layer 3: per-tool on_failure handlers
None needed. Standard GitHub releases + brew.

---

## 7. Recipe Structure

```python
"istioctl": {
    "cli": "istioctl",
    "label": "istioctl (Istio service mesh CLI)",
    "category": "k8s",
    "install": {
        "brew":    ["brew", "install", "istioctl"],
        "_default": ["bash", "-c", "VERSION=... && curl .../istioctl-{ver}-{os}-{arch}.tar.gz | tar ..."],
    },
    "needs_sudo": {"brew": False, "_default": True},
    "install_via": {"_default": "github_release"},
    "requires": {"binaries": ["curl"]},
    "arch_map": {"x86_64": "amd64", "aarch64": "arm64", "armv7l": "armv7"},
    "prefer": ["brew"],
    "verify": ["istioctl", "version", "--remote=false"],
    "update": { ... per-method update commands ... },
}
```

---

## 8. Validation Results

```
Schema:    VALID (recipe + all method-family handlers)
Coverage:  342/342 (100%) — 18 scenarios × 19 presets
Handlers:  1 brew + 5 _default + 3 github_release + 9 INFRA = 18 total
```

---

## 9. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "istioctl"` |
| `data/recipes.py` | Updated label to `"istioctl (Istio service mesh CLI)"` |
| `data/recipes.py` | Replaced full Istio distro download with standalone `istioctl-only` tar.gz |
| `data/recipes.py` | Added `install_via: {"_default": "github_release"}` |
| `data/recipes.py` | Added `arch_map` (amd64, arm64, armv7) |
| `data/recipes.py` | Added `prefer: ["brew"]` |
| `data/recipes.py` | Added per-method `update` commands |

---

## 10. Future Enhancements

- **macOS `{os}` placeholder**: Currently `{os}` maps `darwin→darwin`,
  but Istio uses `osx`. If cross-platform _default is needed, may
  require an `os_map` field or special handling.
- **Istio profile support**: Could offer `istioctl install --set profile=`
  options after binary install.
