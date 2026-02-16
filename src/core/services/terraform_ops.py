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


from src.core.services.audit_helpers import make_auditor

_audit = make_auditor("terraform")


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


# ═══════════════════════════════════════════════════════════════════
# Re-exports — backward compatibility
# ═══════════════════════════════════════════════════════════════════

from src.core.services.terraform_actions import (  # noqa: F401, E402
    terraform_init,
    terraform_apply,
    terraform_output,
    terraform_destroy,
    terraform_workspace_select,
    terraform_fmt,
)

from src.core.services.terraform_generate import (  # noqa: F401, E402
    generate_terraform,
)

