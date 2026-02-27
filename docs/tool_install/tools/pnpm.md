# pnpm — Full Spectrum Analysis

> **Tool ID:** `pnpm`
> **Last audited:** 2026-02-26
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | pnpm — fast, disk efficient Node.js package manager |
| Language | JavaScript |
| CLI binary | `pnpm` |
| Category | `node` |
| Verify command | `pnpm --version` |
| Recipe key | `pnpm` |

### Special notes
- pnpm uses a content-addressable store for node_modules, saving
  significant disk space compared to npm/yarn.
- Unlike yarn, pnpm has **very limited system PM availability**.
  Only `apk` (Alpine) and `brew` have official packages.
- pnpm has an **official standalone installer** at
  `https://get.pnpm.io/install.sh` that works **without npm**.
- The standalone installer handles OS/arch detection internally,
  downloading the correct pnpm binary for the platform.
- The brew formula **conflicts with corepack** (same as yarn).
- When installed via standalone script, pnpm installs to
  `$PNPM_HOME` (~/.local/share/pnpm) and needs PATH setup.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `npm` | ✅ | `pnpm` | Universal via `npm install -g pnpm` |
| `apk` | ✅ | `pnpm` | Alpine community/edge repo |
| `brew` | ✅ | `pnpm` | Conflicts with corepack formula |
| `apt` | ❌ | — | Not in default repos, no official PPA |
| `dnf` | ❌ | — | Not in Fedora repos |
| `pacman` | ❌ | — | Only AUR (not official repos) |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `snap` | ❌ | — | Not available |
| `pip` | ❌ | — | Not available |
| `cargo` | ❌ | — | Not available |

### Package name notes
- pnpm is `pnpm` everywhere it's available — no name divergence.
- No KNOWN_PACKAGES entry needed.

---

## 3. Install Method — _default (standalone script)

| Field | Value |
|-------|-------|
| Command | `curl -fsSL https://get.pnpm.io/install.sh \| sh -` |
| Script | Official pnpm standalone installer |
| Install location | `$PNPM_HOME` (default: `~/.local/share/pnpm`) |
| Dependencies | `curl` (download) |
| needs_sudo | No |

### Key advantage over npm method
The standalone installer does **not require npm** to be pre-installed.
It downloads a pre-built pnpm binary directly. This means pnpm can
be installed on a system that only has curl — no Node.js needed.

### Platform coverage
The standalone installer handles OS/arch detection internally:
- Linux x86_64 ✅
- Linux aarch64 ✅
- Linux armv7l (Raspbian) ✅
- macOS Intel ✅
- macOS Apple Silicon ✅

The npm method (`npm install -g pnpm`) is also platform-agnostic
since pnpm is a JS package (pure JavaScript, no native code).

### Post-install
When installed via standalone script, the PATH needs updating:
```bash
export PNPM_HOME="$HOME/.local/share/pnpm"
export PATH="$PNPM_HOME:$PATH"
```
This is configured via `post_env` in the recipe.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For `_default` standalone installer |
| Optional | `npm` | For `npm` install method |
| Optional | `node` | Required by npm (transitive) |

### Reverse deps
pnpm is used by:
- Monorepo setups (pnpm workspaces)
- Projects preferring disk-efficient dependency management
- CI/CD pipelines optimizing for speed and caching

---

## 5. Post-install

**npm method:** No PATH additions needed — pnpm binary goes to
npm's global bin directory.

**standalone method:** Requires PATH setup (handled by `post_env`):
```bash
export PNPM_HOME="$HOME/.local/share/pnpm"
export PATH="$PNPM_HOME:$PATH"
```

---

## 6. Failure Handlers

### Layer 1: method-family handlers
Because pnpm can be installed via `npm`, it inherits the **full
npm handler suite** (12 handlers). See yarn.md for the full list.

Additionally: `apk` (2 handlers), `brew` (1 handler), `_default`
(5 dependency handlers).

### Layer 2: INFRA handlers (9 cross-tool)
Network, disk, permissions, OOM, timeout — all standard.

### Layer 3: per-tool on_failure handlers

| Handler | Category | Trigger | Options |
|---------|----------|---------|---------|
| `pnpm_corepack_conflict` | configuration | `Cannot install pnpm because conflicting formulae` | Switch to npm (recommended), standalone installer, manual corepack unlink |

---

## 7. Recipe Structure

```python
"pnpm": {
    "cli": "pnpm",
    "label": "pnpm (fast, disk efficient Node package manager)",
    "category": "node",
    "install": {
        "npm":  ["npm", "install", "-g", "pnpm"],
        "apk":  ["apk", "add", "pnpm"],
        "brew": ["brew", "install", "pnpm"],
        "_default": [
            "bash", "-c",
            "curl -fsSL https://get.pnpm.io/install.sh | sh -",
        ],
    },
    "needs_sudo": {
        "npm": False, "apk": True,
        "brew": False, "_default": False,
    },
    "prefer": ["npm", "brew", "_default"],
    "requires": {"binaries": ["curl"]},
    "verify": ["pnpm", "--version"],
    "update": {
        "npm": ["npm", "update", "-g", "pnpm"],
        "brew": ["brew", "upgrade", "pnpm"],
    },
    "post_env": "export PNPM_HOME=...",
}
```

---

## 8. Validation Results

```
Schema:    VALID (recipe + all method-family handlers + on_failure)
Coverage:  570/570 (100%) — 30 scenarios × 19 presets
Handlers:  12 npm + 2 apk + 1 brew + 5 _default + 1 on_failure + 9 INFRA = 30 total
```

---

## 9. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "pnpm"` |
| `data/recipes.py` | Updated `label` to include description |
| `data/recipes.py` | Added `npm` and `apk` install methods |
| `data/recipes.py` | Changed `_default` from `npm install -g` to standalone installer |
| `data/recipes.py` | Changed `requires` from `npm` to `curl` (standalone doesn't need npm) |
| `data/recipes.py` | Added `prefer: ["npm", "brew", "_default"]` |
| `data/recipes.py` | Added `needs_sudo` for all 4 methods |
| `data/recipes.py` | Added `post_env` for PNPM_HOME PATH setup |
| `data/recipes.py` | Added `update.npm` (previously only `_default`) |
| `data/tool_failure_handlers.py` | Added `pnpm_corepack_conflict` handler (3 options) |

---

## 10. Update Derivation

Explicit `update` map provided for npm and brew. Other PM updates
derived by `get_update_map()`:

| PM | Update command | Source |
|----|---------------|--------|
| npm | `npm update -g pnpm` | Explicit |
| brew | `brew upgrade pnpm` | Explicit |
| apk | `apk upgrade pnpm` | Derived |
| _default | N/A (standalone script) | — |

---

## 11. Design Notes

### Why _default is the standalone installer (not npm)
Unlike yarn (which is always installed via npm), pnpm's
`_default` method uses the official standalone installer because:
1. It does not require npm/Node.js pre-installed
2. The script handles OS/arch detection automatically
3. It's the officially recommended installation method
4. It provides a self-contained binary

### Why fewer system PM packages than yarn
Yarn had an official Yarn repo for apt/dnf/zypper. pnpm does not
maintain external package repositories. It relies on:
- npm (universal)
- Alpine community repo (apk)
- Homebrew (brew)
- Standalone installer (_default)

### Corepack
Like yarn, pnpm can also be managed via Corepack (`corepack enable`).
This is a per-project concern. The brew formula conflicts with
corepack — same situation as yarn.
