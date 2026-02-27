# terraform — Full Spectrum Analysis

> **Tool ID:** `terraform`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Terraform — infrastructure as code |
| Language | Go |
| CLI binary | `terraform` |
| Category | `iac` |
| Verify command | `terraform --version` |
| Recipe key | `terraform` |

### Special notes
- Terraform is HashiCorp's flagship IaC tool for provisioning cloud and
  on-prem infrastructure declaratively.
- The binary is a **single statically-linked Go binary** — no runtime deps.
- HashiCorp maintains **official package repositories** for apt and dnf,
  requiring GPG key + repo setup before install.
- The `_default` method downloads from `releases.hashicorp.com` (HashiCorp's
  CDN, NOT GitHub releases), but uses the `github_release` install_via
  family because the failure modes are identical (rate limits, arch
  mismatches, archive extraction).
- Version discovery uses HashiCorp's checkpoint API:
  `https://checkpoint.hashicorp.com/v1/check/terraform`
- Binary is distributed as a `.zip` archive (requires `unzip`).
- The `brew` method uses HashiCorp's **official tap** (`hashicorp/tap/terraform`),
  not the community formula.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `terraform` | Requires HashiCorp GPG key + apt repo |
| `dnf` | ✅ | `terraform` | Requires HashiCorp dnf repo |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ✅ | `terraform` | Arch `extra` repo |
| `zypper` | ⚠️ | `terraform` | Only in OBS community repos — not reliable |
| `snap` | ✅ | `terraform` | `--classic` confinement required |
| `brew` | ✅ | `hashicorp/tap/terraform` | Official HashiCorp tap |
| `pip` | ❌ | — | Not available |
| `npm` | ❌ | — | Not available |
| `cargo` | ❌ | — | Not available |
| `go` | ❌ | — | Not a `go install` tool |

### Package name notes
- **apt/dnf:** Package name matches CLI (`terraform`), but both require
  adding the HashiCorp repository and GPG key first. The install commands
  in the recipe handle this automatically as a multi-step bash -c script.
- **brew:** Uses `hashicorp/tap/terraform` (official tap), NOT the core
  `terraform` formula which may lag behind releases.
- **snap:** Requires `--classic` confinement for filesystem access.
- **zypper:** Not included in recipe — only available via community OBS
  repos which require manual repository addition.

---

## 3. Binary Download (_default)

| Field | Value |
|-------|-------|
| Source | https://releases.hashicorp.com/terraform/ |
| URL pattern | `https://releases.hashicorp.com/terraform/{version}/terraform_{version}_linux_amd64.zip` |
| Archive format | `.zip` (contains single `terraform` binary) |
| Install location | `/usr/local/bin/terraform` |
| Dependencies | `curl` (download), `unzip` (extract), `python3` (version parse) |
| needs_sudo | Yes (writes to `/usr/local/bin/`) |

### Version resolution
The `_default` command auto-resolves the latest version via HashiCorp's
checkpoint API:
```
curl -sSf https://checkpoint.hashicorp.com/v1/check/terraform
```
Returns JSON with `current_version` field.

### Architecture support
HashiCorp publishes binaries for:

| Architecture | Zip suffix |
|-------------|-----------|
| x86_64 | `linux_amd64.zip` |
| aarch64 (ARM64) | `linux_arm64.zip` |
| armv7l (ARM 32) | `linux_arm.zip` |
| i386 | `linux_386.zip` |

The `_default` command uses `{os}` and `{arch}` placeholders with
`arch_map` for Go-standard architecture naming. All 5 platforms resolve
correctly to valid HashiCorp download URLs.

### OS support
HashiCorp publishes for Linux, macOS (darwin), Windows, FreeBSD, OpenBSD,
and Solaris. The `_default` command targets Linux. macOS users should
prefer `brew`.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For `_default` install and version check |
| Download | `unzip` | For extracting the .zip archive |
| Download | `python3` | For parsing checkpoint API JSON |
| Download | `wget` | For `apt` method (GPG key download) |
| Runtime | None | Self-contained static binary |

### Reverse deps
Terraform is referenced by:
- `terragrunt` — Terraform wrapper for DRY configurations
- `tflint` — Terraform linter
- `terraform-docs` — Documentation generator
- `checkov`, `tfsec` — Terraform security scanners
- Various CI/CD pipelines and IaC workflows

---

## 5. Post-install

No PATH additions or shell configuration needed. The binary is
installed to `/usr/local/bin/` which is in the default PATH on
all supported platforms.

For apt/dnf installs, the binary goes to `/usr/bin/terraform`
(standard package location).

---

## 6. Failure Handlers

### Layer 2b: install_via family (github_release)
| Handler | Category | Trigger |
|---------|----------|---------|
| `github_rate_limit` | environment | API rate limit exceeded |
| `github_asset_not_found` | environment | No binary for OS/arch |
| `github_extract_failed` | environment | Archive extraction failure |

