# delve — Full Spectrum Analysis

> **Tool ID:** `delve`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | delve — Go debugger |
| Language | Go |
| CLI binary | `dlv` (**not** `delve`) |
| Category | `go` |
| Verify command | `dlv version` |
| Recipe key | `delve` |

### Special notes
- The standard Go debugger — used by VS Code, GoLand, Vim/Neovim.
- **Binary name mismatch**: recipe key is `delve` but CLI binary is `dlv`.
- Supports breakpoints, goroutine inspection, variable evaluation, core dumps.
- Written in Go — installed exclusively via `go install`.
- NOT available in any system package manager or brew.
- Installs to `$HOME/go/bin` — requires PATH addition.

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
| `go` | ✅ | `github.com/go-delve/delve/cmd/dlv@latest` | **Only method** |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Any with Go | `go install github.com/go-delve/delve/cmd/dlv@latest` | _default (go) |

### _default method (go install)
```bash
go install github.com/go-delve/delve/cmd/dlv@latest
```
- **No sudo needed** — installs to `$HOME/go/bin`.
- Binary name: `dlv` (not `delve`).
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
| `data/recipes.py` | Moved `cli: "dlv"` to top of recipe |
| `data/recipes.py` | Updated label to "Go debugger — dlv" |
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
