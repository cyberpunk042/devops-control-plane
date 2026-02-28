# skopeo — Full Spectrum Analysis

> **Tool ID:** `skopeo`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Skopeo — container image inspection & transfer |
| Language | Go |
| CLI binary | `skopeo` |
| Category | `container` |
| Verify command | `skopeo --version` |
| Recipe key | `skopeo` |

### Special notes
- Same containers project as podman (Red Hat).
- Inspects, copies, and signs container images without Docker daemon.
- Can copy images between registries without pulling locally.
- Available in ALL native PMs — wide coverage.
- No `_default` binary download needed.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `skopeo` | Debian 11+, Ubuntu 20.10+ |
| `dnf` | ✅ | `skopeo` | Fedora, RHEL, CentOS |
| `apk` | ✅ | `skopeo` | Alpine community |
| `pacman` | ✅ | `skopeo` | Arch extra |
| `zypper` | ✅ | `skopeo` | openSUSE (Virtualization:containers) |
| `brew` | ✅ | `skopeo` | Standard formula |

---

## 3. Installation

Every supported platform has skopeo in its native PM.

| Platform | Command | PM |
|----------|---------|-----|
| Debian/Ubuntu | `apt-get install -y skopeo` | apt |
| Fedora/RHEL | `dnf install -y skopeo` | dnf |
| Alpine | `apk add skopeo` | apk |
| Arch | `pacman -S --noconfirm skopeo` | pacman |
| openSUSE | `zypper install -y skopeo` | zypper |
| macOS | `brew install skopeo` | brew |

---

## 4. Dependencies

No special runtime dependencies. Container registries accessed via
HTTP(S) — no Docker daemon needed.

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (per PM — 10 total)
| Family | Handler | Trigger |
|--------|---------|---------|
| `apt` | `apt_stale_index` | Stale package index |
| `apt` | `apt_locked` | dpkg locked |
| `dnf` | `dnf_no_match` | Package not found |
| `apk` | `apk_unsatisfiable` | Package not found |
| `apk` | `apk_locked` | DB locked |
| `pacman` | `pacman_target_not_found` | Not found |
| `pacman` | `pacman_locked` | DB locked |
| `zypper` | `zypper_not_found` | Not found |
| `zypper` | `zypper_locked` | PM locked |
| `brew` | `brew_no_formula` | Formula not found |

### Layer 1: INFRA handlers (9 cross-tool)
All standard.

### Layer 3: None needed.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  361/361 (100%) — 19 scenarios × 19 presets
Handlers:  10 PM-specific + 9 INFRA = 19 total
```

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "skopeo"` |
| `data/recipes.py` | Updated label |
| `data/recipes.py` | Added `zypper` install method |
| `data/recipes.py` | Added `prefer` and `update` for all 6 PMs |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | Standard formula |
| **Raspbian** | apt | Standard repos |
| **Debian/Ubuntu** | apt | Debian 11+ |
| **Fedora/RHEL** | dnf | Native |
| **Alpine** | apk | Community |
| **Arch** | pacman | Extra |
| **openSUSE** | zypper | Virtualization:containers |
