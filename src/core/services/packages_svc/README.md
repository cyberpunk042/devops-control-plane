# Packages Service

> **3 files · 792 lines · Multi-ecosystem package management engine.**
>
> Detects package managers across 9 ecosystems (pip, npm, go, cargo,
> Maven, Gradle, .NET, Mix, Bundler), checks for outdated packages,
> runs security audits, lists installed packages, and provides
> install/update actions. Every operation auto-detects the correct
> package manager from dependency manifest files — no configuration
> needed.

---

## How It Works

### Architecture Overview

```
┌────────────────────────────────────────────────────────────────────┐
│ Two files, four operation tiers                                      │
│                                                                      │
│  ops.py    — DETECT tier                                            │
│  ──────    Package manager detection, status, per-module scan       │
│                                                                      │
│  actions.py — OBSERVE + ACT tiers                                   │
│  ──────────  Outdated, audit, list, install, update                 │
│                                                                      │
│  Pattern: Detect → Observe → Facilitate → Act                       │
│  (Facilitate is omitted — no config generation needed for packages) │
└────────────────────────────────────────────────────────────────────┘
```

### Detection Pipeline

```
package_status(project_root)
     │
     ├── _detect_pm_for_dir(project_root)
     │     │
     │     ├── For each of 9 package manager definitions:
     │     │     │
     │     │     ├── Scan for dependency files on disk:
     │     │     │     ├── requirements.txt, pyproject.toml, setup.py     (pip)
     │     │     │     ├── package.json                                    (npm)
     │     │     │     ├── go.mod                                          (go)
     │     │     │     ├── Cargo.toml                                      (cargo)
     │     │     │     ├── pom.xml                                         (maven)
     │     │     │     ├── build.gradle, build.gradle.kts                  (gradle)
     │     │     │     ├── *.csproj, *.fsproj                              (.NET)
     │     │     │     ├── mix.exs                                         (mix)
     │     │     │     └── Gemfile                                         (bundler)
     │     │     │
     │     │     ├── Scan for lock files:
     │     │     │     ├── requirements.txt / Pipfile.lock / poetry.lock   (pip)
     │     │     │     ├── package-lock.json / yarn.lock / pnpm-lock.yaml  (npm)
     │     │     │     ├── go.sum                                          (go)
     │     │     │     └── Cargo.lock / gradle.lockfile / Gemfile.lock     (others)
     │     │     │
     │     │     ├── Check CLI availability:
     │     │     │     ├── pip: sys.executable -m pip --version
     │     │     │     └── others: shutil.which(spec["cli"])
     │     │     │
     │     │     └── If dependency files found → record:
     │     │           {id, name, cli, cli_available,
     │     │            dependency_files, lock_files, has_lock}
     │     │
     │     └── Return list of detected managers
     │
     ├── Check for missing tools:
     │     └── check_required_tools([cli_ids where not available])
     │
     └── Return {managers, total_managers, has_packages, missing_tools}
```

### Enriched Status (with installed packages)

```
package_status_enriched(project_root)
     │
     ├── Call package_status(root) → base result
     │
     ├── For each manager with cli_available:
     │     └── package_list(root, manager) → {packages: [...]}
     │
     └── Return base + {installed_packages: {pip: [...], ...},
                          total_installed: N}
```

### Per-Module Detection

```
package_status_per_module(project_root, modules)
     │
     ├── For each module in project:
     │     ├── Module has {name, path}
     │     ├── Resolve module_dir = root / path
     │     │
     │     └── _detect_pm_for_dir(module_dir)
     │           → {managers, has_packages}
     │
     └── Return {modules: {module_name: {managers, has_packages}, ...}}
```

### Outdated Package Checking

```
package_outdated(root, *, manager=None)
     │
     ├── Auto-detect manager if not specified
     │
     ├── Dispatch to ecosystem-specific checker:
     │     │
     │     ├── pip:   sys.executable -m pip list --outdated --format json
     │     │     └── Parse JSON → [{name, current, latest, type}]
     │     │
     │     ├── npm:   npm outdated --json
     │     │     └── Parse JSON (exit code 1 is valid) → [{name, current, wanted, latest}]
     │     │
     │     ├── go:    go list -u -m -json all
     │     │     └── Parse concatenated JSON objects → [{name, current, latest}]
     │     │
     │     └── cargo: cargo outdated --format json (requires cargo-outdated)
     │           └── Parse JSON → [{name, current, latest}]
     │
     └── Return {ok, manager, outdated, count}
```

