# Documentation Service Domain

> **3 files · 700 lines · Documentation health analysis, link checking, and generation.**
>
> README detection with heading extraction, documentation directory
> inventory, API spec file detection, per-module documentation coverage
> analysis, internal link validation, changelog generation from
> git history, and README template generation from project metadata.

---

## How It Works

### Architecture Overview

```
┌────────────────────────────────────────────────────────────────────┐
│ Two files, three operation tiers                                    │
│                                                                      │
│  ops.py     — DETECT + OBSERVE tiers                                │
│  ──────     Status, coverage, link validation                       │
│                                                                      │
│  generate.py — FACILITATE tier                                      │
│  ───────────  Changelog from git, README from metadata              │
│                                                                      │
│  Pattern: Detect → Observe → Facilitate                             │
│  (Act is omitted — docs are generated, not mutated)                 │
└────────────────────────────────────────────────────────────────────┘
```

### Documentation Status Pipeline

```
docs_status(root)
     │
     ├── Find README (case-insensitive search):
     │     ├── _find_readme(root)
     │     │     └── Try: README.md, README.rst, README.txt, README, readme.md
     │     │
     │     ├── If found:
     │     │     ├── Read file size + line count
     │     │     ├── Extract headings (_extract_headings):
     │     │     │     └── Regex: ^#{1,6}\s+(.+)$
     │     │     │     └── Return [{level, text}, ...] (max 10)
     │     │     └── Record {exists: True, path, size, lines, headings}
     │     │
     │     └── If not found:
     │           └── {exists: False}
     │
     ├── Scan documentation directories:
     │     ├── Check for: docs/, doc/, documentation/, wiki/
     │     │
     │     ├── For each found directory:
     │     │     ├── Count all files (rglob "*")
     │     │     ├── Count doc files (.md, .rst, .txt, .adoc, .asciidoc, .textile)
     │     │     ├── Sum total size
     │     │     └── Record {name, file_count, doc_count, total_size}
     │     │
     │     └── Return doc_dirs[]
     │
     ├── Count root-level documentation files:
     │     └── root_doc_files = count of files with doc extensions at project root
     │
     ├── Detect API specification files:
     │     └── _detect_api_specs(root)
     │           ├── Load patterns from DataRegistry: _api_spec_files()
     │           ├── For glob patterns → rglob(pattern), skip _SKIP_DIRS
     │           ├── For exact names → check existence
     │           └── Return [{file, type, format}]
     │
     ├── Check key documentation files (5 categories):
     │     ├── changelog  → CHANGELOG.md, CHANGELOG, CHANGES.md, HISTORY.md
     │     ├── license    → LICENSE, LICENSE.md, LICENSE.txt, LICENCE
     │     ├── contributing → CONTRIBUTING.md, CONTRIBUTING, CONTRIBUTE.md
     │     ├── code_of_conduct → CODE_OF_CONDUCT.md
     │     └── security_policy → SECURITY.md
     │
     ├── Check missing tools:
     │     └── check_required_tools(["git"])
     │
     └── Return {readme, doc_dirs, root_doc_files, api_specs,
                  changelog, license, contributing, code_of_conduct,
                  security_policy, missing_tools}
```

### Documentation Coverage

```
docs_coverage(root)
     │
     ├── Load project metadata:
     │     ├── load_project(root / "project.yml")
     │     ├── discover_stacks(root / "stacks")
     │     └── detect_modules(project, root, stacks)
     │
     ├── For each detected module:
     │     ├── Resolve module directory:
     │     │     └── root / module.path (or root if path == ".")
     │     │
     │     ├── Check for README:
     │     │     └── _find_readme(mod_path) → bool
     │     │
     │     ├── Count doc files:
     │     │     └── rglob("*") → filter by _DOC_EXTENSIONS
     │     │         └── Skip _SKIP_DIRS
     │     │
     │     └── Record {name, path, stack, has_readme, doc_files}
     │
     ├── Fallback (if detection fails):
     │     └── Single module = project root
     │
     ├── Compute coverage ratio:
     │     └── documented / total (where documented = has_readme)
     │
     └── Return {modules, coverage (0.0-1.0), total, documented}
```

### Link Validation

