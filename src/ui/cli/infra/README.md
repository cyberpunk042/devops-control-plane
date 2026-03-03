# CLI Domain: Infra — Environment Variables & IaC Detection

> **4 files · 364 lines · 10 commands + 2 subgroups · Group: `controlplane infra`**
>
> Two concern areas under one group: `.env` file management (status,
> list vars, diff, validate, and generate .env / .env.example) and
> Infrastructure-as-Code detection (detect Terraform/Pulumi/CDK
> providers and inventory declared resources). A combined `status`
> command merges both perspectives.
>
> Core service: `core/services/env/ops.py` (re-exported via `env_ops.py`)

---

## How It Works

```
┌──────────────────────────────────────────────────────────────────────┐
│                        controlplane infra                           │
│                                                                      │
│  ┌── Combined ─┐   ┌── env subgroup ─────────────┐                 │
│  │ status      │   │ env status                  │                 │
│  └─────────────┘   │ env vars [-f FILE]           │                 │
│                     │ env diff [-s SRC] [-t TGT]  │                 │
│                     │ env validate [-f FILE]       │                 │
│                     │ env generate-example         │                 │
│                     │ env generate-env             │                 │
│                     └─────────────────────────────┘                 │
│                                                                      │
│  ┌── iac subgroup ──────────────────────────────────┐               │
│  │ iac status                                       │               │
│  │ iac resources                                    │               │
│  └──────────────────────────────────────────────────┘               │
└──────────┬─────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    core/services/env/ops.py (via env_ops.py)        │
│                                                                      │
│  Combined:                                                           │
│    infra_status(root)       → env + iac merged status               │
│                                                                      │
│  Env:                                                                │
│    env_status(root)         → .env files, has_env, has_example      │
│    env_vars(root, file, redact) → variables{}, count               │
│    env_diff(root, src, tgt) → missing[], extra[], common[]          │
│    env_validate(root, file) → valid, issues[]                       │
│    generate_env_example(root) → file data                           │
│    generate_env_from_example(root) → file data                      │
│                                                                      │
│  IaC:                                                                │
│    iac_status(root)         → has_iac, providers[]                  │
│    iac_resources(root)      → resources[], count                    │
└──────────────────────────────────────────────────────────────────────┘
```

### Three-Level Structure

This domain has the deepest command hierarchy in the CLI:

```
controlplane infra status              → combined infra status
controlplane infra env status          → .env file detection
controlplane infra env vars            → list variables
controlplane infra env diff            → compare .env files
controlplane infra env validate        → check for issues
controlplane infra env generate-example → create .env.example
controlplane infra env generate-env    → create .env
controlplane infra iac status          → detect IaC providers
controlplane infra iac resources       → inventory resources
```

### Environment File Management

```
.env workflow
├── env status
│   ├── Detect .env and .env.example
│   └── Report presence, variable counts
├── env vars
│   ├── Parse specified .env file (default: .env)
│   ├── Redact values by default (safety)
│   └── --show-values to display actual values
├── env diff
│   ├── Compare source (.env.example) vs target (.env)
│   ├── Find missing vars (in source but not target)
│   ├── Find extra vars (in target but not source)
│   └── Count common vars
├── env validate
│   ├── Parse .env file for syntax/content issues
│   ├── Check: empty values, duplicate keys, quoting
│   └── Report issues with severity + line numbers
├── env generate-example
│   ├── Read .env → strip values → create .env.example
│   └── Preview or --write
└── env generate-env
    ├── Read .env.example → create .env with placeholders
    └── Preview or --write
```

### IaC Detection

```
iac status
├── Scan for IaC configuration files
│   ├── Terraform → *.tf, terraform/ directory
│   ├── Pulumi → Pulumi.yaml
│   ├── AWS CDK → cdk.json
│   └── Others → Ansible, CloudFormation
├── Check CLI availability for each provider
└── Report providers with dirs/files found

iac resources
├── Parse IaC configuration files
├── Extract declared resources
│   ├── Terraform → resource blocks (type/name)
│   ├── Pulumi → resource declarations
│   └── CDK → construct instances
└── Report: provider, type, name, source file
```

---

## Commands

### `controlplane infra status`

Combined environment + IaC status in one view.

```bash
controlplane infra status
controlplane infra status --json
```

**Output example:**

```
🔐 Environment:
   📄 .env (12 vars)
   📄 .env.example (10 vars)

🏗️  Infrastructure as Code:
   ✅ terraform (terraform)
   ❌ pulumi (pulumi)
```

