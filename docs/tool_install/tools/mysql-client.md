# mysql-client — Full Spectrum Analysis

> **Tool ID:** `mysql-client`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | MySQL client (mysql command-line interface) |
| Language | C/C++ |
| Author | Oracle Corporation / MySQL Community |
| CLI binary | `mysql` |
| Category | `database` |
| Verify command | `mysql --version` |
| Recipe key | `mysql-client` |

### Special notes
- Written in C/C++ — part of the MySQL project.
- **Binary name mismatch**: recipe key is `mysql-client` but CLI binary is `mysql`.
- Client-only — the recipe installs only the `mysql` CLI, NOT the MySQL server.
- **Package names differ significantly across distros**:
  - apt: `mysql-client`
  - dnf: `mysql`
  - apk: `mysql-client`
  - pacman: `mariadb-clients` (Arch defaults to MariaDB as MySQL-compatible)
  - zypper: `mysql-client`
  - brew: `mysql-client` (keg-only formula)
- Arch Linux uses MariaDB as its default MySQL-compatible client. The
  `mariadb-clients` package provides the `mysql` binary.
- Available in ALL major distro repos — no _default needed.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `mysql-client` | Client-only package |
| `dnf` | ✅ | `mysql` | Includes client tools |
| `apk` | ✅ | `mysql-client` | Client-only package |
| `pacman` | ✅ | `mariadb-clients` | MariaDB compat — provides `mysql` |
| `zypper` | ✅ | `mysql-client` | Client-only package |
| `brew` | ✅ | `mysql-client` | Keg-only formula |
| `_default` | — | — | Not needed — full PM coverage |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Debian/Ubuntu | `apt-get install -y mysql-client` | apt |
| Fedora/RHEL | `dnf install -y mysql` | dnf |
| Alpine | `apk add mysql-client` | apk |
| Arch Linux | `pacman -S mariadb-clients` | pacman |
| openSUSE | `zypper install -y mysql-client` | zypper |
| macOS | `brew install mysql-client` | brew |

All methods use the native PM — no fallback scripts needed.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| None | — | Installed from distro repos with deps handled by PM |

Package managers resolve all dependencies automatically (libmysqlclient, openssl).

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
| **Debian/Ubuntu** | apt | **Native** — `mysql-client` ✅ |
| **Fedora/RHEL** | dnf | **Native** — `mysql` ✅ |
| **Alpine** | apk | **Native** — `mysql-client` ✅ |
| **Arch Linux** | pacman | **Native** — `mariadb-clients` (provides `mysql`) ✅ |
| **openSUSE** | zypper | **Native** — `mysql-client` ✅ |
| **macOS** | brew | Formula `mysql-client` (keg-only) ✅ |
| **Raspbian** | apt | Same as Debian ✅ |
| **WSL** | apt | Same as Debian/Ubuntu ✅ |

**Full native PM coverage** — no fallback method needed.
Every target platform installs mysql-client from its distro's package repos.
