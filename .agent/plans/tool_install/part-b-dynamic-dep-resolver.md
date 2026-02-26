---
description: Part B — Dynamic dep resolver for unregistered dependencies
---

# Part B: Dynamic Dep Resolver

## Goal

When a dependency is detected at runtime but has no entry in `TOOL_RECIPES`,
the system should still be able to resolve it to an install command using the
system's package manager — instead of silently skipping it or marking it
impossible.

This also means respecting package manager configurations (`.npmrc`, `pip.conf`,
apt sources) so the install commands work in the user's actual environment.

---

## 1. Current dep resolution paths (what exists)

### Path 1: Install-time (`_collect_deps` in `dependency_collection.py`)

```
_collect_deps("some_dep", system_profile, ...)
  ↓
  recipe = TOOL_RECIPES.get("some_dep")
  if not recipe:
      logger.warning("not found in TOOL_RECIPES")  ← silently gives up
      return
  ↓
  cli = recipe.get("cli", tool_id)
  if shutil.which(cli):
      return  ← already installed, done
  ↓
  # Recurse into requires.binaries
  for dep in recipe.requires.binaries:
      _collect_deps(dep, ...)  ← same problem if dep has no recipe
  ↓
  # Collect requires.packages[family]
  family_pkgs = recipe.requires.packages.get(family, [])
  for pkg in family_pkgs:
      batch_packages.append(pkg)  ← adds to batch
  ↓
  # Pick install method, build step
  method = _pick_install_method(recipe, pm, snap_ok)
```

**Problem:** If a dep has no recipe, it's silently dropped. The install
might fail later because the dep wasn't installed.

### Path 2: Remediation-time (`_check_dep_availability` in `remediation_planning.py`)

```
_check_dep_availability("unzip")
  ↓
  dep_recipe = TOOL_RECIPES.get("unzip")
  if dep_recipe:
      cli = dep_recipe.get("cli", "unzip")
      if shutil.which(cli): return "ready"
      return "locked", "unzip not installed", ["unzip"]
  ↓
  # No recipe — treat as system package (recently fixed)
  if shutil.which("unzip"): return "ready"
  return "locked", "unzip not installed (system package)", ["unzip"]
```

**Current state:** This was recently fixed to not return "impossible" for
recipe-less deps. But it returns "locked" with `["unzip"]` as unlock_deps,
and there's no actual logic to install that dep — the unlock dep ID `"unzip"`
is not in TOOL_RECIPES either.

### Path 3: Library mapping (`LIB_TO_PACKAGE_MAP`)

```python
LIB_TO_PACKAGE_MAP = {
    "ssl": {"debian": "libssl-dev", "rhel": "openssl-devel", ...},
    "ffi": {"debian": "libffi-dev", "rhel": "libffi-devel", ...},
    # 14 entries total
}
```

**Current state:** Imported in `remediation_planning.py` but **never used**.
Only consumed conceptually by `dynamic_packages: True` handlers, but the
execution side doesn't exist yet.

---

## 2. Dynamic resolution strategy

### 2.1 Three-tier resolution

```
resolve_dep_install("curl", system_profile)
  ↓
  Tier 1: Recipe lookup
    TOOL_RECIPES.get("curl") → found? Use recipe's install method.
  ↓
  Tier 2: Known package mapping
    KNOWN_PACKAGES.get("curl") → {"apt": "curl", "dnf": "curl", ...}
    → Use system's primary PM to build install command
  ↓
  Tier 3: Direct package name (identity mapping)
    dep_name = package_name on most systems
    → Build install command: apt install -y curl
  ↓
  None: Truly unknown — can't resolve
```

### 2.2 The `KNOWN_PACKAGES` map

This is the key new data structure. It maps common tool/binary names to
their actual package names per system. Most are identity mappings (curl →
curl), but some differ significantly:

```python
KNOWN_PACKAGES: dict[str, dict[str, str | list[str]]] = {
    # ── System utilities ────────────────────────────────────────
    "curl": {
        "apt": "curl", "dnf": "curl", "apk": "curl",
        "pacman": "curl", "zypper": "curl", "brew": "curl",
    },
    "wget": {
        "apt": "wget", "dnf": "wget", "apk": "wget",
        "pacman": "wget", "zypper": "wget", "brew": "wget",
    },
    "unzip": {
        "apt": "unzip", "dnf": "unzip", "apk": "unzip",
        "pacman": "unzip", "zypper": "unzip", "brew": "unzip",
    },
    "tar": {
        "apt": "tar", "dnf": "tar", "apk": "tar",
        "pacman": "tar", "zypper": "tar", "brew": "gnu-tar",
    },
    "jq": {
        "apt": "jq", "dnf": "jq", "apk": "jq",
        "pacman": "jq", "zypper": "jq", "brew": "jq",
    },
    "git": {
        "apt": "git", "dnf": "git", "apk": "git",
        "pacman": "git", "zypper": "git", "brew": "git",
    },
    "make": {
        "apt": "make", "dnf": "make", "apk": "make",
        "pacman": "make", "zypper": "make", "brew": "make",
    },
    "gcc": {
        "apt": "gcc", "dnf": "gcc", "apk": "gcc",
        "pacman": "gcc", "zypper": "gcc", "brew": "gcc",
    },

    # ── Tools where package name differs ────────────────────────
    "pip": {
        "apt": "python3-pip", "dnf": "python3-pip",
        "apk": "py3-pip", "pacman": "python-pip",
        "zypper": "python3-pip", "brew": "python3",  # pip comes with python
    },
    "pip3": {
        "apt": "python3-pip", "dnf": "python3-pip",
        "apk": "py3-pip", "pacman": "python-pip",
        "zypper": "python3-pip", "brew": "python3",
    },
    "pipx": {
        "apt": "pipx", "dnf": "pipx",
        "apk": "pipx", "pacman": "python-pipx",
        "zypper": "python3-pipx", "brew": "pipx",
    },
    "python3": {
        "apt": "python3", "dnf": "python3",
        "apk": "python3", "pacman": "python",
        "zypper": "python3", "brew": "python@3",
    },
    "node": {
        "apt": "nodejs", "dnf": "nodejs",
        "apk": "nodejs", "pacman": "nodejs",
        "zypper": "nodejs", "brew": "node",
    },
    "npm": {
        "apt": "npm", "dnf": "npm",
        "apk": "nodejs-npm", "pacman": "npm",
        "zypper": "npm", "brew": "node",  # npm comes with node
    },
    "rustup": {
        # Not in system repos — use _default curl installer
        "_install_cmd": "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y",
    },
    "nvm": {
        # Not in system repos — use _default curl installer
        "_install_cmd": "curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/HEAD/install.sh | bash",
    },

    # ── Build dependencies (often needed by pip/cargo builds) ───
    "build-essential": {
        "apt": "build-essential",
        "dnf": ["gcc", "gcc-c++", "make"],  # list = multiple packages
        "apk": "build-base",
        "pacman": "base-devel",
        "zypper": ["gcc", "gcc-c++", "make"],
    },
}
```

### 2.3 Integration with LIB_TO_PACKAGE_MAP

`LIB_TO_PACKAGE_MAP` already maps C library short names to package names per
distro **family** (debian, rhel, alpine, arch, suse). `KNOWN_PACKAGES` maps
by **package manager** (apt, dnf, apk, pacman, zypper, brew).

We keep both and search both:

```
resolve_dep_install("ssl", system_profile)
  ↓
  Tier 1: TOOL_RECIPES.get("ssl") → not found
  Tier 2: KNOWN_PACKAGES.get("ssl") → not found
  Tier 2b: LIB_TO_PACKAGE_MAP.get("ssl") → {"debian": "libssl-dev", ...}
    → Map family to package name → build install command
  Tier 3: Assume "ssl" is the package name → build install command
```

