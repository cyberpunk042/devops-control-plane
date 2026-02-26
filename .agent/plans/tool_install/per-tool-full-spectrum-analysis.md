# Per-Tool Full Spectrum Analysis

## What This Document Is

This is the complete, uncompressed analysis of what it takes to properly
cover ONE tool through the entire remediation system. It serves as the
foundation for writing the actual per-tool workflow.

Nothing here is optional. Nothing is reduced. Every item must be addressed
for each tool.

---

## The Files Involved

| File | What lives there | What changes per tool |
|------|-----------------|----------------------|
| `src/core/services/tool_install/data/recipes.py` | `TOOL_RECIPES` — install instructions per PM | Recipe entry (new or updated) |
| `src/core/services/tool_install/data/remediation_handlers.py` | `METHOD_FAMILY_HANDLERS` — failure patterns + options per install method | Handler entries if tool introduces new failure patterns |
| `src/core/services/tool_install/data/remediation_handlers.py` | `INFRA_HANDLERS` — cross-method failure patterns (network, disk, etc.) | Handler entries if tool exposes infrastructure failures |
| `src/core/services/tool_install/data/remediation_handlers.py` | `BOOTSTRAP_HANDLERS` — bootstrap-level failures (no PM, no sudo, etc.) | Rarely changes, but may if tool has unique bootstrap needs |
| `src/core/services/tool_install/data/remediation_handlers.py` | `LIB_TO_PACKAGE_MAP` — C library name → system package name per distro | New entries if tool depends on C libraries |
| `src/core/services/tool_install/resolver/dynamic_dep_resolver.py` | `KNOWN_PACKAGES` — tool/dep name → system package name per PM | New entries if tool or its deps have different package names per distro |
| `src/core/services/tool_install/resolver/dynamic_dep_resolver.py` | `resolve_dep_install()` — 4-tier resolution logic | May need new tiers, new special installers, logic fixes |
| `src/core/services/tool_install/resolver/dependency_collection.py` | `_collect_deps()` — recursive dep tree walker | May need changes if tool has unusual dep shapes (repos to add, custom installers, etc.) |
| `src/core/services/tool_install/domain/remediation_planning.py` | `_compute_availability()` — ready/locked/impossible per option per system | May need new gates if tool exposes new capability requirements |
| `src/core/services/tool_install/domain/remediation_planning.py` | `_check_dep_availability()` — dep availability check with dynamic resolver | May need refinement for new dep patterns |
| `src/core/services/dev_scenarios.py` | `SYSTEM_PRESETS` — 19 simulated OS profiles | May need new fields if this tool requires a capability not yet tracked |
| `tests/test_remediation_coverage.py` | Validation test — 6 checks across all presets | May need new allowlist entries, new expected tools, updated assertions |

---

## Recipe Fields (recipes.py)

For each tool, the recipe entry must include:

### Required fields

| Field | Description | Example |
|-------|-------------|---------|
| `cli` | Binary name that `shutil.which()` looks for | `"act"` |
| `label` | Human-readable display name | `"act (local GitHub Actions)"` |
| `category` | Stack/category tag | `"cicd"` |
| `install` | Dict of install method → command list | See below |
| `verify` | Command to verify the tool works post-install | `["act", "--version"]` |

### Install methods (one per package manager where the tool is available)

Each method is a key in `install` with a command list value.

#### System package manager methods

| Method key | When it applies | Example value |
|------------|----------------|---------------|
| `apt` | Tool is in Debian/Ubuntu repos | `["apt-get", "install", "-y", "act"]` |
| `dnf` | Tool is in Fedora/RHEL repos | `["dnf", "install", "-y", "act"]` |
| `apk` | Tool is in Alpine repos | `["apk", "add", "act"]` |
| `pacman` | Tool is in Arch repos (or AUR) | `["pacman", "-S", "--noconfirm", "act"]` |
| `zypper` | Tool is in openSUSE repos | `["zypper", "install", "-y", "act"]` |
| `brew` | Tool is in Homebrew | `["brew", "install", "act"]` |
| `snap` | Tool is available as a snap | `["snap", "install", "act"]` |

