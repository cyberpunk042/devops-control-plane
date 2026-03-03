# Config Routes — Project Configuration API

> **1 file · 83 lines · 3 endpoints · Blueprint: `config_bp` · Prefix: `/api`**
>
> Thin HTTP wrappers over `src.core.services.config_ops`.
> These routes handle the project's `project.yml` configuration file:
> reading the current config as JSON, saving updated config from the wizard,
> and discovering content folders (configured, detected, and infrastructure).
> This is the persistence layer for the setup wizard — it reads and writes
> the project's central config file. The core service (328 lines) handles
> YAML parsing, format normalization, key preservation, content folder
> scanning, and audit logging.

---

## How It Works

### Request Flow

```
Wizard / Dashboard / Secrets UI
│
├── GET  /api/config                  → read project.yml as JSON
├── POST /api/config                  → save wizard data → project.yml
└── GET  /api/config/content-folders  → configured + detected content folders
     │
     ▼
routes/config/__init__.py              ← HTTP layer (this file)
     │
     ▼
core/services/config_ops.py (328 lines) ← Business logic
├── read_config()            — parse project.yml → normalized dict
├── save_config()            — merge + key-preserve + write project.yml
└── detect_content_folders() — filesystem scan + infra dir metadata
     │
     ├── core/config/loader.py → find_project_file() (auto-discovery)
     └── audit_helpers → make_auditor() (audit trail on save)
```

### Config Path Resolution

```
_config_path()
     │
     ├── Flask app.config["CONFIG_PATH"] set?
     │   └── YES → Path(CONFIG_PATH)
     │
     └── NO → find_project_file(_project_root())
              │
              ├── Scans for: project.yml, project.yaml,
              │              devops.yml, devops.yaml
              └── Returns Path to first found, or None
```

The config path is resolved lazily per-request. This allows the admin
panel to work both with an explicit config path (passed via CLI
`--config`) and in auto-discovery mode (scanning for known filenames).

### Config Read Flow

```
GET /api/config
     │
     ▼
read_config(project_root, config_path)
     │
     ├── config_path is None?
     │   └── find_project_file(root) → scan for known filenames
     │
     ├── File not found?
     │   └── Return EMPTY TEMPLATE:
     │       { exists: false, config: { version: 1, name: "", ... } }
     │
     └── File found → parse YAML
         │
         ├── Handle "project" wrapper key:
         │   conf = data.get("project", data)
         │   (supports both flat and nested formats)
         │
         └── Normalize to consistent shape:
             { exists: true, path: "...",
               config: { version, name, description, repository,
                         domains, environments, modules,
                         content_folders, external } }
```

### Config Save Flow

```
POST /api/config  { "config": { "name": "my-project", ... } }
     │
     ▼
save_config(project_root, config, config_path)
     │
     ├── Validate: name is required
     │
     ├── Build YAML dict (only include non-empty keys)
     │   ├── version, name (always)
     │   ├── description, repository, domains (if present)
     │   ├── environments, modules (if present)
     │   ├── content_folders (from _contentFolders or content_folders)
     │   └── external (if present)
     │
     ├── Resolve target path:
     │   ├── config_path provided → use it
     │   ├── find_project_file() → use existing file
     │   └── fallback → project_root / "project.yml"
     │
     ├── KEY PRESERVATION: ← critical design feature
     │   read existing YAML, keep any keys NOT in _WIZARD_KEYS
     │   (e.g. "pages", "ci", or custom subsystem keys survive)
     │
     ├── Write: comment header + YAML dump
     │
     └── Audit log: "⚙️ Config Saved" with project name and path
```

### Content Folder Detection

```
GET /api/config/content-folders?include_hidden=true
     │
     ▼
detect_content_folders(project_root, include_hidden=True)
     │
     ├── 1. Scan project_root for directories:
     │   ├── Skip: ., _, node_modules, __pycache__, .git, venv, ...
     │   │        (30 skip patterns in _SKIP_DIRS)
     │   ├── For each dir: count files recursively (capped at 999)
     │   └── Flag as "suggested" if name ∈ _COMMON_CONTENT_NAMES:
     │       docs, media, content, assets, images, files, uploads,
     │       resources, public, static, data, backups, archive, notes, wiki
     │
     └── 2. If include_hidden: append infrastructure dirs:
         ├── .ledger  📒 — Git worktree (shared)
         ├── .state   💾 — Local cache (local)
         ├── .backup  🗄️ — Backup archives (local)
         ├── .large   📦 — Optimised large files (local)
         └── .pages   🌐 — Generated site output (local)
              │
              └── Each tagged with: type, role, icon, description,
                  shared, exists (whether directory actually exists yet)
```

