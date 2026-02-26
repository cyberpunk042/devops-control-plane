# Infrastructure Gap Analysis

Based on the per-tool full spectrum analysis, this document identifies
every gap between what the analysis says we NEED and what the current
infrastructure ACTUALLY SUPPORTS.

Each gap is marked with a severity:
- 🔴 **Blocker** — Must fix before starting per-tool work, tools will fail
- 🟡 **Important** — Should fix early, many tools will trigger this
- 🟢 **Can defer** — Fix when the first tool exposes it

---

## 1. Recipe Structure (recipes.py)

### 1a. Missing `cli` fields

**Current state:** 223 recipes have missing or placeholder `cli` fields.
The test (`check_recipe_completeness`) catches this.

**Gap:** None — this is per-tool data work, not an infrastructure gap.
Every tool needs its `cli` set to the correct binary name.

**Severity:** N/A (data, not infra)

---

### 1b. `needs_sudo` is required by plan_resolution but many recipes don't have it

**Current state:** `plan_resolution.py` line 269 does:
```python
sudo = recipe_t["needs_sudo"].get(method, False)
```
This is a hard `KeyError` if `needs_sudo` is missing from the recipe.

**Gap:** 🟡 **Important** — Recipes without `needs_sudo` will crash
`resolve_install_plan()`. Either:
- Option A: Make `needs_sudo` required in all recipes (data work)
- Option B: Default safely: `recipe_t.get("needs_sudo", {}).get(method, False)`

**Recommendation:** Option B (defensive default) as an infrastructure fix,
then fill in correct `needs_sudo` values per tool during data work.

---

### 1c. `source` method structure is complex but not validated

**Current state:** `plan_resolution.py` lines 182-266 handle `source` method
installs with a rich structure:
```python
source_spec = recipe_t["install"]["source"]
build_system = source_spec.get("build_system", "autotools")
```
The `source` key expects a DICT (not a command list like other methods),
containing `build_system`, `git_repo`, `branch`, `depth`, `requires_toolchain`,
`configure_flags`, etc.

**Gap:** 🟡 **Important** — `check_recipe_completeness` does NOT validate
source method structure. A recipe with `"source": ["some", "cmd"]` would
pass the test but crash at plan resolution time.

**Recommendation:** Add a sub-check in `check_recipe_completeness`:
if a recipe has `install.source`, validate it's a dict with at least
`build_system` and either `git_repo` or `command`.

---

### 1d. `_default` method: no arch/OS awareness in recipes

**Current state:** `_default` values are typically hardcoded bash commands
like `curl -sSfL https://...x86_64.tar.gz | tar -xz`. These are x86-only.

**Gap:** 🟡 **Important** — On ARM systems (raspbian_bookworm, macos_14_arm),
these `_default` commands will download the wrong binary. The
`_substitute_install_vars` function in `build_helpers.py` handles `{arch}` and
`{os}` placeholders, BUT it's only used in the `source` method path
(plan_resolution.py line 250). It is NOT used for `_default` method commands.

**Recommendation:** Two options:
- Option A: Use `_substitute_install_vars` for ALL `_default` commands
  (requires recipes to use `{arch}` placeholders like `tool_{os}_{arch}.tar.gz`)
- Option B: Support per-arch `_default` variants in recipes
  (e.g. `"_default__aarch64": [...]`, `"_default__x86_64": [...]`)

**What exists in build_helpers.py:**
```python
_substitute_install_vars(command, profile, *, version="", extra=None)
# Maps arch names: x86_64→amd64, aarch64→arm64
# Maps OS names based on system_profile
```
This IS the right tool but it's not wired into the `_default` path.

---

## 2. Method Selection (method_selection.py)

### 2a. `source` is never auto-selected

**Current state:** `_pick_install_method()` resolution order is:
1. Recipe's `prefer` list
2. System's primary PM
3. snap
4. `_default`
5. Any PM whose binary is on PATH

**Gap:** 🔴 **Blocker for source-only tools** — `source` is never tried.
A recipe that ONLY has `"install": {"source": {...}}` will return
`method=None` → plan fails with "No install method available."

**Recommendation:** Add `source` as a fallback AFTER `_default` in the
resolution chain:
```python
# 5. source
if "source" in install:
    return "source"
```

---

### 2b. Language ecosystem methods (pip, npm, cargo, go) treated as generic PMs

**Current state:** `_pick_install_method` treats `pip`, `npm`, `cargo`, `go`
the same as any other method key. Step 5 checks `shutil.which(method)` — so
`pip` is picked if `pip` binary is on PATH through the "any available pm" fallback.

**Gap:** 🟢 **Can defer** — This works today but the resolution order is
imprecise. A tool available via both `apt` and `pip` on a Debian system will
always prefer `apt` (step 2), which is usually correct. But there's no
explicit logic for preferring language managers when they're available.

**No immediate fix needed.**

---

### 2c. `_is_batchable` only batches primary PM

**Current state:**
```python
def _is_batchable(method: str, primary_pm: str) -> bool:
    return method == primary_pm
```

