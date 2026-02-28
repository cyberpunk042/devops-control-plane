# playwright — Full Spectrum Analysis

> **Tool ID:** `playwright`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | playwright — cross-browser E2E testing |
| Language | TypeScript/JavaScript |
| Author | Microsoft |
| CLI binary | `npx` (runs via `npx playwright`) |
| Category | `node` |
| Verify command | `npx playwright --version` |
| Recipe key | `playwright` |

### Special notes
- By Microsoft. Cross-browser automation and testing framework.
- Supports Chromium, Firefox, and WebKit — all three engines.
- Uses `npx` as CLI — no standalone global binary produced.
- After install, browsers must be downloaded separately: `npx playwright install`.
- Browser downloads are ~200 MB+ and require system dependencies
  (shared libraries for Chromium/Firefox/WebKit rendering).
- npm-only — no brew, no native PMs.
- Auto-waits for elements — more reliable than Selenium/Puppeteer.
- Supports test generation with codegen: `npx playwright codegen`.

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
| `npm` | ✅ | `playwright` | **Only method** |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Any with npm | `npm install -g playwright` | _default (npm) |

### _default method (npm)
```bash
npm install -g playwright
npx playwright install  # downloads browser binaries (separate step)
```
- **No sudo needed** for npm install.
- Browser install may need sudo for system dependencies.
- Requires `npm` on PATH.
- `install_via: npm`.

### Browser dependencies (post-install)
Playwright needs system libraries for browser rendering. On Debian/Ubuntu:
```bash
npx playwright install-deps  # installs required system packages
```

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Runtime | `npm` | Node.js + npm required |
| Post-install | browser binaries | Downloaded by `npx playwright install` |
| Post-install | system libs | Rendering libraries for Chromium/Firefox/WebKit |

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
Browser download failures are handled by npm and network INFRA handlers.

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
| `data/recipes.py` | Moved `cli: "npx"` to top of recipe |
| `data/recipes.py` | Updated label to "cross-browser E2E testing — by Microsoft" |
| `data/recipes.py` | Added `update` command |
| `data/recipes.py` | Added research comments |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | _default (npm) | Requires Node.js |
| **Debian/Ubuntu** | _default (npm) | Needs `install-deps` for browsers |
| **Fedora/RHEL** | _default (npm) | Needs `install-deps` for browsers |
| **Alpine** | _default (npm) | Limited browser support |
| **Arch** | _default (npm) | Not in pacman |
| **openSUSE** | _default (npm) | Not in zypper |
| **Any with Node.js** | _default (npm) | Universal — only method |

No native PM coverage. npm-only install, but post-install browser
setup may require platform-specific dependencies.
