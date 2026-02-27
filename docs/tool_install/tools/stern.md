# stern — Full Spectrum Analysis

> **Tool ID:** `stern`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Stern — multi-pod Kubernetes log tailing |
| Language | Go |
| CLI binary | `stern` |
| Category | `k8s` |
| Verify command | `stern --version` |
| Recipe key | `stern` |

### Special notes
- Stern tails logs from multiple pods/containers simultaneously,
  with color-coded output and regex-based pod selection.
- Single statically-linked Go binary — no runtime deps.
- **NOT available** in any system package manager (apt, dnf, apk,
  pacman, zypper, snap). Only brew and GitHub releases.
- GitHub release asset naming: version in tag has `v` prefix (`v1.33.1`),
  in filename it does not (`stern_1.33.1_linux_amd64.tar.gz`).

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora repos |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ❌ | — | AUR only |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `stern` | Standard formula |
| `snap` | ❌ | — | Not available |
| `pip` | ❌ | — | Not available |
| `npm` | ❌ | — | Not available |
| `cargo` | ❌ | — | Not available |
| `go` | ✅ | `github.com/stern/stern` | Can `go install` but not in recipe |

---

## 3. Binary Download (_default)

| Field | Value |
|-------|-------|
| Source | GitHub releases (`stern/stern`) |
| URL pattern | `https://github.com/stern/stern/releases/download/v{version}/stern_{version}_{os}_{arch}.tar.gz` |
| Format | `.tar.gz` containing single `stern` binary |
| Install location | `/usr/local/bin/stern` |
| Dependencies | `curl` (download + version resolution) |
| needs_sudo | Yes (writes to `/usr/local/bin/`) |
| install_via | `github_release` |

### Version resolution
Latest version fetched from GitHub API:
```
curl -sSf https://api.github.com/repos/stern/stern/releases/latest
```
Tag format: `v1.33.1` → filename uses `1.33.1` (stripped).

### Architecture naming (Go-standard)

| Architecture | Archive suffix |
|-------------|---------------|
| x86_64 | `linux_amd64` |
| aarch64 (ARM64) | `linux_arm64` |
| armv7l (ARM 32) | `linux_arm` |

Uses `arch_map`: `x86_64→amd64`, `aarch64→arm64`, `armv7l→arm`.

### OS naming
- Linux: `linux` (lowercase)
- macOS: `darwin` (lowercase)

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For binary download and version resolution |
| Runtime | None | Self-contained static binary |
| Runtime (implied) | kubeconfig | Needs `~/.kube/config` or `KUBECONFIG` env |

---

## 5. Post-install

No PATH additions needed. Binary installed to `/usr/local/bin/`
via `_default` or standard brew location.

---

## 6. Failure Handlers

### Layer 2b: install_via family (github_release)
| Handler | Category | Trigger |
|---------|----------|---------|
| `github_rate_limit` | environment | GitHub API rate limit exceeded |
| `github_asset_not_found` | environment | No release asset for this OS/arch |
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
None needed. stern uses standard GitHub releases — no custom
repo setup or unique failure modes.

---

## 7. Recipe Structure

```python
"stern": {
    "cli": "stern",
    "label": "Stern (multi-pod K8s log tailing)",
    "category": "k8s",
    "install": {
        "brew":    ["brew", "install", "stern"],
        "_default": ["bash", "-c", "VERSION=... && curl .../stern_{ver}_{os}_{arch}.tar.gz | tar -xz ..."],
    },
    "needs_sudo": {"brew": False, "_default": True},
    "install_via": {"_default": "github_release"},
    "requires": {"binaries": ["curl"]},
    "arch_map": {"x86_64": "amd64", "aarch64": "arm64", "armv7l": "arm"},
    "prefer": ["brew"],
    "verify": ["stern", "--version"],
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
| `data/recipes.py` | Added `cli: "stern"` |
| `data/recipes.py` | Updated label to `"Stern (multi-pod K8s log tailing)"` |
| `data/recipes.py` | **Fixed broken `_default`** — was nested `{"linux": [...]}` dict with hardcoded `linux_amd64` |
| `data/recipes.py` | Replaced with proper GitHub release download using dynamic version + `{os}/{arch}` |
| `data/recipes.py` | Added `arch_map` (amd64, arm64, arm) |
| `data/recipes.py` | Added `prefer: ["brew"]` |
| `data/recipes.py` | Added per-method `update` commands |

---

## 10. Future Enhancements

- **`go install` method**: Could add `go install github.com/stern/stern@latest`
  for systems with Go toolchain.
- **Krew plugin**: stern is also available as a kubectl plugin via Krew.
