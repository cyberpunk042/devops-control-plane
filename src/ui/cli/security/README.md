# CLI Domain: Security — Secret Scanning, Gitignore & Posture Analysis

> **4 files · 317 lines · 5 commands + 1 subgroup · Group: `controlplane security`**
>
> Security operations: scan source code for hardcoded secrets, detect
> sensitive files (keys, certificates) and check gitignore protection,
> analyze .gitignore completeness per stack, compute a unified security
> posture score with per-check breakdown, and generate .gitignore files
> from detected stacks.
>
> Core service: `core/services/security/ops.py` (re-exported via
> `security_ops.py`)

---

## How It Works

```
┌──────────────────────────────────────────────────────────────────────┐
│                       controlplane security                         │
│                                                                      │
│  ┌── Detect ────────┐  ┌── Observe ──────────┐  ┌── Generate ───┐  │
│  │ scan             │  │ gitignore           │  │ generate      │  │
│  │ files            │  │ posture             │  │  gitignore    │  │
│  └──────────────────┘  └─────────────────────┘  └──────────────-┘  │
└──────────┬──────────────────────┬──────────────────┬──────────────┘
           │                      │                  │
           ▼                      ▼                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│               core/services/security/ops.py (via security_ops.py)  │
│                                                                      │
│  scan_secrets(root)               → findings[], summary, scanned   │
│  detect_sensitive_files(root)     → files[], count, unprotected    │
│  gitignore_analysis(root, stacks) → exists, coverage, missing[]    │
│  security_posture(root)           → score, grade, checks[], recs[] │
│  generate_gitignore(root, stacks) → file data                     │
└──────────────────────────────────────────────────────────────────────┘
```

### Security Scanning

The `scan` command searches source code for patterns that match
hardcoded secrets (API keys, passwords, tokens, connection strings).
Findings are categorized by severity:

```
scan_secrets(root)
├── Scan all tracked files
├── For each file:
│   ├── Match against secret patterns (regex-based)
│   ├── For each match:
│   │   ├── Classify severity (critical, high, medium)
│   │   ├── Record: file, line, pattern name, match preview
│   │   └── Add to findings[]
├── Summarize: total, critical, high, medium
└── Return: findings[], summary, files_scanned
```

### Sensitive File Detection

The `files` command looks for known sensitive file types (private keys,
certificates, credential files) and checks whether each is protected
by `.gitignore`:

```
detect_sensitive_files(root)
├── Scan for known file patterns:
│   ├── *.pem, *.key, *.p12, *.pfx     (keys/certs)
│   ├── id_rsa, id_ed25519              (SSH keys)
│   ├── credentials.json, .htpasswd     (credential files)
│   └── *.env (except .env.example)     (environment files)
├── For each found file:
│   ├── Check: is it in .gitignore?
│   └── Record: path, description, gitignored
└── Return: files[], count, unprotected count
```

### Gitignore Completeness

The `gitignore` command checks whether `.gitignore` covers all patterns
needed for the project's detected stacks:

```
gitignore_analysis(root, stack_names)
├── Read .gitignore
├── For each detected stack (python, node, go, ...):
│   └── Check required patterns (*.pyc, node_modules/, etc.)
├── Calculate coverage percentage
├── Identify missing patterns with categories
└── Return: exists, coverage, current_patterns, missing[]
```

### Security Posture

The `posture` command computes a weighted aggregate score across
multiple security dimensions:

```
security_posture(root)
├── Run checks:
│   ├── Hardcoded secrets scan
│   ├── .gitignore completeness
│   ├── Sensitive file protection
│   ├── Dependency vulnerability audit
│   └── (other security checks)
├── For each check:
│   ├── Score: 0.0 to 1.0
│   ├── Weight: relative importance
│   ├── Passed: boolean
│   └── Details: explanation
├── Compute weighted score (0-100)
├── Assign grade (A-F)
├── Generate recommendations
└── Return: score, grade, checks[], recommendations[]
```

### Stack Detection Helper

Both `gitignore` and `generate gitignore` use `_detect_stack_names()`
which imports `detect_stacks` from `env_ops`. This is a cross-domain
dependency: security needs to know what languages/frameworks the
project uses to determine which patterns should be in `.gitignore`.

