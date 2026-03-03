# Docs Routes — Documentation Inventory, Coverage, Link Validation & Generation API

> **3 files · 88 lines · 5 endpoints · Blueprint: `docs_bp` · Prefix: `/api`**
>
> Thin HTTP wrappers over `src.core.services.docs_svc` (ops.py: 403 lines,
> generate.py: 290 lines). These routes provide documentation health
> analysis: project-wide inventory (README, API specs, CHANGELOG, LICENSE,
> CONTRIBUTING, CODE_OF_CONDUCT, SECURITY.md), per-module documentation
> coverage with percentage scoring, internal link validation across all
> markdown files (anchor checking, relative path resolution, GitHub-style
> anchor conversion), and documentation generation (CHANGELOG from git
> history with conventional commit icons, README template from project
> metadata with stack-aware prerequisites and install commands).

---

## How It Works

### Request Flow

```
Frontend
│
├── devops/_docs.html ──────────── Documentation dashboard card
│   ├── GET  /api/docs/status     (cached detection)
│   ├── GET  /api/docs/coverage   (per-module analysis)
│   └── GET  /api/docs/links      (link validation)
│
└── (wizard / setup UI)
    ├── POST /api/docs/generate/changelog  (from git history)
    └── POST /api/docs/generate/readme     (template from metadata)
     │
     ▼
routes/docs/                        ← HTTP layer (this package)
├── __init__.py  — blueprint definition
├── status.py    — status, coverage, links
└── generate.py  — changelog, readme
     │
     ▼
core/services/docs_svc/            ← Business logic
├── ops.py (403 lines)
│   ├── docs_status()             — comprehensive inventory
│   ├── _find_readme()            — case-insensitive README finder
│   ├── _extract_headings()       — markdown heading parser
│   ├── _detect_api_specs()       — API spec file detection
│   ├── docs_coverage()           — per-module coverage analysis
│   ├── check_links()             — internal link validation
│   ├── _heading_to_anchor()      — GitHub-style anchor conversion
│   └── _collect_md_files()       — markdown file collector (cap: 100)
│
└── generate.py (290 lines)
    ├── generate_changelog()      — git log → CHANGELOG.md
    ├── _commit_icon()            — conventional commit emoji mapping
    └── generate_readme()         — project metadata → README.md template
```

### Documentation Inventory Pipeline (Offline)

```
GET /api/docs/status?bust=1
     │
     ▼
devops_cache.get_cached(root, "docs", ...)
     │
     ├── Cache HIT → return cached snapshot
     └── Cache MISS → docs_ops.docs_status(root)
         │
         ├── 1. Find README (case-insensitive scan):
         │   README.md → README.rst → README.txt → README → readme.md
         │   If found: read size, line count, extract headings (top 10)
         │
         ├── 2. Scan documentation directories:
         │   For each of: docs/, doc/, documentation/, wiki/
         │   ├── Count all files
         │   ├── Count doc files (.md, .rst, .txt, .adoc, .asciidoc, .textile)
         │   └── Sum total size
         │
         ├── 3. Count root-level doc files:
         │   *.md, *.rst, etc. at project root
         │
         ├── 4. Detect API specification files:
         │   _detect_api_specs(root)
         │   ├── Check exact filenames: openapi.yml, swagger.json, etc.
         │   ├── Check glob patterns: *.proto, *.graphql, etc.
         │   └── Skip _SKIP_DIRS: .git, .venv, node_modules, etc.
         │
         ├── 5. Check key documentation files:
         │   ├── changelog: CHANGELOG.md, CHANGELOG, CHANGES.md, HISTORY.md
         │   ├── license:   LICENSE, LICENSE.md, LICENSE.txt, LICENCE
         │   ├── contributing: CONTRIBUTING.md, CONTRIBUTING, CONTRIBUTE.md
         │   ├── code_of_conduct: CODE_OF_CONDUCT.md
         │   └── security_policy: SECURITY.md
         │
         └── 6. Check required tools:
             check_required_tools(["git"])
```

### Documentation Coverage Pipeline