### Security Audit

```
package_audit(root, *, manager=None)
     │
     ├── Auto-detect manager if not specified
     │
     ├── Dispatch to ecosystem-specific auditor:
     │     │
     │     ├── pip:   pip-audit --format json
     │     │     ├── Not installed → {ok, available: False, message}
     │     │     └── Installed → parse vulnerabilities from dependencies[]
     │     │
     │     ├── npm:   npm audit --json
     │     │     └── Parse metadata.vulnerabilities → sum all severity counts
     │     │
     │     └── cargo: cargo audit --json
     │           ├── Not installed → {ok, available: False, message}
     │           └── Installed → count vulnerabilities.list[]
     │
     └── Return {ok, manager, vulnerabilities, output, available}
```

### Install & Update

```
package_install(root, *, manager=None)          package_update(root, *, package, manager)
     │                                                │
     ├── Auto-detect manager                          ├── Auto-detect manager
     │                                                │
     ├── Build command:                               ├── Build command:
     │     ├── pip:    pip install -e .               │     ├── pip:    pip install --upgrade [pkg]
     │     ├── npm:    npm ci                          │     ├── npm:    npm update [pkg]
     │     ├── go:     go mod download                │     ├── go:     go get -u [pkg | ./...]
     │     ├── cargo:  cargo fetch                    │     ├── cargo:  cargo update [-p pkg]
     │     ├── maven:  mvn dependency:resolve -q      │     └── others: not implemented
     │     ├── gradle: gradle dependencies --no-daemon -q│
     │     ├── mix:    mix deps.get                   └── Run with 300s timeout
     │     └── bundler: bundle install                      → {ok, manager, package, output}
     │
     └── Run with 300s timeout
           → {ok, manager, output}
```

---

## File Map

```
packages_svc/
├── __init__.py      8 lines   — public API re-exports
├── ops.py         275 lines   — detection, status, per-module scan
├── actions.py     509 lines   — outdated, audit, list, install, update
└── README.md                  — this file
```

---

## Per-File Documentation

### `ops.py` — Detection & Status (275 lines)

Contains the `_PACKAGE_MANAGERS` registry and detection logic.

**The Package Manager Registry:**

```python
_PACKAGE_MANAGERS = {
    "pip":     { stacks: ["python"],          files: ["requirements.txt", "pyproject.toml", ...] },
    "npm":     { stacks: ["node", "typescript"], files: ["package.json"] },
    "go":      { stacks: ["go"],              files: ["go.mod"] },
    "cargo":   { stacks: ["rust"],            files: ["Cargo.toml"] },
    "maven":   { stacks: ["java-maven", "java"], files: ["pom.xml"] },
    "gradle":  { stacks: ["java-gradle"],     files: ["build.gradle", "build.gradle.kts"] },
    "dotnet":  { stacks: ["dotnet"],          files: ["*.csproj", "*.fsproj"] },
    "mix":     { stacks: ["elixir"],          files: ["mix.exs"] },
    "bundler": { stacks: ["ruby"],            files: ["Gemfile"] },
}
```

Each entry also has `lock_files` (for detecting reproducible builds)
and `cli` (for checking tool availability).

**Private:**

| Function | What It Does |
|----------|-------------|
| `_run(args, cwd, timeout)` | `subprocess.run()` wrapper with capture + text + timeout |
| `_detect_pm_for_dir(directory)` | Detect all package managers in a directory |

**Public API:**

| Function | What It Does |
|----------|-------------|
| `package_status(root)` | Detect managers + check missing tools |
| `package_status_enriched(root)` | Status + installed package lists per manager |
| `package_status_per_module(root, modules)` | Per-module package manager detection |

### `actions.py` — Observe & Act (509 lines)

Imports `_run`, `_PACKAGE_MANAGERS`, and `_detect_pm_for_dir` from
`ops.py`. All public functions follow the same pattern: auto-detect
the manager if not specified, dispatch to the ecosystem-specific
implementation.

