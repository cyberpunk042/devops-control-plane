# node — Full Spectrum Analysis

> **Tool ID:** `node`
> **Last audited:** 2026-02-26
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Node.js — JavaScript runtime built on Chrome V8 engine |
| Language | C++ (V8 engine) + C (libuv) |
| CLI binary | `node` |
| Category | `language` |
| Verify command | `node --version` |
| Recipe key | `node` |

### Special notes
- Node.js includes `npm` (package manager) and `npx` (package runner) in
  the official binary distribution, but system packages (apt/dnf/apk/pacman)
  often package `npm` separately — the recipe accounts for this.
- The `_default` method downloads the pre-compiled LTS binary from nodejs.org
  which includes both `node` and `npm`.
- Node.js has a version constraint of `>= 18.0.0` — this ensures modern ESM
  (`import`/`export`), `fetch()`, and other features are available.
- Binary naming uses **x64** and **arm64** (not x86_64/aarch64) — handled via
  `arch_map` in the recipe.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `snap` | ✅ | `node` | `--classic` required, provides near-latest |
| `apt` | ✅ | `nodejs` | Debian 12 ships v18, may lag |
| `dnf` | ✅ | `nodejs` | Fedora ships current, RHEL via AppStream |
| `apk` | ✅ | `nodejs` + `npm` | Alpine, npm packaged separately |
| `pacman` | ✅ | `nodejs` + `npm` | Arch, npm packaged separately |
| `zypper` | ✅ | `nodejs20` | openSUSE uses versioned packages |
| `brew` | ✅ | `node` | macOS/Linux Homebrew, always current |
| `pip` | ❌ | — | Not available |
| `npm` | ❌ | — | Circular — npm requires node |
| `cargo` | ❌ | — | Not available |

### Package name notes
- **apt/dnf/apk/pacman:** Package is `nodejs`, differs from CLI binary `node`
- **zypper:** Uses versioned packages (`nodejs16`, `nodejs20`, `nodejs22`).
  Recipe uses `nodejs20` to match LTS.
- **apk/pacman:** The `npm` binary is packaged separately, so both
  `nodejs` + `npm` are installed.
- **brew/snap:** Package provides both node and npm in a single install.

---

## 3. Binary Download (_default)

`_default` is an **OS-variant dict** (Evolution: OS & Arch Awareness).
Each OS has its own command because the archive formats differ.

| Field | Linux | macOS |
|-------|-------|-------|
| URL pattern | `node-v{VER}-linux-{arch}.tar.xz` | `node-v{VER}-darwin-{arch}.tar.gz` |
| Archive format | `.tar.xz` (`tar -xJf`) | `.tar.gz` (`tar -xzf`) |
| Contents | `bin/node`, `bin/npm`, `bin/npx`, `lib/node_modules/` | Same |
| Install location | `/usr/local/` (via `--strip-components=1`) | Same |
| Dependencies | `curl` (download), `python3` (version detection) | Same |
| needs_sudo | Yes (writes to `/usr/local/`) | Yes |

### Architecture naming
Node.js uses its own naming convention for architectures:

| uname -m | Node.js name | Handled by |
|----------|-------------|------------|
| `x86_64` | `x64` | `arch_map` |
| `aarch64` | `arm64` | `arch_map` |
| `armv7l` | `armv7l` | `arch_map` (Raspbian) |

**Raspbian note:** The L0 system profiler detects 64-bit kernel + 32-bit
userland via `struct.calcsize("P")` and corrects `aarch64` → `armv7l`
automatically. This prevents downloading an arm64 binary that cannot
execute on 32-bit userland.

### Version resolution
The `_default` command auto-detects the latest LTS version by querying
`https://nodejs.org/dist/index.json` and filtering for entries where
`lts` is truthy. Falls back to `v22.15.0` if the query fails.

### Why binary download as _default?
Unlike Python, Node.js publishes **pre-compiled binaries** for all major
platforms. No build step needed. The binary archive includes everything:
node, npm, npx, and core modules. This is faster and more reliable than
building from source.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For `_default` install method |
| Download | `python3` | For LTS version detection (optional, has fallback) |
| Runtime | None | Self-contained once installed |

