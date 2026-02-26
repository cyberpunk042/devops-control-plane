---
description: Full-spectrum tool coverage workflow — research, recipe, resolver data, validation across 19 system presets
---

# Tool Coverage Audit Workflow

> **Reference documents:**
> - `.agent/plans/tool_install/per-tool-full-spectrum-analysis.md` — every field, every structure, every layer
> - `.agent/plans/tool_install/infrastructure-gap-analysis.md` — what was fixed, what is deferred
> - `.agent/plans/tool_install/stack-coverage-plan.md` — stack ordering and tool lists
>
> **Next workflow:** After this base coverage is done for a tool, run
> `/tool-remediation-audit` to add remediation handlers and availability gates.

---

## Phase 0: Understand the current state

Before touching any tool, run the validation suite to see where things stand.

```bash
# Quick — errors only
// turbo
.venv/bin/python -m tests.test_remediation_coverage

# Full — errors + warnings + suggestions + arch checks
// turbo
.venv/bin/python -m tests.test_remediation_coverage --verbose --suggest
```

Read the output. Understand:
- How many recipes have missing `cli` fields (Check 1)
- How many tools are in EXPECTED_TOOLS but have no recipe (Check 5)
- How many `_default` commands have hardcoded x86 URLs (Check 7)
- How many method coverage gaps exist (Check 6)

---

## Phase 1: Select a tool

Pick a tool from the stack coverage plan, or from the test output. One tool at a time.

State which tool you are working on. Do not proceed to Phase 2 without naming it.

---

## Phase 2: Research the tool

For the selected tool, determine ALL of the following. Do not guess — research.

### 2.1 Identity
- What is the tool? What does it do? What language is it written in?
- What is the CLI binary name? (This is the `cli` field)
- What category/stack does it belong to?

### 2.2 Package availability
For EACH package manager, determine if the tool is available and what the EXACT package name is:

| PM | Available? | Package name | Source |
|----|-----------|--------------|--------|
| `apt` | ? | ? | packages.debian.org |
| `dnf` | ? | ? | pkgs.org or Fedora packages |
| `apk` | ? | ? | pkgs.alpinelinux.org |
| `pacman` | ? | ? | archlinux.org/packages |
| `zypper` | ? | ? | software.opensuse.org |
| `brew` | ? | ? | formulae.brew.sh |
| `snap` | ? | ? | snapcraft.io |
| `pip` | ? | ? | pypi.org |
| `npm` | ? | ? | npmjs.com |
| `cargo` | ? | ? | crates.io |
| `go` | ? | ? | pkg.go.dev |

Not every tool is in every PM. Record "not available" where it isn't.

### 2.3 Binary download (_default)
- Does the tool publish pre-compiled binaries? Where?
- What is the download URL pattern? Does it use `{arch}` and `{os}` in the URL?
  - What naming convention for arch? (`amd64` vs `x86_64` vs `64bit`)
  - What naming convention for OS? (`linux` vs `Linux` vs `linux-gnu`)
- What archive format? (`.tar.gz`, `.zip`, raw binary, `.deb`, `.rpm`)
- Does it have an installer script? (e.g. `curl ... | bash`)
- What tools does the download/extract need? (`curl`, `tar`, `unzip`, `jq`)

### 2.4 Build from source (if applicable)
- What build system? (`make`, `cmake`, `cargo`, `go build`)
- Git repo URL?
- Build dependencies? (compiler, language runtime, C library dev packages)
- Branch/tag to build from?

### 2.5 Dependencies
- Runtime binary deps? (e.g. `docker`, `git`, `python3`)
- System library packages?

### 2.6 Post-install
- PATH additions needed?
- Shell config sourcing?
- Verify command? (e.g. `tool --version`)

---

## Phase 3: Write the recipe

File: `src/core/services/tool_install/data/recipes.py`

### Required fields
```python
"tool_id": {
    "cli": "binary_name",
    "label": "Tool Name (description)",
    "category": "stack_name",
    "install": {
        # One entry per PM where the tool IS available
        # Use {arch} and {os} placeholders in _default URLs
        "apt": ["apt-get", "install", "-y", "package_name"],
        "dnf": ["dnf", "install", "-y", "package_name"],
        "_default": ["bash", "-c", "curl -sSfL ... | tar -xz ..."],
    },
    "needs_sudo": {
        "apt": True, "dnf": True, "apk": True,
        "pacman": True, "zypper": True,
        "brew": False, "snap": True,
        "_default": True,
    },
    "verify": ["binary_name", "--version"],
},
```