**Gap:** 🟢 **Can defer** — Snap installs and brew installs on Linux are also
batchable in theory, but treating them as non-batchable (individual steps) is
correct behavior for now.

---

## 3. Dependency Collection (dependency_collection.py)

### 3a. Dynamic resolver fallback works but lacks build dep support

**Current state:** When `_collect_deps` encounters a tool without a recipe,
it calls `resolve_dep_install()` which handles:
- `known_package` → batch packages
- `special_installer` → tool step
- `identity` → batch packages (assume same name)

**Gap:** 🟡 **Important** — The dynamic resolver does NOT handle
`requires.packages` (system library dev packages per family). If a tool's
recipe says `"requires": {"packages": {"debian": ["libssl-dev"]}}`, the
dep collector handles it (lines 131-135 of dependency_collection.py). BUT
if a DEPENDENCY's recipe has `requires.packages`, those are only collected
when the dependency has a recipe entry. Dynamically-resolved deps have no
`requires.packages`.

**This is acceptable for now** — dynamically resolved deps are typically
binaries (curl, git, tar), not library-requiring tools. When a tool needs
C library deps, it should have a full recipe.

---

### 3b. No `pre_install` support in the collector

**Current state:** `_collect_deps` does not process `pre_install` steps
from recipes. However, `plan_resolution.py` does handle `repo_setup`
(lines 153-162) which serves a similar purpose.

**Gap:** 🟢 **Can defer** — The `repo_setup` pattern already exists for
adding repos before install. If `pre_install` is needed as a distinct
concept, it can be added when a tool requires it.

---

## 4. Remediation Planning (remediation_planning.py)

### 4a. `_compute_availability` doesn't gate `source` method

**Current state:** The `switch_method` strategy checks PM availability for
`_PM_METHODS` (apt, dnf, apk, pacman, zypper, brew, snap). But it does NOT
check anything specific for `source` method.

**Gap:** 🟡 **Important** — When a remediation option suggests
`"strategy": "switch_method", "method": "source"`, the availability
should check:
- Compiler toolchain available? (gcc/make on PATH)
- Build system tool available? (cmake, cargo, go)
- Sufficient disk space? (build needs more space than binary download)

Currently it just checks if `"source"` exists in `recipe["install"]` and
returns `"ready"`, which is technically wrong — the option should be
`"locked"` if build tools are missing.

**Recommendation:** Add a `source` gate in `_compute_availability`:
```python
if target_method == "source":
    # Check build toolchain
    source_spec = install_methods.get("source", {})
    if isinstance(source_spec, dict):
        toolchain = source_spec.get("requires_toolchain", [])
        for tool in toolchain:
            if not shutil.which(tool):
                return "locked", f"{tool} not installed", [tool], None
```

---

### 4b. `_compute_availability` doesn't gate language ecosystem methods

**Current state:** `pip`, `npm`, `cargo`, `go` methods are not in `_PM_METHODS`
and not in `_NATIVE_PMS` or `_INSTALLABLE_PMS`. So when a remediation option
says `"switch_method"` to `"pip"`, the only check is whether `"pip"` exists
in the recipe's `install` dict. It does NOT check if `pip` is actually on the
system.

**Gap:** 🟡 **Important** — A `switch_method` to `pip` should be `locked`
if `pip` is not installed, not `ready`.

**Recommendation:** Add a language ecosystem gate:
```python
_LANG_ECOSYSTEM_PMS = {"pip": "pip3", "npm": "npm", "cargo": "cargo", "go": "go"}

if target_method in _LANG_ECOSYSTEM_PMS:
    cli = _LANG_ECOSYSTEM_PMS[target_method]
    if not shutil.which(cli):
        return "locked", f"{cli} not installed", [target_method], None
```

---

### 4c. `install_packages` strategy doesn't check if PM is operational

**Current state:** The `install_packages` strategy checks:
- Read-only rootfs → impossible
- `dynamic_packages` → ready
- Missing family → impossible
- Otherwise → ready

**Gap:** 🟢 **Can defer** — It assumes the system PM is working. It could
be broken (corrupted apt lists, no repos configured, etc.), but that's a
runtime failure, not something we can statically check.

---

## 5. Dynamic Resolver (dynamic_dep_resolver.py)

### 5a. `KNOWN_PACKAGES` coverage

**Current state:** ~30 entries covering common system tools (curl, git, make,
tar, unzip, gcc, cmake, etc.) and language runtimes (python3, node, go, ruby,
php, docker).

**Gap:** 🟡 **Important** — Many tool dependencies are missing:
- `jq` — needed by many install scripts
- `gpg` — needed for signature verification
- `sudo` — some systems don't have it
- `bash` — Alpine images often only have `ash`
- `file` — needed by some build scripts
- `patch` — needed for source builds with patches
- `xz-utils` — needed for .tar.xz extraction

These should be added proactively before starting per-tool work, as many
tools will depend on them.

**Recommendation:** Add the missing common deps to KNOWN_PACKAGES.

---

### 5b. Two `LIB_TO_PACKAGE_MAP` definitions

**Current state:** `LIB_TO_PACKAGE_MAP` is defined in
`remediation_handlers.py` (line 1063) and imported by
`dynamic_dep_resolver.py` (line 23). Single source of truth.

