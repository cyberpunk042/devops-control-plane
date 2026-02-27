# helmfile — Full Spectrum Analysis

> **Tool ID:** `helmfile`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Helmfile — declarative Helm chart management |
| Language | Go |
| CLI binary | `helmfile` |
| Category | `k8s` |
| Verify command | `helmfile --version` |
| Recipe key | `helmfile` |

### Special notes
- Helmfile manages Helm releases declaratively via `helmfile.yaml`.
- Supports environments, values templating, and dependency ordering.
- Single statically-linked Go binary — no runtime deps beyond `helm`.
- **Requires `helm`** as a runtime dependency (delegates chart operations).
- NOT in apt, dnf, apk, or zypper standard repos.
- Available in pacman (community), brew, snap.
- GitHub releases: `helmfile_{version}_{os}_{arch}.tar.gz`
  with `v` in tag, without in filename.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora repos |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ✅ | `helmfile` | Arch community |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `helmfile` | Standard formula |
| `snap` | ✅ | `helmfile` | `--classic` confinement |
| `pip` | ❌ | — | Not available |
| `npm` | ❌ | — | Not available |

---

## 3. Binary Download (_default)

| Field | Value |
|-------|-------|
| Source | GitHub releases (`helmfile/helmfile`) |
| URL pattern | `https://github.com/helmfile/helmfile/releases/download/v{version}/helmfile_{version}_{os}_{arch}.tar.gz` |
| Format | `.tar.gz` containing single `helmfile` binary |
| Install location | `/usr/local/bin/helmfile` |
| Dependencies | `curl` (download + version resolution) |
| needs_sudo | Yes |
| install_via | `github_release` |

### Architecture naming (Go-standard)

| Architecture | Archive suffix |
|-------------|---------------|
| x86_64 | `linux_amd64` |
| aarch64 (ARM64) | `linux_arm64` |

Uses `arch_map`: `x86_64→amd64`, `aarch64→arm64`.

### Version resolution
Latest version from GitHub API. Tag: `v1.3.2` → filename: `1.3.2`.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For binary download and version resolution |
| Runtime | `helm` | **Required** — helmfile delegates all chart ops to helm |
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
None needed. Standard GitHub releases + standard repos.

---

## 7. Recipe Structure

```python
"helmfile": {
    "cli": "helmfile",
    "label": "Helmfile (declarative Helm chart management)",
    "category": "k8s",
    "install": {
        "pacman": ["pacman", "-S", "--noconfirm", "helmfile"],
        "brew":   ["brew", "install", "helmfile"],
        "snap":   ["snap", "install", "helmfile", "--classic"],
        "_default": ["bash", "-c", "VERSION=... && curl .../helmfile_{ver}_{os}_{arch}.tar.gz | tar ..."],
    },
    "needs_sudo": {"pacman": True, "brew": False, "snap": True, "_default": True},
    "install_via": {"_default": "github_release"},
    "requires": {"binaries": ["curl", "helm"]},
    "arch_map": {"x86_64": "amd64", "aarch64": "arm64"},
    "prefer": ["pacman", "brew"],
    "verify": ["helmfile", "--version"],
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
| `data/recipes.py` | Added `cli: "helmfile"` |
| `data/recipes.py` | Updated label to `"Helmfile (declarative Helm chart management)"` |
| `data/recipes.py` | **Fixed broken `_default`** — was nested `{"linux": [...]}` dict with hardcoded `linux_amd64` |
| `data/recipes.py` | Replaced with proper GitHub release tar.gz + dynamic version + `{os}/{arch}` |
| `data/recipes.py` | Added `pacman` method (Arch community) |
| `data/recipes.py` | Added `snap` method (`--classic`) |
| `data/recipes.py` | Added `arch_map` (amd64, arm64) |
| `data/recipes.py` | Added `prefer: ["pacman", "brew"]` |
| `data/recipes.py` | Added per-method `update` commands |

---

## 10. Future Enhancements

- **helm dep check**: Could verify helm is installed before attempting
  helmfile operations and offer to install helm first.
- **helmfile init**: Could run `helmfile init` after install to set up
  default plugins (helm-diff, helm-secrets).
