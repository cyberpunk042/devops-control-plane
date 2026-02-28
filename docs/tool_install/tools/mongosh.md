# mongosh — Full Spectrum Analysis

> **Tool ID:** `mongosh`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | MongoDB Shell (mongosh interactive client) |
| Language | TypeScript / Node.js |
| Author | MongoDB Inc. |
| CLI binary | `mongosh` |
| Category | `database` |
| Verify command | `mongosh --version` |
| Recipe key | `mongosh` |

### Special notes
- Written in TypeScript — requires Node.js runtime.
- Modern replacement for the legacy `mongo` shell (deprecated in MongoDB 6.0).
- **npm**: `mongosh` (global install via `npm install -g mongosh`).
- **brew**: `mongosh` formula — **preferred** (no Node.js dependency to manage).
- NOT in apt, dnf, apk, pacman, zypper (MongoDB provides their own repos
  but setup is complex — repo + GPG key. npm is simpler as a fallback).
- `_default` uses npm because mongosh is a Node.js package.
- Does NOT need sudo for either method — npm -g installs to user prefix,
  brew installs to homebrew prefix.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | MongoDB repo required (complex setup) |
| `dnf` | ❌ | — | MongoDB repo required (complex setup) |
| `apk` | ❌ | — | Not available |
| `pacman` | ❌ | — | AUR only (not standard pacman) |
| `zypper` | ❌ | — | Not available |
| `brew` | ✅ | `mongosh` | **Preferred** |
| `npm` (_default) | ✅ | `mongosh` | Global install |
| `snap` | ❌ | — | Not available |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| macOS/Linux (preferred) | `brew install mongosh` | brew |
| Any with Node.js (fallback) | `npm install -g mongosh` | npm (_default) |

### brew method (preferred)
```bash
brew install mongosh
```

### _default method (npm)
```bash
npm install -g mongosh
```
- **Does NOT need sudo** — npm global installs to user prefix.
- Requires Node.js and npm on PATH.
- `install_via: npm` — triggers npm family handlers.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Runtime | `npm` | For _default method |
| Runtime | `node` | npm requires Node.js |

brew method has no external dependencies.

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (18 total)
| Family | Handlers |
|--------|----------|
| `brew` | 1 (no formula) |
| `_default` | 5 (missing curl/git/wget/unzip/npm) |
| `npm` | 12 (install_via triggers npm-specific handlers) |

### Layer 1: INFRA handlers (9 cross-tool)
All standard — network, disk, permissions, OOM, timeout.

### Layer 3: None needed.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  513/513 (100%) — 27 scenarios × 19 presets
Handlers:  18 method-specific + 9 INFRA = 27
```

Higher scenario count than pure PM tools because the npm method family
adds handler scenarios (npm not found, Node.js version, etc.).

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "mongosh"` |
| `data/recipes.py` | Updated label to full description |
| `data/recipes.py` | Reordered methods — brew first |
| `data/recipes.py` | Added `prefer: ["brew"]` |
| `data/recipes.py` | Added research comments |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | **Preferred** — formula `mongosh` ✅ |
| **Linux with brew** | brew | Linuxbrew supported ✅ |
| **Debian/Ubuntu** | _default (npm) | Needs Node.js installed |
| **Fedora/RHEL** | _default (npm) | Needs Node.js installed |
| **Alpine** | _default (npm) | Needs Node.js installed |
| **Arch Linux** | _default (npm) | Needs Node.js installed |
| **openSUSE** | _default (npm) | Needs Node.js installed |
| **Raspbian** | _default (npm) | Needs Node.js installed |
| **WSL** | brew or npm | Standard methods |

brew preferred where available. npm as universal fallback — requires
Node.js/npm on PATH. If npm not installed, handler suggests installing
Node.js first via the `install_dep` strategy.
