# Domain: Repositories

> ⚠️ **PHASE LABELS MAY BE STALE** — As of 2026-02-25, code has evolved far beyond
> what the phase roadmaps suggest. Many features labeled "Phase 4-8 future" are
> ALREADY IMPLEMENTED. See `audit-domain-docs.md` and `audit-missing-pieces.md`
> for the verified truth. Code is the source of truth, not these phase labels.


> This document catalogs all repository types the tool install system
> encounters, how they're configured, authenticated, and trusted.
> Covers system PM repos, language PM registries, and third-party
> sources.
>
> SOURCE DOCS: scope-expansion §2.3 (repo types table),
>              phase2.2 §repo_setup (recipe format, Docker CE example),
>              arch-recipe-format §repo_setup (canonical schema)

---

## Overview

A "repository" is any source from which packages/binaries are fetched.
Repos matter for tool installation because some tools are NOT in a
system's default repos and require additional repo configuration.

### When repo setup is needed

| Situation | Example | Repo setup? |
|-----------|---------|------------|
| Tool in default system repos | git, curl, jq | **No** |
| Tool in official vendor repo | Docker CE, GitHub CLI | **Yes** — GPG key + source list |
| Tool via language PM | ruff (pip), eslint (npm) | **No** — uses default registry |
| Tool via language PM + private mirror | Internal PyPI | **Yes** — custom index URL |
| Tool via binary download | kubectl, helm | **No** — direct URL |
| Tool via snap | kubectl, terraform | **No** — Canonical store is default |

### Phase 2 stance

In Phase 2, we avoid repo setup by:
- Using `docker.io` (community) instead of Docker CE (official repo)
- Using snap/brew/binary for kubectl, terraform (instead of apt repo)
- Using snap for gh (instead of GitHub CLI apt repo)

Repo setup is DOCUMENTED in Phase 2.2 but only POPULATED when we
add install variants that require non-default repos.

---

## System PM Repositories

### apt repositories (Debian family)

**Components:**
1. GPG signing key — verifies package authenticity
2. Sources list entry — tells apt WHERE to fetch packages
3. `apt-get update` — refreshes package index after adding source

**Modern approach (Debian 12+ / Ubuntu 22.04+):**
```bash
# 1. Download and install GPG key
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# 2. Add source with signed-by pointing to the key
echo "deb [arch=$(dpkg --print-architecture) \
    signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
    > /etc/apt/sources.list.d/docker.list

# 3. Refresh index
apt-get update
```

**Legacy approach (deprecated):**
```bash
# apt-key is deprecated since Debian 11
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -
add-apt-repository "deb https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
```

**Key storage locations:**
- Modern: `/etc/apt/keyrings/` (per-repo key files)
- Legacy: `/etc/apt/trusted.gpg` (single keyring, deprecated)
- Legacy: `/etc/apt/trusted.gpg.d/` (directory of keyrings)

**Source file locations:**
- `/etc/apt/sources.list` — main sources (distro repos)
- `/etc/apt/sources.list.d/*.list` — third-party repos
- `/etc/apt/sources.list.d/*.sources` — new DEB822 format

**Recipe format:**
```python
"repo_setup": {
    "apt": [
        {"label": "Install prerequisites",
         "command": ["apt-get", "install", "-y",
                     "ca-certificates", "curl", "gnupg"],
         "needs_sudo": True},
        {"label": "Add Docker GPG key",
         "command": ["bash", "-c",
                     "install -m 0755 -d /etc/apt/keyrings && "
                     "curl -fsSL https://download.docker.com/linux/"
                     "$(. /etc/os-release && echo $ID)/gpg "
                     "| gpg --dearmor -o /etc/apt/keyrings/docker.gpg"],
         "needs_sudo": True},
        {"label": "Add Docker apt repo",
         "command": ["bash", "-c",
                     'echo "deb [arch=$(dpkg --print-architecture) '
                     'signed-by=/etc/apt/keyrings/docker.gpg] '
                     'https://download.docker.com/linux/'
                     '$(. /etc/os-release && echo $ID) '
                     '$(. /etc/os-release && echo $VERSION_CODENAME) '
                     'stable" > /etc/apt/sources.list.d/docker.list'],
         "needs_sudo": True},
        {"label": "Update package index",
         "command": ["apt-get", "update"],
         "needs_sudo": True},
    ],
},
```

**Tools that would need apt repo setup:**

