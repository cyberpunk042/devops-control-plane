# CLI Domain: Packages — Detection, Audit, Outdated & Install/Update

> **1 file · 206 lines · 7 commands · Group: `controlplane packages`**
>
> Multi-manager package management: detect package managers
> (npm/pip/cargo/etc.), list installed packages, check for outdated
> versions, run security audits, install dependencies, and update
> packages. All commands auto-detect the project's package manager
> with optional explicit override.
>
> Core service: `core/services/packages_svc/ops.py` (re-exported via
> `package_ops.py`)

---

## How It Works

```
┌──────────────────────────────────────────────────────────────────────┐
│                      controlplane packages                          │
│                                                                      │
│  ┌── Detect ─┐   ┌──── Observe ──────────┐   ┌── Act ───────────┐  │
│  │ status    │   │ outdated [-m MGR]      │   │ install [-m MGR] │  │
│  └───────────┘   │ audit [-m MGR]         │   │ update [PKG]     │  │
│                   │ list [-m MGR]          │   │        [-m MGR]  │  │
│                   └───────────────────────-┘   └─────────────────-┘  │
└──────────┬──────────────────┬──────────────────────┬───────────────┘
           │                  │                      │
           ▼                  ▼                      ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  core/services/packages_svc/ops.py                  │
│                                                                      │
│  package_status(root)           → managers[], has_packages          │
│  package_outdated(root, mgr)    → outdated[], count, manager       │
│  package_audit(root, mgr)       → vulnerabilities, output          │
│  package_list(root, mgr)        → packages[], count, manager       │
│  package_install(root, mgr)     → installed result                 │
│  package_update(root, pkg, mgr) → updated result                   │
└──────────────────────────────────────────────────────────────────────┘
```

### Manager Auto-Detection

All observation and action commands accept `--manager/-m` to specify
which package manager to use. If not specified, the core service
auto-detects based on dependency files in the project root:

```
auto-detect(root)
├── pyproject.toml / requirements.txt → pip
├── package.json → npm (or yarn if yarn.lock exists)
├── Cargo.toml → cargo
├── go.mod → go
├── Gemfile → bundler
└── (first match wins)
```

### Detect-Observe-Act Pattern

```
status         → "What package managers do I have?"
outdated       → "Are any packages behind latest?"
audit          → "Are any packages vulnerable?"
list           → "What's currently installed?"
install        → "Install from lock/dependency file"
update [pkg]   → "Upgrade specific or all packages"
```

### Status Detection

The `status` command shows more than just which managers exist. For
each detected manager, it reports:

```
for each manager:
├── CLI availability (is pip/npm/cargo in PATH?)
├── CLI name
├── Dependency files found
├── Lock files found (or warning if missing)
└── Icon: ✅ cli available, ❌ not available
         🔒 has lock file, ⚠️ no lock file
```

### Audit Output Truncation

The `audit` command truncates security audit output to 1000 characters.
Security audit tools (npm audit, pip-audit, cargo audit) can produce
extremely verbose output with full advisory descriptions. The truncation
shows enough to identify the critical issues while keeping CLI output
manageable.

---

## Commands

### `controlplane packages status`

Show detected package managers and dependency files.

```bash
controlplane packages status
controlplane packages status --json
```

**Output example:**

```
📦 Package Managers:
   ✅ pip (pip)
      Files: pyproject.toml, requirements.txt
      🔒 Lock: requirements.lock
   ✅ npm (npm)
      Files: package.json
      ⚠️  No lock file
```

---

### `controlplane packages outdated`

Check for outdated packages.

```bash
controlplane packages outdated
controlplane packages outdated -m pip
controlplane packages outdated --json
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `-m/--manager` | string | (auto) | Package manager to use |
| `--json` | flag | off | JSON output |

**Output example:**

```
📦 Outdated (4, pip):
   click                          8.1.7        → 8.2.0
   httpx                          0.25.1       → 0.27.0
   cryptography                   41.0.7       → 43.0.1
   jinja2                         3.1.2        → 3.1.4
