# tsx — Full Spectrum Analysis

> **Tool ID:** `tsx`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | tsx — TypeScript execute for Node.js |
| Language | TypeScript/JavaScript |
| Author | privatenumber |
| CLI binary | `tsx` |
| Category | `node` |
| Verify command | `tsx --version` |
| Recipe key | `tsx` |

### Special notes
- Runs TypeScript (and ESM) files directly via Node.js without compilation.
- Enhanced Node.js — patches Node's module system to handle `.ts` files.
- Drop-in replacement for `node` when running TypeScript files.
- Significantly faster than `ts-node` — uses esbuild for transpilation.
- npm-only tool — no brew, no native PMs, no binary downloads.
- Single install method — `npm install -g tsx`.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora repos |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ❌ | — | Not in Arch repos |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ❌ | — | Not in Homebrew |
| `npm` | ✅ | `tsx` | **Only method** |
| `pip` | ❌ | — | Not a Python tool |
| `cargo` | ❌ | — | Not a Rust tool |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Any with npm | `npm install -g tsx` | _default (npm) |

### _default method (npm)
```bash
npm install -g tsx
```
- **No sudo needed** — npm global installs go to user's npm prefix.
- Requires `npm` on PATH (comes with Node.js).
- `install_via: npm` — triggers npm's comprehensive failure handlers.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Runtime | `npm` | Node.js + npm required |

No C library dependencies — pure JavaScript package.

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (17 total)
| Family | Handlers |
|--------|----------|
| `npm` | 12 (EACCES, ERESOLVE, node-gyp, cache corrupt, registry auth, TLS, ETARGET, ELIFECYCLE, EBADPLATFORM, ENOENT, missing npm, version) |
| `_default` | 5 (missing curl/git/wget/unzip/npm) |

### Layer 1: INFRA handlers (9 cross-tool)
All standard — network, disk, permissions, OOM, timeout.

### Layer 3: None needed.
No unique tsx-specific failure modes. npm handlers cover all
Node ecosystem scenarios comprehensively.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  494/494 (100%) — 26 scenarios × 19 presets
Handlers:  17 method-specific + 9 INFRA = 26
```

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "tsx"` |
| `data/recipes.py` | Updated label to "TypeScript execute — Node.js enhanced" |
| `data/recipes.py` | Added research comments |
| `data/recipes.py` | `update` already present |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | _default (npm) | Requires Node.js |
| **Debian/Ubuntu** | _default (npm) | Not in apt |
| **Fedora/RHEL** | _default (npm) | Not in dnf |
| **Alpine** | _default (npm) | Not in apk |
| **Arch** | _default (npm) | Not in pacman |
| **openSUSE** | _default (npm) | Not in zypper |
| **Any with Node.js** | _default (npm) | Universal — only method |

No native PM coverage. npm is the sole install path.
Standard for npm-ecosystem dev tools.