```
check_links(root, *, file_path=None)
     │
     ├── Collect target files:
     │     ├── If file_path → single file
     │     └── If None → _collect_md_files(root) (max 100 files)
     │           └── rglob("*.md"), skip _SKIP_DIRS
     │
     ├── For each .md file:
     │     ├── Build anchor index:
     │     │     ├── Scan all headings via _HEADING_ANCHOR_PATTERN
     │     │     └── Convert to GitHub-style anchors: _heading_to_anchor(text)
     │     │           ├── Lowercase
     │     │           ├── Strip non-alphanumeric (keep hyphens)
     │     │           └── Replace spaces with hyphens
     │     │
     │     ├── For each link found (via _LINK_PATTERN):
     │     │     │
     │     │     ├── Skip external: http://, https://, mailto:, ftp://
     │     │     ├── Skip data URIs: data:
     │     │     │
     │     │     ├── Anchor-only links (#section):
     │     │     │     ├── Check anchor exists in defined_anchors
     │     │     │     └── If missing → broken: "Anchor not found in file"
     │     │     │
     │     │     └── Relative file links (./file.md, ../dir/file):
     │     │           ├── Split off anchor portion (file#anchor → file)
     │     │           ├── Resolve path relative to current file's parent
     │     │           └── If not exists → broken: "File not found: X"
     │     │
     │     └── Count: files_checked, total_links
     │
     └── Return {files_checked, total_links, broken[], broken_count, ok}
```

### Changelog Generation

```
generate_changelog(root, *, max_commits=50, since=None)
     │
     ├── Build git command:
     │     ├── git log --max-count=N --format=%H|%ai|%s|%an
     │     └── Optional: --since=YYYY-MM-DD
     │
     ├── Run subprocess (timeout: 15s)
     │     └── Error → {"error": "Git unavailable: ..."}
     │
     ├── Parse each commit line (split on "|"):
     │     ├── commit_hash → short_hash (first 7 chars)
     │     ├── date_str → date_only (YYYY-MM-DD)
     │     ├── subject → conventional commit icon
     │     └── author
     │
     ├── Build CHANGELOG.md:
     │     ├── Header with commit count note
     │     ├── Group by date (## YYYY-MM-DD headings)
     │     └── Per commit: "- {icon} {subject} (`{short_hash}` by {author})"
     │
     ├── Wrap in GeneratedFile model:
     │     └── {path: "CHANGELOG.md", content, overwrite: True, reason}
     │
     └── Return {ok, file: {...}, commits}
```

### README Generation

```
generate_readme(root)
     │
     ├── Load project metadata:
     │     ├── project.yml → name
     │     ├── Stack discovery → stacks[]
     │     └── Module detection → modules[]
     │     └── Fallback: use directory name
     │
     ├── Build README.md template (stack-aware):
     │     ├── # Title
     │     ├── Badge placeholders (commented out)
     │     ├── Table of Contents
     │     ├── Overview (TODO placeholder)
     │     │
     │     ├── Getting Started:
     │     │     ├── Prerequisites (stack-specific):
     │     │     │     ├── python → Python 3.12+
     │     │     │     ├── node/typescript → Node.js 18+
     │     │     │     ├── go → Go 1.21+
     │     │     │     └── rust → Rust (stable)
     │     │     │
     │     │     └── Installation (stack-specific):
     │     │           ├── python → venv + pip install
     │     │           └── node → npm install
     │     │
     │     ├── Project Structure (if modules detected):
     │     │     └── Table: Module | Path | Stack
     │     │
     │     ├── Development (stack-specific test + lint commands)
     │     ├── Contributing (placeholder)
     │     └── License (placeholder)
     │
     ├── Wrap in GeneratedFile model:
     │     └── {path: "README.md", content, overwrite: False, reason}
     │
     └── Return {ok, file: {...}}
```

---

## Architecture

