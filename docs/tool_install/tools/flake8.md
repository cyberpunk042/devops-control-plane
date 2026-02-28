# flake8 — Full Spectrum Analysis

> **Tool ID:** `flake8`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | flake8 — Python linter (PEP 8 + pyflakes + mccabe) |
| Language | Python |
| Author | PyCQA (Python Code Quality Authority) |
| CLI binary | `flake8` |
| Category | `python` |
| Verify command | `flake8 --version` |
| Recipe key | `flake8` |

### Special notes
- Wraps three tools: pycodestyle (PEP 8), pyflakes (logical errors), mccabe (complexity).
- Extensible plugin ecosystem — hundreds of plugins available on PyPI.
- Industry standard Python linter — used in nearly every Python project.
- Written in Python — pure Python package, no C extensions.
- Available in pacman as `flake8` (same name on Arch).
- Available in brew as `flake8`.
- NOT in apt, dnf, apk, zypper, snap.
- `pipx` is the recommended install method for isolated CLI tools.
- Being gradually replaced by `ruff` in new projects, but still dominant.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora repos |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ✅ | `flake8` | Arch community (same name) |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `flake8` | macOS/Linux |
| `pipx` | ✅ | `flake8` | **Recommended** — isolated env |
| `pip` | ✅ | `flake8` | PyPI |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Any (recommended) | `pipx install flake8` | pipx |
| Arch Linux | `pacman -S --noconfirm flake8` | pacman |
| macOS/Linux | `brew install flake8` | brew |
| Fallback | `python3 -m pip install flake8` | _default (pip) |

### pipx method (recommended)
```bash
pipx install flake8
```
- **No sudo needed** — installs in isolated virtualenv.
- Note: pipx isolation means plugins must be injected: `pipx inject flake8 plugin-name`.

### _default method (pip)
```bash
python3 -m pip install flake8
```
- `install_via: pip` — triggers pip's comprehensive 11 failure handlers.
- Plugins install naturally alongside with pip.

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
No unique flake8-specific failure modes.

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
| `data/recipes.py` | Added `cli: "flake8"` |
| `data/recipes.py` | Updated label to "Python linter (PEP 8 + pyflakes + mccabe)" |
| `data/recipes.py` | Added `pipx` install method (**recommended**) |
| `data/recipes.py` | Added `pacman` install method (`flake8`) |
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
| **Arch** | pacman | Package: `flake8` (same name) |
| **Debian/Ubuntu** | pipx or pip | Not in apt |
| **Fedora/RHEL** | pipx or pip | Not in dnf |
| **Alpine** | pipx or pip | Not in apk |
| **openSUSE** | pipx or pip | Not in zypper |
| **Any with pip** | _default (pip) | Universal fallback |

One native PM (pacman only). Most platforms rely on pipx/pip.
Standard pattern for pure Python CLI tools.