### Layer 2a: method-family handlers (shared)
| Family | Handler | Trigger |
|--------|---------|---------|
| `apt` | `apt_stale_index` | Stale package index |
| `apt` | `apt_locked` | dpkg lock held |
| `dnf` | `dnf_no_match` | Package not in repos |
| `pacman` | `pacman_target_not_found` | Package not found |
| `pacman` | `pacman_locked` | Database locked |
| `snap` | `snapd_unavailable` | snapd not running |
| `brew` | `brew_no_formula` | Formula not found |
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
| `terraform_gpg_repo_setup_failed` | configuration | GPG key import fails, keyring permission denied, signing key verification error | Switch to `_default` binary (recommended), switch to `snap` |
| `terraform_repo_not_configured` | configuration | `Unable to locate package terraform` / package not found on apt/dnf | Switch to `_default` binary (recommended), switch to `snap` |
| `terraform_checkpoint_api_failed` | network | Checkpoint API DNS failure, connection refused, JSON parse error | Switch to `snap` (recommended), switch to `brew`, manual version download |

---

## 7. Recipe Structure

```python
"terraform": {
    "cli": "terraform",
    "label": "Terraform (infrastructure as code)",
    "category": "iac",
    "install": {
        "apt":    ["bash", "-c", "wget ... | gpg ... && apt install terraform"],
        "dnf":    ["bash", "-c", "dnf config-manager ... && dnf install terraform"],
        "pacman": ["pacman", "-S", "--noconfirm", "terraform"],
        "snap":   ["snap", "install", "terraform", "--classic"],
        "brew":   ["bash", "-c", "brew tap hashicorp/tap && brew install ..."],
        "_default": [
            "bash", "-c",
            "TF_VERSION=$(curl checkpoint API) && "
            "curl -o /tmp/terraform.zip releases.hashicorp.com/... && "
            "sudo unzip -o /tmp/terraform.zip -d /usr/local/bin && "
            "rm /tmp/terraform.zip",
        ],
    },
    "needs_sudo": {
        "apt": True, "dnf": True, "pacman": True,
        "snap": True, "brew": False, "_default": True,
    },
    "install_via": {"_default": "github_release"},
    "requires": {"binaries": ["curl", "unzip"]},
    "arch_map": {"x86_64": "amd64", "aarch64": "arm64", "armv7l": "arm"},
    "prefer": ["apt", "dnf", "pacman", "snap", "brew"],
    "verify": ["terraform", "--version"],
    "update": {
        "apt": ["bash", "-c", "apt-get update && apt-get install --only-upgrade terraform"],
        "dnf": ["dnf", "upgrade", "-y", "terraform"],
        "pacman": ["pacman", "-Syu", "--noconfirm", "terraform"],
        "snap": ["snap", "refresh", "terraform"],
        "brew": ["brew", "upgrade", "hashicorp/tap/terraform"],
        "_default": ["bash", "-c", "(same as install _default)"],
    },
}
```

---

## 8. Validation Results

```
Schema:    VALID (recipe + all method-family handlers + on_failure)
Coverage:  513/513 (100%) — 27 scenarios × 19 presets
Handlers:  2 apt + 1 dnf + 2 pacman + 1 snap + 1 brew + 5 _default
           + 3 github_release + 3 on_failure + 9 INFRA = 27 total
```

---

## 9. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "terraform"` |
| `data/recipes.py` | Added `category: "iac"` |
| `data/recipes.py` | Added `apt` method (HashiCorp GPG + repo + install) |
| `data/recipes.py` | Added `dnf` method (HashiCorp repo + install) |
| `data/recipes.py` | Added `pacman` method |
| `data/recipes.py` | Added `_default` binary download from releases.hashicorp.com |
| `data/recipes.py` | Added `install_via: {"_default": "github_release"}` |
| `data/recipes.py` | Added `requires: {"binaries": ["curl", "unzip"]}` |
| `data/recipes.py` | Updated `prefer` to include all PM methods |
| `data/recipes.py` | Added per-method `update` commands |
| `data/recipes.py` | Updated `brew` to use official `hashicorp/tap` |
| `data/tool_failure_handlers.py` | Added `terraform_gpg_repo_setup_failed` handler (2 options) |
| `data/tool_failure_handlers.py` | Added `terraform_repo_not_configured` handler (2 options) |
| `data/tool_failure_handlers.py` | Added `terraform_checkpoint_api_failed` handler (3 options) |
| `data/remediation_handlers.py` | Added `retry` to `VALID_STRATEGIES` |
| `data/recipe_schema.py` | Added `retry` to `_STRATEGY_FIELDS` |
| `data/recipes.py` | Upgraded `_default` from hardcoded `linux_amd64` to `{os}_{arch}` |
| `data/recipes.py` | Added `arch_map` for amd64/arm64/arm naming |

---

## 10. Future Enhancements

- **`zypper` method**: Add when HashiCorp publishes official SUSE repos.
- **OpenTofu alternative**: Some users may want OpenTofu (terraform fork).
  Could be a separate recipe entry.
- **BSL license handler**: Detect license acceptance prompts if HashiCorp
  adds them to future versions.
