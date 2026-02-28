# nginx — Full Spectrum Analysis

> **Tool ID:** `nginx`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Nginx — high-performance web server and reverse proxy |
| Language | C |
| Author | Igor Sysoev / F5 / Nginx Inc. |
| CLI binary | `nginx` |
| Category | `proxy` |
| Verify command | `nginx -v` |
| Recipe key | `nginx` |

### Special notes
- Written in C — compiled binary, available in every distro.
- **Best PM coverage in the project** — available in all 6 major PMs.
- No `_default` needed — every target platform has nginx in its repos.
- Verify uses `nginx -v` (NOT `--version`).
- snap available but rarely used — omitted.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `nginx` | Debian/Ubuntu — default repos |
| `dnf` | ✅ | `nginx` | Fedora/RHEL — default repos |
| `apk` | ✅ | `nginx` | Alpine — main repo |
| `pacman` | ✅ | `nginx` | Arch — extra repo |
| `zypper` | ✅ | `nginx` | openSUSE — default repos |
| `brew` | ✅ | `nginx` | macOS/Linux |
| `snap` | ⚠️ | `nginx` | Available but omitted |
| `_default` | — | — | Not needed — full PM coverage |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Debian/Ubuntu | `apt-get install -y nginx` | apt |
| Fedora/RHEL | `dnf install -y nginx` | dnf |
| Alpine | `apk add nginx` | apk |
| Arch Linux | `pacman -S nginx` | pacman |
| openSUSE | `zypper install -y nginx` | zypper |
| macOS | `brew install nginx` | brew |

All methods use the native PM — no fallback scripts needed.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| None | — | Installed from distro repos with deps handled by PM |

Package managers resolve all dependencies automatically (libpcre, zlib, openssl).

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
| `data/recipes.py` | Added `cli: "nginx"` |
| `data/recipes.py` | Updated label to full description |
| `data/recipes.py` | Added `--no-cache` to apk command |
| `data/recipes.py` | Added `prefer: ["apt", "dnf", "apk", "pacman", "zypper", "brew"]` |
| `data/recipes.py` | Added `update` for all 6 methods |
| `data/recipes.py` | Added research comments |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **Debian/Ubuntu** | apt | **Native** — default repos ✅ |
| **Fedora/RHEL** | dnf | **Native** — default repos ✅ |
| **Alpine** | apk | **Native** — main repo ✅ |
| **Arch Linux** | pacman | **Native** — extra repo ✅ |
| **openSUSE** | zypper | **Native** — default repos ✅ |
| **macOS** | brew | Formula `nginx` ✅ |
| **Raspbian** | apt | Same as Debian ✅ |
| **WSL** | apt | Same as Debian/Ubuntu ✅ |

**Full native PM coverage** — no fallback method needed.
Every target platform installs nginx from its distro's package repos.
