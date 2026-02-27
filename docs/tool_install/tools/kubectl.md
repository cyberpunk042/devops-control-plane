# kubectl — Full Spectrum Analysis

> **Tool ID:** `kubectl`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | kubectl — Kubernetes command-line tool |
| Language | Go |
| CLI binary | `kubectl` |
| Category | `k8s` |
| Verify command | `kubectl version --client` |
| Recipe key | `kubectl` |

### Special notes
- kubectl is the primary CLI for interacting with Kubernetes clusters.
- Version constraint: kubectl should be within **±1 minor version** of
  the target K8s cluster (`reference_hint: cluster_version`).
- The `_default` install method downloads a **bare binary** (no archive)
  directly from `dl.k8s.io`. No tar/unzip step needed.
- On apt/dnf/zypper, kubectl requires adding the **Kubernetes external
  repository** first. This is often not configured by default, making
  `_default` the most reliable installation path.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `snap` | ✅ | `kubectl` | `--classic` required |
| `apt` | ✅ | `kubectl` | Requires kubernetes.io apt repo |
| `dnf` | ✅ | `kubernetes-client` | Fedora packages |
| `apk` | ✅ | `kubectl` | Alpine community repo |
| `pacman` | ✅ | `kubectl` | Arch extra repo |
| `zypper` | ✅ | `kubernetes-client` | openSUSE devel:kubic repo |
| `brew` | ✅ | `kubectl` | macOS/Linux Homebrew |
| `pip` | ❌ | — | Not available |
| `npm` | ❌ | — | Not available |
| `cargo` | ❌ | — | Not available |

### Package name notes
- **dnf/zypper:** Package is `kubernetes-client`, differs from CLI binary
  `kubectl`. Recorded in `KNOWN_PACKAGES`.
- **apt:** Package name matches CLI (`kubectl`), but requires adding the
  Kubernetes apt repository and GPG key first.
- **snap:** Provides stable channel tracking, `--classic` confinement
  required for kubeconfig access.

---

## 3. Binary Download (_default)

| Field | Value |
|-------|-------|
| Source | https://dl.k8s.io/release/ |
| URL pattern | `https://dl.k8s.io/release/{stable}/bin/{os}/{arch}/kubectl` |
| Archive format | None — bare binary |
| Install location | `/usr/local/bin/kubectl` |
| Dependencies | `curl` (download) |
| needs_sudo | Yes (writes to `/usr/local/bin/`) |

### Architecture naming
kubectl uses Go-standard architecture naming:

| uname -m | kubectl name | Handled by |
|----------|-------------|------------|
| `x86_64` | `amd64` | `arch_map` |
| `aarch64` | `arm64` | `arch_map` |
| `armv7l` | `arm` | `arch_map` (Raspbian) |

