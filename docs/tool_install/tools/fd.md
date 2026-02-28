# fd — Full Spectrum Analysis

> **Tool ID:** `fd`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | fd — modern find replacement |
| Language | Rust |
| CLI binary | `fd` |
| Category | `devtools` |
| Verify command | `fd --version` |
| Recipe key | `fd` |

### Special notes
- By sharkdp (David Peter). Same author as `bat`.
- Faster than `find`, respects `.gitignore`, colorized output.
- Written in Rust — pre-compiled in all native PMs.
- **Package name varies across PMs:**
  - `fd-find` on Debian/Ubuntu (`apt`) and Fedora (`dnf`)
  - `fd` on Alpine (`apk`), Arch (`pacman`), openSUSE (`zypper`), macOS (`brew`)
- This mismatch also applies to `update` commands — must use the correct
  package name per PM.
- Available in ALL 6 native PMs — no `_default` needed.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `fd-find` | Name conflict avoidance |
| `dnf` | ✅ | `fd-find` | Same as Debian convention |
| `apk` | ✅ | `fd` | Standard name |
| `pacman` | ✅ | `fd` | Standard name |
| `zypper` | ✅ | `fd` | Standard name |
| `brew` | ✅ | `fd` | Standard name |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Debian/Ubuntu | `apt-get install -y fd-find` | apt |
| Fedora/RHEL | `dnf install -y fd-find` | dnf |
| Alpine | `apk add fd` | apk |
| Arch | `pacman -S --noconfirm fd` | pacman |
| openSUSE | `zypper install -y fd` | zypper |
| macOS | `brew install fd` | brew |

### Package name mismatch
On Debian/Ubuntu and Fedora, the package is `fd-find` to avoid a naming
conflict with an existing `fd` package (a different tool). The binary is
still `fd` on all platforms. The `update` commands correctly use the
per-PM package name (`fd-find` for apt/dnf, `fd` elsewhere).

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
No unique fd-specific failure modes.

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
| `data/recipes.py` | Updated label to "fd (modern find replacement)" |
| `data/recipes.py` | Added `zypper` install method |
| `data/recipes.py` | Added `prefer` list for all 6 PMs |
| `data/recipes.py` | Added `update` commands for all 6 PMs (with correct per-PM package names) |
| `data/recipes.py` | Added research comments (package name mismatch) |

Note: `cli: "fd"` was already present before audit.

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | Package: `fd` |
| **Raspbian (aarch64)** | apt | Package: `fd-find` |
| **Debian/Ubuntu** | apt | Package: `fd-find` |
| **Fedora/RHEL** | dnf | Package: `fd-find` |
| **Alpine** | apk | Package: `fd` |
| **Arch** | pacman | Package: `fd` |
| **openSUSE** | zypper | Package: `fd` |

All presets have native PM coverage. No fallback needed.