---

## File Map

```
routes/config/
├── __init__.py     83 lines  — blueprint + all 3 endpoints + _config_path helper
└── README.md                 — this file
```

Single-file package — the domain is too small to split. All logic
is in `__init__.py`.

---

## Per-File Documentation

### `__init__.py` — Blueprint + All Endpoints (83 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `api_config_read()` | GET | `/config` | Read project.yml as structured JSON |
| `api_config_save()` | POST | `/config` | Save wizard data → project.yml |
| `api_config_content_folders()` | GET | `/config/content-folders` | List configured + detected content folders |

**Helper — config path resolution:**

```python
def _config_path() -> Path | None:
    from src.core.config.loader import find_project_file

    p = current_app.config.get("CONFIG_PATH")
    if p:
        return Path(p)
    return find_project_file(_project_root())
```

Lazy import of `find_project_file` — only loaded when `CONFIG_PATH`
is not set in the Flask app config. Used by all 3 endpoints.

**Read config:**

```python
result = config_ops.read_config(_project_root(), config_path=_config_path())
if "error" in result:
    return jsonify(result), 500  # 500: server problem (file unreadable)
return jsonify(result)
```

When no config file exists, the core function returns a template
with `exists: false` and empty defaults — allowing the wizard to
render a fresh setup form without errors.

**Save config:**

```python
data = request.get_json(silent=True)
if not data:
    return jsonify({"error": "No JSON body"}), 400

result = config_ops.save_config(
    _project_root(),
    config=data.get("config", {}),    # nested under "config" key
    config_path=_config_path(),
)
```

The wizard sends the full config dict nested under `{"config": {...}}`.
The core function:
1. Validates that `name` is present
2. Builds a clean YAML dict (only non-empty keys)
3. Resolves the target file path (explicit, existing, or fallback)
4. Reads existing YAML to preserve non-wizard keys
5. Writes YAML with comment header
6. Logs to audit trail

**Content folders with hidden directory support:**

```python
include_hidden = request.args.get("include_hidden", "").lower() == "true"
folders = config_ops.detect_content_folders(
    _project_root(), include_hidden=include_hidden,
)
return jsonify({"folders": folders})
```

The `?include_hidden=true` parameter controls whether infrastructure
directories (`.ledger`, `.state`, `.backup`, `.large`, `.pages`)
appear in the response. The wizard uses this for the folder
selection step so users can see both content and infrastructure
directories.

---

## Dependency Graph

```
__init__.py (routes)
├── config_ops           ← from core.services (eager import)
│   ├── config.loader    ← lazy import for find_project_file
│   ├── yaml             ← for YAML parsing and dumping
│   └── audit_helpers    ← for audit trail on save
└── helpers.project_root ← from ui.web.helpers
```

**Core service internals (config_ops.py, 328 lines):**

```
config_ops.py
├── _SKIP_DIRS            — 30 directory names to skip in scanning
├── _COMMON_CONTENT_NAMES — 16 "suggested" content folder names
├── _INFRA_DIRS           — 5 infrastructure directory definitions
│   ├── .ledger (📒, shared)
│   ├── .state  (💾, local)
│   ├── .backup (🗄️, local)
│   ├── .large  (📦, local)
│   └── .pages  (🌐, local)
├── read_config()         — parse + normalize
├── save_config()         — validate + merge + preserve + write + audit
├── detect_content_folders() — scan + classify
└── _count_files()        — recursive count with cap (999 limit)
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Server | `ui/web/server.py` | Imports `config_bp`, registers at `/api` prefix |
| Wizard | `scripts/wizard/_init.html` | `GET /config` (load current config into wizard) |
| Wizard | `scripts/wizard/_nav.html` | `POST /config` (save wizard config on completion) |
| Wizard | `scripts/wizard/_steps.html` | `GET /config/content-folders?include_hidden=true` |
| Secrets | `scripts/secrets/_init.html` | `GET /config` (read config for secrets UI) |

---

## Service Delegation Map

```
Route Handler                  →   Core Service Function
──────────────────────────────────────────────────────────────
api_config_read()              →   config_ops.read_config()
                                    ├→ config.loader.find_project_file() (if no explicit path)
                                    ├→ yaml.safe_load() (parse YAML)
                                    └→ normalize "project" wrapper key