```
GET /api/docs/coverage
     │
     ▼
docs_ops.docs_coverage(root)
     │
     ├── Detect project modules:
     │   load_project() → discover_stacks() → detect_modules()
     │
     ├── For each detected module:
     │   ├── Check: has README? (_find_readme(module_path))
     │   ├── Count doc files in module tree (recursive, skip _SKIP_DIRS)
     │   └── Record: { name, path, stack, has_readme, doc_files }
     │
     ├── Calculate coverage:
     │   documented = count(modules where has_readme == true)
     │   total = count(all modules)
     │   coverage = documented / total  (0.0 to 1.0, rounded to 2dp)
     │
     └── Fallback (if module detection fails):
         → check root only, return single module entry
```

### Link Validation Pipeline

```
GET /api/docs/links?file=docs/guide.md
     │
     ▼
docs_ops.check_links(root, file_path="docs/guide.md")
     │
     ├── Collect markdown files:
     │   ├── If ?file= specified → check only that file
     │   └── If no file → _collect_md_files(root) (cap: 100 files)
     │
     ├── For each markdown file:
     │   ├── Build defined anchors set:
     │   │   Scan headings → _heading_to_anchor(heading_text)
     │   │   "## Getting Started" → "getting-started"
     │   │
     │   ├── Find all links: regex [text](target)
     │   │
     │   └── For each link:
     │       ├── Skip external: http://, https://, mailto:, ftp://
     │       ├── Skip data URIs: data:
     │       │
     │       ├── Anchor-only (#heading):
     │       │   Check if anchor exists in defined_anchors set
     │       │   → if not found: broken (reason: "Anchor not found in file")
     │       │
     │       └── Relative file link (path/to/file.md#section):
     │           Split at # → resolve file part relative to current dir
     │           → if target doesn't exist: broken (reason: "File not found: ...")
     │
     └── Return: { files_checked, total_links, broken[], broken_count, ok }
```

### Changelog Generation Pipeline

```
POST /api/docs/generate/changelog  { commits: 50, since: "2026-01-01" }
     │
     ├── @run_tracked("generate", "generate:changelog")
     │
     ▼
docs_ops.generate_changelog(root, max_commits=50, since="2026-01-01")
     │
     ├── Run git log:
     │   git log --max-count=50 --since=2026-01-01 --format=%H|%ai|%s|%an
     │   timeout=15s
     │
     ├── Parse each line:
     │   commit_hash | date_str | subject | author
     │   → short_hash (first 7 chars), date_only (YYYY-MM-DD)
     │
     ├── Group by date (## YYYY-MM-DD headers)
     │
     ├── Categorize with conventional commit icons:
     │   feat    → ✨    fix      → 🐛    docs     → 📝
     │   style   → 💅    refactor → ♻️     test     → 🧪
     │   chore   → 🔧    ci       → ⚙️     perf     → ⚡
     │   build   → 📦    merge    → 🔀    (other)  → 📋
     │
     ├── Format: - ✨ feat: add login flow (`abc1234` by author)
     │
     └── Return as GeneratedFile:
         { ok: true, file: { path, content, reason, overwrite: true }, commits: N }
```

### README Generation Pipeline

```
POST /api/docs/generate/readme
     │
     ├── @run_tracked("generate", "generate:readme")
     │
     ▼
docs_ops.generate_readme(root)
     │
     ├── Load project metadata:
     │   load_project() → name, stacks, modules
     │
     ├── Build template sections:
     │   ├── # Project Name
     │   ├── Badge placeholders (CI badge template)
     │   ├── Table of Contents (6 sections)
     │   ├── ## Overview (TODO placeholder)
     │   │
     │   ├── ## Getting Started
     │   │   ├── ### Prerequisites (stack-aware):
     │   │   │   python → "Python 3.12+"
     │   │   │   node   → "Node.js 18+"
     │   │   │   go     → "Go 1.21+"
     │   │   │   rust   → "Rust (stable)"
     │   │   │
     │   │   └── ### Installation (stack-aware):
     │   │       python → venv + pip install
     │   │       node   → npm install
     │   │
     │   ├── ## Project Structure (if modules detected):
     │   │   | Module | Path | Stack |
     │   │
     │   ├── ## Development (stack-aware test/lint commands)
     │   ├── ## Contributing (TODO placeholder)
     │   └── ## License (TODO placeholder)
     │
     └── Return as GeneratedFile:
         { ok: true, file: { path, content, reason, overwrite: false } }
```

