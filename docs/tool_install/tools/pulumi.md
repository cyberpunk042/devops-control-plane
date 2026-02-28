# pulumi — Full Spectrum Analysis

> **Tool ID:** `pulumi`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Pulumi — infrastructure as code SDK |
| Language | Go (CLI), multi-language SDKs (Python, TypeScript, Go, C#, Java) |
| Author | Pulumi Corporation |
| CLI binary | `pulumi` |
| Category | `iac` |
| Verify command | `pulumi version` (NOT `--version`) |
| Recipe key | `pulumi` |

### Special notes
- Written in Go — CLI ships as pre-compiled binary.
- IaC using **real programming languages** instead of DSLs (unlike Terraform HCL).
  Supports Python, TypeScript/JavaScript, Go, C#, Java, YAML.
- **Verify uses `pulumi version`** — not `--version`. Non-standard.
- Official installer (`get.pulumi.com`) auto-detects OS and architecture at
  runtime — no `{arch}` or `arch_map` needed in recipe.
- Installs to `$HOME/.pulumi/bin` — **no sudo needed** for _default method.
- Requires `post_env` PATH addition for `$HOME/.pulumi/bin`.
- NOT in apt, dnf, apk, pacman (official), zypper, snap.
  AUR has `pulumi-bin` but that's `yay`, not standard `pacman -S`.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora repos |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ❌ | — | AUR only (yay) — not standard |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `pulumi` | **Preferred** |
| `snap` | ❌ | — | Not available |
| `_default` | ✅ | — | Official installer script |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| macOS/Linux (preferred) | `brew install pulumi` | brew |
| Any Linux (fallback) | `curl -fsSL https://get.pulumi.com \| sh` | _default |

### brew method (preferred)
```bash
brew install pulumi
```

### _default method (official installer)
```bash
curl -fsSL https://get.pulumi.com | sh
```
- **Does NOT need sudo** — installs to `$HOME/.pulumi/bin`.
- Auto-detects OS and architecture at runtime.
- `install_via: curl_pipe_bash` — triggers curl-pipe-bash family handlers.
- Requires PATH addition after install: `export PATH="$HOME/.pulumi/bin:$PATH"`

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For _default installer script |
| Runtime | Language SDK | Python, Node.js, Go, .NET, or Java for Pulumi programs |

The Pulumi CLI itself has no runtime dependencies, but Pulumi programs
require the corresponding language runtime installed.

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (9 total)
| Family | Handlers |
|--------|----------|
| `brew` | 1 (no formula) |
| `_default` | 5 (missing curl/git/wget/unzip/npm) |
| `curl_pipe_bash` | 3 (TLS error, unsupported OS/arch, script URL not found) |

### Layer 1: INFRA handlers (9 cross-tool)
All standard — network, disk, permissions, OOM, timeout.

### Layer 3: None needed.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  342/342 (100%) — 18 scenarios × 19 presets
Handlers:  9 method-specific + 9 INFRA = 18
```

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "pulumi"` |
| `data/recipes.py` | Updated label to "Pulumi (infrastructure as code SDK)" |
| `data/recipes.py` | Reordered methods — brew first |
| `data/recipes.py` | Added `prefer: ["brew"]` |
| `data/recipes.py` | Added `update` for both methods |
| `data/recipes.py` | Added research comments |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | **Preferred** — formula `pulumi` ✅ |
| **Linux with brew** | brew | Linuxbrew supported ✅ |
| **Debian/Ubuntu** | _default | `get.pulumi.com` → `$HOME/.pulumi/bin` ✅ |
| **Fedora/RHEL** | _default | Installer auto-detects ✅ |
| **Alpine** | _default | Installer auto-detects ✅ |
| **Arch Linux** | _default | AUR has it but installer is simpler ✅ |
| **openSUSE** | _default | Installer auto-detects ✅ |
| **Raspbian (aarch64)** | _default | Installer auto-detects ARM64 ✅ |
| **WSL** | brew or _default | Standard methods ✅ |

brew preferred where available. Official installer script as universal
fallback — auto-detects OS and arch, installs to user home.
No sudo needed for either method.