api_config_save()              →   config_ops.save_config()
                                    ├→ validate name required
                                    ├→ build YAML dict (sparse — only non-empty keys)
                                    ├→ config.loader.find_project_file() (resolve path)
                                    ├→ read existing YAML → preserve non-wizard keys
                                    ├→ yaml.dump() → write file with header
                                    └→ _audit("⚙️ Config Saved", ...)

api_config_content_folders()   →   config_ops.detect_content_folders()
                                    ├→ scan project_root directories
                                    ├→ _count_files() per dir (capped at 999)
                                    ├→ flag "suggested" names
                                    └→ append _INFRA_DIRS if include_hidden
```

---

## Data Shapes

### `GET /api/config` response (config exists)

```json
{
    "exists": true,
    "path": "/home/user/my-project/project.yml",
    "config": {
        "version": 1,
        "name": "my-project",
        "description": "DevOps control plane",
        "repository": "github.com/org/repo",
        "domains": ["example.com"],
        "environments": [
            {"name": "dev", "branch": "main"},
            {"name": "prod", "branch": "release"}
        ],
        "modules": [
            {"name": "web", "path": "src/web", "stack": "python"}
        ],
        "content_folders": ["docs", "configs"],
        "external": {
            "github": {"repo": "org/repo", "token_env": "GITHUB_TOKEN"}
        }
    }
}
```

### `GET /api/config` response (no config file)

```json
{
    "exists": false,
    "config": {
        "version": 1,
        "name": "",
        "description": "",
        "repository": "",
        "domains": [],
        "environments": [],
        "modules": [],
        "external": {}
    }
}
```

### `POST /api/config` request

```json
{
    "config": {
        "name": "my-project",
        "description": "DevOps control plane",
        "repository": "github.com/org/repo",
        "modules": [
            {"name": "web", "path": "src/web", "stack": "python"}
        ],
        "_contentFolders": ["docs", "media"]
    }
}
```

Note: `_contentFolders` is the wizard's internal key. The core
service accepts both `_contentFolders` and `content_folders`:

```python
content_folders = config.get("_contentFolders") or config.get("content_folders")
```

### `POST /api/config` response (success)

```json
{
    "ok": true,
    "path": "/home/user/my-project/project.yml"
}
```

### `POST /api/config` response (error — missing name)

```json
{
    "error": "Project name is required"
}
```

### `GET /api/config/content-folders` response (include_hidden=false)

```json
{
    "folders": [
        {"name": "docs", "path": "docs", "file_count": 24, "suggested": true},
        {"name": "media", "path": "media", "file_count": 156, "suggested": true},
        {"name": "configs", "path": "configs", "file_count": 8, "suggested": false},
        {"name": "src", "path": "src", "file_count": 999, "suggested": false}
    ]
}
```

### `GET /api/config/content-folders?include_hidden=true` response

```json
{
    "folders": [
        {"name": "docs", "path": "docs", "file_count": 24, "suggested": true},
        {"name": "media", "path": "media", "file_count": 156, "suggested": true},
        {
            "name": ".ledger",
            "path": ".ledger",
            "file_count": 42,
            "exists": true,
            "type": "infrastructure",
            "role": "ledger",
            "icon": "📒",
            "description": "Git worktree for chat threads, trace snapshots, and audit records",
            "shared": true,
            "suggested": false
        },
        {
            "name": ".state",
            "path": ".state",
            "file_count": 8,
            "exists": true,
            "type": "infrastructure",
            "role": "state",
            "icon": "💾",
            "description": "Local cache — preferences, audit scores, pending audits, run history, traces",
            "shared": false,
            "suggested": false
        },
        {
            "name": ".pages",
            "path": ".pages",
            "file_count": 0,
            "exists": false,
            "type": "infrastructure",
            "role": "pages",
            "icon": "🌐",
            "description": "Generated site output from the Pages pipeline",
            "shared": false,
            "suggested": false
        }
    ]
}
```

---

## Advanced Feature Showcase

### 1. Key Preservation on Save

The most important design feature — saving config from the wizard
must NOT destroy keys managed by other subsystems:

```python
# From config_ops.save_config()
_WIZARD_KEYS = {
    "version", "name", "description", "repository",
    "domains", "environments", "modules",
    "content_folders", "external",
}
if config_path.is_file():
    existing = yaml.safe_load(config_path.read_text()) or {}
    for k, v in existing.items():
        if k not in _WIZARD_KEYS and k not in yml:
            yml[k] = v  # preserve non-wizard keys
