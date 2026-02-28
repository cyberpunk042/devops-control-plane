# pyright — Full Spectrum Analysis

> **Tool ID:** `pyright`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | pyright — fast Python type checker |
| Language | TypeScript/Node.js |
| Author | Microsoft |
| CLI binary | `pyright` |
| Category | `python` |
| Verify command | `pyright --version` |
| Recipe key | `pyright` |

### Special notes
- Written in TypeScript, runs on Node.js. By Microsoft.
- Static type checker for Python — analyzes type annotations.
- **Cross-ecosystem tool**: native install is npm, but a **PyPI wrapper** exists
  (`pyright` on pip/pipx) that bundles Node.js internally meaning pip/pipx
  install works **without npm being installed**.
- Wider method coverage than most Python-extended tools due to dual ecosystem.
- Available: pipx, npm, pacman, brew, snap.
- NOT in apt, dnf, apk, zypper.
- Highest scenario count in the project: **43 scenarios** (npm 12 + pip 11 +
  pipx 2 + pacman 2 + brew 1 + snap 1 + _default 5 + INFRA 9).

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora repos |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ✅ | `pyright` | Arch community |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `pyright` | macOS/Linux |
| `npm` | ✅ | `pyright` | Native install (npmjs.com) |
| `pip` | ✅ | `pyright` | PyPI wrapper — bundles Node.js |
| `pipx` | ✅ | `pyright` | Same wrapper — **recommended for Python devs** |
| `snap` | ✅ | `pyright` | Snapcraft (--classic) |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Python devs (recommended) | `pipx install pyright` | pipx |
| Arch Linux | `pacman -S --noconfirm pyright` | pacman |
| macOS/Linux | `brew install pyright` | brew |
| Snap-enabled | `snap install pyright --classic` | snap |
| Node.js devs (native) | `npm install -g pyright` | _default |

### _default method (npm)
```bash
npm install -g pyright
```
- **No sudo needed** — installs to npm global prefix.
- Requires `npm` on PATH.
- `install_via: npm` — triggers npm's comprehensive 12 failure handlers.

### pipx method (PyPI wrapper)
```bash
pipx install pyright
```
- PyPI package bundles Node.js internally via `nodeenv`.
- Works without npm — self-contained.
- Recommended for Python developers who don't have Node.js installed.

### snap --classic
The `--classic` flag is needed because pyright needs access to the
filesystem to read Python source files and type stubs.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Runtime | `npm` | For _default method only |
| Runtime | `python3` | For pipx method (PyPI wrapper) |

No C library dependencies.

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (34 total)
| Family | Handlers |
|--------|----------|
| `pipx` | 2 (venv missing, pipx not installed) |
| `pacman` | 2 (not found, locked) |
| `brew` | 1 (no formula) |
| `snap` | 1 (snapd unavailable) |
| `_default` | 5 (missing curl/git/wget/unzip/npm) |
| `npm` | 12 (EACCES, missing npm, ERESOLVE, node too old, node-gyp, cache corruption, registry auth, ETARGET, ELIFECYCLE, TLS cert, EBADPLATFORM, ENOENT) |
| `pip` | 11 (PEP 668, venv, system install, missing pip, permissions, version conflict, hash mismatch, build wheel, no matching dist, SSL, python version) |

### Layer 1: INFRA handlers (9 cross-tool)
All standard — network, disk, permissions, OOM, timeout.

### Layer 3: None needed.
No unique pyright-specific failure modes.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  817/817 (100%) — 43 scenarios × 19 presets
Handlers:  34 method-specific + 9 INFRA = 43
```

**New project record for scenario count.** The dual npm+pip ecosystem
plus pipx, pacman, brew, snap methods combine for 34 method handlers.

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "pyright"` |
| `data/recipes.py` | Updated label to "fast Python type checker — by Microsoft" |
| `data/recipes.py` | Added `pipx` method (recommended for Python devs) |
| `data/recipes.py` | Added `pacman` method |
| `data/recipes.py` | Added `snap` method (--classic) |
| `data/recipes.py` | Added `prefer` and `update` for all 5 methods |
| `data/recipes.py` | Added research comments (cross-ecosystem notes) |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | Standard formula |
| **Any with pipx** | pipx | **Recommended** — no npm needed |
| **Arch** | pacman | Community repos |
| **Any with snap** | snap | --classic for filesystem access |
| **Any with npm** | _default | Native Node.js install |
| **Debian/Ubuntu** | pipx or npm | Not in apt |
| **Fedora/RHEL** | pipx or npm | Not in dnf |
| **Alpine** | pipx or npm | Not in apk |
| **openSUSE** | pipx or npm | Not in zypper |

Cross-ecosystem tool — Python devs use pipx (PyPI wrapper bundles Node.js),
Node.js devs use npm (native).
