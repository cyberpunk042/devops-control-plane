# Security Domain

> **5 files · 1,132 lines · Secret scanning, sensitive file detection,
> gitignore analysis & generation, finding dismissal, and security
> posture scoring.**
>
> Scans source code for hardcoded secrets using 18 regex patterns,
> detects sensitive files that shouldn't be tracked, analyzes
> `.gitignore` completeness against stack-aware pattern catalogs,
> manages inline `# nosec` suppressions, and computes a unified
> security posture score (0–100, letter grade A–F) by aggregating
> five weighted checks.

---

## How It Works

The security domain has five operational modes. Scanning and detection
are offline and fast. Posture scoring aggregates everything into a
single grade. Dismissal modifies source files. Generation creates
new files.

```
┌──────────────────────────────────────────────────────────────────┐
│ SCAN — Find hardcoded secrets in source code                      │
│                                                                   │
│  scan_secrets(project_root, *, max_files=500, max_file_size=512KB)│
│    │                                                              │
│    ├── _iter_files(root, 500) → collect up to 500 files via rglob │
│    │                                                              │
│    ├── Filter: _should_scan(path, root)?                          │
│    │     ├── Skip if any path part is in _SKIP_DIRS (17 dirs)     │
│    │     ├── Skip if extension in _SKIP_EXTENSIONS (31 exts)      │
│    │     ├── Skip if filename in _EXPECTED_SECRET_FILES (9 files) │
│    │     └── Skip if not a file                                   │
│    │                                                              │
│    ├── Skip if file > 512KB or size == 0                          │
│    │                                                              │
│    ├── For each line in each file:                                │
│    │     ├── Skip comment lines (starts with #, //, *)            │
│    │     ├── If _has_nosec(line) → count as suppressed, skip      │
│    │     └── Test against 18 _SECRET_PATTERNS:                    │
│    │           ├── First match wins (one finding per line)         │
│    │           └── Redact match: first 8 chars + "****" + last 4  │
│    │                                                              │
│    └── OUTPUT:                                                    │
│          {                                                        │
│              "ok": True,                                          │
│              "findings": [{file, line, pattern, severity,         │
│                            description, match_preview}, ...],     │
│              "summary": {total, suppressed, critical, high,       │
│                          medium},                                 │
│              "files_scanned": int,                                │
│          }                                                        │
├──────────────────────────────────────────────────────────────────┤
│ DETECT — Find sensitive files that shouldn't be tracked           │
│                                                                   │
│  detect_sensitive_files(project_root)                              │
│    │                                                              │
│    ├── Load patterns from DataRegistry (_sensitive_patterns())    │
│    │     Each pattern: (glob_pattern, description)                │
│    │                                                              │
│    ├── For each pattern: rglob(pattern) across project            │
│    │     ├── Skip if any path part is in _SKIP_DIRS               │
│    │     └── Check if file is gitignored (_is_gitignored)         │
│    │                                                              │
│    └── OUTPUT:                                                    │
│          {                                                        │
│              "files": [{path, pattern, description,               │
│                         gitignored: bool}, ...],                  │
│              "count": int,                                        │
│              "unprotected": int,  ← count where !gitignored       │
│          }                                                        │
├──────────────────────────────────────────────────────────────────┤
│ ANALYZE — Check .gitignore completeness                           │
│                                                                   │
│  gitignore_analysis(root, *, stack_names=None)                    │
│    │                                                              │
│    ├── Read .gitignore, parse active lines (non-comment, non-blank)│
│    │                                                              │
│    ├── Load gitignore catalog from DataRegistry:                  │
│    │     catalog["universal"]  → always-expected patterns         │
│    │     catalog["stacks"][base] → per-stack patterns             │
│    │     (base = stack_name.split("-")[0])                         │
│    │                                                              │
│    ├── For each expected pattern:                                 │
│    │     ├── Direct match?                                        │
│    │     ├── Match without trailing slash?                         │
│    │     ├── Substring match in any current line?                 │
│    │     └── Otherwise → missing                                  │
│    │                                                              │
│    └── OUTPUT:                                                    │
│          {                                                        │
│              "exists": bool,                                      │
│              "current_patterns": int,                             │
│              "missing_patterns": [{pattern, category, reason}],   │
│              "missing_count": int,                                │
│              "coverage": float (0.0–1.0),                         │
│          }                                                        │
├──────────────────────────────────────────────────────────────────┤
│ SCORE — Unified security posture                                  │
│                                                                   │
│  security_posture(project_root)                                   │
│    │                                                              │
│    ├── Check 1: Secret scanning (weight 30)                       │
│    │     0 findings → 1.0 | critical → 0.0 | high → 0.3         │
│    │     | medium only → 0.6                                      │
│    │                                                              │
│    ├── Check 2: Sensitive files (weight 15)                       │
│    │     0 files → 1.0 | all gitignored → 0.9                    │
│    │     | unprotected → max(0, 1.0 - unprotected * 0.3)         │
│    │                                                              │
│    ├── Check 3: Gitignore coverage (weight 20)                    │
│    │     No .gitignore → 0.0 | otherwise → coverage value        │
│    │     Auto-detects stacks via load_project + discover_stacks   │
│    │                                                              │
│    ├── Check 4: Vault protection (weight 20)                      │
│    │     No .env → 0.8 | locked → 1.0 | unlocked → 0.5          │
│    │     | .env but no vault → 0.3                                │
│    │                                                              │
│    ├── Check 5: Dependency audit (weight 15)                      │
│    │     No vulns → 1.0 | vulns → max(0, 1.0 - vulns * 0.15)    │
│    │     Tool not available → 0.5                                 │
│    │                                                              │
│    ├── Final: score = sum(score * weight) / sum(weights) * 100    │
│    │                                                              │
│    ├── Grade: ≥90 → A | ≥75 → B | ≥60 → C | ≥40 → D | <40 → F  │
│    │                                                              │
│    └── OUTPUT:                                                    │
│          {                                                        │
│              "score": float (0–100),                              │
│              "grade": "A" | "B" | "C" | "D" | "F",               │
│              "checks": [{name, passed, score, weight,             │
│                          details, recommendations}, ...],         │
│              "recommendations": [str, ...],  ← top 10 aggregated │
│              "missing_tools": [...],         ← check_required_tools│
│          }                                                        │
├──────────────────────────────────────────────────────────────────┤
│ FACILITATE — Generate and manage                                  │
│                                                                   │
│  generate_gitignore(root, stack_names)                             │
│    ├── Build sections: Security, OS, Editor, per-stack            │
│    └── Return GeneratedFile model_dump()                          │
│                                                                   │
│  dismiss_finding(root, file, line, comment)                       │
│    ├── Read file, find line, append "# nosec" (or "// nosec")    │
│    ├── Comment style chosen by file extension                     │
│    └── Return {ok, file, line} or {ok, file, line, already}      │
│                                                                   │
│  undismiss_finding(root, file, line)                              │
│    ├── Read file, strip nosec annotation via regex                │
│    └── Return {ok, file, line} or {ok, file, line, already}      │
│                                                                   │
│  batch_dismiss_findings(root, items, comment)                     │
│    ├── Call dismiss_finding for each item                         │
│    ├── Bust devops caches: "audit:l2:risks", "security"           │
│    ├── Record audit event: "🚫 Finding Dismissed"                 │
│    └── Return {ok, count, results}                                │
│                                                                   │
│  undismiss_finding_audited(root, file, line)                      │
│    ├── Call undismiss_finding                                     │
│    ├── Bust devops caches: "audit:l2:risks", "security"           │
│    └── Record audit event: "↩️ Finding Restored"                  │
└──────────────────────────────────────────────────────────────────┘
```

