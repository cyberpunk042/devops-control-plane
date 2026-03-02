# Environment & Infrastructure Domain

> **3 files · 688 lines · Environment variables + Infrastructure as Code detection.**
>
> Two related concerns in one domain: (1) `.env` file detection, parsing,
> comparison, validation, and generation, and (2) IaC provider detection
> (Terraform, Kubernetes, Pulumi, CloudFormation, Ansible) with resource
> inventory. Both feed the DevOps dashboard environment card — a single
> aggregated view of project environments, vault state, and GitHub sync.

---

## How It Works

### Architecture Overview

```
┌────────────────────────────────────────────────────────────────────┐
│ Two layers in one domain                                            │
│                                                                      │
│  Layer 1: Environment Variables (ops.py)                            │
│  ──────────────────────────────────────────                         │
│  Detect .env files → parse key=value → diff → validate → generate  │
│                                                                      │
│  Layer 2: Infrastructure as Code (infra_ops.py)                     │
│  ──────────────────────────────────────────                         │
│  Detect IaC providers → inventory resources → aggregate for card    │
│                                                                      │
│  Both follow the Detect → Observe → Facilitate → Act pattern.       │
└────────────────────────────────────────────────────────────────────┘
```

### Environment Variable Pipeline

```
env_status(root)
     │
     ├── Load file variants from DataRegistry:
     │     └── _env_files() → [".env", ".env.example", ".env.local",
     │                          ".env.development", ".env.staging",
     │                          ".env.production", ".env.test",
     │                          ".env.sample", ".env.template"]
     │
     ├── For each file in variants:
     │     ├── Check existence on disk
     │     ├── Parse with _parse_env_file() → {key: value}
     │     ├── Count variables
     │     └── Record {name, exists: True, var_count}
     │
     ├── Determine flags:
     │     ├── has_env = ".env" found
     │     └── has_example = ".env.example" | ".env.sample" | ".env.template" found
     │
     └── Return {files, has_env, has_example, total_vars}
```

### Environment Diff

```
env_diff(root, source=".env.example", target=".env")
     │
     ├── Parse source file → set of keys
     ├── Parse target file → set of keys
     │
     ├── Compute:
     │     ├── missing = source_keys - target_keys  (vars you need to add)
     │     ├── extra   = target_keys - source_keys  (vars not in template)
     │     └── common  = source_keys ∩ target_keys  (vars in both)
     │
     └── Return {ok, source, target, missing, extra, common, in_sync}
```

### Environment Validation

```
env_validate(root, file=".env")
     │
     ├── Read file line-by-line
     │
     ├── For each non-blank, non-comment line:
     │     ├── Strip optional 'export ' prefix
     │     │
     │     ├── Check: has '=' separator?
     │     │     └── No → warning: "No '=' found"
     │     │
     │     ├── Check: duplicate key?
     │     │     └── Yes → warning: "Duplicate key 'X' (first at line N)"
     │     │
     │     ├── Check: empty value?
     │     │     └── Yes → info: "Empty value for 'X'"
     │     │
     │     ├── Check: placeholder value?
     │     │     └── Patterns: your_, changeme, xxx, todo, fixme,
     │     │                    replace, example, placeholder, <, >
     │     │     └── Match → warning: "Possible placeholder value for 'X'"
     │     │
     │     └── Check: unquoted value with spaces?
     │           └── Yes → warning: "Unquoted value with spaces for 'X'"
     │
     └── Return {ok, file, issues, issue_count, valid}
```

### IaC Provider Detection

```
iac_status(root)
     │
     ├── Load provider catalog from DataRegistry:
     │     └── _iac_providers() → {terraform: {...}, kubernetes: {...}, ...}
     │
     ├── For each provider in catalog:
     │     ├── Scan for marker files (e.g., main.tf, Chart.yaml)
     │     │     └── Glob patterns: "*.tf", "*.yaml" in specific dirs
     │     │
     │     ├── Scan for marker directories (e.g., k8s/, manifests/)
     │     │     └── Also scan files within: *.yml, *.yaml, *.tf, *.json
     │     │
     │     ├── Check CLI availability:
     │     │     └── shutil.which(spec["cli"])
     │     │
     │     └── If files or dirs found → record provider:
     │           {id, name, cli, cli_available, files_found, dirs_found}
     │
     └── Return {providers, has_iac}
```

