# CLI Domain: Terraform — Status, Validate, Plan, State & Generation

> **4 files · 326 lines · 7 commands · Group: `controlplane terraform`**
>
> Terraform lifecycle: detect Terraform configuration and CLI availability,
> validate syntax, run dry-run plans with resource change summaries,
> inspect state and workspaces, and generate scaffolding (main.tf,
> variables.tf, outputs.tf) for multiple cloud providers.
>
> Core service: `core/services/terraform/ops.py` (re-exported via
> `terraform_ops.py`)

---

## How It Works

```
┌──────────────────────────────────────────────────────────────────────┐
│                      controlplane terraform                         │
│                                                                      │
│  ┌── Detect ──┐  ┌── Observe ────────────┐  ┌── Generate ────────┐ │
│  │ status     │  │ validate              │  │ generate           │ │
│  └────────────┘  │ plan                  │  │  --provider aws    │ │
│                   │ state                 │  │  --backend s3      │ │
│                   │ workspaces            │  │  --project-name    │ │
│                   └───────────────────────┘  └────────────────────┘ │
└──────────┬──────────────────────┬──────────────────┬──────────────┘
           │                      │                  │
           ▼                      ▼                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  core/services/terraform/ops.py                     │
│                                                                      │
│  terraform_status(root)     → cli, has_terraform, root, initialized │
│                                files[], providers[], modules[],     │
│                                resources[], backend                 │
│  terraform_validate(root)   → valid, errors[]                      │
│  terraform_plan(root)       → changes{add, change, destroy}        │
│  terraform_state(root)      → resources[], count                   │
│  terraform_workspaces(root) → workspaces[], current                │
│  generate_terraform(root, provider, backend, name) → files[]       │
└──────────────────────────────────────────────────────────────────────┘
```

### Detection and Status

The `status` command provides a comprehensive view of the Terraform
configuration:

```
terraform_status(root)
├── Check CLI availability (terraform version)
├── Find Terraform root (directory with *.tf files)
├── Check initialization (.terraform/ directory)
├── Parse *.tf files:
│   ├── Extract file types (main, variables, outputs, modules)
│   ├── Extract declared providers
│   ├── Extract declared modules (name → source)
│   ├── Extract declared resources (type.name → file)
│   └── Extract backend configuration
└── Return: comprehensive status object
```

### Plan Change Summary

The `plan` command wraps `terraform plan` and extracts a change summary:

```
plan → changes
├── add:     resources to create    (green ➕)
├── change:  resources to modify    (yellow 🔄)
├── destroy: resources to destroy   (red 🗑️)
└── total = 0 → "No changes. Infrastructure is up-to-date."
```

### Multi-File Generation

Like K8s manifests, `generate` produces **multiple files** in one
operation:

```
generate --provider aws --backend s3 --project-name myapp
├── terraform/main.tf        → provider + backend config
├── terraform/variables.tf   → common input variables
├── terraform/outputs.tf     → output definitions
└── (preview or --write)
```

---

## Commands

### `controlplane terraform status`

Show Terraform configuration status.

```bash
controlplane terraform status
controlplane terraform status --json
```

**Output example:**

```
🏗️  Terraform Status:

   🔧 CLI: v1.7.0
   📁 Root: terraform/
   📋 Initialized: ✅

   📄 Files (4):
      terraform/main.tf                  [main]
      terraform/variables.tf             [variables]
      terraform/outputs.tf               [outputs]
      terraform/networking.tf            [main]

   🔌 Providers: aws, random

   📦 Modules (2):
      vpc                            → terraform-aws-modules/vpc/aws
      ecs                            → terraform-aws-modules/ecs/aws

   🏗️  Resources (8):
      aws_s3_bucket.assets                   [main.tf]
      aws_rds_instance.db                    [main.tf]
      aws_ecs_service.app                    [main.tf]
      ...and 5 more

   💾 Backend: s3 (main.tf)
```

**No Terraform detected:**

```
🏗️  Terraform Status:

   🔧 CLI: v1.7.0

   📁 No Terraform configuration found

   💡 Generate: controlplane terraform generate --provider aws
```

---

### `controlplane terraform validate`

Validate Terraform configuration syntax.