### Secret Patterns

18 compiled regex patterns, each a tuple of
`(name, compiled_regex, severity, description)`:

| # | Pattern | Regex Key | Severity |
|---|---------|----------|----------|
| 1 | AWS Access Key | `AKIA[0-9A-Z]{16}` | critical |
| 2 | AWS Secret Key | `aws[_-]?secret[_-]?access[_-]?key` + 40 chars | critical |
| 3 | GitHub Token (classic) | `ghp_[A-Za-z0-9]{36}` | critical |
| 4 | GitHub Token (fine-grained) | `github_pat_[A-Za-z0-9_]{82}` | critical |
| 5 | GitHub OAuth | `gho_[A-Za-z0-9]{36}` | high |
| 6 | GitHub App Token | `ghu_` or `ghs_` + 36 chars | high |
| 7 | Google API Key | `AIza[0-9A-Za-z\-_]{35}` | high |
| 8 | Google OAuth Client Secret | `GOCSPX-[A-Za-z0-9\-_]{28}` | critical |
| 9 | Slack Bot Token | `xoxb-[0-9]{10,13}-...` | high |
| 10 | Slack Webhook | `hooks.slack.com/services/T.../B.../...` | high |
| 11 | Stripe Secret Key | `sk_live_[0-9a-zA-Z]{24}` | critical |
| 12 | Stripe Publishable Key | `pk_live_[0-9a-zA-Z]{24}` | medium |
| 13 | Private Key Header | `-----BEGIN ... PRIVATE KEY-----` | critical |
| 14 | Hex-encoded Secret | `secret|token|password|key|passwd|api_key` + hex 32+ | high |
| 15 | Base64-encoded Secret | `secret|token|password|key|passwd` + base64 40+ | medium |
| 16 | Database URL | `postgres|mysql|mongodb|redis|amqp` + `://` | high |
| 17 | JWT Token | `eyJ...<3 base64 segments>` | high |
| 18 | Password Assignment | `password|passwd|pwd = "..."` (6+ chars) | medium |

