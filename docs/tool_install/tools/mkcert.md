# mkcert — Full Spectrum Analysis

> **Tool ID:** `mkcert`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | mkcert — local TLS certificate authority |
| Language | Go |
| Author | Filippo Valsorda (FiloSottile) |
| CLI binary | `mkcert` |
| Category | `network` |
| Verify command | `mkcert --version` |
| Recipe key | `mkcert` |

### Special notes
- Written in Go — single static binary.
- Creates locally-trusted development certificates (no config needed).
- Automatically installs a local CA in the system trust store.
- `libnss3-tools` (certutil) recommended for Firefox/Chrome trust stores
  but not strictly required for basic cert generation.
- GitHub releases use `amd64`/`arm64` (NOT `x86_64`/`aarch64`).
- `arch_map` translates `uname -m` → GitHub naming convention.
- NOT in apt, dnf, zypper, snap.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora repos |
| `apk` | ✅ | `mkcert` | Alpine community |
| `pacman` | ✅ | `mkcert` | Arch community repo |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `mkcert` | **Preferred** |
| `snap` | ❌ | — | Not available |
| `_default` | ✅ | — | GitHub release binary |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| macOS/Linux (preferred) | `brew install mkcert` | brew |
| Arch Linux | `pacman -S mkcert` | pacman |
| Alpine | `apk add mkcert` | apk |
| Any Linux (fallback) | GitHub release download | _default |

### brew method (preferred)
```bash
brew install mkcert
```

### pacman method (Arch)
```bash
sudo pacman -S --noconfirm mkcert
```

### apk method (Alpine)
```bash
apk add --no-cache mkcert
```

### _default method (GitHub release)
```bash
curl -sSfL -o /usr/local/bin/mkcert \
  https://github.com/FiloSottile/mkcert/releases/latest/download/mkcert-$(uname -s)-{arch} \
  && chmod +x /usr/local/bin/mkcert
```
- **Needs sudo** — writes to `/usr/local/bin`.
- `{arch}` resolved via `arch_map`: x86_64→amd64, aarch64→arm64.
- `$(uname -s)` resolves OS at runtime (Linux, Darwin).
- `install_via: github_release` — triggers release handlers.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For _default method |
| Optional | `libnss3-tools` | For browser trust store integration |

No C library dependencies — self-contained Go binary.

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (13 total)
| Family | Handlers |
|--------|----------|
| `brew` | 1 (no formula) |
| `pacman` | 2 (not found, db locked) |
| `apk` | 2 (not found, db locked) |
| `_default` | 5 (missing curl/git/wget/unzip/npm) |
| `github_release` | 3 (rate limit, asset not found, extract failed) |

### Layer 1: INFRA handlers (9 cross-tool)
All standard — network, disk, permissions, OOM, timeout.

### Layer 3: None needed.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  418/418 (100%) — 22 scenarios × 19 presets
Handlers:  13 method-specific + 9 INFRA = 22
```

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "mkcert"` |
| `data/recipes.py` | Updated label to "mkcert (local TLS certificate authority)" |
| `data/recipes.py` | **Fixed hardcoded `amd64`** → `{arch}` with `arch_map` |
| `data/recipes.py` | Removed platform dict — single _default list |
| `data/recipes.py` | Added `pacman` install method |
| `data/recipes.py` | Added `apk` install method |
| `data/recipes.py` | Added `arch_map: {x86_64→amd64, aarch64→arm64}` |
| `data/recipes.py` | Added `prefer: ["brew", "pacman", "apk"]` |
| `data/recipes.py` | Added `update` for all methods |
| `data/recipes.py` | Added research comments |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | **Preferred** — formula `mkcert` |
| **Linux with brew** | brew | Linuxbrew supported |
| **Arch Linux** | pacman | Community repo ✅ |
| **Alpine** | apk | Community repo ✅ |
| **Debian/Ubuntu** | _default | GitHub release binary |
| **Fedora/RHEL** | _default | GitHub release binary |
| **openSUSE** | _default | GitHub release binary |
| **Raspbian (aarch64)** | _default | `arch_map` → arm64 ✅ |
| **WSL** | brew or _default | Standard methods |

brew preferred. pacman for Arch, apk for Alpine.
GitHub release binary with `arch_map` as universal fallback.
