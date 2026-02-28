# cypress — Full Spectrum Analysis

> **Tool ID:** `cypress`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | cypress — JavaScript E2E and component testing |
| Language | JavaScript |
| Author | Cypress.io |
| CLI binary | `cypress` |
| Category | `testing` |
| Verify command | `cypress --version` |
| Recipe key | `cypress` |

### Special notes
- Full-featured E2E and component testing framework for web applications.
- Has a desktop Test Runner app (Electron-based) and CLI mode.
- Downloads a large binary (~200 MB) on first `cypress install` / first run.
- Time-travel debugging — takes snapshots at each test step.
- Automatic waiting — no need for explicit waits/sleeps.
- npm-only — no brew, no native PMs.
- Note: `cypress` category is `testing` (not `node`) because it's a test tool.
- Runs in-browser — real Chrome, Firefox, Edge, Electron.

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
| `npm` | ✅ | `cypress` | **Only method** |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Any with npm | `npm install -g cypress` | _default (npm) |

### _default method (npm)
```bash
npm install -g cypress
```
- **No sudo needed** — npm global installs go to user's npm prefix.
- Requires `npm` on PATH.
- `install_via: npm`.
- Downloads Cypress binary on first run (~200 MB).

### System dependencies (Linux)
Cypress on Linux may require X11 libraries for the desktop app:
```
libgtk2.0-0 libgtk-3-0 libgbm-dev libnotify-dev libnss3 libxss1 libasound2
```
CLI-only (headless) mode avoids most of these.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Runtime | `npm` | Node.js + npm required |
| Post-install | Cypress binary | ~200 MB, downloaded on first run |
| Linux (GUI) | X11 libs | For Test Runner desktop app |

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
Cypress binary download failures are covered by npm and INFRA handlers.

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
| `data/recipes.py` | Added `cli: "cypress"` |
| `data/recipes.py` | Updated label to "JavaScript E2E and component testing" |
| `data/recipes.py` | Added `update` command |
| `data/recipes.py` | Added research comments |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | _default (npm) | Requires Node.js |
| **Debian/Ubuntu** | _default (npm) | May need X11 libs for GUI |
| **Fedora/RHEL** | _default (npm) | May need X11 libs for GUI |
| **Alpine** | _default (npm) | Limited — no X11 by default |
| **Arch** | _default (npm) | Not in pacman |
| **openSUSE** | _default (npm) | Not in zypper |
| **Any with Node.js** | _default (npm) | Universal — only method |

No native PM coverage. npm-only. Headless mode recommended
for CI/containers (avoids X11 dependency).