### Reverse deps
Node.js is a dependency for many tools installed via npm:
- `eslint`, `prettier`, `typescript`, `webpack`, `vite`, `nextjs`,
  `express`, `pm2`, `nodemon`, `pnpm`, `yarn`, `nx`, `lerna`,
  `storybook`, `docusaurus`, and many more
- The `npm` tool recipe also depends on node being installed

---

## 5. Failure Surface

### 5.1 Per-install-method failures (Layer 2)
All PM-based install methods have dedicated METHOD_FAMILY_HANDLERS:

| PM | Handlers | IDs |
|----|---------|-----|
| `snap` | Snapd not running | `snapd_unavailable` |
| `apt` | Stale index, DB locked | `apt_stale_index`, `apt_locked` |
| `dnf` | Package not found | `dnf_no_match` |
| `apk` | Unsatisfiable, DB locked | `apk_unsatisfiable`, `apk_locked` |
| `pacman` | Target not found, DB locked | `pacman_target_not_found`, `pacman_locked` |
| `zypper` | Not found, PM locked | `zypper_not_found`, `zypper_locked` |
| `brew` | Formula not found | `brew_no_formula` |
| `_default` | Missing curl/git/wget/unzip/npm | 5 dependency handlers |

### 5.2 Tool-specific failures (Layer 3 on_failure)

| ID | Category | Pattern matches | Remediation |
|----|----------|----------------|-------------|
| `node_glibc_too_old` | environment | `GLIBC_2.XX not found`, `libc.so.6 version not found` | Switch to PM install, upgrade OS, or use unofficial builds |
| `node_version_too_old` | environment | `SyntaxError: Unexpected token '?'`, `ERR_REQUIRE_ESM`, `ERR_UNKNOWN_FILE_EXTENSION`, engine incompatible | Install LTS from nodejs.org, snap, or nvm |
| `node_npm_not_found` | dependency | `npm: command not found`, `npm: not found` | Install npm via PM, or reinstall from nodejs.org (bundled) |
| `node_musl_incompatible` | environment | `ld-linux not found`, `error loading shared libraries ld-linux` | Install via apk (Alpine-native), or install libc6-compat shim |

---

## 6. Handler Layers

### Layer 1: INFRA_HANDLERS (existing)
9 cross-tool handlers apply. No changes needed.

### Layer 2: METHOD_FAMILY_HANDLERS
- `snap` family: 1 handler — existing
- `apt` family: 2 handlers — existing
- `dnf` family: 1 handler — existing
- `apk` family: 2 handlers — existing
- `pacman` family: 2 handlers — existing
- `zypper` family: 2 handlers — existing
- `brew` family: 1 handler — existing
- `_default` family: 5 handlers — existing

### Layer 3: Recipe on_failure (TOOL_FAILURE_HANDLERS)
4 handlers:
- `node_glibc_too_old` — environment — 3 options
- `node_version_too_old` — environment — 3 options
- `node_npm_not_found` — dependency — 2 options
- `node_musl_incompatible` — environment — 2 options

---

## 7. Install Method Preference

```
prefer: ["_default", "snap", "brew"]
```

**Rationale:**
1. `_default` — Pre-compiled binary from nodejs.org. Always latest LTS.
   Includes node + npm + npx in a single download. Most reliable.
2. `snap` — Canonical-maintained, near-latest versions. `--classic`
   gives full filesystem access.
3. `brew` — Homebrew provides current versions immediately.
4. System PMs (apt/dnf/apk/pacman/zypper) — Distro-maintained. May lag
   behind significantly (Debian ships 18.x, Ubuntu 22.04 ships 18.x).

---

## 8. Version Constraint

```python
"version_constraint": {
    "type": "gte",
    "reference": "18.0.0",
    "description": "Node.js 18+ required for modern ESM and fetch support.",
}
```

