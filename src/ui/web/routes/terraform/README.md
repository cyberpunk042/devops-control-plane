# Terraform Routes — IaC Status, Validation, Plan, Apply & Generation API

> **3 files · 182 lines · 11 endpoints · Blueprint: `terraform_bp` · Prefix: `/api`**
>
> Two sub-domains under a single blueprint:
>
> 1. **Status (read-only)** — Terraform configuration analysis, state
>    listing, workspace listing, output values (4 endpoints, 1 cached)
> 2. **Actions (mutations)** — validate, plan, init, apply, destroy,
>    generate scaffolding, workspace select, format (7 endpoints)
>
> Backed by `core/services/terraform/ops.py` (514 lines).

---

## How It Works

### Terraform Status Pipeline (Cached)

```
GET /api/terraform/status?bust=1
     │
     ▼
devops_cache.get_cached(root, "terraform", lambda: terraform_ops.terraform_status(root))
     │
     ├── Cache HIT → return cached status
     └── Cache MISS → terraform_status(root)
         │
         ├── Scan for *.tf files
         ├── Parse providers, resources, data sources, variables, outputs
         ├── Check terraform CLI availability (shutil.which)
         ├── Check initialization status (.terraform/ directory)
         ├── Detect backend configuration (local, s3, gcs, azurerm)
         │
         └── Return:
             {
                 has_terraform: true,
                 cli_available: true,
                 initialized: true,
                 backend: "s3",
                 providers: ["aws", "random"],
                 resource_count: 12,
                 files: ["main.tf", "variables.tf", ...]
             }
```

### State & Workspace Queries

```
GET /api/terraform/state
     │
     ▼
terraform_ops.terraform_state(root)
     │
     └── terraform state list
         → { ok: true, resources: ["aws_instance.web", "aws_s3_bucket.data"] }

GET /api/terraform/workspaces
     │
     ▼
terraform_ops.terraform_workspaces(root)
     │
     └── terraform workspace list
         → { ok: true, workspaces: ["default", "staging", "production"],
             current: "default" }

GET /api/terraform/output
     │
     ▼
terraform_ops.terraform_output(root)
     │
     └── terraform output -json
         → { ok: true, outputs: { "vpc_id": { value: "vpc-abc123", type: "string" } } }
```

### Terraform Lifecycle Pipeline

```
POST /api/terraform/init  { upgrade: true }
     │
     ├── @run_tracked("setup", "setup:terraform")
     │
     ▼
terraform_ops.terraform_init(root, upgrade=True)
     └── terraform init [-upgrade]
         → { ok: true, output: "Initializing provider plugins..." }

POST /api/terraform/validate
     │
     ├── @run_tracked("validate", "validate:terraform")
     │
     ▼
terraform_ops.terraform_validate(root)
     └── terraform validate -json
         → { ok: true, valid: true, diagnostics: [] }

POST /api/terraform/plan
     │
     ├── @run_tracked("plan", "plan:terraform")
     │
     ▼
terraform_ops.terraform_plan(root)
     └── terraform plan -json
         → { ok: true, add: 3, change: 1, destroy: 0, output: "..." }

POST /api/terraform/apply
     │
     ├── @run_tracked("deploy", "deploy:terraform")
     │
     ▼
terraform_ops.terraform_apply(root)
     └── terraform apply -auto-approve
         → { ok: true, output: "Apply complete! Resources: 3 added, 1 changed, 0 destroyed." }

POST /api/terraform/destroy
     │
     ├── @run_tracked("destroy", "destroy:terraform")
     │
     ▼
terraform_ops.terraform_destroy(root)
     └── terraform destroy -auto-approve
         → { ok: true, output: "Destroy complete! Resources: 4 destroyed." }
```

### Scaffolding Generation Pipeline

```
POST /api/terraform/generate
     Body: { provider: "aws", backend: "s3", project_name: "my-app" }
     │
     ├── @run_tracked("generate", "generate:terraform")
     │
     ▼
terraform_ops.generate_terraform(root, "aws", backend="s3", project_name="my-app")
     │
     ├── Generate provider-specific files:
     │   ├── main.tf — provider block + backend block
     │   ├── variables.tf — common variables (region, project_name)
     │   ├── outputs.tf — common outputs
     │   └── terraform.tfvars — default values
     │
     └── Return:
         { ok: true, files: ["main.tf", "variables.tf", "outputs.tf", "terraform.tfvars"] }
```

