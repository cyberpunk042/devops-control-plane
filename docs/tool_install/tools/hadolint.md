# hadolint — Full Spectrum Analysis

> **Tool ID:** `hadolint`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Hadolint — Dockerfile linter |
| Language | Haskell |
| CLI binary | `hadolint` |
| Category | `container` |
| Verify command | `hadolint --version` |
| Recipe key | `hadolint` |

### Special notes
- Written in Haskell — one of the few Haskell tools in the system.
- Lints Dockerfiles for best practices and security issues.
- NOT in apt, dnf, apk, zypper, snap.
- pacman only via AUR (not official repos).
- Available in brew and GitHub releases.
- Original `_default` was broken: nested `{"linux": [...]}` with hardcoded values.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in repos |
| `dnf` | ❌ | — | Not in repos |
| `apk` | ❌ | — | Not in repos |
| `pacman` | ⚠️ | `hadolint-bin` | AUR only |
| `zypper` | ❌ | — | Not in repos |
| `brew` | ✅ | `hadolint` | Standard formula |
| `snap` | ❌ | — | Not available |

---

## 3. Installation (_default via GitHub raw binary)

| Field | Value |
|-------|-------|
| Method | Raw binary download |
| URL | `github.com/hadolint/hadolint/releases/latest/download/hadolint-$(uname -s)-{arch}` |
| Archive format | None — raw binary |
| needs_sudo | Yes (_default) |
| install_via | `binary_download` |

### NON-STANDARD naming conventions
```
hadolint-Linux-x86_64    — Capital 'L' in Linux!
hadolint-Linux-arm64
hadolint-Darwin-x86_64   — Capital 'D' in Darwin!
hadolint-Darwin-arm64
```

**Solution:** Uses `$(uname -s)` which natively returns `Linux`/`Darwin`
with the correct capitalization, avoiding the need for a custom `os_map`.

### Arch map
| System arch | Asset arch |
|------------|------------|
| `x86_64` | `x86_64` |
| `aarch64` | `arm64` |

### What was broken
- Nested `_default.linux` — not a flat list
- Hardcoded `Linux` and `x86_64` — no macOS/ARM64 support
- Only worked on Linux x86_64

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For _default method |

No runtime dependencies — standalone binary.

---

## 5. Failure Handlers

### Layer 2a: method-family handlers
| Family | Handler | Trigger |
|--------|---------|---------|
| `brew` | `brew_no_formula` | Formula not found |
| `_default` | `missing_curl` | curl not installed |
| `_default` | `missing_git` | git not installed |
| `_default` | `missing_wget` | wget not installed |
| `_default` | `missing_unzip` | unzip not installed |
| `_default` | `missing_npm_default` | npm not installed |

### Layer 1: INFRA handlers (9 cross-tool)
All standard.

### Layer 3: None needed.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  285/285 (100%) — 15 scenarios × 19 presets
Handlers:  1 brew + 5 _default + 9 INFRA = 15
```

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "hadolint"` |
| `data/recipes.py` | Fixed broken nested `_default.linux` → flat list |
| `data/recipes.py` | Fixed hardcoded `Linux x86_64` → `$(uname -s)-{arch}` |
| `data/recipes.py` | Changed `install_via` from `github_release` → `binary_download` |
| `data/recipes.py` | Added `arch_map`, `prefer`, `update` |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS (arm64)** | brew | Standard formula |
| **macOS (Intel)** | brew | Standard formula |
| **Raspbian (aarch64)** | _default | `hadolint-Linux-arm64` |
| **Debian/Ubuntu** | _default | Raw binary download |
| **Fedora/RHEL** | _default | Raw binary download |
| **Alpine** | _default | Raw binary download |
| **Arch** | _default | (AUR package not in official repos) |
| **openSUSE** | _default | Raw binary download |
