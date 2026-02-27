# yarn — Full Spectrum Analysis

> **Tool ID:** `yarn`
> **Last audited:** 2026-02-26
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Yarn — JavaScript package manager |
| Language | JavaScript |
| CLI binary | `yarn` |
| Category | `node` |
| Verify command | `yarn --version` |
| Recipe key | `yarn` |

### Special notes
- Yarn is itself a package manager for the Node.js ecosystem.
- **Yarn Classic** (1.x) is what system package managers provide.
  **Yarn Berry** (2+/4+) is managed per-project via Corepack.
- Our recipe installs Yarn Classic globally. Yarn Berry is a
  per-project concern, not a system install.
- The `_default` method and `npm` method are identical: both use
  `npm install -g yarn`. npm is the universal install path.
- **apt/dnf/zypper** all require adding external Yarn repositories
  first — the system repos don't include yarn by default. This makes
  `npm` the most reliable installation method.
- The brew formula **conflicts with corepack**. If corepack is
  installed via brew, `brew install yarn` will fail.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `npm` | ✅ | `yarn` | Primary install method |
| `apt` | ✅ | `yarn` | Requires Yarn apt repo (dl.yarnpkg.com) |
| `dnf` | ✅ | `yarnpkg` | Fedora, requires Yarn repo |
| `apk` | ✅ | `yarn` | Alpine community repo |
| `pacman` | ✅ | `yarn` | Arch extra repo |
| `zypper` | ✅ | `yarn` | openSUSE, requires Yarn repo |
| `brew` | ✅ | `yarn` | Conflicts with corepack formula |
| `snap` | ⚠️ | N/A | No standalone snap; bundled in `node` snap |
| `pip` | ❌ | — | Not available |
| `cargo` | ❌ | — | Not available |

### Package name notes
- **dnf:** Package is `yarnpkg` (not `yarn`). Recorded in
  `KNOWN_PACKAGES`.
- **apt:** Package name matches CLI (`yarn`), but requires adding
  the Yarn Debian repository and GPG key first. Note: Debian has
  a `cmdtest` package that also provides a `yarn` binary — adding
  the Yarn repo resolves this conflict.

---

## 3. Install Method — _default

| Field | Value |
|-------|-------|
| Command | `npm install -g yarn` |
| Archive format | N/A — installed via npm |
| Install location | npm global prefix (typically `~/.npm-global/` or `/usr/lib/node_modules/`) |
| Dependencies | `npm` (and therefore `node`) |
| needs_sudo | No (npm global installs to user prefix) |

### No binary download
Yarn does not publish standalone platform-specific binaries.
It is a JavaScript package, always installed through npm or a
system package manager. No `{os}/{arch}` placeholders are needed.

### Platform coverage
Because yarn is installed via npm (which is a JS runtime, not
a native binary), it works on any platform where Node.js runs:
- Linux x86_64 ✅
- Linux aarch64 ✅
- Linux armv7l (Raspbian) ✅
- macOS Intel ✅
- macOS Apple Silicon ✅

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Runtime | `npm` | Required for `_default` and `npm` methods |
| Runtime | `node` | Required by npm (transitive) |

### Reverse deps
Yarn is commonly used as a dependency by:
- Many JavaScript/TypeScript projects
- Monorepo setups (Yarn workspaces)
- CI/CD pipelines

---

## 5. Post-install

No additional PATH or shell configuration needed when installed
via npm. The `yarn` binary is placed in npm's global bin directory,
which should already be on PATH.

---

## 6. Failure Handlers

### Layer 1: method-family handlers
Because yarn uses `npm` as its primary install method, it inherits
the **full npm handler suite** (12 handlers):

| Handler | Category | Trigger |
|---------|----------|---------|
| `npm_eacces` | permissions | Permission denied |
| `missing_npm` | dependency | npm not installed |
| `npm_eresolve` | dependency | Dependency conflict |
| `npm_node_too_old` | dependency | Node.js version too old |
| `node_gyp_build_fail` | compiler | Native addon build failed |
| `npm_cache_corruption` | environment | Cache corrupted |
| `npm_registry_auth` | network | Registry auth failed |
| `npm_etarget` | dependency | Package version not found |
| `npm_elifecycle` | install | Lifecycle script failed |
| `npm_self_signed_cert` | network | TLS certificate error |
| `npm_ebadplatform` | compatibility | Platform incompatible |
| `npm_enoent` | environment | File/script not found |

Plus system PM handlers for apt, dnf, apk, pacman, zypper, brew.

### Layer 2: INFRA handlers (9 cross-tool)
Network, disk, permissions, OOM, timeout — all standard.

