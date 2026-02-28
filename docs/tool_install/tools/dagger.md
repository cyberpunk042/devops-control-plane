# dagger — Full Spectrum Analysis

> **Tool ID:** `dagger`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Dagger — programmable CI/CD engine |
| Language | Go |
| CLI binary | `dagger` |
| Category | `container` |
| Verify command | `dagger version` |
| Recipe key | `dagger` |

### Special notes
- By Dagger Inc. (founded by Docker co-founder Solomon Hykes).
- Programmable CI/CD that runs pipelines in containers.
- NOT in apt, dnf, apk, pacman, zypper, snap.
- Available in brew (custom tap: `dagger/tap/dagger`).
- Official installer script: `dl.dagger.io/dagger/install.sh`.
- Requires Docker as container runtime.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in repos |
| `dnf` | ❌ | — | Not in repos |
| `apk` | ❌ | — | Not in repos |
| `pacman` | ❌ | — | Not in repos |
| `zypper` | ❌ | — | Not in repos |
| `brew` | ✅ | `dagger/tap/dagger` | Custom tap |
| `snap` | ❌ | — | Not available |

---

## 3. Installation

### Official installer script (_default)
```bash
curl -sSfL https://dl.dagger.io/dagger/install.sh | sh
```
- Auto-detects OS and architecture — no placeholders needed.
- Installs to `/usr/local/bin/dagger` (needs sudo).
- `install_via: curl_pipe_bash`.

### Homebrew (brew)
```bash
brew install dagger/tap/dagger
```
- Custom tap, not a standard formula.

### GitHub releases
- Pattern: `dagger_v{version}_{os}_{arch}.tar.gz`
- OS: `linux`, `darwin`. Arch: `amd64`, `arm64`, `armv7`.
- Not used in recipe — official installer is preferred.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Runtime | `docker` | Container engine required |
| Download | `curl` | For installer script |

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
| `curl_pipe_bash` | `curl_tls_certificate` | TLS cert verification failed |
| `curl_pipe_bash` | `curl_unsupported_arch` | Unsupported OS/arch |
| `curl_pipe_bash` | `curl_script_not_found` | Script URL 404 or HTML |

### Layer 1: INFRA handlers (9 cross-tool)
All standard.

### Layer 3: None needed.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  342/342 (100%) — 18 scenarios × 19 presets
Handlers:  1 brew + 5 _default + 3 curl_pipe_bash + 9 INFRA = 18
```

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "dagger"` |
| `data/recipes.py` | Updated label to "programmable CI/CD engine" |
| `data/recipes.py` | Added `docker` to `requires.binaries` |
| `data/recipes.py` | Added `prefer` and `update` |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | Custom tap |
| **All Linux** | _default | Installer script auto-detects |
| **ARM64** | _default | Installer script supports arm64 |
| **ARMv7** | _default | Installer script supports armv7 |
