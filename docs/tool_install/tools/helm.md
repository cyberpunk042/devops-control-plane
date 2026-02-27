# helm — Full Spectrum Analysis

> **Tool ID:** `helm`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Helm — Kubernetes package manager |
| Language | Go |
| CLI binary | `helm` |
| Category | `k8s` |
| Verify command | `helm version` |
| Recipe key | `helm` |

### Special notes
- Helm is the **de-facto standard** for packaging and deploying
  Kubernetes applications via charts.
- Single statically-linked Go binary — no runtime deps.
- The official installer is the `get-helm-3` curl\|bash script, which
  auto-detects OS/arch and downloads the right binary.
- **apt** requires adding the Buildkite-hosted GPG key + Debian repo
  (moved from Balto to Buildkite hosting).
- **dnf** — available in standard Fedora repos since Fedora 35.
  No repo setup needed.
- **snap** requires `--classic` confinement.
- **NOT available** in pacman (Arch) or zypper (openSUSE) official repos.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `helm` | Requires Buildkite GPG key + repo setup |
| `dnf` | ✅ | `helm` | Standard Fedora repos (since F35) |
| `apk` | ✅ | `helm` | Alpine community repo |
| `pacman` | ❌ | — | AUR only, not in official repos |
| `zypper` | ❌ | — | Not in official openSUSE repos |
| `brew` | ✅ | `helm` | Standard formula |
| `snap` | ✅ | `helm` | Requires `--classic` confinement |
| `pip` | ❌ | — | Not available |
| `npm` | ❌ | — | Not available |
| `cargo` | ❌ | — | Not available |
| `go` | ❌ | — | Not a `go install` binary |

### Package name notes
- Package name is `helm` on every available PM.
- apt install is a multi-step process (GPG key + repo + install) —
  implemented as a single `bash -c` command.

---

## 3. Binary Download (_default)

| Field | Value |
|-------|-------|
| Source | Official `get-helm-3` installer script |
| URL | `https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3` |
| Method | `curl -fsSL ... \| bash` |
| Install location | `/usr/local/bin/helm` |
| Dependencies | `curl` |
| needs_sudo | Yes |

### How the installer works
The `get-helm-3` script:
1. Detects OS and architecture
2. Downloads the latest Helm release from GitHub
3. Extracts the binary from the `.tar.gz` archive
4. Installs to `/usr/local/bin/helm`

### GitHub Releases format (used internally by the installer)
```
https://github.com/helm/helm/releases/download/v{version}/helm-v{version}-{os}-{arch}.tar.gz
```
- Archive contains: `{os}-{arch}/helm` binary
- OS: `linux`, `darwin`, `windows`
- Arch: `amd64`, `arm64`, `arm`, `386`

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For installer script download |
| Runtime | None | Self-contained static binary |

### Reverse deps
Helm is depended on by:
- Kubernetes deployments using Helm charts
- `helmfile` — declarative Helm chart management
- CI/CD pipelines deploying to Kubernetes
- ArgoCD Helm-based applications

---

## 5. Post-install

No PATH additions or shell configuration needed. The binary is
installed to `/usr/local/bin/` (via `_default` and `apt` repo) or
standard package locations (via PM installs).

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
| `apt` | `apt_stale_index` | Stale package index |
| `apt` | `apt_locked` | dpkg lock held |
| `dnf` | `dnf_no_match` | Package not in repos |
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

| Handler | Category | Trigger | Options |
|---------|----------|---------|---------|
| `helm_gpg_repo_setup_failed` | configuration | Buildkite GPG key import fails, keyring permission denied, packages.buildkite.com unreachable | Switch to `_default` installer (recommended), switch to `brew` |
| `helm_repo_not_configured` | configuration | `Unable to locate package helm` / no installation candidate | Switch to `_default` installer (recommended), switch to `snap` |

---

## 7. Recipe Structure

```python
"helm": {
    "cli": "helm",
    "label": "Helm (Kubernetes package manager)",
    "category": "k8s",
    "install": {
        "apt": ["bash", "-c", "apt-get install gpg && setup repo && apt install helm"],
        "dnf": ["dnf", "install", "-y", "helm"],
        "apk": ["apk", "add", "helm"],
        "brew": ["brew", "install", "helm"],
        "snap": ["snap", "install", "helm", "--classic"],
        "_default": ["bash", "-c", "curl get-helm-3 | bash"],
    },
    "needs_sudo": {
        "apt": True, "dnf": True, "apk": True,
        "brew": False, "snap": True, "_default": True,
    },
    "install_via": {"_default": "curl_pipe_bash"},
    "requires": {"binaries": ["curl"]},
    "prefer": ["apt", "dnf", "apk", "brew"],
    "verify": ["helm", "version"],
    "update": { ... per-method update commands ... },
}
```

---

## 8. Validation Results

```
Schema:    VALID (recipe + all method-family + on_failure handlers)
Coverage:  494/494 (100%) — 26 scenarios × 19 presets
Handlers:  2 apt + 1 dnf + 2 apk + 1 brew + 1 snap
           + 5 _default + 3 curl_pipe_bash + 2 on_failure
           + 9 INFRA = 26 total
```

---

## 9. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "helm"` |
| `data/recipes.py` | Added `category: "k8s"` |
| `data/recipes.py` | Updated label to `"Helm (Kubernetes package manager)"` |
| `data/recipes.py` | Added `apt` method (Buildkite GPG key + repo + install) |
| `data/recipes.py` | Added `dnf` method (standard Fedora repos) |
| `data/recipes.py` | Added `apk` method (Alpine community) |
| `data/recipes.py` | Added `snap` method (`--classic` confinement) |
| `data/recipes.py` | Added `prefer` list (apt, dnf, apk, brew) |
| `data/recipes.py` | Added per-method `update` commands for all methods |
| `data/tool_failure_handlers.py` | Added `helm_gpg_repo_setup_failed` handler (2 options) |
| `data/tool_failure_handlers.py` | Added `helm_repo_not_configured` handler (2 options) |

---

## 10. Future Enhancements

- **Helm plugin support**: `helm plugin install` guidance for common
  plugins (diff, secrets, push).
- **Chart repository setup**: Post-install guidance for `helm repo add`.