### Layer 3: per-tool on_failure handlers

| Handler | Category | Trigger | Options |
|---------|----------|---------|---------|
| `yarn_cmdtest_conflict` | configuration | `There are no scenarios` / cmdtest | Switch to `npm` (recommended), manual cmdtest removal |
| `yarn_repo_not_configured` | configuration | `Unable to locate package yarn` | Switch to `npm` (recommended), switch to `brew` |
| `yarn_corepack_conflict` | configuration | `Cannot install yarn because conflicting formulae` | Switch to `npm` (recommended), manual corepack unlink |

---

## 7. Recipe Structure

```python
"yarn": {
    "cli": "yarn",
    "label": "Yarn (JavaScript package manager)",
    "category": "node",
    "install": {
        "npm":    ["npm", "install", "-g", "yarn"],
        "apt":    ["apt-get", "install", "-y", "yarn"],
        "dnf":    ["dnf", "install", "-y", "yarnpkg"],
        "apk":    ["apk", "add", "yarn"],
        "pacman": ["pacman", "-S", "--noconfirm", "yarn"],
        "zypper": ["zypper", "install", "-y", "yarn"],
        "brew":   ["brew", "install", "yarn"],
        "_default": ["npm", "install", "-g", "yarn"],
    },
    "needs_sudo": {
        "npm": False, "apt": True, "dnf": True,
        "apk": True, "pacman": True, "zypper": True,
        "brew": False, "_default": False,
    },
    "prefer": ["npm", "brew", "_default"],
    "requires": {"binaries": ["npm"]},
    "verify": ["yarn", "--version"],
    "update": {
        "npm": ["npm", "update", "-g", "yarn"],
        "brew": ["brew", "upgrade", "yarn"],
    },
}
```

---

## 8. Validation Results

```
Schema:    VALID (recipe + all method-family handlers + on_failure)
Coverage:  741/741 (100%) — 39 scenarios × 19 presets
Handlers:  12 npm + 10 PM-family + 5 _default + 3 on_failure + 9 INFRA = 39 total
```

---

## 9. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "yarn"` |
| `data/recipes.py` | Updated `label` to include description |
| `data/recipes.py` | Added `npm`, `apt`, `dnf`, `apk`, `pacman`, `zypper` install methods |
| `data/recipes.py` | Added explicit `npm` method (previously only `_default`) |
| `data/recipes.py` | Added `prefer: ["npm", "brew", "_default"]` |
| `data/recipes.py` | Added `needs_sudo` for all 8 methods |
| `data/recipes.py` | Added `update.npm` (previously only `_default`) |
| `resolver/dynamic_dep_resolver.py` | Added yarn to `KNOWN_PACKAGES` (dnf=yarnpkg) |
| `data/remediation_handlers.py` | Fixed pre-existing npm handler `packages` schema errors (2 occurrences) |
| `data/tool_failure_handlers.py` | Added `yarn_cmdtest_conflict` handler (2 options) |
| `data/tool_failure_handlers.py` | Added `yarn_repo_not_configured` handler (2 options) |
| `data/tool_failure_handlers.py` | Added `yarn_corepack_conflict` handler (2 options) |

---

## 10. Update Derivation

Explicit `update` map provided for npm and brew. Other PM updates
derived by `get_update_map()`:

| PM | Update command | Source |
|----|---------------|--------|
| npm | `npm update -g yarn` | Explicit |
| brew | `brew upgrade yarn` | Explicit |
| apt | `apt-get install --only-upgrade -y yarn` | Derived |
| dnf | `dnf upgrade -y yarnpkg` | Derived |
| apk | `apk upgrade yarn` | Derived |
| pacman | `pacman -S --noconfirm yarn` | Derived |
| zypper | `zypper update -y yarn` | Derived |
| _default | N/A (same as npm) | — |

---

## 11. Design Notes

### Why `_default` and `npm` are the same command
Yarn is a JavaScript package — it has no standalone binary to
download. `npm install -g yarn` is the universal method. We keep
both `npm` (explicit method) and `_default` (fallback) pointing
to the same command so that:
1. When npm is detected as available, the `npm` method is selected
2. If method selection falls through to `_default`, it still works

### Why prefer npm over system PMs
System package managers (apt, dnf, zypper) require adding the
Yarn repository first. Without it, `apt-get install yarn` fails
because yarn isn't in default repos. Using npm avoids this repo
configuration step entirely.

### Yarn Berry / Corepack
This recipe installs Yarn Classic (1.x) globally. For Yarn Berry
(2+/4+), the recommended approach is:
```bash
corepack enable
yarn set version stable
```
This is a per-project concern, not a system-level install.
