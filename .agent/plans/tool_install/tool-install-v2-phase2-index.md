# Tool Install v2 — Phase 2 Index

## Context

Phase 1 (system detection) is **done and deployed**. The system now knows:
distro family, package manager, snap availability, systemd, sudo, root,
container status, library versions.

Phase 2 is the **recipe unification and resolver engine**. It replaces
the current flat, Debian-only, non-recursive install system with one
that handles the FULL lifecycle of a tool on ANY system:

1. **Pre-install** — repository setup, key import, prerequisites
2. **Install** — platform-correct command, dependency resolution
3. **Post-install** — service start, config, group membership, PATH setup
4. **Verify** — is the binary on PATH? correct version? can it run?
5. **Update** — how to bring an installed tool to the latest version

## The Full Scope — What Tool Management Actually Involves

### Pre-install: Repository Configuration

Some tools are NOT in the default system repos. Before `apt-get install`
can work, the repo must be added:

| Tool | Repo needed | What's involved |
|------|-------------|-----------------|
| Docker CE | Docker's official apt/dnf repo | Import GPG key + add apt source + apt-get update |
| GitHub CLI (gh) | GitHub's apt/dnf repo | Import GPG key + add apt source |
| Terraform | HashiCorp's apt/dnf repo | Import GPG key + add apt source |
| kubectl (via apt) | Kubernetes apt/dnf repo | Import GPG key + add apt source |
| Node.js (recent) | NodeSource repo | Run NodeSource setup script |

Current system avoids this by using snap for kubectl/terraform/gh/node,
and docker.io (Debian community package) instead of Docker CE.
But on systems without snap, the repo setup becomes necessary.

This is a **step type** the recipe format must support: `"type": "repo"`.

### Install: The Install Command

This is what the current system does. Platform-correct install command.
Already analyzed in Phase 2.2.

### Post-install: Configuration & Service Management

After installing the binary, some tools need additional setup:

| Tool | Post-install actions | Why |
|------|---------------------|-----|
| docker | `systemctl start docker` | Daemon must be running |
| docker | `systemctl enable docker` | Start on boot |
| docker | `usermod -aG docker $USER` | Run without sudo |
| docker (WSL2) | Different — needs systemd or Docker Desktop | WSL-specific |
| docker (container) | SKIP service start — Docker-in-Docker has its own rules | Container-specific |
| cargo/rustc | Add `~/.cargo/bin` to PATH | Binaries installed to ~/.cargo |
| go | Add `~/go/bin` to PATH | Go binaries install to ~/go |
| node (snap) | Symlinks may be needed for global npm | Snap confinement |
| gh | `gh auth login` | Needs authentication to be useful |
| trivy | `trivy image --download-db-only` | Needs vulnerability DB |

The recipe format must support `post_install` steps — ordered actions
to run after the install command succeeds.

### Post-install: Service Management Specifically

Services are a special case of post-install. They involve:
- **Start**: `systemctl start SERVICE` (or equivalent)
- **Enable**: `systemctl enable SERVICE` (start on boot)
- **Status check**: `systemctl is-active SERVICE`
- **No systemd**: on WSL1, containers, Alpine — different init systems
- **Root vs user**: some services run as user (podman), some as root (docker)

Tools that need service management:
| Tool | Service name | Needs systemd | What to do without systemd |
|------|-------------|---------------|--------------------------|
| docker | docker | Yes (daemon) | Manual `dockerd &` or Docker Desktop on WSL2 |
| snapd | snapd | Yes (snap itself) | Can't use snap at all |
| containerd | containerd | Yes (if standalone) | Manual start |

Not every tool needs services. Most don't. But docker is a critical one
and it's in our registry.

### Verify: Post-Install Verification

After installing, verify:
1. **Binary on PATH**: `shutil.which(cli)` — already done in current `install_tool()`
2. **Version check**: `tool --version` — currently only done for Rust mismatch
3. **Functional check**: can the tool actually do something? (e.g. `docker info`)
4. **PATH reload**: if the binary was installed to a new directory (cargo),
   the current shell session may not see it until PATH is reloaded