| Tool | Repo source | Key URL | Status |
|------|-----------|---------|--------|
| Docker CE | download.docker.com | `docker.com/.../gpg` | Documented, not used (using docker.io instead) |
| GitHub CLI (gh) | cli.github.com | `github.com/cli/cli/...` | Documented, not used (using snap instead) |
| kubectl | pkgs.k8s.io | `kubernetes.io/...` | Documented, not used (using snap/binary instead) |
| Terraform | apt.releases.hashicorp.com | `hashicorp.com/...` | Documented, not used (using snap instead) |
| Node.js (newer) | deb.nodesource.com | `nodesource.com/...` | Not populated (system version sufficient) |

### PPA (Ubuntu-only)

**Personal Package Archives** — Ubuntu-specific third-party repos:

```bash
add-apt-repository ppa:deadsnakes/ppa
apt-get update
```

**What `add-apt-repository` does:**
1. Adds signing key from Launchpad
2. Creates source file in `/etc/apt/sources.list.d/`
3. Runs `apt-get update`

**Recipe format (conceptual):**
```python
"repo_setup": {
    "ppa": {
        "type": "ppa",
        "name": "ppa:deadsnakes/ppa",
    },
},
```

**Phase 2:** No PPA-based tools. PPAs are Ubuntu-specific (not
cross-distro) and should be avoided for portable recipes.

### dnf/yum repositories (RHEL family)

**Components:**
1. RPM GPG key — imported into rpm keyring
2. Repo file — `.repo` file in `/etc/yum.repos.d/`
3. `dnf makecache` — refreshes metadata (optional, auto-refreshes)

**Setup pattern:**
```bash
# 1. Import GPG key
rpm --import https://download.docker.com/linux/fedora/gpg

# 2. Add repo file
dnf config-manager --add-repo \
    https://download.docker.com/linux/fedora/docker-ce.repo

# Or manually create /etc/yum.repos.d/docker-ce.repo:
[docker-ce-stable]
name=Docker CE Stable
baseurl=https://download.docker.com/linux/fedora/$releasever/$basearch/stable
gpgcheck=1
gpgkey=https://download.docker.com/linux/fedora/gpg
```

**Repo file locations:**
- `/etc/yum.repos.d/*.repo`

**Recipe format:**
```python
"repo_setup": {
    "dnf": [
        {"label": "Import Docker GPG key",
         "command": ["rpm", "--import",
                     "https://download.docker.com/linux/fedora/gpg"],
         "needs_sudo": True},
        {"label": "Add Docker repo",
         "command": ["dnf", "config-manager", "--add-repo",
                     "https://download.docker.com/linux/fedora/docker-ce.repo"],
         "needs_sudo": True},
    ],
},
```

### COPR (Fedora community)

**Community-maintained repos for Fedora:**

```bash
dnf copr enable user/project
```

Similar to Ubuntu's PPA. Not used in Phase 2.

### apk repositories (Alpine)

**Alpine's repo system is simpler:**

```
# /etc/apk/repositories
https://dl-cdn.alpinelinux.org/alpine/v3.19/main
https://dl-cdn.alpinelinux.org/alpine/v3.19/community
```

**Setup:** Enable the `community` repository (may be commented out
in minimal Alpine containers). Most tools we need are in `community`.

```bash
# Enable community repo (if commented out)
sed -i 's|#.*community|community|' /etc/apk/repositories
apk update
```

No GPG key management needed — Alpine signs repos at the index level.

### pacman repositories (Arch family)

**Arch repos in `/etc/pacman.conf`:**

```ini
[core]
Include = /etc/pacman.d/mirrorlist

[extra]
Include = /etc/pacman.d/mirrorlist

[community]
Include = /etc/pacman.d/mirrorlist
```

**AUR (Arch User Repository):** Community-maintained packages
built from source via `makepkg`. Accessed through helpers
like `yay` or `paru`.

**Phase 2:** We do NOT use AUR. It requires:
- Manual review of PKGBUILD files
- `makepkg` invocation
- Trusting community maintainers

Too risky for automated installs.

### zypper repositories (SUSE family)

```bash
# Add a repo
zypper addrepo https://download.docker.com/linux/sles/docker-ce.repo docker-ce

# Refresh
zypper refresh
```

Key management: `rpm --import` (same as dnf/yum, shares rpm keyring).

### Homebrew taps

