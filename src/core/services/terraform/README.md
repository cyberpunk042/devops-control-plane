# Terraform Domain

> **4 files · 1,463 lines · Terraform detection, operations, code generation, and cross-domain bridges.**
>
> Full Terraform lifecycle: detect configs → validate → plan → apply → state inspect.
> Plus IaC scaffolding generators for cloud providers and K8s cluster provisioning.

---

## How It Works

The domain is organized around four operation modes:

```
┌──────────────────────────────────────────────────────────────────┐
│  DETECT — What Terraform exists?                                  │
│     terraform_status(root) → files, providers, modules, backend   │
│     ├── CLI detection + version                                   │
│     ├── .tf file scanning + classification                        │
│     ├── Resource/provider/module extraction (regex-based)          │
│     ├── Backend detection (local, s3, gcs, azurerm)               │
│     └── Initialization status (.terraform/ present?)              │
├──────────────────────────────────────────────────────────────────┤
│  OBSERVE — What's the current state?                              │
│     terraform_validate(root) → syntax errors                      │
│     terraform_plan(root) → add/change/destroy counts              │
│     terraform_state(root) → managed resource list                 │
│     terraform_workspaces(root) → workspace list + current          │
├──────────────────────────────────────────────────────────────────┤
│  ACT — Mutate infrastructure                                      │
│     terraform_init(root) → initialize providers/backend           │
│     terraform_apply(root) → apply plan (auto-approve)             │
│     terraform_destroy(root) → tear down resources                  │
│     terraform_output(root) → read outputs                          │
│     terraform_workspace_select(root, name) → switch workspace     │
│     terraform_fmt(root) → format .tf files                         │
├──────────────────────────────────────────────────────────────────┤
│  GENERATE — Create IaC from scratch                               │
│     generate_terraform(root, provider) → main.tf + vars + outputs │
│     generate_terraform_k8s(root, provider, ...) → cluster IaC     │
│     terraform_to_docker_registry(provider) → CI registry config   │
└──────────────────────────────────────────────────────────────────┘
```

### Detection Flow (step by step)

```
terraform_status(project_root)
     │
     ├── _terraform_available():
     │     ├── Try: terraform version -json → parse JSON
     │     ├── Fallback: terraform version → parse first line
     │     └── Return: {available, version}
     │
     ├── _find_tf_root(project_root):
     │     ├── Check in order: terraform/, infra/, infrastructure/, .
     │     │     └── Any directory with *.tf files → return it
     │     ├── Fallback: rglob("*.tf") excluding _SKIP_DIRS
     │     └── Return first .tf file's parent, or None
     │
     ├── If no tf_root → return empty status + missing_tools
     │
     ├── Scan .tf files (rglob("*.tf"), skip _SKIP_DIRS):
     │     For each file:
     │     ├── _classify_tf_file(name):
     │     │     main, variables, outputs, providers, backend,
     │     │     versions, data, modules, other
     │     │
     │     ├── Parse providers:
     │     │     ├── provider "aws" { → regex
     │     │     └── source = "hashicorp/aws" → regex
     │     │
     │     ├── Parse modules:
     │     │     └── module "vpc" { ... source = "..." → regex
     │     │
     │     ├── Parse resources:
     │     │     └── resource "aws_instance" "web" → regex
     │     │
     │     ├── Parse data sources:
     │     │     └── data "aws_ami" "latest" → regex
     │     │
     │     └── Parse backend (first found):
     │           └── backend "s3" { ... } → regex
     │
     ├── Check initialized: (tf_root / ".terraform").is_dir()
     │
     ├── check_required_tools(["terraform"]) → missing_tools
     │
     └── Return: {has_terraform, cli, root, files, providers,
                   modules, resources, resource_count, backend,
                   initialized, missing_tools}
```

### Action Flow (common pattern)

Every action function follows the same guard pattern:

```
terraform_<action>(project_root, **kwargs)
     │
     ├── _find_tf_root(project_root) → tf_root or None
     │     └── None → {"ok": False, "error": "No Terraform files found"}
     │
     ├── _terraform_available() → cli
     │     └── not available → {"ok": False, "error": "terraform CLI not available"}
     │
     ├── (For apply/destroy/plan only): check .terraform/ exists
     │     └── missing → {"ok": False, "error": "Not initialized. Run init first."}
     │
     ├── _run_terraform(*args, cwd=tf_root, timeout=<varies>)
     │     └── subprocess.run(["terraform", ...], capture_output=True)
     │
     ├── Parse output (action-specific)
     │
     ├── If success → _audit(...)
     │
     └── Return result dict
```

**Timeout values per action:**

| Action | Timeout | Output Cap |
|--------|---------|-----------|
| `init` | 120s | Full output |
| `apply` | 300s | Last 3000 chars |
| `destroy` | 300s | Last 3000 chars |
| `plan` | 120s | Last 2000 chars |
| `output` | 30s | Full JSON |
| `validate` | 60s | Full JSON diagnostics |
| `state list` | 60s | Full output |
| `workspace list` | 60s | Full output |
| `fmt` | 60s | File list |