The recipe format can support a `verify` command — a quick command to run
after install to confirm it works. This also feeds into the audit system
(l0_detection re-scans tools after install).

### Update: How to Upgrade

Each install method has its own update mechanism:

| Install method | Update command | Notes |
|---------------|---------------|-------|
| pip | `pip install --upgrade X` | Updates in-place |
| npm | `npm update -g X` | Updates global package |
| cargo | `cargo install X` | Re-installs latest (compilation) |
| apt | `apt-get install --only-upgrade X` | Upgrade single package |
| dnf | `dnf upgrade X` | Upgrade single package |
| apk | `apk upgrade X` | Upgrade single package |
| pacman | `pacman -S X` | Reinstalls latest |
| zypper | `zypper update X` | Upgrade single package |
| brew | `brew upgrade X` | Upgrade formula |
| snap | `snap refresh X` | Upgrade snap |
| bash-curl | Re-run install script | Most bash scripts handle this |
| rustup | `rustup update` | Updates Rust toolchain |

The recipe format should include an `update` field so the system can
offer "Update" alongside "Install" when a tool is installed but outdated.

---

## What Gets Replaced

This is an active development project. Phase 2 **evolves** the existing
system. Pieces will be replaced:

| Current piece | Fate |
|---------------|------|
| `_NO_SUDO_RECIPES` | Merged into `TOOL_RECIPES` |
| `_SUDO_RECIPES` | Merged into `TOOL_RECIPES` |
| `CARGO_BUILD_DEPS` | Moved into per-recipe `requires.packages` |
| `_RUNTIME_DEPS` / `_TOOL_REQUIRES` | Replaced by `requires.binaries` |
| `check_system_deps()` (dpkg-only) | Replaced with multi-pm version |
| `install_tool()` | Replaced by plan-based execution |
| `ops-modal` (sudo password) | Replaced by `showStepModal` (Phase 3) |
| `_showDepsModal` | Replaced by `showStepModal` (Phase 3) |
| `streamCommand()` / dup SSE readers | Replaced by `streamSSE()` (Phase 3) |

---

## The Recipe Format Must Support

Based on the full lifecycle analysis above, a recipe entry needs:

```
label            — display name
cli              — binary to check (when ≠ tool id)
install          — per-pm install commands
needs_sudo       — per-method sudo flag
requires         — binaries + system packages
prefer           — method priority order
post_env         — PATH/env changes after install
post_install     — ordered steps after install (service start, config, group add)
verify           — command to confirm install works
update           — per-method update command
repo_setup       — per-pm repo add commands (GPG key, source list)
```

Not every tool needs every field. pip tools only need `install`.
Docker needs almost everything.

---

## Sub-Phases

Phase 2 is split into sub-phases. Each gets its own analysis document.
Each is implemented and verified before moving to the next.

### Phase 2.1 — Multi-Distro Package Checking

**File:** `tool-install-v2-phase2.1-package-checking.md` ✅ ANALYZED

**Scope:**
- `_is_pkg_installed(pkg, pkg_manager)` — check one package via dpkg/rpm/apk/pacman/brew
- `check_system_deps(packages, pkg_manager)` — replaces current dpkg-only version
- `_build_pkg_install_cmd(packages, pm)` — build install command per pm
- Update `/audit/check-deps` endpoint to auto-detect pm from system profile

**Why first:** Every later sub-phase needs the ability to check and install
system packages on any distro. This is the foundation.

**Files touched:** `tool_install.py`, `routes_audit.py`

---

### Phase 2.2 — Recipe Format & Dependency Declarations

**File:** `tool-install-v2-phase2.2-dependency-declarations.md` ✅ ANALYZED

**Scope:**
- Define the complete recipe format (install, requires, post_env,
  post_install, verify, update, repo_setup)
- Build the `TOOL_RECIPES` dict — ALL tools across ALL platforms
- Cross-platform package name mapping (every family)
- Dependency chains fully traced
- Replace `_NO_SUDO_RECIPES`, `_SUDO_RECIPES`, `CARGO_BUILD_DEPS`,
  `_RUNTIME_DEPS`, `_TOOL_REQUIRES`