```python
def _detect_stack_names(project_root):
    from src.core.services.env_ops import detect_stacks
    stacks = detect_stacks(project_root)
    return [s["name"] for s in stacks if s.get("name")]
```

Falls back to empty list on any exception (tolerant detection).

---

## Commands

### `controlplane security scan`

Scan source code for hardcoded secrets.

```bash
controlplane security scan
controlplane security scan --json
```

**Output example (clean):**

```
🔍 Scanning for hardcoded secrets...
✅ No secrets found (142 files scanned)
```

**Output example (findings):**

```
🔍 Scanning for hardcoded secrets...
🚨 5 potential secret(s) found!

   🚨 Critical: 1
   ⚠️  High: 2
   ℹ️  Medium: 2

   🚨 [CRITICAL] aws_access_key
      src/config.py:42 — AKIA1234567890EXAMPLE
   ⚠️  [HIGH] generic_api_key
      src/utils.py:15 — api_key = "sk-1234..."
   ...

   Files scanned: 142
```

**Finding display cap:** Shows at most 20 findings. If more, shows
`"... and N more (use --json for full list)"`.

---

### `controlplane security files`

Detect sensitive files and check gitignore protection.

```bash
controlplane security files
controlplane security files --json
```

**Output example:**

```
📄 Sensitive files (3):
   ✅ certs/server.key
      TLS private key — gitignored
   ❌ config/credentials.json
      Credential file — NOT gitignored
   ✅ .env
      Environment file — gitignored

   🚨 1 file(s) NOT protected by .gitignore!
```

---

### `controlplane security gitignore`

Analyze .gitignore completeness for detected stacks.

```bash
controlplane security gitignore
controlplane security gitignore --json
```

**Output examples:**

```
✅ .gitignore: 95% coverage
   Patterns: 42
```

```
⚠️  .gitignore: 72% coverage
   Patterns: 28

   Missing (8):
      *.pyc                     (python)
      __pycache__/              (python)
      .mypy_cache/              (python)
      node_modules/             (node)
      ...and 4 more
```

**Missing pattern display cap:** Shows at most 15 missing patterns.

---

### `controlplane security posture`

Unified security posture score with visual bar and per-check breakdown.

```bash
controlplane security posture
controlplane security posture --json
```

**Output example:**

```
🔐 Computing security posture...

════════════════════════════════════════════════════════════
  SECURITY POSTURE: 78/100 — Grade B
════════════════════════════════════════════════════════════

  [████████████████████████████████░░░░░░░░] 78%

  ✅ Hardcoded Secrets         100%  (weight: 3)
     No hardcoded secrets found
  ✅ .gitignore Coverage        95%  (weight: 2)
     42 patterns, 95% coverage
  ❌ Sensitive Files             50%  (weight: 2)
     1 of 2 sensitive files not gitignored
  ✅ Dependency Audit           100%  (weight: 2)
     No known vulnerabilities
  ❌ Branch Protection           0%  (weight: 1)
     Main branch not protected

  💡 Recommendations:
     1. Add config/credentials.json to .gitignore
     2. Enable branch protection on main
```

**Recommendation cap:** Shows at most 7 recommendations.

---

### `controlplane security generate gitignore`

Generate .gitignore from detected stacks.

```bash
controlplane security generate gitignore
controlplane security generate gitignore --write
```

**Fallback behavior:** If no stacks are detected, falls back to
generating a minimal Python .gitignore.

---

## File Map

```
cli/security/
├── __init__.py     47 lines — group definition, _resolve_project_root,
│                              _detect_stack_names helper, sub-module imports
├── detect.py      109 lines — scan, files (sensitive file detection)
├── observe.py     108 lines — gitignore analysis, posture score
├── generate.py     53 lines — generate subgroup (gitignore command)
└── README.md               — this file
```

**Total: 317 lines of Python across 4 files.**

---

## Per-File Documentation