**Key difference:**
- `KNOWN_PACKAGES` is keyed by **package manager** (apt, dnf) — direct
- `LIB_TO_PACKAGE_MAP` is keyed by **distro family** (debian, rhel) — needs mapping

Both are needed because:
- `KNOWN_PACKAGES` handles tools/binaries where PM matters
- `LIB_TO_PACKAGE_MAP` handles C libraries where family matters (dev package naming)

---

## 3. Package manager config awareness

### 3.1 What to detect

| PM | Config locations | What matters |
|----|-----------------|--------------|
| **pip** | `~/.pip/pip.conf`, `~/.config/pip/pip.conf`, `/etc/pip.conf`, venv `pyvenv.cfg` | `index-url`, `trusted-host`, `--user` vs venv |
| **npm** | `.npmrc` (project), `~/.npmrc` (user), `/etc/npmrc` | `registry`, `scope`, proxy, auth tokens |
| **apt** | `/etc/apt/sources.list`, `/etc/apt/sources.list.d/`, proxy.conf | repos, GPG keys, proxy |
| **dnf** | `/etc/dnf/dnf.conf`, `/etc/yum.repos.d/` | repos, proxy, gpgcheck |
| **cargo** | `~/.cargo/config.toml`, `$CARGO_HOME/config.toml` | registries, proxy |
| **brew** | `HOMEBREW_PREFIX`, `HOMEBREW_CELLAR` env vars | prefix path (differs x86/ARM), taps |

### 3.2 What to do with config info

**We do NOT modify configs.** We do:

1. **Detect** — add `package_manager_config` to the system profile
2. **Inform** — if custom registries or proxies are configured, include that
   in the remediation option's description so the user knows
3. **Respect** — when building install commands:
   - pip: detect if in a venv, use `--user` if not root and no venv
   - npm: pass `--registry` if custom registry is set in .npmrc
   - apt/dnf: no changes needed (they read their own config)
   - cargo: no changes needed

### 3.3 PM config detection function

```python
def detect_pm_config(system_profile: dict) -> dict:
    """Detect package manager configurations.

    Returns a dict with config info per PM, e.g.:
    {
        "pip": {
            "in_venv": True,
            "custom_index": "https://pypi.example.com/simple",
            "user_mode": False,
        },
        "npm": {
            "custom_registry": "https://npm.example.com",
            "has_auth_token": True,
        },
        "apt": {
            "has_proxy": False,
            "custom_repos": ["docker", "nodesource"],
        },
    }
    """
```

This goes into the system profile enrichment, NOT into the dep resolver.
The dep resolver just reads it when building install commands.

---

## 4. The `resolve_dep_install()` function

### 4.1 Signature

```python
def resolve_dep_install(
    dep: str,
    system_profile: dict,
) -> dict | None:
    """Resolve how to install a dependency on this system.

    Resolution order:
      1. TOOL_RECIPES — full recipe with install methods
      2. KNOWN_PACKAGES — common tools with per-PM package names
      3. LIB_TO_PACKAGE_MAP — C library mappings by distro family
      4. Identity — assume dep name = package name

    Args:
        dep: Dependency name (binary name, tool ID, or lib short name).
        system_profile: System profile from _detect_os().

    Returns:
        Resolution dict or None if truly unresolvable:
        {
            "dep": "unzip",
            "source": "recipe" | "known_package" | "lib_mapping" | "identity",
            "package_names": ["unzip"],       # actual package(s) to install
            "install_cmd": ["apt-get", "install", "-y", "unzip"],
            "needs_sudo": True,
            "pm": "apt",
            "confidence": "high" | "medium" | "low",
            "notes": None | "Using identity mapping — verify package name",
        }
    """
```

### 4.2 Confidence levels

| Source | Confidence | Why |
|--------|-----------|-----|
| TOOL_RECIPES | high | Explicitly defined install method |
| KNOWN_PACKAGES | high | Manually verified package names per PM |
| LIB_TO_PACKAGE_MAP | high | Manually verified lib→package mapping |
| Identity mapping | medium | Works for 80% of deps (curl, wget, git, jq) |
| Special installer | high | curl pipe commands (rustup, nvm) |