### Workspace & Format Operations

```
POST /api/terraform/workspace/select  { workspace: "staging" }
     │
     ├── @run_tracked("setup", "setup:terraform_ws")
     │
     ▼
terraform_ops.terraform_workspace_select(root, "staging")
     └── terraform workspace select staging
         (or terraform workspace new staging if it doesn't exist)
         → { ok: true, workspace: "staging" }

POST /api/terraform/fmt
     │
     ├── @run_tracked("format", "format:terraform")
     │
     ▼
terraform_ops.terraform_fmt(root)
     └── terraform fmt -recursive
         → { ok: true, output: "main.tf\nvariables.tf" }
```

---

## File Map

```
routes/terraform/
├── __init__.py     18 lines — blueprint + 2 sub-module imports
├── status.py       45 lines — 4 read-only endpoints
├── actions.py     119 lines — 7 action endpoints
└── README.md               — this file
```

Core business logic: `core/services/terraform/ops.py` (514 lines).

---

## Per-File Documentation

### `__init__.py` — Blueprint Definition (18 lines)

```python
terraform_bp = Blueprint("terraform", __name__)

from . import status, actions  # register routes
```

### `status.py` — Read-Only Endpoints (45 lines)

| Function | Method | Route | Cached | What It Does |
|----------|--------|-------|--------|-------------|
| `tf_status()` | GET | `/terraform/status` | ✅ `"terraform"` | Config analysis |
| `tf_state()` | GET | `/terraform/state` | No | List state resources |
| `tf_workspaces()` | GET | `/terraform/workspaces` | No | List workspaces |
| `tf_output()` | GET | `/terraform/output` | No | Get output values |

### `actions.py` — Mutation Endpoints (119 lines)

| Function | Method | Route | Tracked | What It Does |
|----------|--------|-------|---------|-------------|
| `tf_validate()` | POST | `/terraform/validate` | ✅ `validate:terraform` | Validate config |
| `tf_plan()` | POST | `/terraform/plan` | ✅ `plan:terraform` | Preview changes |
| `tf_init()` | POST | `/terraform/init` | ✅ `setup:terraform` | Initialize providers |
| `tf_apply()` | POST | `/terraform/apply` | ✅ `deploy:terraform` | Apply changes |
| `tf_destroy()` | POST | `/terraform/destroy` | ✅ `destroy:terraform` | Destroy resources |
| `tf_generate()` | POST | `/terraform/generate` | ✅ `generate:terraform` | Generate scaffolding |
| `tf_workspace_select()` | POST | `/terraform/workspace/select` | ✅ `setup:terraform_ws` | Switch workspace |
| `tf_fmt()` | POST | `/terraform/fmt` | ✅ `format:terraform` | Format .tf files |

**Init supports upgrade mode:**

```python
data = request.get_json(silent=True) or {}
upgrade = data.get("upgrade", False)
result = terraform_ops.terraform_init(root, upgrade=upgrade)
```

**Generate accepts provider + backend + project name:**

```python
result = terraform_ops.generate_terraform(
    root, provider,
    backend=backend,
    project_name=data.get("project_name", ""),
)
```

---

## Dependency Graph

