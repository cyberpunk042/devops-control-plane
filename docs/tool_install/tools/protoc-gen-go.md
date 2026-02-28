# protoc-gen-go — Full Spectrum Analysis

> **Tool ID:** `protoc-gen-go`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | protoc-gen-go — Go protobuf code generator |
| Language | Go |
| Author | Google (google.golang.org/protobuf) |
| CLI binary | `protoc-gen-go` |
| Category | `go` |
| Verify command | `protoc-gen-go --version` |
| Recipe key | `protoc-gen-go` |

### Special notes
- Generates Go code from `.proto` (Protocol Buffers) definition files.
- Plugin for `protoc` — the protobuf compiler invokes it automatically.
- Used as `protoc --go_out=. --go_opt=paths=source_relative foo.proto`.
- Requires `protoc` installed separately at runtime (not a dependency in recipe
  because protoc is a separate tool with its own recipe).
- Written in Go — installed exclusively via `go install`.
- NOT available in any system package manager or brew.
- Installs to `$HOME/go/bin` — requires PATH addition.
- Often paired with `protoc-gen-go-grpc` for gRPC service generation.

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
| `go` | ✅ | `google.golang.org/protobuf/cmd/protoc-gen-go@latest` | **Only method** |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Any with Go | `go install google.golang.org/protobuf/cmd/protoc-gen-go@latest` | _default (go) |

### _default method (go install)
```bash
go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
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
| Runtime | `protoc` | Protobuf compiler (separate tool) |

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
| `data/recipes.py` | Added `cli: "protoc-gen-go"` |
| `data/recipes.py` | Updated label to "Go protobuf code generator" |
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
Requires `protoc` separately for actual protobuf compilation.
