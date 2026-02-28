# tox — Full Spectrum Analysis

> **Tool ID:** `tox`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | tox — Python test automation and virtualenv management |
| Language | Python |
| Author | tox-dev (originally Holger Krekel) |
| CLI binary | `tox` |
| Category | `python` |
| Verify command | `tox --version` |
| Recipe key | `tox` |

### Special notes
- Standard tool for testing Python packages across multiple Python versions.
- Automates virtualenv creation, dependency installation, and test execution.
- Configured via `tox.ini`, `setup.cfg`, or `pyproject.toml`.
- tox v4 is a complete rewrite — faster, more extensible, parallel execution.
- Used by most major Python projects for CI testing.
- Written in Python — pure Python package, no C extensions.
- Available in pacman as `python-tox` (Arch naming convention).
- Available in brew as `tox`.
- NOT in apt, dnf, apk, zypper, snap.
- `pipx` is the recommended install method for isolated CLI tools.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora repos |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ✅ | `python-tox` | Arch community (note: `python-` prefix) |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `tox` | macOS/Linux |
| `pipx` | ✅ | `tox` | **Recommended** — isolated env |
| `pip` | ✅ | `tox` | PyPI |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Any (recommended) | `pipx install tox` | pipx |
| Arch Linux | `pacman -S --noconfirm python-tox` | pacman |
| macOS/Linux | `brew install tox` | brew |
| Fallback | `python3 -m pip install tox` | _default (pip) |

### pipx method (recommended)
```bash
pipx install tox
```
- **No sudo needed** — installs in isolated virtualenv.
- tox manages its own virtualenvs for test environments.

### _default method (pip)
```bash
python3 -m pip install tox
```
- `install_via: pip` — triggers pip's comprehensive 11 failure handlers.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Runtime | `python3` | Python 3.7+ required |
| Recommended | `pipx` | For isolated installation |
| Runtime | Multiple Python versions | For multi-version testing |

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
No unique tox-specific failure modes.

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
| `data/recipes.py` | Added `cli: "tox"` |
| `data/recipes.py` | Updated label to "Python test automation and virtualenv management" |
| `data/recipes.py` | Added `pipx` install method (**recommended**) |
| `data/recipes.py` | Added `pacman` install method (`python-tox`) |
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
| **Arch** | pacman | Package: `python-tox` |
| **Debian/Ubuntu** | pipx or pip | Not in apt |
| **Fedora/RHEL** | pipx or pip | Not in dnf |
| **Alpine** | pipx or pip | Not in apk |
| **openSUSE** | pipx or pip | Not in zypper |
| **Any with pip** | _default (pip) | Universal fallback |

One native PM (pacman only). Most platforms rely on pipx/pip.
Standard pattern for pure Python CLI tools.