```
             Routes (docs/)
             CLI (docs/__init__.py)
             Audit (l2_risk.py)
                     │
                     │ imports
                     │
          ┌──────────▼──────────────────────────────┐
          │  docs_svc/__init__.py                     │
          │  Public API — re-exports 5 functions      │
          │  docs_status · docs_coverage · check_links│
          │  generate_changelog · generate_readme      │
          └──────────┬───────────────────────────────┘
                     │
            ┌────────┴────────┐
            │                 │
            ▼                 ▼
         ops.py          generate.py
         (status,         (changelog,
          coverage,        README)
          links)              │
            │                 ├── subprocess (git log)
            ├── DataRegistry  ├── config.loader
            └── audit_helpers └── GeneratedFile model

          docs_ops.py — backward-compat shim
          docs_generate.py — backward-compat shim
```

### Dependency Rules

| Rule | Detail |
|------|--------|
| `ops.py` is nearly standalone | Only DataRegistry + audit_helpers |
| `ops.py` re-exports from `generate.py` | Backward compat at bottom |
| `generate.py` imports lazily | config.loader, stack_loader, detection — inside function |
| No cross-service imports | Fully self-contained domain |
| Both return dicts | Never raise across the public API boundary |

---

## File Map

```
docs_svc/
├── __init__.py        7 lines   — public API re-exports
├── ops.py           403 lines   — status, coverage, links
├── generate.py      290 lines   — changelog, README generation
└── README.md                    — this file
```

---

## Per-File Documentation

### `ops.py` — Documentation Analysis (403 lines)

**Constants:**

| Constant | Contents |
|----------|---------|
| `_DOC_EXTENSIONS` | `{.md, .rst, .txt, .adoc, .asciidoc, .textile}` |
| `_DOC_DIRS` | `{docs, doc, documentation, wiki}` |
| `_SKIP_DIRS` | 17 directories excluded from scanning |
| `_LINK_PATTERN` | Regex: `\[([^\]]*)\]\(([^)]+)\)` |
| `_HEADING_ANCHOR_PATTERN` | Regex: `^#{1,6}\s+(.+)$` |

**Private helpers:**

| Function | Parameters | What It Does |
|----------|-----------|-------------|
| `_find_readme(root)` | `Path` | Case-insensitive README search (5 names) |
| `_extract_headings(path)` | `Path` | Regex-extract markdown headings → `[{level, text}]` |
| `_detect_api_specs(root)` | `Path` | Match DataRegistry patterns against disk |
| `_heading_to_anchor(text)` | `str` | GitHub-style anchor conversion |
| `_collect_md_files(root)` | `Path` | rglob `*.md`, skip dirs, cap at 100 |
| `_api_spec_files()` | — | Load API spec patterns from DataRegistry |

**Public API:**

| Function | Parameters | What It Does |
|----------|-----------|-------------|
| `docs_status(root)` | `Path` | Comprehensive documentation inventory |
| `docs_coverage(root)` | `Path` | Per-module documentation coverage ratio |
| `check_links(root, *, file_path)` | `Path, str|None` | Broken internal link detection |

### `generate.py` — Documentation Generation (290 lines)

**Private helpers:**

| Function | Parameters | What It Does |
|----------|-----------|-------------|
| `_commit_icon(subject)` | `str` | Map conventional commit prefix → emoji |

**Public API:**

| Function | Parameters | What It Does |
|----------|-----------|-------------|
| `generate_changelog(root, *, max_commits, since)` | `Path, int, str|None` | Changelog from git history |
| `generate_readme(root)` | `Path` | Stack-aware README template |

---

## Key Data Shapes

### docs_status response

```python
{
    "readme": {
        "exists": True,
        "path": "README.md",
        "size": 4523,
        "lines": 142,
        "headings": [
            {"level": 1, "text": "My Project"},
            {"level": 2, "text": "Getting Started"},
            {"level": 2, "text": "API Reference"},
            {"level": 3, "text": "Authentication"},
        ],
    },
    "doc_dirs": [
        {"name": "docs", "file_count": 15, "doc_count": 12, "total_size": 45230},
    ],
    "root_doc_files": 3,
    "api_specs": [
        {"file": "openapi.yaml", "type": "OpenAPI", "format": "yaml"},
    ],
    "changelog": {"exists": True, "path": "CHANGELOG.md"},
    "license": {"exists": True, "path": "LICENSE"},
    "contributing": {"exists": False, "path": None},
    "code_of_conduct": {"exists": False, "path": None},
    "security_policy": {"exists": False, "path": None},
    "missing_tools": [],
}
```