#### Language ecosystem methods

| Method key | When it applies | Example value |
|------------|----------------|---------------|
| `pip` | Python tool via pip | `[sys.executable, "-m", "pip", "install", "act"]` |
| `npm` | Node tool via npm | `["npm", "install", "-g", "act"]` |
| `cargo` | Rust tool via cargo | `["cargo", "install", "act"]` |
| `go` | Go tool via go install | `["go", "install", "github.com/user/tool@latest"]` |

#### Binary download (`_default`)

This is the most universal install path. Almost every modern CLI tool publishes
pre-compiled binaries on GitHub Releases or their own site. The recipe must
handle ALL of the following per-tool concerns:

**Architecture detection:**
- The download URL must select the right binary for the system architecture
- x86_64 / amd64 (most systems)
- aarch64 / arm64 (Raspberry Pi, Apple Silicon, ARM servers, Graviton)
- armv7 / armhf (older ARM boards)
- Some tools only publish for x86_64 — on ARM they may not be available at all
  (this becomes an `arch_exclude` in remediation)

**OS detection:**
- The download URL must select the right binary for the OS
- linux (most servers/containers)
- darwin (macOS)
- windows (rare in our context but some tools support it)
- Some tools use different archive formats per OS (tar.gz on Linux, zip on macOS)

**URL patterns — each tool has its own:**
- GitHub Releases: `https://github.com/{org}/{repo}/releases/download/v{version}/{tool}_{version}_{os}_{arch}.tar.gz`
- Direct site: `https://tool.dev/download/{version}/tool-{os}-{arch}`
- Installer scripts: `curl -sSfL https://raw.githubusercontent.com/{org}/{repo}/master/install.sh | bash`
- Some tools use different naming conventions for OS (linux vs Linux vs linux-gnu)
- Some tools use different naming conventions for arch (amd64 vs x86_64 vs 64bit)

**Archive extraction:**
- `.tar.gz` / `.tgz` → `tar -xzf`
- `.tar.xz` → `tar -xJf`
- `.tar.bz2` → `tar -xjf`
- `.zip` → `unzip`
- `.deb` → `dpkg -i` (Debian/Ubuntu direct deb download)
- `.rpm` → `rpm -i` (RHEL/Fedora direct rpm download)
- `.AppImage` → `chmod +x` (Linux desktop)
- Raw binary (no archive) → `chmod +x` directly

**Post-download steps:**
- Move binary to the correct location:
  - `/usr/local/bin/` (needs sudo, system-wide)
  - `~/.local/bin/` (user-level, no sudo)
  - Tool-specific location (e.g. `~/.cargo/bin/`, `~/.local/share/tool/`)
- Set executable permission: `chmod +x`
- Verify checksum/signature (some tools publish SHA256SUMS or .sig files)
- Clean up temporary download files

**Dependencies for binary download:**
- `curl` or `wget` — to download
- `tar` — to extract archives
- `unzip` — for zip archives
- `jq` — some install scripts need it to parse GitHub API responses
- `gpg` — for signature verification

**Example recipe value (multi-step):**
```python
"_default": [
    "bash", "-c",
    "curl -sSfL https://github.com/nektos/act/"
    "releases/latest/download/act_Linux_x86_64.tar.gz"
    " | tar -xz -C /usr/local/bin act",
],
```

**Example recipe value (installer script):**
```python
"_default": [
    "bash", "-c",
    "curl -sSfL https://raw.githubusercontent.com/nektos/act/"
    "master/install.sh | sudo bash",
],
```

#### Build from source (`source`)

This is the fallback when no binary download or package exists. It is also
the path for users who want a specific version, patched build, or are on an
unsupported architecture. Each tool has its own build system and requirements:

**Build systems — each tool uses one:**
- `make` / `Makefile` → `./configure && make && make install`
- `cmake` → `mkdir build && cd build && cmake .. && make && make install`
- `meson` + `ninja` → `meson setup build && ninja -C build && ninja -C build install`
- `autotools` → `autoreconf -i && ./configure && make && make install`
- `cargo` (Rust) → `cargo build --release` (binary in `target/release/`)
- `go build` (Go) → `go build -o /usr/local/bin/tool .`
- `pip install .` (Python) → from cloned repo
- `npm install` (Node) → from cloned repo
- `gradle` / `maven` (Java) → `./gradlew build` or `mvn package`
- Custom build script → `./build.sh`, `make.sh`, etc.

**Source acquisition:**
- `git clone` from the project's repo (needs `git`)
- `curl` / `wget` a source tarball from GitHub releases
- Some tools need a specific branch, tag, or commit

**Build dependencies — per distro family:**
- **Compiler toolchain:**
  - Debian: `build-essential` (includes gcc, g++, make)
  - RHEL: `gcc`, `gcc-c++`, `make` (or `@development-tools` group)
  - Alpine: `build-base` (includes gcc, g++, make, libc-dev)
  - Arch: `base-devel` (includes gcc, make, etc.)
  - openSUSE: `gcc`, `gcc-c++`, `make`
  - macOS: Xcode Command Line Tools (`xcode-select --install`)

- **Language-specific build deps:**
  - Rust tools: `rustup` + `cargo` (installed via rustup)
  - Go tools: `go` (golang package)
  - Python tools: `python3-dev`, `python3-venv`
  - Node tools: `nodejs`, `npm`

- **Library dev packages (per family):**
  - Each C library the tool links to needs the `-dev` / `-devel` package
  - Example: OpenSSL
    - Debian: `libssl-dev`
    - RHEL: `openssl-devel`
    - Alpine: `openssl-dev`
    - Arch: `openssl`
    - openSUSE: `libopenssl-devel`
    - macOS: `openssl` (via brew, then set `OPENSSL_DIR`)
  - These are tracked in `LIB_TO_PACKAGE_MAP` and `requires.packages`

- **Build tools beyond the compiler:**
  - `cmake` — for cmake-based projects
  - `ninja` — for meson/ninja-based projects
  - `pkg-config` — for projects that use pkg-config to find libraries
  - `autoconf`, `automake`, `libtool` — for autotools-based projects

**Platform-specific build considerations:**
- Alpine uses `musl` libc, not `glibc` — some tools don't compile on Alpine
  without patches or `musl-dev`
- macOS needs Xcode CLT and may need `CFLAGS`/`LDFLAGS` for Homebrew-installed
  libs (e.g. `LDFLAGS=-L/opt/homebrew/lib`)
- ARM architecture may need cross-compilation or specific flags
- Some tools need kernel headers (`linux-headers` on Alpine, `kernel-headers` on RHEL)

**Post-build steps:**
- Copy built binary to `/usr/local/bin/` or `~/.local/bin/`
- Set permissions
- Clean up build directory
- May need `ldconfig` if shared libraries were installed

**Example recipe value:**
```python
"source": [
    "bash", "-c",
    "git clone https://github.com/nektos/act.git /tmp/act-build"
    " && cd /tmp/act-build"
    " && go build -o /usr/local/bin/act ."
    " && rm -rf /tmp/act-build",
],
```

**Not every tool has every method.** The tool may only exist in brew and as a direct download. That's fine — but every method where it IS available must be listed, with the CORRECT package name for that PM (researched, not guessed).

### Optional fields