**Severity distribution:** 7 critical, 8 high, 3 medium.

### Nosec Suppression

Lines can be suppressed with inline comments:

```python
api_key = "test_key_123"  # nosec: test fixture
connection = "postgres://..."  // nosec
```

Both `#` and `//` comment styles are supported. The optional reason
after `nosec:` is preserved in the annotation. Detection regex:
`(?:#|//)\\s*nosec\\b` (case-insensitive).

### Comment Style Selection

`dismiss_finding` chooses the comment style based on file extension:

- `// nosec` for: `.js`, `.ts`, `.jsx`, `.tsx`, `.mjs`, `.cjs`, `.c`,
  `.cpp`, `.h`, `.java`, `.go`, `.rs`, `.cs`
- `# nosec` for everything else

### Skip Filters

**`_SKIP_DIRS`** (17 directories):

`.git`, `.venv`, `venv`, `node_modules`, `__pycache__`, `.mypy_cache`,
`.ruff_cache`, `.pytest_cache`, `.tox`, `dist`, `build`, `.eggs`,
`.terraform`, `.pages`, `htmlcov`, `.backup`, `state`

**`_SKIP_EXTENSIONS`** (33 extensions):

`.pyc`, `.pyo`, `.so`, `.dll`, `.exe`, `.bin`, `.png`, `.jpg`, `.jpeg`,
`.gif`, `.ico`, `.svg`, `.webp`, `.mp4`, `.mp3`, `.wav`, `.avi`, `.mov`,
`.zip`, `.tar`, `.gz`, `.bz2`, `.xz`, `.7z`, `.woff`, `.woff2`, `.ttf`,
`.eot`, `.pdf`, `.doc`, `.docx`, `.lock`, `.vault`

Note: `.lock` files are excluded because they often contain hashes that
look like secrets. `.vault` files are excluded because they are our own
encrypted format.

**`_EXPECTED_SECRET_FILES`** (9 files):

`.env`, `.env.example`, `.env.sample`, `.env.template`, `.env.local`,
`.env.development`, `.env.staging`, `.env.production`, `.env.test`

These files are expected to contain secret-like values and are not
flagged during scanning.

### Security Posture Scoring

`security_posture()` runs 5 checks with explicit integer weights:

| # | Check | Weight | Score Logic |
|---|-------|--------|------------|
| 1 | Secret scanning | **30** | 0 findings → 1.0 · critical → 0.0 · high → 0.3 · medium → 0.6 |
| 2 | Sensitive files | **15** | 0 files → 1.0 · all gitignored → 0.9 · unprotected → `max(0, 1.0 - n * 0.3)` |
| 3 | Gitignore coverage | **20** | No file → 0.0 · otherwise → coverage float from analysis |
| 4 | Vault protection | **20** | No .env → 0.8 · locked → 1.0 · unlocked → 0.5 · .env no vault → 0.3 |
| 5 | Dependency audit | **15** | 0 vulns → 1.0 · n vulns → `max(0, 1.0 - n * 0.15)` · unavailable → 0.5 |

**Formula:** `final_score = sum(check_score × weight) / sum(weights) × 100`

Each check score is 0.0–1.0 internally. The final score is 0–100.

**Grade thresholds:**

| Score | Grade |
|-------|-------|
| ≥ 90 | A |
| ≥ 75 | B |
| ≥ 60 | C |
| ≥ 40 | D |
| < 40 | F |

The posture function auto-detects stacks for the gitignore check by
loading `project.yml` → `discover_stacks` → `detect_modules` and
extracting `effective_stack` from each module. This is wrapped in
try/except so it degrades gracefully if detection fails.

---

## Key Data Shapes

### scan_secrets response

```python
{
    "ok": True,
    "findings": [
        {
            "file": "config.py",            # relative to project_root
            "line": 42,
            "pattern": "AWS Access Key",     # name from _SECRET_PATTERNS
            "severity": "critical",
            "description": "AWS IAM access key ID",
            "match_preview": "AKIA1234****5678",  # redacted
        },
    ],
    "summary": {
        "total": 3,
        "suppressed": 1,       # lines with # nosec that matched
        "critical": 1,
        "high": 1,
        "medium": 1,
    },
    "files_scanned": 150,
}
```

### detect_sensitive_files response