### Generation Flow

```
generate_terraform(project_root, provider, *, backend, project_name)
     │
     ├── Load provider config from DataRegistry:
     │     └── _provider_blocks() → {aws: {source, version, config, default_region}, ...}
     │
     ├── Validate provider exists in registry
     │
     ├── Build HCL blocks:
     │     ├── provider_block: source + version
     │     ├── backend_block: _backend_blocks()[backend].format(project, region)
     │     ├── main.tf: terraform {} + provider {} + resources placeholder
     │     ├── variables.tf: project, environment, region, tags
     │     └── outputs.tf: commented-out template
     │
     ├── Write .gitignore: .terraform/, *.tfstate, *.tfplan, crash.log
     │
     ├── Each file → GeneratedFile(path, content, overwrite=False, reason)
     │
     ├── Audit: "📝 Terraform Generated"
     │
     └── Return: {"ok": True, "files": [GeneratedFile dicts]}
```

### K8s Cross-Domain Generation Flow

```
generate_terraform_k8s(project_root, provider, *, backend, project_name,
                        namespace, services, node_count, node_size, k8s_version)
     │
     ├── Validate provider: _provider_blocks().get(provider)
     ├── Validate K8s template: _k8s_catalog().get(provider)
     │
     ├── Apply defaults from catalog:
     │     ├── node_size → k8s_config["default_node_size"]
     │     └── k8s_version → k8s_config["default_k8s_version"]
     │
     ├── Determine if registry needed:
     │     └── has_images = any(svc.get("image") for svc in services)
     │
     ├── Generate main.tf:
     │     ├── terraform {} with cloud provider + kubernetes provider
     │     ├── provider "<cloud>" {} with config
     │     ├── Cluster resource (from k8s_config["cluster_hcl"])
     │     └── If has_images → registry resource (k8s_config["registry_hcl"])
     │
     ├── Generate variables.tf:
     │     ├── project, region, k8s_version, node_count, node_size
     │     ├── If namespace → namespace variable
     │     └── If aws → subnet_ids variable
     │
     ├── Generate outputs.tf:
     │     ├── cluster_endpoint, cluster_ca_certificate (sensitive), kubeconfig_command
     │     └── If has_images → registry_url
     │
     ├── Generate k8s.tf:
     │     ├── provider "kubernetes" { host, cluster_ca_certificate }
     │     └── If namespace → kubernetes_namespace resource
     │
     ├── Generate .gitignore
     │
     ├── Audit: "📝 Terraform K8s Generated"
     │
     └── Return: {"ok": True, "files": [5 GeneratedFile dicts]}
```

### Docker Registry Bridge

```
terraform_to_docker_registry(provider, *, project_name, region)
     │
     ├── Lookup _DOCKER_REGISTRY_MAP[provider]
     │     └── not found → {"ok": False, "error": "Unknown provider"}
     │
     ├── Apply default region per provider:
     │     ├── aws → us-east-1
     │     ├── google → us-central1
     │     └── azurerm → eastus
     │
     ├── Clean project name (Azure: no hyphens in ACR names)
     │
     ├── Build registry URL:
     │     ├── If explicit region → url_template.format(...)
     │     └── Else → url_default.format(...)
     │
     ├── Build login_step from template
     │
     └── Return: {ok, registry_type, registry_url, credentials, login_step, login_action}
```

### File Classification

When scanning `.tf` files, each is classified by naming convention:

| Filename Pattern | Classification |
|-----------------|---------------|
| `main.tf` | `main` |
| `variables.tf`, `vars.tf` | `variables` |
| `outputs.tf` | `outputs` |
| `providers.tf`, `provider.tf` | `providers` |
| `backend.tf`, `state.tf` | `backend` |
| `terraform.tf`, `versions.tf` | `versions` |
| `data.tf`, `datasources.tf` | `data` |
| `module*.tf` | `modules` |
| Other `.tf` | `other` |

### Terraform Root Discovery

`_find_tf_root` searches in this order:

```
1. project_root/terraform/   ← if has *.tf files
2. project_root/infra/       ← if has *.tf files
3. project_root/infrastructure/
4. project_root/             ← project root itself
5. Fallback: rglob("*.tf")  ← first match excluding _SKIP_DIRS
```

**Skipped directories (`_SKIP_DIRS`):**

```python
{".git", ".venv", "venv", "node_modules", "__pycache__",
 ".terraform", "dist", "build", ".pages", ".backup"}
```

---

## Key Data Shapes

### terraform_status response