| Field | Description | Example |
|-------|-------------|---------|
| `needs_sudo` | Dict of method → bool | `{"apt": True, "brew": False, "_default": True}` |
| `requires.binaries` | List of binary deps (other tool IDs) | `["curl", "docker"]` |
| `requires.packages` | Dict of distro family → list of system packages | `{"debian": ["libssl-dev"], "rhel": ["openssl-devel"]}` |
| `update` | Dict of method → update command | `{"_default": ["pip", "install", "--upgrade", "ruff"]}` |
| `post_env` | Shell snippet to source after install (e.g. PATH additions) | `"export PATH=$HOME/.cargo/bin:$PATH"` |
| `pre_install` | Commands to run before install (e.g. adding a repo) | `[["bash", "-c", "add-apt-repository ..."]]` |
| `on_failure` | Tool-specific failure handlers (Layer 3) | List of handler dicts |
| `_not_installable` | Flag for config/data entries (no install needed) | `True` |

---

## Remediation Handlers (remediation_handlers.py)

### Three layers, evaluated bottom-up (most specific first)

| Layer | Registry | Scope | Example |
|-------|----------|-------|---------|
| **Layer 3** | `on_failure` in the recipe itself | Tool-specific failures | `terraform` has a handler for state lock conflicts |
| **Layer 2** | `METHOD_FAMILY_HANDLERS` | Install-method-family failures | `pip` → PEP 668, missing pip; `cargo` → rustc version mismatch, gcc bug, missing C library |
| **Layer 1** | `INFRA_HANDLERS` | Cross-tool infrastructure failures | Network unreachable, disk full, permission denied, timeout |
| **Layer 0** | `BOOTSTRAP_HANDLERS` | Bootstrap-level failures | No package manager, no sudo, no compiler |

### Handler structure (each handler dict)

| Field | Description |
|-------|-------------|
| `pattern` | Regex matching stderr to detect this failure |
| `failure_id` | Unique ID for this failure type |
| `category` | One of: environment, dependency, permissions, network, disk, resources, timeout, compiler, package_manager, bootstrap |
| `label` | Human-readable failure label |
| `description` | Detailed explanation of what went wrong |
| `example_stderr` | Example of the stderr that triggers this pattern |
| `options` | List of remediation options (see below) |

### Option structure (each option dict within a handler)

| Field | Description |
|-------|-------------|
| `id` | Unique option ID (e.g. `"use-pipx"`, `"switch-apt"`, `"install-gcc12"`) |
| `label` | Human-readable label shown to user |
| `description` | Explanation of what this option does |
| `icon` | Emoji icon for the UI |
| `recommended` | Boolean — is this the recommended choice? |
| `strategy` | One of the valid strategies (see below) |
| `risk` | Optional risk level (`"low"`, `"medium"`, `"high"`) |
| `requires_binary` | Optional binary name that must be on PATH for this option to be `ready` (used by `retry_with_modifier`) |
| `group` | Optional `"primary"` or `"extended"` — UI grouping for option display |
| `arch_exclude` | Optional list of architecture strings where this option is `impossible` |

### Strategies (what the option actually does)

| Strategy | What it does | Required fields |
|----------|-------------|-----------------|
| `install_dep` | Install a prerequisite tool | `dep` — tool ID to install |
| `install_dep_then_switch` | Install dep, then switch install method | `dep`, `switch_to` — target method |
| `install_packages` | Install system packages | `packages` (dict of family → list) or `dynamic_packages: True` |
| `switch_method` | Switch to a different install method | `method` — target method key |
| `retry_with_modifier` | Retry with extra flags or env changes | `modifier` — dict of modifications |
| `add_repo` | Add a package repo, then retry | `repo_commands` — commands to add the repo |
| `upgrade_dep` | Upgrade an existing dep to newer version | `dep` — tool ID to upgrade |
| `env_fix` | Fix environment (PATH, config) | `fix_commands` — commands to run |
| `manual` | Manual steps for the user | `instructions` — text |
| `cleanup_retry` | Clean up and retry | `cleanup_commands` — commands to run first |

---

## Availability Computation (remediation_planning.py)

For EACH option, `_compute_availability()` determines the state:

### States

