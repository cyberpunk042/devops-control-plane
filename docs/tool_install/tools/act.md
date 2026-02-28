# act — Full Spectrum Analysis

> **Tool ID:** `act`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | act — local GitHub Actions runner |
| Language | Go |
| Author | nektos |
| CLI binary | `act` |
| Category | `cicd` |
| Verify command | `act --version` |
| Recipe key | `act` |

### Special notes
- Runs GitHub Actions workflows locally using Docker containers.
- Written in Go — single static binary.
- **Runtime dependency**: Docker Engine must be installed and running.
- brew formula: `act`. pacman: `act` (Arch community repo).
- Official install.sh script auto-detects OS and arch at runtime
  (supports x86_64, aarch64, armv7).
- Script installs to `/usr/local/bin` by default (needs sudo).
- Also available via COPR (Fedora) but not standard dnf repos.
- NOT in apt, dnf (standard), apk, zypper, snap.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | COPR only — not standard |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ✅ | `act` | Arch community repo |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `act` | **Preferred** — macOS + Linux |
| `snap` | ❌ | — | Not available |
| `_default` | ✅ | — | Official `install.sh` script |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| macOS/Linux (preferred) | `brew install act` | brew |
| Arch Linux | `pacman -S act` | pacman |
| Any Linux (fallback) | Official install.sh | _default |

### brew method (preferred)
```bash
brew install act
```

### pacman method (Arch)
```bash
sudo pacman -S --noconfirm act
```

### _default method (install script)
```bash
curl -sSfL https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash
```
- **Needs sudo** — installs to `/usr/local/bin`.
- Script auto-detects OS and architecture.
- `install_via: curl_pipe_bash`.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For _default method |
| Runtime | `docker` | **Required** — act runs workflows in Docker |

Docker must be installed and the daemon must be running.

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (11 total)
| Family | Handlers |
|--------|----------|
| `brew` | 1 (no formula) |
| `pacman` | 2 (not found, db locked) |
| `_default` | 5 (missing curl/git/wget/unzip/npm) |
| `curl_pipe_bash` | 3 (TLS, unsupported arch, script 404) |

### Layer 1: INFRA handlers (9 cross-tool)
All standard — network, disk, permissions, OOM, timeout.

### Layer 3: None needed.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  380/380 (100%) — 20 scenarios × 19 presets
Handlers:  11 method-specific + 9 INFRA = 20
```

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Updated label to "act (local GitHub Actions runner)" |
| `data/recipes.py` | Added `pacman` install method |
| `data/recipes.py` | Added `prefer: ["brew", "pacman"]` |
| `data/recipes.py` | Added `update` for all 3 methods |
| `data/recipes.py` | Reordered methods (brew first as preferred) |
| `data/recipes.py` | Added research comments |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | **Preferred** — formula `act` |
| **Linux with brew** | brew | Linuxbrew supported |
| **Arch Linux** | pacman | Community repo — `act` |
| **Debian/Ubuntu** | _default | install.sh auto-detects arch |
| **Fedora/RHEL** | _default | COPR available but not used |
| **Alpine** | _default | Script installs Go binary |
| **openSUSE** | _default | Not in zypper |
| **Raspbian (aarch64)** | _default | Script auto-detects aarch64 ✅ |
| **WSL** | brew or _default | Docker Desktop required for WSL |

brew preferred. pacman for Arch. Install script as universal fallback.
All platforms require Docker runtime.