```python
# Terraform detected
{
    "has_terraform": True,
    "cli": {
        "available": True,
        "version": "1.7.4",
    },
    "root": "terraform",                  # relative to project root, or "."
    "files": [
        {"path": "terraform/main.tf", "type": "main"},
        {"path": "terraform/variables.tf", "type": "variables"},
        {"path": "terraform/outputs.tf", "type": "outputs"},
    ],
    "providers": ["aws", "random"],       # sorted, deduplicated
    "modules": [
        {"name": "vpc", "source": "terraform-aws-modules/vpc/aws"},
    ],
    "resources": [
        {"type": "aws_instance", "name": "web", "file": "terraform/main.tf"},
        {"type": "data.aws_ami", "name": "latest", "file": "terraform/main.tf"},
    ],
    "resource_count": 2,
    "backend": {
        "type": "s3",
        "file": "terraform/main.tf",
    },
    "initialized": True,
    "missing_tools": [],
}

# No Terraform
{
    "has_terraform": False,
    "cli": {"available": False, "version": None},
    "root": None,
    "files": [],
    "providers": [],
    "modules": [],
    "resources": [],
    "backend": None,
    "initialized": False,
    "missing_tools": [{"tool": "terraform", ...}],
}
```

### terraform_validate response

```python
# Valid
{
    "ok": True,
    "valid": True,
    "errors": [],
    "error_count": 0,
    "warning_count": 0,
}

# Invalid
{
    "ok": True,
    "valid": False,
    "errors": [
        {"message": "Unsupported argument", "detail": "...", "severity": "error"},
    ],
    "error_count": 1,
    "warning_count": 0,
}
```

### terraform_plan response

```python
{
    "ok": True,
    "changes": {"add": 3, "change": 1, "destroy": 0},
    "output": "Plan: 3 to add, 1 to change, 0 to destroy. ...",
}
```

### terraform_state response

```python
{
    "ok": True,
    "resources": [
        {"address": "aws_instance.web", "type": "aws_instance",
         "name": "web", "module": ""},
        {"address": "module.vpc.aws_vpc.main", "type": "aws_vpc",
         "name": "main", "module": "vpc"},
        {"address": "data.aws_ami.latest", "type": "data.aws_ami",
         "name": "latest", "module": ""},
    ],
    "count": 3,
}
```

### terraform_workspaces response

```python
{
    "ok": True,
    "current": "staging",
    "workspaces": ["default", "staging", "production"],
}
```

### terraform_output response

```python
{
    "ok": True,
    "outputs": {
        "cluster_endpoint": {
            "value": "https://eks.us-east-1.amazonaws.com/...",
            "type": "string",
            "sensitive": False,
        },
        "cluster_ca": {
            "value": "LS0tLS1...",
            "type": "string",
            "sensitive": True,
        },
    },
}
```

### terraform_apply response

```python
{
    "ok": True,
    "output": "Apply complete! Resources: 3 added, 1 changed, 0 destroyed.",
    "changes": {"add": 3, "change": 1, "destroy": 0},
}
```

### generate_terraform response

```python
{
    "ok": True,
    "files": [
        {"path": "terraform/main.tf", "content": "...",
         "reason": "Terraform main config (aws provider, s3 backend)",
         "overwrite": False},
        {"path": "terraform/variables.tf", "content": "...",
         "reason": "Terraform variables with validation",
         "overwrite": False},
        {"path": "terraform/outputs.tf", "content": "...",
         "reason": "Terraform outputs (template)",
         "overwrite": False},
        {"path": "terraform/.gitignore", "content": "...",
         "reason": "Terraform .gitignore",
         "overwrite": False},
    ],
}
```

### generate_terraform_k8s response

```python
{
    "ok": True,
    "files": [
        {"path": "terraform/main.tf", "content": "...",
         "reason": "K8s cluster infrastructure (aws, aws_eks_cluster)"},
        {"path": "terraform/variables.tf", "content": "...",
         "reason": "Terraform variables for K8s cluster provisioning"},
        {"path": "terraform/outputs.tf", "content": "...",
         "reason": "Cross-domain outputs (cluster endpoint, CA, kubeconfig, registry)"},
        {"path": "terraform/k8s.tf", "content": "...",
         "reason": "Kubernetes provider + namespace resource"},
        {"path": "terraform/.gitignore", "content": "...",
         "reason": "Terraform .gitignore"},
    ],
}
```

### terraform_to_docker_registry response

```python
{
    "ok": True,
    "registry_type": "ecr",                          # or "gar", "acr"
    "registry_url": "123456789.dkr.ecr.us-east-1.amazonaws.com/my-app",
    "credentials": {
        "AWS_ACCESS_KEY_ID": "${{ secrets.AWS_ACCESS_KEY_ID }}",
        "AWS_SECRET_ACCESS_KEY": "${{ secrets.AWS_SECRET_ACCESS_KEY }}",
    },
    "login_step": "aws ecr get-login-password ...",
    "login_action": "docker/login-action@v3",
}
```

**Docker registry mapping per provider:**

| Provider | Registry Type | URL Pattern | Login |
|----------|-------------|------------|-------|
| `aws` | ECR | `{account_id}.dkr.ecr.{region}.amazonaws.com/{project}` | `aws ecr get-login-password` |
| `google` | GAR | `{region}-docker.pkg.dev/{project}/{project}` | `docker login -u _json_key` |
| `azurerm` | ACR | `{project_clean}.azurecr.io/{project}` | `docker login` with ACR creds |

---

## Architecture

