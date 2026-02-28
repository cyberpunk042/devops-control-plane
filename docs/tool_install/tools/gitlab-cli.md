# gitlab-cli — Full Spectrum Analysis

> **Tool ID:** `gitlab-cli`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | glab — GitLab command-line tool |
| Language | Go |
| Author | GitLab (gitlab-org/cli) |
| CLI binary | `glab` |
| Category | `cicd` |
| Verify command | `glab --version` |
| Recipe key | `gitlab-cli` |

### Special notes
- **Binary name mismatch**: recipe key is `gitlab-cli` but CLI binary is `glab`.
- Written in Go — single static binary.
- Official repo: `gitlab.com/gitlab-org/cli` (formerly `profclems/glab`).
- **Old profclems install script URLs are BROKEN** — do not use.
- Wide PM coverage: brew, snap, pacman, dnf, apk — no curl script needed.
- NOT in apt (standard Debian/Ubuntu repos), zypper.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in standard Debian/Ubuntu repos |
| `dnf` | ✅ | `glab` | Fedora 38+ |
| `apk` | ✅ | `glab` | Alpine edge/testing |
| `pacman` | ✅ | `glab` | Arch community repo |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `glab` | **Preferred** — officially supported |
| `snap` | ✅ | `glab` | Good cross-distro fallback |
| `_default` | ✅ | — | Falls back to snap |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| macOS/Linux (preferred) | `brew install glab` | brew |
| Any Linux with snap | `snap install glab` | snap |
| Arch Linux | `pacman -S glab` | pacman |
| Fedora/RHEL | `dnf install glab` | dnf |
| Alpine | `apk add glab` | apk |

### brew method (preferred — officially supported)
```bash
brew install glab
```

### snap method
```bash
sudo snap install glab
```

### pacman method (Arch)
```bash
sudo pacman -S --noconfirm glab
```

### dnf method (Fedora)
```bash
sudo dnf install -y glab
```

### apk method (Alpine)
```bash
apk add --no-cache glab
```

### _default fallback
Falls back to snap — widely available on Linux distributions with systemd.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| None | — | Self-contained Go binary |

No runtime dependencies. No C library dependencies.

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (12 total)
| Family | Handlers |
|--------|----------|
| `brew` | 1 (no formula) |
| `snap` | 1 (snapd not running) |
| `pacman` | 2 (not found, db locked) |
| `dnf` | 1 (not found) |
| `apk` | 2 (not found, db locked) |
| `_default` | 5 (missing curl/git/wget/unzip/npm) |

### Layer 1: INFRA handlers (9 cross-tool)
All standard — network, disk, permissions, OOM, timeout.

### Layer 3: None needed.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  399/399 (100%) — 21 scenarios × 19 presets
Handlers:  12 method-specific + 9 INFRA = 21
```

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Moved `cli: "glab"` to top |
| `data/recipes.py` | Updated label to full description |
| `data/recipes.py` | Removed broken profclems install script |
| `data/recipes.py` | Added `snap` install method |
| `data/recipes.py` | Added `pacman` install method |
| `data/recipes.py` | Added `dnf` install method |
| `data/recipes.py` | Added `apk` install method |
| `data/recipes.py` | Set `_default` to snap (fallback) |
| `data/recipes.py` | Added `prefer: ["brew", "snap", "pacman", "dnf", "apk"]` |
| `data/recipes.py` | Added `update` for all methods |
| `data/recipes.py` | Removed `install_via` and `requires` (no curl needed) |
| `data/recipes.py` | Added research comments |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | **Preferred** — officially supported |
| **Linux with brew** | brew | Linuxbrew supported |
| **Debian/Ubuntu** | snap | Not in apt — snap is next best |
| **Fedora/RHEL** | dnf | `glab` in Fedora 38+ ✅ |
| **Alpine** | apk | `glab` in edge/testing ✅ |
| **Arch Linux** | pacman | Community repo ✅ |
| **openSUSE** | snap or _default | Not in zypper |
| **Raspbian** | _default (snap) | May need snap on Raspbian |
| **WSL** | brew or snap | Standard methods |

Best PM coverage in the CI/CD stack — 5 native PM methods.
No curl scripts needed. brew officially supported by GitLab.