### `__init__.py` — Group + helpers (47 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `_resolve_project_root(ctx)` | helper | Reads `config_path` from context, falls back to `find_project_file()` |
| `_detect_stack_names(root)` | helper | Detects project stacks via `env_ops.detect_stacks` (tolerant) |
| `security()` | Click group | Top-level `security` group |
| `from . import detect, observe, generate` | import | Registers sub-modules |

---

### `detect.py` — Secret + file scanning (109 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `scan(ctx, as_json)` | command | Scan source for hardcoded secrets |
| `sensitive_files(ctx, as_json)` | command (`files`) | Detect sensitive files, check gitignore protection |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `scan_secrets` | `security_ops` | Regex-based secret scanning |
| `detect_sensitive_files` | `security_ops` | Sensitive file detection |

**Scan severity hierarchy:** critical → high → medium, each with
its own icon (🚨, ⚠️, ℹ️) and color (red, red, yellow).

**Sensitive file dual-check:** Each file gets both a gitignore icon
(✅/❌) and a description of what it is.

---

### `observe.py` — Gitignore + posture (108 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `gitignore(ctx, as_json)` | command | Analyze .gitignore completeness |
| `posture(ctx, as_json)` | command | Unified security posture score |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `gitignore_analysis` | `security_ops` | .gitignore completeness check |
| `security_posture` | `security_ops` | Weighted security scoring |

**Posture visual elements:**
- ASCII progress bar: `█` (filled) + `░` (empty), 40 characters wide
- Grade coloring: A/B → green, C → yellow, D/F → red
- Decorative borders: `═` × 60 for "report card" framing

---

### `generate.py` — Gitignore generation (53 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `generate()` | Click group | `security generate` subgroup |
| `gen_gitignore(ctx, write)` | command (`generate gitignore`) | Generate .gitignore from stacks |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `generate_gitignore` | `security_ops` | .gitignore content generation |
| `write_generated_file` | `docker_ops` | Shared file writer |

---

## Dependency Graph

```
__init__.py
├── click                     ← click.group
├── core.config.loader        ← find_project_file (lazy)
├── core.services.env_ops     ← detect_stacks (lazy, cross-domain)
└── Imports: detect, observe, generate

detect.py
├── click                     ← click.command
└── core.services.security_ops ← scan_secrets, detect_sensitive_files (lazy)

observe.py
├── click                     ← click.command
└── core.services.security_ops ← gitignore_analysis, security_posture (lazy)

generate.py
├── click                     ← click.group, click.command
├── core.services.security_ops ← generate_gitignore (lazy)
└── core.services.docker_ops   ← write_generated_file (lazy)
```

---

## Consumers

### Who registers this CLI group

| Layer | Module | What It Does |
|-------|--------|-------------|
| CLI entry | `src/main.py:459` | `from src.ui.cli.security import security` |

### Who also uses the same core service

| Layer | Module | Core Service Used |
|-------|--------|------------------|
| Web routes | `routes/security_scan/detect.py` | `security.ops` (scan, files) |
| Web routes | `routes/security_scan/actions.py` | `security.ops` (generate) |

---

## Design Decisions

### Why `scan` and `files` are separate commands

Secret scanning (regex on source code) and sensitive file detection
(file path patterns) use different detection strategies and produce
different output structures. Combining them would make the output
confusing.

### Why `posture` is the most visually elaborate command

Security posture is a dashboard-style overview. The visual elements
(ASCII bar, grade card, weighted checks, recommendations) make it
the most informative single command in the entire CLI. It's designed
to be run periodically to track security health.

### Why the gitignore fallback is `["python"]`

The project itself is a Python project. If stack detection fails
(e.g., no `project.yml`), a Python .gitignore is the safest
default — it covers `__pycache__`, `.venv`, `.egg-info`, etc.

### Why `_detect_stack_names` catches all exceptions

Stack detection depends on `env_ops.detect_stacks` which can fail
if the environment detection pipeline has issues. Since stack names
are supplementary (not critical) to security commands, silently
falling back to an empty list is better than crashing.

### Why missing patterns show at most 15

A project using 5+ stacks could have 50+ missing patterns. Showing
all of them floods the terminal. 15 is enough to understand the
scope; `--json` provides the full list.
