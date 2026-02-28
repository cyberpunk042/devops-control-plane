# air — Full Spectrum Analysis

> **Tool ID:** `air`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | air — Go live reload for development |
| Language | Go |
| Author | air-verse (cosmtrek) |
| CLI binary | `air` |
| Category | `go` |
| Verify command | `air -v` |
| Recipe key | `air` |

### Special notes
- Live reload for Go applications during development.
- Watches `.go` files for changes, rebuilds and restarts automatically.
- Configurable via `.air.toml` — supports custom build commands, watch paths, colors.
- Alternative to `reflex`, `realize`, or manual `go run` loops.
- Written in Go — installed exclusively via `go install`.
- NOT available in any system package manager or brew.
- Installs to `$HOME/go/bin` — requires PATH addition.
- Verify flag is `-v` (not `--version`).

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora repos |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ❌ | — | Not in Arch repos |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ❌ | — | Not in Homebrew |
| `go` | ✅ | `github.com/air-verse/air@latest` | **Only method** |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Any with Go | `go install github.com/air-verse/air@latest` | _default (go) |

### _default method (go install)
```bash
go install github.com/air-verse/air@latest
```
- **No sudo needed** — installs to `$HOME/go/bin`.
- `install_via: go`.

### Post-install
```bash
export PATH="$HOME/go/bin:$PATH"
```

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Runtime | `go` | Go 1.18+ toolchain required |

No C library dependencies — pure Go binary.

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (8 total)
| Family | Handlers |
|--------|----------|
| `_default` | 5 (missing curl/git/wget/unzip/npm) |
| `go` | 3 (go not installed, GOPATH, module download) |

### Layer 1: INFRA handlers (9 cross-tool)
All standard — network, disk, permissions, OOM, timeout.

### Layer 3: None needed.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  323/323 (100%) — 17 scenarios × 19 presets
Handlers:  8 method-specific + 9 INFRA = 17
```

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "air"` |
| `data/recipes.py` | Updated label to "Go live reload for development" |
| `data/recipes.py` | Added `update` command |
| `data/recipes.py` | Added research comments |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | _default (go) | Requires Go toolchain |
| **Debian/Ubuntu** | _default (go) | Not in apt |
| **Fedora/RHEL** | _default (go) | Not in dnf |
| **Alpine** | _default (go) | Not in apk |
| **Arch** | _default (go) | Not in pacman |
| **openSUSE** | _default (go) | Not in zypper |
| **Any with Go** | _default (go) | Universal — only method |

No native PM coverage. Standard Go ecosystem pattern.
