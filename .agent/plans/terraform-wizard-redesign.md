# Terraform Setup Wizard — Redesign Plan

> Created: 2026-02-18
> Status: PLANNED
> Depends on: Backend fully ✅ (milestones 0.6.1–0.6.8 all checked)
> Scope: UI wizard + minimal backend glue (no new backend services needed)

---

## Current State

The current wizard is 155 lines, 3 thin steps:
- **Detect**: 4 boolean status rows from `probe_terraform()` (CLI, file count, initialized, state)
- **Configure**: Provider + Region + 4 fake resource checkboxes + Backend (checkboxes are never sent to backend)
- **Review**: Cosmetic file list

`setup_terraform()` only uses 3 fields: `provider`, `backend`, `project_name`.
`generate_terraform_k8s()` and `terraform_to_docker_registry()` are never called.

---

## Target State — 5-Step Wizard

### Step 1 — Detect (Environment Scan)

**Data source**: `/api/terraform/status` (full `terraform_status()`, NOT the lightweight probe)

**UI shows**:
| Row | Source field | Display |
|-----|-------------|---------|
| Terraform CLI | `cli.available`, `cli.version` | ✅ v1.7.3 or ❌ Not found |
| TF Root | `root` | `terraform/` or "None found" |
| Files | `files[]` | Count + classified breakdown (main, variables, outputs, providers, backend, data, modules, other) |
| Providers | `providers[]` | Badges: `aws`, `hashicorp/google`, etc. |
| Resources | `resource_count` | "12 resources (3 aws_instance, 2 aws_s3_bucket, …)" |
| Modules | `modules[]` | List with name + source |
| Backend | `backend` | Type badge (s3, gcs, local, etc.) |
| Initialized | `initialized` | ✅/❌ |

**Cross-domain context** (from wizard detect cache):
- If K8s integration active → "🔗 Kubernetes detected — cluster IaC available"
- If Docker integration active → "🔗 Docker detected — registry IaC available"
- If CI/CD integration active → "🔗 CI/CD detected — pipeline integration available"

**Caching**: Same pattern as other wizards (`wizCached('tf:detect')`).

**Implementation notes**:
- Replace `api('/wizard/detect')` → `api('/terraform/status')` for the TF-specific data
- Still read `/wizard/detect` for cross-domain context (K8s/Docker/CI status)
- Store both in wizard data for later steps

---

### Step 2 — Provider & Backend (Cloud Setup)

**UI fields**:
| Field | Type | Default | Notes |
|-------|------|---------|-------|
| Cloud Provider | select | `aws` | AWS, Google Cloud, Azure, DigitalOcean, Custom |
| Region | text | `us-east-1` | Hint: "Primary deployment region" — auto-update default when provider changes (AWS→us-east-1, GCP→us-central1, Azure→eastus, DO→nyc1) |
| Project Name | text | `{root.name}` | Used in backend bucket names, resource naming |
| State Backend | select | `local` | Local, S3, GCS, Azure Blob |

**Conditional fields** (when backend ≠ local):
| Field | Type | Shows when | Notes |
|-------|------|------------|-------|
| State Bucket | text | S3/GCS/Azure | Auto-suggested: `{project}-tfstate` |
| State Lock Table | text | S3 | DynamoDB table for locking: `{project}-tflock` |

**Pre-fill logic**:
- If Step 1 found existing providers → pre-select that provider
- If Step 1 found existing backend → pre-select that backend type
- Region default changes per provider

**Implementation notes**:
- Wire `onchange` on provider select to update region default
- `collect()` stores: `data.provider`, `data.region`, `data.projectName`, `data.backend`

---

### Step 3 — Resources (Infrastructure)

**This is where cross-domain bridges activate.**

**Resource checkboxes** (each expands a config section when checked):

#### ☐ Kubernetes Cluster
> Shows when: always (primary use case for Terraform in this project)
> Backend: `generate_terraform_k8s()`

When checked, show:
| Field | Type | Default | Notes |
|-------|------|---------|-------|
| Node Count | number | `2` | Min 1, max 10 |
| Node Size | text | auto per provider | AWS: `t3.medium`, GCP: `e2-medium`, Azure: `Standard_D2s_v3` |
| K8s Version | text | auto per provider | AWS: `1.29`, GCP: `1.29`, Azure: `1.29` |

