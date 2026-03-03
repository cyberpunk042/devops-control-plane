# CLI Domain: Docs — Documentation Status, Coverage, Links & Generation

> **1 file · 265 lines · 5 commands + 1 subgroup · Group: `controlplane docs`**
>
> Analyzes project documentation: detects README, changelog, license,
> API specs, and key governance files; measures per-module documentation
> coverage; checks markdown files for broken internal links; generates
> CHANGELOG.md from git history and README.md from project metadata.
>
> Core service: `core/services/docs_svc/ops.py`

---

## How It Works

```
┌──────────────────────────────────────────────────────────────────────┐
│                        controlplane docs                            │
│                                                                      │
│  ┌─ Detect ──┐   ┌──── Observe ─────────┐   ┌── Generate ────────┐ │
│  │ status    │   │ coverage             │   │ generate changelog │ │
│  └───────────┘   │ links [--file PATH]  │   │ generate readme    │ │
│                   └─────────────────────-┘   └────────────────────┘ │
└──────────┬────────────────┬──────────────────────┬─────────────────┘
           │                │                      │
           ▼                ▼                      ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     core/services/docs_svc/ops.py                   │
│                                                                      │
│  docs_status(root)                                                   │
│    ├── Check for README.md (exists, lines, headings)                │
│    ├── Scan doc directories (docs/, doc/)                           │
│    ├── Detect API specs (OpenAPI, Swagger, GraphQL)                 │
│    └── Check key files: CHANGELOG, LICENSE, CONTRIBUTING,           │
│        CODE_OF_CONDUCT, SECURITY                                    │
│                                                                      │
│  docs_coverage(root)     → coverage %, documented/total, modules[]  │
│  check_links(root, file) → ok, broken[], total_links                │
│  generate_changelog(root, max, since) → file data                  │
│  generate_readme(root)   → file data                               │
└──────────────────────────────────────────────────────────────────────┘
```

### Status Detection

The `status` command provides a comprehensive view of the project's
documentation health by checking five distinct categories:

```
status(root)
├── README
│   ├── Exists? → path, line count
│   └── Parse heading structure (first 5 headings)
├── Documentation directories
│   ├── docs/ → doc files count, total files count
│   └── doc/ → doc files count, total files count
├── API specifications
│   ├── openapi.yaml / swagger.json
│   └── schema.graphql
├── Key governance files
│   ├── CHANGELOG.md → exists, path
│   ├── LICENSE → exists, path
│   ├── CONTRIBUTING.md → exists, path
│   ├── CODE_OF_CONDUCT.md → exists, path
│   └── SECURITY.md → exists, path
└── Return combined result dict
```

### Coverage Analysis

```
coverage(root)
├── Discover all project modules (via stack detection)
├── For each module:
│   ├── Has README.md? → documented
│   ├── Has doc files? → count
│   └── Stack type? → label
├── Calculate: documented / total = coverage %
└── Return coverage %, per-module details, module list
```

Coverage is color-coded by health: ≥80% green, ≥50% yellow, <50% red.

### Link Checking

```
links(root, file=None)
├── If --file specified → check only that file
│   └── Else → find all *.md files in project
├── For each markdown file:
│   ├── Parse all [text](link) patterns
│   ├── For internal links:
│   │   ├── Resolve relative path from file location
│   │   └── Check if target exists on disk
│   └── Record broken links with file, line, reason
├── Return:
│   ├── ok=true → all links valid
│   └── ok=false → broken[], broken_count
└── Display: first 20 broken links + "... and N more"
```

### Changelog Generation

```
generate changelog --commits 50 --since 2025-01-01
├── Read git log (last N commits, or since date)
├── Group commits by date or conventional commit type
├── Format as CHANGELOG.md content
├── Return {file: {path, content, reason}, commits: N}
└── Preview (first 40 lines) or --write to disk
```

---

## Commands

### `controlplane docs status`

Show documentation status: README, directories, API specs, governance files.

```bash
controlplane docs status
controlplane docs status --json
```

**Output example:**

```
📚 Documentation Status:

   📖 README: README.md (245 lines)
      # DevOps Control Plane
        ## Features
        ## Installation
        ## Usage
        ## Contributing

   📁 Documentation directories:
      docs/: 12 doc file(s), 18 total

   📡 API Specifications:
      openapi.yaml (openapi)

   📝 Changelog: CHANGELOG.md
   ⚖️  License: LICENSE
   🤝 Contributing guide: CONTRIBUTING.md
   📜 Code of Conduct: not found
   🔐 Security policy: SECURITY.md
```

