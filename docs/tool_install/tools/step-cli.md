# step-cli — Full Spectrum Analysis

> **Tool ID:** `step-cli`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | step CLI — Smallstep certificate authority toolkit |
| Language | Go |
| Author | Smallstep Labs |
| CLI binary | `step` |
| Category | `crypto` |
| Verify command | `step --version` |
| Recipe key | `step-cli` |

### Special notes
- **Binary name mismatch**: recipe key is `step-cli` but CLI binary is `step`.
- Written in Go — single static binary.
- Zero-trust PKI, ACME, SSH certificates, certificate management.
- GitHub releases provide `.tar.gz`, `.deb`, and `.rpm` formats.
  We use `.tar.gz` for cross-platform compatibility.
- Uses `amd64`/`arm64` in asset names — `arch_map` translates from `uname -m`.
- NOT in apt, dnf, apk, pacman (standard), zypper, snap.
- AUR has `step-cli` but that requires `yay`, not standard `pacman -S`.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora repos |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ❌ | — | AUR only (yay) — not standard |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `step` | **Preferred** |
| `snap` | ❌ | — | Not available |
| `_default` | ✅ | — | GitHub release tar.gz |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| macOS/Linux (preferred) | `brew install step` | brew |
| Any Linux (fallback) | GitHub release tar.gz | _default |

### brew method (preferred)
```bash
brew install step
```

### _default method (GitHub release)
```bash
curl -sSfL https://github.com/smallstep/cli/releases/latest/download/step_linux_{arch}.tar.gz \
  | sudo tar -xz -C /usr/local/bin --strip-components=2 step/bin/step
```
- **Needs sudo** — writes to `/usr/local/bin`.
- `{arch}` resolved via `arch_map`: x86_64→amd64, aarch64→arm64.
- `install_via: github_release` — triggers release handlers.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For _default method |

No C library dependencies — self-contained Go binary.

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (9 total)
| Family | Handlers |
|--------|----------|
| `brew` | 1 (no formula) |
| `_default` | 5 (missing curl/git/wget/unzip/npm) |
| `github_release` | 3 (rate limit, asset not found, extract failed) |

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
| `data/recipes.py` | Updated label to full description |
| `data/recipes.py` | **Fixed hardcoded `amd64.deb`** → cross-platform tar.gz with `{arch}` |
| `data/recipes.py` | Removed Debian-only dpkg install — now works everywhere |
| `data/recipes.py` | Added `arch_map: {x86_64→amd64, aarch64→arm64}` |
| `data/recipes.py` | Added `prefer: ["brew"]` |
| `data/recipes.py` | Added `update` for both methods |
| `data/recipes.py` | Added research comments |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | **Preferred** — formula `step` |
| **Linux with brew** | brew | Linuxbrew supported |
| **Debian/Ubuntu** | _default | tar.gz (was .deb — now cross-platform) |
| **Fedora/RHEL** | _default | tar.gz works everywhere |
| **Alpine** | _default | tar.gz works everywhere |
| **Arch Linux** | _default | AUR has it but tar.gz is simpler |
| **openSUSE** | _default | tar.gz works everywhere |
| **Raspbian (aarch64)** | _default | `arch_map` → arm64 ✅ |
| **WSL** | brew or _default | Standard methods |

brew preferred. GitHub release tar.gz as universal fallback.
Cross-platform fix: was Debian-only .deb, now works on all Linux.
