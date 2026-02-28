# cdktf — Full Spectrum Analysis

> **Tool ID:** `cdktf`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)
> **⚠️ DEPRECATED:** Archived by HashiCorp on December 10, 2025.

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | CDK for Terraform — infrastructure as code with programming languages |
| Language | TypeScript |
| Author | HashiCorp |
| CLI binary | `cdktf` |
| Category | `iac` |
| Verify command | `cdktf --version` |
| Recipe key | `cdktf` |

### Special notes
- Written in TypeScript — requires Node.js runtime.
- **⚠️ DEPRECATED** — HashiCorp archived CDKTF on December 10, 2025.
  No further updates, fixes, or compatibility patches. Use at own risk.
  Consider migrating to Terraform HCL or Pulumi.
- Allows writing Terraform infrastructure in Python, TypeScript, Go, C#, Java
  instead of HCL.
- npm package name is `cdktf-cli` (not `cdktf`). brew formula is `cdktf`.
- **Runtime dependency**: requires `terraform` CLI (>= 1.2.0) at runtime.
- Does NOT need sudo for either install method.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora repos |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ❌ | — | Not in Arch repos |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `cdktf` | **Preferred** |
| `snap` | ❌ | — | Not available |
| `npm` (_default) | ✅ | `cdktf-cli` | Global install |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| macOS/Linux (preferred) | `brew install cdktf` | brew |
| Any with Node.js (fallback) | `npm install -g cdktf-cli` | npm (_default) |

### brew method (preferred)
```bash
brew install cdktf
```

### _default method (npm)
```bash
npm install -g cdktf-cli
```
- **Does NOT need sudo** — npm global installs to user prefix.
- Requires Node.js and npm on PATH.
- `install_via: npm` — triggers the full npm family handler set (12 handlers).

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Runtime | `terraform` | Must be >= 1.2.0. Required to synthesize/deploy |
| Runtime | `npm` / `node` | For _default install method |
| Runtime | Language SDK | Python, Node.js, Go, C#, or Java for CDKTF programs |

The `terraform` CLI must be installed separately — it is a runtime dependency of
cdktf, not an install-time dependency.

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (18 total)
| Family | Handlers |
|--------|----------|
| `brew` | 1 (no formula) |
| `_default` | 5 (missing curl/git/wget/unzip/npm) |
| `npm` | 12 (permission denied, dep conflict, Node.js too old, node-gyp, cache corrupt, auth failed, version not found, lifecycle script, TLS, platform incompat, file not found, npm not installed) |

### Layer 1: INFRA handlers (9 cross-tool)
All standard — network, disk, permissions, OOM, timeout.

### Layer 3: None needed.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  513/513 (100%) — 27 scenarios × 19 presets
Handlers:  18 method-specific + 9 INFRA = 27
```

Higher scenario count than simple tools because the npm method family has
12 dedicated handlers covering Node.js-specific failure patterns.

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "cdktf"` |
| `data/recipes.py` | Updated label with description |
| `data/recipes.py` | Added brew method (`brew install cdktf`) |
| `data/recipes.py` | Added `prefer: ["brew"]` |
| `data/recipes.py` | Added brew `update` |
| `data/recipes.py` | Added research comments (including deprecation notice) |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | **Preferred** — formula `cdktf` ✅ |
| **Linux with brew** | brew | Linuxbrew supported ✅ |
| **Debian/Ubuntu** | _default (npm) | Needs Node.js installed |
| **Fedora/RHEL** | _default (npm) | Needs Node.js installed |
| **Alpine** | _default (npm) | Needs Node.js installed |
| **Arch Linux** | _default (npm) | Needs Node.js installed |
| **openSUSE** | _default (npm) | Needs Node.js installed |
| **Raspbian** | _default (npm) | Needs Node.js installed |
| **WSL** | brew or npm | Standard methods |

brew preferred where available. npm as universal fallback — requires
Node.js/npm on PATH. If npm not installed, handler suggests installing
Node.js first via the `install_dep` strategy.

**Note**: This tool is deprecated. Consider Pulumi or Terraform HCL instead.