```
              Routes / CLI
                  │
         ┌────────▼────────┐
         │  __init__.py     │  Public API re-exports
         └──┬──────┬───────┘
            │      │
     ┌──────┘      └──────┐
     ▼                     ▼
  ops.py              actions.py
  (detect, validate,   (init, apply, destroy,
   plan, state,         output, workspace,
   workspaces)          fmt)
     │
     ├── re-exports actions.py  ← backward compat
     └── re-exports generate.py ← backward compat
            │
     generate.py
     (scaffolding: HCL templates,
      K8s cluster generation,
      Docker registry bridge)
            │
     DataRegistry ← provider/backend/k8s configs
```

---

## Dependency Graph

```
ops.py                                   ← primary module
   │
   ├── subprocess                        ← terraform CLI calls
   ├── audit_helpers.make_auditor        ← module level
   ├── tool_requirements.check_required_tools ← lazy (inside terraform_status)
   ├── actions.* (re-export)             ← at bottom of file
   └── generate.generate_terraform (re-export) ← at bottom of file

actions.py                               ← mutating operations
   │
   ├── ops._run_terraform                ← module level
   ├── ops._terraform_available          ← module level
   ├── ops._find_tf_root                 ← module level
   ├── ops._parse_plan_output            ← module level
   └── audit_helpers.make_auditor        ← module level

generate.py                              ← scaffolding (standalone)
   │
   ├── audit_helpers.make_auditor        ← module level
   ├── core.data.get_registry            ← lazy (inside _provider_blocks, _backend_blocks, _k8s_catalog)
   └── core.models.template.GeneratedFile ← lazy (inside generate functions)

__init__.py                              ← public surface
   │
   ├── ops.* (re-export)                 ← all public functions
   ├── actions.* (re-export)             ← all public functions
   └── generate.* (re-export)            ← all public functions
```

Key: `generate.py` is fully standalone — it imports nothing from `ops.py`
or `actions.py`. Data comes from DataRegistry (lazy-loaded).

### Dependency Rules

| Rule | Detail |
|------|--------|
| `ops.py` is the primary module | Detection + read-only operations |
| `actions.py` imports helpers from `ops.py` | `_run_terraform`, `_find_tf_root`, `_terraform_available`, `_parse_plan_output` |
| `generate.py` is standalone | Uses DataRegistry for HCL templates, no ops/actions imports |
| `ops.py` re-exports both submodules | Backward-compatible API surface |
| No circular imports | `actions.py → ops.py` only (one direction) |

---

## File Map

```
terraform/
├── __init__.py     40 lines   — public API re-exports
├── ops.py         515 lines   — detection, validate, plan, state, workspaces
├── actions.py     250 lines   — init, apply, destroy, output, workspace, fmt
├── generate.py    658 lines   — HCL scaffolding + K8s cluster + Docker bridge
└── README.md                  — this file
```

---

## Per-File Documentation

### `ops.py` — Detection & Read-Only Operations (515 lines)

**Constants:**

| Constant | Type | Value |
|----------|------|-------|
| `_SKIP_DIRS` | `frozenset` | 10 directory names to exclude from scanning |

**Functions:**

| Function | Parameters | What It Does |
|----------|-----------|-------------|
| `terraform_status(root)` | `Path` | **Main** — comprehensive Terraform detection: CLI, files, providers, modules, resources, backend, init status, missing_tools |
| `terraform_validate(root)` | `Path` | Offline syntax check (`terraform validate -json`) → valid/invalid + diagnostics |
| `terraform_plan(root, *, var_file)` | `Path, str\|None` | Dry-run plan → add/change/destroy counts + output (last 2000 chars) |
| `terraform_state(root)` | `Path` | `terraform state list` → parse resource addresses (type.name, module.mod.type.name, data.type.name) |
| `terraform_workspaces(root)` | `Path` | `terraform workspace list` → parse `* current` marker |
| `_terraform_available()` | — | Check CLI + parse version (JSON first, fallback to text) |
| `_find_tf_root(root)` | `Path` | Locate primary Terraform directory (check 4 conventional names + fallback rglob) |
| `_classify_tf_file(name)` | `str` | Name-convention file type → one of 9 types |
| `_run_terraform(*args, cwd, timeout)` | `str..., Path, int` | `subprocess.run(["terraform", ...], capture_output=True)` |
| `_parse_plan_output(output)` | `str` | Regex: "Plan: X to add, Y to change, Z to destroy" → `{add, change, destroy}` |

**HCL parsing regex patterns:**

| Pattern | Target | Example Match |
|---------|--------|---------------|
| `provider "([^"]+)"` | Provider blocks | `provider "aws" {` → `aws` |
| `(\w+)\s*=\s*\{.*source\s*=\s*"([^"]+)"` | Required providers | `aws = { source = "hashicorp/aws"` → `hashicorp/aws` |
| `module "([^"]+)"\s*\{[^}]*source\s*=\s*"([^"]+)"` | Module blocks | `module "vpc" { source = "..."` |
| `resource "([^"]+)"\s+"([^"]+)"` | Resource blocks | `resource "aws_instance" "web"` |
| `data "([^"]+)"\s+"([^"]+)"` | Data sources | `data "aws_ami" "latest"` |
| `backend "([^"]+)"\s*\{([^}]*)\}` | Backend block | `backend "s3" { ... }` |