---

## File Map

```
routes/docs/
├── __init__.py     18 lines — blueprint definition + sub-module imports
├── status.py       37 lines — 3 endpoints: status, coverage, links
├── generate.py     33 lines — 2 endpoints: changelog, readme
└── README.md                — this file
```

Core business logic resides in:
- `core/services/docs_svc/ops.py` (403 lines) — status, coverage, link checking
- `core/services/docs_svc/generate.py` (290 lines) — changelog, README generation

---

## Per-File Documentation

### `__init__.py` — Blueprint Definition (18 lines)

```python
docs_bp = Blueprint("docs", __name__)

from . import status, generate  # register routes
```

### `status.py` — Status, Coverage, Links (37 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `docs_status()` | GET | `/docs/status` | Documentation inventory (**cached**) |
| `docs_coverage()` | GET | `/docs/coverage` | Per-module documentation coverage |
| `docs_links()` | GET | `/docs/links` | Internal link validation |

**Status with caching:**

```python
from src.core.services.devops.cache import get_cached

root = _project_root()
force = request.args.get("bust", "") == "1"
return jsonify(get_cached(
    root, "docs",
    lambda: docs_ops.docs_status(root),
    force=force,
))
```

**Coverage — direct delegation:**

```python
return jsonify(docs_ops.docs_coverage(_project_root()))
```

No caching for coverage because module detection is fast and the
result should reflect the current state (new READMEs are added
frequently during documentation work).

**Links — optional file parameter:**

```python
file_path = request.args.get("file")
return jsonify(docs_ops.check_links(_project_root(), file_path=file_path))
```

If `?file=docs/guide.md` is provided, only that file is checked.
Without the parameter, all markdown files in the project are
scanned (capped at 100 files to prevent excessive I/O).

### `generate.py` — Changelog & README Generation (33 lines)

| Function | Method | Route | Tracked As | What It Does |
|----------|--------|-------|-----------|-------------|
| `docs_generate_changelog()` | POST | `/docs/generate/changelog` | `generate:changelog` | CHANGELOG from git history |
| `docs_generate_readme()` | POST | `/docs/generate/readme` | `generate:readme` | README template from metadata |

**Changelog — configurable history depth:**

```python
data = request.get_json(silent=True) or {}
result = docs_ops.generate_changelog(
    _project_root(),
    max_commits=data.get("commits", 50),
    since=data.get("since"),
)
```

Two parameters control the changelog scope:
- `commits` (default: 50) — maximum number of commits to include
- `since` (optional) — ISO date string to start from

**README — zero configuration:**

```python
return jsonify(docs_ops.generate_readme(_project_root()))
```

No parameters needed. The generator introspects the project
(project.yml, stacks, modules) and produces a stack-aware template.

---

## Dependency Graph

```
__init__.py
└── Imports: status, generate

status.py
├── docs_svc.ops          ← docs_status, docs_coverage, check_links (eager)
├── devops.cache          ← get_cached (lazy, inside handler)
└── helpers               ← project_root

generate.py
├── docs_svc.ops          ← generate_changelog, generate_readme (eager)
│   └── (re-exported from docs_svc.generate)
├── run_tracker           ← @run_tracked decorator
└── helpers               ← project_root
```

**Core service internals:**

