# argocd-cli — Full Spectrum Analysis

> **Tool ID:** `argocd-cli`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Argo CD CLI — GitOps continuous delivery for Kubernetes |
| Language | Go |
| CLI binary | `argocd` |
| Category | `k8s` |
| Verify command | `argocd version --client` |
| Recipe key | `argocd-cli` |

### Special notes
- Argo CD is a CNCF-graduated declarative, GitOps continuous delivery
  tool for Kubernetes.
- The CLI manages Argo CD server: apps, projects, repos, clusters.
- Single statically-linked Go binary — no runtime deps.
- **NOT available** in apt, dnf, apk, zypper, or snap.
- Available in pacman (AUR/community) and brew.
- GitHub releases publish **raw binaries** (no archive/tar.gz).
- Asset naming: `argocd-{os}-{arch}` (no file extension).

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora repos |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ✅ | `argocd` | Arch AUR/community |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `argocd` | Standard formula |
| `snap` | ❌ | — | Not available |

---

## 3. Binary Download (_default)

| Field | Value |
|-------|-------|
| Source | GitHub releases (`argoproj/argo-cd`) |
| URL pattern | `https://github.com/argoproj/argo-cd/releases/latest/download/argocd-{os}-{arch}` |
| Format | **Raw binary** — no archive, no extraction |
| Install location | `/usr/local/bin/argocd` |
| Dependencies | `curl` |
| needs_sudo | Yes |
| install_via | `binary_download` |

### Architecture naming (Go-standard)

| Architecture | Asset suffix |
|-------------|-------------|
| x86_64 | `linux-amd64` |
| aarch64 (ARM64) | `linux-arm64` |

Uses `arch_map`: `x86_64→amd64`, `aarch64→arm64`.

### Version resolution
Uses `/releases/latest/download/` redirect — no explicit version
resolution needed.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For binary download |
| Runtime | None | Self-contained static binary |
| Runtime (implied) | kubeconfig | Needs `~/.kube/config` or `KUBECONFIG` |
| Runtime (implied) | Argo CD server | CLI connects to an Argo CD server |

---

## 5. Post-install

No PATH additions needed. Binary installed to `/usr/local/bin/`.

---

## 6. Failure Handlers

### Layer 2a: method-family handlers (shared)
| Family | Handler | Trigger |
|--------|---------|---------|
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
None needed. Standard raw binary download + standard repos.

---

## 7. Recipe Structure

```python
"argocd-cli": {
    "cli": "argocd",
    "label": "Argo CD CLI (GitOps continuous delivery)",
    "category": "k8s",
    "install": {
        "pacman": ["pacman", "-S", "--noconfirm", "argocd"],
        "brew":   ["brew", "install", "argocd"],
        "_default": ["bash", "-c", "curl ... argocd-{os}-{arch} && chmod +x && mv ..."],
    },
    "needs_sudo": {"pacman": True, "brew": False, "_default": True},
    "install_via": {"_default": "binary_download"},
    "requires": {"binaries": ["curl"]},
    "arch_map": {"x86_64": "amd64", "aarch64": "arm64"},
    "prefer": ["pacman", "brew"],
    "verify": ["argocd", "version", "--client"],
    "update": { ... per-method update commands ... },
}
```

---

## 8. Validation Results

```
Schema:    VALID (recipe + all method-family handlers)
Coverage:  323/323 (100%) — 17 scenarios × 19 presets
Handlers:  2 pacman + 1 brew + 5 _default + 9 INFRA = 17 total
```

---

## 9. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Updated label to `"Argo CD CLI (GitOps continuous delivery)"` |
| `data/recipes.py` | **Fixed broken `_default`** — was nested `{"linux": [...]}` with hardcoded `linux-amd64` |
| `data/recipes.py` | Replaced with flat list using `{os}-{arch}` placeholders |
| `data/recipes.py` | Changed `install_via` from `github_release` to `binary_download` (raw binary, not archive) |
| `data/recipes.py` | Downloads to `/tmp/` first, then moves (safer) |
| `data/recipes.py` | Added `pacman` method (Arch AUR/community) |
| `data/recipes.py` | Added `arch_map` (amd64, arm64) |
| `data/recipes.py` | Added `prefer: ["pacman", "brew"]` |
| `data/recipes.py` | Added per-method `update` commands |

---

## 10. Future Enhancements

- **Server connection check**: Could verify `argocd server` connectivity
  after install with `argocd cluster list`.
- **Login helper**: Could offer `argocd login` with detected server URL.