```python
{
    "files": [
        {
            "path": "secrets/credentials.json",   # relative path
            "pattern": "*.credentials*",           # glob from DataRegistry
            "description": "Cloud credential file",
            "gitignored": False,
        },
    ],
    "count": 2,
    "unprotected": 1,     # count where gitignored == False
}
```

### gitignore_analysis response

```python
# .gitignore exists
{
    "exists": True,
    "current_patterns": 45,       # active lines in .gitignore
    "missing_patterns": [
        {
            "pattern": ".mypy_cache/",
            "category": "python",
            "reason": "Required for python projects",
        },
    ],
    "missing_count": 3,
    "coverage": 0.92,             # 0.0–1.0
}

# No .gitignore
{
    "exists": False,
    "current_patterns": 0,
    "missing_patterns": [],
    "coverage": 0.0,
}
```

### security_posture response

```python
{
    "score": 78.5,                  # 0–100
    "grade": "B",                   # A/B/C/D/F
    "checks": [
        {
            "name": "Secret scanning",
            "passed": True,           # boolean
            "score": 1.0,             # 0.0–1.0 (NOT 0–100)
            "weight": 30,
            "details": "No secrets found in 150 files",
            "recommendations": [],
        },
        {
            "name": "Gitignore coverage",
            "passed": False,          # score >= 0.9 for this check
            "score": 0.85,
            "weight": 20,
            "details": "Coverage: 85% (3 pattern(s) missing)",
            "recommendations": [
                "Update .gitignore with missing patterns",
            ],
        },
    ],
    "recommendations": [             # top 10 from all checks, flattened
        "Update .gitignore with missing patterns",
    ],
    "missing_tools": [               # from check_required_tools(["git"])
        {"tool": "git", "available": True},
    ],
}
```

### dismiss_finding response

```python
# Newly dismissed
{"ok": True, "file": "config.py", "line": 42}

# Already had # nosec
{"ok": True, "file": "config.py", "line": 42, "already": True}

# Error
{"ok": False, "error": "File not found: config.py"}
```

Note: there is **no** `annotation` field in the response — the old
README fabricated that. The annotation is written to the file but not
returned.

### generate_gitignore response

```python
{
    "ok": True,
    "file": {
        "path": ".gitignore",
        "content": "# ── Security ──...\n.env\n...",
        "overwrite": False,
        "reason": "Generated .gitignore for stacks: python, node",
    },
}
```

The `file` dict is a `GeneratedFile.model_dump()` — it has `path`,
`content`, `overwrite`, and `reason`. There are **no** `patterns` or
`stacks` fields — the old README fabricated those.

### batch_dismiss_findings response

```python
{
    "ok": True,          # False if any item errored
    "count": 3,          # total items processed
    "results": [         # one per input item
        {"ok": True, "file": "a.py", "line": 10},
        {"ok": True, "file": "b.py", "line": 20, "already": True},
    ],
}
```

---

## Architecture

```
        Routes (security_scan/)           CLI (cli/security/)
        ┌──────────────────────┐         ┌──────────────────┐
        │ detect.py            │         │ detect.py         │
        │ actions.py           │         │ observe.py        │
        └──────────┬───────────┘         │ generate.py       │
                   │                     └────────┬──────────┘
                   │                              │
          ┌────────▼──────────────────────────────▼──┐
          │  __init__.py (42 lines)                   │
          │  Re-exports all public API                │
          └──┬──────────┬──────────┬─────────────────┘
             │          │          │
      ┌──────▼──┐  ┌────▼────┐  ┌─▼────────────┐
      │ scan.py │  │posture.py│ │ common.py     │
      │ 361 ln  │  │ 305 ln   │ │ 382 ln        │
      ├─────────┤  ├──────────┤ ├───────────────┤
      │ scan_   │  │ security_│ │ _SECRET_      │
      │ secrets │  │ posture  │ │   PATTERNS    │
      │ detect_ │  │          │ │ _SKIP_DIRS    │
      │ sensitive│  │ Calls:  │ │ _SKIP_EXTS    │
      │ files   │  │ scan_*  │ │ _EXPECTED_*   │
      │ gitignore│  │ detect_*│ │ _NOSEC_RE     │
      │ _analysis│  │ gi_anals│ │ dismiss_*     │
      │ generate_│  │ vault_* │ │ undismiss_*   │
      │ gitignore│  │ pkg_aud │ │ batch_dismiss │
      └──┬──────┘  └─────────┘ └───────────────┘
         │                            ↑
         └────────────────────────────┘
              scan.py imports from common.py
```

**`ops.py` (42 lines)** is a backward-compatibility shim — it re-exports
everything from `__init__.py` so that old imports like
`from src.core.services.security.ops import scan_secrets` continue
working. It exists because routes use
`from src.core.services.security import ops as security_ops`.