```
__init__.py
└── Imports: status, actions

status.py
├── terraform.ops  ← terraform_status, terraform_state,
│                    terraform_workspaces, terraform_output (eager)
├── helpers        ← project_root (eager)
└── devops.cache   ← get_cached (lazy, inside handler)

actions.py
├── terraform.ops  ← terraform_validate, terraform_plan 
│                    terraform_init, terraform_apply,
│                    terraform_destroy, generate_terraform,
│                    terraform_workspace_select, terraform_fmt (eager)
├── run_tracker    ← @run_tracked (eager)
└── helpers        ← project_root (eager)
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Server | `ui/web/server.py` | Imports `terraform_bp`, registers at `/api` |
| DevOps card | `scripts/devops/_terraform.html` | `/terraform/status` (cached) |
| Terraform panel | `scripts/integrations/_terraform.html` | `/terraform/*` (all endpoints) |
| Terraform setup | `scripts/integrations/setup/_terraform.html` | `/terraform/init`, `/terraform/generate` |
| DNS setup | `scripts/integrations/setup/_dns.html` | `/terraform/status` (check TF available) |
| Wizard | `scripts/wizard/_integration_actions.html` | `/terraform/init`, `/terraform/generate` |

---

## Data Shapes

### `GET /api/terraform/status` response

```json
{
    "has_terraform": true,
    "cli_available": true,
    "initialized": true,
    "backend": "s3",
    "providers": ["aws", "random"],
    "resource_count": 12,
    "files": ["main.tf", "variables.tf", "outputs.tf", "terraform.tfvars"]
}
```

### `GET /api/terraform/state` response

```json
{
    "ok": true,
    "resources": [
        "aws_instance.web",
        "aws_s3_bucket.data",
        "aws_security_group.allow_https"
    ]
}
```

### `GET /api/terraform/workspaces` response

```json
{
    "ok": true,
    "workspaces": ["default", "staging", "production"],
    "current": "default"
}
```

### `GET /api/terraform/output` response

```json
{
    "ok": true,
    "outputs": {
        "vpc_id": { "value": "vpc-abc123", "type": "string" },
        "public_ip": { "value": "54.123.45.67", "type": "string" }
    }
}
```

### `POST /api/terraform/plan` response

```json
{
    "ok": true,
    "add": 3,
    "change": 1,
    "destroy": 0,
    "output": "Plan: 3 to add, 1 to change, 0 to destroy."
}
```

### `POST /api/terraform/generate` request + response

```json
// Request:
{ "provider": "aws", "backend": "s3", "project_name": "my-app" }

// Response:
{
    "ok": true,
    "files": ["main.tf", "variables.tf", "outputs.tf", "terraform.tfvars"]
}
```

---

## Advanced Feature Showcase

### 1. Full Terraform Lifecycle in One API

The routes cover the entire Terraform workflow:

```
generate → init → validate → plan → apply → destroy
                                 ↕
                            workspace/select
                                 ↕
                               fmt
```

### 2. Tracked Activity Categories

Every Terraform mutation maps to a semantic tracker category:
- `setup:terraform` — init
- `setup:terraform_ws` — workspace select
- `validate:terraform` — validate
- `plan:terraform` — plan
- `deploy:terraform` — apply
- `destroy:terraform` — destroy
- `generate:terraform` — scaffolding
- `format:terraform` — format

### 3. Provider-Aware Scaffolding

The generate endpoint produces provider-specific Terraform files:
- AWS → VPC, subnets, security groups
- GCP → project config, networking
- Azure → resource groups, virtual networks

Each includes appropriate backend configuration (local, S3, GCS,
Azure Blob).

---

## Design Decisions

### Why state/workspaces/output are not cached

These query live Terraform state which can change between calls
(other team members applying changes, CI/CD pipelines). Only the
file-system scan (`/status`) is cached because it reads local
`.tf` files.

### Why apply and destroy use -auto-approve

The control plane is an interactive tool where the user explicitly
clicks "Apply" or "Destroy" in the UI. The confirmation step
happens in the frontend (modal confirmation), not in the CLI.

### Why every action is tracked

Terraform operations are high-impact infrastructure changes. The
activity log provides an audit trail of who did what and when,
which is critical for IaC governance.

---

## Coverage Summary

| Capability | Endpoint | Method | Tracked | Cached |
|-----------|----------|--------|---------|--------|
| Status | `/terraform/status` | GET | No | ✅ `"terraform"` |
| State list | `/terraform/state` | GET | No | No |
| Workspaces | `/terraform/workspaces` | GET | No | No |
| Outputs | `/terraform/output` | GET | No | No |
| Validate | `/terraform/validate` | POST | ✅ `validate:terraform` | No |
| Plan | `/terraform/plan` | POST | ✅ `plan:terraform` | No |
| Init | `/terraform/init` | POST | ✅ `setup:terraform` | No |
| Apply | `/terraform/apply` | POST | ✅ `deploy:terraform` | No |
| Destroy | `/terraform/destroy` | POST | ✅ `destroy:terraform` | No |
| Generate | `/terraform/generate` | POST | ✅ `generate:terraform` | No |
| Workspace select | `/terraform/workspace/select` | POST | ✅ `setup:terraform_ws` | No |
| Format | `/terraform/fmt` | POST | ✅ `format:terraform` | No |