Cross-domain hint: If K8s wizard has been configured → show "K8s namespace: `{namespace}`, {N} services detected" and auto-fill namespace from K8s wizard data.

#### ☐ Container Registry
> Shows when: Docker integration detected OR K8s cluster checked
> Backend: `terraform_to_docker_registry()` data feeds into IaC

When checked: No extra fields needed — registry type auto-determined from provider (ECR/GAR/ACR). Show info badge: "ECR will be provisioned for image storage".

#### ☐ VPC / Networking
> Shows when: always
> Backend: Included in `generate_terraform_k8s()` when K8s checked, otherwise a TODO placeholder in main.tf

When checked alone (no K8s): Show info "Networking module will be added as a placeholder". When K8s also checked: Show info "VPC created automatically with cluster".

#### ☐ Database (RDS / Cloud SQL / Azure DB)
> Shows when: always
> Backend: Currently **no generator** for this — will add a placeholder module block

When checked: Show info "Database resource block will be added as a placeholder — configure in generated .tf files".

#### ☐ Object Storage (S3 / GCS / Azure Blob)
> Shows when: always
> Backend: Same — placeholder module block

When checked: Show info "Storage resource block will be added as a placeholder".

**Implementation notes**:
- K8s cluster checkbox is the main one with real generation
- Registry checkbox reads from `terraform_to_docker_registry()` for display/hints
- VPC/DB/Storage are honest placeholders (not fake checkboxes) — they add commented resource blocks
- `collect()` stores: `data.k8sCluster`, `data.nodeCount`, `data.nodeSize`, `data.k8sVersion`, `data.registry`, `data.networking`, `data.database`, `data.storage`

---

### Step 4 — Environments (Workspaces & Variables)

**Data sources**:
- Project environments from wizard detect: `probes.project.environments[]` (or project.yml)
- Vault keys from `/api/vault/keys` (for variable/secret picker — same pattern as CI/CD Step 4)

**Auto-seed**: If project.yml defines environments (dev, staging, prod), pre-create workspace cards for each.

**Per-environment card** (same card pattern as CI/CD wizard):
| Field | Type | Notes |
|-------|------|-------|
| Workspace Name | text (readonly) | e.g. `dev`, `staging`, `production` |
| Region Override | text | Optional — override default region for this env |
| Var File | text (readonly) | `terraform/{name}.tfvars` — auto-generated |

**Add Environment button**: Manual add for custom workspaces.

**Variable picker** (per environment):
- Same pattern as CI/CD wizard: vault secrets + vault variables + suggestions + custom
- Variables go into the `.tfvars` file for that environment
- "Does not exist yet" notice when key not in vault

**Generated per environment**:
- `{env}.tfvars` file with environment-specific variable values
- Workspace name matches environment name

**Implementation notes**:
- If no project.yml environments → show "Add at least one environment" prompt
- Minimal first pass: just workspace names and region overrides
- Variable picker is a stretch goal — can be added later if environment cards are complex enough

---

### Step 5 — Review & Generate

**Summary sections**:

1. **Provider & Backend**: Provider badge, region, backend type
2. **Resources**: List of checked resources with status badges (create/exists/placeholder)
3. **Environments**: Workspace list with var files
4. **Files to generate**: Full file list with create/skip/overwrite badges

