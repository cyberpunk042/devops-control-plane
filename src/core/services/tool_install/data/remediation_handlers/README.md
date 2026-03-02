# Remediation Handler Registry

> **77 handlers. 19 method families. 4 layers. Pure data, no logic.**
>
> Every known failure pattern, its detection regex, and its remediation options —
> organized by layer and method family. The folder structure IS the documentation.

---

## How It Works

When a tool install fails, the engine captures stderr + exit code and walks
the handler layers **bottom-up** — most specific first:

```
           STDERR + EXIT CODE
                  │
                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    LAYER 3 — Recipe-Declared                         │
│    (on_failure in TOOL_RECIPES — NOT in this package)                │
│                                                                      │
│    Tool-specific overrides. Checked first because the recipe         │
│    author knows their tool's failure modes better than any           │
│    generic handler. Defined in recipes/, not here.                   │
└─────────────────────────────┬────────────────────────────────────────┘
                              │ no match
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    LAYER 2 — Method Family                           │
│    (METHOD_FAMILY_HANDLERS — this package, method_families/)         │
│                                                                      │
│    The install method (pip, npm, cargo, apt, ...) determines which   │
│    handler list to search. pip failures match pip handlers, npm      │
│    failures match npm handlers, etc. 66 handlers across 19 families. │
│                                                                      │
│    Each handler offers MULTIPLE remediation options. The planner     │
│    computes option availability at runtime (ready/locked/impossible) │
│    based on the system profile — what's stored here is the raw       │
│    menu of possibilities, not the runtime decision.                  │
└─────────────────────────────┬────────────────────────────────────────┘
                              │ no match
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    LAYER 1 — Infrastructure                          │
│    (INFRA_HANDLERS — this package, infra.py)                         │
│                                                                      │
│    Cross-cutting failures that affect ANY method: network down,      │
│    disk full, read-only filesystem, no sudo, OOM kill, timeout.      │
│    9 handlers. Method-agnostic — checked regardless of which PM      │
│    was used.                                                         │
└─────────────────────────────┬────────────────────────────────────────┘
                              │ no match
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    LAYER 0 — Bootstrap                                │
│    (BOOTSTRAP_HANDLERS — this package, bootstrap.py)                 │
│                                                                      │
│    Lowest-level: no package manager found, no shell found.           │
│    2 handlers. Only reached when none of the above layers matched.   │
└──────────────────────────────────────────────────────────────────────┘
```

Every consumer does flat symbol import:

```python
from src.core.services.tool_install.data.remediation_handlers import (
    METHOD_FAMILY_HANDLERS,
    INFRA_HANDLERS,
    BOOTSTRAP_HANDLERS,
    LIB_TO_PACKAGE_MAP,
)
```

The internal package structure is invisible to consumers.

---

## Package Structure

```
remediation_handlers/
├── __init__.py                  ← Re-exports all 7 public symbols
│
├── constants.py                 ← VALID_STRATEGIES, VALID_AVAILABILITY, VALID_CATEGORIES
│
├── method_families/             ← Layer 2 — one file per method family (66 handlers)
│   ├── __init__.py              ← Merges all 19 → METHOD_FAMILY_HANDLERS
│   ├── pip.py                   ← pip    (11 handlers, 31 options)
│   ├── pipx.py                  ← pipx   (2 handlers, 3 options)
│   ├── cargo.py                 ← cargo  (6 handlers, 8 options)
│   ├── go.py                    ← go     (3 handlers, 5 options)
│   ├── npm.py                   ← npm    (12 handlers, 23 options)
│   ├── apt.py                   ← apt    (2 handlers, 4 options)
│   ├── dnf.py                   ← dnf    (1 handler, 2 options)
│   ├── yum.py                   ← yum    (1 handler, 2 options)
│   ├── snap.py                  ← snap   (1 handler, 2 options)
│   ├── brew.py                  ← brew   (1 handler, 2 options)
│   ├── apk.py                   ← apk    (2 handlers, 5 options)
│   ├── pacman.py                ← pacman (2 handlers, 4 options)
│   ├── zypper.py                ← zypper (2 handlers, 4 options)
│   ├── default.py               ← _default fallback scripts (5 handlers, 8 options)
│   ├── gem.py                   ← gem    (2 handlers, 5 options)
│   ├── source.py                ← source builds (5 handlers, 7 options)
│   ├── composer.py              ← composer_global (2 handlers, 4 options)
│   ├── curl_pipe_bash.py        ← curl|bash scripts (3 handlers, 6 options)
│   └── github_release.py        ← GitHub release downloads (3 handlers, 6 options)
│
├── infra.py                     ← Layer 1 — INFRA_HANDLERS (9 handlers, 17 options)
├── bootstrap.py                 ← Layer 0 — BOOTSTRAP_HANDLERS (2 handlers, 3 options)
└── lib_package_map.py           ← LIB_TO_PACKAGE_MAP (16 C-lib → distro-package entries)
```