**Raspbian note:** The L0 system profiler detects 64-bit kernel + 32-bit
userland via `struct.calcsize("P")` and corrects `aarch64` → `armv7l`.
The `arch_map` then maps `armv7l` → `arm` (Go's naming for 32-bit ARM).
This produces the correct URL: `.../bin/linux/arm/kubectl`.

### OS support
The `_default` command uses `{os}` and `{arch}` placeholders:
- Path component: `/bin/{os}/{arch}/kubectl`
- Linux: `/bin/linux/amd64/kubectl`
- macOS: `/bin/darwin/arm64/kubectl`

Same binary format (raw ELF/Mach-O) on both platforms, same URL
structure — `{os}` placeholder is sufficient.

### Version resolution
The `_default` command auto-detects the latest stable version by
querying `https://dl.k8s.io/release/stable.txt`. This returns a
version string like `v1.32.0`.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For `_default` install method |
| Runtime | None | Self-contained binary |

### Reverse deps
kubectl is referenced by many K8s tools:
- `helm`, `kustomize`, `skaffold`, `argocd-cli`, `k9s`, `stern`
- Often a prerequisite for K8s cluster interaction workflows

---

## 5. Post-install

No PATH additions or shell configuration needed. The binary is
installed to `/usr/local/bin/` which is in the default PATH on
all supported platforms.

---

## 6. Version Constraint

```python
"version_constraint": {
    "type": "minor_range",
    "reference_hint": "cluster_version",
    "range": 1,
    "description": "kubectl should be within ±1 minor version of the K8s cluster.",
},
```

This is a dynamic constraint — the "correct" version depends on what
K8s cluster the user is targeting. The `reference_hint` tells the
resolver to check the cluster version when validating.

---

## 7. Failure Handlers

### Layer 1: method-family handlers (shared)
| Family | Handler | Trigger |
|--------|---------|---------|
| `snap` | `snapd_unavailable` | snapd not running |
| `apt` | `apt_stale_index` | Stale package index |
| `apt` | `apt_locked` | dpkg lock held |
| `dnf` | `dnf_no_match` | Package not in repos |
| `apk` | `apk_unsatisfiable` | Dependency conflict |
| `apk` | `apk_locked` | Database locked |
| `pacman` | `pacman_target_not_found` | Package not found |
| `pacman` | `pacman_locked` | Database locked |
| `zypper` | `zypper_not_found` | Package not found |
| `zypper` | `zypper_locked` | zypper locked |
| `brew` | `brew_no_formula` | Formula not found |
| `_default` | `missing_curl` | curl not installed |
| `_default` | `missing_git` | git not installed |
| `_default` | `missing_wget` | wget not installed |
| `_default` | `missing_unzip` | unzip not installed |
| `_default` | `missing_npm_default` | npm not installed |

### Layer 2: INFRA handlers (9 cross-tool)
Network, disk, permissions, OOM, timeout — all standard.

### Layer 3: per-tool on_failure handlers

| Handler | Category | Trigger | Options |
|---------|----------|---------|---------|
| `kubectl_repo_not_configured` | configuration | `Unable to locate package kubectl` / package not found | Switch to `_default` binary (recommended), switch to `snap` |
| `kubectl_version_skew` | environment | `WARNING: version difference` / version skew | Manual: reinstall matching cluster version |
| `kubectl_exec_format_error` | environment | `exec format error` / cannot execute binary | Switch to `_default` (recommended), switch to `apt` |

---

## 8. Recipe Structure

```python
"kubectl": {
    "cli": "kubectl",
    "label": "kubectl (Kubernetes CLI)",
    "category": "k8s",
    "install": {
        "snap":   ["snap", "install", "kubectl", "--classic"],
        "apt":    ["apt-get", "install", "-y", "kubectl"],
        "dnf":    ["dnf", "install", "-y", "kubernetes-client"],
        "apk":    ["apk", "add", "kubectl"],
        "pacman": ["pacman", "-S", "--noconfirm", "kubectl"],
        "zypper": ["zypper", "install", "-y", "kubernetes-client"],
        "brew":   ["brew", "install", "kubectl"],
        "_default": [
            "bash", "-c",
            "curl -sSfL -o /tmp/kubectl "
            "\"https://dl.k8s.io/release/"
            "$(curl -sSfL https://dl.k8s.io/release/stable.txt)"
            "/bin/{os}/{arch}/kubectl\" && "
            "chmod +x /tmp/kubectl && "
            "mv /tmp/kubectl /usr/local/bin/kubectl",
        ],
    },
    "needs_sudo": {
        "snap": True, "apt": True, "dnf": True,
        "apk": True, "pacman": True, "zypper": True,
        "brew": False, "_default": True,
    },
    "install_via": {"_default": "binary_download"},
    "prefer": ["_default", "snap", "brew"],
    "requires": {"binaries": ["curl"]},
    "arch_map": {"x86_64": "amd64", "aarch64": "arm64", "armv7l": "arm"},
    "version_constraint": {...},
    "verify": ["kubectl", "version", "--client"],
    "update": { ... per-method update commands ... },
}
```

---

## 9. Validation Results

```
Schema:    VALID (recipe + all method-family handlers + on_failure)
Coverage:  532/532 (100%) — 28 scenarios × 19 presets
Handlers:  1 snap + 10 PM-family + 5 _default + 3 on_failure + 9 INFRA = 28 total
```

---

## 10. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "kubectl"` |
| `data/recipes.py` | Added `category: "k8s"` |
| `data/recipes.py` | Added `apt`, `dnf`, `apk`, `pacman`, `zypper` install methods |
| `data/recipes.py` | Upgraded `_default` from hardcoded linux/amd64 to `{os}/{arch}` |
| `data/recipes.py` | Added `arch_map` for amd64/arm64 naming |
| `data/recipes.py` | Updated `prefer` to `["_default", "snap", "brew"]` |
| `data/recipes.py` | Added `install_via: {"_default": "binary_download"}` |
| `data/recipes.py` | Updated label to `"kubectl (Kubernetes CLI)"` |
| `data/recipes.py` | Added explicit per-method `update` commands for all 8 methods |
| `resolver/dynamic_dep_resolver.py` | Added kubectl to `KNOWN_PACKAGES` (dnf=kubernetes-client, zypper=kubernetes-client) |
| `data/remediation_handlers.py` | Fixed pre-existing dnf handler `packages` schema error |
| `data/remediation_handlers.py` | Added `configuration` to `VALID_CATEGORIES` |
| `data/tool_failure_handlers.py` | Added `kubectl_repo_not_configured` handler (2 options) |
| `data/tool_failure_handlers.py` | Added `kubectl_version_skew` handler (1 option) |
| `data/tool_failure_handlers.py` | Added `kubectl_exec_format_error` handler (2 options) |