**Private helpers:**

| Function | What It Does |
|----------|-------------|
| `_pip_cmd(*args)` | Build `[sys.executable, "-m", "pip", ...]` command |
| `_resolve_manager(root)` | Auto-detect primary package manager |

**Ecosystem-specific outdated checkers:**

| Function | CLI Command | Output Format |
|----------|------------|---------------|
| `_pip_outdated(root)` | `pip list --outdated --format json` | JSON array |
| `_npm_outdated(root)` | `npm outdated --json` | JSON object `{name: {current, wanted, latest}}` |
| `_go_outdated(root)` | `go list -u -m -json all` | Concatenated JSON objects (one per line) |
| `_cargo_outdated(root)` | `cargo outdated --format json` | JSON with `dependencies[]` |

**Ecosystem-specific security auditors:**

| Function | CLI Tool | Availability |
|----------|---------|-------------|
| `_pip_audit(root)` | `pip-audit` | Optional — graceful degradation if not installed |
| `_npm_audit(root)` | `npm audit` | Built into npm |
| `_cargo_audit(root)` | `cargo-audit` | Optional — graceful degradation if not installed |

**Ecosystem-specific package listers:**

| Function | CLI Command | Output |
|----------|------------|--------|
| `_pip_list(root)` | `pip list --format json` | `[{name, version}]` |
| `_npm_list(root)` | `npm list --json --depth=0` | `{dependencies: {name: {version}}}` |

**Public API:**

| Function | What It Does |
|----------|-------------|
| `package_outdated(root, *, manager)` | Check outdated packages (4 ecosystems) |
| `package_audit(root, *, manager)` | Security vulnerability audit (3 ecosystems) |
| `package_list(root, *, manager)` | List installed packages (2 ecosystems) |
| `package_install(root, *, manager)` | Install dependencies (8 ecosystems) |
| `package_update(root, *, package, manager)` | Update packages (4 ecosystems) |

---

## Key Data Shapes

### package_status response

```python
{
    "managers": [
        {
            "id": "pip",
            "name": "pip",
            "cli": "pip",
            "cli_available": True,
            "dependency_files": ["requirements.txt", "pyproject.toml"],
            "lock_files": ["requirements.txt"],
            "has_lock": True,
        },
        {
            "id": "npm",
            "name": "npm",
            "cli": "npm",
            "cli_available": True,
            "dependency_files": ["package.json"],
            "lock_files": ["package-lock.json"],
            "has_lock": True,
        },
    ],
    "total_managers": 2,
    "has_packages": True,
    "missing_tools": [],
}
```

### package_outdated response

```python
# pip
{
    "ok": True,
    "manager": "pip",
    "outdated": [
        {"name": "requests", "current": "2.28.1", "latest": "2.31.0", "type": "sdist"},
        {"name": "flask", "current": "2.2.5", "latest": "3.0.0", "type": "bdist_wheel"},
    ],
    "count": 2,
}

# npm (note: includes "wanted" — semver-compatible latest)
{
    "ok": True,
    "manager": "npm",
    "outdated": [
        {"name": "express", "current": "4.18.2", "wanted": "4.18.3", "latest": "5.0.0", "type": "dependencies"},
    ],
    "count": 1,
}

# cargo (when cargo-outdated is not installed)
{
    "ok": True,
    "manager": "cargo",
    "outdated": [],
    "count": 0,
    "note": "Install cargo-outdated for full analysis: cargo install cargo-outdated",
}
```

### package_audit response

```python
# pip-audit installed
{
    "ok": True,
    "manager": "pip",
    "vulnerabilities": 3,
    "output": "{...truncated JSON output...}",
    "available": True,
}

# pip-audit NOT installed (graceful degradation)
{
    "ok": True,
    "manager": "pip",
    "vulnerabilities": 0,
    "output": "pip-audit not installed. Install with: pip install pip-audit",
    "available": False,
}
```

### package_install response

```python
{
    "ok": True,
    "manager": "pip",
    "output": "Successfully installed flask-3.0.0 werkzeug-3.0.1...",
}
```

### package_update response