```

For example, if `project.yml` contains a `pages:` section managed
by the Pages pipeline, saving wizard data will NOT drop it. The
wizard only touches its own keys — everything else survives.

### 2. Dual Config Path Resolution

All endpoints support two modes transparently:

```python
def _config_path() -> Path | None:
    p = current_app.config.get("CONFIG_PATH")
    if p:
        return Path(p)                        # explicit: CLI --config
    return find_project_file(_project_root())  # auto-discovery
```

And save has a third fallback:
```python
if config_path is None:
    config_path = project_root / "project.yml"  # create new
```

### 3. Empty Template on Missing Config

When no config file exists, read returns a valid empty template:

```python
return {
    "exists": False,
    "config": {
        "version": 1, "name": "", "description": "",
        "repository": "", "domains": [], "environments": [],
        "modules": [], "external": {},
    },
}
```

This allows the wizard to render without special-casing the
"first run" scenario — it just populates form fields from the
template, and the user fills them in.

### 4. Infrastructure Directory Awareness

Content folder detection includes infrastructure directories
with rich metadata when `include_hidden=true`:

```python
_INFRA_DIRS = [
    {"name": ".ledger", "role": "ledger", "icon": "📒",
     "description": "Git worktree for chat threads...", "shared": True},
    {"name": ".state", "role": "state", "icon": "💾",
     "description": "Local cache — preferences...", "shared": False},
    # ... 3 more
]
```

Each infra dir is tagged with:
- `type: "infrastructure"` — distinguishes from user content
- `exists: bool` — whether the directory has been created yet
- `shared: bool` — whether it's shared via git (`.ledger`) or local
- `icon` and `description` — for the wizard UI

### 5. File Count Cap

Folder scanning caps recursive file counts at 999 to prevent
freezing on large directories:

```python
def _count_files(folder: Path, limit: int = 999) -> int:
    count = 0
    for f in folder.rglob("*"):
        if f.is_file():
            count += 1
        if count > limit:
            break  # stop scanning
    return count
```

A `file_count` of 999 means "999 or more" — the UI can show "999+"
without the backend spending time counting millions of files in
`node_modules` or similar.

---

## Design Decisions

### Why this is a single-file package

83 lines, 3 endpoints, 1 helper. Splitting into sub-modules would
add structural overhead with zero readability benefit. The package
exists as a directory (not a standalone `.py` file) for consistency
with every other route domain.

### Why read errors return 500 but save errors return 400

- **Read failure** = server problem (config file unreadable, YAML
  parse error, filesystem permission). The client did nothing
  wrong → 500.
- **Save failure** = client problem (missing name, invalid data).
  The server is functioning correctly → 400.

### Why config data is nested under "config" key in the request

The POST body uses `{"config": {...}}` instead of sending the config
dict at the top level. This leaves room for additional metadata:

```json
{ "config": {...}, "dry_run": true, "comment": "..." }
```

Without nesting, config keys could collide with control keys.

### Why config_ops eagerly imported but config.loader is lazy

`config_ops` is used by every endpoint — lazy import would add
boilerplate with no benefit. `config.loader.find_project_file` is
only needed when `CONFIG_PATH` isn't set (the auto-discovery path).
In production with `--config`, the loader is never imported.

### Why save_config doesn't just write the full dict

The save function builds a sparse YAML dict, including only non-empty
keys. This means a fresh project with no modules gets a clean
3-line YAML file instead of a 20-line file full of empty lists
and blank strings. It also means the file stays readable for
humans who edit it manually.

### Why the "project" wrapper key is handled in read

Some project.yml files use a `project:` top-level key:

```yaml
project:
  name: my-project
  modules: [...]
```

While others are flat:

```yaml
name: my-project
modules: [...]
```

The normalize step handles both:

```python
conf = data.get("project", data) if "project" in data else data
```

---

## Coverage Summary

| Capability | Endpoint | Method |
|-----------|----------|--------|
| Read config | `/config` | GET |
| Save config | `/config` | POST |
| Content folder discovery | `/config/content-folders` | GET |
