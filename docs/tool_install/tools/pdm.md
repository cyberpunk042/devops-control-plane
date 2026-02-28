# pdm — Full Spectrum Analysis

> **Tool ID:** `pdm`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | pdm — modern Python package and project manager |
| Language | Python |
| CLI binary | `pdm` |
| Category | `python` |
| Verify command | `pdm --version` (needs PATH to `~/.local/bin`) |
| Recipe key | `pdm` |

### Special notes
- PEP 582 pioneer, now fully PEP 621 compliant.
- Supports virtual environments and PEP 582 `__pypackages__`.
- Lock-file based dependency management like Poetry but with standards-first approach.
- Written in Python — **NOT in any native system PMs** (apt, dnf, apk, etc.).
- Python-ecosystem only: pipx, pip, brew, official installer.
- Official installer pipes to `python3` (not bash) — requires python3 on PATH.
- Installs to `~/.local/bin` — requires `post_env` PATH export.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora repos |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ❌ | — | Not in Arch repos |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `pdm` | macOS/Linux |
| `pipx` | ✅ | `pdm` | **Recommended** — isolated env |
| `pip` | ✅ | `pdm` | PyPI |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Any (recommended) | `pipx install pdm` | pipx |
| Any with pip | `pip install --user pdm` | pip |
| macOS/Linux | `brew install pdm` | brew |
| Fallback | `curl -sSL https://pdm-project.org/install-pdm.py \| python3 -` | _default |

### _default method
```bash
curl -sSL https://pdm-project.org/install-pdm.py | python3 -
```
- **No sudo needed** — installs to `~/.local/bin`.
- Requires `curl` and `python3`.
- Official installer from pdm-project.org.
- `install_via: curl_pipe_bash` — triggers TLS, arch, and script 404 handlers.

### Post-install
```bash
export PATH="$HOME/.local/bin:$PATH"
```

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Runtime | `python3` | Python 3.8+ required |
| Download | `curl` | For _default method |
| Recommended | `pipx` | For isolated installation |

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (22 total)
| Family | Handlers |
|--------|----------|
| `pipx` | 2 (venv missing, pipx not installed) |
| `pip` | 11 (PEP 668, venv, system install, missing pip, permissions, version conflict, hash mismatch, build wheel, no matching dist, SSL, python version) |
| `brew` | 1 (no formula) |
| `_default` | 5 (missing curl/git/wget/unzip/npm) |
| `curl_pipe_bash` | 3 (TLS, unsupported arch, script 404) |

### Layer 1: INFRA handlers (9 cross-tool)
All standard — network, disk, permissions, OOM, timeout.

### Layer 3: None needed.
No unique pdm-specific failure modes. pip handlers cover all
Python-ecosystem edge cases comprehensively.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  589/589 (100%) — 31 scenarios × 19 presets
Handlers:  22 method-specific + 9 INFRA = 31
```

Highest scenario count in the project — pip's 11 handlers +
pipx's 2 + brew + _default + curl_pipe_bash = 22 method handlers.

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "pdm"` |
| `data/recipes.py` | Updated label to "modern Python package and project manager" |
| `data/recipes.py` | Added `pipx` and `pip` install methods (2 new) |
| `data/recipes.py` | Added `install_via` for pip and _default |
| `data/recipes.py` | Added `python3` to `requires.binaries` |
| `data/recipes.py` | Added `prefer` and `update` for all 4 methods |
| `data/recipes.py` | Added research comments |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | Standard formula |
| **Any with pipx** | pipx | **Recommended** — isolated |
| **Any with pip** | pip | User-level install |
| **Debian/Ubuntu** | pip or _default | Not in apt |
| **Fedora/RHEL** | pip or _default | Not in dnf |
| **Alpine** | pip or _default | Not in apk |
| **Arch** | pip or _default | Not in pacman |
| **openSUSE** | pip or _default | Not in zypper |
| **Any (fallback)** | _default | Official installer script |

No native PM coverage — all platforms rely on Python-ecosystem
methods (pipx, pip) or the official installer script.
