# kustomize — Full Spectrum Analysis

> **Tool ID:** `kustomize`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Kustomize — Kubernetes-native config customization |
| Language | Go |
| CLI binary | `kustomize` |
| Category | `k8s` |
| Verify command | `kustomize version` |
| Recipe key | `kustomize` |

### Special notes
- Kustomize is a Kubernetes-native configuration management tool.
- Allows template-free YAML customization via overlays and patches.
- **Embedded in kubectl** since v1.14 (`kubectl apply -k`), but the
  standalone binary often has newer features.
- Single statically-linked Go binary — no runtime deps.
- **NOT available** in apt, dnf, pacman, or zypper standard repos.
- Available in apk (Alpine community), brew, snap.
- **Non-standard GitHub release tags**: `kustomize/vX.Y.Z` (tool-prefixed),
  not just `vX.Y.Z`. The official install script handles this.
- OS/arch naming is lowercase: `linux_amd64`, `darwin_arm64`.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora repos |
| `apk` | ✅ | `kustomize` | Alpine community repo |
| `pacman` | ❌ | — | AUR only |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `kustomize` | Standard formula |
| `snap` | ✅ | `kustomize` | Available |
| `pip` | ❌ | — | Not available |
| `npm` | ❌ | — | Not available |
| `cargo` | ❌ | — | Not available |
| `go` | ❌ | — | Not a `go install` binary |

---

## 3. Installation (_default via installer script)

| Field | Value |
|-------|-------|
| Source | Official `install_kustomize.sh` from kubernetes-sigs |
| URL | `https://raw.githubusercontent.com/kubernetes-sigs/kustomize/master/hack/install_kustomize.sh` |
| Method | `curl -s ... \| bash && mv kustomize /usr/local/bin/` |
| Install location | `/usr/local/bin/kustomize` |
| Dependencies | `curl` |
| needs_sudo | Yes |
| install_via | `curl_pipe_bash` |

### How the installer works
The `install_kustomize.sh` script:
1. Detects OS and architecture
2. Resolves latest release from GitHub API
3. Downloads the correct `kustomize_{tag}_{os}_{arch}.tar.gz`
4. Extracts the binary to the current directory
5. Recipe then moves it to `/usr/local/bin/`

### GitHub Releases format
```
https://github.com/kubernetes-sigs/kustomize/releases/download/
  kustomize/{tag}/kustomize_{tag}_{os}_{arch}.tar.gz
```

**Tag format:** `kustomize/v5.8.1` (tool-prefixed — non-standard!)

### Architecture naming (Go-standard)

| Architecture | Archive suffix |
|-------------|---------------|
| x86_64 | `linux_amd64` |
| aarch64 (ARM64) | `linux_arm64` |

Uses `arch_map`: `x86_64→amd64`, `aarch64→arm64`.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For installer script |
| Runtime | None | Self-contained static binary |

### Reverse deps
Kustomize is used by:
- `kubectl apply -k` (embedded version)
- Argo CD (for GitOps kustomization rendering)
- Flux CD (kustomize controller)
- CI/CD pipelines for Kubernetes manifest generation

---

## 5. Post-install

No PATH additions needed. Binary installed to `/usr/local/bin/`
(via `_default`) or standard package locations.

---

## 6. Failure Handlers

### Layer 2b: install_via family (curl_pipe_bash)
| Handler | Category | Trigger |
|---------|----------|---------|
| `curl_tls_certificate` | environment | TLS certificate verification failed |
| `curl_unsupported_arch` | environment | Unsupported OS or architecture |
| `curl_script_not_found` | environment | Install script URL returned 404/HTML |

### Layer 2a: method-family handlers (shared)
| Family | Handler | Trigger |
|--------|---------|---------|
| `apk` | `apk_unsatisfiable` | Dependency conflict |
| `apk` | `apk_locked` | Database locked |
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
None needed. Kustomize uses standard repos and the official
installer — no custom repo setup like helm/trivy.

---

## 7. Recipe Structure

```python
"kustomize": {
    "cli": "kustomize",
    "label": "Kustomize (Kubernetes config customization)",
    "category": "k8s",
    "install": {
        "apk":     ["apk", "add", "kustomize"],
        "brew":    ["brew", "install", "kustomize"],
        "snap":    ["snap", "install", "kustomize"],
        "_default": ["bash", "-c", "curl install_kustomize.sh | bash && mv ..."],
    },
    "needs_sudo": {
        "apk": True, "brew": False, "snap": True, "_default": True,
    },
    "install_via": {"_default": "curl_pipe_bash"},
    "requires": {"binaries": ["curl"]},
    "arch_map": {"x86_64": "amd64", "aarch64": "arm64"},
    "prefer": ["apk", "brew"],
    "verify": ["kustomize", "version"],
    "update": { ... per-method update commands ... },
}
```

---

## 8. Validation Results

```
Schema:    VALID (recipe + all method-family handlers)
Coverage:  399/399 (100%) — 21 scenarios × 19 presets
Handlers:  2 apk + 1 brew + 1 snap
           + 5 _default + 3 curl_pipe_bash + 9 INFRA = 21 total
```

---

## 9. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "kustomize"` |
| `data/recipes.py` | Updated label to `"Kustomize (Kubernetes config customization)"` |
| `data/recipes.py` | Added `apk` method (Alpine community) |
| `data/recipes.py` | Added `snap` method |
| `data/recipes.py` | Added `arch_map` (amd64, arm64) |
| `data/recipes.py` | Added `prefer: ["apk", "brew"]` |
| `data/recipes.py` | Added per-method `update` commands |

---

## 10. Future Enhancements

- **kubectl integration**: Could detect embedded kustomize version
  via `kubectl version --client` and skip install if sufficient.
- **Version pinning**: Support installing specific kustomize versions
  for reproducible CI/CD builds.
