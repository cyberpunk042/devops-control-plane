"""
Environment & IaC operations — channel-independent service.

Covers two related domains:

1. **Environment variables** — .env file detection, parsing, comparison,
   validation, and generation.
2. **Infrastructure as Code** — detection of Terraform, Kubernetes,
   Pulumi, CloudFormation, and Ansible configurations.

Both follow the Detect → Observe → Facilitate → Act pattern.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from src.core.services.audit_helpers import make_auditor

_audit = make_auditor("env")


# ═══════════════════════════════════════════════════════════════════
#  Environment Variables
# ═══════════════════════════════════════════════════════════════════


def _env_files() -> list[str]:
    """Env file variants — loaded from DataRegistry."""
    from src.core.data import get_registry
    return get_registry().env_files


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse a .env file into a key/value dict.

    Handles:
    - KEY=value
    - KEY="value"
    - KEY='value'
    - export KEY=value
    - Comments (#)
    - Empty lines
    """
    result: dict[str, str] = {}
    if not path.is_file():
        return result

    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return result

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

    return result


def _redact_value(value: str) -> str:
    """Redact sensitive values for display."""
    if not value:
        return "(empty)"
    if len(value) <= 4:
        return "****"
    return value[:2] + "****" + value[-2:]


# ── Detect ──────────────────────────────────────────────────────


def env_status(project_root: Path) -> dict:
    """Detect .env files and their state.

    Returns:
        {
            "files": [{name, exists, var_count}, ...],
            "has_env": bool,
            "has_example": bool,
            "total_vars": int,
        }
    """
    files = []
    total_vars = 0
    has_env = False
    has_example = False

    for name in _env_files():
        path = project_root / name
        if path.is_file():
            parsed = _parse_env_file(path)
            files.append({
                "name": name,
                "exists": True,
                "var_count": len(parsed),
            })
            total_vars += len(parsed)

            if name == ".env":
                has_env = True
            if name in (".env.example", ".env.sample", ".env.template"):
                has_example = True

    return {
        "files": files,
        "has_env": has_env,
        "has_example": has_example,
        "total_vars": total_vars,
    }


# ── Observe ─────────────────────────────────────────────────────


def env_vars(project_root: Path, *, file: str = ".env", redact: bool = True) -> dict:
    """List variables in a .env file.

    Returns:
        {"ok": True, "file": str, "variables": {key: value, ...}}
    """
    path = project_root / file
    if not path.is_file():
        return {"error": f"File not found: {file}"}

    parsed = _parse_env_file(path)

    if redact:
        variables = {k: _redact_value(v) for k, v in parsed.items()}
    else:
        variables = parsed

    return {
        "ok": True,
        "file": file,
        "variables": variables,
        "count": len(variables),
    }


def env_diff(
    project_root: Path,
    *,
    source: str = ".env.example",
    target: str = ".env",
) -> dict:
    """Compare two .env files — find missing, extra, and common variables.

    Returns:
        {
            "ok": True,
            "source": str, "target": str,
            "missing": [keys in source but not target],
            "extra": [keys in target but not source],
            "common": [keys in both],
            "in_sync": bool,
        }
    """
    source_path = project_root / source
    target_path = project_root / target

    if not source_path.is_file():
        return {"error": f"Source file not found: {source}"}
    if not target_path.is_file():
        return {"error": f"Target file not found: {target}"}

    source_vars = set(_parse_env_file(source_path).keys())
    target_vars = set(_parse_env_file(target_path).keys())

    missing = sorted(source_vars - target_vars)
    extra = sorted(target_vars - source_vars)
    common = sorted(source_vars & target_vars)

    return {
        "ok": True,
        "source": source,
        "target": target,
        "missing": missing,
        "extra": extra,
        "common": common,
        "in_sync": len(missing) == 0 and len(extra) == 0,
    }


