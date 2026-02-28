# dive — Full Spectrum Analysis

> **Tool ID:** `dive`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Dive — Docker image layer explorer |
| Language | Go |
| CLI binary | `dive` |
| Category | `container` |
| Verify command | `dive --version` |
| Recipe key | `dive` |

### Special notes
- By wagoodman. Analyzes Docker image layers for efficiency.
- Shows wasted space and potential image size optimizations.
- NOT in apt, dnf, apk, zypper.
- Available in pacman (Arch extra), brew, snap, GitHub releases.
- snap may interfere with Docker rootdir on some systems.
- Original `_default` was broken: nested `{"linux": [...]}` with hardcoded `amd64`.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Only `.deb` from GitHub |
| `dnf` | ❌ | — | Only `.rpm` from GitHub |
| `pacman` | ✅ | `dive` | Arch extra |
| `brew` | ✅ | `dive` | Standard formula |
| `snap` | ✅ | `dive` | May conflict with Docker |
| `apk` | ❌ | — | Not available |
| `zypper` | ❌ | — | Not available |

---

## 3. Installation (_default via GitHub release)

| Field | Value |
|-------|-------|
| Method | `.tar.gz` download + extract |
| URL pattern | `github.com/wagoodman/dive/releases/download/v{ver}/dive_{ver}_{os}_{arch}.tar.gz` |
| Arch naming | `amd64`, `arm64` (Go-standard) |
| OS naming | `linux`, `darwin` |
| Archive format | `.tar.gz` (also `.deb`, `.rpm`) |
| Tag prefix | `v` (but not in filename) |
| needs_sudo | Yes (_default) |
| install_via | `github_release` |

### What was broken
- Nested `_default.linux` — not a flat list
- Hardcoded `amd64` — no ARM64 support
- No `{os}` or `{arch}` placeholders

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For _default method |
| Runtime | Docker/Podman | To inspect images (optional — can analyze saved tarballs) |

---

## 5. Failure Handlers

### Layer 2a: method-family handlers
| Family | Handler | Trigger |
|--------|---------|---------|
| `pacman` | `pacman_target_not_found` | Not found |
| `pacman` | `pacman_locked` | DB locked |
| `brew` | `brew_no_formula` | Formula not found |
| `snap` | `snapd_unavailable` | snapd not running |
| `_default` | `missing_curl` | curl not installed |
| `_default` | `missing_git` | git not installed |
| `_default` | `missing_wget` | wget not installed |
| `_default` | `missing_unzip` | unzip not installed |
| `_default` | `missing_npm_default` | npm not installed |
| `github_release` | `github_rate_limit` | API rate limited |
| `github_release` | `github_asset_not_found` | No asset for platform |
| `github_release` | `github_extract_failed` | Archive extraction failed |

### Layer 1: INFRA handlers (9 cross-tool)
All standard.

### Layer 3: None needed.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  399/399 (100%) — 21 scenarios × 19 presets
Handlers:  2 pacman + 1 brew + 1 snap + 5 _default + 3 github_release + 9 INFRA = 21
```

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "dive"` |
| `data/recipes.py` | Fixed broken nested `_default.linux` → flat list |
| `data/recipes.py` | Fixed hardcoded `amd64` → `{os}_{arch}` with `arch_map` |
| `data/recipes.py` | Added `pacman` and `snap` methods |
| `data/recipes.py` | Added `arch_map`, `prefer`, `update` |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | Standard formula |
| **Raspbian (aarch64)** | _default | `.tar.gz` with `arm64` |
| **Debian/Ubuntu** | _default or snap | No apt package |
| **Fedora/RHEL** | _default | No dnf package |
| **Alpine** | _default | No apk package |
| **Arch** | pacman | `dive` in extra |
| **openSUSE** | _default | No zypper package |
