# redis-cli — Full Spectrum Analysis

> **Tool ID:** `redis-cli`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Redis CLI (redis-cli command-line interface) |
| Language | C |
| Author | Redis Ltd. / Salvatore Sanfilippo |
| CLI binary | `redis-cli` |
| Category | `database` |
| Verify command | `redis-cli --version` |
| Recipe key | `redis-cli` |

### Special notes
- Written in C — compiled binary.
- Client-only intent but most distros package redis-cli with the server.
- **apt** has a dedicated `redis-tools` package — client-only, installs
  redis-cli without starting a Redis server.
- All other PMs install the full `redis` package (includes redis-cli +
  redis-server). The server won't auto-start without systemd enablement.
- Available in ALL major distro repos — no _default needed.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `redis-tools` | **Client-only** — no server |
| `dnf` | ✅ | `redis` | Full package (includes redis-cli) |
| `apk` | ✅ | `redis` | Full package |
| `pacman` | ✅ | `redis` | Full package |
| `zypper` | ✅ | `redis` | Full package |
| `brew` | ✅ | `redis` | Full package |
| `_default` | — | — | Not needed — full PM coverage |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Debian/Ubuntu | `apt-get install -y redis-tools` | apt |
| Fedora/RHEL | `dnf install -y redis` | dnf |
| Alpine | `apk add redis` | apk |
| Arch Linux | `pacman -S redis` | pacman |
| openSUSE | `zypper install -y redis` | zypper |
| macOS | `brew install redis` | brew |

All methods use the native PM — no fallback scripts needed.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| None | — | Installed from distro repos with deps handled by PM |

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
| `data/recipes.py` | Updated label to full description |
| `data/recipes.py` | Added `--no-cache` to apk command |
| `data/recipes.py` | Added `prefer: ["apt", "dnf", "apk", "pacman", "zypper", "brew"]` |
| `data/recipes.py` | Added `update` for all 6 methods |
| `data/recipes.py` | Added research comments |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **Debian/Ubuntu** | apt | **Native** — `redis-tools` (client-only) ✅ |
| **Fedora/RHEL** | dnf | **Native** — `redis` ✅ |
| **Alpine** | apk | **Native** — `redis` ✅ |
| **Arch Linux** | pacman | **Native** — `redis` ✅ |
| **openSUSE** | zypper | **Native** — `redis` ✅ |
| **macOS** | brew | Formula `redis` ✅ |
| **Raspbian** | apt | Same as Debian — `redis-tools` ✅ |
| **WSL** | apt | Same as Debian/Ubuntu ✅ |

**Full native PM coverage** — no fallback method needed.
Every target platform installs redis-cli from its distro's package repos.