### docs_coverage response

```python
{
    "modules": [
        {
            "name": "core",
            "path": "src/core",
            "stack": "python",
            "has_readme": True,
            "doc_files": 5,
        },
        {
            "name": "web",
            "path": "src/ui/web",
            "stack": "python",
            "has_readme": False,
            "doc_files": 0,
        },
    ],
    "coverage": 0.5,      # 1 of 2 documented
    "total": 2,
    "documented": 1,
}
```

### check_links response

```python
# All links valid
{
    "files_checked": 12,
    "total_links": 87,
    "broken": [],
    "broken_count": 0,
    "ok": True,
}

# Broken links found
{
    "files_checked": 12,
    "total_links": 87,
    "broken": [
        {
            "file": "docs/guide.md",
            "line": 15,
            "link": "#nonexistent-section",
            "text": "Go to section",
            "reason": "Anchor not found in file",
        },
        {
            "file": "README.md",
            "line": 42,
            "link": "./docs/old-page.md",
            "text": "Old Page",
            "reason": "File not found: ./docs/old-page.md",
        },
    ],
    "broken_count": 2,
    "ok": False,
}
```

### generate_changelog response

```python
# Success
{
    "ok": True,
    "file": {
        "path": "CHANGELOG.md",
        "content": "# Changelog\n\n> Generated from git history...\n\n## 2026-02-28\n\n- ✨ feat: add login page (`abc1234` by Jane)\n...",
        "overwrite": True,
        "reason": "Generated changelog from 50 commits",
    },
    "commits": 50,
}

# Failure
{"error": "Git unavailable: FileNotFoundError"}
```

### generate_readme response

```python
{
    "ok": True,
    "file": {
        "path": "README.md",
        "content": "# my-project\n\n> TODO: Add a description...\n\n## Getting Started\n...",
        "overwrite": False,     # Never overwrites existing README
        "reason": "Generated README template from project metadata",
    },
}
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| **Routes** | `routes/docs/status.py` | `docs_status`, `docs_coverage`, `check_links` |
| **Routes** | `routes/docs/generate.py` | `generate_changelog`, `generate_readme` |
| **CLI** | `cli/docs/__init__.py` | Full API |
| **Audit** | `audit/l2_risk.py` | `docs_status`, `docs_coverage` |
| **Shims** | `docs_ops.py` | Backward-compat re-export of `ops.py` |
| **Shims** | `docs_generate.py` | Backward-compat re-export of `generate.py` |

---

## Dependency Graph

```
ops.py                              ← nearly standalone
   │
   ├── DataRegistry.api_spec_files  ← API spec patterns
   ├── audit_helpers.make_auditor   ← (imported but unused in current code)
   ├── tool_requirements            ← check_required_tools(["git"])
   └── generate.py (re-export)      ← backward compat at bottom

generate.py                         ← standalone, lazy imports
   │
   ├── subprocess (git log)         ← changelog generation
   ├── config.loader                ← project metadata (lazy)
   ├── config.stack_loader          ← stack discovery (lazy)
   ├── services.detection           ← module detection (lazy)
   └── models.template.GeneratedFile ← output model (lazy)
```

Key: All imports in `generate.py` are inside function bodies —
the module can be imported without triggering any service imports.

---

## Documentation File Extensions

Files counted as documentation:

```
.md          .rst         .txt
.adoc        .asciidoc    .textile
```

---

## Documentation Directories

Directories scanned as documentation roots:

```
docs/        doc/         documentation/        wiki/
```

---

## Conventional Commit Icons

| Prefix | Icon | Meaning |
|--------|------|---------|
| `feat` | ✨ | New feature |
| `fix` | 🐛 | Bug fix |
| `docs` | 📝 | Documentation |
| `style` | 💅 | Formatting |
| `refactor` | ♻️ | Refactoring |
| `test` | 🧪 | Tests |
| `chore` | 🔧 | Maintenance |
| `ci` | ⚙️ | CI configuration |
| `perf` | ⚡ | Performance |
| `build` | 📦 | Build system |
| `merge` | 🔀 | Merge commit |
| *(other)* | 📋 | General |

---

## Link Validation Rules

| Link Type | Check Performed |
|-----------|----------------|
| `#anchor` | Heading exists in same file |
| `./file.md` | File exists on disk |
| `../dir/file.md` | File exists relative to current |
| `http://...` | Skipped (no network requests) |
| `https://...` | Skipped (no network requests) |
| `mailto:...` | Skipped |
| `data:...` | Skipped (data URIs) |