**File list** (varies by what's checked):

| File | When | Badge |
|------|------|-------|
| `terraform/main.tf` | Always | create / overwrite |
| `terraform/variables.tf` | Always | create / overwrite |
| `terraform/outputs.tf` | Always | create / overwrite |
| `terraform/.gitignore` | Always | create / overwrite |
| `terraform/k8s.tf` | K8s cluster checked | create |
| `terraform/registry.tf` | Registry checked | create |
| `terraform/{env}.tfvars` | Per environment | create |

**Overwrite toggle**: Checkbox — "Overwrite existing Terraform files"

**onComplete payload**:
```javascript
{
    action: 'setup_terraform',
    provider: data.provider,
    region: data.region,
    project_name: data.projectName,
    backend: data.backend,
    overwrite: data.overwrite,
    // Cross-domain (for generate_terraform_k8s)
    k8s_cluster: data.k8sCluster,
    node_count: data.nodeCount,
    node_size: data.nodeSize,
    k8s_version: data.k8sVersion,
    namespace: data.namespace,  // from K8s wizard context
    // Resource flags
    registry: data.registry,
    networking: data.networking,
    database: data.database,
    storage: data.storage,
    // Environments
    environments: data.environments,  // [{name, region}]
}
```

---

## Backend Changes Needed

### 1. `setup_terraform()` — Expand to handle cross-domain

Current: Only calls `generate_terraform(provider, backend, project_name)`.

Needed:
- If `k8s_cluster=True` → call `generate_terraform_k8s()` instead of `generate_terraform()`
- Pass through `node_count`, `node_size`, `k8s_version`, `namespace`, `services`
- If `environments` provided → generate per-env `.tfvars` files
- Handle `overwrite` flag (already supported but not sent by current wizard)
- Add placeholder resource blocks for database/storage when those flags are true

### 2. `generate_terraform()` — Add resource placeholder blocks

Current: Generates clean skeleton with provider + backend only.

Needed:
- Accept optional `resources` dict: `{database: True, storage: True, networking: True}`
- When a resource flag is true → add a commented HCL block for that resource type
- This is additive — doesn't break existing behavior

### 3. No new services or routes needed
- All routes already exist (`/terraform/status`, `/terraform/generate`, `/wizard/setup`)
- All backend functions already exist
- Just need to wire the wizard data through to the right generator

---

## Implementation Order

### Phase 1 — Rebuild the wizard UI (Steps 1-2-5)
> Core flow: better detection, real provider/backend config, review with overwrite

1. [x] **Step 1 (Detect)**: Replace probe with full `terraform_status()` call. Render all detection data. Add cross-domain context hints.
2. [x] **Step 2 (Provider & Backend)**: Provider + region + project name + backend. Dynamic region defaults. Pre-fill from detection.
3. [x] **Step 5 (Review)**: File list, overwrite toggle, summary.
4. [x] **Wire onComplete**: Send `provider`, `backend`, `project_name`, `overwrite` to `/wizard/setup`.
5. [ ] **Verify**: Run server, open wizard, check each step renders and submits correctly.

### Phase 2 — Resources step (Step 3)
> Cross-domain bridge: K8s cluster IaC, registry hints

6. [x] **Step 3 (Resources)**: Resource checkboxes with expand sections. K8s cluster fields. Registry info badge.
7. [ ] **Backend: `setup_terraform()` expansion**: If `k8s_cluster=True` → delegate to `generate_terraform_k8s()`.
8. [ ] **Backend: placeholder resources**: Database/storage/networking commented blocks.
9. [ ] **Verify**: Check K8s cluster checkbox → verify `k8s.tf` generated with correct HCL.

### Phase 3 — Environments step (Step 4)
> Workspace alignment with project.yml

10. [x] **Step 4 (Environments)**: Auto-seed from project.yml. Workspace cards. Region overrides.
11. [ ] **Backend: `.tfvars` generation**: Per-environment variable files.
12. [ ] **Verify**: Check environments show correctly, var files generated.

### Phase 4 — Polish
13. [ ] **Variable picker in Step 4**: Vault secret/variable picker (same pattern as CI/CD wizard).
14. [ ] **Post-generate actions**: After completion, offer "Run terraform init" button.
15. [ ] **Update audit plan**: Mark Terraform section in ui-api-surface-audit.md.

---

## Assumptions

1. `generate_terraform_k8s()` is the primary cross-domain generator — it already works and is tested.
2. Database/storage/networking without K8s = commented placeholder blocks, not real modules. We're honest about this.
3. Environment/workspace support is workspace names + `.tfvars` files. Not full Terraform Cloud workspace management.
4. Variable picker in Step 4 is a stretch goal — can be deferred if Phase 3 is already complex enough.
5. No new routes or backend services needed — just expanding `setup_terraform()` to accept more fields.
