# fzf — Full Spectrum Analysis

> **Tool ID:** `fzf`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | fzf — command-line fuzzy finder |
| Language | Go |
| CLI binary | `fzf` |
| Category | `devtools` |
| Verify command | `fzf --version` |
| Recipe key | `fzf` |

### Special notes
- By junegunn. Interactive Unix filter for any list (files, history, processes, etc.).
- Integrates with shell (bash, zsh, fish) for Ctrl+R history search and file completion.
- Available in ALL 6 native PMs.
- _default method uses `git clone` to `~/.fzf` — unique pattern vs curl downloads.
- _default runs as user (no sudo needed) — installs to home directory.
- Snap exists (`fzf-slowday`) but is unofficial — not included in recipe.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `fzf` | Debian/Ubuntu |
| `dnf` | ✅ | `fzf` | Fedora/RHEL |
| `apk` | ✅ | `fzf` | Alpine |
| `pacman` | ✅ | `fzf` | Arch |
| `zypper` | ✅ | `fzf` | openSUSE |
| `brew` | ✅ | `fzf` | macOS |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Debian/Ubuntu | `apt-get install -y fzf` | apt |
| Fedora/RHEL | `dnf install -y fzf` | dnf |
| Alpine | `apk add fzf` | apk |
| Arch | `pacman -S --noconfirm fzf` | pacman |
| openSUSE | `zypper install -y fzf` | zypper |
| macOS | `brew install fzf` | brew |
| Fallback | `git clone --depth 1 ... ~/.fzf && ~/.fzf/install --all` | _default |

### _default method (unique pattern)
```bash
git clone --depth 1 https://github.com/junegunn/fzf.git ~/.fzf && ~/.fzf/install --all
```
- **No sudo needed** — installs to user home `~/.fzf`.
- Requires `git` (not curl).
- `--all` flag: enables key bindings, fuzzy completion, and updates shell config.
- Update: `cd ~/.fzf && git pull && ./install --all`.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `git` | For _default method (git clone) |

No runtime dependencies — standalone Go binary.

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (15 total)
| Family | Handlers |
|--------|----------|
| `apt` | 2 (stale index, locked) |
| `dnf` | 1 (no match) |
| `apk` | 2 (unsatisfiable, locked) |
| `pacman` | 2 (not found, locked) |
| `zypper` | 2 (not found, locked) |
| `brew` | 1 (no formula) |
| `_default` | 5 (missing curl/git/wget/unzip/npm) |

### Layer 1: INFRA handlers (9 cross-tool)
All standard — network, disk, permissions, OOM, timeout.

### Layer 3: None needed.
No unique fzf-specific failure modes.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  456/456 (100%) — 24 scenarios × 19 presets
Handlers:  15 method-specific + 9 INFRA = 24
```

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "fzf"` |
| `data/recipes.py` | Updated label to "command-line fuzzy finder" |
| `data/recipes.py` | Added `zypper` install method |
| `data/recipes.py` | Added `git` to `requires.binaries` |
| `data/recipes.py` | Added `prefer` list for all 6 native PMs |
| `data/recipes.py` | Added `update` commands for all 7 methods |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | Standard formula |
| **Raspbian (aarch64)** | apt | Standard repos |
| **Debian/Ubuntu** | apt | Standard repos |
| **Fedora/RHEL** | dnf | Standard repos |
| **Alpine** | apk | Standard repos |
| **Arch** | pacman | Standard repos |
| **openSUSE** | zypper | Standard repos |
| **Any (fallback)** | _default | git clone to ~/.fzf (user-local) |

All presets have native PM coverage. _default provides universal fallback
via git clone to user home directory (no root required).