```
docs_svc/ops.py
├── _DOC_EXTENSIONS      ← .md, .rst, .txt, .adoc, .asciidoc, .textile
├── _DOC_DIRS            ← docs, doc, documentation, wiki
├── _SKIP_DIRS           ← .git, .venv, node_modules, etc.
├── _api_spec_files()    ← DataRegistry patterns (lazy load)
├── docs_status()        ← inventory (lines 51-126)
├── _find_readme()       ← case-insensitive finder (lines 129-135)
├── _extract_headings()  ← markdown heading parser (lines 138-153)
├── _detect_api_specs()  ← API spec scanner (lines 156-185)
├── docs_coverage()      ← per-module coverage (lines 193-264)
├── check_links()        ← link validator (lines 276-369)
├── _heading_to_anchor() ← GitHub-style anchor (lines 372-377)
├── _collect_md_files()  ← markdown collector, cap 100 (lines 380-391)
└── Re-exports: generate_changelog, generate_readme

docs_svc/generate.py
├── generate_changelog() ← git log → CHANGELOG.md (lines 18-98)
├── _commit_icon()       ← 12 conventional commit types (lines 101-126)
└── generate_readme()    ← metadata → README.md (lines 134-289)
    ├── config.loader    ← load_project() (lazy)
    ├── stack_loader     ← discover_stacks() (lazy)
    └── detection        ← detect_modules() (lazy)
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Server | `ui/web/server.py` | Imports `docs_bp`, registers at `/api` prefix |
| Dashboard | `scripts/devops/_docs.html` | `GET /docs/status` (docs card) |
| Dashboard | `scripts/devops/_docs.html` | `GET /docs/coverage` (coverage bar) |
| Dashboard | `scripts/devops/_docs.html` | `GET /docs/links` (link health) |
| Cache | `devops/cache` compute registry | `"docs"` key → `docs_ops.docs_status(root)` |

---

## Service Delegation Map

```
Route Handler               →   Core Service Function
──────────────────────────────────────────────────────────────────
docs_status()               →   cache.get_cached("docs", ...)
                                  └→ docs_ops.docs_status(root)
                                       ├→ _find_readme(root)
                                       ├→ _extract_headings(readme_path)
                                       ├→ scan doc dirs (docs/, doc/, ...)
                                       ├→ _detect_api_specs(root)
                                       ├→ check key files (CHANGELOG, LICENSE, ...)
                                       └→ check_required_tools(["git"])

docs_coverage()             →   docs_ops.docs_coverage(root)
                                  ├→ load_project() + detect_modules()
                                  ├→ _find_readme() per module
                                  ├→ count doc files per module tree
                                  └→ calculate coverage percentage

docs_links()                →   docs_ops.check_links(root, file_path)
                                  ├→ _collect_md_files(root) or single file
                                  ├→ build anchor set per file
                                  ├→ regex scan for [text](target) links
                                  ├→ validate anchor-only links
                                  └→ validate relative file links

docs_generate_changelog()   →   docs_ops.generate_changelog(root, max_commits, since)
                                  ├→ subprocess: git log --format=...
                                  ├→ parse: hash|date|subject|author
                                  ├→ _commit_icon(subject) mapping
                                  └→ GeneratedFile(path="CHANGELOG.md", overwrite=True)

docs_generate_readme()      →   docs_ops.generate_readme(root)
                                  ├→ load_project() + detect_modules()
                                  ├→ build stack-aware template sections
                                  └→ GeneratedFile(path="README.md", overwrite=False)
```

---

## Data Shapes

### `GET /api/docs/status` response

```json
{
    "readme": {
        "exists": true,
        "path": "README.md",
        "size": 4523,
        "lines": 142,
        "headings": [
            { "level": 1, "text": "DevOps Control Plane" },
            { "level": 2, "text": "Getting Started" },
            { "level": 2, "text": "Architecture" },
            { "level": 2, "text": "Development" }
        ]
    },
    "doc_dirs": [
        {
            "name": "docs",
            "file_count": 24,
            "doc_count": 18,
            "total_size": 125430
        }
    ],
    "root_doc_files": 5,
    "api_specs": [
        { "file": "openapi.yml", "type": "openapi", "format": "yaml" }
    ],
    "changelog": { "exists": true, "path": "CHANGELOG.md" },
    "license": { "exists": true, "path": "LICENSE" },
    "contributing": { "exists": true, "path": "CONTRIBUTING.md" },
    "code_of_conduct": { "exists": false, "path": null },
    "security_policy": { "exists": true, "path": "SECURITY.md" },
    "missing_tools": {
        "git": { "found": true, "path": "/usr/bin/git" }
    }
}
```

### `GET /api/docs/status` response (minimal project)

```json
{
    "readme": { "exists": false },
    "doc_dirs": [],
    "root_doc_files": 0,
    "api_specs": [],
    "changelog": { "exists": false, "path": null },
    "license": { "exists": false, "path": null },
    "contributing": { "exists": false, "path": null },
    "code_of_conduct": { "exists": false, "path": null },
    "security_policy": { "exists": false, "path": null },
    "missing_tools": {
        "git": { "found": false }
    }
}
```

### `GET /api/docs/coverage` response

```json
{
    "modules": [
        {
            "name": "web",
            "path": "src/ui/web",
            "stack": "python",
            "has_readme": true,
            "doc_files": 12
        },
        {
            "name": "cli",
            "path": "src/cli",
            "stack": "python",
            "has_readme": false,
            "doc_files": 2
        },
        {
            "name": "core",
            "path": "src/core",
            "stack": "python",
            "has_readme": true,
            "doc_files": 45
        }
    ],
    "coverage": 0.67,
    "total": 3,
    "documented": 2
}
```

### `GET /api/docs/links` response (clean)

```json
{
    "files_checked": 24,
    "total_links": 156,
    "broken": [],
    "broken_count": 0,
    "ok": true
}
```

### `GET /api/docs/links?file=docs/guide.md` response (with broken links)

```json
{
    "files_checked": 1,
    "total_links": 12,
    "broken": [
        {
            "file": "docs/guide.md",
            "line": 45,
            "link": "#gettting-started",
            "text": "Getting Started",
            "reason": "Anchor not found in file"
        },
        {
            "file": "docs/guide.md",
            "line": 78,
            "link": "../api/deprecated.md",
            "text": "API reference",
            "reason": "File not found: ../api/deprecated.md"
        }
    ],
    "broken_count": 2,
    "ok": false
}
```

### `POST /api/docs/generate/changelog` request + response

```json
// Request:
{ "commits": 30, "since": "2026-01-01" }

