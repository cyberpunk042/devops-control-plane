# k9s — Full Spectrum Analysis

> **Tool ID:** `k9s`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | K9s — Kubernetes TUI (terminal user interface) |
| Language | Go |
| CLI binary | `k9s` |
| Category | `k8s` |
| Verify command | `k9s version` |
| Recipe key | `k9s` |

### Special notes
- k9s provides a full terminal UI for interacting with Kubernetes clusters.
- Navigates pods, deployments, services, logs, shell access — all from TUI.
- Single statically-linked Go binary — no runtime deps.
- **NOT available** in apt (Debian/Ubuntu) or zypper (openSUSE) standard repos.
- Available in dnf (Fedora 42+), apk (Alpine community), pacman (Arch community).
- **snap requires `--devmode`** — strict confinement breaks kubeconfig access.
- Previously used `webinstall.dev` third-party installer — replaced with
  official GitHub releases direct download for reliability.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos (only .deb from releases) |
| `dnf` | ✅ | `k9s` | Fedora 42+, some older via COPR |
| `apk` | ✅ | `k9s` | Alpine community repo |
| `pacman` | ✅ | `k9s` | Arch community repo |
| `zypper` | ❌ | — | Only via third-party repo (home:tlusk) |
| `brew` | ✅ | `k9s` | Standard formula |
| `snap` | ✅ | `k9s` | Requires `--devmode` confinement |
| `pip` | ❌ | — | Not available |
| `npm` | ❌ | — | Not available |
| `cargo` | ❌ | — | Not available |
| `go` | ❌ | — | Not a `go install` binary |

---

## 3. Binary Download (_default)

| Field | Value |
|-------|-------|
| Source | https://github.com/derailed/k9s/releases |
| URL pattern | `https://github.com/derailed/k9s/releases/download/{tag}/k9s_{OS}_{arch}.tar.gz` |
| Format | `.tar.gz` archive containing `k9s` binary |
| Install location | `/usr/local/bin/k9s` |
| Dependencies | `curl` |
| needs_sudo | Yes (writes to `/usr/local/bin/`) |

### Version resolution
Latest version resolved via GitHub API:
```
curl -sSf https://api.github.com/repos/derailed/k9s/releases/latest
```
Extracts `tag_name` which uses `v`-prefix (e.g. `v0.50.18`).

### Architecture support

| Architecture | Archive suffix |
|-------------|---------------|
| x86_64 | `k9s_Linux_amd64.tar.gz` |
| aarch64 (ARM64) | `k9s_Linux_arm64.tar.gz` |
| armv7l (ARM 32) | `k9s_Linux_armv7.tar.gz` |

Uses `arch_map`: `x86_64→amd64`, `aarch64→arm64`, `armv7l→armv7`.

### OS naming
- Linux: `k9s_Linux_{arch}` (capital L)
- macOS: `k9s_Darwin_{arch}` (capital D, "Darwin")

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For version discovery + binary download |
| Runtime | None | Self-contained static binary |
| Runtime (implied) | `kubectl` / kubeconfig | Needs a valid kubeconfig to connect |

### Reverse deps
k9s is a terminal tool — nothing depends on it.

---

## 5. Post-install

No PATH additions or shell configuration needed. The binary is
installed to `/usr/local/bin/` (via `_default`) or standard package
locations (via PM installs).

Requires a valid `~/.kube/config` or `KUBECONFIG` env var to function.

---

## 6. Failure Handlers

### Layer 2b: install_via family (github_release)
| Handler | Category | Trigger |
|---------|----------|---------|
| `github_rate_limit` | environment | API rate limit exceeded |
| `github_asset_not_found` | environment | No binary for OS/arch |
| `github_extract_failed` | environment | Download/extraction failure |

### Layer 2a: method-family handlers (shared)
| Family | Handler | Trigger |
|--------|---------|---------|
| `dnf` | `dnf_no_match` | Package not in repos |
| `apk` | `apk_unsatisfiable` | Dependency conflict |
| `apk` | `apk_locked` | Database locked |
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
None needed. k9s is a simple tool available in several standard repos.
No custom repo setup required (unlike gh/helm/trivy).

---

## 7. Recipe Structure

```python
"k9s": {
    "cli": "k9s",
    "label": "K9s (Kubernetes TUI)",
    "category": "k8s",
    "install": {
        "dnf":     ["dnf", "install", "-y", "k9s"],
        "apk":     ["apk", "add", "k9s"],
        "pacman":  ["pacman", "-S", "--noconfirm", "k9s"],
        "brew":    ["brew", "install", "k9s"],
        "snap":    ["snap", "install", "k9s", "--devmode"],
        "_default": ["bash", "-c", "... GitHub release download ..."],
    },
    "needs_sudo": {
        "dnf": True, "apk": True, "pacman": True,
        "brew": False, "snap": True, "_default": True,
    },
    "install_via": {"_default": "github_release"},
    "requires": {"binaries": ["curl"]},
    "arch_map": {"x86_64": "amd64", "aarch64": "arm64", "armv7l": "armv7"},
    "prefer": ["dnf", "apk", "pacman", "brew"],
    "verify": ["k9s", "version"],
    "update": { ... per-method update commands ... },
}
```

---

## 8. Validation Results

```
Schema:    VALID (recipe + all method-family handlers)
Coverage:  456/456 (100%) — 24 scenarios × 19 presets
Handlers:  1 dnf + 2 apk + 2 pacman + 1 brew + 1 snap
           + 5 _default + 3 github_release + 9 INFRA = 24 total
```

---

## 9. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "k9s"` |
| `data/recipes.py` | Updated label to `"K9s (Kubernetes TUI)"` |
| `data/recipes.py` | Replaced webinstall.dev `_default` with GitHub releases download |
| `data/recipes.py` | Changed `install_via` from `curl_pipe_bash` to `github_release` |
| `data/recipes.py` | Added `dnf` method (Fedora standard repos) |
| `data/recipes.py` | Added `apk` method (Alpine community) |
| `data/recipes.py` | Added `pacman` method (Arch community) |
| `data/recipes.py` | Added `arch_map` for amd64/arm64/armv7 naming |
| `data/recipes.py` | Updated `prefer` to prioritize system PMs |
| `data/recipes.py` | Added per-method `update` commands |
| `data/recipes.py` | Changed `needs_sudo._default` from False to True (GitHub releases) |

---

## 10. Future Enhancements

- **apt via .deb download**: k9s publishes `.deb` packages in releases.
  Could add a `_default_deb` method that downloads and installs via `dpkg`.
- **Skin/plugin support**: k9s has `~/.config/k9s/` config directory
  for skins and plugins — not relevant to install recipe.
