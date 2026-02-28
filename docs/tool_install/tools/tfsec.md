# tfsec — Full Spectrum Analysis

> **Tool ID:** `tfsec`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)
> **⚠️ DEPRECATED:** tfsec has been merged into Trivy. Use `trivy` for new setups.

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | tfsec — Terraform static analysis security scanner |
| Language | Go |
| CLI binary | `tfsec` |
| Category | `security` |
| Verify command | `tfsec --version` |
| Recipe key | `tfsec` |

### Special notes
- **DEPRECATED**: Acquired by Aqua Security, merged into Trivy in 2024.
- Still receives maintenance releases (bug fixes, dependency bumps).
- No new feature development — use `trivy` for Terraform scanning.
- Single statically-linked Go binary — no runtime deps.
- NOT in apt, dnf, apk, zypper, snap.
- Available in pacman (AUR) and brew.
- GitHub releases provide BOTH raw binaries and `.tar.gz` archives.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora repos |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ✅ | `tfsec` | AUR |
| `zypper` | ❌ | — | Not available |
| `brew` | ✅ | `tfsec` | Standard formula |
| `snap` | ❌ | — | Not available |

---

## 3. Binary Download (_default)

| Field | Value |
|-------|-------|
| Source | GitHub releases (`aquasecurity/tfsec`) |
| URL pattern | `https://github.com/aquasecurity/tfsec/releases/latest/download/tfsec-{os}-{arch}` |
| Format | **Raw binary** — no archive, no extraction |
| Install location | `/usr/local/bin/tfsec` |
| Dependencies | `curl` |
| needs_sudo | Yes |
| install_via | `binary_download` |

### Architecture naming (Go-standard)

| Architecture | Asset suffix |
|-------------|-------------|
| x86_64 | `amd64` |
| aarch64 (ARM64) | `arm64` |

Platform coverage:
- **macOS (arm64)**: `tfsec-darwin-arm64` ✅
- **macOS (Intel)**: `tfsec-darwin-amd64` ✅
- **Raspbian (aarch64)**: `tfsec-linux-arm64` ✅
- **Debian/WSL (x86_64)**: `tfsec-linux-amd64` ✅

Uses `arch_map`: `x86_64→amd64`, `aarch64→arm64`.
Uses `/releases/latest/download/` redirect — no version resolution needed.

### Alternative tar.gz assets
GitHub releases also provide `tfsec_{version}_{os}_{arch}.tar.gz` archives.
Tag: `v1.28.14` (with `v`), filename without `v`.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For binary download |
| Runtime | None | Self-contained static binary |

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
None needed. Standard raw binary download + pacman + brew.

---

## 7. Recipe Structure

```python
"tfsec": {
    "cli": "tfsec",
    "label": "tfsec (Terraform security scanner — deprecated, use Trivy)",
    "category": "security",
    "install": {
        "pacman": ["pacman", "-S", "--noconfirm", "tfsec"],
        "brew":   ["brew", "install", "tfsec"],
        "_default": ["bash", "-c", "curl ... tfsec-{os}-{arch} && chmod +x && mv ..."],
    },
    "needs_sudo": {"pacman": True, "brew": False, "_default": True},
    "install_via": {"_default": "binary_download"},
    "requires": {"binaries": ["curl"]},
    "arch_map": {"x86_64": "amd64", "aarch64": "arm64"},
    "prefer": ["pacman", "brew"],
    "verify": ["tfsec", "--version"],
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
| `data/recipes.py` | Added `cli: "tfsec"` |
| `data/recipes.py` | Updated label with deprecation notice |
| `data/recipes.py` | **Fixed broken `_default`** — was nested `{"linux": [...]}` with Linux-only installer |
| `data/recipes.py` | Replaced with raw binary download using `{os}-{arch}` (works on macOS too!) |
| `data/recipes.py` | Changed `install_via` to `binary_download` (raw binary, not archive) |
| `data/recipes.py` | Added `pacman` method (Arch AUR) |
| `data/recipes.py` | Added `arch_map` (`x86_64→amd64`, `aarch64→arm64`) |
| `data/recipes.py` | Added `prefer: ["pacman", "brew"]` |
| `data/recipes.py` | Added per-method `update` commands |

---

## 10. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS (arm64)** | brew preferred | `tfsec-darwin-arm64` binary also works |
| **macOS (Intel)** | brew preferred | `tfsec-darwin-amd64` binary also works |
| **Raspbian (aarch64)** | _default | `tfsec-linux-arm64`; no pacman |
| **Debian/Ubuntu** | _default | `tfsec-linux-amd64`; brew if installed |
| **Arch** | pacman | AUR package |
| **Alpine** | _default | Static binary works on musl |
| **Fedora/SUSE** | _default | No pacman; brew if installed |

---

## 11. Future Considerations

- **Migration to Trivy**: Consider adding a deprecation warning
  at install time suggesting `trivy` as the successor.
- **Removal**: Once tfsec stops receiving any releases,
  consider removing from recipes or marking as unsupported.