| State | Meaning | UI effect |
|-------|---------|-----------|
| `ready` | Can be executed right now | Option is clickable |
| `locked` | Needs prerequisite(s) first | Option shown but grayed, shows what to install first |
| `impossible` | Can NEVER work on this system | Option hidden or crossed out |

### Current gates (version-aware)

| Gate | Checks | Returns |
|------|--------|---------|
| Architecture exclusion | `option.arch_exclude` vs `system_profile.arch` | impossible |
| Native PM availability | `apt`, `dnf`, `apk`, `pacman`, `zypper` not in system's PM list | impossible |
| Installable PM availability (brew) | `brew` not available | locked (install brew first) |
| Installable PM availability (snap) | `snap` not available + has systemd | locked (install snapd first) |
| Snap without systemd | snap target but no systemd (containers, macOS) | impossible |
| Read-only rootfs | `install_packages` on read-only container | impossible |
| Recipe method existence | `switch_method` target not in recipe's `install` dict | impossible |
| Dep availability | `install_dep` dep not available | locked (install dep first) |

### Potential new gates a tool could require

When working through a tool, I may discover the system needs new gates:
- New capability checks (e.g. `has_gpu`, `has_selinux`, `cgroup_version`)
- New installer types not covered by current strategies
- New PM types (e.g. `yay` for AUR, `flatpak`, `sdkman`, `asdf`)
- New dep shapes (e.g. a tool requiring a kernel module, a systemd service, etc.)

---

## Dynamic Resolver (dynamic_dep_resolver.py)

### Data structures that may need new entries per tool

| Structure | What it is | When to update |
|-----------|-----------|----------------|
| `KNOWN_PACKAGES` | Maps tool/binary name → per-PM package name | When the tool or its dep has a different package name across distros |
| `LIB_TO_PACKAGE_MAP` | Maps C library short name → per-family dev package | When the tool depends on C libraries (ssl, ffi, xml2, etc.) |
| Special installers | Entries with `_install_cmd` in KNOWN_PACKAGES | When a dep needs a standalone installer script (rustup, nvm, sdkman) |

### Resolution tiers (may need new tiers)

1. TOOL_RECIPES lookup
2. KNOWN_PACKAGES lookup
3. LIB_TO_PACKAGE_MAP lookup
4. Identity mapping (dep name = package name)

New tiers could include:
- Convention-based resolution (e.g. `lib<name>-dev` on Debian)
- Language-specific resolvers (e.g. `pip install <name>`, `npm install -g <name>`)

---

## System Presets (dev_scenarios.py)

### Current 19 presets

| Preset | Family | PM | Arch | Container | Systemd | Snap |
|--------|--------|-----|------|-----------|---------|------|
| `ubuntu_2004` | debian | apt | x86_64 | No | Yes | Yes |
| `ubuntu_2204` | debian | apt | x86_64 | No | Yes | Yes |
| `ubuntu_2404` | debian | apt | x86_64 | No | Yes | Yes |
| `debian_11` | debian | apt | x86_64 | No | Yes | No |
| `debian_12` | debian | apt | x86_64 | No | Yes | No |
| `docker_debian_12` | debian | apt | x86_64 | Yes | No | No |
| `wsl2_ubuntu_2204` | debian | apt | x86_64 | No (WSL) | Yes | Yes |
| `raspbian_bookworm` | debian | apt | aarch64 | No | Yes | Yes |
| `fedora_39` | rhel | dnf | x86_64 | No | Yes | No |
| `fedora_41` | rhel | dnf | x86_64 | No | Yes | No |
| `centos_stream9` | rhel | dnf | x86_64 | No | Yes | No |
| `rocky_9` | rhel | dnf | x86_64 | No | Yes | No |
| `alpine_318` | alpine | apk | x86_64 | No | No | No |
| `alpine_320` | alpine | apk | x86_64 | No | No | No |
| `k8s_alpine_318` | alpine | apk | x86_64 | Yes (read-only) | No | No |
| `arch_latest` | arch | pacman | x86_64 | No | Yes | No |
| `opensuse_15` | suse | zypper | x86_64 | No | Yes | No |
| `macos_13_x86` | macos | brew | x86_64 | No | No | No |
| `macos_14_arm` | macos | brew | arm64 | No | No | No |

