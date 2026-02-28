# prometheus — Full Spectrum Analysis

> **Tool ID:** `prometheus`
> **Last audited:** 2026-02-28
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Prometheus — metrics monitoring and alerting toolkit |
| Language | Go |
| Author | CNCF (Cloud Native Computing Foundation) |
| CLI binary | `prometheus` |
| Category | `monitoring` |
| Verify command | `prometheus --version` |
| Recipe key | `prometheus` |

### Special notes
- Written in Go — single static binary per platform.
- CNCF graduated project — the de facto standard for cloud-native metrics.
- GitHub releases include **both** `prometheus` (server) and `promtool`
  (config validator). The recipe extracts both.
- **Version is embedded in filename**: `prometheus-VERSION.OS-ARCH.tar.gz`.
  Tag has `v` prefix (e.g. `v2.53.0`), filename strips it (`2.53.0`).
  Requires GitHub API lookup to resolve latest version at install time.
- Archive is nested: files are in `prometheus-VERSION.OS-ARCH/` subdirectory.
  `--strip-components=1` is needed, with explicit subpath extraction.
- Arch naming: `amd64`, `arm64`, `armv7`. OS naming: `linux`, `darwin`.
- **NOT in apt, dnf, apk (standard), zypper, snap.**
  pacman community has it but includes systemd service setup.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora repos |
| `apk` | ❌ | — | community repo only, may lag |
| `pacman` | ⚠️ | `prometheus` | Community — includes server service |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `prometheus` | **Preferred** |
| `snap` | ❌ | — | Not available |
| `_default` | ✅ | — | GitHub release tar.gz |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| macOS/Linux (preferred) | `brew install prometheus` | brew |
| Any Linux (fallback) | GitHub API → release tar.gz | _default |

### brew method (preferred)
```bash
brew install prometheus
```

### _default method (GitHub release)
```bash
VERSION=$(curl -sSf https://api.github.com/repos/prometheus/prometheus/releases/latest \
  | grep -o '"tag_name": "v[^"]*"' | cut -d'"' -f4 | sed 's/^v//')
curl -sSfL "https://github.com/prometheus/prometheus/releases/download/v${VERSION}/prometheus-${VERSION}.linux-amd64.tar.gz" \
  | sudo tar -xz --strip-components=1 -C /usr/local/bin \
    prometheus-${VERSION}.linux-amd64/prometheus \
    prometheus-${VERSION}.linux-amd64/promtool
```
- **Needs sudo** — writes to `/usr/local/bin`.
- `{arch}` resolved via `arch_map`: x86_64→amd64, aarch64→arm64, armv7l→armv7.
- `{os}` resolved at runtime: linux, darwin.
- `install_via: github_release` — triggers release handlers.
- Uses GitHub API to resolve latest version (version in filename).

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For both API lookup and binary download |

No runtime dependencies — prometheus is a self-contained Go binary.

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (9 total)
| Family | Handlers |
|--------|----------|
| `brew` | 1 (no formula) |
| `_default` | 5 (missing curl/git/wget/unzip/npm) |
| `github_release` | 3 (rate limit, no asset, extract failed) |

### Layer 1: INFRA handlers (9 cross-tool)
All standard — network, disk, permissions, OOM, timeout.

### Layer 3: None needed.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  342/342 (100%) — 18 scenarios × 19 presets
Handlers:  9 method-specific + 9 INFRA = 18
```

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "prometheus"` |
| `data/recipes.py` | Updated label to full description |
| `data/recipes.py` | **Fixed broken wildcard glob** in URL (curl doesn't glob) |
| `data/recipes.py` | **Removed platform dict** — single cross-platform `_default` |
| `data/recipes.py` | **Fixed hardcoded `amd64`** → `{arch}` with `arch_map` |
| `data/recipes.py` | Added `{os}` for OS detection (linux/darwin) |
| `data/recipes.py` | Added GitHub API version lookup (`VERSION=$(curl ...)`) |
| `data/recipes.py` | Added `arch_map: {x86_64→amd64, aarch64→arm64, armv7l→armv7}` |
| `data/recipes.py` | Added `prefer: ["brew"]` |
| `data/recipes.py` | Added `update` for both methods |
| `data/recipes.py` | Added research comments |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | **Preferred** — formula `prometheus` ✅ |
| **Linux with brew** | brew | Linuxbrew supported ✅ |
| **Debian/Ubuntu** | _default | GitHub release tar.gz ✅ |
| **Fedora/RHEL** | _default | GitHub release tar.gz ✅ |
| **Alpine** | _default | GitHub release tar.gz ✅ |
| **Arch Linux** | _default | Community has it but _default is simpler ✅ |
| **openSUSE** | _default | GitHub release tar.gz ✅ |
| **Raspbian (aarch64)** | _default | `arch_map` → arm64 ✅ |
| **WSL** | brew or _default | Standard methods ✅ |

brew preferred where available. GitHub release with API version lookup
as universal fallback. Cross-platform fix: was broken glob + hardcoded
amd64, now works on all Linux + macOS + ARM.
