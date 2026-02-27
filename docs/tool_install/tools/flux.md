# flux — Full Spectrum Analysis

> **Tool ID:** `flux`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Flux CD CLI — GitOps toolkit for Kubernetes |
| Language | Go |
| CLI binary | `flux` |
| Category | `k8s` |
| Verify command | `flux --version` |
| Recipe key | `flux` |

### Special notes
- Flux is the CNCF-graduated GitOps toolkit for Kubernetes.
- Reconciles cluster state from Git (kustomizations, Helm releases).
- Single statically-linked Go binary — no runtime deps.
- **NOT available** in any system PM standard repos (apt, dnf, apk,
  pacman, zypper, snap).
- **brew uses a custom tap**: `fluxcd/tap/flux` (not standard formula).
- Official installer at `https://fluxcd.io/install.sh` handles OS/arch
  detection, download, verification, and install to `/usr/local/bin/`.
- GitHub repo is `fluxcd/flux2` (not `fluxcd/flux`).

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora repos |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ❌ | — | AUR only (`flux-bin`) |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `fluxcd/tap/flux` | Custom tap |
| `snap` | ❌ | — | Not available |
| `pip` | ❌ | — | Not available |
| `npm` | ❌ | — | Not available |

---

## 3. Installation (_default via installer script)

| Field | Value |
|-------|-------|
| Source | Official `install.sh` from fluxcd.io |
| URL | `https://fluxcd.io/install.sh` |
| Method | `curl -s https://fluxcd.io/install.sh \| bash` |
| Install location | `/usr/local/bin/flux` |
| Dependencies | `curl` |
| needs_sudo | Yes |
| install_via | `curl_pipe_bash` |

### How the installer works
The official installer:
1. Detects OS and architecture
2. Resolves latest release from GitHub API (fluxcd/flux2)
3. Downloads the correct `flux_{version}_{os}_{arch}.tar.gz`
4. Verifies checksums
5. Installs binary to `/usr/local/bin/`

### GitHub Releases format
```
https://github.com/fluxcd/flux2/releases/download/v{version}/flux_{version}_{os}_{arch}.tar.gz
```
- Version: `v2.8.1` in tag, `2.8.1` in filename
- OS: `linux`, `darwin`
- Arch: `amd64`, `arm64`, `arm`

### Architecture naming (Go-standard)

| Architecture | Archive suffix |
|-------------|---------------|
| x86_64 | `linux_amd64` |
| aarch64 (ARM64) | `linux_arm64` |
| armv7l (ARM 32) | `linux_arm` |

Uses `arch_map`: `x86_64→amd64`, `aarch64→arm64`, `armv7l→arm`.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For installer script |
| Runtime | None | Self-contained static binary |
| Runtime (implied) | kubeconfig | Needs `~/.kube/config` or `KUBECONFIG` env |

---

## 5. Post-install

No PATH additions needed. Binary installed to `/usr/local/bin/`.

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
| `brew` | `brew_no_formula` | Formula/tap not found |
| `_default` | `missing_curl` | curl not installed |
| `_default` | `missing_git` | git not installed |
| `_default` | `missing_wget` | wget not installed |
| `_default` | `missing_unzip` | unzip not installed |
| `_default` | `missing_npm_default` | npm not installed |

### Layer 1: INFRA handlers (9 cross-tool)
Network, disk, permissions, OOM, timeout — all standard.

### Layer 3: per-tool on_failure handlers
None needed. Official installer script and brew tap — no custom repo setup.

---

## 7. Recipe Structure

```python
"flux": {
    "cli": "flux",
    "label": "Flux CD CLI (GitOps for Kubernetes)",
    "category": "k8s",
    "install": {
        "brew":    ["brew", "install", "fluxcd/tap/flux"],
        "_default": ["bash", "-c", "curl -s https://fluxcd.io/install.sh | bash"],
    },
    "needs_sudo": {"brew": False, "_default": True},
    "install_via": {"_default": "curl_pipe_bash"},
    "requires": {"binaries": ["curl"]},
    "arch_map": {"x86_64": "amd64", "aarch64": "arm64", "armv7l": "arm"},
    "prefer": ["brew"],
    "verify": ["flux", "--version"],
    "update": { ... per-method update commands ... },
}
```

---

## 8. Validation Results

```
Schema:    VALID (recipe + all method-family handlers)
Coverage:  342/342 (100%) — 18 scenarios × 19 presets
Handlers:  1 brew + 5 _default + 3 curl_pipe_bash + 9 INFRA = 18 total
```

---

## 9. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "flux"` |
| `data/recipes.py` | Updated label to `"Flux CD CLI (GitOps for Kubernetes)"` |
| `data/recipes.py` | Removed `sudo` from installer (script handles it) |
| `data/recipes.py` | Added `arch_map` (amd64, arm64, arm) |
| `data/recipes.py` | Added `prefer: ["brew"]` |
| `data/recipes.py` | Added per-method `update` commands |

---

## 10. Future Enhancements

- **Bootstrap validation**: Could verify flux bootstrap completed
  successfully by checking `flux check` output.
- **Git provider detection**: flux bootstrap supports GitHub, GitLab,
  Bitbucket — could auto-detect provider from config.
