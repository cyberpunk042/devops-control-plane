# gopls — Full Spectrum Analysis

> **Tool ID:** `gopls`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | gopls — official Go language server |
| Language | Go |
| Author | Go team (golang.org/x/tools) |
| CLI binary | `gopls` |
| Category | `go` |
| Verify command | `gopls version` |
| Recipe key | `gopls` |

### Special notes
- Official Language Server Protocol (LSP) implementation for Go.
- Used by VS Code (Go extension), Vim/Neovim, Emacs, and all LSP-capable editors.
- Provides code completion, diagnostics, refactoring, hover info, navigation.
- Written in Go — installed exclusively via `go install`.
- NOT available in any system package manager (apt, dnf, apk, pacman, zypper).
- NOT available in brew, npm, pip, cargo.
- Installs to `$HOME/go/bin` — requires PATH addition.
- Update is the same command as install (`@latest` always gets newest).

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
| `go` | ✅ | `golang.org/x/tools/gopls@latest` | **Only method** |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Any with Go | `go install golang.org/x/tools/gopls@latest` | _default (go) |

### _default method (go install)
```bash
go install golang.org/x/tools/gopls@latest
```
- **No sudo needed** — installs to `$HOME/go/bin`.
- Requires Go toolchain on PATH.
- `install_via: go` — triggers go-specific failure handlers.
- Update is identical (re-run with `@latest`).

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
| `go` | 3 (go not installed, GOPATH issues, module download) |

### Layer 1: INFRA handlers (9 cross-tool)
All standard — network, disk, permissions, OOM, timeout.

### Layer 3: None needed.
No unique gopls-specific failure modes.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  323/323 (100%) — 17 scenarios × 19 presets
Handlers:  8 method-specific + 9 INFRA = 17
```

Single-method tool — `go install` only. Lower scenario count is expected
for tools with only one install path.

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "gopls"` |
| `data/recipes.py` | Updated label to "Go language server — official" |
| `data/recipes.py` | Added research comments |
| `data/recipes.py` | `update` already present (re-runs go install @latest) |

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

No native PM coverage. All platforms require Go toolchain installed first.
This is standard for Go ecosystem tools — the Go team ships gopls
exclusively through `go install`.