### Anchor Conversion Rules

Headings are converted to GitHub-style anchors:

```
Input                     Output
─────                     ──────
"My Heading!"          →  "my-heading"
"API v2.0"             →  "api-v20"
"Getting Started"      →  "getting-started"
"#[test] macros"       →  "test-macros"
```

Rules: lowercase → strip non-alphanumeric (keep hyphens) →
replace spaces with hyphens → strip leading/trailing hyphens.

---

## Key Documentation Files

The `docs_status` function checks for 5 categories of
project-level documentation files:

| Category | Files Checked |
|----------|--------------|
| **Changelog** | `CHANGELOG.md`, `CHANGELOG`, `CHANGES.md`, `HISTORY.md` |
| **License** | `LICENSE`, `LICENSE.md`, `LICENSE.txt`, `LICENCE` |
| **Contributing** | `CONTRIBUTING.md`, `CONTRIBUTING`, `CONTRIBUTE.md` |
| **Code of Conduct** | `CODE_OF_CONDUCT.md` |
| **Security Policy** | `SECURITY.md` |

Each returns `{exists: bool, path: str|None}`.

---

## API Spec Patterns

Loaded from DataRegistry via `_api_spec_files()`:

| Format | File Patterns |
|--------|--------------|
| **OpenAPI 3.x** | `openapi.yaml`, `openapi.json`, `openapi.yml` |
| **Swagger 2.0** | `swagger.yaml`, `swagger.json`, `swagger.yml` |
| **AsyncAPI** | `asyncapi.yaml`, `asyncapi.json` |
| **GraphQL** | `schema.graphql`, `*.graphql` |
| **Protobuf** | `*.proto` |

Glob patterns (`*.graphql`, `*.proto`) use `rglob` and skip
`_SKIP_DIRS` to avoid matching files inside `node_modules/`
or `build/` directories.

---

## README Search Order

The `_find_readme` function checks these names in order:

```
1. README.md       (most common)
2. README.rst      (reStructuredText)
3. README.txt      (plain text)
4. README          (no extension)
5. readme.md       (lowercase)
```

First match wins. The search is **not recursive** — only the
target directory root is checked.

---

## Skipped Directories

Directories excluded from documentation scanning and link checking:

```
.git          .venv         venv          node_modules
__pycache__   .mypy_cache   .ruff_cache   .pytest_cache
.tox          dist          build         .eggs
.terraform    .pages        htmlcov       .backup
state
```

Note: `.pages` appears twice in the source set (frozen set
deduplicates it). These directories are excluded from all
scanning operations: doc file counting, link validation,
and coverage analysis.

---

## Changelog Git Format

The git log format string used to extract commit data:

```
--format=%H|%ai|%s|%an
```

| Field | Description | Example |
|-------|-------------|---------|
| `%H` | Full commit hash | `abc123def456789...` |
| `%ai` | Author date (ISO) | `2026-01-15 10:30:00 -0500` |
| `%s` | Subject line | `feat: add login page` |
| `%an` | Author name | `Jane Developer` |

The pipe `|` delimiter was chosen because it doesn't appear in
typical commit subjects (unlike `:` or `,`). The format is split
with `split("|", 3)` to handle subjects containing pipes.

---

## Generated File Model

Both `generate_changelog` and `generate_readme` return data
wrapped in the `GeneratedFile` model:

```python
class GeneratedFile:
    path: str           # e.g. "CHANGELOG.md"
    content: str        # Full file content
    reason: str         # Why the file was generated
    overwrite: bool     # True for changelog, False for README
```

| Function | path | overwrite | Why |
|----------|------|-----------|-----|
| `generate_changelog` | `CHANGELOG.md` | `True` | Always regenerated from latest commits |
| `generate_readme` | `README.md` | `False` | User-customized content takes precedence |

