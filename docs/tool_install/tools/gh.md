# gh — Full Spectrum Analysis

> **Tool ID:** `gh`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | GitHub CLI — GitHub from the terminal |
| Language | Go |
| CLI binary | `gh` |
| Category | `scm` |
| Verify command | `gh --version` |
| Recipe key | `gh` |

### Special notes
- GitHub CLI is GitHub's **official** command-line tool for GitHub.
- The binary is a **single statically-linked Go binary** — no runtime deps.
- GitHub maintains **official package repositories** for apt and RPM-based
  distros, requiring GPG key + repo setup before install.
- The `apt` install requires downloading the GPG keyring from
  `cli.github.com/packages/githubcli-archive-keyring.gpg`.
- The `dnf` and `zypper` installs use the same RPM repo at
  `cli.github.com/packages/rpm/gh-cli.repo`.
- **Snap is officially discouraged** by the GitHub CLI team due to
  numerous runtime issues. It's kept in the recipe for compatibility
  but excluded from the `prefer` list.
- Package name is `gh` on apt/dnf/zypper/brew but `github-cli` on
  apk (Alpine) and pacman (Arch).

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `gh` | **Official** — requires GPG key + repo setup |
| `dnf` | ✅ | `gh` | **Official** — requires RPM repo config |
| `apk` | ✅ | `github-cli` | Community — Alpine community repo |
| `pacman` | ✅ | `github-cli` | Community — Arch extra repo |
| `zypper` | ✅ | `gh` | **Official** — uses same RPM repo as dnf |
| `brew` | ✅ | `gh` | **Official** support |
| `snap` | ⛔ | `gh` | **Officially discouraged** by GitHub CLI team |
| `pip` | ❌ | — | Not available |
| `npm` | ❌ | — | Not available |
| `cargo` | ❌ | — | Not available |
| `go` | ❌ | — | Not a `go install` tool |

### Package name notes
- **apt/dnf/zypper/brew:** Package name is `gh`.
- **apk/pacman:** Package name is `github-cli` (different!).
  The install and update commands specify the correct name per method.
- **snap:** Functional but maintainers explicitly recommend against it.
  Excluded from `prefer` list but available as fallback.

---

## 3. Binary Download (_default)

| Field | Value |
|-------|-------|
| Source | https://github.com/cli/cli/releases |
| URL pattern | `https://github.com/cli/cli/releases/download/v{version}/gh_{version}_{os}_{arch}.tar.gz` |
| Archive format | `.tar.gz` (contains `bin/gh` + man pages + completions) |
| Install location | `/usr/local/bin/gh` (via `--strip-components=1`) |
| Dependencies | `curl` (download + version discovery) |
| needs_sudo | Yes (writes to `/usr/local/`) |

### Version resolution
Latest version resolved via GitHub API:
```
curl -sSf https://api.github.com/repos/cli/cli/releases/latest
```
Extracts `tag_name` (e.g. `v2.48.0`) via grep + sed.

### Architecture support

| Architecture | Archive suffix |
|-------------|---------------|
| x86_64 | `linux_amd64.tar.gz` |
| aarch64 (ARM64) | `linux_arm64.tar.gz` |
| armv7l (ARM 32) | `linux_armv6.tar.gz` |

The `_default` command uses `{os}` and `{arch}` placeholders with
`arch_map` for Go-standard naming. Note: armv7l maps to `armv6`
(GitHub CLI publishes armv6 builds, compatible with armv7l).

### OS support
GitHub CLI publishes for Linux, macOS (darwin), Windows.
macOS users should prefer `brew`.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For `_default` install and version discovery |
| Runtime | None | Self-contained static binary |

### Reverse deps
gh is referenced by:
- CI/CD workflows using `gh pr`, `gh release`, `gh run`
- `act` — local GitHub Actions runner
- Various DevOps automation scripts

---

## 5. Post-install

No PATH additions or shell configuration needed. The binary is
installed to `/usr/local/bin/` (via `_default`) or standard package
locations (via PM installs).