### Backward Compatibility Shims (at services root)

| Shim File | What It Re-exports |
|-----------|-------------------|
| `security_ops.py` | `from src.core.services.security import *` |
| `security_common.py` | `from src.core.services.security.common import *` |
| `security_scan.py` | `from src.core.services.security.scan import *` |
| `security_posture.py` | `from src.core.services.security.posture import *` |

---

## Dependency Graph

```
common.py (foundation — no imports from this package)
   │
   ├── re                              ← pattern compilation
   └── pathlib                         ← file operations
   │
   │   dismiss/undismiss → devops.cache   (lazy import)
   │     ├── cache.invalidate("audit:l2:risks")
   │     ├── cache.invalidate("security")
   │     └── cache.record_event(...)
   │
   ↓
scan.py (imports from common)
   │
   ├── common._SECRET_PATTERNS         ← pattern matching
   ├── common._SKIP_DIRS               ← directory filter
   ├── common._SKIP_EXTENSIONS         ← extension filter
   ├── common._EXPECTED_SECRET_FILES   ← expected files filter
   ├── common._should_scan             ← combined filter
   ├── common._has_nosec               ← suppression detection
   ├── DataRegistry.sensitive_files    ← lazy import
   ├── DataRegistry.gitignore_patterns ← lazy import
   ├── GeneratedFile                   ← for generate_gitignore
   └── audit_helpers.make_auditor      ← audit logging
   │
   ↓
posture.py (standalone — calls scan functions internally)
   │
   ├── scan_secrets                    ← called directly (not imported)
   ├── detect_sensitive_files          ← called directly
   ├── gitignore_analysis              ← called directly
   ├── vault.vault_status              ← lazy import
   ├── packages_svc.ops.package_audit  ← lazy import
   ├── config.loader.load_project      ← lazy (for stack detect)
   ├── config.stack_loader             ← lazy (for stack detect)
   ├── detection.detect_modules        ← lazy (for stack detect)
   └── tool_requirements               ← lazy (missing_tools)
```

Key design: `posture.py` uses **no imports from this package at module
level**. It calls `scan_secrets`, `detect_sensitive_files`, and
`gitignore_analysis` as bare function calls — these are resolved at
runtime from the module scope. All cross-domain imports are lazy
(inside the function body) to avoid circular dependencies.

---

## Consumers

| Layer | Module | What It Uses | Import Style |
|-------|--------|-------------|--------------|
| **Routes** | `routes/security_scan/detect.py` | `scan_secrets`, `detect_sensitive_files`, `security_posture` | via `ops` module |
| **Routes** | `routes/security_scan/actions.py` | `dismiss_finding`, `undismiss_finding`, `batch_dismiss_findings` | via `ops` module |
| **Routes** | `routes/devops/audit.py` | `batch_dismiss_findings`, `undismiss_finding_audited` | lazy |
| **CLI** | `cli/security/detect.py` | `scan_secrets`, `detect_sensitive_files` | lazy |
| **CLI** | `cli/security/observe.py` | `gitignore_analysis`, `security_posture` | lazy |
| **CLI** | `cli/security/generate.py` | `generate_gitignore` | lazy |
| **Services** | `audit/l2_risk.py` | `scan_secrets`, `detect_sensitive_files`, `gitignore_analysis` | lazy (via ops) |
| **Services** | `wizard/setup_git.py` | `generate_gitignore` | lazy (direct scan import) |
| **Services** | `wizard/helpers.py` | `gitignore_analysis` | lazy (via ops) |

---

## File Map

```
security/
├── __init__.py    42 lines   — public API re-exports (all symbols)
├── common.py      382 lines  — patterns, constants, dismiss/undismiss ops
├── scan.py        361 lines  — secret scan, sensitive files, gitignore
├── posture.py     305 lines  — unified security posture scoring
├── ops.py         42 lines   — backward-compat shim (= __init__.py)
└── README.md                 — this file
```

---

## Per-File Documentation

### `common.py` — Patterns & Operations (382 lines)

The foundation module. Everything else imports from here.

**Constants:**

| Constant | Type | Count | Purpose |
|----------|------|-------|---------|
| `_SECRET_PATTERNS` | `list[tuple]` | 18 | `(name, compiled_regex, severity, description)` |
| `_SKIP_DIRS` | `frozenset` | 17 | Directories excluded from scanning |
| `_SKIP_EXTENSIONS` | `frozenset` | 33 | File extensions excluded (binary, media, lock, vault) |
| `_EXPECTED_SECRET_FILES` | `frozenset` | 9 | `.env` variants — not flagged |
| `_NOSEC_RE` | `re.Pattern` | — | `(?:#\|//)\\s*nosec\\b` (detection) |
| `_NOSEC_STRIP_RE` | `re.Pattern` | — | Strips nosec + trailing text (undismiss) |