**State address parsing:**

```
terraform state list output → address parsing:

  aws_instance.web
    → type=aws_instance, name=web, module=""

  module.vpc.aws_vpc.main
    → type=aws_vpc, name=main, module=vpc

  data.aws_ami.latest
    → type=data.aws_ami, name=latest, module=""
```

**Re-exports at bottom of file:**

- From `actions.py`: `terraform_init`, `terraform_apply`, `terraform_output`, `terraform_destroy`, `terraform_workspace_select`, `terraform_fmt`
- From `generate.py`: `generate_terraform`

### `actions.py` — Mutating Operations (250 lines)

**Functions:**

| Function | Parameters | What It Does | Timeout | Audit |
|----------|-----------|-------------|---------|-------|
| `terraform_init(root, *, upgrade)` | `Path, bool` | Initialize providers + backend. `-upgrade` re-downloads. | 120s | ⚙️ Terraform Init |
| `terraform_apply(root, *, auto_approve)` | `Path, bool` | Apply plan. Output capped at 3000 chars. Parses change counts. | 300s | 🚀 Terraform Apply |
| `terraform_destroy(root, *, auto_approve)` | `Path, bool` | Tear down all managed resources. Output capped at 3000 chars. | 300s | 💥 Terraform Destroy |
| `terraform_output(root)` | `Path` | Read outputs as JSON → simplified `{key: {value, type, sensitive}}` | 30s | — |
| `terraform_workspace_select(root, workspace)` | `Path, str` | Switch workspace; creates with `workspace new` if doesn't exist | 60s | 🔀 Terraform Workspace |
| `terraform_fmt(root)` | `Path` | Format `.tf` files recursively. Returns changed file list. | 60s | ✨ Terraform Fmt |

**`terraform_output` simplification:**

```python
# Raw terraform output -json:
{"cluster_endpoint": {"value": "...", "type": "string", "sensitive": false}}

# Simplified:
{"cluster_endpoint": {"value": "...", "type": "string", "sensitive": false}}
# (extracts value, type, sensitive for each key)
```

**`terraform_workspace_select` auto-create:**

```
1. Try: terraform workspace select <name>
2. If fails → terraform workspace new <name>
3. Return: {ok, workspace, created: True/False}
```

### `generate.py` — IaC Scaffolding (658 lines)

**HCL Templates (module-level strings):**

| Template | Purpose | Generated To |
|----------|---------|-------------|
| `_MAIN_TF_TEMPLATE` | Provider + backend + resource placeholder | `terraform/main.tf` |
| `_VARIABLES_TF_TEMPLATE` | project, environment, region, tags variables | `terraform/variables.tf` |
| `_OUTPUTS_TF_TEMPLATE` | Commented-out output example | `terraform/outputs.tf` |

**Data Access Functions (lazy from DataRegistry):**

| Function | Returns |
|----------|---------|
| `_provider_blocks()` | `dict[str, dict]` — cloud provider configs (source, version, config, default_region) |
| `_backend_blocks()` | `dict[str, str]` — backend HCL templates with `{project}` and `{region}` placeholders |
| `_k8s_catalog()` | `dict[str, dict]` — per-provider K8s cluster HCL templates |

**Generator Functions:**

| Function | Parameters | What It Does |
|----------|-----------|-------------|
| `generate_terraform(root, provider, *, backend, project_name)` | `Path, str, str, str` | Scaffold standard Terraform project (4 files) |
| `generate_terraform_k8s(root, provider, *, backend, project_name, namespace, services, node_count, node_size, k8s_version)` | `Path, str, str, str, str, list[dict], int, str, str` | Cross-domain K8s cluster IaC (5 files) |
| `terraform_to_docker_registry(provider, *, project_name, region)` | `str, str, str` | Map cloud provider → Docker CI registry config |

**Supported providers for scaffolding:**

| Provider | Default Region | Cluster Resource | Default Node Size | Docker Registry |
|----------|---------------|-----------------|-------------------|----------------|
| `aws` | us-east-1 | `aws_eks_cluster` | (from catalog) | ECR |
| `google` | us-central1 | `google_container_cluster` | (from catalog) | GAR |
| `azurerm` | eastus | `azurerm_kubernetes_cluster` | (from catalog) | ACR |

**Supported backends:**

| Backend | Config Fields |
|---------|--------------|
| `local` | (default, no config) |
| `s3` | bucket, key, region, encrypt, dynamodb_table |
| `gcs` | bucket, prefix |
| `azurerm` | resource_group_name, storage_account_name, container_name, key |

**Docker Registry Map (`_DOCKER_REGISTRY_MAP`):**