```bash
controlplane terraform validate
controlplane terraform validate --json
```

**Output examples:**

```
🔍 Validating Terraform...
✅ Configuration is valid
```

```
🔍 Validating Terraform...
❌ Configuration has errors
   ❌ [error] Missing required attribute "region"
      Expected in provider "aws" block
   ⚠️  [warning] Deprecated attribute "instance_count"
      Use "desired_count" instead
```

---

### `controlplane terraform plan`

Run terraform plan (dry-run).

```bash
controlplane terraform plan
controlplane terraform plan --json
```

**Output examples:**

```
📋 Running terraform plan...
✅ No changes. Infrastructure is up-to-date.
```

```
📋 Running terraform plan...
📋 Plan: 2 to add, 1 to change, 0 to destroy
      ➕ 2 to add
      🔄 1 to change
```

---

### `controlplane terraform state`

List resources in terraform state.

```bash
controlplane terraform state
controlplane terraform state --json
```

**Output example:**

```
📋 State (5 resources):
   aws_s3_bucket.assets
   aws_rds_instance.db
   [module.vpc] aws_vpc.this
   [module.vpc] aws_subnet.public
   aws_ecs_service.app
```

**Module prefix:** Resources inside modules show `[module.name]` prefix.

---

### `controlplane terraform workspaces`

List terraform workspaces.

```bash
controlplane terraform workspaces
controlplane terraform workspaces --json
```

**Output example:**

```
🏗️  Workspaces (current: production):
   ▶ production
     staging
     development
```

---

### `controlplane terraform generate`

Generate Terraform scaffolding (main.tf, variables.tf, outputs.tf).

```bash
controlplane terraform generate
controlplane terraform generate --provider aws --backend s3
controlplane terraform generate --provider google --project-name myapp --write
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--provider` | string | aws | Cloud provider (aws, google, azurerm, digitalocean) |
| `--backend` | string | local | Backend type (s3, gcs, azurerm, local) |
| `--project-name` | string | (empty) | Project name for variable defaults |
| `--write` | flag | off | Write files to disk |

---

## File Map

```
cli/terraform/
├── __init__.py     36 lines — group definition, _resolve_project_root,
│                              sub-module imports (detect, observe, generate)
├── detect.py       82 lines — status command (comprehensive TF detection)
├── observe.py     150 lines — validate, plan, state, workspaces commands
├── generate.py     58 lines — generate command (multi-file scaffolding)
└── README.md               — this file
```

**Total: 326 lines of Python across 4 files.**

---

## Per-File Documentation

### `__init__.py` — Group definition (36 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `_resolve_project_root(ctx)` | helper | Reads `config_path` from context, falls back to `find_project_file()` |
| `terraform()` | Click group | Top-level `terraform` group |
| `from . import detect, observe, generate` | import | Registers sub-modules |

---

### `detect.py` — Terraform status (82 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `status(ctx, as_json)` | command | CLI check + root detection + file/provider/module/resource/backend analysis |

**Core service import (lazy):**

| Import | From | Used For |
|--------|------|----------|
| `terraform_status` | `terraform.ops` | Comprehensive Terraform detection |

**Status display sections (7):**
1. CLI availability + version
2. Root directory
3. Initialization state (.terraform/)
4. File list with types
5. Providers
6. Modules (name → source)
7. Resources (capped at 15) + Backend

**Resource display cap:** Shows at most 15 resources in status view.
Terraform projects can have hundreds of resources; 15 is enough to
understand the project structure.

---

### `observe.py` — Validate, plan, state, workspaces (150 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `validate(ctx, as_json)` | command | Syntax validation with error/warning display |
| `plan(ctx, as_json)` | command | Dry-run with add/change/destroy summary |
| `state(ctx, as_json)` | command | List resources in Terraform state |
| `workspaces(ctx, as_json)` | command | List workspaces with current indicator |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `terraform_validate` | `terraform.ops` | Configuration validation |
| `terraform_plan` | `terraform.ops` | Plan execution |
| `terraform_state` | `terraform.ops` | State resource listing |
| `terraform_workspaces` | `terraform.ops` | Workspace listing |

**Plan change colors:** add → green, change → yellow, destroy → red.
This matches Terraform's native color scheme.