---

### `controlplane infra env status`

Show detected .env files with presence indicators.

```bash
controlplane infra env status
controlplane infra env status --json
```

**Output example:**

```
🔐 Environment Files:
   📄 .env (12 variables)
   📄 .env.example (10 variables)

   ✅ .env present │ ✅ .env.example present
```

---

### `controlplane infra env vars`

List variables in a .env file (values redacted by default).

```bash
controlplane infra env vars
controlplane infra env vars -f .env.production
controlplane infra env vars --show-values
controlplane infra env vars --json
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `-f/--file` | string | `.env` | Which env file to read |
| `--show-values` | flag | off | Show actual values (default: redacted) |
| `--json` | flag | off | JSON output |

**Output example (redacted):**

```
📄 .env (12 variables):
   DATABASE_URL                        ********
   REDIS_URL                           ********
   SECRET_KEY                          ********
```

---

### `controlplane infra env diff`

Compare two .env files to find missing and extra variables.

```bash
controlplane infra env diff
controlplane infra env diff -s .env.production -t .env
controlplane infra env diff --json
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `-s/--source` | string | `.env.example` | Source file |
| `-t/--target` | string | `.env` | Target file |

**Output example:**

```
📊 .env.example ↔ .env:

   ❌ Missing from .env (2):
      STRIPE_KEY
      WEBHOOK_SECRET

   ⚠️  Extra in .env (1):
      DEBUG

   ✅ Common: 10 variables
```

**In-sync output:**

```
✅ .env.example ↔ .env: In sync
```

---

### `controlplane infra env validate`

Validate a .env file for common issues.

```bash
controlplane infra env validate
controlplane infra env validate -f .env.production
controlplane infra env validate --json
```

**Output example:**

```
⚠️  .env: 3 issue(s)
   ⚠️  Line 5: Empty value for DATABASE_URL
   ⚠️  Line 12: Duplicate key: REDIS_URL
   ℹ️  Line 15: Unquoted value with spaces
```

---

### `controlplane infra env generate-example`

Generate .env.example from existing .env (strips values).

```bash
controlplane infra env generate-example
controlplane infra env generate-example --write
```

---

### `controlplane infra env generate-env`

Generate .env from .env.example (creates placeholders).

```bash
controlplane infra env generate-env
controlplane infra env generate-env --write
```

---

### `controlplane infra iac status`

Detect IaC tools and configurations.

```bash
controlplane infra iac status
controlplane infra iac status --json
```

**Output example:**

```
🏗️  IaC Providers:
   ✅ terraform (terraform)
      Dirs: terraform/
      Files: 5 found
   ❌ pulumi (pulumi)
```

---

### `controlplane infra iac resources`

Inventory IaC resources from detected configurations.

```bash
controlplane infra iac resources
controlplane infra iac resources --json
```

**Output example:**

```
📋 IaC Resources (8):
   [terraform] aws_s3_bucket/assets
            File: terraform/storage.tf
   [terraform] aws_rds_instance/db
            File: terraform/database.tf
```

---

## File Map

```
cli/infra/
├── __init__.py     56 lines — group definition, _resolve_project_root,
│                              _handle_generated helper, sub-module imports
├── detect.py       50 lines — combined infra status command
├── env.py         188 lines — env subgroup (status, vars, diff, validate,
│                              generate-example, generate-env)
├── iac.py          70 lines — iac subgroup (status, resources)
└── README.md               — this file
```

**Total: 364 lines of Python across 4 files.**

---

## Per-File Documentation

### `__init__.py` — Group + shared helper (56 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `_resolve_project_root(ctx)` | helper | Reads `config_path` from context, falls back to `find_project_file()` |
| `infra()` | Click group | Top-level `infra` group |
| `_handle_generated(root, file_data, write)` | helper | Preview or write generated file (shared by env generate commands) |
| `from . import env, iac, detect` | import | Registers sub-modules |

**Note on `_handle_generated`:** This helper is defined in `__init__.py`
(not in each sub-module) because both `env generate-example` and
`env generate-env` share the same preview-or-write logic. It imports
`write_generated_file` from `docker_ops` lazily.

---

### `detect.py` — Combined status (50 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `infra_status(ctx, as_json)` | command (`status`) | Combined env + IaC status in one view |

**Core service import (lazy):**

| Import | From | Used For |
|--------|------|----------|
| `infra_status` | `env_ops` | Merged env + IaC detection |