```

**All up to date:**

```
✅ All packages up to date
```

---

### `controlplane packages audit`

Run security audit on dependencies.

```bash
controlplane packages audit
controlplane packages audit -m npm
controlplane packages audit --json
```

**Output examples:**

```
✅ No vulnerabilities found (pip)
```

```
🚨 3 vulnerability(ies) found (npm)
   # npm audit output (first 1000 chars)
   moderate  prototype-pollution  >= 4.17.11 in lodash
   high      arbitrary-code-exec  < 5.0.1 in some-package
   ...
```

---

### `controlplane packages list`

List installed packages.

```bash
controlplane packages list
controlplane packages list -m pip
controlplane packages list --json
```

**Display cap:** Shows at most 50 packages. If more, shows
`"... and N more"`.

**Output example:**

```
📦 Installed (128, pip):
   click                              8.1.7
   httpx                              0.25.1
   jinja2                             3.1.2
   ...and 125 more
```

---

### `controlplane packages install`

Install dependencies from the project's dependency/lock file.

```bash
controlplane packages install
controlplane packages install -m npm
```

**Output:** `"✅ Installed (pip)"`

---

### `controlplane packages update`

Update packages (specific or all).

```bash
# Update all packages
controlplane packages update

# Update specific package
controlplane packages update click

# With explicit manager
controlplane packages update click -m pip
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `PACKAGE` | argument | (optional) | Specific package to update |
| `-m/--manager` | string | (auto) | Package manager to use |

---

## File Map

```
cli/packages/
├── __init__.py    206 lines — group definition + 7 commands
│                              + _resolve_project_root helper
└── README.md               — this file
```

**Total: 206 lines of Python in 1 file.**

---

## Per-File Documentation

### `__init__.py` — Group + all commands (206 lines)

**Group:**

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `packages()` | Click group | Top-level `packages` group |

**Commands:**

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `status(ctx, as_json)` | command | Detect package managers, show CLI + lock file status |
| `outdated(ctx, manager, as_json)` | command | List packages with newer versions available |
| `audit(ctx, manager, as_json)` | command | Run security vulnerability audit |
| `list_packages(ctx, manager, as_json)` | command (`list`) | List installed packages (display capped at 50) |
| `install(ctx, manager)` | command | Install dependencies from lock/config file |
| `update(ctx, package, manager)` | command | Update specific package or all packages |

**Helper:**

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `_resolve_project_root(ctx)` | helper | Reads `config_path` from context, falls back to `find_project_file()` |

**Code organization within the file:**

```python
# ── Detect ──    (status)                      lines 31-62
# ── Observe ──   (outdated, audit, list)       lines 65-162
# ── Act ──       (install, update)             lines 165-206
```

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `package_status` | `packages_svc.ops` | Manager detection |
| `package_outdated` | `packages_svc.ops` | Version comparison |
| `package_audit` | `packages_svc.ops` | Security audit |
| `package_list` | `packages_svc.ops` | Installed package listing |
| `package_install` | `packages_svc.ops` | Dependency installation |
| `package_update` | `packages_svc.ops` | Package update |

**Status dual-icon system:** Each manager shows two icons:
- CLI availability: ✅ (cli available) / ❌ (not found)
- Lock file: 🔒 (has lock) / ⚠️ (no lock file)

This gives a quick visual assessment of project health.

**Outdated format:** Uses fixed-width formatting for aligned columns:
`name:<30` (left-aligned 30 chars), `current:<12` (12 chars), `→ latest`.

**Audit output cap:** Security audit output is truncated at 1000
characters. npm audit in particular can produce extremely long output
with full advisory text, CVE numbers, and remediation steps.

**List display cap:** List is capped at 50 entries. A Python project
can have 200+ transitive dependencies. Showing all of them in the
terminal is noise — JSON output provides the full list.

---

## Dependency Graph

```
__init__.py
├── click                        ← click.group, click.command
├── core.config.loader           ← find_project_file (lazy)
└── core.services.packages_svc   ← package_status, package_outdated,
                                    package_audit, package_list,
                                    package_install, package_update (all lazy)
```

Single file, no internal dependencies.

---

## Consumers

### Who registers this CLI group