```python
{
    "aws": {
        "registry_type": "ecr",
        "url_template": "{account_id}.dkr.ecr.{region}.amazonaws.com/{project}",
        "url_default": "${{ secrets.AWS_ACCOUNT_ID }}.dkr.ecr.us-east-1.amazonaws.com/{project}",
        "credentials": {"AWS_ACCESS_KEY_ID": "...", "AWS_SECRET_ACCESS_KEY": "..."},
        "login_step": "aws ecr get-login-password --region {region} | docker login ...",
    },
    "google": {
        "registry_type": "gar",
        "url_template": "{region}-docker.pkg.dev/{project}/{project}",
        ...
    },
    "azurerm": {
        "registry_type": "acr",
        "url_template": "{project_clean}.azurecr.io/{project}",
        ...
    },
}
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| **Web Routes** | `routes/terraform/status.py` | `terraform_status`, `terraform_validate`, `terraform_plan`, `terraform_state`, `terraform_workspaces` |
| **Web Routes** | `routes/terraform/actions.py` | `terraform_init`, `terraform_apply`, `terraform_destroy`, `terraform_output`, `terraform_workspace_select`, `terraform_fmt` |
| **Web Routes** | `routes/devops/__init__.py` | Terraform blueprint registration |
| **CLI** | `cli/terraform/detect.py` | `terraform_status` |
| **CLI** | `cli/terraform/observe.py` | `terraform_validate`, `terraform_plan`, `terraform_state`, `terraform_workspaces` |
| **CLI** | `cli/terraform/generate.py` | `generate_terraform`, `generate_terraform_k8s` |
| **Services** | `k8s/validate_cross_domain.py` | `terraform_to_docker_registry` |
| **Services** | `wizard/setup_infra.py` | `generate_terraform`, `generate_terraform_k8s` |
| **Services** | `wizard/helpers.py` | `terraform_status` |
| **Compat Shims** | `terraform_ops.py` | Re-exports from `terraform.ops` |
| **Compat Shims** | `terraform_actions.py` | Re-exports from `terraform.actions` |
| **Compat Shims** | `terraform_generate.py` | Re-exports from `terraform.generate` |

---

## Backward Compatibility

Three compatibility layers exist:

**1. Module-level re-exports (ops.py → actions + generate):**

```python
# ops.py bottom
from .actions import terraform_init, terraform_apply, ...
from .generate import generate_terraform
```

Old code using `from terraform.ops import terraform_init` still works.

**2. Package re-exports (__init__.py):**

```python
# __init__.py
from .ops import terraform_status, terraform_validate, ...
from .actions import terraform_init, terraform_apply, ...
from .generate import generate_terraform, generate_terraform_k8s, ...
```

Package-level imports like `from terraform import terraform_init` work.

**3. Flat-file shims (services/ root):**

```python
# services/terraform_ops.py → re-exports from terraform.ops
# services/terraform_actions.py → re-exports from terraform.actions
# services/terraform_generate.py → re-exports from terraform.generate
```

Pre-refactor imports like `from services.terraform_ops import terraform_status` work.

---

## Error Handling

| Function | Error Condition | Response |
|----------|---------------|----------|
| `terraform_status` | No .tf files | `{"has_terraform": False, ...}` (not an error) |
| `terraform_validate` | No .tf files | `{"ok": False, "error": "No Terraform files found"}` |
| `terraform_validate` | CLI missing | `{"ok": False, "error": "terraform CLI not available"}` |
| `terraform_plan` | Not initialized | `{"ok": False, "error": "Terraform not initialized. Run: terraform init"}` |
| `terraform_plan` | Timeout (120s) | `{"ok": False, "error": "terraform plan timed out (120s)"}` |
| `terraform_apply` | Timeout (300s) | `{"ok": False, "error": "terraform apply timed out (300s)"}` |
| `terraform_state` | No state file | `{"ok": True, "resources": [], "count": 0, "note": "No state file"}` |
| `terraform_output` | No outputs | `{"ok": True, "outputs": {}, "note": "No outputs defined or no state"}` |
| `terraform_workspace_select` | Missing name | `{"ok": False, "error": "Missing workspace name"}` |
| `generate_terraform` | Unknown provider | `{"error": "Unknown provider: X. Available: aws, google, azurerm"}` |
| `generate_terraform_k8s` | No K8s template | `{"error": "No K8s cluster template for provider: X"}` |
| `terraform_to_docker_registry` | Unknown provider | `{"ok": False, "error": "Unknown provider: X"}` |
| All actions | `TimeoutExpired` | `{"ok": False, "error": "... timed out"}` |
| All actions | `FileNotFoundError` | Caught by `_terraform_available()` → `{"available": False}` |

---

## Audit Trail

All audit entries use `make_auditor("terraform")`.

| Event | Icon | Action | Target |
|-------|------|--------|--------|
| Terraform init | ⚙️ | `initialized` | `terraform` |
| Terraform plan | 📋 | `planned` | `infrastructure` |
| Terraform apply | 🚀 | `applied` | `infrastructure` |
| Terraform destroy | 💥 | `destroyed` | `infrastructure` |
| Workspace switch | 🔀 | `switched` | `<workspace>` |
| Format files | ✨ | `formatted` | `terraform` |
| Scaffold generated | 📝 | `generated` | `terraform` |
| K8s IaC generated | 📝 | `generated` | `terraform-k8s` |

---

## Advanced Feature Showcase

### 1. Multi-Regex HCL Scanning Pipeline

`terraform_status` in `ops.py` scans every `.tf` file with 6 independent
regex patterns extracted in a single pass. Each captures different HCL
constructs without a full parser:

```python
# ops.py — terraform_status (lines 160-213)

