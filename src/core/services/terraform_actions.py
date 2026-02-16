"""
Terraform mutating actions — init, apply, destroy, output, workspace, fmt.

Channel-independent: no Flask, no HTTP dependency.
Requires ``terraform`` CLI for all operations.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from src.core.services.terraform_ops import (
    _run_terraform,
    _terraform_available,
    _find_tf_root,
    _parse_plan_output,
)
from src.core.services.audit_helpers import make_auditor

_audit = make_auditor("terraform")


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
    import json

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
