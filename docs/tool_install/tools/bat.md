# bat — Full Spectrum Analysis

> **Tool ID:** `bat`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | bat — cat replacement with syntax highlighting |
| Language | Rust |
| CLI binary | `bat` |
| Category | `devtools` |
| Verify command | `bat --version` |
| Recipe key | `bat` |

### Special notes
- By sharkdp (David Peter). A `cat` clone with syntax highlighting and Git integration.
- Supports 100+ programming languages with automatic detection.
- Written in Rust — pre-compiled in all native PMs.
- Available in ALL 6 native PMs — no `_default` needed.
- **Debian/Ubuntu caveat:** On older versions (before 22.04), the binary is
  named `batcat` due to a name conflict with another package. Modern versions
  use `bat` directly.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `bat` | Debian/Ubuntu |
| `dnf` | ✅ | `bat` | Fedora/RHEL |
| `apk` | ✅ | `bat` | Alpine |
| `pacman` | ✅ | `bat` | Arch |
| `zypper` | ✅ | `bat` | openSUSE |
| `brew` | ✅ | `bat` | macOS |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Debian/Ubuntu | `apt-get install -y bat` | apt |
| Fedora/RHEL | `dnf install -y bat` | dnf |
| Alpine | `apk add bat` | apk |
| Arch | `pacman -S --noconfirm bat` | pacman |
| openSUSE | `zypper install -y bat` | zypper |
| macOS | `brew install bat` | brew |

---

## 4. Dependencies

No build or runtime dependencies — standalone Rust binary.
Pre-compiled and available in all distro repos.

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
No unique bat-specific failure modes.

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
| `data/recipes.py` | Added `cli: "bat"` |
| `data/recipes.py` | Updated label to "bat (cat replacement with syntax highlighting)" |
| `data/recipes.py` | Added `zypper` install method |
| `data/recipes.py` | Added `prefer` list for all 6 PMs |
| `data/recipes.py` | Added `update` commands for all 6 PMs |
| `data/recipes.py` | Added research comments (batcat caveat) |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | Standard formula |
| **Raspbian (aarch64)** | apt | Standard repos |
| **Debian/Ubuntu** | apt | Binary may be `batcat` on older versions |
| **Fedora/RHEL** | dnf | Standard repos |
| **Alpine** | apk | Standard repos |
| **Arch** | pacman | Standard repos |
| **openSUSE** | zypper | Standard repos |

All presets have native PM coverage. No fallback needed.