for tf_file in sorted(tf_root.rglob("*.tf")):
    content = tf_file.read_text(encoding="utf-8", errors="ignore")
    rel_path = str(tf_file.relative_to(project_root))

    # 1. Provider blocks: provider "aws" {
    for m in re.finditer(r'provider\s+"([^"]+)"', content):
        providers.add(m.group(1))

    # 2. Required providers: aws = { source = "hashicorp/aws"
    for m in re.finditer(r'(\w+)\s*=\s*\{\s*source\s*=\s*"([^"]+)"', content):
        providers.add(m.group(2))

    # 3. Modules: module "vpc" { ... source = "..."
    for m in re.finditer(r'module\s+"([^"]+)"\s*\{[^}]*source\s*=\s*"([^"]+)"',
                         content, re.DOTALL):
        modules.append({"name": m.group(1), "source": m.group(2)})

    # 4. Resources: resource "aws_instance" "web"
    for m in re.finditer(r'resource\s+"([^"]+)"\s+"([^"]+)"', content):
        resources.append({"type": m.group(1), "name": m.group(2), "file": rel_path})

    # 5. Data sources: data "aws_ami" "latest" → type=data.aws_ami
    for m in re.finditer(r'data\s+"([^"]+)"\s+"([^"]+)"', content):
        resources.append({"type": f"data.{m.group(1)}", "name": m.group(2), ...})

    # 6. Backend (first found only): backend "s3" { ... }
    if not backend:
        backend_match = re.search(r'backend\s+"([^"]+)"\s*\{([^}]*)\}',
                                   content, re.DOTALL)
```

The result is a complete infrastructure inventory (providers, modules,
resources, data sources, backend) without installing any HCL parser library.
Validation delegates to `terraform validate` which uses the real parser.

### 2. Cross-Domain K8s Cluster Generation

`generate_terraform_k8s` in `generate.py` bridges three domains (Terraform,
K8s, Docker) by taking wizard state and producing multi-file HCL:

```python
# generate.py — generate_terraform_k8s (lines 218-528)

# Input: K8s wizard state → Output: 5 Terraform HCL files
def generate_terraform_k8s(
    project_root, provider="aws", *, backend="local", project_name="",
    namespace="", services=None, node_count=2, node_size="", k8s_version="",
):
    # Load provider config + K8s catalog from DataRegistry
    prov_config = _provider_blocks().get(provider)
    k8s_config = _k8s_catalog().get(provider)

    # Auto-fill from catalog
    if not node_size:
        node_size = k8s_config["default_node_size"]
    if not k8s_version:
        k8s_version = k8s_config["default_k8s_version"]

    # Detect if services need a container registry
    has_images = any(svc.get("image") for svc in services)

    # Generate: main.tf (cluster + optional registry), variables.tf,
    #           outputs.tf (cross-domain), k8s.tf (namespace), .gitignore
    # → 5 GeneratedFile objects
```

Each provider (AWS/GCP/Azure) gets completely different HCL — the cluster
resource, registry type, output references, and even variable requirements
differ. AWS EKS needs `subnet_ids`, while GKE and AKS don't. The K8s
catalog in DataRegistry provides the per-provider HCL templates.

### 3. Terraform State Address Parser

`terraform_state` in `ops.py` parses three distinct resource address formats
from `terraform state list` output:

```python
# ops.py — terraform_state (lines 415-436)

for line in result.stdout.strip().splitlines():
    parts = line.split(".")

    if parts[0] == "module":
        # module.vpc.aws_vpc.main → type=aws_vpc, name=main, module=vpc
        resource_type = parts[2]
        resource_name = parts[3]
        module = parts[1]

    elif parts[0] == "data":
        # data.aws_ami.latest → type=data.aws_ami, name=latest, module=""
        resource_type = f"data.{parts[1]}"
        resource_name = parts[2]
        module = ""

    else:
        # aws_instance.web → type=aws_instance, name=web, module=""
        resource_type = parts[0]
        resource_name = parts[1]
        module = ""
```

This handles the three address formats Terraform uses, including the
composite `module.xxx.type.name` format with the module name extracted
into a separate field for UI grouping.

### 4. Docker Registry Bridge — Provider-to-CI Mapping

`terraform_to_docker_registry` in `generate.py` maps cloud providers to
Docker CI registry configurations with provider-specific quirks:

```python
# generate.py — terraform_to_docker_registry (lines 581-657)

# Azure ACR names can't contain hyphens — clean automatically
project_clean = project_name.replace("-", "").replace("_", "")

# Default regions differ per provider
default_regions = {
    "aws": "us-east-1",
    "google": "us-central1",
    "azurerm": "eastus",
}

