# nox — Full Spectrum Analysis

> **Tool ID:** `nox`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | nox — flexible Python test automation |
| Language | Python |
| Author | Thea Flowers (Google) |
| CLI binary | `nox` |
| Category | `python` |
| Verify command | `nox --version` |
| Recipe key | `nox` |

### Special notes
- Modern alternative to tox — uses Python functions instead of INI config.
- Sessions defined in `noxfile.py` as decorated Python functions.
- More flexible than tox — arbitrary Python logic for session setup.
- Supports conda environments alongside virtualenvs.
- Created at Google — used by many Google open-source Python projects.
- Written in Python — pure Python package, no C extensions.
- Available in pacman as `python-nox` (Arch naming convention).
- Available in brew as `nox`.
- NOT in apt, dnf, apk, zypper, snap.
- `pipx` is the recommended install method for isolated CLI tools.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora repos |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ✅ | `python-nox` | Arch community (note: `python-` prefix) |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `nox` | macOS/Linux |
| `pipx` | ✅ | `nox` | **Recommended** — isolated env |
| `pip` | ✅ | `nox` | PyPI |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Any (recommended) | `pipx install nox` | pipx |
| Arch Linux | `pacman -S --noconfirm python-nox` | pacman |
| macOS/Linux | `brew install nox` | brew |
| Fallback | `python3 -m pip install nox` | _default (pip) |

### pipx method (recommended)
```bash
pipx install nox
```
- **No sudo needed** — installs in isolated virtualenv.

### _default method (pip)
```bash
python3 -m pip install nox
```
- `install_via: pip` — triggers pip's comprehensive 11 failure handlers.

### Noxfile example
```python
import nox

@nox.session
def tests(session):
    session.install("pytest")
    session.run("pytest")
```

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Runtime | `python3` | Python 3.7+ required |
| Recommended | `pipx` | For isolated installation |
| Optional | Multiple Python versions | For multi-version testing |
| Optional | `conda` | For conda-backed sessions |

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
No unique nox-specific failure modes.

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
| `data/recipes.py` | Added `cli: "nox"` |
| `data/recipes.py` | Updated label to "flexible Python test automation" |
| `data/recipes.py` | Added `pipx` install method (**recommended**) |
| `data/recipes.py` | Added `pacman` install method (`python-nox`) |
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
| **Arch** | pacman | Package: `python-nox` |
| **Debian/Ubuntu** | pipx or pip | Not in apt |
| **Fedora/RHEL** | pipx or pip | Not in dnf |
| **Alpine** | pipx or pip | Not in apk |
| **openSUSE** | pipx or pip | Not in zypper |
| **Any with pip** | _default (pip) | Universal fallback |

One native PM (pacman only). Most platforms rely on pipx/pip.
Standard pattern for pure Python CLI tools.