// Response:
{
    "ok": true,
    "file": {
        "path": "CHANGELOG.md",
        "content": "# Changelog\n\n> Generated from git history (30 most recent commits)\n\n## 2026-03-02\n\n- ✨ feat: add DNS record generation (`abc1234` by author)\n- 🐛 fix: resolve cache invalidation bug (`def5678` by author)\n\n## 2026-03-01\n\n- ♻️ refactor: extract docs generation module (`ghi9012` by author)\n",
        "reason": "Generated changelog from 30 commits",
        "overwrite": true
    },
    "commits": 30
}
```

### `POST /api/docs/generate/readme` response

```json
{
    "ok": true,
    "file": {
        "path": "README.md",
        "content": "# devops-control-plane\n\n> TODO: Add a description...\n\n## Table of Contents\n\n- [Overview](#overview)\n- [Getting Started](#getting-started)\n...\n\n### Prerequisites\n\n- Python 3.12+\n\n### Installation\n\n```bash\ngit clone <repo-url>\ncd devops-control-plane\npython -m venv .venv\nsource .venv/bin/activate\npip install -e '.[dev]'\n```\n\n## Project Structure\n\n| Module | Path | Stack |\n|--------|------|-------|\n| web | `src/ui/web` | python |\n...",
        "reason": "Generated README template from project metadata",
        "overwrite": false
    }
}
```

### `POST /api/docs/generate/changelog` response (git unavailable)

```json
{
    "error": "Git unavailable: [Errno 2] No such file or directory: 'git'"
}
```

---

## Advanced Feature Showcase

### 1. Conventional Commit Icon Mapping

The changelog generator maps 12 conventional commit prefixes to emojis:

```python
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
    elif "merge" in lower:           return "🔀"
    return "📋"  # fallback
```

### 2. GitHub-Style Anchor Conversion

Link validation converts headings to anchors using GitHub's algorithm:

```python
def _heading_to_anchor(text: str) -> str:
    anchor = text.lower()
    anchor = re.sub(r"[^\w\s-]", "", anchor)  # remove special chars
    anchor = re.sub(r"\s+", "-", anchor)       # spaces → hyphens
    return anchor.strip("-")

# "## Getting Started" → "getting-started"
# "## API Reference (v2)" → "api-reference-v2"
# "## What's New?" → "whats-new"
```

### 3. Two-Mode Link Validation

The link checker supports both project-wide and single-file modes:

```python
# Single file mode: fast, targeted
GET /api/docs/links?file=docs/guide.md
→ check_links(root, file_path="docs/guide.md")