**Functions:**

| Function | What It Does |
|----------|-------------|
| `_should_scan(path, root)` | Combined filter: skip dirs + extensions + expected files + non-files |
| `_has_nosec(line)` | Check if line has inline `# nosec` or `// nosec` |
| `dismiss_finding(root, file, line, comment)` | Add `# nosec` (or `// nosec`) to the target line. Chooses comment style by extension. Returns `{ok, file, line}` or `already: True`. |
| `undismiss_finding(root, file, line)` | Strip nosec annotation from line via `_NOSEC_STRIP_RE`. Returns `{ok, file, line}` or `already: True`. |
| `batch_dismiss_findings(root, items, comment)` | Call `dismiss_finding` for each item, bust devops caches (`audit:l2:risks` + `security`), record "🚫 Finding Dismissed" audit event. |
| `undismiss_finding_audited(root, file, line)` | Call `undismiss_finding`, bust caches, record "↩️ Finding Restored" audit event. |

### `scan.py` — Scanning & Analysis (361 lines)

**Public functions:**

| Function | What It Does |
|----------|-------------|
| `scan_secrets(root, *, max_files=500, max_file_size=512_000)` | Scan source code for hardcoded secrets. Iterates files, applies filters, tests each line against 18 patterns. One finding per line (first match wins). Redacts match preview. |
| `detect_sensitive_files(root)` | Find files matching sensitive patterns from DataRegistry. Check each against `.gitignore`. Returns found files with `gitignored` flag and `unprotected` count. |
| `gitignore_analysis(root, *, stack_names=None)` | Analyze `.gitignore` completeness against universal + stack-specific patterns from DataRegistry. Returns coverage ratio and missing patterns list. |
| `generate_gitignore(root, stack_names)` | Build a `.gitignore` with sections: Security (`.env`, keys), OS (`.DS_Store`), Editor (swap files), Per-stack (from catalog). Returns `GeneratedFile` model dump. |

**Private functions:**

| Function | What It Does |
|----------|-------------|
| `_iter_files(root, max_count)` | Collect up to `max_count` regular files via `rglob("*")`. |
| `_sensitive_patterns()` | Load `DataRegistry.sensitive_files` (lazy DataRegistry import). |
| `_gitignore_catalog()` | Load `DataRegistry.gitignore_patterns` (lazy DataRegistry import). |
| `_is_gitignored(rel_path, pattern, gitignore_content)` | Simple gitignore check: direct name match, extension match (`*.pem`), or path substring match. Not fully spec-compliant but practical. |

### `posture.py` — Security Scoring (305 lines)

A single public function: `security_posture(project_root)`.

This is a ~295-line function that sequentially runs 5 checks, each
wrapped in a try/except so individual failures don't crash the whole
assessment. The function:

1. Calls `scan_secrets` → scores based on severity of findings
2. Calls `detect_sensitive_files` → scores based on unprotected count
3. Auto-detects stacks, calls `gitignore_analysis` → uses coverage value
4. Calls `vault.vault_status` → scores based on lock state
5. Calls `packages_svc.ops.package_audit` → scores based on vuln count

Cross-domain imports (vault, packages_svc, config, detection,
tool_requirements) are all lazy — inside the function body. This means
`posture.py` has zero import-time dependencies on other services.

### `ops.py` — Backward-Compat Shim (42 lines)

Identical content to `__init__.py`. Exists because routes import as
`from src.core.services.security import ops as security_ops`. This
gives routes a module-level `security_ops` namespace without importing
the package directly (which could cause circular import issues with
lazy loaders).

---

## Audit Trail

| Event Label | Icon | Action | Target Format |
|-------------|------|--------|---------------|
| Finding Dismissed | 🚫 | `dismissed` | `file1.py:10, file2.py:20` |
| Finding Restored | ↩️ | `undismissed` | `file.py:42` |

Both events bust two devops caches: `audit:l2:risks` and `security`.
Dismissal events include the `comment` in the `detail` dict and in
the summary text. Only newly-dismissed items (not `already: True`)
are logged.

---

## Advanced Feature Showcase

### 1. Match Redaction — Safe Preview Without Leaking Secrets

When a secret is found, the full match is redacted for safe display:

```python
# scan.py — scan_secrets (lines 78-79)

raw = match.group(0)
preview = raw[:8] + "****" + raw[-4:] if len(raw) > 12 else "****"
```

If the match is long enough (>12 chars), the first 8 and last 4 characters
are shown with `****` in between: `AKIA1234****5678`. This gives enough
context for identification without exposing the full secret. Matches
≤12 chars are fully redacted to `****` — no partial exposure of short
tokens.