**State module prefix:** If a resource lives inside a module, it's
displayed as `[module.name] type.name` for clarity.

**Workspace current indicator:** The current workspace gets a `▶`
prefix; others get a space for alignment.

---

### `generate.py` — Scaffolding generation (58 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `generate(ctx, provider, backend, project_name, write)` | command | Multi-file TF scaffolding generation |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `generate_terraform` | `terraform.ops` | Scaffolding content generation |
| `write_generated_file` | `docker_ops` | Shared file writer |

**Multi-file loop:** Like K8s and quality config generation, this
iterates over `result["files"]` and writes or previews each file
independently.

---

## Dependency Graph

```
__init__.py
├── click                        ← click.group
├── core.config.loader           ← find_project_file (lazy)
└── Imports: detect, observe, generate

detect.py
├── click                        ← click.command
└── core.services.terraform.ops  ← terraform_status (lazy)

observe.py
├── click                        ← click.command
└── core.services.terraform.ops  ← terraform_validate, terraform_plan,
                                    terraform_state, terraform_workspaces
                                    (all lazy)

generate.py
├── click                        ← click.command
├── core.services.terraform.ops  ← generate_terraform (lazy)
└── core.services.docker_ops     ← write_generated_file (lazy)
```

---

## Consumers

### Who registers this CLI group

| Layer | Module | What It Does |
|-------|--------|-------------|
| CLI entry | `src/main.py:463` | `from src.ui.cli.terraform import terraform` |

### Who also uses the same core service

| Layer | Module | Core Service Used |
|-------|--------|------------------|
| Web routes | `routes/terraform/status.py` | `terraform.ops` (status) |
| Web routes | `routes/terraform/actions.py` | `terraform.ops` (validate, plan) |
| Web routes | `routes/devops/__init__.py:153` | `terraform.ops` (detection) |
| Core | `k8s/validate_cross_domain.py:14` | `terraform_status` (cross-validation) |
| Core | `wizard/helpers.py:62` | `terraform_status` (wizard detection) |
| Core | `wizard/setup_infra.py:257` | `terraform.generate` (wizard setup) |

---

## Design Decisions

### Why `status` shows 7 sections

Terraform projects are complex: CLI version matters, initialization
state matters, providers determine cloud targets, modules add
abstraction, resources are the actual infrastructure, and the backend
determines state storage. Each section answers a different question.

### Why `plan` doesn't show individual resource changes

`terraform plan` output can be extremely long (full HCL diffs for
each resource). The CLI shows a summary (N to add, N to change, N to
destroy). Users needing full details should run `terraform plan`
directly or use `--json`.

### Why `generate` defaults to AWS with local backend

AWS is the most common cloud provider. Local backend is the simplest
starting point (no remote state configuration needed). Users can
override both with `--provider` and `--backend`.

### Why `state` shows module prefixes

In a modular Terraform project, the same resource type can appear in
multiple modules. Without the module prefix, `aws_vpc.this` is
ambiguous. With it, `[module.vpc] aws_vpc.this` is unambiguous.

### Why `workspaces` uses `▶` for the current workspace

Terraform's native `terraform workspace list` uses `*` for the current
workspace. The `▶` character is more visible in mixed-icon CLI output.

---

## JSON Output Examples

### `terraform status --json`

```json
{
  "cli": {"available": true, "version": "v1.7.0"},
  "has_terraform": true,
  "root": "terraform",
  "initialized": true,
  "files": [
    {"path": "terraform/main.tf", "type": "main"},
    {"path": "terraform/variables.tf", "type": "variables"}
  ],
  "providers": ["aws", "random"],
  "modules": [
    {"name": "vpc", "source": "terraform-aws-modules/vpc/aws"}
  ],
  "resources": [
    {"type": "aws_s3_bucket", "name": "assets", "file": "main.tf"}
  ],
  "backend": {"type": "s3", "file": "main.tf"}
}
```

### `terraform plan --json`

```json
{
  "changes": {
    "add": 2,
    "change": 1,
    "destroy": 0
  }
}
```

### `terraform workspaces --json`

```json
{
  "workspaces": ["default", "staging", "production"],
  "current": "production"
}
```
