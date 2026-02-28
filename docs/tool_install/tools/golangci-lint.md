# golangci-lint — Full Spectrum Analysis

> **Tool ID:** `golangci-lint`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | golangci-lint — Go linters aggregator |
| Language | Go |
| CLI binary | `golangci-lint` |
| Category | `go` |
| Verify command | `golangci-lint --version` |
| Recipe key | `golangci-lint` |

### Special notes
- Aggregates 100+ Go linters into a single fast CLI.
- Significantly faster than running individual linters — runs them in parallel.
- Official installer script is recommended for CI reproducibility.
- Also available via `go install` but official docs discourage it for CI
  because it doesn't guarantee reproducible builds.
- Only Go-stack tool with brew support.
- NOT in apt, dnf, apk, pacman, zypper, pip, npm, cargo.
- Installs to `$(go env GOPATH)/bin` — needs PATH addition.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora repos |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ❌ | — | Not in Arch repos |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `golangci-lint` | **Preferred** — macOS/Linux |
| `_default` | ✅ | — | Official `curl | sh` installer script |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| macOS/Linux (preferred) | `brew install golangci-lint` | brew |
| Any with Go + curl | Official installer script | _default |

### brew method (preferred)
```bash
brew install golangci-lint
```

### _default method (installer script)
```bash
curl -sSfL https://raw.githubusercontent.com/golangci/golangci-lint/HEAD/install.sh \
  | sh -s -- -b $(go env GOPATH)/bin
```
- **No sudo needed** — installs to GOPATH/bin.
- Requires `go` and `curl` on PATH.
- `install_via: curl_pipe_bash` — triggers TLS and script handlers.

### Post-install
```bash
export PATH="$HOME/go/bin:$PATH"
```

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Runtime | `go` | Go toolchain (for _default method GOPATH) |
| Download | `curl` | For _default installer script |

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (12 total)
| Family | Handlers |
|--------|----------|
| `brew` | 1 (no formula) |
| `_default` | 5 (missing curl/git/wget/unzip/npm) |
| `curl_pipe_bash` | 3 (TLS, unsupported arch, script 404) |
| `go` | 3 (go not installed, GOPATH, module download) |

### Layer 1: INFRA handlers (9 cross-tool)
All standard — network, disk, permissions, OOM, timeout.

### Layer 3: None needed.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  399/399 (100%) — 21 scenarios × 19 presets
Handlers:  12 method-specific + 9 INFRA = 21
```

Higher scenario count than other Go tools due to brew + curl_pipe_bash
adding handler families beyond the base `go install` pattern.

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "golangci-lint"` |
| `data/recipes.py` | Updated label to "Go linters aggregator" |
| `data/recipes.py` | Added `prefer: ["brew"]` |
| `data/recipes.py` | Added research comments |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | **Preferred** — formula |
| **Linux with brew** | brew | Linuxbrew supported |
| **Any with Go + curl** | _default | Official script |
| **Debian/Ubuntu** | _default | Not in apt |
| **Fedora/RHEL** | _default | Not in dnf |
| **Alpine** | _default | Not in apk |
| **Arch** | _default | Not in pacman |
| **openSUSE** | _default | Not in zypper |

Only Go-stack tool with native PM support (brew). All other platforms
fall back to the official installer script.
