# caddy — Full Spectrum Analysis

> **Tool ID:** `caddy`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Caddy — automatic HTTPS web server |
| Language | Go |
| Author | Matt Holt / Caddy project |
| CLI binary | `caddy` |
| Category | `network` |
| Verify command | `caddy version` |
| Recipe key | `caddy` |

### Special notes
- Written in Go — single static binary.
- Automatic TLS with Let's Encrypt — zero-config HTTPS.
- **Verify uses `caddy version`** — NOT `caddy --version`.
- brew: `caddy`. pacman: `caddy` (Arch community). apk: `caddy` (Alpine).
- dnf: `caddy` (Fedora has it natively, RHEL/CentOS via COPR).
- **apt**: NOT in default Debian/Ubuntu repos — needs official Caddy repo
  setup (apt-key + sources.list). Too complex → omitted.
- **zypper**: Available via OBS but not standard — omitted.
- **OLD `getcaddy.com` script is for Caddy v1** — DO NOT USE.
- GitHub releases: `caddy_{ver}_linux_{amd64|arm64}.tar.gz`.
- Uses `amd64`/`arm64` in asset names — `arch_map` translates from `uname -m`.
- NOT in snap.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ⚠️ | `caddy` | Needs repo setup — not used |
| `dnf` | ✅ | `caddy` | Fedora 38+ native |
| `apk` | ✅ | `caddy` | Alpine community |
| `pacman` | ✅ | `caddy` | Arch community repo |
| `zypper` | ⚠️ | `caddy` | OBS only — not used |
| `brew` | ✅ | `caddy` | **Preferred** |
| `snap` | ❌ | — | Not available |
| `_default` | ✅ | — | GitHub release binary |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| macOS/Linux (preferred) | `brew install caddy` | brew |
| Arch Linux | `pacman -S caddy` | pacman |
| Fedora/RHEL | `dnf install caddy` | dnf |
| Alpine | `apk add caddy` | apk |
| Any Linux (fallback) | GitHub release tar.gz | _default |

### brew method (preferred)
```bash
brew install caddy
```

### pacman method (Arch)
```bash
sudo pacman -S --noconfirm caddy
```

### dnf method (Fedora)
```bash
sudo dnf install -y caddy
```

### apk method (Alpine)
```bash
apk add --no-cache caddy
```

### _default method (GitHub release)
Downloads latest release tarball, extracts `caddy` binary to `/usr/local/bin`.
- **Needs sudo** — writes to `/usr/local/bin`.
- Uses GitHub API to resolve latest version tag.
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

### Layer 2a: method-family handlers (14 total)
| Family | Handlers |
|--------|----------|
| `brew` | 1 (no formula) |
| `pacman` | 2 (not found, db locked) |
| `dnf` | 1 (not found) |
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
Coverage:  437/437 (100%) — 23 scenarios × 19 presets
Handlers:  14 method-specific + 9 INFRA = 23
```

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "caddy"` |
| `data/recipes.py` | Updated label to "Caddy (automatic HTTPS web server)" |
| `data/recipes.py` | **Removed broken `getcaddy.com` v1 script** |
| `data/recipes.py` | **Removed `apt`** — not in default repos |
| `data/recipes.py` | Changed `_default` to GitHub release with `{arch}` |
| `data/recipes.py` | Changed `install_via` from `curl_pipe_bash` to `github_release` |
| `data/recipes.py` | Added `apk` install method |
| `data/recipes.py` | Added `arch_map: {x86_64→amd64, aarch64→arm64}` |
| `data/recipes.py` | Added `requires: {binaries: ["curl"]}` |
| `data/recipes.py` | Added `prefer: ["brew", "pacman", "dnf", "apk"]` |
| `data/recipes.py` | Added `update` for all methods |
| `data/recipes.py` | Added research comments |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | **Preferred** — formula `caddy` |
| **Linux with brew** | brew | Linuxbrew supported |
| **Arch Linux** | pacman | Community repo ✅ |
| **Alpine** | apk | Community repo ✅ |
| **Fedora/RHEL** | dnf | Native in Fedora 38+ ✅ |
| **Debian/Ubuntu** | _default | GitHub release (apt needs repo setup) |
| **openSUSE** | _default | OBS available but not used |
| **Raspbian (aarch64)** | _default | `arch_map` → arm64 ✅ |
| **WSL** | brew or _default | Standard methods |

brew preferred. 3 native PMs (pacman, dnf, apk).
GitHub release binary with `arch_map` as universal fallback.