```python
{
    "ok": True,
    "manager": "npm",
    "package": "express",        # or "all" for full update
    "output": "updated 1 package...",
}
```

---

## Package Manager Registry

Full reference of the `_PACKAGE_MANAGERS` constant:

| ID | Name | Stacks | Dependency Files | Lock Files | CLI |
|----|------|--------|-----------------|------------|-----|
| `pip` | pip | python | `requirements.txt`, `pyproject.toml`, `setup.py`, `setup.cfg`, `Pipfile` | `requirements.txt`, `Pipfile.lock`, `poetry.lock`, `pdm.lock` | `pip` |
| `npm` | npm | node, typescript | `package.json` | `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml` | `npm` |
| `go` | go modules | go | `go.mod` | `go.sum` | `go` |
| `cargo` | cargo | rust | `Cargo.toml` | `Cargo.lock` | `cargo` |
| `maven` | Maven | java-maven, java | `pom.xml` | *(none)* | `mvn` |
| `gradle` | Gradle | java-gradle | `build.gradle`, `build.gradle.kts` | `gradle.lockfile` | `gradle` |
| `dotnet` | .NET (NuGet) | dotnet | `*.csproj`, `*.fsproj` | `packages.lock.json` | `dotnet` |
| `mix` | Mix (Hex) | elixir | `mix.exs` | `mix.lock` | `mix` |
| `bundler` | Bundler | ruby | `Gemfile` | `Gemfile.lock` | `bundle` |

---

## Operation Coverage Matrix

Not every operation is implemented for every package manager:

| Operation | pip | npm | go | cargo | maven | gradle | dotnet | mix | bundler |
|-----------|-----|-----|----|-------|-------|--------|--------|-----|---------|
| **detect** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **outdated** | ✅ | ✅ | ✅ | ✅* | ❌ | ❌ | ❌ | ❌ | ❌ |
| **audit** | ✅* | ✅ | ❌ | ✅* | ❌ | ❌ | ❌ | ❌ | ❌ |
| **list** | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **install** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| **update** | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

`*` = Requires optional tool (`pip-audit`, `cargo-outdated`, `cargo-audit`).
When the tool is missing, the function returns `ok: True` with `available: False`
and a message explaining how to install it.

---

## pip CLI Behavior

pip is special-cased in the codebase. Instead of running the bare
`pip` binary (which may not be in PATH inside a virtual environment),
all pip commands use:

```python
[sys.executable, "-m", "pip", ...]
```

This ensures pip always runs in the **same Python environment** as
the application, regardless of PATH configuration or venv activation
method.

### pip-specific Detection

```python
# CLI availability check for pip (unique)
r = subprocess.run(
    [sys.executable, "-m", "pip", "--version"],
    capture_output=True, timeout=5,
)
cli_available = r.returncode == 0

# CLI availability check for all other managers
cli_available = shutil.which(spec["cli"]) is not None
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| **Routes** | `routes/packages/status.py` | `package_status`, `package_status_enriched`, `package_outdated`, `package_audit`, `package_list` |
| **Routes** | `routes/packages/actions.py` | `package_install`, `package_update` |
| **CLI** | `cli/packages/__init__.py` | `package_status`, `package_outdated`, `package_audit` |
| **Metrics** | `metrics/ops.py` | `package_status` (package manager detection) |
| **Audit** | `audit/l2_risk.py` | `package_audit`, `package_outdated` (risk register) |
| **Security** | `security/posture.py` | `package_audit` (security posture) |
| **Shims** | `package_ops.py` | Backward-compat re-export of `ops.py` |
| **Shims** | `package_actions.py` | Backward-compat re-export of `actions.py` |

---

## Dependency Graph

```
ops.py                              ← standalone (subprocess, pathlib, shutil)
   │                                     _PACKAGE_MANAGERS registry
   │                                     _detect_pm_for_dir() detection logic
   │                                     _run() subprocess wrapper
   │
   ├── tool_requirements             ← check_required_tools() for missing_tools
   └── actions (re-export at bottom) ← backward compatibility
   
actions.py                          ← imports from ops.py
   │
   ├── ops._run                     ← subprocess wrapper
   ├── ops._PACKAGE_MANAGERS        ← registry for spec lookups
   └── ops._detect_pm_for_dir      ← auto-detect manager