When confidence is **medium**, the UI should show a note:
> "Package name assumed to be 'foo'. If install fails, verify the correct
> package name for your system."

### 4.3 Sudo detection

```python
def _needs_sudo(pm: str, system_profile: dict) -> bool:
    """Does this PM command need sudo?"""
    if system_profile.get("capabilities", {}).get("is_root", False):
        return False
    if pm == "brew":
        return False  # brew should never run as root
    if pm == "apk" and not system_profile.get("capabilities", {}).get("has_sudo"):
        return False  # Alpine containers often run as root
    return True  # apt, dnf, pacman, zypper need sudo
```

---

## 5. Integration points

### 5.1 Where `resolve_dep_install` gets called

**A) `_collect_deps` fallback (install-time)**

Current:
```python
recipe = TOOL_RECIPES.get(tool_id)
if not recipe:
    logger.warning("not found in TOOL_RECIPES")
    return  ← drops the dep silently
```

New:
```python
recipe = TOOL_RECIPES.get(tool_id)
if not recipe:
    resolution = resolve_dep_install(tool_id, system_profile)
    if resolution:
        # Add the resolved package to the batch
        for pkg in resolution["package_names"]:
            if pkg not in batch_packages:
                batch_packages.append(pkg)
        logger.info("Resolved '%s' dynamically via %s", tool_id, resolution["source"])
        return
    logger.warning("Cannot resolve dep '%s' — no recipe and no package mapping", tool_id)
    return
```

**B) `_check_dep_availability` enrichment (remediation-time)**

Current:
```python
# No recipe — treat as system package
if shutil.which(dep):
    return "ready", None, None, None
return "locked", f"{dep} not installed (system package)", [dep], None
```

New:
```python
# No recipe — try dynamic resolution
if shutil.which(dep):
    return "ready", None, None, None

resolution = resolve_dep_install(dep, system_profile)
if resolution:
    return "locked", f"{dep} not installed", [dep], None
# No resolution available — still locked but with lower confidence
return "locked", f"{dep} not installed (unverified package name)", [dep], None
```

**C) `dynamic_packages` handler execution (future)**