---

### `controlplane docs coverage`

Check documentation coverage per project module.

```bash
controlplane docs coverage
controlplane docs coverage --json
```

**Output example:**

```
📊 Documentation Coverage: 75% (6/8 modules)

   ✅ api (python) [3 doc files]
      Path: src/api
   ✅ web (node) [1 doc files]
      Path: src/web
   ❌ workers (python)
      Path: src/workers
   ❌ scripts
      Path: scripts/
```

---

### `controlplane docs links`

Check for broken internal links in markdown files.

```bash
# Check all markdown files
controlplane docs links

# Check a specific file
controlplane docs links --file docs/architecture.md

# JSON output
controlplane docs links --json
```

**Output examples:**

```
🔗 Checking links...
✅ All links valid (42 links in 8 files)
```

```
🔗 Checking links...
❌ 3 broken link(s) found!

   ❌ docs/setup.md:15
      [installation guide](./install.md)
      Reason: File not found

   ❌ README.md:42
      [API docs](docs/api-reference.md)
      Reason: File not found
```

---

### `controlplane docs generate changelog`

Generate CHANGELOG.md from git history.

```bash
controlplane docs generate changelog
controlplane docs generate changelog --commits 100
controlplane docs generate changelog --since 2025-01-01
controlplane docs generate changelog --write
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--commits` | int | 50 | Maximum commits to include |
| `--since` | string | (none) | Only include commits since date (YYYY-MM-DD) |
| `--write` | flag | off | Write to disk |

**Preview output:** Shows first 40 lines of generated content + line count
for remainder. Uses the standard preview-or-write pattern.

---

### `controlplane docs generate readme`

Generate README.md template from project metadata.

```bash
controlplane docs generate readme
controlplane docs generate readme --write
```

Uses the standard preview-or-write pattern. The generated README pulls
project name, description, stack information, and module listing from
detected project context.

---

## File Map

```
cli/docs/
├── __init__.py    265 lines — group definition + 5 commands + generate subgroup
│                              + _resolve_project_root helper
└── README.md               — this file
```

**Total: 265 lines of Python in 1 file.**

---

## Per-File Documentation

### `__init__.py` — Group + all commands (265 lines)

**Groups:**

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `docs()` | Click group | Top-level `docs` group |
| `generate()` | Click group | `docs generate` subgroup |

**Commands:**

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `status(ctx, as_json)` | command | Detect README, doc dirs, API specs, governance files |
| `coverage(ctx, as_json)` | command | Per-module documentation coverage with % |
| `links(ctx, file_path, as_json)` | command | Broken internal link checker for markdown |
| `gen_changelog(ctx, commits, since, write)` | command (`generate changelog`) | Generate CHANGELOG.md from git log |
| `gen_readme(ctx, write)` | command (`generate readme`) | Generate README.md from project metadata |

**Helper:**

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `_resolve_project_root(ctx)` | helper | Reads `config_path` from context, falls back to `find_project_file()` |

**Code organization within the file:**

```python
# ── Detect ──    (status)                 lines 31-100
# ── Observe ──   (coverage, links)        lines 103-183
# ── Facilitate ── (generate subgroup)     lines 186-265
```

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `docs_status` | `docs_svc.ops` | Documentation status detection |
| `docs_coverage` | `docs_svc.ops` | Per-module coverage analysis |
| `check_links` | `docs_svc.ops` | Broken link checking |
| `generate_changelog` | `docs_svc.ops` | CHANGELOG.md generation from git |
| `generate_readme` | `docs_svc.ops` | README.md template generation |
| `write_generated_file` | `docker_ops` | Shared file writer (for generate commands) |

**Status display logic:** The status command renders five categories
in sequence, each conditionally: README (with heading parsing), doc
directories, API specs, and five governance files. Each governance file
is iterated from a constant tuple: `(key, icon, label)`.

**Coverage color coding:** Uses a three-tier threshold:
- `≥ 80%` → green (healthy)
- `≥ 50%` → yellow (needs attention)
- `< 50%` → red (critical)

**Link display truncation:** Shows at most 20 broken links with full
context (file, line number, link text, target, reason). If more than
20, shows `"... and N more"`.