```

The dependency is **one-way**: `actions.py` imports from `ops.py`,
never the reverse. The `ops.py` file has re-exports at the bottom
for backward compatibility, but the core logic doesn't depend on
actions.

---

## Error Handling

Every function returns either `{ok: True, ...result}` or
`{error: "descriptive message"}`. Never raises exceptions
across the public API boundary.

### Error categories

| Error | Cause | Response |
|-------|-------|----------|
| No manager detected | No dependency files found | `{"error": "No package manager detected"}` |
| Unknown manager | Invalid manager ID passed | `{"error": "Unknown package manager: X"}` |
| CLI not installed | Tool not in PATH | `{"error": "pip not installed"}` |
| Command failed | Non-zero exit code | `{"error": "<stderr output>"}` |
| Not implemented | Operation unsupported for this ecosystem | `{"error": "Audit not implemented for Maven"}` |
| Optional tool missing | pip-audit / cargo-outdated absent | `{"ok": True, "available": False, "output": "install with..."}` |

Note the last category: **optional tools return `ok: True`** with
`available: False`. This is graceful degradation — the UI can show
a "tool not installed" message with an install button instead of
treating it as an error.

---

## Go Output Parsing

Go's `go list -u -m -json all` outputs concatenated JSON objects —
one per module — without array wrapping or delimiters:

```json
{
  "Path": "github.com/gin-gonic/gin",
  "Version": "v1.9.0",
  "Update": {"Version": "v1.9.1"}
}
{
  "Path": "golang.org/x/text",
  "Version": "v0.9.0"
}
```

The parser splits on `}\n{` and re-wraps each fragment to parse
individually. Only modules with an `"Update"` key are included
in the outdated results.

---

## npm Outdated Exit Code

npm has a non-standard behavior: `npm outdated --json` returns
**exit code 1** when outdated packages exist, and exit code 0
only when everything is current. The parser ignores the exit code
and parses stdout regardless — a non-zero exit code does NOT mean
the command failed.

---

## Command Timeouts

| Operation | Timeout | Rationale |
|-----------|---------|-----------|
| Detection (CLI check) | 5s | Quick version probe |
| Outdated check | 30s | Network call for each package registry |
| Security audit | 60-120s | pip-audit downloads advisory DB; npm audit calls registry |
| Package listing | 15s | Local operation, fast |
| Install / Update | 300s | May download + compile packages (Rust, C extensions) |

---

## Backward Compatibility

Two shim files remain at the services root:

```python
# package_ops.py
from src.core.services.packages_svc.ops import *  # noqa

# package_actions.py
from src.core.services.packages_svc.actions import *  # noqa
```

These shims allow old import paths to continue working
during the migration to the package structure.

---

## Advanced Feature Showcase

### 1. Venv-Safe pip Execution — `sys.executable` Over `shutil.which`

All pip commands route through the current Python interpreter:

```python
# actions.py — _pip_cmd (lines 30-36)

def _pip_cmd(*args: str) -> list[str]:
    return [sys.executable, "-m", "pip", *args]

# Usage in _pip_outdated:
r = _run(_pip_cmd("list", "--outdated", "--format", "json"), cwd=project_root, timeout=30)

# Usage in _pip_list:
r = _run(_pip_cmd("list", "--format", "json"), cwd=project_root, timeout=15)
```

Why not `shutil.which("pip")`? Inside a virtual environment, PATH may
contain the system pip first. `sys.executable -m pip` always invokes
the pip module from the *same Python* that's running the application.
This guarantees `package_list()` shows the venv's packages, not the
system's, and `package_install()` installs into the correct environment.

Detection also uses this pattern:

```python
# ops.py — _detect_pm_for_dir (lines 131-139)

if pm_id == "pip":
    r = subprocess.run(
        [sys.executable, "-m", "pip", "--version"],
        capture_output=True, timeout=5,
    )
    cli_available = r.returncode == 0
else:
    cli_available = shutil.which(spec["cli"]) is not None
```

### 2. Glob-Based vs Literal File Detection — Dual Scan Strategy

Some package managers use simple filenames, others use patterns:

```python
# ops.py — _detect_pm_for_dir (lines 118-126)

for pattern in spec["files"]:
    if "*" in pattern:
        # Glob: *.csproj, *.fsproj (dotnet)
        dep_files.extend(
            str(p.relative_to(directory))
            for p in directory.glob(pattern)
        )
    elif (directory / pattern).is_file():
        # Literal: requirements.txt, package.json, etc.
        dep_files.append(pattern)
```

Most ecosystems use literal filenames (`package.json`, `Cargo.toml`).
But .NET projects use `*.csproj` / `*.fsproj` because the filename
varies per project (e.g., `MyApp.csproj`, `MyLib.fsproj`). The glob
branch handles this — `directory.glob("*.csproj")` finds all matching
files and includes their relative paths.

### 3. Concatenated JSON Parsing — Go's Non-Standard Output

Go's `go list -u -m -json all` outputs concatenated JSON objects
without array wrapping:

```python
# actions.py — _go_outdated (lines 150-168)

# Output looks like: {...}\n{...}\n{...}
for line in r.stdout.strip().split("}\n{"):
    line = line.strip()
    if not line.startswith("{"):
        line = "{" + line
    if not line.endswith("}"):
        line = line + "}"
    try:
        mod = json.loads(line)
        update = mod.get("Update")
        if update:
            outdated.append({
                "name": mod.get("Path", ""),
                "current": mod.get("Version", ""),
                "latest": update.get("Version", ""),
            })
    except json.JSONDecodeError:
        continue
```

The split on `}\n{` breaks the concatenated stream into individual
objects, then each fragment is re-wrapped with braces. The first
fragment already starts with `{` (no prefix needed), and the last
already ends with `}` (no suffix needed) — but the guards handle
edge cases defensively. Only modules with an `"Update"` key
(meaning a newer version exists) are included in the result.

### 4. Graceful Degradation for Optional Audit Tools — ok: True, available: False

Optional security tools return success with a "not available" flag:

```python
# actions.py — _pip_audit (lines 247-254)

if not shutil.which("pip-audit"):
    return {
        "ok": True,
        "manager": "pip",
        "vulnerabilities": 0,
        "output": "pip-audit not installed. Install with: pip install pip-audit",
        "available": False,
    }

# actions.py — _cargo_outdated (lines 175-183)

if not shutil.which("cargo-outdated"):
    return {
        "ok": True,
        "manager": "cargo",
        "outdated": [],
        "count": 0,
        "note": "Install cargo-outdated for full analysis: cargo install cargo-outdated",
    }
```

This design decision prevents the UI from showing alarming red error
states for something that's merely an uninstalled *optional* tool.
The `ok: True` + `available: False` combination lets the dashboard
render a helpful "install this tool" button instead.

### 5. npm Exit-Code-1 Tolerance — Non-Standard Behavior Handling

npm returns exit code 1 when outdated packages exist:

```python
# actions.py — _npm_outdated (lines 113-137)

r = _run(["npm", "outdated", "--json"], cwd=project_root, timeout=30)

# npm outdated returns exit code 1 when outdated packages exist
try:
    data = json.loads(r.stdout) if r.stdout.strip() else {}
except json.JSONDecodeError:
    data = {}

outdated = [
    {"name": name, "current": info.get("current", ""),
     "wanted": info.get("wanted", ""), "latest": info.get("latest", ""),
     "type": info.get("type", "")}
    for name, info in data.items()
]
```

Notice: no `if r.returncode != 0: return error` guard. Unlike pip
(where non-zero means failure), npm uses exit code 1 to *signal*
outdated packages — not an error. The parser ignores the return code
entirely and parses stdout regardless.

### 6. `dict.fromkeys` Deduplication for Missing Tools — Order-Preserving Unique

Missing tool IDs are deduplicated before checking:

```python
# ops.py — package_status (lines 169-173)

tool_ids = list(dict.fromkeys(
    m["cli"] for m in managers if m.get("cli") and not m.get("cli_available")
))
from src.core.services.tool_requirements import check_required_tools
missing = check_required_tools(tool_ids) if tool_ids else []
```

If a project has both `pyproject.toml` (pip) and `setup.py` (pip),
the same manager is detected once (not twice), but the `cli` value
`"pip"` would appear in the generator. `dict.fromkeys()` eliminates
duplicates while preserving insertion order — `check_required_tools`
is called with each tool ID exactly once.

### 7. Output Truncation at 2000 Characters — Response Size Guard

CLI output is capped to keep API responses reasonable:

```python
# actions.py — _pip_audit (line 273)
"output": r.stdout.strip()[:2000],

# actions.py — _npm_audit (line 297)
"output": r.stdout.strip()[:2000],

# actions.py — package_install (line 450)
return {"ok": True, "manager": manager, "output": r.stdout.strip()[:2000]}

# actions.py — package_update (line 507)
"output": r.stdout.strip()[:2000],
```

Install/update/audit output can be enormous (megabytes for large
projects with many dependencies). The 2000-character cap ensures:
- JSON responses stay fast to serialize and transfer
- The UI gets enough context to show meaningful results
- Memory usage remains bounded for concurrent requests
- The first 2000 chars typically contain the most important info
  (summary lines, error messages, first few package names)

---

### Feature Coverage Summary

| Feature | Where | Complexity |
|---------|-------|-----------|
| Venv-safe pip execution | `actions.py` `_pip_cmd` + `ops.py` detection | `sys.executable -m pip` pattern |
| Glob vs literal file detection | `ops.py` `_detect_pm_for_dir` | `*` pattern branch for .NET projects |
| Concatenated JSON parsing | `actions.py` `_go_outdated` | Split + re-wrap + per-fragment parse |
| Graceful audit degradation | `actions.py` `_pip_audit`, `_cargo_*` | `ok: True, available: False` pattern |
| npm exit-code-1 tolerance | `actions.py` `_npm_outdated` | Skip returncode check, parse stdout |
| Missing tool deduplication | `ops.py` `package_status` | `dict.fromkeys()` order-preserving |
| Output truncation | All action functions | `[:2000]` response cap |

---

## Design Decisions

### Why 9 package managers in one registry?

Every package manager follows the same mental model: dependency
files → lock files → CLI tool → status/outdated/audit/install.
A single registry with per-ecosystem specializations (in actions.py)
keeps the pattern consistent. Adding a new ecosystem means adding
one dict entry to `_PACKAGE_MANAGERS` and implementing the specific
command functions.

### Why is ops.py the detection layer and actions.py the observe/act layer?

Detection (`_detect_pm_for_dir`) is used by 3 public functions in
ops.py and also by `_resolve_manager()` in actions.py. Keeping
detection in ops.py means actions.py has a clean one-way import —
it reads the registry and detection results, then dispatches to
ecosystem-specific implementations. This also keeps ops.py light
enough to import for status-only queries without pulling in the
heavier action code.

### Why auto-detect instead of requiring the manager parameter?

Most projects have one primary package manager. Requiring the user
(or the frontend) to specify it adds friction for the common case.
Auto-detect picks the first detected manager, which works for
single-ecosystem projects. Multi-ecosystem projects can override
with the explicit `manager` parameter.

### Why does pip use sys.executable instead of shutil.which?

Inside a virtual environment, `shutil.which("pip")` may find the
system pip instead of the venv pip. `sys.executable -m pip` always
runs the pip associated with the current Python interpreter,
guaranteeing packages are installed in the correct environment.

### Why graceful degradation for optional audit tools?

`pip-audit` and `cargo-audit` are separate installations. Returning
an error would make the security dashboard card show a red error
state for something that's a missing *optional* tool. Returning
`ok: True` with `available: False` lets the UI show a helpful
"install this tool" button instead of an alarming error message.

### Why is output truncated to 2000 characters?

CLI output from install/update/audit can be enormous (megabytes for
large projects). The API response needs to be JSON-serializable and
fast to transfer. 2000 characters captures enough context for the
UI to show meaningful results without bloating the response payload.

### Why `npm ci` instead of `npm install` for package_install?

`npm ci` is the reproducible install command — it installs from the
lock file exactly, removes node_modules first, and fails if the lock
file is out of sync with package.json. This is safer for a
DevOps control plane that should produce predictable results.