# URL construction: explicit region → url_template, else → url_default
if region:
    registry_url = spec["url_template"].format(**template_vars)
else:
    registry_url = spec["url_default"].format(**template_vars)

# Login commands are provider-specific:
# AWS:    aws ecr get-login-password | docker login --username AWS ...
# Google: echo '${{ secrets.GOOGLE_CREDENTIALS }}' | docker login -u _json_key ...
# Azure:  docker login {acr}.azurecr.io -u ... -p ...
```

The result includes everything a CI pipeline needs: registry URL, credentials
mapping (as GitHub Secrets references), login step, and the GHA login action.

### 5. Workspace Auto-Creation Pattern

`terraform_workspace_select` in `actions.py` implements an atomic
select-or-create pattern to avoid race conditions:

```python
# actions.py — terraform_workspace_select (lines 196-216)

# Try select first; if it doesn't exist, create it
result = _run_terraform("workspace", "select", workspace, cwd=tf_root)
if result.returncode != 0:
    result = _run_terraform("workspace", "new", workspace, cwd=tf_root)
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr.strip()}
    return {"ok": True, "workspace": workspace, "created": True}
return {"ok": True, "workspace": workspace, "created": False}
```

The `created` boolean in the response lets the UI notify the user whether
they switched to an existing workspace or created a new one.

### 6. CLI Version Detection with JSON-First + Text Fallback

`_terraform_available` in `ops.py` handles both modern and legacy Terraform
CLI versions:

```python
# ops.py — _terraform_available (lines 57-89)

# Modern: terraform version -json → structured output
try:
    result = subprocess.run(["terraform", "version", "-json"], ...)
    if result.returncode == 0:
        data = json.loads(result.stdout)
        return {"available": True, "version": data.get("terraform_version")}
except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
    pass

# Legacy fallback: terraform version → parse first line text
try:
    result = subprocess.run(["terraform", "version"], ...)
    if result.returncode == 0:
        version = result.stdout.strip().split("\n")[0]
        return {"available": True, "version": version}
except (FileNotFoundError, subprocess.TimeoutExpired):
    pass

return {"available": False, "version": None}
```

The `version -json` flag was added in Terraform 0.12. The fallback ensures
compatibility with older installations. `FileNotFoundError` is caught at
both levels so a missing binary never raises.

---

### Feature Coverage Summary

| Feature | Where | Complexity |
|---------|-------|-----------|
| 6-pattern HCL regex scanning pipeline | `ops.py` `terraform_status` | Providers, modules, resources, data sources, backend — single pass |
| Cross-domain K8s cluster generation | `generate.py` `generate_terraform_k8s` | 3 providers × 5 files × conditional registry/namespace |
| State address parsing (3 formats) | `ops.py` `terraform_state` | resource, module.x.resource, data.resource — module extraction |
| Docker registry bridge | `generate.py` `terraform_to_docker_registry` | Provider-specific URL, credentials, login — Azure name cleaning |
| Workspace auto-creation | `actions.py` `terraform_workspace_select` | Atomic select → fallback create with `created` flag |
| CLI version detection (dual format) | `ops.py` `_terraform_available` | JSON-first + text fallback + FileNotFoundError safety |

---

## Design Decisions


### Why regex-based HCL parsing instead of a full parser?

Terraform's HCL syntax is complex (nested blocks, expressions,
heredocs). A full HCL parser in Python would be a large dependency.
Regex extraction covers the 95% case (standard resource/module/provider
declarations) and is fast. For validation, we delegate to
`terraform validate` which uses the real parser.

### Why auto-approve by default for apply/destroy?

The control plane runs non-interactively. The UI confirms the action
before calling the API. Requiring interactive confirmation would
break the API flow. The plan step shows what will change, and the
user confirms in the UI before triggering apply.

### Why cross-domain generators live in terraform/generate.py?

`generate_terraform_k8s` and `terraform_to_docker_registry` bridge
Terraform with K8s and Docker domains. Placing them in `generate.py`
keeps all IaC generation logic together. The alternatives — placing
them in k8s/ or docker/ — would create awkward cross-imports and
scatter HCL template knowledge across domains.

### Why _find_tf_root searches a conventional directory list?

Convention over configuration: most projects place Terraform configs
in a `terraform/` subdirectory. The function also checks `infra/`,
`infrastructure/`, and the project root itself. This covers both standard
and simple layouts without requiring explicit configuration. The
fallback `rglob` catches unconventional structures.

### Why generate.py uses DataRegistry instead of inline templates?

Provider configs (source, version, default_region), backend templates,
and K8s cluster HCL are loaded from DataRegistry. This keeps the
generator functions clean and makes it easy to add new providers
or update versions without modifying Python code. The templates
are maintained in the data layer alongside tool recipes and other
configuration.

### Why generate.py is the largest file (658 lines)?

It contains three complete generators with embedded HCL templates,
a Docker registry mapping table, and produces 4-5 files each with
proper terraform/variables/outputs structure. The K8s generator alone
handles namespace, services, node configuration, multi-provider
variables, and cross-domain outputs. This complexity is inherent
to multi-provider IaC generation.