---

## Coverage Scoring

The `docs_coverage` function computes a simple ratio:

```
coverage = documented_modules / total_modules
```

A module is considered "documented" if `_find_readme(mod_path)`
returns a file. The ratio ranges from 0.0 (no documentation)
to 1.0 (all modules documented).

This metric is consumed by the audit system's L2 risk layer
to flag under-documented projects as a documentation risk.

---

## Markdown File Cap

The `_collect_md_files` function caps results at **100 files**:

```python
return files[:100]  # Cap at 100
```

For link validation across very large monorepos, this prevents
excessive scanning time. The cap is hardcoded (not configurable)
and files are returned in rglob order (depth-first by filesystem).

---

## Error Handling

| Function | Can Fail? | Error Shape |
|----------|----------|-------------|
| `docs_status` | No | Always returns a result dict |
| `docs_coverage` | No | Falls back to single-module on detection failure |
| `check_links` | No | Always returns `{ok, broken, ...}` |
| `generate_changelog` | Yes | `{"error": "Git unavailable: ..."}` |
| `generate_readme` | No | Falls back to directory name if config fails |

The changelog generator can fail in two ways:
- `FileNotFoundError` — git binary not found
- `subprocess.TimeoutExpired` — git log exceeds 15s timeout
- Non-zero exit code — git log command fails (e.g., not a repo)

All other functions are designed to never raise exceptions
across the public API boundary.

---

## Backward Compatibility

Two shim files remain at the services root:

```python
# docs_ops.py
from src.core.services.docs_svc.ops import *  # noqa

# docs_generate.py
from src.core.services.docs_svc.generate import *  # noqa
```

These shims allow old import paths to continue working
during the migration to the package structure.

---

## Advanced Feature Showcase

### 1. GitHub-Style Anchor Conversion — Three-Step Transform

Heading text is converted to anchors matching GitHub's algorithm:

```python
# ops.py — _heading_to_anchor (lines 372-377)

def _heading_to_anchor(text: str) -> str:
    anchor = text.lower()
    anchor = re.sub(r"[^\w\s-]", "", anchor)   # Strip non-alnum (keep hyphens)
    anchor = re.sub(r"\s+", "-", anchor)        # Spaces → hyphens
    return anchor.strip("-")                     # Trim leading/trailing hyphens
```

Examples of the transform:
- `"My Heading!"` → `"my-heading"` (strip `!`)
- `"API v2.0"` → `"api-v20"` (strip `.`)
- `"#[test] macros"` → `"test-macros"` (strip `#[]`)

This is used by `check_links` to validate `#anchor` links — the regex
strips punctuation that GitHub removes, ensuring the anchor index
matches what users see in rendered markdown.

### 2. Conventional Commit Icon Mapping — Prefix-Based Categorization

Commit messages are categorized by their conventional prefix:

```python
# generate.py — _commit_icon (lines 101-126)

def _commit_icon(subject: str) -> str:
    lower = subject.lower()
    if lower.startswith("feat"):     return "✨"
    elif lower.startswith("fix"):    return "🐛"
    elif lower.startswith("docs"):   return "📝"
    elif lower.startswith("style"):  return "💅"
    elif lower.startswith("refactor"): return "♻️"
    elif lower.startswith("test"):   return "🧪"
    elif lower.startswith("chore"):  return "🔧"
    elif lower.startswith("ci"):     return "⚙️"
    elif lower.startswith("perf"):   return "⚡"
    elif lower.startswith("build"):  return "📦"
    elif "merge" in lower:           return "🔀"  # substring, not prefix
    return "📋"                                    # default: general
```

