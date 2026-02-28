# az-cli — Full Spectrum Analysis

> **Tool ID:** `az-cli`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | az-cli — Microsoft Azure command-line interface |
| Language | Python |
| Author | Microsoft |
| CLI binary | `az` |
| Category | `cloud` |
| Verify command | `az --version` |
| Recipe key | `az-cli` |

### Special notes
- **Binary name mismatch**: recipe key is `az-cli` but CLI binary is `az`.
- Written in Python. Available on PyPI as `azure-cli`.
- `_default` uses `_PIP + ["install", "azure-cli"]` — the established pattern
  for Python tools (uses `sys.executable -m pip`, not bare `pip`).
- brew formula: `azure-cli`.
- Microsoft provides distro-specific repo setup scripts (InstallAzureCLIDeb for
  Debian, RPM repo for Fedora, etc.) but those are distro-locked and require
  repo + key setup — NOT used as `_default`.
- pip is the true universal fallback — works everywhere Python runs.
- NOT in snap, apk, pacman.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `azure-cli` | Needs Microsoft repo + key — not used |
| `dnf` | ✅ | `azure-cli` | Needs Microsoft repo + key — not used |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ❌ | — | AUR only |
| `zypper` | ✅ | `azure-cli` | Needs Microsoft repo + key — not used |
| `brew` | ✅ | `azure-cli` | **Preferred** |
| `snap` | ❌ | — | Not available |
| `pip` | ✅ | `azure-cli` | **Universal fallback** — `_default` |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| macOS/Linux (preferred) | `brew install azure-cli` | brew |
| Any with Python | `_PIP + ["install", "azure-cli"]` | pip (_default) |

### brew method (preferred)
```bash
brew install azure-cli
```

### _default method (pip — universal)
```python
_PIP + ["install", "azure-cli"]
# Resolves to: sys.executable -m pip install azure-cli
```
- **No sudo needed**.
- Uses `sys.executable -m pip` — the project's Python interpreter.
- `install_via: pip` — triggers pip's comprehensive 11 failure handlers.
- Works on **every platform** where Python runs (Debian, Fedora, Alpine,
  Arch, Raspbian, macOS, WSL — all covered).

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Runtime | Python 3 | For pip/_default method |

No C library dependencies. No curl required (pip handles download).

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (17 total)
| Family | Handlers |
|--------|----------|
| `brew` | 1 (no formula) |
| `_default` | 5 (missing curl/git/wget/unzip/npm) |
| `pip` | 11 (PEP 668, venv, system install, missing pip, permissions, version conflict, hash mismatch, build wheel, no matching dist, SSL, python version) |

### Layer 1: INFRA handlers (9 cross-tool)
All standard — network, disk, permissions, OOM, timeout.

### Layer 3: None needed.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  494/494 (100%) — 26 scenarios × 19 presets
Handlers:  17 method-specific + 9 INFRA = 26
```

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Moved `cli: "az"` to top |
| `data/recipes.py` | Updated label to include full description |
| `data/recipes.py` | Removed Debian-only `InstallAzureCLIDeb` script |
| `data/recipes.py` | Changed `_default` to `_PIP + ["install", "azure-cli"]` |
| `data/recipes.py` | Removed separate `pip` method — `_default` IS pip |
| `data/recipes.py` | Removed `requires: {"binaries": ["curl"]}` — pip handles download |
| `data/recipes.py` | Set `prefer: ["brew"]` |
| `data/recipes.py` | Added research comments |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | **Preferred** — formula `azure-cli` |
| **Linux with brew** | brew | Linuxbrew supported |
| **Debian/Ubuntu** | _default (pip) | Universal ✅ |
| **Fedora/RHEL** | _default (pip) | Universal ✅ |
| **Alpine** | _default (pip) | Universal ✅ |
| **Arch** | _default (pip) | Universal ✅ |
| **openSUSE** | _default (pip) | Universal ✅ |
| **Raspbian (aarch64)** | _default (pip) | Universal ✅ |
| **WSL** | _default (pip) | Universal ✅ |

brew preferred. pip via `_PIP` as universal cross-platform fallback.
No distro-locked scripts — works everywhere Python runs.