---

## Handler Model Reference

Handlers are not scripts. They are **declarative failure-pattern-to-remediation maps**.
The domain layer (`handler_matching.py`) matches stderr against handler patterns at runtime.
The planning layer (`remediation_planning.py`) computes option availability.
What's stored here is pure data — the knowledge base, not the runtime logic.

### Handler Fields

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `pattern` | `str` (regex) | ✅ | Regex matched against stderr + stdout |
| `failure_id` | `str` | ✅ | Unique identifier for this failure mode |
| `category` | `str` | ✅ | Failure domain (see `VALID_CATEGORIES`) |
| `label` | `str` | ✅ | Human-readable failure name |
| `description` | `str` | ✅ | Explanation of what went wrong and why |
| `example_stderr` | `str` | | Real-world stderr that triggers this handler |
| `exit_code` | `int` | | Match on exit code instead of/in addition to pattern |
| `options` | `list[dict]` | ✅ | Remediation options (see below) |

### Option Fields

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `id` | `str` | ✅ | Unique option identifier within this handler |
| `label` | `str` | ✅ | Human-readable option name |
| `description` | `str` | ✅ | What this option does |
| `icon` | `str` | ✅ | Emoji icon for UI display |
| `recommended` | `bool` | ✅ | Whether this is the suggested default |
| `strategy` | `str` | ✅ | Remediation strategy (see `VALID_STRATEGIES`) |
| `risk` | `str` | | `medium`, `high`, `critical` — risk classification |
| `modifier` | `dict` | | Modifiers applied when retrying (see below) |
| `packages` | `dict[str, list]` | | Per-distro packages to install |
| `dynamic_packages` | `bool` | | If `True`, resolve packages via `LIB_TO_PACKAGE_MAP` |
| `fix_commands` | `list[list]` | | Commands to fix the environment before retry |
| `cleanup_commands` | `list[list]` | | Commands to run before retry (cache clearing, etc.) |
| `pre_packages` | `dict[str, list]` | | Per-distro packages needed BEFORE fix_commands |
| `dep` | `str` | | Tool/binary to install as a dependency |
| `switch_to` | `str` | | Method to switch to after dep install |
| `method` | `str` | | Method to switch to (for `switch_method` strategy) |
| `instructions` | `str` | | Manual instructions for the user |
| `env_override` | `dict[str, str]` | | Environment variables to set for retry |

### Strategies

| Strategy | What It Does |
|----------|-------------|
| `install_dep` | Install a missing dependency, then retry the original command |
| `install_dep_then_switch` | Install a dependency (e.g. `uv`), then switch install method to it |
| `install_packages` | Install system packages via the detected package manager |
| `switch_method` | Abandon current method, retry with a different install method |
| `retry_with_modifier` | Retry the same command with extra arguments or flags |
| `add_repo` | Add a package repository, then retry |
| `upgrade_dep` | Upgrade a dependency to a newer version, then retry |
| `env_fix` | Run fix commands to repair the environment, then retry |
| `manual` | Present instructions to the user — no automated fix |
| `cleanup_retry` | Run cleanup commands, then retry the original command |
| `retry` | Retry the original command without changes |

---

## Advanced Feature Showcase

### 1. Multi-Option Remediation Trees (pip PEP 668 — 6 options)

The most complex handler in the system. A single failure pattern (`externally.managed.environment`)
offers **6 different remediation paths**, each with its own strategy, prerequisites,
risk level, and environment requirements:

```python
# method_families/pip.py — handler: pep668
{
    "pattern": r"externally.managed.environment",
    "failure_id": "pep668",
    "category": "environment",
    "label": "Externally managed Python (PEP 668)",
    "options": [
        {
            "id": "use-venv",                              # ← recommended
            "strategy": "env_fix",
            "pre_packages": {                              # install python3-venv FIRST
                "debian": ["python3-venv"],
                "rhel": ["python3-virtualenv"],
            },
            "fix_commands": [                              # THEN create venv + install
                ["python3", "-m", "venv", "${HOME}/.local/venvs/tools"],
                ["${HOME}/.local/venvs/tools/bin/pip", "install", "${TOOL_PACKAGE}"],
            ],
        },
        {
            "id": "use-uv",                                # ← switch to a different PM
            "strategy": "install_dep_then_switch",
            "dep": "uv",                                   # install uv first
            "switch_to": "uv",                             # then re-resolve with uv
        },
        {
            "id": "use-conda",
            "strategy": "manual",                          # user-driven, no automation
            "instructions": "conda activate <env> && pip install <package>...",
        },
        {
            "id": "use-pipx",
            "strategy": "install_dep_then_switch",
            "dep": "pipx",
            "switch_to": "pipx",
        },
        {
            "id": "use-apt",
            "strategy": "switch_method",                   # abandon pip, use system PM
            "method": "apt",
        },
        {
            "id": "break-system",                          # ← nuclear option
            "strategy": "retry_with_modifier",
            "modifier": {"extra_args": ["--break-system-packages"]},
            "risk": "critical",                            # risk flag for UI warning
        },
    ],
}
```

One failure → six paths. The planner chooses which are available based on reality
(is `python3-venv` installable? is `uv` on PATH? does this system have apt?).

---

### 2. Distro-Aware Package Resolution (17 handlers)

Handlers that install system packages provide per-distro-family package lists.
The runtime reads the system profile and picks the right packages.

```python
# method_families/npm.py — handler: node_gyp_build_fail
{
    "pattern": r"node-gyp|gyp ERR!|make: \*\*\*.*Error",
    "failure_id": "node_gyp_build_fail",
    "category": "compiler",
    "options": [{
        "strategy": "install_packages",
        "packages": {
            "debian": ["build-essential", "python3"],      # Debian/Ubuntu
            "rhel":   ["gcc-c++", "make", "python3"],      # RHEL/Fedora/CentOS
            "alpine": ["build-base", "python3"],           # Alpine (musl)
            "arch":   ["base-devel", "python"],            # Arch Linux
            "suse":   ["devel_basis", "python3"],          # openSUSE
            "macos":  ["python3"],                         # Homebrew
        },
    }],
}
```

Same failure on Ubuntu → installs `build-essential`. Same failure on Alpine → installs `build-base`.

---

### 3. Dynamic Package Resolution via LIB_TO_PACKAGE_MAP

When a C linker error reports `cannot find -lssl`, the handler doesn't hard-code the fix.
It sets `dynamic_packages: True` and the runtime resolves `ssl` → `libssl-dev` (Debian)
or `openssl-devel` (RHEL) using `LIB_TO_PACKAGE_MAP`:

```python
# method_families/cargo.py — handler: missing_c_library
{
    "pattern": r"cannot find -l(\S+)",                     # captures library name
    "failure_id": "missing_c_library",
    "options": [{
        "strategy": "install_packages",
        "dynamic_packages": True,                          # ← runtime resolution
    }],
}

# lib_package_map.py — the resolution table
LIB_TO_PACKAGE_MAP = {
    "ssl":     {"debian": "libssl-dev",   "rhel": "openssl-devel",  "alpine": "openssl-dev",   ...},
    "crypto":  {"debian": "libssl-dev",   "rhel": "openssl-devel",  ...},
    "curl":    {"debian": "libcurl4-openssl-dev", "rhel": "libcurl-devel", ...},
    "z":       {"debian": "zlib1g-dev",   "rhel": "zlib-devel",     ...},
    "ffi":     {"debian": "libffi-dev",   "rhel": "libffi-devel",   ...},
    "sqlite3": {"debian": "libsqlite3-dev", "rhel": "sqlite-devel", ...},
    # ... 16 libraries total across 6 distro families
}
```

The regex captures the library name, `LIB_TO_PACKAGE_MAP` resolves it to the correct
distro-specific `-dev`/`-devel` package. One handler covers all C library link failures.

---

### 4. Retry Modifiers (14 handlers)

Instead of writing separate retry logic for each case, handlers declare
**modifiers** — small parameter tweaks applied to the original command:

```python
# Extra arguments
{"modifier": {"extra_args": ["--break-system-packages"]}}    # pip
{"modifier": {"extra_args": ["--force-reinstall"]}}          # pip
{"modifier": {"extra_args": ["--no-cache-dir"]}}             # pip
{"modifier": {"extra_args": ["--user"]}}                     # pip
{"modifier": {"extra_args": ["--prefer-binary"]}}            # pip

# Package manager flags
{"modifier": {"npm_legacy_peer_deps": True}}                 # npm --legacy-peer-deps
{"modifier": {"npm_force": True}}                            # npm --force
{"modifier": {"npm_ignore_scripts": True}}                   # npm --ignore-scripts
{"modifier": {"npm_use_latest": True}}                       # npm @latest

# Execution control
{"modifier": {"retry_sudo": True}}                           # prepend sudo
{"modifier": {"sudo": True}}                                 # same, different naming
{"modifier": {"reprompt_password": True}}                    # re-prompt for password
{"modifier": {"wait_seconds": 10, "retry": True}}            # wait then retry
{"modifier": {"reduce_parallelism": True}}                   # fewer build jobs
{"modifier": {"extend_timeout": True}}                       # double the timeout
{"modifier": {"use_compatible_version": True}}               # find older compat ver
```

The execution engine interprets these modifiers — the handler just declares the intent.

---

### 5. Environment Override for Compiler Switching (cargo)

When a GCC bug blocks compilation, the handler installs an alternative compiler
AND tells the retry to use it:

```python
# method_families/cargo.py — handler: gcc_memcmp_bug
{
    "pattern": r"COMPILER BUG DETECTED|memcmp.*gcc\.gnu\.org",
    "failure_id": "gcc_memcmp_bug",
    "options": [
        {
            "id": "install-gcc12",
            "strategy": "install_packages",
            "packages": {
                "debian": ["gcc-12", "g++-12"],
                "rhel": ["gcc-toolset-12-gcc", "gcc-toolset-12-gcc-c++"],
            },
            "env_override": {"CC": "gcc-12", "CXX": "g++-12"},  # ← use new compiler
        },
        {
            "id": "use-clang",
            "strategy": "install_dep",
            "dep": "clang",
            "env_override": {"CC": "clang", "CXX": "clang++"},  # ← alternative
        },
    ],
}
```

Install the fix AND rewire the build environment in one step.

---

### 6. Method Switching as Escalation (11 handlers)

When the primary install method fails irrecoverably, handlers offer to
**switch to a different method** entirely:

```python
# method_families/github_release.py — handler: github_rate_limit
{
    "failure_id": "github_rate_limit",
    "options": [
        {"strategy": "manual", "instructions": "Set GITHUB_TOKEN..."},
        {
            "strategy": "switch_method",
            "method": "brew",                              # ← abandon GitHub API, use brew
        },
    ],
}

# infra.py — handler: no_sudo_access
{
    "failure_id": "no_sudo_access",
    "options": [{
        "strategy": "switch_method",
        "method": "_default",                              # ← switch to user-space method
    }],
}
```

The planner re-resolves the entire install plan with the new method.

---

### 7. Exit Code Matching (infra)

Some failures don't produce identifiable stderr patterns — the process just dies.
The OOM killer sends `SIGKILL` (exit code 137) with no output:

```python
# infra.py — handler: oom_killed
{
    "pattern": r"",                                        # ← empty pattern!
    "exit_code": 137,                                      # ← match on exit code only
    "failure_id": "oom_killed",
    "category": "resources",
    "label": "Out of memory (killed by OOM)",
    "example_exit_code": 137,
    "options": [
        {"modifier": {"reduce_parallelism": True}},        # fewer make -j jobs
        {"strategy": "manual", "instructions": "Add swap..."},
    ],
}
```

Pattern is empty. Exit code is the sole signal. The matching engine handles both axes.

---

### 8. Chained Dependency Resolution (install_dep_then_switch)

The most sophisticated strategy: install a tool, then re-resolve the
entire install plan using that tool as the method:

```python
# method_families/pip.py — handler: pep668
{
    "id": "use-uv",
    "strategy": "install_dep_then_switch",
    "dep": "uv",                # 1. install uv (via its own recipe)
    "switch_to": "uv",         # 2. re-resolve original tool install via uv
}
```

This triggers a recursive resolution: the planner looks up the `uv` recipe,
resolves its install plan, executes it, then starts over with the original tool
but using `uv` as the install method. Two full resolution cycles, automated.

---

### 9. Pre-Package + Fix Command Chains (pip)