### IaC Resource Inventory

```
iac_resources(root)
     │
     ├── Terraform resources:
     │     ├── Glob **/*.tf (skip .terraform/)
     │     ├── Regex: resource "type" "name" { ... }
     │     └── Record {provider: "terraform", type, name, file}
     │
     ├── Kubernetes resources:
     │     ├── Search dirs: k8s/, kubernetes/, manifests/, deploy/
     │     ├── Glob **/*.y*ml in each dir
     │     ├── Parse YAML (safe_load_all for multi-doc)
     │     └── Record {provider: "kubernetes", type: kind, name, file}
     │
     └── Return {resources, count}
```

### Environment Card Aggregation

This is the most complex function — it assembles everything the
dashboard environment card needs in a single API call:

```
env_card_status(root)
     │
     ├── 1. Project environments
     │     ├── find_project_file(root) → project.yml path
     │     ├── load_project(path) → project config
     │     └── Extract: [{name, default}, ...] from config.environments
     │
     ├── 2. Active environment
     │     └── vault_env_ops.read_active_env(root)
     │
     ├── 3. GitHub environments
     │     └── secrets_ops.list_environments(root)
     │           → {available, reason, environments: [names]}
     │
     ├── 4. Per-env GitHub secrets
     │     └── For each env (if GH available):
     │           └── secrets_ops.list_gh_secrets(root, env_name)
     │                 → {secrets: [names], variables: [names]}
     │
     ├── 5. Per-env vault state + local key counts
     │     └── For each env:
     │           ├── Resolve .env path:
     │           │     ├── Active env → .env
     │           │     └── Other env → .env.{name}
     │           │
     │           ├── Determine vault_state:
     │           │     ├── .env exists        → "unlocked"
     │           │     ├── .env.vault exists  → "locked"
     │           │     └── neither            → "empty"
     │           │
     │           ├── Count local keys:
     │           │     └── vault_io.list_env_keys(env_path)
     │           │
     │           └── Compute sync status:
     │                 ├── local_only = local_keys - gh_keys
     │                 ├── gh_only    = gh_keys - local_keys
     │                 └── in_sync    = (both empty)
     │
     ├── 6. .env file inventory
     │     └── env_status(root) → {files, has_env, total_vars}
     │
     └── Return {environments, active, github, env_files,
                  has_env, total_vars}
```

---

## Architecture

```
                Routes (infra/)
                CLI (infra/)
                Metrics (probes)
                Audit (l2_risk.py)
                        │
                        │ imports
                        │
             ┌──────────▼──────────────────────────────┐
             │  env/__init__.py                          │
             │  Public API — re-exports 6 functions      │
             │  env_status · env_diff                     │
             │  iac_status · iac_resources                │
             │  infra_status · env_card_status            │
             └──────────┬───────────────────────────────┘
                        │
               ┌────────┴────────┐
               │                 │
               ▼                 ▼
            ops.py          infra_ops.py
            (.env files:      (IaC providers:
             status,           detection,
             diff,             resources,
             validate,         combined,
             generate)         card aggregation)
                │                 │
                │                 ├── project config (loader)
                │                 ├── vault (vault_env_ops, vault_io)
                │                 ├── secrets (secrets_ops)
                │                 └── DataRegistry (iac_providers)
                │
                └── DataRegistry (env_files)

             env_ops.py — backward-compat shim
             env_infra_ops.py — backward-compat shim
```

### Dependency Rules

| Rule | Detail |
|------|--------|
| `ops.py` is standalone | Only pathlib, re, DataRegistry |
| `infra_ops.py` imports from `ops.py` | One-way: `env_status()` for card |
| `infra_ops.py` imports cross-domain | vault, secrets, config loader — all lazy |
| `ops.py` uses audit helpers | `make_auditor("env")` for audit logging |
| Both use DataRegistry | `env_files`, `iac_providers` from catalog |

---

## File Map

