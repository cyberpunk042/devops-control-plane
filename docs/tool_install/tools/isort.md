# isort — Full Spectrum Analysis

> **Tool ID:** `isort`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | isort — Python import sorter |
| Language | Python |
| Author | Timothy Crosley |
| CLI binary | `isort` |
| Category | `python` |
| Verify command | `isort --version` |
| Recipe key | `isort` |

### Special notes
- Automatically sorts Python imports according to PEP 8 and configurable profiles.
- Supports Black-compatible profiles (`--profile black`).
- Integrates with pre-commit, editor plugins, and CI pipelines.
- Written in Python — pure Python package, no C extensions.
- Available in pacman as `python-isort` (Arch naming convention).
- Available in brew as `isort`.
- NOT in apt, dnf, apk, zypper, snap.
- `pipx` is the recommended install method for isolated CLI tools.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora repos |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ✅ | `python-isort` | Arch community (note: `python-` prefix) |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `isort` | macOS/Linux |
| `pipx` | ✅ | `isort` | **Recommended** — isolated env |
| `pip` | ✅ | `isort` | PyPI |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Any (recommended) | `pipx install isort` | pipx |
| Arch Linux | `pacman -S --noconfirm python-isort` | pacman |
| macOS/Linux | `brew install isort` | brew |
| Fallback | `python3 -m pip install isort` | _default (pip) |

### pipx method (recommended)
```bash
pipx install isort
```
- **No sudo needed** — installs in isolated virtualenv.
- Recommended for CLI tools to avoid polluting system Python.

### _default method (pip)
```bash
python3 -m pip install isort
```
- `install_via: pip` — triggers pip's comprehensive 11 failure handlers.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Runtime | `python3` | Python 3.8+ required |
| Recommended | `pipx` | For isolated installation |

No C library dependencies — pure Python package.

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (21 total)
| Family | Handlers |
|--------|----------|
| `pipx` | 2 (venv missing, pipx not installed) |
| `pacman` | 2 (not found, locked) |
| `brew` | 1 (no formula) |
| `_default` | 5 (missing curl/git/wget/unzip/npm) |
| `pip` | 11 (PEP 668, venv, system install, missing pip, permissions, version conflict, hash mismatch, build wheel, no matching dist, SSL, python version) |

### Layer 1: INFRA handlers (9 cross-tool)
All standard — network, disk, permissions, OOM, timeout.

### Layer 3: None needed.
No unique isort-specific failure modes.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  570/570 (100%) — 30 scenarios × 19 presets
Handlers:  21 method-specific + 9 INFRA = 30
```

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "isort"` |
| `data/recipes.py` | Updated label to "Python import sorter" |
| `data/recipes.py` | Added `pipx` install method (**recommended**) |
| `data/recipes.py` | Added `pacman` install method (`python-isort`) |
| `data/recipes.py` | Added `brew` install method |
| `data/recipes.py` | Added `prefer` list (pipx > pacman > brew) |
| `data/recipes.py` | Added `update` commands for all 4 methods |
| `data/recipes.py` | Added research comments |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | Standard formula |
| **Any with pipx** | pipx | **Recommended** — isolated |
| **Arch** | pacman | Package: `python-isort` |
| **Debian/Ubuntu** | pipx or pip | Not in apt |
| **Fedora/RHEL** | pipx or pip | Not in dnf |
| **Alpine** | pipx or pip | Not in apk |
| **openSUSE** | pipx or pip | Not in zypper |
| **Any with pip** | _default (pip) | Universal fallback |

One native PM (pacman only). Most platforms rely on pipx/pip.
Standard pattern for pure Python CLI tools.