**Gap:** None — properly structured.

---

## 6. Test Framework (test_remediation_coverage.py)

### 6a. `check_recipe_completeness` doesn't validate `source` structure

**Current state:** Check 1 validates `cli`, `label`, and presence of install
methods. It does NOT look at the structure/type of install method values.

**Gap:** Same as gap 1c above. `source` method expects a dict, not a list.
A malformed `source` entry would pass the test but crash at runtime.

**Recommendation:** Add validation for `source` method structure.

---

### 6b. `check_recipe_completeness` doesn't validate `needs_sudo`

**Current state:** The test doesn't check for `needs_sudo` presence.

**Gap:** Same as gap 1b above. Missing `needs_sudo` causes `KeyError` at
plan resolution time.

**Recommendation:** Add a warning (not error) for recipes missing `needs_sudo`
when they have install methods.

---

### 6c. `check_recipe_completeness` doesn't check for language ecosystem methods

**Current state:** Line 112-115 only checks for `_default` or system PM methods.
A recipe with only `"pip": [...]` and no `_default` will trigger:
```
recipe/tool: no _default and no system pkg manager method
```

**Gap:** 🟡 **Important** — Language ecosystem methods (`pip`, `npm`, `cargo`,
`go`) are valid install methods. The check should count them as valid.

**Recommendation:** Update the check to also accept language ecosystem methods:
```python
has_lang_method = any(m in install for m in ("pip", "npm", "cargo", "go"))
if not has_universal and not has_any_pkg_mgr and not has_lang_method:
    ...
```

---

### 6d. No check for `_default` arch compatibility

**Current state:** No test checks whether a `_default` method will work
on ARM systems. A hardcoded x86_64 download URL passes all checks.

**Gap:** 🟡 **Important** — ARM presets (raspbian, macos_arm) will get
broken `_default` commands. Adding a check requires the recipe to use
`{arch}` templates or to explicitly exclude ARM via `arch_exclude`.

**Recommendation:** Add a warning in `check_method_coverage` for tools with
`_default` methods that contain hardcoded `x86_64` or `amd64` in the command
but no `arch_exclude` declaration.

---

## 7. System Presets (dev_scenarios.py)

### 7a. Missing `capabilities.has_compiler` flag

**Current state:** Presets track `has_systemd`, `has_sudo`,
`snap_available`, `containerized`, `read_only_rootfs`.

**Gap:** 🟢 **Can defer** — No preset tracks whether build tools (gcc, make)
are available. This matters for `source` method availability. However, the
`_validate_toolchain` function in `build_helpers.py` checks at runtime. The
planning layer uses `shutil.which()` checks for live detection.

For static simulation (in tests), this means `source` methods appear as
`ready` even on systems that don't have compilers. This is a false positive
in the test but not a runtime issue.

**Recommendation:** Consider adding `has_build_tools: bool` to presets for
more accurate static validation. Can wait until a tool actually needs it.

---

## Summary: What to Fix Before Starting Per-Tool Work

### 🔴 Blockers (must fix)

| # | Gap | Fix | Status |
|---|-----|-----|--------|
| 2a | `source` never auto-selected by `_pick_install_method` | Add `source` as fallback in resolution chain | ✅ FIXED — `method_selection.py` |

### 🟡 Important (should fix early)

| # | Gap | Fix | Status |
|---|-----|-----|--------|
| 1b | `needs_sudo` causes KeyError if missing | Defensive default in `plan_resolution.py` | ✅ FIXED — `plan_resolution.py` |
| 1c | `source` method structure not validated | Add sub-check in `check_recipe_completeness` | ✅ FIXED — `test_remediation_coverage.py` |
| 1d | `_default` not arch-aware | Wire `_substitute_install_vars` into `_default` path | ✅ FIXED — `plan_resolution.py` |
| 4a | `source` method not gated for build tools | Add toolchain check in `_compute_availability` | ✅ FIXED — `remediation_planning.py` |
| 4b | Language PMs not gated | Add pip/npm/cargo/go availability check | ✅ FIXED — `remediation_planning.py` |
| 5a | Common deps missing from KNOWN_PACKAGES | Add jq, gpg, bash, patch, etc. | ✅ FIXED — `dynamic_dep_resolver.py` |
| 6c | Language methods flagged as "no install method" | Update test check to accept pip/npm/cargo/go | ✅ FIXED — `test_remediation_coverage.py` |
| 6d | No arch check for _default commands | Add warning for hardcoded x86 URLs | ✅ FIXED — `test_remediation_coverage.py` (Check 7) |

### 🟢 Can Defer

| # | Gap | Notes |
|---|-----|-------|
| 2b | Language PM resolution order imprecise | Works today, optimize later |
| 2c | Only primary PM batches | Correct behavior for now |
| 3a | Dynamic resolver lacks build dep support | OK for now, full recipes cover this |
| 3b | No pre_install in collector | repo_setup covers the same need |
| 4c | install_packages doesn't check PM health | Runtime check, can't do statically |
| 7a | No has_build_tools in presets | Add when a tool needs it |