```
env/
├── __init__.py        7 lines   — public API re-exports
├── ops.py           393 lines   — .env detection, diff, validate, generate
├── infra_ops.py     288 lines   — IaC providers, resources, card aggregation
└── README.md                    — this file
```

---

## Per-File Documentation

### `ops.py` — Environment Variables (393 lines)

Follows the Detect → Observe → Facilitate pattern for `.env` files.

**Private helpers:**

| Function | What It Does |
|----------|-------------|
| `_env_files()` | Load env file variant names from DataRegistry |
| `_parse_env_file(path)` | Parse `.env` into `{key: value}` dict |
| `_redact_value(value)` | Redact sensitive values: `"ab****yz"` |

**Public API — Detect:**

| Function | What It Does |
|----------|-------------|
| `env_status(root)` | Detect all `.env` files with variable counts |

**Public API — Observe:**

| Function | What It Does |
|----------|-------------|
| `env_vars(root, *, file, redact)` | List variables in a `.env` file (optionally redacted) |
| `env_diff(root, *, source, target)` | Compare two `.env` files — missing, extra, common |
| `env_validate(root, *, file)` | Validate `.env` for common issues |

**Public API — Facilitate:**

| Function | What It Does |
|----------|-------------|
| `generate_env_example(root)` | Generate `.env.example` from `.env` (redacted, grouped by prefix) |
| `generate_env_from_example(root)` | Generate `.env` from `.env.example` (copy with placeholders) |

### `infra_ops.py` — Infrastructure as Code (288 lines)

Handles IaC provider detection and the dashboard environment card.

**Private helpers:**

| Function | What It Does |
|----------|-------------|
| `_iac_providers()` | Load IaC provider catalog from DataRegistry |

**Public API:**

| Function | What It Does |
|----------|-------------|
| `iac_status(root)` | Detect IaC providers with CLI and file checks |
| `iac_resources(root)` | Inventory Terraform resources + K8s manifests |
| `infra_status(root)` | Combined env + IaC status in one call |
| `env_card_status(root)` | Full dashboard card data (envs + vault + GH + sync) |

---

## Key Data Shapes

### env_status response

```python
{
    "files": [
        {"name": ".env", "exists": True, "var_count": 12},
        {"name": ".env.example", "exists": True, "var_count": 15},
    ],
    "has_env": True,
    "has_example": True,
    "total_vars": 27,
}
```

### env_diff response

```python
{
    "ok": True,
    "source": ".env.example",
    "target": ".env",
    "missing": ["REDIS_URL", "SENTRY_DSN"],     # in example but not .env
    "extra": ["DEBUG", "LOCAL_SECRET"],            # in .env but not example
    "common": ["DATABASE_URL", "API_KEY", ...],   # in both
    "in_sync": False,
}
```

### env_validate response

```python
{
    "ok": True,
    "file": ".env",
    "issues": [
        {"line": 3, "severity": "warning", "message": "Duplicate key 'API_KEY' (first at line 1)"},
        {"line": 7, "severity": "info", "message": "Empty value for 'REDIS_URL'"},
        {"line": 12, "severity": "warning", "message": "Possible placeholder value for 'SECRET'"},
    ],
    "issue_count": 3,
    "valid": False,  # True only when zero warnings
}
```

### env_card_status response

```python
{
    "environments": [
        {
            "name": "production",
            "default": True,
            "active": True,
            "vault_state": "unlocked",  # "unlocked" | "locked" | "empty"
            "local_keys": 12,
            "gh_secrets": 8,
            "gh_variables": 3,
            "local_only": ["LOCAL_SECRET"],      # keys not on GitHub
            "gh_only": ["DEPLOY_KEY"],             # keys not locally
            "in_sync": False,                      # local_only + gh_only both empty?
            "on_github": True,                     # GH deployment env exists?
        },
        {
            "name": "staging",
            "default": False,
            "active": False,
            "vault_state": "locked",
            "local_keys": 10,
            ...
        },
    ],
    "active": "production",
    "github": {"available": True, "reason": None},
    "env_files": [{"name": ".env", "exists": True, "var_count": 12}, ...],
    "has_env": True,
    "total_vars": 27,
}
```

### iac_status response

