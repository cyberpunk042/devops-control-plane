# trivy — Full Spectrum Analysis

> **Tool ID:** `trivy`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Trivy — comprehensive vulnerability scanner |
| Language | Go |
| CLI binary | `trivy` |
| Category | `security` |
| Verify command | `trivy --version` |
| Recipe key | `trivy` |

### Special notes
- Trivy is Aqua Security's open-source vulnerability scanner.
- Scans containers, filesystems, git repos, IaC configs (Terraform,
  Kubernetes), and SBOMs for vulnerabilities, misconfigurations,
  secrets, and license issues.
- Single statically-linked Go binary — no runtime deps.
- **apt** requires adding Aqua Security's GPG key + Debian repo
  (hosted at `aquasecurity.github.io/trivy-repo/`).
- **dnf** requires adding Aqua Security's RPM repo config.
- **NOT available** in apk (Alpine), pacman (Arch community only),
  or zypper (openSUSE) standard repos.
- The official `install.sh` curl|bash installer auto-detects OS/arch.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `trivy` | Requires Aqua Security GPG key + repo |
| `dnf` | ✅ | `trivy` | Requires Aqua Security RPM repo |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ❌ | — | AUR only (community) |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `trivy` | Standard formula |
| `snap` | ✅ | `trivy` | Available |
| `pip` | ❌ | — | Not available |
| `npm` | ❌ | — | Not available |
| `cargo` | ❌ | — | Not available |
| `go` | ❌ | — | Not a `go install` binary |

---

## 3. Binary Download (_default)

| Field | Value |
|-------|-------|
| Source | Official `install.sh` from Aqua Security |
| URL | `https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh` |
| Method | `curl -sfL ... \| sh -s -- -b /usr/local/bin` |
| Install location | `/usr/local/bin/trivy` |
| Dependencies | `curl` |
| needs_sudo | Yes |

### How the installer works
The `install.sh` script:
1. Detects OS and architecture
2. Downloads the matching release from GitHub
3. Extracts and installs the binary

### GitHub Releases format (used internally by the installer)
```
https://github.com/aquasecurity/trivy/releases/download/v{version}/trivy_{version}_{OS}-{ARCH}.tar.gz
```

### Architecture naming (non-standard!)

| Architecture | Archive suffix |
|-------------|---------------|
| x86_64 | `Linux-64bit.tar.gz` |
| aarch64 (ARM64) | `Linux-ARM64.tar.gz` |
| armv7l (ARM 32) | `Linux-ARM.tar.gz` |

**Note:** Trivy uses `64bit`/`ARM64`/`ARM` — not the standard
`amd64`/`arm64` convention. The installer handles this.

### Also publishes
- `.deb` packages (can be installed directly with `dpkg -i`)
- `.rpm` packages (can be installed directly with `rpm -ivh`)

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For installer script download |
| Runtime | None | Self-contained static binary |

### Reverse deps
Trivy is used by:
- CI/CD pipelines for container image scanning
- IaC security checks (Terraform, Kubernetes manifests)
- SBOM generation and vulnerability assessment
- GitOps workflows for security gates

---

## 5. Post-install

No PATH additions or shell configuration needed. The binary is
installed to `/usr/local/bin/` (via `_default`) or standard package
locations (via PM installs).

---

## 6. Failure Handlers

### Layer 2b: install_via family (curl_pipe_bash)
| Handler | Category | Trigger |
|---------|----------|---------|
| `curl_tls_certificate` | environment | TLS certificate verification failed |
| `curl_unsupported_arch` | environment | Unsupported OS or architecture |
| `curl_script_not_found` | environment | Install script URL returned 404/HTML |

### Layer 2a: method-family handlers (shared)
| Family | Handler | Trigger |
|--------|---------|---------|
| `apt` | `apt_stale_index` | Stale package index |
| `apt` | `apt_locked` | dpkg lock held |
| `dnf` | `dnf_no_match` | Package not in repos |
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

| Handler | Category | Trigger | Options |
|---------|----------|---------|---------|
| `trivy_gpg_repo_setup_failed` | configuration | Aqua Security GPG key import fails, aquasecurity.github.io unreachable, repo file permission denied | Switch to `_default` installer (recommended), switch to `brew` |
| `trivy_repo_not_configured` | configuration | `Unable to locate package trivy` / no installation candidate / no match for argument | Switch to `_default` installer (recommended), switch to `snap` |

---

## 7. Recipe Structure

```python
"trivy": {
    "cli": "trivy",
    "label": "Trivy (comprehensive vulnerability scanner)",
    "category": "security",
    "install": {
        "apt":     ["bash", "-c", "setup GPG key + repo && apt install trivy"],
        "dnf":     ["bash", "-c", "setup RPM repo && dnf install trivy"],
        "brew":    ["brew", "install", "trivy"],
        "snap":    ["snap", "install", "trivy"],
        "_default": ["bash", "-c", "curl install.sh | sh -s -- -b /usr/local/bin"],
    },
    "needs_sudo": {
        "apt": True, "dnf": True,
        "brew": False, "snap": True, "_default": True,
    },
    "install_via": {"_default": "curl_pipe_bash"},
    "requires": {"binaries": ["curl"]},
    "prefer": ["apt", "dnf", "brew"],
    "verify": ["trivy", "--version"],
    "update": { ... per-method update commands ... },
}
```

---

## 8. Validation Results

```
Schema:    VALID (recipe + all method-family + on_failure handlers)
Coverage:  456/456 (100%) — 24 scenarios × 19 presets
Handlers:  2 apt + 1 dnf + 1 brew + 1 snap
           + 5 _default + 3 curl_pipe_bash + 2 on_failure
           + 9 INFRA = 24 total
```

---

## 9. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "trivy"` |
| `data/recipes.py` | Added `category: "security"` |
| `data/recipes.py` | Updated label to `"Trivy (comprehensive vulnerability scanner)"` |
| `data/recipes.py` | Added `apt` method (Aqua Security GPG key + repo + install) |
| `data/recipes.py` | Added `dnf` method (Aqua Security RPM repo + install) |
| `data/recipes.py` | Added `snap` method |
| `data/recipes.py` | Added `prefer` list (apt, dnf, brew) |
| `data/recipes.py` | Added per-method `update` commands |
| `data/tool_failure_handlers.py` | Added `trivy_gpg_repo_setup_failed` handler (2 options) |
| `data/tool_failure_handlers.py` | Added `trivy_repo_not_configured` handler (2 options) |

---

## 10. Future Enhancements

- **DB update**: Post-install `trivy image --download-db-only` for
  offline vulnerability database setup.
- **Config file**: `trivy.yaml` configuration for default scan options.