Some remediation requires a multi-step chain: install prerequisites,
then run fix commands:

```python
# method_families/pip.py — handler: pip_permission_denied
{
    "id": "use-venv",
    "strategy": "env_fix",
    "pre_packages": {                                      # STEP 1: system packages
        "debian": ["python3-venv"],
        "rhel": ["python3-virtualenv"],
        "suse": ["python3-virtualenv"],
    },
    "fix_commands": [                                      # STEP 2: fix the env
        ["python3", "-m", "venv", "${HOME}/.local/venvs/tools"],
        ["${HOME}/.local/venvs/tools/bin/pip", "install", "${TOOL_PACKAGE}"],
    ],
}
```

The planner executes `pre_packages` first (via the system PM), THEN runs `fix_commands`.
`${TOOL_PACKAGE}` is interpolated at runtime with the actual package name.

---

### 10. Container/Kubernetes Awareness (infra)

Infrastructure handlers detect container-specific failure modes that don't
happen on bare metal:

```python
# infra.py — handler: read_only_rootfs
{
    "pattern": r"Read-only file system|EROFS",
    "failure_id": "read_only_rootfs",
    "description": "Cannot write — likely a K8s pod with read-only root filesystem.",
    "options": [
        {
            "id": "use-writable-mount",
            "instructions": (
                "Kubernetes read-only rootfs detected.\n"
                "Options:\n"
                "  1. Add an emptyDir volume mount for tools:\n"
                "     volumes: [{name: tools, emptyDir: {}}]\n"
                "     volumeMounts: [{name: tools, mountPath: /opt/tools}]\n"
                "  2. Download pre-built binary to the writable path:\n"
                "     export PATH=/opt/tools/bin:$PATH\n"
                "  3. Or bake the tool into the container image."
            ),
        },
        {
            "id": "bake-into-image",
            "instructions": "Add to your Dockerfile:\n  RUN apt-get install -y <tool>",
        },
    ],
}
```

---

## Feature Coverage Summary

| Feature | Count | Example |
|---------|------|---------:|
| Regex pattern matching | 77 handlers | Every handler |
| Multi-option remediation | 61 handlers | pip pep668 (6 options), pip permission (4) |
| Distro-aware packages | 14 handlers | npm node-gyp, pip wheel build, cargo compiler |
| `retry_with_modifier` | 27 handlers | pip --force-reinstall, npm --legacy-peer-deps |
| `switch_method` escalation | 19 handlers | github_release → brew, no_sudo → _default |
| `env_fix` with commands | 12 handlers | pip venv creation, npm prefix fix |
| `manual` instructions | 33 handlers | conda guidance, corporate CA setup |
| `install_dep_then_switch` | 4 handlers | pip → uv, pip → pipx |
| `install_packages` | 20 handlers | build-essential, ca-certificates |
| `dynamic_packages` | 6 handlers | cargo -lssl, source header, CMake |
| `env_override` | 2 options | cargo gcc→gcc-12, cargo gcc→clang |
| `pre_packages` chain | 4 handlers | python3-venv before venv creation |
| `cleanup_retry` | 7 handlers | npm cache, pip cache, apt cache |
| `exit_code` matching | 1 handler | OOM kill (exit 137) |
| `risk` classification | 11 handlers | break-system-packages (critical), --force (high) |
| Container/K8s awareness | 1 handler | read-only rootfs |

---

## Utility Data: LIB_TO_PACKAGE_MAP

Maps C library short names (from linker errors) to distro-specific
development package names. Used by `dynamic_dep_resolver.py`.