10 prefix matches + 1 substring match (`merge` — because merge commits
often have varying formats like "Merge pull request..." or "merge
branch..."). The 12th fallback emoji (`📋`) catches everything else.

### 3. Stack-Aware Prerequisite Generation — Dynamic README Sections

The README generator adapts sections based on detected project stacks:

```python
# generate.py — generate_readme (lines 206-232)

# Prerequisites — only show relevant runtimes
if any("python" in s for s in stacks):
    lines.append("- Python 3.12+")
if any("node" in s or "typescript" in s for s in stacks):
    lines.append("- Node.js 18+")
if any("go" in s for s in stacks):
    lines.append("- Go 1.21+")
if any("rust" in s for s in stacks):
    lines.append("- Rust (stable)")

# Installation — stack-specific commands
if any("python" in s for s in stacks):
    lines.extend([
        "python -m venv .venv",
        "source .venv/bin/activate",
        "pip install -e '.[dev]'",
    ])
elif any("node" in s or "typescript" in s for s in stacks):
    lines.append("npm install")
```

A Python project gets `pip install` instructions. A Node.js project
gets `npm install`. A polyglot project gets both prerequisites listed.
If stack detection fails entirely, the sections are still present but
empty — the user fills in their own commands.

### 4. Multi-Signal API Spec Detection — Glob + Exact Name Matching

API spec files use two different matching strategies:

```python
# ops.py — _detect_api_specs (lines 156-185)

for filename, spec_type, spec_format in _api_spec_files():
    if "*" in filename:
        # Glob pattern → rglob, skip _SKIP_DIRS
        for match in project_root.rglob(filename):
            skip = False
            for part in match.relative_to(project_root).parts:
                if part in _SKIP_DIRS:
                    skip = True
                    break
            if not skip:
                found.append({"file": rel, "type": spec_type, ...})
    else:
        # Exact name → direct existence check
        path = project_root / filename
        if path.is_file():
            found.append({"file": filename, "type": spec_type, ...})
```

Exact names (`openapi.yaml`, `swagger.json`) get fast O(1) existence
checks. Glob patterns (`*.graphql`, `*.proto`) use rglob but filter
through `_SKIP_DIRS` to avoid matching files in `node_modules/` or
`build/`. The patterns are loaded from DataRegistry — new spec
formats can be added without touching Python code.

### 5. Three-Pass Link Validation — Anchors, Files, and Skips

Each markdown file undergoes three validation passes:

```python
# ops.py — check_links (lines 303-361)

for md_file in files:
    # Pass 1: Build anchor index from all headings
    defined_anchors = set()
    for heading_match in _HEADING_ANCHOR_PATTERN.finditer(content):
        text = heading_match.group(1).strip()
        anchor = _heading_to_anchor(text)
        defined_anchors.add(anchor)

    for line_num, line in enumerate(content.splitlines(), 1):
        for match in _LINK_PATTERN.finditer(line):
            link_target = match.group(2)

            # Pass 2: Skip external/data URIs
            if link_target.startswith(("http://", "https://", "mailto:", "ftp://")):
                continue
            if link_target.startswith("data:"):
                continue

            # Pass 3a: Anchor-only (#heading)
            if link_target.startswith("#"):
                if link_target[1:] not in defined_anchors:
                    broken.append({...})

            # Pass 3b: Relative file (./path or ../path)
            file_part = link_target.split("#")[0]
            target_path = md_file.parent / file_part
            if not target_path.exists():
                broken.append({...})
```

The anchor index is built first (pass 1) so all anchor checks are
O(1) lookups. External links are skipped (pass 2) — no network
requests. File links are resolved relative to the current file's
parent directory (pass 3b), matching how browsers resolve paths.

### 6. Module Detection Fallback — Graceful Degradation on Config Failure

Coverage analysis wraps module detection in a try/except with a
single-module fallback:

```python
# ops.py — docs_coverage (lines 193-264)

modules: list[dict] = []

try:
    # Full detection pipeline
    project = load_project(project_root / "project.yml")
    stacks = discover_stacks(project_root / "stacks")
    detection = detect_modules(project, project_root, stacks)

    for module in detection.modules:
        mod_path = project_root / module.path if module.path != "." else project_root
        has_readme = _find_readme(mod_path) is not None
        # ... count doc files
        modules.append({...})

except Exception:
    # Fallback: treat project root as single module
    has_readme = _find_readme(project_root) is not None
    modules.append({
        "name": project_root.name,
        "path": ".",
        "stack": None,
        "has_readme": has_readme,
        "doc_files": 0,
    })

# Coverage is always computed, even on fallback
documented = sum(1 for m in modules if m["has_readme"])
coverage = round(documented / len(modules), 2)
```

If `project.yml` doesn't exist, or stacks aren't configured, the
function still returns a valid result with a single module
representing the project root. This ensures the audit system always
gets a coverage score.

### 7. Date-Grouped Changelog Formatting — Git History to Markdown

Commits are grouped by date with section headers:

```python
# generate.py — generate_changelog (lines 53-85)

current_date = ""
for raw in result.stdout.strip().splitlines():
    parts = raw.split("|", 3)       # maxsplit=3 handles | in subjects
    commit_hash, date_str, subject, author = parts
    short_hash = commit_hash[:7]
    date_only = date_str.split(" ")[0]   # "2026-01-15 10:30:00 -0500" → "2026-01-15"

    if date_only != current_date:
        current_date = date_only
        lines.append(f"## {date_only}")   # New date section
        lines.append("")

    icon = _commit_icon(subject)
    lines.append(f"- {icon} {subject} (`{short_hash}` by {author})")
```

The format string `%H|%ai|%s|%an` uses pipe delimiters because they
rarely appear in commit subjects (unlike `:` or `,`). The `split("|", 3)`
maxsplit ensures subjects containing pipes don't break parsing. Each
date transition creates a new `## YYYY-MM-DD` heading, producing a
nested changelog structure.

---

### Feature Coverage Summary

| Feature | Where | Complexity |
|---------|-------|-----------|
| GitHub-style anchor conversion | `ops.py` `_heading_to_anchor` | Three regex transforms + strip |
| Conventional commit icon mapping | `generate.py` `_commit_icon` | 10 prefix + 1 substring + fallback |
| Stack-aware README sections | `generate.py` `generate_readme` | Dynamic prerequisites + install |
| Dual-strategy API spec detection | `ops.py` `_detect_api_specs` | Exact name O(1) + glob with skip |
| Three-pass link validation | `ops.py` `check_links` | Anchor index → skip externals → validate |
| Module detection fallback | `ops.py` `docs_coverage` | Full pipeline → single-module fallback |
| Date-grouped changelog | `generate.py` `generate_changelog` | Pipe-delimited parse + date sections |

---

## Design Decisions

### Why offline link checking only?

External link checking requires network requests and can be slow
and unreliable (rate limits, DNS failures, transient 503s). The
service checks only internal links (relative paths and anchors)
which can be validated instantly from the filesystem. External
link checking is delegated to CI tools like `markdown-link-check`
or `lychee` which are purpose-built for that task.

### Why stack-aware README generation?

The generated README includes prerequisites, installation commands,
and development commands that match the detected stacks. A Python
project gets `pip install -e '.[dev]'` while a Node.js project gets
`npm install`. This produces immediately useful documentation
instead of generic placeholders that every developer ignores.

### Why DataRegistry for API spec patterns?

API specification file patterns change over time (new spec formats
emerge — AsyncAPI, Protobuf, GraphQL). Storing patterns in
DataRegistry allows updates without modifying Python code. The
`_api_spec_files()` function loads patterns lazily from the
registry, so new formats can be added by editing the data catalog.

### Why conventional commit parsing?

Conventional commits (`feat:`, `fix:`, `docs:`) are the de facto
standard for structured commit messages. Parsing them allows
automatic categorization and icon assignment, producing a
structured changelog that groups changes by type rather than
presenting a flat chronological list.

### Why overwrite: True for changelog but False for README?

Changelogs are generated from git history — always reproducible
and always current. Overwriting is safe because the content isn't
manually edited. READMEs contain user-customized prose, badges,
screenshots, and context that would be destroyed by overwriting.
The `overwrite: False` flag prevents accidental loss.

### Why 100-file cap for link checking?

Large monorepos can contain thousands of markdown files (e.g.,
generated docs, changelogs in every package). Checking all links
in all files would take minutes and produce too much noise.
The 100-file cap keeps the operation fast (< 2 seconds) while
still covering the most important files (rglob returns files
in depth-first order, hitting root-level docs first).

### Why pipe delimiter in git log format?

The `|` character was chosen because it almost never appears in
commit subject lines (unlike `:` which is part of conventional
commit syntax, or `,` which appears in prose). The parser uses
`split("|", 3)` with a maxsplit argument to handle the edge case
where a subject line contains a pipe.
