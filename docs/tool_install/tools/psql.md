# psql — Full Spectrum Analysis

> **Tool ID:** `psql`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | psql — PostgreSQL interactive terminal |
| Language | C |
| Author | PostgreSQL Global Development Group |
| CLI binary | `psql` |
| Category | `database` |
| Verify command | `psql --version` |
| Recipe key | `psql` |

### Special notes
- Written in C — part of the PostgreSQL project.
- Client-only: the recipe installs only `psql`, NOT the PostgreSQL server.
- **Package names differ across distros**: apt=`postgresql-client`,
  dnf/pacman/zypper=`postgresql`, apk=`postgresql-client`,
  brew=`libpq` (client-only keg formula).
- brew `libpq` is keg-only — may need `brew link --force libpq`
  or PATH addition for `psql` to be found.
- Available in ALL major distro repos — no _default needed.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `postgresql-client` | Client-only package |
| `dnf` | ✅ | `postgresql` | Includes psql |
| `apk` | ✅ | `postgresql-client` | Client-only package |
| `pacman` | ✅ | `postgresql` | Full package (includes psql) |
| `zypper` | ✅ | `postgresql` | Includes psql |
| `brew` | ✅ | `libpq` | Client-only keg formula |
| `_default` | — | — | Not needed — full PM coverage |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Debian/Ubuntu | `apt-get install -y postgresql-client` | apt |
| Fedora/RHEL | `dnf install -y postgresql` | dnf |
| Alpine | `apk add postgresql-client` | apk |
| Arch Linux | `pacman -S postgresql` | pacman |
| openSUSE | `zypper install -y postgresql` | zypper |
| macOS | `brew install libpq` | brew |

---

## 4. Dependencies

None — package managers resolve all dependencies.

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (10 total)
| Family | Handlers |
|--------|----------|
| `apt` | 2 (not found, PM locked) |
| `dnf` | 1 (not found) |
| `apk` | 2 (not found, db locked) |
| `pacman` | 2 (not found, db locked) |
| `zypper` | 2 (not found, PM locked) |
| `brew` | 1 (no formula) |

### Layer 1: INFRA handlers (9 cross-tool)
All standard.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  361/361 (100%) — 19 scenarios × 19 presets
```

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "psql"` |
| `data/recipes.py` | Updated label |
| `data/recipes.py` | Added `prefer`, `update`, research comments |

---

## 8. Platform Coverage

| Platform | Method |
|----------|--------|
| **Debian/Ubuntu** | apt ✅ |
| **Fedora/RHEL** | dnf ✅ |
| **Alpine** | apk ✅ |
| **Arch Linux** | pacman ✅ |
| **openSUSE** | zypper ✅ |
| **macOS** | brew ✅ |
| **Raspbian** | apt ✅ |
| **WSL** | apt ✅ |

Full native PM coverage — every target platform.
