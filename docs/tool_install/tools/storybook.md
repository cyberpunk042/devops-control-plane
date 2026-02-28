# storybook — Full Spectrum Analysis

> **Tool ID:** `storybook`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | storybook — UI component explorer and workshop |
| Language | TypeScript/JavaScript |
| Author | Storybook (storybookjs) |
| CLI binary | `npx` (runs via `npx sb` or `npx storybook`) |
| Category | `node` |
| Verify command | `npx sb --version` |
| Recipe key | `storybook` |

### Special notes
- Interactive UI development environment for building components in isolation.
- Supports React, Vue, Angular, Svelte, Web Components, and more.
- Uses `npx` as CLI — runs via `npx storybook init` / `npx storybook dev`.
- Global install of `@storybook/cli` provides the `sb` command.
- The scoped package name `@storybook/cli` (not `storybook`) is the CLI package.
- npm-only — no brew, no native PMs.
- **New recipe** — created from scratch during this audit.
- Typically project-local, but global CLI is useful for `storybook init`.

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
| `npm` | ✅ | `@storybook/cli` | Scoped package — **only method** |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Any with npm | `npm install -g @storybook/cli` | _default (npm) |

### _default method (npm)
```bash
npm install -g @storybook/cli
```
- **No sudo needed** — npm global installs go to user's npm prefix.
- Requires `npm` on PATH.
- `install_via: npm`.
- Provides `sb` command globally.
- Alternative: use `npx storybook` without global install.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Runtime | `npm` | Node.js + npm required |
| Project | React/Vue/etc. | Framework-specific — project-level |

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
| `data/recipes.py` | **New recipe** — created from scratch |
| `data/recipes.py` | cli, label, install (npm), needs_sudo, install_via, requires, verify, update |
| `data/recipes.py` | Added research comments |

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

No native PM coverage. npm-only. Usually used via `npx` in
project context rather than global install.