**Changelog preview truncation:** Shows first 40 lines of generated
content. If longer, shows `"... (N more lines)"`. This prevents flooding
the terminal with a full changelog.

---

## Dependency Graph

```
__init__.py
├── click                      ← click.group, click.command
├── core.config.loader         ← find_project_file (lazy, _resolve_project_root)
├── core.services.docs_svc.ops ← docs_status, docs_coverage, check_links,
│                                 generate_changelog, generate_readme (all lazy)
└── core.services.docker_ops   ← write_generated_file (lazy, generate commands)
```

---

## Consumers

### Who registers this CLI group

| Layer | Module | What It Does |
|-------|--------|-------------|
| CLI entry | `src/main.py:460` | `from src.ui.cli.docs import docs` |

### Who also uses the same core service

| Layer | Module | Core Service Used |
|-------|--------|------------------|
| Web routes | `routes/docs/status.py` | `docs_svc.ops` (status, coverage) |
| Web routes | `routes/docs/generate.py` | `docs_svc.ops` (changelog, readme generation) |
| Core | `audit/l2_risk.py:289` | `check_links`, `docs_status` (documentation risk analysis) |

### Cross-domain dependency

| Import | From | Why |
|--------|------|-----|
| `write_generated_file` | `docker_ops` | Shared file writer for generate changelog/readme |

---

## Design Decisions

### Why all code is in __init__.py

With 265 lines and 5 commands, the domain is moderate-sized. All commands
import from the same core module (`docs_svc.ops`), so splitting by phase
(detect/observe/generate) would create 3 tiny files with no benefit.

### Why `generate changelog` truncates preview to 40 lines

Changelogs can be very long (50+ commits generate hundreds of lines).
Showing the full content in preview mode would flood the terminal.
The 40-line limit gives enough to verify the format and commit grouping
before committing to `--write`.

### Why `links` shows at most 20 broken links

A project with systemic link issues (e.g., renamed directories) can
have hundreds of broken links. Showing all of them is noise — the user
needs to fix the root cause (the rename) rather than fixing links
one by one. 20 samples are enough to identify the pattern.

### Why `links --file` exists

Link checking can be slow on large projects. The `--file` flag allows
checking a single file after editing it, without scanning the entire
project. This supports a fast edit-check-fix development loop.

### Why `coverage` uses stack detection

Documentation coverage is per-module, not per-file. To know which
modules exist, the command uses the same module detection as CI coverage
and other analysis commands. This ensures consistent module definitions
across all domains.

### Why governance files are enumerated as a tuple

The status command checks 5 governance files (changelog, license,
contributing, code of conduct, security policy). Rather than repeating
the same display logic 5 times, they're iterated from a tuple of
`(key, icon, label)` — reducing code duplication from ~50 lines to ~12.

---

## JSON Output Examples

### `docs status --json`

```json
{
  "readme": {
    "exists": true,
    "path": "README.md",
    "lines": 245,
    "headings": [
      {"level": 1, "text": "DevOps Control Plane"},
      {"level": 2, "text": "Features"},
      {"level": 2, "text": "Installation"}
    ]
  },
  "doc_dirs": [
    {"name": "docs", "doc_count": 12, "file_count": 18}
  ],
  "api_specs": [
    {"file": "openapi.yaml", "type": "openapi"}
  ],
  "changelog": {"exists": true, "path": "CHANGELOG.md"},
  "license": {"exists": true, "path": "LICENSE"},
  "contributing": {"exists": true, "path": "CONTRIBUTING.md"},
  "code_of_conduct": {"exists": false},
  "security_policy": {"exists": true, "path": "SECURITY.md"}
}
```

### `docs coverage --json`

```json
{
  "coverage": 0.75,
  "documented": 6,
  "total": 8,
  "modules": [
    {
      "name": "api",
      "stack": "python",
      "path": "src/api",
      "has_readme": true,
      "doc_files": 3
    },
    {
      "name": "workers",
      "stack": "python",
      "path": "src/workers",
      "has_readme": false,
      "doc_files": 0
    }
  ]
}
```

### `docs links --json`

```json
{
  "ok": false,
  "files_checked": 8,
  "total_links": 42,
  "broken_count": 3,
  "broken": [
    {
      "file": "docs/setup.md",
      "line": 15,
      "text": "installation guide",
      "link": "./install.md",
      "reason": "File not found"
    }
  ]
}
```