```python
{
    "providers": [
        {
            "id": "terraform",
            "name": "Terraform",
            "cli": "terraform",
            "cli_available": True,
            "files_found": ["main.tf", "variables.tf", "outputs.tf"],
            "dirs_found": [],
        },
        {
            "id": "kubernetes",
            "name": "Kubernetes",
            "cli": "kubectl",
            "cli_available": True,
            "files_found": ["k8s/deployment.yaml", "k8s/service.yaml"],
            "dirs_found": ["k8s"],
        },
    ],
    "has_iac": True,
}
```

### iac_resources response

```python
{
    "resources": [
        {"provider": "terraform", "type": "aws_instance", "name": "web", "file": "main.tf"},
        {"provider": "terraform", "type": "aws_s3_bucket", "name": "assets", "file": "storage.tf"},
        {"provider": "kubernetes", "type": "Deployment", "name": "api", "file": "k8s/deployment.yaml"},
        {"provider": "kubernetes", "type": "Service", "name": "api-svc", "file": "k8s/service.yaml"},
    ],
    "count": 4,
}
```

---

## .env Parser Rules

The `_parse_env_file()` function handles these formats:

```bash
# Standard key=value
DATABASE_URL=postgres://localhost/mydb

# Quoted values (single or double)
API_KEY="sk-123456789"
SECRET='my_secret_value'

# export prefix (stripped)
export NODE_ENV=production

# Comments (ignored)
# This is a comment

# Empty lines (ignored)

# Values with spaces (must be quoted for validation)
GREETING="Hello World"
```

**Parser behavior:**

| Input | Parsed Key | Parsed Value |
|-------|-----------|-------------|
| `KEY=value` | `KEY` | `value` |
| `KEY="value"` | `KEY` | `value` (quotes stripped) |
| `KEY='value'` | `KEY` | `value` (quotes stripped) |
| `export KEY=value` | `KEY` | `value` (`export` stripped) |
| `KEY=` | `KEY` | `""` (empty string) |
| `# comment` | *(skipped)* | *(skipped)* |
| *(empty line)* | *(skipped)* | *(skipped)* |
| `no_equals_sign` | *(skipped)* | *(skipped)* |

---

## IaC Provider Catalog

Loaded from DataRegistry via `_iac_providers()`:

| Provider | CLI | Marker Files | Marker Directories |
|----------|-----|-------------|-------------------|
| **Terraform** | `terraform` | `*.tf`, `terraform.tfvars` | — |
| **Kubernetes** | `kubectl` | — | `k8s/`, `kubernetes/`, `manifests/`, `deploy/` |
| **Pulumi** | `pulumi` | `Pulumi.yaml`, `Pulumi.*.yaml` | — |
| **CloudFormation** | `aws` | `template.yaml`, `template.json` | `cloudformation/` |
| **Ansible** | `ansible` | `ansible.cfg`, `playbook.yml` | `roles/`, `playbooks/` |

Each detected provider reports:
- Whether the CLI tool is installed
- Which files were found (capped at 20)
- Which directories were found

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| **Routes** | `routes/infra/env.py` | `env_status`, `env_diff`, `env_vars`, `env_validate`, `generate_env_example`, `generate_env_from_example` |
| **Routes** | `routes/infra/iac.py` | `iac_status`, `iac_resources`, `infra_status`, `env_card_status` |
| **CLI** | `cli/infra/env.py` | `env_status`, `env_diff` |
| **CLI** | `cli/infra/iac.py` | `iac_status` |
| **CLI** | `cli/infra/detect.py` | `env_status` |
| **CLI** | `cli/security/__init__.py` | `env_status` |
| **Metrics** | `metrics/ops.py` | `env_status`, `env_diff` |
| **Audit** | `audit/l2_risk.py` | `env_status`, `env_diff` |
| **Wizard** | `wizard/helpers.py` | `env_status` |
| **Vault** | `vault_env_ops.py` | *(reads same .env files)* |
| **Secrets** | `secrets_ops.py`, `secrets_env_ops.py` | *(reads same .env files)* |
| **Shims** | `env_ops.py` | Backward-compat re-export of `ops.py` |
| **Shims** | `env_infra_ops.py` | Backward-compat re-export of `infra_ops.py` |