**Note on import aliasing:** The function name `infra_status` conflicts
with the core service name, so the import is aliased: `from ... import
infra_status as _status`.

---

### `env.py` — Environment management (188 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `env()` | Click group | `infra env` subgroup |
| `env_status(ctx, as_json)` | command (`env status`) | Detect .env files, report presence |
| `env_vars(ctx, file, show_values, as_json)` | command (`env vars`) | List variables (redacted by default) |
| `env_diff(ctx, source, target, as_json)` | command (`env diff`) | Compare two .env files |
| `env_validate(ctx, file, as_json)` | command (`env validate`) | Check for syntax/content issues |
| `env_generate_example(ctx, write)` | command (`env generate-example`) | Create .env.example from .env |
| `env_generate_env(ctx, write)` | command (`env generate-env`) | Create .env from .env.example |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `env_status` | `env_ops` | .env file detection |
| `env_vars` | `env_ops` | Variable listing with redaction |
| `env_diff` | `env_ops` | .env file comparison |
| `env_validate` | `env_ops` | .env syntax validation |
| `generate_env_example` | `env_ops` | .env → .env.example conversion |
| `generate_env_from_example` | `env_ops` | .env.example → .env conversion |
| `write_generated_file` | `docker_ops` | File writer (via `_handle_generated`) |

**Security note:** `env vars` redacts values by default. The
`--show-values` flag must be explicitly passed to see actual values.
This prevents accidental exposure of secrets in terminal logs.

---

### `iac.py` — IaC detection (70 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `iac()` | Click group | `infra iac` subgroup |
| `iac_status(ctx, as_json)` | command (`iac status`) | Detect IaC providers + CLI availability |
| `iac_resources(ctx, as_json)` | command (`iac resources`) | Inventory declared IaC resources |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `iac_status` | `env_ops` | IaC provider detection |
| `iac_resources` | `env_ops` | Resource inventory from config files |

---

## Dependency Graph

```
__init__.py
├── click                     ← click.group
├── core.config.loader        ← find_project_file (lazy)
├── core.services.docker_ops  ← write_generated_file (lazy, _handle_generated)
└── Imports: env, iac, detect

detect.py
├── click                     ← click.command
└── core.services.env_ops     ← infra_status (lazy)

env.py
├── click                     ← click.group, click.command
├── core.services.env_ops     ← env_status, env_vars, env_diff,
│                                env_validate, generate_env_example,
│                                generate_env_from_example (all lazy)
└── (via _handle_generated)   ← docker_ops.write_generated_file

iac.py
├── click                     ← click.group, click.command
└── core.services.env_ops     ← iac_status, iac_resources (all lazy)
```

---

## Consumers

### Who registers this CLI group

| Layer | Module | What It Does |
|-------|--------|-------------|
| CLI entry | `src/main.py:456` | `from src.ui.cli.infra import infra` |

### Who also uses the same core service

| Layer | Module | Core Service Used |
|-------|--------|------------------|
| Web routes | `routes/infra/env.py` | `env_ops` (env status, vars, diff, validate) |
| Web routes | `routes/infra/iac.py` | `env_ops` (IaC status, resources) |
| CLI | `cli/security/__init__.py:33` | `env_ops.detect_stacks` (stack detection for security) |

---

## Design Decisions

### Why env and iac are subgroups (not flat commands)

Environment and IaC are distinct concerns with different audiences.
A devops engineer managing secrets cares about `env vars` and `env diff`.
An infrastructure architect cares about `iac resources`. Subgroups
keep these concerns separated while co-locating under `infra`.

### Why there's a combined `infra status` AND separate `env status` / `iac status`

The combined `infra status` is the quick overview ("what do I have?").
The separate `env status` shows env-specific details (`.env` vs
`.env.example` presence markers). The separate `iac status` shows
provider-specific details (directories, file counts, CLI versions).

### Why `env vars` redacts by default

`.env` files contain secrets (database passwords, API keys). Showing
them in CLI output creates security risks (terminal logs, screen
sharing, shoulder surfing). Redacting by default follows the principle
of least privilege.

### Why `generate-example` and `generate-env` are symmetric

Users need to go both directions: create `.env.example` for team
sharing (strip values from `.env`) and create `.env` from `.env.example`
when setting up a new environment (fill in placeholders).

### Why all IaC and env operations share one core service

Environment detection and IaC detection often need the same project
scanning. Keeping them in a single `env_ops.py` (with clear function
naming) avoids duplicate project-root scanning and file discovery.
