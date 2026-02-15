"""
Terraform operations — channel-independent service.

Deep Terraform integration beyond the detection in env_ops.iac_status().
Provides Terraform init, plan, apply, state inspection, workspace
management, and module/provider template generation.

Requires ``terraform`` CLI to be installed for online operations.
Offline operations (manifest parsing, validation, generation) work
without the CLI.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _audit(label: str, summary: str, **kwargs) -> None:
    """Record an audit event if a project root is registered."""
    try:
        from src.core.context import get_project_root
        root = get_project_root()
    except Exception:
        return
    if root is None:
        return
    from src.core.services.devops_cache import record_event
    record_event(root, label=label, summary=summary, card="terraform", **kwargs)


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


_SKIP_DIRS = frozenset({
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".terraform",  # don't scan terraform cache
    "dist", "build", ".pages", ".backup",
})


def _run_terraform(
    *args: str,
    cwd: Path,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    """Run a terraform command."""
    return subprocess.run(
        ["terraform", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _terraform_available() -> dict:
    """Check if terraform CLI is available."""
    try:
        result = subprocess.run(
            ["terraform", "version", "-json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return {
                "available": True,
                "version": data.get("terraform_version", "unknown"),
            }
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass

    # Try non-json fallback
    try:
        result = subprocess.run(
            ["terraform", "version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            version = result.stdout.strip().split("\n")[0]
            return {"available": True, "version": version}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return {"available": False, "version": None}


def _find_tf_root(project_root: Path) -> Path | None:
    """Find the primary Terraform root directory."""
    # Check common locations
    for name in ("terraform", "infra", "infrastructure", "."):
        candidate = project_root / name if name != "." else project_root
        if any(candidate.glob("*.tf")):
            return candidate

    # Fallback: search for any .tf file
    for tf_file in project_root.rglob("*.tf"):
        skip = False
        for part in tf_file.relative_to(project_root).parts:
            if part in _SKIP_DIRS:
                skip = True
                break
        if not skip:
            return tf_file.parent

    return None


# ═══════════════════════════════════════════════════════════════════
#  Detect: Terraform status
# ═══════════════════════════════════════════════════════════════════


def terraform_status(project_root: Path) -> dict:
    """Detailed Terraform status.

    Returns:
        {
            "has_terraform": bool,
            "cli": {available, version},
            "root": str | None,
            "files": [{path, type}, ...],
            "providers": [str, ...],
            "modules": [{name, source}, ...],
            "resources": [{type, name, file}, ...],
            "backend": {type, config} | None,
            "initialized": bool,
        }
    """
    cli = _terraform_available()
    tf_root = _find_tf_root(project_root)

    if tf_root is None:
        return {
            "has_terraform": False,
            "cli": cli,
            "root": None,
            "files": [],
            "providers": [],
            "modules": [],
            "resources": [],
            "backend": None,
            "initialized": False,
        }

    # Scan .tf files
    tf_files: list[dict] = []
    providers: set[str] = set()
    modules: list[dict] = []
    resources: list[dict] = []
    backend: dict | None = None

    for tf_file in sorted(tf_root.rglob("*.tf")):
        skip = False
        for part in tf_file.relative_to(project_root).parts:
            if part in _SKIP_DIRS:
                skip = True
                break
        if skip:
            continue

        rel_path = str(tf_file.relative_to(project_root))
        file_type = _classify_tf_file(tf_file.name)
        tf_files.append({"path": rel_path, "type": file_type})

        try:
            content = tf_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        # Parse providers
        for m in re.finditer(r'provider\s+"([^"]+)"', content):
            providers.add(m.group(1))

        # Parse required_providers
        for m in re.finditer(r'(\w+)\s*=\s*\{\s*source\s*=\s*"([^"]+)"', content):
            providers.add(m.group(2))

        # Parse modules
        for m in re.finditer(r'module\s+"([^"]+)"\s*\{[^}]*source\s*=\s*"([^"]+)"', content, re.DOTALL):
            modules.append({"name": m.group(1), "source": m.group(2)})

        # Parse resources
        for m in re.finditer(r'resource\s+"([^"]+)"\s+"([^"]+)"', content):
            resources.append({
                "type": m.group(1),
                "name": m.group(2),
                "file": rel_path,
            })

        # Parse data sources
        for m in re.finditer(r'data\s+"([^"]+)"\s+"([^"]+)"', content):
            resources.append({
                "type": f"data.{m.group(1)}",
                "name": m.group(2),
                "file": rel_path,
            })

        # Parse backend
        if not backend:
            backend_match = re.search(r'backend\s+"([^"]+)"\s*\{([^}]*)\}', content, re.DOTALL)
            if backend_match:
                backend = {
                    "type": backend_match.group(1),
                    "file": rel_path,
                }

    # Check if initialized
    initialized = (tf_root / ".terraform").is_dir()

    rel_root = str(tf_root.relative_to(project_root)) if tf_root != project_root else "."

    return {
        "has_terraform": True,
        "cli": cli,
        "root": rel_root,
        "files": tf_files,
        "providers": sorted(providers),
        "modules": modules,
        "resources": resources,
        "resource_count": len(resources),
        "backend": backend,
        "initialized": initialized,
    }


def _classify_tf_file(name: str) -> str:
    """Classify a .tf file by its name convention."""
    name_lower = name.lower().replace(".tf", "")
    if name_lower in ("main", ""):
        return "main"
    if name_lower in ("variables", "vars"):
        return "variables"
    if name_lower == "outputs":
        return "outputs"
    if name_lower in ("providers", "provider"):
        return "providers"
    if name_lower in ("backend", "state"):
        return "backend"
    if name_lower in ("terraform", "versions"):
        return "versions"
    if name_lower in ("data", "datasources"):
        return "data"
    if name_lower.startswith("module"):
        return "modules"
    return "other"


# ═══════════════════════════════════════════════════════════════════
#  Observe: Terraform validate & plan
# ═══════════════════════════════════════════════════════════════════


def terraform_validate(project_root: Path) -> dict:
    """Run terraform validate (offline syntax check).

    Returns:
        {
            "ok": bool,
            "valid": bool,
            "errors": [{message, severity}, ...],
            "output": str,
        }
    """
    tf_root = _find_tf_root(project_root)
    if tf_root is None:
        return {"ok": False, "error": "No Terraform files found"}

    cli = _terraform_available()
    if not cli.get("available"):
        return {"ok": False, "error": "terraform CLI not available"}

    try:
        result = _run_terraform("validate", "-json", cwd=tf_root)
        try:
            data = json.loads(result.stdout)
            diagnostics = data.get("diagnostics", [])
            errors = [
                {
                    "message": d.get("summary", ""),
                    "detail": d.get("detail", ""),
                    "severity": d.get("severity", "error"),
                }
                for d in diagnostics
            ]
            return {
                "ok": True,
                "valid": data.get("valid", False),
                "errors": errors,
                "error_count": len([e for e in errors if e["severity"] == "error"]),
                "warning_count": len([e for e in errors if e["severity"] == "warning"]),
            }
        except json.JSONDecodeError:
            return {
                "ok": True,
                "valid": result.returncode == 0,
                "output": result.stdout.strip(),
                "errors": [],
            }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "terraform validate timed out"}


def terraform_plan(project_root: Path) -> dict:
    """Run terraform plan (dry-run).

    Returns:
        {
            "ok": bool,
            "changes": {add, change, destroy},
            "output": str,
        }
    """
    tf_root = _find_tf_root(project_root)
    if tf_root is None:
        return {"ok": False, "error": "No Terraform files found"}

    cli = _terraform_available()
    if not cli.get("available"):
        return {"ok": False, "error": "terraform CLI not available"}

    if not (tf_root / ".terraform").is_dir():
        return {"ok": False, "error": "Terraform not initialized. Run: terraform init"}

    try:
        result = _run_terraform("plan", "-no-color", cwd=tf_root, timeout=120)

        output = result.stdout + result.stderr
        changes = _parse_plan_output(output)

        ok = result.returncode == 0
        if ok:
            _audit(
                "📋 Terraform Plan", "Plan executed",
                action="planned", target="infrastructure",
            )
        return {
            "ok": ok,
            "changes": changes,
            "output": output.strip()[-2000:],  # Last 2000 chars
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "terraform plan timed out (120s)"}


def _parse_plan_output(output: str) -> dict:
    """Parse terraform plan output for change summary."""
    add = change = destroy = 0

    # "Plan: X to add, Y to change, Z to destroy."
    plan_match = re.search(
        r"Plan:\s+(\d+)\s+to\s+add,\s+(\d+)\s+to\s+change,\s+(\d+)\s+to\s+destroy",
        output,
    )
    if plan_match:
        add = int(plan_match.group(1))
        change = int(plan_match.group(2))
        destroy = int(plan_match.group(3))

    return {"add": add, "change": change, "destroy": destroy}


# ═══════════════════════════════════════════════════════════════════
#  Observe: State inspection
# ═══════════════════════════════════════════════════════════════════


def terraform_state(project_root: Path) -> dict:
    """List resources in terraform state.

    Returns:
        {
            "ok": bool,
            "resources": [{type, name, provider}, ...],
            "count": int,
        }
    """
    tf_root = _find_tf_root(project_root)
    if tf_root is None:
        return {"ok": False, "error": "No Terraform files found"}

    cli = _terraform_available()
    if not cli.get("available"):
        return {"ok": False, "error": "terraform CLI not available"}

    try:
        result = _run_terraform("state", "list", cwd=tf_root)

        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "no state" in stderr.lower() or "does not exist" in stderr.lower():
                return {"ok": True, "resources": [], "count": 0, "note": "No state file"}
            return {"ok": False, "error": stderr}

        resources: list[dict] = []
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue

            # Parse resource address: type.name or module.modname.type.name
            parts = line.split(".")
            if len(parts) >= 2:
                if parts[0] == "module":
                    resource_type = parts[2] if len(parts) > 2 else "?"
                    resource_name = parts[3] if len(parts) > 3 else "?"
                    module = parts[1]
                elif parts[0] == "data":
                    resource_type = f"data.{parts[1]}"
                    resource_name = parts[2] if len(parts) > 2 else "?"
                    module = ""
                else:
                    resource_type = parts[0]
                    resource_name = parts[1]
                    module = ""

                resources.append({
                    "address": line,
                    "type": resource_type,
                    "name": resource_name,
                    "module": module,
                })

        return {
            "ok": True,
            "resources": resources,
            "count": len(resources),
        }

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "terraform state list timed out"}


# ═══════════════════════════════════════════════════════════════════
#  Observe: Workspaces
# ═══════════════════════════════════════════════════════════════════


def terraform_workspaces(project_root: Path) -> dict:
    """List terraform workspaces.

    Returns:
        {
            "ok": bool,
            "current": str,
            "workspaces": [str, ...],
        }
    """
    tf_root = _find_tf_root(project_root)
    if tf_root is None:
        return {"ok": False, "error": "No Terraform files found"}

    cli = _terraform_available()
    if not cli.get("available"):
        return {"ok": False, "error": "terraform CLI not available"}

    try:
        result = _run_terraform("workspace", "list", cwd=tf_root)

        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip()}

        workspaces: list[str] = []
        current = "default"

        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if line.startswith("* "):
                current = line[2:].strip()
                workspaces.append(current)
            elif line:
                workspaces.append(line)

        return {
            "ok": True,
            "current": current,
            "workspaces": workspaces,
        }

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "terraform workspace list timed out"}


def terraform_init(project_root: Path, *, upgrade: bool = False) -> dict:
    """Run terraform init.

    Returns:
        {"ok": True, "output": "..."} or {"error": "..."}
    """
    tf_root = _find_tf_root(project_root)
    if tf_root is None:
        return {"ok": False, "error": "No Terraform files found"}

    cli = _terraform_available()
    if not cli.get("available"):
        return {"ok": False, "error": "terraform CLI not available"}

    args = ["init", "-no-color"]
    if upgrade:
        args.append("-upgrade")

    try:
        result = _run_terraform(*args, cwd=tf_root, timeout=120)
        output = result.stdout.strip() + "\n" + result.stderr.strip()
        if result.returncode != 0:
            return {"ok": False, "error": output.strip()}
        _audit(
            "⚙️ Terraform Init",
            "Terraform initialized" + (" (upgrade)" if upgrade else ""),
            action="initialized", target="terraform",
        )
        return {"ok": True, "output": output.strip()}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "terraform init timed out (120s)"}


def terraform_apply(project_root: Path, *, auto_approve: bool = True) -> dict:
    """Run terraform apply.

    Args:
        auto_approve: Skip confirmation (default True, since we're non-interactive).

    Returns:
        {"ok": True, "output": "...", "changes": {...}} or {"error": "..."}
    """
    tf_root = _find_tf_root(project_root)
    if tf_root is None:
        return {"ok": False, "error": "No Terraform files found"}

    cli = _terraform_available()
    if not cli.get("available"):
        return {"ok": False, "error": "terraform CLI not available"}

    if not (tf_root / ".terraform").is_dir():
        return {"ok": False, "error": "Terraform not initialized. Run init first."}

    args = ["apply", "-no-color"]
    if auto_approve:
        args.append("-auto-approve")

    try:
        result = _run_terraform(*args, cwd=tf_root, timeout=300)
        output = result.stdout + result.stderr
        changes = _parse_plan_output(output)
        ok = result.returncode == 0
        if ok:
            _audit(
                "🚀 Terraform Apply", "Infrastructure changes applied",
                action="applied", target="infrastructure",
            )
        return {
            "ok": ok,
            "output": output.strip()[-3000:],
            "changes": changes,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "terraform apply timed out (300s)"}


def terraform_output(project_root: Path) -> dict:
    """Get terraform outputs.

    Returns:
        {"ok": True, "outputs": {...}} or {"error": "..."}
    """
    tf_root = _find_tf_root(project_root)
    if tf_root is None:
        return {"ok": False, "error": "No Terraform files found"}

    cli = _terraform_available()
    if not cli.get("available"):
        return {"ok": False, "error": "terraform CLI not available"}

    try:
        result = _run_terraform("output", "-json", cwd=tf_root, timeout=30)
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "no outputs" in stderr.lower() or "no state" in stderr.lower():
                return {"ok": True, "outputs": {}, "note": "No outputs defined or no state"}
            return {"ok": False, "error": stderr}

        try:
            outputs = json.loads(result.stdout)
            # Simplify: extract value + type for each output
            simplified = {}
            for key, val in outputs.items():
                simplified[key] = {
                    "value": val.get("value"),
                    "type": val.get("type", "unknown"),
                    "sensitive": val.get("sensitive", False),
                }
            return {"ok": True, "outputs": simplified}
        except json.JSONDecodeError:
            return {"ok": True, "outputs": {}, "raw": result.stdout.strip()}

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "terraform output timed out"}


def terraform_destroy(project_root: Path, *, auto_approve: bool = True) -> dict:
    """Run terraform destroy.

    Returns:
        {"ok": True, "output": "..."} or {"error": "..."}
    """
    tf_root = _find_tf_root(project_root)
    if tf_root is None:
        return {"ok": False, "error": "No Terraform files found"}

    cli = _terraform_available()
    if not cli.get("available"):
        return {"ok": False, "error": "terraform CLI not available"}

    if not (tf_root / ".terraform").is_dir():
        return {"ok": False, "error": "Terraform not initialized. Run init first."}

    args = ["destroy", "-no-color"]
    if auto_approve:
        args.append("-auto-approve")

    try:
        result = _run_terraform(*args, cwd=tf_root, timeout=300)
        output = result.stdout + result.stderr
        ok = result.returncode == 0
        if ok:
            _audit(
                "💥 Terraform Destroy", "Infrastructure resources destroyed",
                action="destroyed", target="infrastructure",
            )
        return {
            "ok": ok,
            "output": output.strip()[-3000:],
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "terraform destroy timed out (300s)"}


def terraform_workspace_select(project_root: Path, workspace: str) -> dict:
    """Switch to a different terraform workspace.

    Returns:
        {"ok": True, "workspace": "..."} or {"error": "..."}
    """
    tf_root = _find_tf_root(project_root)
    if tf_root is None:
        return {"ok": False, "error": "No Terraform files found"}
    if not workspace:
        return {"ok": False, "error": "Missing workspace name"}

    cli = _terraform_available()
    if not cli.get("available"):
        return {"ok": False, "error": "terraform CLI not available"}

    try:
        # Try select first; if it doesn't exist, create it
        result = _run_terraform("workspace", "select", workspace, cwd=tf_root)
        if result.returncode != 0:
            result = _run_terraform("workspace", "new", workspace, cwd=tf_root)
            if result.returncode != 0:
                return {"ok": False, "error": result.stderr.strip()}
            _audit(
                "🔀 Terraform Workspace",
                f"Workspace '{workspace}' created and selected",
                action="switched", target=workspace,
            )
            return {"ok": True, "workspace": workspace, "created": True}
        _audit(
            "🔀 Terraform Workspace",
            f"Workspace switched to '{workspace}'",
            action="switched", target=workspace,
        )
        return {"ok": True, "workspace": workspace, "created": False}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "terraform workspace select timed out"}


def terraform_fmt(project_root: Path) -> dict:
    """Format Terraform files.

    Returns:
        {"ok": True, "files": [...], "output": "..."} or {"error": "..."}
    """
    tf_root = _find_tf_root(project_root)
    if tf_root is None:
        return {"ok": False, "error": "No Terraform files found"}

    cli = _terraform_available()
    if not cli.get("available"):
        return {"ok": False, "error": "terraform CLI not available"}

    try:
        result = _run_terraform("fmt", "-recursive", "-list=true", cwd=tf_root)
        files_changed = [f for f in result.stdout.strip().splitlines() if f.strip()]
        ok = result.returncode == 0
        if ok:
            _audit(
                "✨ Terraform Fmt", "Terraform files formatted",
                action="formatted", target="terraform",
            )
        return {
            "ok": ok,
            "files": files_changed,
            "count": len(files_changed),
            "output": result.stderr.strip() if not ok else "",
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "terraform fmt timed out"}


# ═══════════════════════════════════════════════════════════════════
#  Facilitate: Terraform scaffolding
# ═══════════════════════════════════════════════════════════════════


_MAIN_TF_TEMPLATE = '''# ── Main Terraform Configuration ─────────────────────────────────
# Generated by DevOps Control Plane

terraform {{
  required_version = ">= 1.5.0"

  required_providers {{
    {provider_block}
  }}

  {backend_block}
}}

provider "{provider}" {{
  {provider_config}
}}

# ── Resources ────────────────────────────────────────────────────

# Add your resources here
'''

_VARIABLES_TF_TEMPLATE = '''# ── Variables ────────────────────────────────────────────────────
# Generated by DevOps Control Plane

variable "project" {{
  description = "Project name"
  type        = string
  default     = "{project_name}"
}}

variable "environment" {{
  description = "Environment (dev, staging, production)"
  type        = string
  default     = "dev"

  validation {{
    condition     = contains(["dev", "staging", "production"], var.environment)
    error_message = "Environment must be dev, staging, or production."
  }}
}}

variable "region" {{
  description = "Cloud region"
  type        = string
  default     = "{default_region}"
}}

variable "tags" {{
  description = "Common resource tags"
  type        = map(string)
  default = {{
    Project     = "{project_name}"
    ManagedBy   = "terraform"
  }}
}}
'''

_OUTPUTS_TF_TEMPLATE = '''# ── Outputs ──────────────────────────────────────────────────────
# Generated by DevOps Control Plane

# output "example_id" {{
#   description = "ID of the example resource"
#   value       = resource_type.resource_name.id
# }}
'''

_PROVIDER_BLOCKS = {
    "aws": {
        "source": "hashicorp/aws",
        "version": "~> 5.0",
        "config": 'region = var.region',
        "default_region": "us-east-1",
    },
    "google": {
        "source": "hashicorp/google",
        "version": "~> 5.0",
        "config": 'project = var.project\n  region  = var.region',
        "default_region": "us-central1",
    },
    "azurerm": {
        "source": "hashicorp/azurerm",
        "version": "~> 3.0",
        "config": 'features {}',
        "default_region": "eastus",
    },
    "digitalocean": {
        "source": "digitalocean/digitalocean",
        "version": "~> 2.0",
        "config": '# token = var.do_token',
        "default_region": "nyc1",
    },
}

_BACKEND_BLOCKS = {
    "s3": '''backend "s3" {{
    bucket = "{project}-terraform-state"
    key    = "state/terraform.tfstate"
    region = "{region}"
  }}''',
    "gcs": '''backend "gcs" {{
    bucket = "{project}-terraform-state"
    prefix = "state"
  }}''',
    "azurerm": '''backend "azurerm" {{
    resource_group_name  = "terraform-state"
    storage_account_name = "{project}tfstate"
    container_name       = "state"
    key                  = "terraform.tfstate"
  }}''',
    "local": '''backend "local" {{
    path = "terraform.tfstate"
  }}''',
}


def generate_terraform(
    project_root: Path,
    provider: str = "aws",
    *,
    backend: str = "local",
    project_name: str = "",
) -> dict:
    """Generate Terraform scaffolding.

    Returns:
        {"ok": True, "files": [{path, content, reason}, ...]}
    """
    from src.core.models.template import GeneratedFile

    if not project_name:
        project_name = project_root.name

    prov_config = _PROVIDER_BLOCKS.get(provider)
    if not prov_config:
        return {"error": f"Unknown provider: {provider}. Available: {', '.join(_PROVIDER_BLOCKS.keys())}"}

    # Build provider block
    provider_block = f"""{provider} = {{
      source  = "{prov_config['source']}"
      version = "{prov_config['version']}"
    }}"""

    # Build backend block
    backend_template = _BACKEND_BLOCKS.get(backend, _BACKEND_BLOCKS["local"])
    backend_block = backend_template.format(
        project=project_name.replace("-", "").replace("_", ""),
        region=prov_config.get("default_region", "us-east-1"),
    )

    # main.tf
    main_content = _MAIN_TF_TEMPLATE.format(
        provider_block=provider_block,
        backend_block=backend_block,
        provider=provider,
        provider_config=prov_config["config"],
    )

    # variables.tf
    vars_content = _VARIABLES_TF_TEMPLATE.format(
        project_name=project_name,
        default_region=prov_config.get("default_region", "us-east-1"),
    )

    files: list[dict] = []

    files.append(GeneratedFile(
        path="terraform/main.tf",
        content=main_content,
        overwrite=False,
        reason=f"Terraform main config ({provider} provider, {backend} backend)",
    ).model_dump())

    files.append(GeneratedFile(
        path="terraform/variables.tf",
        content=vars_content,
        overwrite=False,
        reason="Terraform variables with validation",
    ).model_dump())

    files.append(GeneratedFile(
        path="terraform/outputs.tf",
        content=_OUTPUTS_TF_TEMPLATE,
        overwrite=False,
        reason="Terraform outputs (template)",
    ).model_dump())

    # .gitignore for terraform
    tf_gitignore = """# Terraform
.terraform/
*.tfstate
*.tfstate.*
*.tfplan
crash.log
*.tfvars
!terraform.tfvars.example
.terraform.lock.hcl
"""
    files.append(GeneratedFile(
        path="terraform/.gitignore",
        content=tf_gitignore,
        overwrite=False,
        reason="Terraform .gitignore",
    ).model_dump())

    _audit(
        "📝 Terraform Generated",
        f"Scaffolding generated (provider={provider}, backend={backend})",
        action="generated", target="terraform",
        after_state={"provider": provider, "backend": backend},
    )
    return {"ok": True, "files": files}