---

## Dependency Graph

```
ops.py                            ← standalone (pathlib, subprocess, DataRegistry)
   │                                  make_auditor("env") for audit logging
   │
   └── DataRegistry.env_files     ← file variant names
   
infra_ops.py                      ← imports env_status from ops.py
   │
   ├── ops.env_status             ← .env file detection (for card)
   ├── config.loader              ← project.yml environments
   ├── vault_env_ops              ← active environment
   ├── vault_io                   ← list_env_keys (local key count)
   ├── secrets_ops                ← GitHub environments + secrets
   └── DataRegistry.iac_providers ← provider catalog
```

Key: `infra_ops.py` is the "aggregator" — it reaches into vault,
secrets, and config to build the complete environment card. All
cross-domain imports happen inside `env_card_status()`, not at
module level, preventing import-time circular dependencies.

---

## Placeholder Patterns

The `env_validate` function detects placeholder values using
these patterns (case-insensitive):

```
your_          →  "your_api_key_here"
changeme       →  "changeme"
xxx            →  "xxx-xxx-xxx"
todo           →  "TODO: fill in"
fixme          →  "FIXME"
replace        →  "replace_with_real_value"
example        →  "example.com"
placeholder    →  "placeholder"
<              →  "<your-token>"
>              →  "<your-token>"
```

---

## Value Redaction

The `_redact_value()` function protects sensitive values:

| Input | Output |
|-------|--------|
| `""` | `(empty)` |
| `"ab"` | `****` |
| `"abcd"` | `****` |
| `"abcde"` | `ab****de` |
| `"sk-123456789"` | `sk****89` |

Rule: values ≤ 4 characters → full redact. Longer values →
show first 2 + last 2 characters with `****` in between.

---

## Generated File Outputs

### generate_env_example

```bash
# Environment variables
# Copy to .env and fill in values
#
# Generated from .env (12 variables)

# ── API ──
API_KEY=
API_SECRET=

# ── DATABASE ──
DATABASE_HOST=
DATABASE_NAME=
DATABASE_PASSWORD=
DATABASE_URL=
DATABASE_USER=

# ── REDIS ──
REDIS_URL=
```

Variables are sorted alphabetically and grouped by underscore
prefix. Values are stripped (`.env.example` only has keys).

### generate_env_from_example

Copies `.env.example` (or `.env.sample`, `.env.template`) verbatim
to `.env`. The `overwrite: False` flag prevents overwriting an
existing `.env` file.

---

## Backward Compatibility

Two shim files remain at the services root:

```python
# env_ops.py
from src.core.services.env.ops import *  # noqa

# env_infra_ops.py
from src.core.services.env.infra_ops import *  # noqa
```

These shims allow old import paths to continue working
during the migration to the package structure.

---

## Advanced Feature Showcase

### 1. Quote-Aware .env Parser — Three Quoting Styles in One Pass

The parser handles unquoted, double-quoted, and single-quoted values:

```python
# ops.py — _parse_env_file (lines 61-83)

for line in content.splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue

    # Strip optional 'export'
    if line.startswith("export "):
        line = line[7:].strip()

    if "=" not in line:
        continue

    key, _, value = line.partition("=")
    key = key.strip()
    value = value.strip()

    # Remove surrounding quotes
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        value = value[1:-1]

    result[key] = value
```

The quote detection `value[0] == value[-1] and value[0] in ('"', "'")`
ensures only *matching* quotes are stripped. `"hello'` is kept as-is
because the first and last characters differ. The `len(value) >= 2`
guard prevents index errors on single-character values. The `partition("=")`
ensures only the *first* `=` splits the line — values like
`DATABASE_URL=postgres://host?opt=1` preserve everything after the first `=`.

### 2. Length-Adaptive Value Redaction — Protecting Short Secrets

Redaction adapts to value length:

```python
# ops.py — _redact_value (lines 86-92)

def _redact_value(value: str) -> str:
    if not value:
        return "(empty)"
    if len(value) <= 4:
        return "****"
    return value[:2] + "****" + value[-2:]
```

