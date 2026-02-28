# sqlite3 — Full Spectrum Analysis

> **Tool ID:** `sqlite3`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | SQLite3 (lightweight embedded SQL database) |
| Language | C |
| Author | D. Richard Hipp / SQLite Consortium |
| CLI binary | `sqlite3` |
| Category | `database` |
| Verify command | `sqlite3 --version` |
| Recipe key | `sqlite3` |

### Special notes
- Written in C — the most widely deployed database engine in the world.
- Self-contained, serverless, zero-configuration, transactional.
- **Package names differ**: apt/zypper use `sqlite3`, while
  dnf/apk/pacman/brew use `sqlite`.
- brew `sqlite` is keg-only — may need PATH addition.
- Available in ALL major distro repos — no _default needed.
- Often pre-installed on many Linux distros and macOS.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `sqlite3` | |
| `dnf` | ✅ | `sqlite` | |
| `apk` | ✅ | `sqlite` | |
| `pacman` | ✅ | `sqlite` | |
| `zypper` | ✅ | `sqlite3` | |
| `brew` | ✅ | `sqlite` | Keg-only |
| `_default` | — | — | Not needed — full PM coverage |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Debian/Ubuntu | `apt-get install -y sqlite3` | apt |
| Fedora/RHEL | `dnf install -y sqlite` | dnf |
| Alpine | `apk add sqlite` | apk |
| Arch Linux | `pacman -S sqlite` | pacman |
| openSUSE | `zypper install -y sqlite3` | zypper |
| macOS | `brew install sqlite` | brew |

All methods use the native PM — no fallback scripts needed.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| None | — | Self-contained — no external dependencies |

SQLite is famously dependency-free. The entire library is a single C file.

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (10 total)
| Family | Handlers |
|--------|----------|
| `apt` | 2 (not found, PM locked) |
| `dnf` | 1 (not found) |
| `apk` | 2 (not found/dep conflict, db locked) |
| `pacman` | 2 (not found, db locked) |
| `zypper` | 2 (not found, PM locked) |
| `brew` | 1 (no formula) |

### Layer 1: INFRA handlers (9 cross-tool)
All standard — network, disk, permissions, OOM, timeout.

### Layer 3: None needed.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  361/361 (100%) — 19 scenarios × 19 presets
Handlers:  10 method-specific + 9 INFRA = 19
```

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "sqlite3"` |
| `data/recipes.py` | Updated label to "SQLite3 (lightweight embedded SQL database)" |
| `data/recipes.py` | Added `--no-cache` to apk command |
| `data/recipes.py` | Added `prefer: ["apt", "dnf", "apk", "pacman", "zypper", "brew"]` |
| `data/recipes.py` | Added `update` for all 6 methods |
| `data/recipes.py` | Added research comments |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **Debian/Ubuntu** | apt | **Native** — `sqlite3` ✅ |
| **Fedora/RHEL** | dnf | **Native** — `sqlite` ✅ |
| **Alpine** | apk | **Native** — `sqlite` ✅ |
| **Arch Linux** | pacman | **Native** — `sqlite` ✅ |
| **openSUSE** | zypper | **Native** — `sqlite3` ✅ |
| **macOS** | brew | Formula `sqlite` (keg-only) ✅ |
| **Raspbian** | apt | Same as Debian ✅ |
| **WSL** | apt | Same as Debian/Ubuntu ✅ |

**Full native PM coverage** — no fallback method needed.
Every target platform installs SQLite from its distro's package repos.
Often pre-installed on Linux and macOS.
