# direnv — Full Spectrum Analysis

> **Tool ID:** `direnv`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | direnv — environment switcher for the shell |
| Language | Go |
| CLI binary | `direnv` |
| Category | `devtools` |
| Verify command | `direnv version` (no `--`) |
| Recipe key | `direnv` |

### Special notes
- Auto-loads/unloads environment variables when entering/leaving directories.
- Uses `.envrc` files for per-directory configuration.
- Available in ALL native PMs + snap + official installer.
- Widest method coverage in devtools stack.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `direnv` | Debian/Ubuntu |
| `dnf` | ✅ | `direnv` | Fedora/RHEL |
| `apk` | ✅ | `direnv` | Alpine community |
| `pacman` | ✅ | `direnv` | Arch extra |
| `zypper` | ✅ | `direnv` | openSUSE |
| `brew` | ✅ | `direnv` | Standard formula |
| `snap` | ✅ | `direnv` | Snapcraft |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Debian/Ubuntu | `apt-get install -y direnv` | apt |
| Fedora/RHEL | `dnf install -y direnv` | dnf |
| Alpine | `apk add direnv` | apk |
| Arch | `pacman -S --noconfirm direnv` | pacman |
| openSUSE | `zypper install -y direnv` | zypper |
| macOS | `brew install direnv` | brew |
| Snap-enabled | `snap install direnv` | snap |
| Fallback | `curl -sfL https://direnv.net/install.sh \| bash` | _default |

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For _default method |

No runtime dependencies — standalone binary.

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (19 total)
| Family | Handlers |
|--------|----------|
| `apt` | 2 (stale index, locked) |
| `dnf` | 1 (no match) |
| `apk` | 2 (unsatisfiable, locked) |
| `pacman` | 2 (not found, locked) |
| `zypper` | 2 (not found, locked) |
| `brew` | 1 (no formula) |
| `snap` | 1 (snapd unavailable) |
| `_default` | 5 (missing curl/git/wget/unzip/npm) |
| `curl_pipe_bash` | 3 (TLS, unsupported arch, script 404) |

### Layer 1: INFRA handlers (9 cross-tool)
All standard.

### Layer 3: None needed.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  532/532 (100%) — 28 scenarios × 19 presets
Handlers:  19 method-specific + 9 INFRA = 28
```

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "direnv"` |
| `data/recipes.py` | Updated label to include description |
| `data/recipes.py` | Added `zypper` and `snap` methods |
| `data/recipes.py` | Added `curl` to `requires.binaries` |
| `data/recipes.py` | Added `prefer` and `update` for all 8 methods |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | Standard formula |
| **Raspbian (aarch64)** | apt | Standard repos |
| **Debian/Ubuntu** | apt | Standard repos |
| **Fedora/RHEL** | dnf | Standard repos |
| **Alpine** | apk | Community |
| **Arch** | pacman | Extra |
| **openSUSE** | zypper | Standard repos |
| **Any with snap** | snap | Universal fallback |
