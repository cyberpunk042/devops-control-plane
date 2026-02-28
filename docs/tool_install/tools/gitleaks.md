# gitleaks — Full Spectrum Analysis

> **Tool ID:** `gitleaks`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Gitleaks — Git secret scanner |
| Language | Go |
| CLI binary | `gitleaks` |
| Category | `security` |
| Verify command | `gitleaks version` |
| Recipe key | `gitleaks` |

### Special notes
- Scans Git repos for hardcoded secrets (API keys, passwords, tokens).
- Used in CI/CD pipelines and pre-commit hooks.
- Single statically-linked Go binary — no runtime deps.
- NOT in apt, dnf, apk, zypper, snap.
- Available in pacman (community) and brew.
- **NON-STANDARD arch naming**: Uses `x64` (NOT `amd64`!) for x86_64.
  ARM64 uses standard `arm64`.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora repos |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ✅ | `gitleaks` | Arch community |
| `zypper` | ❌ | — | Not in standard repos (OBS exists) |
| `brew` | ✅ | `gitleaks` | Standard formula |
| `snap` | ❌ | — | Not available |

---

## 3. Binary Download (_default)

| Field | Value |
|-------|-------|
| Source | GitHub releases (`gitleaks/gitleaks`) |
| URL pattern | `https://github.com/gitleaks/gitleaks/releases/download/v{version}/gitleaks_{version}_{os}_{arch}.tar.gz` |
| Format | `.tar.gz` containing single `gitleaks` binary |
| Install location | `/usr/local/bin/gitleaks` |
| Dependencies | `curl` |
| needs_sudo | Yes |
| install_via | `github_release` |

### Architecture naming (**NON-STANDARD!**)

| Architecture | Asset suffix |
|-------------|-------------|
| x86_64 | `x64` (**NOT** `amd64`!) |
| aarch64 (ARM64) | `arm64` |

Uses `arch_map`: `x86_64→x64`, `aarch64→arm64`.

This is important for:
- **macOS** (arm64 on Apple Silicon, x64 on Intel Macs → via `darwin_arm64` / `darwin_x64`)
- **Raspbian** (aarch64 → `linux_arm64`)
- **Debian/WSL** (x86_64 → `linux_x64`)

### Version resolution
Dynamic via GitHub API. Tag: `v8.30.0` → filename: `8.30.0`.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For binary download and version resolution |
| Runtime | None | Self-contained static binary |

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
| `_default` | `missing_curl` | curl not installed |
| `_default` | `missing_git` | git not installed |
| `_default` | `missing_wget` | wget not installed |
| `_default` | `missing_unzip` | unzip not installed |
| `_default` | `missing_npm_default` | npm not installed |

### Layer 1: INFRA handlers (9 cross-tool)
Network, disk, permissions, OOM, timeout — all standard.

### Layer 3: per-tool on_failure handlers
None needed. Standard GitHub releases + pacman + brew.

---

## 7. Recipe Structure

```python
"gitleaks": {
    "cli": "gitleaks",
    "label": "Gitleaks (Git secret scanner)",
    "category": "security",
    "install": {
        "pacman": ["pacman", "-S", "--noconfirm", "gitleaks"],
        "brew":   ["brew", "install", "gitleaks"],
        "_default": ["bash", "-c", "VERSION=... && curl .../gitleaks_{ver}_{os}_{arch}.tar.gz | tar ..."],
    },
    "needs_sudo": {"pacman": True, "brew": False, "_default": True},
    "install_via": {"_default": "github_release"},
    "requires": {"binaries": ["curl"]},
    "arch_map": {"x86_64": "x64", "aarch64": "arm64"},
    "prefer": ["pacman", "brew"],
    "verify": ["gitleaks", "version"],
    "update": { ... per-method update commands ... },
}
```

---

## 8. Validation Results

```
Schema:    VALID (recipe + all method-family handlers)
Coverage:  380/380 (100%) — 20 scenarios × 19 presets
Handlers:  2 pacman + 1 brew + 5 _default + 3 github_release + 9 INFRA = 20 total
```

---

## 9. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "gitleaks"` |
| `data/recipes.py` | Updated label to `"Gitleaks (Git secret scanner)"` |
| `data/recipes.py` | **Fixed broken `_default`** — was nested `{"linux": [...]}` with hardcoded `x64` |
| `data/recipes.py` | Replaced with dynamic version + `{os}_{arch}` placeholders |
| `data/recipes.py` | Added `arch_map` with `x86_64→x64` (non-standard!) |
| `data/recipes.py` | Added `pacman` method (Arch community) |
| `data/recipes.py` | Added `prefer: ["pacman", "brew"]` |
| `data/recipes.py` | Added per-method `update` commands |

---

## 10. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS (arm64)** | brew preferred | `darwin_arm64` binary also works |
| **macOS (Intel)** | brew preferred | `darwin_x64` binary also works |
| **Raspbian (aarch64)** | _default | `linux_arm64` binary; no pacman/snap |
| **Debian/Ubuntu (x86_64)** | _default | `linux_x64` binary; brew if installed |
| **Arch** | pacman | Community repo |
| **Alpine** | _default | Static binary works on musl |
| **Fedora** | _default | No pacman; brew if installed |

---

## 11. Future Enhancements

- **Pre-commit integration**: Could offer `gitleaks protect --staged`
  setup as a git hook after install.
- **Custom config**: Could check for `.gitleaks.toml` and suggest
  creating one if missing.