A tool may expose a need for new preset fields:
- `python.pep668_enforced` — already present
- `hardware.gpu` — may be needed for GPU tools
- `capabilities.has_selinux` — may be needed for security tools
- `capabilities.cgroup_version` — may be needed for container tools
- New distro variants (e.g. Amazon Linux, NixOS)

---

## Test Validation (test_remediation_coverage.py)

### 6 checks run per tool

| Check | What it validates |
|-------|-------------------|
| 1. Recipe completeness | `cli` field exists, `label` exists, at least one install method |
| 2. Dep coverage | Every dep referenced in handlers is resolvable |
| 3. Handler option validity | `switch_method` targets exist in recipe, `install_packages` covers families |
| 4. Scenario availability | No false impossibles across ALL 19 presets |
| 5. Missing expected tools | Common tools that should have recipes |
| 6. Method coverage | Tools with PM methods cover all systems (--suggest only) |

### What may need updating in the test

- `SYSTEM_CORRECT_REASONS` — new legitimate impossible reasons
- `KNOWN_LEGITIMATE_IMPOSSIBLES` — new intentionally impossible scenarios
- `EXPECTED_TOOLS` — if adding a new tool that should be in the expected set
- Reason-matching logic — if a new impossible reason pattern appears

---

## The Full Per-Tool Process

For ONE tool:

### Step 1: Research
- What is this tool? What does it do?
- What package managers carry it? What are the EXACT package names?
- What are its binary dependencies? (curl, git, docker, python3, etc.)
- What system library packages does it need? (libssl-dev, etc.)
- What does it need post-install? (PATH additions, shell source, etc.)
- What are its known failure modes when installing?
- Does it need a repo to be added first on any system?
- Can it be built from source? What does that require?

### Step 2: Recipe
- Write or update the recipe in `recipes.py`
- All fields listed in the "Recipe Fields" section above
- Every install method where the tool is genuinely available
- Correct package names per PM (researched, not guessed)
- Correct deps, correct verify command

### Step 3: Handlers
- Do any existing handlers (Layer 2 method-family or Layer 1 infra) already cover this tool's failure modes?
- Does this tool need NEW failure patterns in any handler layer?
- Does this tool need a Layer 3 `on_failure` entry in the recipe itself?
- For each failure pattern: what options/choices does the user get?
- For each option: what strategy, what deps, what packages per family?

### Step 4: Dynamic resolver data
- Does this tool or any of its deps need entries in `KNOWN_PACKAGES`?
- Does this tool introduce new C library deps for `LIB_TO_PACKAGE_MAP`?
- Does this tool need a new special installer entry?

### Step 5: Infrastructure layer improvements
- Does this tool expose a new capability requirement that `_compute_availability` should check?
- Does this tool need a new install strategy that doesn't exist yet?
- Does this tool need a new system preset field?
- Does the resolver need a new tier or logic adjustment?
- Does `_collect_deps` need changes to handle a new dep shape?

### Step 6: Validate
- Run `test_remediation_coverage.py`
- Verify across all 19 presets
- Check: no false impossibles
- Check: correct ready/locked/impossible for each option on each system
- Check: no regressions in other tools

### Step 7: Fix issues
- If validation fails, fix the issue (in recipe, handler, resolver, or planning layer)
- Re-run validation
- Repeat until clean

---

## Scope of the Task

- 296 existing recipes (most are placeholders needing full coverage)
- ~131 new tools to add (from stack-coverage-plan.md)
- 19 system presets to validate against
- Each tool = Steps 1-7 above = ~10+ minutes of careful work
- Infrastructure layers evolve as tools expose gaps

This is not a bulk find-and-replace operation. It is methodical, per-tool
engineering that builds up the remediation system one verified tool at a time.