### Optional fields (add when applicable)
```python
    "requires": {
        "binaries": ["curl", "git"],
        "packages": {
            "debian": ["libssl-dev"],
            "rhel": ["openssl-devel"],
            "alpine": ["openssl-dev"],
            "arch": ["openssl"],
            "suse": ["libopenssl-devel"],
        },
    },
    "update": {"_default": ["pip", "install", "--upgrade", "tool"]},
    "post_env": "export PATH=$HOME/.local/bin:$PATH",
    "arch_exclude": ["armv7l"],
```

### Source method (when applicable)
```python
    "install": {
        "source": {
            "build_system": "cmake",   # or "autotools", "cargo-git"
            "git_repo": "https://github.com/org/tool.git",
            "branch": "stable",
            "depth": 1,
            "requires_toolchain": ["cmake", "make", "gcc"],
            "configure_flags": ["-DCMAKE_BUILD_TYPE=Release"],
        },
    },
```

---

## Phase 4: Check dynamic resolver data

File: `src/core/services/tool_install/resolver/dynamic_dep_resolver.py`
File: `src/core/services/tool_install/data/remediation_handlers.py` (LIB_TO_PACKAGE_MAP)

### 4.1 KNOWN_PACKAGES
Does this tool or its dependencies have different package names across distros?
- If yes → add entry to `KNOWN_PACKAGES` with per-PM package names
- Check: does the entry already exist?

### 4.2 LIB_TO_PACKAGE_MAP
Does this tool depend on C libraries that need dev packages?
- If yes → add to `LIB_TO_PACKAGE_MAP`
- Check: does the entry already exist? (ssl, ffi, z, yaml, xml2, etc.)

### 4.3 Special installers
Does any dependency need a standalone installer (not in any repo)?
- If yes → add `_install_cmd` entry to `KNOWN_PACKAGES`
- Check: does it already exist? (rustup, nvm already covered)

---

## Phase 5: Validate

```bash
// turbo
.venv/bin/python -m tests.test_remediation_coverage --verbose --suggest
```

| Check | What to look for |
|-------|-----------------|
| Check 1 | Your recipe should NOT appear as "missing cli" or "NO install methods" |
| Check 1 | If you added a `source` method, it should NOT appear as "must be a dict" |
| Check 5 | If your tool is in EXPECTED_TOOLS, it should no longer appear as "missing" |
| Check 7 | If your `_default` uses `{arch}`, it should NOT appear in arch warnings |

If validation fails → fix → re-run → repeat until clean.

```bash
// turbo
.venv/bin/python -m tests.test_remediation_coverage
```

---

## Phase 6: Confirm no regressions

- Total error count did not increase
- No new failures in any check

---

## The files you touch

| File | Responsibility | When |
|------|---------------|------|
| `data/recipes.py` | Recipe data — install instructions per PM | Always |
| `resolver/dynamic_dep_resolver.py` | `KNOWN_PACKAGES` — binary → system package | When deps differ per distro |
| `data/remediation_handlers.py` | `LIB_TO_PACKAGE_MAP` — C lib → dev package | When tool needs C lib dev pkgs |

---

## Example: Adding `act`

### Research
- CLI: `act`, Category: `cicd`
- Available: `brew` (act), `_default` (GitHub releases)
- Not in: `apt`, `dnf`, `apk`, `zypper`, `pip`, `npm`, `cargo`
- Binary URL: `https://github.com/nektos/act/releases/download/v{version}/act_Linux_{arch}.tar.gz`
- Deps: `docker` (runtime), `curl` (download)
- Verify: `act --version`

### Recipe
```python
"act": {
    "cli": "act",
    "label": "act (local GitHub Actions runner)",
    "category": "cicd",
    "install": {
        "brew": ["brew", "install", "act"],
        "_default": [
            "bash", "-c",
            "curl -sSfL https://github.com/nektos/act/"
            "releases/latest/download/act_Linux_{arch}.tar.gz"
            " | sudo tar -xz -C /usr/local/bin act",
        ],
    },
    "needs_sudo": {"brew": False, "_default": True},
    "requires": {"binaries": ["docker", "curl"]},
    "verify": ["act", "--version"],
},
```

### Resolver: `docker` and `curl` already in KNOWN_PACKAGES → no changes.
### Validate → Check 1 clean, Check 7 clean (`{arch}` used) ✅

---

## What NOT to do

- Do NOT guess package names — research them
- Do NOT hardcode x86_64 in `_default` commands — use `{arch}` placeholder
- Do NOT add a recipe without `cli`, `label`, and `needs_sudo`
- Do NOT add a `source` method as a command list — it must be a dict with `build_system`
- Do NOT skip validation — run the test after every tool
- Do NOT forget `needs_sudo` per method — causes runtime KeyError
