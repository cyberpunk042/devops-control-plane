# grype — Full Spectrum Analysis

> **Tool ID:** `grype`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Grype — container & filesystem vulnerability scanner |
| Language | Go |
| CLI binary | `grype` |
| Category | `security` |
| Verify command | `grype version` |
| Recipe key | `grype` |

### Special notes
- By Anchore — scans container images, filesystems, and SBOMs.
- Companion to Syft (SBOM generator).
- Single statically-linked Go binary — no runtime deps.
- Official curl|bash installer handles OS/arch detection.
- NOT in apt, dnf, apk, pacman, zypper standard repos.
- GitHub releases also provide `.deb` and `.rpm` packages.
- Available via brew, snap, and official installer.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in standard repos (.deb on GitHub) |
| `dnf` | ❌ | — | Not in standard repos (.rpm on GitHub) |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ❌ | — | Not available |
| `zypper` | ❌ | — | Not available |
| `brew` | ✅ | `grype` | Standard formula |
| `snap` | ✅ | `grype` | Available |

---

## 3. Installation (_default via curl|bash)

| Field | Value |
|-------|-------|
| Method | Official Anchore installer script |
| URL | `https://raw.githubusercontent.com/anchore/grype/main/install.sh` |
| Install location | `/usr/local/bin/grype` |
| Dependencies | `curl` |
| needs_sudo | Yes |
| install_via | `curl_pipe_bash` |

### GitHub releases (alternative)
- Asset pattern: `grype_{version}_{os}_{arch}.tar.gz`
- Tag: `v0.109.0` (with `v`), filename: `0.109.0` (without `v`)
- OS: `linux`, `darwin`. Arch: `amd64`, `arm64`, `ppc64le`, `s390x`
- Also provides `.deb` and `.rpm` packages

### Architecture naming (Go-standard)

| Architecture | Asset suffix |
|-------------|-------------|
| x86_64 | `linux_amd64` |
| aarch64 (ARM64) | `linux_arm64` |

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For installer script |
| Runtime | None | Self-contained static binary |

---

## 5. Post-install

No PATH additions needed. Binary installed to `/usr/local/bin/`.

---

## 6. Failure Handlers

### Layer 2b: install_via family (curl_pipe_bash)
| Handler | Category | Trigger |
|---------|----------|---------|
| `curl_tls_certificate` | environment | TLS certificate verification failed |
| `curl_unsupported_arch` | environment | Unsupported OS or architecture |
| `curl_script_not_found` | environment | Install script URL not found |

### Layer 2a: method-family handlers (shared)
| Family | Handler | Trigger |
|--------|---------|---------|
| `brew` | `brew_no_formula` | Formula not found |
| `snap` | `snapd_unavailable` | snapd not running |
| `_default` | `missing_curl` | curl not installed |
| `_default` | `missing_git` | git not installed |
| `_default` | `missing_wget` | wget not installed |
| `_default` | `missing_unzip` | unzip not installed |
| `_default` | `missing_npm_default` | npm not installed |

### Layer 1: INFRA handlers (9 cross-tool)
Network, disk, permissions, OOM, timeout — all standard.

### Layer 3: per-tool on_failure handlers
None needed. Standard curl|bash installer + brew + snap.

---

## 7. Recipe Structure

```python
"grype": {
    "cli": "grype",
    "label": "Grype (container vulnerability scanner)",
    "category": "security",
    "install": {
        "brew":    ["brew", "install", "grype"],
        "snap":    ["snap", "install", "grype"],
        "_default": ["bash", "-c", "curl ... install.sh | sh ..."],
    },
    "needs_sudo": {"brew": False, "snap": True, "_default": True},
    "install_via": {"_default": "curl_pipe_bash"},
    "requires": {"binaries": ["curl"]},
    "arch_map": {"x86_64": "amd64", "aarch64": "arm64"},
    "prefer": ["brew"],
    "verify": ["grype", "version"],
    "update": { ... per-method update commands ... },
}
```

---

## 8. Validation Results

```
Schema:    VALID (recipe + all method-family handlers)
Coverage:  361/361 (100%) — 19 scenarios × 19 presets
Handlers:  1 brew + 1 snap + 5 _default + 3 curl_pipe_bash + 9 INFRA = 19 total
```

---

## 9. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "grype"` |
| `data/recipes.py` | Updated label to `"Grype (container vulnerability scanner)"` |
| `data/recipes.py` | Added `snap` install method |
| `data/recipes.py` | Added `arch_map` (amd64, arm64) |
| `data/recipes.py` | Added `prefer: ["brew"]` |
| `data/recipes.py` | Added per-method `update` commands |

---

## 10. Future Enhancements

- **DB update**: Could run `grype db update` after install to
  pull latest vulnerability database.
- **Syft integration**: Could check if Syft is installed and suggest
  pairing for SBOM generation + scanning workflow.