Transform examples:
| Input | Length | Output | Reason |
|-------|--------|--------|--------|
| `""` | 0 | `(empty)` | Distinguish empty from redacted |
| `"ab"` | 2 | `****` | Too short — any hint leaks the value |
| `"abcd"` | 4 | `****` | Still too short — 4 chars visible = full value |
| `"abcde"` | 5 | `ab****de` | Long enough — first 2 + last 2 are safe hints |
| `"sk-123456789"` | 13 | `sk****89` | Typical API key — hints help identify which key |

The threshold of 4 is deliberate: showing first-2 + last-2 of a 4-char
value would expose the entire secret. Only values of 5+ characters get
the hint format.

### 3. Prefix-Grouped Example Generation — Automatic Categorization

Generated `.env.example` files are automatically organized by prefix:

```python
# ops.py — generate_env_example (lines 326-336)

current_prefix = ""
for key in sorted(parsed.keys()):
    prefix = key.split("_")[0] if "_" in key else ""
    if prefix != current_prefix and prefix:
        lines.append(f"\n# ── {prefix} ──")
        current_prefix = prefix

    lines.append(f"{key}=")
```

For keys `API_KEY, API_SECRET, DATABASE_URL, DATABASE_HOST, REDIS_URL`:
- First sorted: `API_KEY, API_SECRET, DATABASE_HOST, DATABASE_URL, REDIS_URL`
- Prefix changes: `API` → insert `# ── API ──`, then `DATABASE` → insert
  `# ── DATABASE ──`, then `REDIS` → insert `# ── REDIS ──`
- Result: three visually distinct groups with comment headers

Keys without underscores (`PORT`, `DEBUG`) get no group header — the
`if "_" in key else ""` clause returns empty prefix, and the
`if prefix != current_prefix and prefix` guard suppresses empty headers.

### 4. Multi-Format Example Fallback — Three Template Sources

When generating `.env` from a template, three file names are tried:

```python
# ops.py — generate_env_from_example (lines 356-365)

example_path = None
for name in (".env.example", ".env.sample", ".env.template"):
    p = project_root / name
    if p.is_file():
        example_path = p
        break

if not example_path:
    return {"error": "No .env.example/.env.sample/.env.template found"}
```

Different ecosystems use different conventions:
- Node.js projects typically use `.env.example`
- Ruby/Rails projects often use `.env.sample`
- Enterprise projects may use `.env.template`

The fallback order prioritizes the most common convention. The `break`
after the first match ensures deterministic behavior — if both
`.env.example` and `.env.sample` exist, the former wins.

### 5. Three-State Vault Resolution — File-Based State Machine

Environment vault state is determined purely by file existence:

```python
# infra_ops.py — env_card_status (lines 230-243)

# Resolve .env file path for this environment
if is_active:
    env_path = project_root / ".env"
else:
    env_path = project_root / f".env.{name}"

vault_path = env_path.with_suffix(env_path.suffix + ".vault")

# Vault state
if env_path.exists():
    vault_state = "unlocked"
elif vault_path.exists():
    vault_state = "locked"
else:
    vault_state = "empty"
```

State transitions:
- `encrypt` → `.env` disappears, `.env.vault` appears → `"locked"`
- `decrypt` → `.env.vault` decrypted to `.env` → `"unlocked"`
- `delete` → both gone → `"empty"`

The path naming convention `env_path.with_suffix(env_path.suffix + ".vault")`
appends `.vault` to the *existing* suffix: `.env` → `.env.vault`,
`.env.staging` → `.env.staging.vault`.

### 6. Bidirectional GitHub Sync Diff — Local vs Cloud Comparison

Sync status compares local vault keys against GitHub secrets + variables:

```python
# infra_ops.py — env_card_status (lines 250-258)

gh_info = gh_secrets_cache.get(name, {})
gh_secret_names = set(gh_info.get("secrets", []))
gh_var_names = set(gh_info.get("variables", []))
gh_all = gh_secret_names | gh_var_names

local_only = sorted(local_key_names - gh_all) if gh_data.get("available") else []
gh_only = sorted(gh_all - local_key_names) if gh_data.get("available") else []
in_sync = (not local_only and not gh_only) if gh_data.get("available") else None
```