**Taps are third-party formula repos for brew:**

```bash
# Add a tap
brew tap hashicorp/tap

# Install from tap
brew install hashicorp/tap/terraform
```

**Phase 2:** No tap-based tools. All tools we install are in the
default Homebrew core tap.

**Recipe format (conceptual):**
```python
"repo_setup": {
    "brew_tap": {
        "type": "tap",
        "name": "hashicorp/tap",
    },
},
```

---

## Language PM Registries

### PyPI (pip)

| Property | Value |
|----------|-------|
| **Default** | `https://pypi.org/simple/` |
| **Config** | `pip config set global.index-url <url>` |
| **Config file** | `~/.config/pip/pip.conf` or `~/.pip/pip.conf` |
| **Env var** | `PIP_INDEX_URL` |
| **Auth** | Basic HTTP auth, token, or keyring integration |

**Private index (Phase 4+):**
```python
# Override index per command
_PIP + ["install", "--index-url", "https://pypi.internal.com/simple/", "ruff"]

# Extra index (falls back to PyPI)
_PIP + ["install", "--extra-index-url", "https://pypi.internal.com/simple/", "ruff"]
```

**PyTorch special indexes:**
```
CPU:       https://download.pytorch.org/whl/cpu
CUDA 11.8: https://download.pytorch.org/whl/cu118
CUDA 12.1: https://download.pytorch.org/whl/cu121
ROCm 5.7:  https://download.pytorch.org/whl/rocm5.7
```

### npmjs (npm)

| Property | Value |
|----------|-------|
| **Default** | `https://registry.npmjs.org/` |
| **Config** | `npm config set registry <url>` |
| **Config file** | `~/.npmrc` |
| **Env var** | `NPM_CONFIG_REGISTRY` |
| **Auth** | Token in .npmrc: `//registry.npmjs.org/:_authToken=...` |

**Scoped registries:**
```ini
# .npmrc — different registry for @company packages
@company:registry=https://npm.internal.com/
//npm.internal.com/:_authToken=TOKEN
```

### crates.io (cargo)

| Property | Value |
|----------|-------|
| **Default** | `https://index.crates.io/` |
| **Config** | `.cargo/config.toml` |
| **Auth** | Token via `cargo login` |

**Alternative registries (.cargo/config.toml):**
```toml
[registries.my-registry]
index = "https://my-intranet.local/git/index"

[source.crates-io]
replace-with = "my-registry"
```

---

## Trust Model

### GPG key trust

| PM type | How keys are trusted | Key storage |
|---------|---------------------|-------------|
| apt (modern) | Per-repo `signed-by=` in source file | `/etc/apt/keyrings/` |
| apt (legacy) | Global `apt-key add` | `/etc/apt/trusted.gpg` |
| rpm (dnf/yum/zypper) | `rpm --import` adds to rpm keyring | RPM keyring |
| pacman | Key packages + `pacman-key` | `/etc/pacman.d/gnupg/` |
| apk | Index-level signatures | Built into apk |
| brew | Git commit signing on core tap | GitHub signatures |

### HTTPS as trust baseline

For tools we install:
- All binary download URLs use HTTPS
- All install scripts use HTTPS
- All language PM registries use HTTPS by default
- rustup enforces `--proto '=https' --tlsv1.2`

### Risk levels per source type

| Source | Trust level | Phase 2 usage |
|--------|------------|---------------|
| Default system repos | **High** — distro maintainers | ✅ Primary method |
| Official vendor repos | **High** — project maintainers + GPG | Referenced but not used |
| Language registries (pypi, npm, crates.io) | **Medium-High** — package author trust | ✅ For pip/npm/cargo tools |
| curl-pipe-bash from official URL | **Medium** — HTTPS + vendor trust | ✅ For rustup, helm, trivy |
| Direct binary from vendor CDN | **Medium** — HTTPS only, no signature | ✅ For kubectl, skaffold |
| PPA / COPR / AUR | **Low-Medium** — community trust | ❌ Not used |
| Unknown third-party | **Low** | ❌ Never used |

---

## Repo Setup in the Recipe System

### Schema (from arch-recipe-format)

```python
"repo_setup": dict[str, list[dict]],
# Keys match PM IDs: "apt", "dnf", etc.
# Values: ordered list of step dicts:
#   {
#     "label": str,           # human-readable description
#     "command": list[str],   # subprocess.run() command
#     "needs_sudo": bool,     # does this step need sudo?
#   }
```