When a handler has `"dynamic_packages": True`, the execute step
needs to resolve the actual library name from stderr and map it
via `LIB_TO_PACKAGE_MAP` → install command. This is the execution
side (not the planning side we're building here).

### 5.2 System profile enrichment

Add to `_detect_os()` (or a parallel function):

```python
# After detecting PMs, detect their configs
info["pm_config"] = _detect_pm_configs(info["package_manager"])
```

---

## 6. File layout

```
src/core/services/tool_install/
├── resolver/
│   ├── dynamic_dep_resolver.py   ← NEW
│   │   ├── KNOWN_PACKAGES        ← tool→package mappings per PM
│   │   ├── resolve_dep_install() ← main function
│   │   └── _needs_sudo()         ← sudo detection
│   └── dependency_collection.py  ← MODIFY: fallback to dynamic resolver
├── data/
│   └── remediation_handlers.py   ← KEEP LIB_TO_PACKAGE_MAP here (used by resolver)
├── domain/
│   └── remediation_planning.py   ← MODIFY: pass system_profile to _check_dep_availability
└── detection/
    └── pm_config.py              ← NEW (future): PM configuration detection
```

---

## 7. Implementation steps

### Step B1: Create `dynamic_dep_resolver.py`
- Define `KNOWN_PACKAGES` dict (start with ~30 most common tools)
- Implement `resolve_dep_install()` — Tier 1→2→3→4 resolution
- Implement `_needs_sudo()`
- Pure function, no I/O except `shutil.which` checks
- **Test:** Unit test that verifies resolution for known deps across all PMs

### Step B2: Wire into `_check_dep_availability`
- Pass `system_profile` to `_check_dep_availability` (currently has no access)
- Call `resolve_dep_install` for recipe-less deps
- Update return to include resolution metadata
- **Test:** Verify remediation options for deps show correct availability

### Step B3: Wire into `_collect_deps`
- Call `resolve_dep_install` when recipe is missing
- Add resolved packages to batch
- Log resolution source for traceability
- **Test:** Verify install plan includes dynamically resolved deps

### Step B4: Add PM config detection (future, lower priority)
- Create `detection/pm_config.py`
- Detect pip.conf, .npmrc, cargo config
- Add to system profile under `pm_config` key
- Wire into `resolve_dep_install` for pip/npm command adjustments

### Step B5: Wire dynamic_packages execution (future)
- When executing a `dynamic_packages: True` handler option:
  - Parse stderr for library name
  - Look up in LIB_TO_PACKAGE_MAP
  - Build install command via `resolve_dep_install`
  - Execute

---

## 8. Current data gaps to fill in KNOWN_PACKAGES

Priority list — these are deps referenced in recipes or handlers that
currently have no recipe:

| Dep | Referenced by | Package name differs? |
|-----|---------------|----------------------|
| `curl` | 60+ recipes as binary dep | No (curl everywhere) |
| `git` | handler dep | No |
| `npm` | handler dep, 20+ recipes | Yes (nodejs-npm on Alpine) |
| `pip` | handler dep | Yes (python3-pip, py3-pip) |
| `pipx` | handler dep | Yes (python-pipx on Arch) |
| `rustup` | handler dep | Not in repos (curl installer) |
| `nvm` | handler dep | Not in repos (curl installer) |
| `unzip` | handler dep | No |
| `wget` | handler dep | No |
| `clang` | handler dep | No (but clang vs clang-tools) |
| `python3` | 3 recipes as binary dep | Yes (python on Arch) |
| `docker` | 10+ recipes as binary dep | Yes (docker.io on Debian, docker-ce via repo) |
| `go` | 12 recipes as binary dep | Yes (golang on some systems) |
| `ruby` | 3 recipes as binary dep | No |
| `java` | 3 recipes as binary dep | Yes (openjdk-N-jdk, java-N-openjdk) |
| `php` | 2 recipes as binary dep | No |

## 10. Bigger picture — Three dep resolution contexts

This dynamic resolver is ONE part of a larger architecture. Dependencies come
from three distinct contexts, each with different resolution rules:

### Context 1: Manifest-driven deps (deterministic)

When the program detects a project manifest file, the PM is **known**. There
is zero guessing:

| Manifest | PM | Operation |
|----------|----|-----------|
| `package.json` | npm / yarn / pnpm | `npm install`, `npm ci` |
| `requirements.txt` | pip | `pip install -r requirements.txt` |
| `Pipfile` / `Pipfile.lock` | pipenv | `pipenv install` |
| `pyproject.toml` (w/ poetry) | poetry | `poetry install` |
| `pyproject.toml` (w/ uv) | uv | `uv sync` |
| `Cargo.toml` | cargo | `cargo build` |
| `Gemfile` | bundler | `bundle install` |
| `go.mod` | go | `go mod download` |
| `composer.json` | composer | `composer install` |
| `Makefile` | make | `make` |
| `pom.xml` | maven | `mvn install` |
| `build.gradle` | gradle | `gradle build` |

**These do NOT use the dynamic resolver.** The manifest tells us exactly
what PM to use. The dynamic resolver only resolves the PM *tool itself*
if it's missing (e.g., `npm` binary not installed → resolve via KNOWN_PACKAGES).

**Future operations on manifest deps:**

| Operation | Scope | Example |
|-----------|-------|---------|
| Install all | All deps | `npm install` |
| Install prod only | Non-dev deps | `npm install --production` |
| Install dev only | Dev deps | `pip install -r requirements-dev.txt` |
| Audit | Vulnerability scan | `npm audit`, `pip-audit` |
| Update | Version bumps | `npm update`, `pip install --upgrade` |
| Lock | Lock file generation | `npm ci`, `pip freeze` |
| Clean | Remove node_modules, venv | `rm -rf node_modules` |

**PM config matters here:** When running `npm install`, the `.npmrc` file
determines registry, auth tokens, scope mappings. When running `pip install`,
`pip.conf` determines index URL, trusted hosts. We must detect and respect
these configs — they are NOT optional for manifest-driven installs.

### Context 2: Curated stack (manually authored)

These are stacks WE build full support for:

| Stack | Recipe coverage | Handlers | Test scenarios |
|-------|----------------|----------|---------------|
| Python (pip, pipx, venv, poetry, uv) | Full recipes | PEP 668, missing compiler, etc. | Per-version PEP 668 behavior |
| Node (npm, yarn, pnpm, nvm) | Full recipes | EACCES, ERESOLVE, etc. | Per-system npm/node versions |
| Rust (rustup, cargo, cross) | Full recipes | Missing linker, OpenSSL, etc. | musl vs glibc |
| Go (go, golangci-lint, gopls) | Full recipes | GOPATH, module issues | |
| Containers (Docker, Podman, kubectl, helm) | Full recipes | Daemon not running, permission | Container vs bare metal |
| System (apt, dnf, apk, brew, pacman) | Built into PM logic | Repo errors, GPG keys | Per-distro |

For curated stacks:
- Every tool has a `TOOL_RECIPES` entry with correct `cli`, `install` methods,
  `requires`, and `post_install`
- Remediation handlers cover known failure patterns
- Scenarios test every remediation path on every system preset
- PM configs are understood and respected

**When we add a new curated stack** (e.g., Ruby, Elixir, .NET):
1. Add recipes for all tools in the stack
2. Add remediation handlers for common failures
3. Add test scenarios
4. Update PM config detection if the stack has config files

### Context 3: Dynamic resolution (fallback for everything else)

This is what Part B builds. For deps and stacks we DIDN'T manually author:

```
User installs a tool that requires "foo" binary
  ↓
  TOOL_RECIPES.get("foo") → not found (we didn't write a recipe)
  ↓
  resolve_dep_install("foo", system_profile)
  ↓
  KNOWN_PACKAGES → found? Use verified mapping.
  LIB_TO_PACKAGE_MAP → C library? Use lib mapping.
  Identity mapping → assume foo = package name
  ↓
  Build install command with confidence tag
```

**The dynamic path is NOT second-class.** It's how the system handles:
- Deps we haven't manually curated yet
- Community-contributed tool stacks
- One-off system packages discovered at runtime
- Transitional coverage (deps that WILL get recipes but don't have them yet)

**Currently missing recipes that could test the dynamic path right now:**

| Dep | Referenced by | Would use dynamic resolution |
|-----|---------------|-----|
| `nvm` | handler dep | ✅ KNOWN_PACKAGES (curl installer) |
| `pipx` | handler dep | ✅ KNOWN_PACKAGES (name differs per PM) |
| `rustup` | handler dep | ✅ KNOWN_PACKAGES (curl installer) |
| `unzip` | handler dep | ✅ identity mapping |
| `python3` | 3 recipes | ✅ KNOWN_PACKAGES (python on Arch) |
| `tar` | implicitly needed | ✅ KNOWN_PACKAGES (gnu-tar on brew) |
| `java` | 3 recipes | ✅ KNOWN_PACKAGES (openjdk naming) |

These are real test cases we can use to validate the dynamic path
before any community stacks appear.

---

## 11. Testing strategy

### 11.1 Unit tests for `resolve_dep_install`

```python
def test_known_package_resolution():
    """Every KNOWN_PACKAGES entry resolves correctly for every PM."""
    for dep, mappings in KNOWN_PACKAGES.items():
        for pm in ["apt", "dnf", "apk", "pacman", "zypper", "brew"]:
            if pm in mappings:
                result = resolve_dep_install(dep, make_profile(pm=pm))
                assert result is not None
                assert result["confidence"] == "high"
                assert result["source"] == "known_package"

def test_identity_fallback():
    """Unknown dep falls through to identity mapping."""
    result = resolve_dep_install("some_random_tool", make_profile(pm="apt"))
    assert result is not None
    assert result["confidence"] == "medium"
    assert result["source"] == "identity"
    assert result["package_names"] == ["some_random_tool"]

def test_lib_mapping_resolution():
    """C library short names resolve via LIB_TO_PACKAGE_MAP."""
    result = resolve_dep_install("ssl", make_profile(pm="apt", family="debian"))
    assert result["package_names"] == ["libssl-dev"]
    assert result["source"] == "lib_mapping"
```

### 11.2 Integration test in `test_remediation_coverage.py`

Add **Check 7: Dynamic dep resolution** to the existing test:

```python
def check_dynamic_deps(verbose: bool = False) -> list[str]:
    """Verify all handler-referenced deps resolve on all presets."""
    issues = []
    for preset_id, profile in SYSTEM_PRESETS.items():
        pm = profile["package_manager"]["primary"]
        for dep in ALL_HANDLER_DEPS:  # collected from handlers
            result = resolve_dep_install(dep, profile)
            if result is None:
                issues.append(f"dynamic/{preset_id}/{dep}: unresolvable")
            elif result["confidence"] == "medium" and dep in EXPECTED_HIGH_CONFIDENCE:
                issues.append(
                    f"dynamic/{preset_id}/{dep}: expected high confidence "
                    f"but got medium (identity mapping)"
                )
    return issues
```

### 11.3 Testing curated vs dynamic boundary

```python
def test_curated_tools_use_recipes():
    """Curated stack tools should resolve via TOOL_RECIPES, not dynamic."""
    curated_tools = ["ruff", "docker", "kubectl", "helm", "node"]
    for tool in curated_tools:
        assert tool in TOOL_RECIPES, f"{tool} should have a recipe"

def test_dynamic_fallback_for_missing():
    """Tools without recipes should still resolve dynamically."""
    for dep in ["nvm", "pipx", "rustup", "unzip"]:
        for preset_id, profile in SYSTEM_PRESETS.items():
            result = resolve_dep_install(dep, profile)
            assert result is not None, f"{dep} should resolve on {preset_id}"
```

---

## 12. What this does NOT do

To be explicit about scope:

1. **Does NOT replace TOOL_RECIPES** — recipes are still the primary source
   for tools that need complex multi-step installs, version constraints, or
   post-install setup. Dynamic resolution is the fallback for simple deps.

2. **Does NOT auto-detect package names** — we don't query `apt-cache search`
   or `dnf provides` at runtime. That would be slow and unreliable. We use
   static mappings with a confidence-tagged identity fallback.

3. **Does NOT install without confirmation** — the resolver produces an
   install command, but the orchestrator still shows it to the user and
   waits for approval before executing.

4. **Does NOT handle version constraints** — if a dep needs a specific
   version (e.g., Python ≥3.10), that requires recipe logic, not dynamic
   resolution.

5. **Does NOT manage manifest deps** — `npm install` from package.json is
   a separate operation (Context 1). The dynamic resolver only resolves
   the PM tool itself if missing (e.g., npm binary not installed).

6. **Does NOT replace manifest-level operations** — install all, devDeps
   filtering, audit, lock — these are future features built on top of
   manifest detection, not on the dynamic resolver.

---

## 13. Risk assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Wrong package name from identity mapping | Install fails | Confidence tag + user note |
| `_needs_sudo` wrong for exotic setups | Command fails | User can modify command |
| KNOWN_PACKAGES incomplete | Misses some deps | Start with handler deps, expand |
| PM config detection slow | Slower _detect_os() | Make it lazy / optional |
| Breaking existing _collect_deps flow | Install regression | Wire as fallback only, don't change happy path |
| Manifest operations scope creep | Dynamic resolver gets overloaded | Keep contexts 1/2/3 separate |