Node.js 18 was the LTS version that introduced:
- Native `fetch()` API (no more `node-fetch` dependency)
- Stable ES Module support
- Test runner (`node:test`)
- Improved `import.meta.resolve()`

Versions below 18 are EOL and will not work with modern npm packages.

---

## 9. Recipe Data

```python
"node": {
    "label": "Node.js",
    "cli": "node",
    "category": "language",
    "install": {
        "snap":    ["snap", "install", "node", "--classic"],
        "apt":     ["apt-get", "install", "-y", "nodejs"],
        "dnf":     ["dnf", "install", "-y", "nodejs"],
        "apk":     ["apk", "add", "nodejs", "npm"],
        "pacman":  ["pacman", "-S", "--noconfirm", "nodejs", "npm"],
        "zypper":  ["zypper", "install", "-y", "nodejs20"],
        "brew":    ["brew", "install", "node"],
        "_default": [...],  # Binary download from nodejs.org
    },
    "needs_sudo": {
        "snap": True, "apt": True, "dnf": True,
        "apk": True, "pacman": True, "zypper": True,
        "brew": False, "_default": True,
    },
    "prefer": ["_default", "snap", "brew"],
    "requires": {"binaries": ["curl"]},
    "arch_map": {"x86_64": "x64", "aarch64": "arm64", "armv7l": "armv7l"},
    "version_constraint": {...},
    "verify": ["node", "--version"],
    # _default is an OS-variant dict with linux and darwin keys
    # update: derived by get_update_map() for PM methods
}
```

---

## 10. Validation Results

```
Schema:    VALID (recipe + on_failure handlers)
Coverage:  551/551 (100%) — 29 scenarios × 19 presets
Handlers:  1 snap + 15 PM-family + 5 _default + 4 on_failure + 9 INFRA = 29 total
```

---

## 11. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "node"` |
| `data/recipes.py` | Added `category: "language"` |
| `data/recipes.py` | Added `zypper` install method (`nodejs20`) |
| `data/recipes.py` | Added `_default` install (binary from nodejs.org) |
| `data/recipes.py` | Evolved `_default` to OS-variant dict (linux + darwin) |
| `data/recipes.py` | Added `_default` and `zypper` to `needs_sudo` |
| `data/recipes.py` | Added `requires` with `curl` binary dependency |
| `data/recipes.py` | Added `arch_map` for Node.js x64/arm64/armv7l naming |
| `data/recipes.py` | Updated `prefer` to `["_default", "snap", "brew"]` |
| `data/recipes.py` | Added `npm` to `apk` and `pacman` install lists |
| `data/recipes.py` | Removed explicit `update` (now derived by Evolution D) |
| `resolver/dynamic_dep_resolver.py` | Updated KNOWN_PACKAGES `node.zypper` from `nodejs16` to `nodejs20` |
| `resolver/method_selection.py` | Handle `_default` as `dict\|list` with OS gating |
| `resolver/plan_resolution.py` | Extract OS-specific command from dict `_default` |
| `execution/build_helpers.py` | Added `{os}` variable, Raspbian userland detection |
| `audit/l0_detection.py` | Raspbian 64-bit kernel + 32-bit userland detection |
| `data/tool_failure_handlers.py` | Added `node_glibc_too_old` handler (3 options) |
| `data/tool_failure_handlers.py` | Added `node_version_too_old` handler (3 options) |
| `data/tool_failure_handlers.py` | Added `node_npm_not_found` handler (2 options) |
| `data/tool_failure_handlers.py` | Added `node_musl_incompatible` handler (2 options) |

---

## 12. Update Derivation

Node has no explicit `update` map. Evolution D's `get_update_map()` derives
PM update commands automatically:

| PM | Derived update command |
|----|----------------------|
| snap | `snap refresh node` |
| apt | `apt-get install --only-upgrade -y nodejs` |
| dnf | `dnf upgrade -y nodejs` |
| apk | `apk upgrade nodejs npm` |
| pacman | `pacman -S --noconfirm nodejs npm` |
| zypper | `zypper update -y nodejs20` |
| brew | `brew upgrade node` |
| _default | Not derivable (binary download) |