### When repo_setup runs

In the resolver's plan generation:

```
1. repo_setup steps (if present for selected PM)
2. requires.packages install (system dev headers)
3. requires.binaries install (runtime dependencies)
4. Install command (the tool itself)
5. post_install steps
6. verify step
```

Repo setup is ALWAYS step 1 — before anything else for that tool.

### Which tools currently have repo_setup populated?

| Tool | repo_setup populated? | Why / why not |
|------|----------------------|--------------|
| docker | ❌ Not populated | Using docker.io (in default repos) |
| gh | ❌ Not populated | Using snap |
| kubectl | ❌ Not populated | Using snap/binary |
| terraform | ❌ Not populated | Using snap |
| ruff, mypy, etc. | ❌ Not applicable | pip tools, no system repo |
| eslint, prettier | ❌ Not applicable | npm tools, no system repo |
| git, curl, jq | ❌ Not applicable | In default repos |
| helm, trivy | ❌ Not applicable | Using binary download |

**Phase 2 result:** `nvidia-driver` uses `repo_setup` (PPA for apt).
Other Phase 2 tools avoid it by using snap/brew/binary alternatives.

---

## Default Repos per Platform

What's available without any repo setup:

| Platform | Default repos | Notable packages available |
|----------|-------------|--------------------------|
| Ubuntu | main, universe, multiverse, restricted | Most common tools |
| Debian | main, contrib, non-free | Most (fewer than Ubuntu) |
| Fedora | fedora, updates | Most common tools |
| RHEL | BaseOS, AppStream | Enterprise subset |
| Alpine | main, community (may need enabling) | Minimal set |
| Arch | core, extra, community | Very broad |
| openSUSE | oss, non-oss, update | Broad |
| macOS (brew) | homebrew-core, homebrew-cask | Very broad |

### Alpine community repo

In minimal Alpine containers, the `community` repo may be disabled:

```
# /etc/apk/repositories — minimal container
https://dl-cdn.alpinelinux.org/alpine/v3.19/main
#https://dl-cdn.alpinelinux.org/alpine/v3.19/community  ← commented out
```

Some tools (e.g., npm, go) are in `community`, not `main`.
Enabling: `sed -i 's|#.*community|&\n&|;s|#||2' /etc/apk/repositories`

This is an edge case the resolver should detect (NOT IMPLEMENTED).

---

## Edge Cases

### Stale package index

| PM | Problem | Solution |
|----|---------|---------|
| apt | `apt-get update` not run → "Unable to locate package" | Run `apt-get update` before install |
| apk | `apk update` not run in container → missing packages | Run `apk update` |
| pacman | `pacman -Sy` not run → old DB → package not found | Run `pacman -Sy` |
| dnf | Auto-refreshes if stale | No action needed |
| brew | Auto-updates before install | No action needed (but slow) |

### Repo key expiry

GPG keys have expiration dates. When a key expires:
- apt: `The following signatures were invalid: EXPKEYSIG`
- rpm: `FAILED (key expired)`
- Fix: re-import the updated key from the vendor

Not handled in Phase 2. The error analysis can detect the signature
and suggest re-importing the key.

### Duplicate repos

Adding the same repo twice is usually harmless:
- apt: warns about duplicate sources, fetches once
- dnf: silently ignores duplicate
- brew tap: already tapped, no error

The recipe's `repo_setup` should be idempotent — safe to re-run.

### Corporate proxies blocking repos

Some environments block access to external repos:
- PyPI, npmjs, crates.io may be unreachable
- GitHub (for binary downloads) may be blocked
- Detection: network endpoint probing (Phase 4)
- Mitigation: private mirrors, proxy config

---

## Traceability

| Topic | Source |
|-------|--------|
| Repo types table | scope-expansion §2.3 |
| repo_setup schema | arch-recipe-format §repo_setup |
| repo_setup field | phase2.2 §repo_setup (with Docker CE example) |
| Docker CE repo steps | phase2.2 §Category 9 (full apt setup) |
| Tools needing repos | phase2.2 §repo_setup note (docker, gh, kubectl, terraform) |
| Private registries | scope-expansion §2.15 |
| PyTorch indexes | scope-expansion §2.9 (GPU variant) |
| Network detection | scope-expansion §2.16 |
| Phase 2 stance | phase2.2 §repo_setup note (documented but not populated) |