| Layer | Module | What It Does |
|-------|--------|-------------|
| CLI entry | `src/main.py:455` | `from src.ui.cli.packages import packages` |

### Who also uses the same core service

| Layer | Module | Core Service Used |
|-------|--------|------------------|
| Web routes | `routes/packages/status.py` | `packages_svc.ops` (status, outdated) |
| Web routes | `routes/packages/actions.py` | `packages_svc.ops` (install, update) |
| Core | `metrics/ops.py:188` | `package_status`, `package_outdated` (metrics probe) |
| Core | `audit/l2_risk.py:215` | `package_audit`, `package_outdated` (risk scoring) |
| Core | `security/posture.py:235` | `package_audit` (security posture calculation) |

### Note on cross-service usage

The `packages_svc` core service is one of the most widely consumed:
metrics checks for outdated packages in health probes, the audit
system uses vulnerability counts for risk scoring, and the security
posture system factors audit results into the overall security score.

---

## Design Decisions

### Why all 7 commands are in one file

At 206 lines, the domain is moderate-sized with all commands importing
from the same core module. Splitting would create multiple tiny files
with no practical benefit.

### Why `-m/--manager` exists on every observe/act command

While auto-detection works for most projects, multi-language monorepos
can have both `pyproject.toml` and `package.json`. The explicit
`--manager` flag lets users target a specific ecosystem.

### Why `audit` truncates at 1000 characters

Security audit output varies wildly between managers. `npm audit` can
produce 5-10KB of text for a few vulnerabilities. The truncation shows
enough to identify the scope of the problem; the `--json` flag provides
full structured data for automation.

### Why `list` caps at 50

A modern Python project can have 200+ packages (including transitive
dependencies). Terminal display of all 200+ is noise — users looking
at specific packages should use `--json` and pipe through `jq`.

### Why `install` has no `--json` flag

Installation is an imperative action. The outcome is "installed" or
"error" — no structured data to return beyond the exit code.

### Why `update` takes an optional package argument (not flags)

The primary use case is `packages update requests` — update a specific
package by name. Making it a positional argument keeps the most common
invocation minimal. Omitting it updates everything, which is the
second most common use case.

### Why `outdated` shows a `note` field

When all packages are up to date, some managers emit helpful notes
(e.g., "pip: 3 packages pinned, not checked" or "npm: excluded
devDependencies"). The `note` field surfaces this information so
users understand why certain packages weren't checked.

### Why `status` reports lock files explicitly

Lock files are critical for reproducible builds. A project without
a lock file will get different dependency versions on different
machines. Making lock file presence a first-class status indicator
alerts teams to missing lock files early.

---

## JSON Output Examples

### `packages status --json`

```json
{
  "has_packages": true,
  "managers": [
    {
      "name": "pip",
      "cli": "pip",
      "cli_available": true,
      "dependency_files": ["pyproject.toml", "requirements.txt"],
      "lock_files": ["requirements.lock"],
      "has_lock": true
    },
    {
      "name": "npm",
      "cli": "npm",
      "cli_available": true,
      "dependency_files": ["package.json"],
      "lock_files": [],
      "has_lock": false
    }
  ]
}
```

### `packages outdated --json`

```json
{
  "manager": "pip",
  "count": 4,
  "outdated": [
    {"name": "click", "current": "8.1.7", "latest": "8.2.0"},
    {"name": "httpx", "current": "0.25.1", "latest": "0.27.0"},
    {"name": "cryptography", "current": "41.0.7", "latest": "43.0.1"},
    {"name": "jinja2", "current": "3.1.2", "latest": "3.1.4"}
  ]
}
```

### `packages audit --json`

```json
{
  "manager": "pip",
  "available": true,
  "vulnerabilities": 2,
  "output": "Found 2 known vulnerabilities...\nPKG-2024-001 (high): ..."
}
```

### `packages list --json`

```json
{
  "manager": "pip",
  "count": 128,
  "packages": [
    {"name": "click", "version": "8.1.7"},
    {"name": "httpx", "version": "0.25.1"},
    {"name": "jinja2", "version": "3.1.2"}
  ]
}
```