For full functionality, users should authenticate with `gh auth login`.

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
| `apk` | `apk_unsatisfiable` | Dependency conflict |
| `apk` | `apk_locked` | Database locked |
| `pacman` | `pacman_target_not_found` | Package not found |
| `pacman` | `pacman_locked` | Database locked |
| `zypper` | `zypper_not_found` | Package not found |
| `zypper` | `zypper_locked` | zypper locked |
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
| `gh_gpg_repo_setup_failed` | configuration | GPG key import fails, keyring permission denied, cli.github.com unreachable, RPM repo add fails | Switch to `_default` binary (recommended), switch to `brew` |
| `gh_repo_not_configured` | configuration | `Unable to locate package gh` / package has no installation candidate | Switch to `_default` binary (recommended), switch to `brew` |

---

## 7. Recipe Structure

```python
"gh": {
    "cli": "gh",
    "label": "GitHub CLI (GitHub from the terminal)",
    "category": "scm",
    "install": {
        "apt":     ["bash", "-c", "wget GPG key && add repo && apt install gh"],
        "dnf":     ["bash", "-c", "add repo && dnf install gh"],
        "apk":     ["apk", "add", "github-cli"],
        "pacman":  ["pacman", "-S", "--noconfirm", "github-cli"],
        "zypper":  ["bash", "-c", "add repo && zypper install gh"],
        "brew":    ["brew", "install", "gh"],
        "snap":    ["snap", "install", "gh"],
        "_default": [
            "bash", "-c",
            "GH_VERSION=$(curl GitHub API) && "
            "curl -o /tmp/gh.tar.gz releases/v.../gh_{os}_{arch}.tar.gz && "
            "sudo tar -xzf -C /usr/local --strip-components=1 && "
            "rm /tmp/gh.tar.gz",
        ],
    },
    "needs_sudo": {
        "apt": True, "dnf": True, "apk": True,
        "pacman": True, "zypper": True,
        "brew": False, "snap": True, "_default": True,
    },
    "install_via": {"_default": "github_release"},
    "requires": {"binaries": ["curl"]},
    "arch_map": {"x86_64": "amd64", "aarch64": "arm64", "armv7l": "armv6"},
    "prefer": ["apt", "dnf", "apk", "pacman", "zypper", "brew"],
    "verify": ["gh", "--version"],
    "update": { ... per-method update commands ... },
}
```

---

## 8. Validation Results

```
Schema:    VALID (recipe + all method-family + on_failure handlers)
Coverage:  570/570 (100%) — 30 scenarios × 19 presets
Handlers:  2 apt + 1 dnf + 2 apk + 2 pacman + 2 zypper + 1 brew
           + 1 snap + 5 _default + 3 github_release + 2 on_failure
           + 9 INFRA = 30 total
```

---

## 9. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "gh"` |
| `data/recipes.py` | Added `category: "scm"` |
| `data/recipes.py` | Updated label to `"GitHub CLI (GitHub from the terminal)"` |
| `data/recipes.py` | Added `apt` method (GitHub GPG key + repo + install) |
| `data/recipes.py` | Added `dnf` method (GitHub RPM repo + install) |
| `data/recipes.py` | Added `apk` method (package name `github-cli`) |
| `data/recipes.py` | Added `pacman` method (package name `github-cli`) |
| `data/recipes.py` | Added `zypper` method (GitHub RPM repo + install) |
| `data/recipes.py` | Added `_default` binary download from GitHub releases |
| `data/recipes.py` | Added `install_via: {"_default": "github_release"}` |
| `data/recipes.py` | Added `requires: {"binaries": ["curl"]}` |
| `data/recipes.py` | Added `arch_map` for amd64/arm64/armv6 naming |
| `data/recipes.py` | Updated `prefer` to prioritize official PMs over snap |
| `data/recipes.py` | Added per-method `update` commands |
| `data/tool_failure_handlers.py` | Added `gh_gpg_repo_setup_failed` handler (2 options) |
| `data/tool_failure_handlers.py` | Added `gh_repo_not_configured` handler (2 options) |

---

## 10. Future Enhancements

- **Auth integration**: Post-install `gh auth login` guidance.
- **Extension support**: `gh extension install` for additional functionality.
- **Remove snap**: Consider removing snap entirely given official discouragement.
