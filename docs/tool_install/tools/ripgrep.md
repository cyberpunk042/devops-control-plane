# ripgrep — Full Spectrum Analysis

> **Tool ID:** `ripgrep`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | ripgrep — recursive grep replacement |
| Language | Rust |
| CLI binary | `rg` (not `ripgrep`) |
| Category | `devtools` |
| Verify command | `rg --version` |
| Recipe key | `ripgrep` |

### Special notes
- By BurntSushi (Andrew Gallant). Ultra-fast line-oriented search tool.
- Respects `.gitignore` by default — smarter than grep.
- Written in Rust — pre-compiled and available in all native PMs.
- **Package name (`ripgrep`) differs from binary name (`rg`)** — important for verification.
- Available in ALL 6 native PMs — no `_default` needed.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `ripgrep` | Debian/Ubuntu |
| `dnf` | ✅ | `ripgrep` | Fedora/RHEL |
| `apk` | ✅ | `ripgrep` | Alpine community |
| `pacman` | ✅ | `ripgrep` | Arch |
| `zypper` | ✅ | `ripgrep` | openSUSE |
| `brew` | ✅ | `ripgrep` | macOS |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Debian/Ubuntu | `apt-get install -y ripgrep` | apt |
| Fedora/RHEL | `dnf install -y ripgrep` | dnf |
| Alpine | `apk add ripgrep` | apk |
| Arch | `pacman -S --noconfirm ripgrep` | pacman |
| openSUSE | `zypper install -y ripgrep` | zypper |
| macOS | `brew install ripgrep` | brew |

---

## 4. Dependencies

No build or runtime dependencies — standalone Rust binary.
Pre-compiled and statically linked in all distro packages.

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (10 total)
| Family | Handlers |
|--------|----------|
| `apt` | 2 (stale index, locked) |
| `dnf` | 1 (no match) |
| `apk` | 2 (unsatisfiable, locked) |
| `pacman` | 2 (not found, locked) |
| `zypper` | 2 (not found, locked) |
| `brew` | 1 (no formula) |

### Layer 1: INFRA handlers (9 cross-tool)
All standard — network, disk, permissions, OOM, timeout.

### Layer 3: None needed.
No unique ripgrep-specific failure modes.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  361/361 (100%) — 19 scenarios × 19 presets
Handlers:  10 PM-specific + 9 INFRA = 19
```

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Updated label to "ripgrep (rg — recursive grep replacement)" |
| `data/recipes.py` | Added `prefer` list for all 6 PMs |
| `data/recipes.py` | Added `update` commands for all 6 PMs |
| `data/recipes.py` | Added research comments |

Note: `cli: "rg"` was already present before audit.

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | Standard formula |
| **Raspbian (aarch64)** | apt | Standard repos |
| **Debian/Ubuntu** | apt | Standard repos |
| **Fedora/RHEL** | dnf | Standard repos |
| **Alpine** | apk | Community repos |
| **Arch** | pacman | Standard repos |
| **openSUSE** | zypper | Standard repos |

All presets have native PM coverage. No fallback needed.
