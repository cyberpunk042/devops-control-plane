# jq — Full Spectrum Analysis

> **Tool ID:** `jq`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | jq — command-line JSON processor |
| Language | C |
| CLI binary | `jq` |
| Category | `utility` |
| Verify command | `jq --version` |
| Recipe key | `jq` |

### Special notes
- jq is the de-facto standard for JSON processing on the command line.
- Written in C, compiled to a **single static binary** — no runtime deps.
- Available in **every major system package manager** with the same name `jq`.
- GitHub releases publish **raw binaries** (not archives) — just download
  and `chmod +x`. No tar/unzip needed.
- Used by virtually every DevOps script, CI/CD pipeline, and shell workflow
  that handles JSON.
- snap package exists but is unmaintained and has strict confinement issues
  that break file access — not included in recipe.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `jq` | Standard repos |
| `dnf` | ✅ | `jq` | Standard repos |
| `apk` | ✅ | `jq` | Standard repos |
| `pacman` | ✅ | `jq` | Standard repos |
| `zypper` | ✅ | `jq` | Standard repos |
| `brew` | ✅ | `jq` | Standard formula |
| `snap` | ⚠️ | `jq` | Unmaintained, strict confinement issues |
| `pip` | ❌ | — | Not available |
| `npm` | ❌ | — | Not available |
| `cargo` | ❌ | — | Not available |
| `go` | ❌ | — | Not available |

### Package name notes
- Package name is `jq` on **every** package manager — no mapping needed.
- This is a "simple system package" — same name everywhere.

---

## 3. Binary Download (_default)

| Field | Value |
|-------|-------|
| Source | https://github.com/jqlang/jq/releases |
| URL pattern | `https://github.com/jqlang/jq/releases/download/{tag}/jq-{os}-{arch}` |
| Format | **Raw binary** — no archive, no extraction |
| Install location | `/usr/local/bin/jq` |
| Dependencies | `curl` (download + version discovery) |
| needs_sudo | Yes (writes to `/usr/local/bin/`) |

### Version resolution
Latest version resolved via GitHub API:
```
curl -sSf https://api.github.com/repos/jqlang/jq/releases/latest
```
Extracts `tag_name` which is `jq-VERSION` format (e.g. `jq-1.8.1`).
**Note:** tag is NOT `v`-prefixed — it uses `jq-` prefix.

### Architecture support

| Architecture | Binary name |
|-------------|------------|
| x86_64 | `jq-linux-amd64` |
| aarch64 (ARM64) | `jq-linux-arm64` |
| armv7l (ARM 32) | `jq-linux-armhf` |

Uses `arch_map`: `x86_64→amd64`, `aarch64→arm64`, `armv7l→armhf`.

### OS support
- Linux: `jq-linux-{arch}`
- macOS: `jq-macos-{arch}` (note: `macos`, not `darwin`)

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For `_default` install and version discovery |
| Runtime | None | Self-contained static binary |

### Reverse deps
jq is one of the most depended-upon CLI tools:
- Nearly every shell script that processes JSON
- CI/CD pipelines (GitHub Actions, GitLab CI, Jenkins)
- Kubernetes tooling (`kubectl get -o json | jq`)
- HashiCorp tools (Vault, Consul API responses)
- AWS/GCP/Azure CLI output parsing

---

## 5. Post-install

No PATH additions or shell configuration needed. The binary is
installed to `/usr/local/bin/` (via `_default`) or standard package
locations (via PM installs).

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

### Layer 1: INFRA handlers (9 cross-tool)
Network, disk, permissions, OOM, timeout — all standard.

### Layer 3: per-tool on_failure handlers
None needed. jq is a simple system package available everywhere.
No tool-specific failures that aren't covered by existing layers.

---

## 7. Recipe Structure

```python
"jq": {
    "cli": "jq",
    "label": "jq (command-line JSON processor)",
    "category": "utility",
    "install": {
        "apt":     ["apt-get", "install", "-y", "jq"],
        "dnf":     ["dnf", "install", "-y", "jq"],
        "apk":     ["apk", "add", "jq"],
        "pacman":  ["pacman", "-S", "--noconfirm", "jq"],
        "zypper":  ["zypper", "install", "-y", "jq"],
        "brew":    ["brew", "install", "jq"],
        "_default": [
            "bash", "-c",
            "JQ_VERSION=$(curl GitHub API) && "
            "curl -sSfL -o /usr/local/bin/jq jq-{os}-{arch} && "
            "chmod +x /usr/local/bin/jq",
        ],
    },
    "needs_sudo": {
        "apt": True, "dnf": True, "apk": True,
        "pacman": True, "zypper": True, "brew": False,
        "_default": True,
    },
    "install_via": {"_default": "github_release"},
    "requires": {"binaries": ["curl"]},
    "arch_map": {"x86_64": "amd64", "aarch64": "arm64", "armv7l": "armhf"},
    "verify": ["jq", "--version"],
    "update": { ... per-method update commands + _default ... },
}
```

---

## 8. Validation Results

```
Schema:    VALID (recipe + all method-family handlers)
Coverage:  513/513 (100%) — 27 scenarios × 19 presets
Handlers:  2 apt + 1 dnf + 2 apk + 2 pacman + 2 zypper + 1 brew
           + 5 _default + 3 github_release + 9 INFRA = 27 total
```

---

## 9. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "jq"` |
| `data/recipes.py` | Added `category: "utility"` |
| `data/recipes.py` | Updated label to `"jq (command-line JSON processor)"` |
| `data/recipes.py` | Added `_default` raw binary download from GitHub releases |
| `data/recipes.py` | Added `install_via: {"_default": "github_release"}` |
| `data/recipes.py` | Added `requires: {"binaries": ["curl"]}` |
| `data/recipes.py` | Added `arch_map` for amd64/arm64/armhf naming |
| `data/recipes.py` | Added `needs_sudo: {"_default": True}` |
| `data/recipes.py` | Added `_default` update command |

---

## 10. Future Enhancements

- **OS mapping**: jq uses `macos` not `darwin` — may need an `os_map`
  if the control plane resolves `darwin` from `platform.system()`.
- **Checksum verification**: GitHub releases include `sha256sum.txt` —
  could verify binary integrity after download.