| Library | Debian | RHEL | Alpine | Arch | SUSE |
|---------|--------|------|--------|------|------|
| `ssl` | `libssl-dev` | `openssl-devel` | `openssl-dev` | `openssl` | `libopenssl-devel` |
| `crypto` | `libssl-dev` | `openssl-devel` | `openssl-dev` | `openssl` | `libopenssl-devel` |
| `curl` | `libcurl4-openssl-dev` | `libcurl-devel` | `curl-dev` | `curl` | `libcurl-devel` |
| `z` | `zlib1g-dev` | `zlib-devel` | `zlib-dev` | `zlib` | `zlib-devel` |
| `ffi` | `libffi-dev` | `libffi-devel` | `libffi-dev` | `libffi` | `libffi-devel` |
| `sqlite3` | `libsqlite3-dev` | `sqlite-devel` | `sqlite-dev` | `sqlite` | `sqlite3-devel` |
| `xml2` | `libxml2-dev` | `libxml2-devel` | `libxml2-dev` | `libxml2` | `libxml2-devel` |
| `yaml` | `libyaml-dev` | `libyaml-devel` | `yaml-dev` | `libyaml` | `libyaml-devel` |
| `readline` | `libreadline-dev` | `readline-devel` | `readline-dev` | `readline` | `readline-devel` |
| `bz2` | `libbz2-dev` | `bzip2-devel` | `bzip2-dev` | `bzip2` | `libbz2-devel` |
| `lzma` | `liblzma-dev` | `xz-devel` | `xz-dev` | `xz` | `xz-devel` |
| `gdbm` | `libgdbm-dev` | `gdbm-devel` | `gdbm-dev` | `gdbm` | `gdbm-devel` |
| `ncurses` | `libncurses-dev` | `ncurses-devel` | `ncurses-dev` | `ncurses` | `ncurses-devel` |
| `png` | `libpng-dev` | `libpng-devel` | `libpng-dev` | `libpng` | `libpng16-devel` |
| `jpeg` | `libjpeg-dev` | `libjpeg-turbo-devel` | `libjpeg-turbo-dev` | `libjpeg-turbo` | `libjpeg-turbo-devel` |
| `pcre2-8` | `libpcre2-dev` | `pcre2-devel` | `pcre2-dev` | `pcre2` | `pcre2-devel` |

16 libraries × 5–6 distro families each = 83 package mappings.

---

## Validation Constants

Three sets define the valid field values, enforced by `recipe_schema.py`:

| Constant | Values |
|----------|--------|
| `VALID_STRATEGIES` | install_dep, install_dep_then_switch, install_packages, switch_method, retry_with_modifier, add_repo, upgrade_dep, env_fix, manual, cleanup_retry, retry |
| `VALID_AVAILABILITY` | ready, locked, impossible |
| `VALID_CATEGORIES` | environment, dependency, permissions, network, disk, resources, timeout, compiler, package_manager, bootstrap, install, compatibility, configuration |

---

## Adding a New Handler

1. **Identify the method family** — What install method caused the failure?
   pip failure → `method_families/pip.py`. Network issue → `infra.py`.

2. **Add the handler dict** to the appropriate file:
   ```python
   {
       "pattern": r"new_error_pattern_regex",
       "failure_id": "unique_failure_id",
       "category": "dependency",           # from VALID_CATEGORIES
       "label": "Human-readable label",
       "description": "What went wrong and why.",
       "example_stderr": "Actual stderr that triggers this",
       "options": [
           {
               "id": "fix-it",
               "label": "Recommended fix",
               "description": "What this option does",
               "icon": "🔧",
               "recommended": True,
               "strategy": "install_packages",    # from VALID_STRATEGIES
               "packages": {
                   "debian": ["package-name"],
                   "rhel": ["package-name-devel"],
               },
           },
       ],
   }
   ```

3. **Done.** No imports to update, no `__init__.py` changes,
   no consumer changes. The merge chain picks it up automatically.

### If adding a new method family:

1. Create `method_families/new_method.py` with `_NEW_METHOD_HANDLERS: list[dict]`
2. Add the import + key in `method_families/__init__.py`
3. That's it — consumers still just use `METHOD_FAMILY_HANDLERS`

---

## Design Decisions

### Why layer-based organization?

The layers mirror the matching priority. A pip-specific handler is more precise
than a generic network handler — the file structure makes this priority visible.
You don't grep a 3,700-line file to find your handler. You open the method family file.

### Why one file per method family, not grouped?

Same reason as recipes: the file name IS the documentation. A developer debugging
an npm failure opens `method_families/npm.py`. They don't scroll through a file
containing 19 unrelated method families or search for `"npm":` in a 3,000-line dict.

### Why `dynamic_packages` instead of hard-coded packages?

C library names are captured from linker errors at runtime (`cannot find -lssl`).
The library name is dynamic — it depends on what the crate/package tried to link.
Hard-coding packages per handler would require one handler per library.
`dynamic_packages: True` + `LIB_TO_PACKAGE_MAP` handles all 16 libraries with
one handler definition.

### Why `example_stderr` on every handler?

It's documentation that doubles as test data. The matching tests use these
examples to verify the regex patterns actually match real-world errors.
No example = untestable handler.
