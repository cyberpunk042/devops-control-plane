# bun — Full Spectrum Analysis

> **Tool ID:** `bun`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | bun — fast all-in-one JavaScript runtime, bundler, and PM |
| Language | Zig |
| Author | Oven (Jarred Sumner) |
| CLI binary | `bun` |
| Category | `node` |
| Verify command | `bun --version` (needs PATH to `~/.bun/bin`) |
| Recipe key | `bun` |

### Special notes
- Written in **Zig** — not JavaScript or C/C++ like Node.js/Deno.
- All-in-one: JS/TS runtime + bundler + package manager + test runner.
- Drop-in replacement for Node.js with dramatically faster startup and npm compatibility.
- Official installer pipes to bash — installs to `~/.bun/bin`.
- brew uses **tap** formula: `oven-sh/bun/bun` (not a core formula).
- npm install works — installs the runtime via its competitor (ironic but functional).
- NOT in apt, dnf, apk, zypper, snap system repos.
- pacman: AUR only (`bun-bin`) — skipped because AUR isn't standard pacman.
- Fastest-growing JS runtime — designed for speed and modern web workloads.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora repos |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ⚠️ | `bun-bin` | AUR only — skipped |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `oven-sh/bun/bun` | Tap formula |
| `npm` | ✅ | `bun` | Cross-ecosystem install |
| `_default` | ✅ | — | Official `curl \| bash` installer |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| macOS/Linux (preferred) | `brew install oven-sh/bun/bun` | brew |
| Any with npm | `npm install -g bun` | npm |
| Any (fallback) | `curl -fsSL https://bun.sh/install \| bash` | _default |

### brew method (preferred)
```bash
brew install oven-sh/bun/bun
```

### npm method
```bash
npm install -g bun
```
- Installs the Zig-compiled runtime via npm — works on all Node.js platforms.

### _default method (installer script)
```bash
curl -fsSL https://bun.sh/install | bash
```
- **No sudo needed** — installs to `~/.bun/bin`.
- Requires `curl` on PATH.
- `install_via: curl_pipe_bash`.

### Post-install
```bash
export PATH="$HOME/.bun/bin:$PATH"
```

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For _default method |

No C library dependencies — self-contained Zig binary.

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (24 total)
| Family | Handlers |
|--------|----------|
| `brew` | 1 (no formula) |
| `npm` | 12 (EACCES, ERESOLVE, node-gyp, cache corrupt, registry auth, TLS, ETARGET, ELIFECYCLE, EBADPLATFORM, ENOENT, missing npm, version) |
| `_default` | 5 (missing curl/git/wget/unzip/npm) |
| `curl_pipe_bash` | 3 (TLS, unsupported arch, script 404) |

### Layer 1: INFRA handlers (9 cross-tool)
All standard — network, disk, permissions, OOM, timeout.

### Layer 3: None needed.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  570/570 (100%) — 30 scenarios × 19 presets
Handlers:  21 method-specific + 9 INFRA = 30
```

Multi-method tool — 3 install paths contribute to higher scenario count.

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "bun"` |
| `data/recipes.py` | Updated label to "fast all-in-one JavaScript runtime, bundler, and PM" |
| `data/recipes.py` | Added `npm` install method |
| `data/recipes.py` | Added `prefer: ["brew", "npm"]` |
| `data/recipes.py` | Added `update` commands for all 3 methods |
| `data/recipes.py` | Added research comments |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | Tap: `oven-sh/bun/bun` |
| **Linux with brew** | brew | Linuxbrew supported |
| **Any with npm** | npm | Cross-ecosystem install |
| **Debian/Ubuntu** | npm or _default | Not in apt |
| **Fedora/RHEL** | npm or _default | Not in dnf |
| **Alpine** | npm or _default | Not in apk |
| **Arch** | npm or _default | AUR only (skipped) |
| **openSUSE** | npm or _default | Not in zypper |
| **Any (fallback)** | _default | Official `bun.sh/install` script |

No native system PM coverage. brew (tap) + npm + installer script
provide universal coverage across all platforms.
