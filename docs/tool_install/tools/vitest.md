# vitest — Full Spectrum Analysis

> **Tool ID:** `vitest`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | vitest — Vite-native unit test framework |
| Language | TypeScript/JavaScript |
| Author | Vite team (vitest-dev) |
| CLI binary | `vitest` |
| Category | `node` |
| Verify command | `vitest --version` |
| Recipe key | `vitest` |

### Special notes
- Blazing fast unit testing framework powered by Vite's transform pipeline.
- Jest-compatible API — easy migration from Jest.
- Native ESM, TypeScript, and JSX support out of the box.
- Supports in-source testing (tests inline with source code).
- Built-in code coverage via v8 or istanbul.
- npm-only tool — no brew, no native PMs, no binary downloads.
- Typically installed as a project devDependency, but global install works for CLI.

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
| `npm` | ✅ | `vitest` | **Only method** |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Any with npm | `npm install -g vitest` | _default (npm) |

### _default method (npm)
```bash
npm install -g vitest
```
- **No sudo needed** — npm global installs go to user's npm prefix.
- Requires `npm` on PATH.
- `install_via: npm`.
- More commonly used as `npx vitest` or local devDependency.

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
| `data/recipes.py` | Added `cli: "vitest"` |
| `data/recipes.py` | Updated label to "Vite-native unit test framework" |
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

No native PM coverage. npm-only — standard for modern JS test frameworks.