# Project-wide mode: comprehensive, capped
GET /api/docs/links
→ check_links(root)
→ _collect_md_files(root)  # capped at 100 files
```

Single-file mode enables "check on save" UX patterns without
scanning the entire project.

### 4. Stack-Aware README Templates

The README generator introspects detected stacks and produces
language-appropriate sections:

```python
# Prerequisites adapt to detected stacks
if any("python" in s for s in stacks):
    lines.append("- Python 3.12+")
if any("node" in s or "typescript" in s for s in stacks):
    lines.append("- Node.js 18+")

# Installation commands adapt too
if any("python" in s for s in stacks):
    lines.extend([
        "python -m venv .venv",
        "source .venv/bin/activate",
        "pip install -e '.[dev]'",
    ])
elif any("node" in s or "typescript" in s for s in stacks):
    lines.append("npm install")
```

### 5. Non-Destructive README, Destructive Changelog

The two generators have different `overwrite` policies:

```python
# Changelog: overwrite=True — regenerate replaces previous
GeneratedFile(path="CHANGELOG.md", overwrite=True,
    reason=f"Generated changelog from {commit_count} commits")

# README: overwrite=False — never overwrite existing
GeneratedFile(path="README.md", overwrite=False,
    reason="Generated README template from project metadata")
```

Changelogs are meant to be regenerated. READMEs are customized
by hand — overwriting would destroy manual edits.

### 6. Key File Detection with Multiple Variants

The status endpoint checks multiple filename variants for each
key documentation file:

```python
for name, patterns in [
    ("changelog", ["CHANGELOG.md", "CHANGELOG", "CHANGES.md", "HISTORY.md"]),
    ("license",   ["LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE"]),
    ("contributing", ["CONTRIBUTING.md", "CONTRIBUTING", "CONTRIBUTE.md"]),
    ("code_of_conduct", ["CODE_OF_CONDUCT.md"]),
    ("security_policy", ["SECURITY.md"]),
]:
```

This accommodates different naming conventions across ecosystems
(e.g., `LICENCE` for British English, `CHANGES.md` for Python
packages, `HISTORY.md` for Ruby gems).

---

## Design Decisions

### Why status is cached but coverage and links are not

- **Status** scans the filesystem for docs, API specs, key files.
  Changes infrequently. Cache key: `"docs"`.
- **Coverage** depends on module detection + README existence.
  During documentation work, READMEs are added frequently.
  Stale coverage would confuse the user ("I just added a README
  but coverage didn't update").
- **Links** run on-demand. Caching would miss newly broken links
  after file edits.

### Why link validation is internal-only

```python
# Skip external URLs
if link_target.startswith(("http://", "https://", "mailto:", "ftp://")):
    continue
```

External URL checking would require network requests, which:
1. Could be slow (DNS resolution, HTTP timeouts)
2. Could fail in offline environments
3. Would produce false positives (temporary outages, rate limiting)
4. Is a separate concern (should be a CI step, not a dashboard feature)

### Why markdown files are capped at 100

```python
return files[:100]  # Cap at 100
```

Projects with generated documentation (e.g., API docs, storybooks)
can have thousands of markdown files. Link-checking all of them
would freeze the dashboard. The cap ensures reasonable response
times (~2s) while covering the most common case.

### Why generate uses GeneratedFile model

Both generators return `GeneratedFile` instances (via `model_dump()`)
instead of raw dicts. This ensures consistent structure across all
generation features (Docker, CI, DNS, docs) with the same fields:
`path`, `content`, `reason`, `overwrite`.

### Why README overwrite is False

A generated README is a starting template with TODO placeholders.
Once the user customizes it, regenerating should NOT overwrite
their work. The frontend should check if the file exists and
warn before writing. The generator explicitly sets `overwrite=False`
as a safety default.

---

## Coverage Summary

| Capability | Endpoint | File | Tracked |
|-----------|----------|------|---------|
| Documentation inventory | GET `/docs/status` | `status.py` | No (cached) |
| Per-module coverage | GET `/docs/coverage` | `status.py` | No |
| Link validation | GET `/docs/links` | `status.py` | No |
| Changelog generation | POST `/docs/generate/changelog` | `generate.py` | ✅ generate |
| README generation | POST `/docs/generate/readme` | `generate.py` | ✅ generate |