def env_validate(project_root: Path, *, file: str = ".env") -> dict:
    """Validate a .env file for common issues.

    Checks:
    - Empty values
    - Duplicate keys
    - Missing quotes on values with spaces
    - Suspicious patterns (passwords, keys, tokens with placeholder values)

    Returns:
        {"ok": True, "file": str, "issues": [...], "valid": bool}
    """
    path = project_root / file
    if not path.is_file():
        return {"error": f"File not found: {file}"}

    issues: list[dict] = []
    seen_keys: dict[str, int] = {}

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        return {"error": str(e)}

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("export "):
            stripped = stripped[7:].strip()

        if "=" not in stripped:
            issues.append({"line": i, "severity": "warning", "message": f"No '=' found: {stripped[:40]}"})
            continue

        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()

        # Duplicate check
        if key in seen_keys:
            issues.append({
                "line": i,
                "severity": "warning",
                "message": f"Duplicate key '{key}' (first at line {seen_keys[key]})",
            })
        seen_keys[key] = i

        # Empty value
        if not value:
            issues.append({
                "line": i,
                "severity": "info",
                "message": f"Empty value for '{key}'",
            })

        # Placeholder detection
        placeholder_patterns = [
            "your_", "changeme", "xxx", "todo", "fixme", "replace",
            "example", "placeholder", "<", ">",
        ]
        lower_val = value.lower()
        for pattern in placeholder_patterns:
            if pattern in lower_val:
                issues.append({
                    "line": i,
                    "severity": "warning",
                    "message": f"Possible placeholder value for '{key}'",
                })
                break

        # Unquoted value with spaces
        if " " in value and not (value.startswith('"') or value.startswith("'")):
            issues.append({
                "line": i,
                "severity": "warning",
                "message": f"Unquoted value with spaces for '{key}'",
            })

    return {
        "ok": True,
        "file": file,
        "issues": issues,
        "issue_count": len(issues),
        "valid": len([i for i in issues if i["severity"] == "warning"]) == 0,
    }


# ── Facilitate ──────────────────────────────────────────────────


def generate_env_example(project_root: Path) -> dict:
    """Generate .env.example from existing .env (redacted).

    Returns:
        {"ok": True, "file": {...}} or {"error": "..."}
    """
    from src.core.models.template import GeneratedFile

    env_path = project_root / ".env"
    if not env_path.is_file():
        return {"error": "No .env file found to generate example from"}

    parsed = _parse_env_file(env_path)
    if not parsed:
        return {"error": ".env file is empty"}

    lines = [
        "# Environment variables",
        "# Copy to .env and fill in values",
        "#",
        f"# Generated from .env ({len(parsed)} variables)",
        "",
    ]

    # Group by prefix if possible
    current_prefix = ""
    for key in sorted(parsed.keys()):
        prefix = key.split("_")[0] if "_" in key else ""
        if prefix != current_prefix and prefix:
            lines.append(f"\n# ── {prefix} ──")
            current_prefix = prefix

        lines.append(f"{key}=")

    content = "\n".join(lines) + "\n"

    file_data = GeneratedFile(
        path=".env.example",
        content=content,
        overwrite=False,
        reason=f"Generated .env.example from .env ({len(parsed)} variables)",
    )

    return {"ok": True, "file": file_data.model_dump()}


def generate_env_from_example(project_root: Path) -> dict:
    """Generate .env from .env.example with placeholder values.

    Returns:
        {"ok": True, "file": {...}} or {"error": "..."}
    """
    from src.core.models.template import GeneratedFile

    # Try multiple example file names
    example_path = None
    for name in (".env.example", ".env.sample", ".env.template"):
        p = project_root / name
        if p.is_file():
            example_path = p
            break

    if not example_path:
        return {"error": "No .env.example/.env.sample/.env.template found"}

    try:
        content = example_path.read_text(encoding="utf-8")
    except OSError as e:
        return {"error": str(e)}

    file_data = GeneratedFile(
        path=".env",
        content=content,
        overwrite=False,
        reason=f"Generated .env from {example_path.name}",
    )

    return {"ok": True, "file": file_data.model_dump()}


# ═══════════════════════════════════════════════════════════════════
# Re-exports — backward compatibility
# ═══════════════════════════════════════════════════════════════════

from src.core.services.env_infra_ops import (  # noqa: F401, E402
    iac_status,
    iac_resources,
    infra_status,
    env_card_status,
)