### 2. Dual-Style Nosec Detection and Annotation

The system handles both `#` and `//` comment styles for inline suppression:

```python
# common.py — detection (line 206)
_NOSEC_RE = re.compile(r"(?:#|//)\s*nosec\b", re.IGNORECASE)

# common.py — stripping (line 209)
_NOSEC_STRIP_RE = re.compile(r"\s*(?:#|//)\s*nosec\b.*$", re.IGNORECASE)

# common.py — dismiss_finding (lines 250-257)
ext = target.suffix.lower()
if ext in (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs",
           ".c", ".cpp", ".h", ".java", ".go", ".rs", ".cs"):
    tag = f"// nosec: {comment}" if comment else "// nosec"
else:
    tag = f"# nosec: {comment}" if comment else "# nosec"
```

Three coordinated regexes and extension-based style selection:
- `_NOSEC_RE` detects both styles (case-insensitive, word-bounded)
- `_NOSEC_STRIP_RE` strips the annotation AND everything after it (reason text)
- `dismiss_finding` writes the correct style for the file type (13 C-family
  extensions use `//`, everything else uses `#`)

### 3. Three-Layer File Filter Cascade

The scanner applies three sequential filters before reading any file:

```python
# common.py — _should_scan (lines 178-199)

def _should_scan(path, project_root):
    rel = path.relative_to(project_root)

    # Layer 1: Directory exclusion (17 dirs)
    for part in rel.parts:
        if part in _SKIP_DIRS:
            return False

    # Layer 2: Extension exclusion (33 extensions)
    if path.suffix.lower() in _SKIP_EXTENSIONS:
        return False

    # Layer 3: Expected secret files (9 .env variants)
    if rel.name in _EXPECTED_SECRET_FILES:
        return False

    if not path.is_file():
        return False
    return True
```

Then in `scan_secrets`, a fourth layer checks file size (>512KB or empty).
This cascade ensures the scanner only reads text files that could
realistically contain hardcoded secrets, avoiding false positives from
binary files, build artifacts, and intentional secret stores.

### 4. Four-Way Gitignore Coverage Matching

The coverage check uses progressively fuzzy matching to avoid false
"missing pattern" reports:

```python
# scan.py — gitignore_analysis (lines 270-278)

for pattern, category, reason in expected:
    if pattern in current_lines:               # Exact match
        covered += 1
    elif pattern.rstrip("/") in current_lines: # Without trailing slash
        covered += 1
    elif any(pattern.rstrip("/") in cl         # Substring in any line
             for cl in current_lines):
        covered += 1
    else:
        missing.append({"pattern": pattern, "category": category,
                        "reason": reason})
```

Why four levels? Users write `.gitignore` differently:
- Exact: `__pycache__/` matches `__pycache__/` ✓
- No slash: `__pycache__` matches `__pycache__/` ✓
- Substring: `build/` is covered by `**/build/` ✓
- Only truly absent patterns are reported as missing

### 5. Weighted Posture Aggregation with Per-Check Isolation

Each of the 5 checks runs in its own try/except — a failing check
doesn't crash the entire assessment:

```python
# posture.py — security_posture (lines 34-276)

# Check 1: Secret scanning (weight: 30)
weight = 30
total_weight += weight
try:
    scan = scan_secrets(project_root)
    if scan["summary"]["total"] == 0:
        score = 1.0
    elif scan["summary"]["critical"] > 0:
        score = 0.0                    # any critical = zero score
    elif scan["summary"]["high"] > 0:
        score = 0.3
    else:
        score = 0.6                    # medium only
    # ... build check dict
    total_score += score * weight
except Exception as e:
    checks.append({"name": "...", "score": 0, ...})
    # Note: total_score unchanged, weight still counted
    # → failing check pulls the score DOWN, not ignored

# Final: weighted average → 0-100 scale
final_score = round(total_score / total_weight * 100, 1)
```

Key design: when a check fails, its weight is still added to
`total_weight` but contributes 0 to `total_score`. This penalizes
broken checks rather than silently ignoring them — a crashed scanner
should lower the score, not artificially inflate it.

### 6. Batch Dismiss with Single Cache Bust + Conditional Audit

`batch_dismiss_findings` optimizes by busting caches once after all
file writes, and only logging truly new dismissals:

```python
# common.py — batch_dismiss_findings (lines 317-352)

results = []
for item in items:
    r = dismiss_finding(root, item["file"], int(item["line"]), comment)
    results.append(r)

# Bust caches ONCE after all writes (not per-item)
devops_cache.invalidate(project_root, "audit:l2:risks")
devops_cache.invalidate(project_root, "security")

# Only log newly dismissed items (not already-dismissed ones)
ok_items = [r for r in results if r.get("ok") and not r.get("already")]
if ok_items:
    files_str = ", ".join(f"{r['file']}:{r['line']}" for r in ok_items)
    devops_cache.record_event(
        project_root,
        label="🚫 Finding Dismissed",
        summary=f"# nosec added to {len(ok_items)} line(s): {files_str}"
            + (f" — {comment}" if comment else ""),
        detail={"items": ok_items, "comment": comment},
        action="dismissed",
        target=files_str,
    )
```

Without this: dismissing 10 findings = 10 cache invalidations + 10 audit log
entries. With this: 1 cache bust + 1 audit entry listing all files.

### 7. Graceful Stack Auto-Detection in Posture Scoring

The gitignore coverage check auto-detects project stacks, but wraps
the detection in a nested try/except so it degrades gracefully:

```python
# posture.py — security_posture (lines 127-139)

stack_names: list[str] = []
try:
    from src.core.config.loader import load_project
    from src.core.config.stack_loader import discover_stacks
    from src.core.services.detection import detect_modules

    project = load_project(project_root / "project.yml")
    stacks = discover_stacks(project_root / "stacks")
    detection = detect_modules(project, project_root, stacks)
    stack_names = list({
        m.effective_stack for m in detection.modules
        if m.effective_stack
    })
except Exception:
    pass  # falls back to empty stacks = universal patterns only

gi = gitignore_analysis(project_root, stack_names=stack_names)
```

If `project.yml` doesn't exist, or stacks aren't configured, or module
detection fails, `stack_names` remains `[]` and the analysis only checks
universal patterns. The outer check's try/except still runs — so the
posture score always includes a gitignore assessment, just with reduced
coverage expectations.

---

### Feature Coverage Summary

| Feature | Where | Complexity |
|---------|-------|-----------|
| Length-aware match redaction | `scan.py` `scan_secrets` | >12 chars partial, ≤12 full redact |
| Dual comment style nosec system | `common.py` three regexes + extension map | Detect, strip, and write correct style |
| Three-layer file filter cascade | `common.py` `_should_scan` | Dirs → extensions → expected files |
| Four-way gitignore coverage | `scan.py` `gitignore_analysis` | Exact → no-slash → substring → missing |
| Per-check isolated posture scoring | `posture.py` `security_posture` | Failing checks penalize, not ignored |
| Batch dismiss with single cache bust | `common.py` `batch_dismiss_findings` | N writes → 1 bust, conditional audit |
| Graceful stack auto-detection | `posture.py` nested try/except | Degrades to universal patterns only |

---

## Design Decisions

### Why regex-based secret scanning instead of entropy analysis?

Regex patterns produce specific, actionable findings ("AWS Access Key
at config.py:42"). Entropy analysis flags random strings that may not
be secrets, producing false positives that erode trust. The 18 patterns
cover the most common secret types with high precision. The `# nosec`
suppression handles remaining false positives on a per-line basis.

### Why inline nosec instead of a separate suppression file?

Inline `# nosec` comments are visible at the point of suppression,
making them auditable during code review. A separate suppression file
would be disconnected from the code, easy to forget, and harder to
review. The annotation supports optional reasons (`# nosec: test
fixture`) so the suppression rationale is documented in the source.

### Why stack-aware gitignore analysis?

A Python project needs different gitignore patterns than a Node.js
project. Stack detection (via the existing module detection system)
determines which pattern catalogs to check against. This prevents
false positives ("missing `node_modules/` pattern" in a pure Python
project) and ensures relevant recommendations. The stack name is split
on `-` to extract the base language (e.g., `python-flask` → `python`).

### Why weighted scoring in security_posture?

Not all security checks are equally important. A hardcoded AWS key
(weight 30, score 0.0 if critical) matters more than a missing
`.mypy_cache/` gitignore pattern (weight 20, partial score reduction).
Weighted scoring ensures the final grade reflects actual risk severity
rather than counting issues equally.

### Why separate common.py from scan.py?

`common.py` contains the pattern definitions and dismiss/undismiss
operations — state and mutation. `scan.py` contains the scanning
logic — traversal and analysis. This separation means:

- Patterns can be updated without touching scan logic
- Dismiss operations can be used independently (routes import them
  for the audit UI's dismiss buttons)
- The dismiss functions need devops cache access (via lazy import)
  which shouldn't pollute the scan module

### Why does ops.py duplicate __init__.py?

Routes use the pattern `from src.core.services.security import ops as
security_ops` followed by `security_ops.scan_secrets(...)`. This gives
them a clean namespace. If routes imported from `__init__.py` directly,
they'd get the package, which can cause issues with lazy import chains.
The shim is 42 lines of pure re-exports — no logic to maintain.