- Update `_analyse_install_failure()` to use recipe data

**Why second:** The resolver (2.3) needs the data. The format must be
locked before resolver logic is written.

**Files touched:** `tool_install.py`

**NOTE:** The 2.2 analysis document needs to be UPDATED to include
post_install, verify, update, and repo_setup in the recipe format
and in the per-tool analysis.

---

### Phase 2.3 — Resolver Engine

**File:** `tool-install-v2-phase2.3-resolver-engine.md` (pending)

**Scope:**
- `_pick_install_method(recipe, primary_pm, snap_ok)` — select install command
- `_collect_deps(tool, ...)` — recursive depth-first dependency walker
- `resolve_install_plan(tool, system_profile)` — produces ordered step list
- Step types: `repo`, `packages`, `tool`, `post_install`, `verify`
- Post-env propagation (wrapping commands with PATH exports)
- Package batching (curl + libssl-dev in one apt-get call)
- `POST /audit/install-plan` endpoint

**Why third:** The resolver consumes the recipe data (2.2) and the
package checking (2.1). It can't be built without both.

**Files touched:** `tool_install.py`, `routes_audit.py`

---

### Phase 2.4 — Install Execution & Replacement

**File:** `tool-install-v2-phase2.4-install-execution.md` (pending)

**Scope:**
- Replace `install_tool()` with plan-based execution
- Step-by-step execution via `/audit/remediate` (SSE streaming)
- sudo password handling across multi-step plans
- Step success/failure tracking
- Post-install verification (verify step)
- Service management (start/enable step)
- Cache invalidation after successful installs
- Remove ALL old recipe data structures

**Why fourth:** The old `install_tool()` can only be removed after
the new resolver (2.3) and recipe data (2.2) are in place.

**Files touched:** `tool_install.py`, `routes_audit.py`

---

### Phase 2.5 — Update & Maintenance

**File:** `tool-install-v2-phase2.5-update-maintenance.md` (pending)

**Scope:**
- `POST /audit/update-tool` endpoint or extend install-plan with action param
- Per-method update commands from recipe `update` field
- Version detection (current vs latest)
- "Update available" indicators in the audit UI
- Bulk update capability

**Why fifth:** Updates build on top of the install system. The recipes
must be in place first, with update commands defined.

**Files touched:** `tool_install.py`, `routes_audit.py`, potentially UI

---

## Dependencies Between Sub-Phases

```
Phase 1 (done) ──→ Phase 2.1 ──→ Phase 2.2 ──→ Phase 2.3 ──→ Phase 2.4 ──→ Phase 2.5
  system profile     pkg check     recipes       resolver      execution      updates
```

Each sub-phase builds on the previous. No sub-phase can be skipped.

## Reference Documents

- `tool-install-v2-analysis.md` — original deep analysis of the whole system
- `tool-install-v2-phase1-system-detection.md` — Phase 1 plan (done)
- `tool-install-v2-phase2-recipe-unification_draft.md` — early draft (superseded)
- `tool-install-v2-phase2.1-package-checking.md` — Phase 2.1 analysis ✅
- `tool-install-v2-phase2.2-dependency-declarations.md` — Phase 2.2 analysis ✅
- `tool-install-v2-phase2.3-resolver-engine.md` — Phase 2.3 analysis ✅
- `tool-install-v2-phase2.3-scenarios.md` — 55 resolver scenarios ✅
- `tool-install-v2-scope-expansion.md` — **Scope expansion: decision trees,
  choices, GPU, build-from-source, ML, data packs, config, restarts**

## Future Phases (Beyond Phase 2)

Phase 2 handles SIMPLE recipes (35+ devops tools). The scope expansion
doc defines the path to a full provisioning system:

```
Phase 3  Frontend (step modal, plan display)
Phase 4  Decision trees (choices, inputs, constraints, branches)
Phase 5  Build-from-source support
Phase 6  Hardware detection (GPU, kernel config)
Phase 7  Data packs & downloads
Phase 8  System configuration & restart management
```

Phase 2's architecture is designed for growth — adding `choices` to
a recipe later doesn't break existing recipes. See scope expansion doc.
