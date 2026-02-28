# snyk — Full Spectrum Analysis

> **Tool ID:** `snyk`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Snyk CLI — security vulnerability scanner |
| Language | Node.js/TypeScript |
| CLI binary | `snyk` |
| Category | `security` |
| Verify command | `snyk --version` |
| Recipe key | `snyk` |

### Special notes
- Scans dependencies, containers, IaC, and code for vulnerabilities.
- **Node.js tool** — canonical install via npm.
- Also provides **standalone binaries** from Snyk CDN (no npm needed):
  `https://static.snyk.io/cli/latest/snyk-linux`, `snyk-linux-arm64`
- brew formula name is `snyk-cli` (**not** `snyk`!).
- Requires a Snyk account/token for most operations.
- NOT available in any system PM (apt, dnf, apk, pacman, zypper, snap).

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `npm` | ✅ | `snyk` | **Official/canonical** install method |
| `brew` | ✅ | `snyk-cli` | Note: `snyk-cli`, not `snyk`! |
| `apt` | ❌ | — | Not available |
| `dnf` | ❌ | — | Not available |
| `apk` | ❌ | — | Not available |
| `pacman` | ❌ | — | Not available |
| `zypper` | ❌ | — | Not available |
| `snap` | ❌ | — | Not available |
| `pip` | ❌ | — | Not available |

---

## 3. Installation (_default via npm)

| Field | Value |
|-------|-------|
| Method | `npm install -g snyk` |
| Install location | Global npm prefix (`/usr/local/lib/node_modules/` or `~/.npm-global/`) |
| Dependencies | `npm` (requires Node.js) |
| needs_sudo | No (user-level npm with proper prefix config) |
| install_via | `npm` |

### Standalone binary alternative
Snyk also provides standalone binaries from their CDN:
```
https://static.snyk.io/cli/latest/snyk-linux        (x86_64)
https://static.snyk.io/cli/latest/snyk-linux-arm64   (ARM64)
https://static.snyk.io/cli/latest/snyk-macos         (x86_64)
https://static.snyk.io/cli/latest/snyk-macos-arm64   (ARM64)
```
These don't require npm/Node.js but need manual updates.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Runtime | `npm` / `node` | For `_default` install method |
| Runtime | Snyk token | Required for scanning (free tier available) |

---

## 5. Post-install

When installed via npm, binary goes to npm's global bin directory.
When installed via brew, binary goes to Homebrew's bin path.

---

## 6. Failure Handlers

### Layer 2b: install_via family (npm)
| Handler | Category | Trigger |
|---------|----------|---------|
| `npm_eacces` | permissions | npm permission denied |
| `missing_npm` | dependency | npm not installed |
| `npm_eresolve` | dependency | npm dependency conflict |
| `npm_node_too_old` | dependency | Node.js version too old |
| `node_gyp_build_fail` | compiler | Native addon build failed |
| `npm_cache_corruption` | environment | npm cache corrupted |
| `npm_registry_auth` | network | Registry authentication failed |
| `npm_etarget` | dependency | Package version not found |
| `npm_elifecycle` | install | Lifecycle script failed |
| `npm_self_signed_cert` | network | TLS certificate error |
| `npm_ebadplatform` | compatibility | Package incompatible with platform |
| `npm_enoent` | environment | File or script not found |

### Layer 2a: method-family handlers (shared)
| Family | Handler | Trigger |
|--------|---------|---------|
| `brew` | `brew_no_formula` | Formula not found |
| `_default` | `missing_curl` | curl not installed |
| `_default` | `missing_git` | git not installed |
| `_default` | `missing_wget` | wget not installed |
| `_default` | `missing_unzip` | unzip not installed |
| `_default` | `missing_npm_default` | npm not installed |

### Layer 1: INFRA handlers (9 cross-tool)
Network, disk, permissions, OOM, timeout — all standard.

### Layer 3: per-tool on_failure handlers
None needed. Standard npm install + brew.

---

## 7. Recipe Structure

```python
"snyk": {
    "cli": "snyk",
    "label": "Snyk CLI (security vulnerability scanner)",
    "category": "security",
    "install": {
        "_default": ["npm", "install", "-g", "snyk"],
        "brew":    ["brew", "install", "snyk-cli"],
    },
    "needs_sudo": {"_default": False, "brew": False},
    "install_via": {"_default": "npm"},
    "requires": {"binaries": ["npm"]},
    "prefer": ["brew"],
    "verify": ["snyk", "--version"],
    "update": {
        "_default": ["npm", "update", "-g", "snyk"],
        "brew":    ["brew", "upgrade", "snyk-cli"],
    },
}
```

---

## 8. Validation Results

```
Schema:    VALID (recipe + all method-family handlers)
Coverage:  513/513 (100%) — 27 scenarios × 19 presets
Handlers:  5 _default + 1 brew + 12 npm + 9 INFRA = 27 total
```

---

## 9. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "snyk"` |
| `data/recipes.py` | Updated label to `"Snyk CLI (security vulnerability scanner)"` |
| `data/recipes.py` | Added `prefer: ["brew"]` |
| `data/recipes.py` | Added evolution comments documenting CDN binary availability |

---

## 10. Future Enhancements

- **Standalone binary method**: Could add CDN binary download as
  an alternative `_default` for systems without npm/Node.js.
- **Token management**: Could detect/prompt for Snyk auth token
  after installation (`snyk auth`).
