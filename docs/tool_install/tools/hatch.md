# hatch — Full Spectrum Analysis

> **Tool ID:** `hatch`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | hatch — modern Python project manager |
| Language | Python |
| CLI binary | `hatch` |
| Category | `python` |
| Verify command | `hatch --version` |
| Recipe key | `hatch` |

### Special notes
- Official PyPA (Python Packaging Authority) project manager.
- Handles environment management, building, publishing, version bumping, and testing.
- PEP 621 compliant — uses `pyproject.toml` as the single source of truth.
- Written in Python — primarily installed via Python-ecosystem tools.
- Available in pacman as `python-hatch` — only native PM that carries it.
- Available on conda-forge but we don't track conda as a PM.
- `pipx` is the recommended install method for isolated CLI tools.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora repos |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ✅ | `python-hatch` | Arch community (note: `python-` prefix) |
| `zypper` | ❌ | — | Only plugins available, not hatch itself |
| `brew` | ✅ | `hatch` | macOS/Linux |
| `pipx` | ✅ | `hatch` | **Recommended** — isolated env |
| `pip` | ✅ | `hatch` | PyPI |
| `conda` | ✅ | `hatch` | conda-forge — not tracked |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Any (recommended) | `pipx install hatch` | pipx |
| Arch Linux | `pacman -S --noconfirm python-hatch` | pacman |
| macOS/Linux | `brew install hatch` | brew |
| Fallback | `python3 -m pip install hatch` | _default (pip) |

### Pacman note
Package name is `python-hatch` (not `hatch`) — follows Arch's naming
convention for Python packages. Binary is still `hatch`.

### _default method (pip)
```bash
python3 -m pip install hatch
```
- **No sudo needed** — installs to user site-packages.
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
No unique hatch-specific failure modes.

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
| `data/recipes.py` | Added `cli: "hatch"` |
| `data/recipes.py` | Updated label to "modern Python project manager — PyPA" |
| `data/recipes.py` | Added `pipx` install method (**recommended**) |
| `data/recipes.py` | Added `pacman` install method (`python-hatch`) |
| `data/recipes.py` | Added `prefer` list (pipx > pacman > brew) |
| `data/recipes.py` | Added `update` commands for all 4 methods |
| `data/recipes.py` | Added research comments |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | Standard formula |
| **Any with pipx** | pipx | **Recommended** — isolated |
| **Arch** | pacman | Package: `python-hatch` |
| **Debian/Ubuntu** | pip or pipx | Not in apt |
| **Fedora/RHEL** | pip or pipx | Not in dnf |
| **Alpine** | pip or pipx | Not in apk |
| **openSUSE** | pip or pipx | Not in zypper |
| **Any with pip** | _default (pip) | Universal fallback |

One native PM (pacman only). Most platforms rely on pipx/pip.