Three sync outcomes:
- **`local_only`**: keys in vault but not on GitHub → need `push`
- **`gh_only`**: keys on GitHub but not locally → need `pull`
- **`in_sync`**: both lists empty → fully synchronized

The `if gh_data.get("available")` guard returns empty lists / `None`
when GitHub API is unavailable (no token, rate limited), preventing
false "out of sync" warnings. The `gh_all = secrets | variables`
union treats both GitHub secrets and variables as the "remote" set,
since a local key might be stored as either.

### 7. Terraform `.terraform` Skip Guard — Vendor Directory Exclusion

IaC resource scanning skips the Terraform cache directory:

```python
# infra_ops.py — iac_resources (lines 101-103)

for tf_file in project_root.glob("**/*.tf"):
    if ".terraform" in str(tf_file):
        continue
```

Terraform downloads provider plugins and module sources into
`.terraform/`. These contain `.tf` files that are *not* user-authored
resources but vendor code. Without this guard, the resource inventory
would be polluted with hundreds of provider schema files. The string
match `".terraform" in str(tf_file)` is intentionally broad — it
catches both `.terraform/` at root and nested `.terraform/` within
module directories.

---

### Feature Coverage Summary

| Feature | Where | Complexity |
|---------|-------|-----------|
| Quote-aware .env parsing | `ops.py` `_parse_env_file` | Matching quote detection + partition split |
| Length-adaptive redaction | `ops.py` `_redact_value` | Threshold-based format switching |
| Prefix-grouped example generation | `ops.py` `generate_env_example` | Underscore prefix extraction + sort |
| Multi-format example fallback | `ops.py` `generate_env_from_example` | Three-name template search |
| Three-state vault resolution | `infra_ops.py` `env_card_status` | File existence → state machine |
| Bidirectional GitHub sync diff | `infra_ops.py` `env_card_status` | Set operations on local vs cloud keys |
| Terraform vendor skip guard | `infra_ops.py` `iac_resources` | String filter on `.terraform` paths |

---

## Design Decisions

### Why two files (ops.py + infra_ops.py)?

`ops.py` handles pure `.env` file operations — no external
dependencies beyond pathlib and DataRegistry. `infra_ops.py`
aggregates data from 4 different services (vault, secrets,
config loader, env ops) to build the dashboard card. Keeping
them separate means `env_status()` and `env_diff()` can be
imported without pulling in vault/secrets dependencies.

### Why DataRegistry for file variants?

The list of `.env` file names (`.env`, `.env.example`,
`.env.local`, `.env.staging`, etc.) is configurable per project
type. A Node.js project might use `.env.development` while a
Python project uses `.env.local`. DataRegistry makes this
configurable without code changes.

### Why regex for Terraform resource parsing?

Full HCL parsing requires a dedicated parser library. The regex
`resource "type" "name"` catches 99% of resource declarations
and runs in milliseconds. The trade-off (missing nested modules
or dynamic blocks) is acceptable for an inventory overview.

### Why YAML safe_load_all for Kubernetes?

Kubernetes manifests often contain multiple documents separated
by `---` in a single file. `yaml.safe_load()` would only parse
the first document. `safe_load_all()` yields all documents,
ensuring the resource inventory captures every manifest.

### Why does env_card_status cross domain boundaries?

The environment card in the dashboard needs data from 4 sources:
project config (environments), vault (lock state), secrets
(GitHub sync), and env ops (.env files). Rather than making the
frontend issue 4 separate API calls and correlate the results,
`env_card_status()` does it server-side in one call. This keeps
the UI simple and reduces network round-trips.

### Why vault_state as a string enum?

Three possible states: `"unlocked"` (`.env` exists, secrets
readable), `"locked"` (`.env.vault` exists, needs decryption),
`"empty"` (neither file exists, environment not configured).
A string enum is self-documenting and avoids boolean ambiguity
(`is_locked=False` could mean "unlocked" or "doesn't exist").

### Why are cross-domain imports inside env_card_status()?

Importing vault, secrets, and config at module level would
create circular dependencies (vault imports env, env imports
vault). Lazy imports inside the function body break the cycle
and ensure the env module can be imported standalone for its
simpler operations (status, diff, validate).
