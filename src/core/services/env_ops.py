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


_ENV_FILES = [
    ".env",
    ".env.local",
    ".env.development",
    ".env.staging",
    ".env.production",
    ".env.test",
    ".env.example",
    ".env.sample",
    ".env.template",
]


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

    for name in _ENV_FILES:
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
#  Infrastructure as Code
# ═══════════════════════════════════════════════════════════════════


_IAC_PROVIDERS = {
    "terraform": {
        "name": "Terraform",
        "files": ["*.tf", "*.tf.json"],
        "dirs": ["terraform", "infra", "infrastructure"],
        "cli": "terraform",
    },
    "kubernetes": {
        "name": "Kubernetes",
        "files": [],
        "dirs": ["k8s", "kubernetes", "manifests", "deploy"],
        "cli": "kubectl",
        "marker_files": ["kustomization.yaml", "kustomization.yml"],
    },
    "helm": {
        "name": "Helm",
        "files": ["Chart.yaml", "Chart.yml"],
        "dirs": ["charts", "helm"],
        "cli": "helm",
    },
    "pulumi": {
        "name": "Pulumi",
        "files": ["Pulumi.yaml", "Pulumi.yml"],
        "dirs": [],
        "cli": "pulumi",
    },
    "cloudformation": {
        "name": "CloudFormation",
        "dirs": ["cloudformation", "cfn"],
        "files": [],
        "cli": "aws",
    },
    "ansible": {
        "name": "Ansible",
        "files": ["ansible.cfg", "playbook.yml", "site.yml"],
        "dirs": ["ansible", "playbooks", "roles"],
        "cli": "ansible",
    },
}


def iac_status(project_root: Path) -> dict:
    """Detect IaC tools and configurations.

    Returns:
        {
            "providers": [{id, name, cli_available, files_found, dirs_found}, ...],
            "has_iac": bool,
        }
    """
    providers = []

    for prov_id, spec in _IAC_PROVIDERS.items():
        files_found: list[str] = []
        dirs_found: list[str] = []

        # Check files
        for pattern in spec.get("files", []):
            if "*" in pattern:
                found = list(project_root.glob(pattern))
                files_found.extend(str(p.relative_to(project_root)) for p in found[:10])
            elif (project_root / pattern).is_file():
                files_found.append(pattern)

        # Check marker files
        for mf in spec.get("marker_files", []):
            if (project_root / mf).is_file():
                files_found.append(mf)

        # Check directories
        for d in spec.get("dirs", []):
            if (project_root / d).is_dir():
                dirs_found.append(d)
                # Also check for files inside
                for ext in (".yml", ".yaml", ".tf", ".json"):
                    for f in (project_root / d).glob(f"*{ext}"):
                        if f.is_file():
                            files_found.append(str(f.relative_to(project_root)))

        if not files_found and not dirs_found:
            continue

        cli_available = shutil.which(spec.get("cli", "")) is not None if spec.get("cli") else False

        providers.append({
            "id": prov_id,
            "name": spec["name"],
            "cli": spec.get("cli", ""),
            "cli_available": cli_available,
            "files_found": files_found[:20],
            "dirs_found": dirs_found,
        })

    return {
        "providers": providers,
        "has_iac": len(providers) > 0,
    }


def iac_resources(project_root: Path) -> dict:
    """Inventory IaC resources from detected configurations.

    Returns:
        {"resources": [{provider, type, name, file}, ...]}
    """
    resources: list[dict] = []

    # Terraform: parse .tf files for resource blocks
    for tf_file in project_root.glob("**/*.tf"):
        if ".terraform" in str(tf_file):
            continue
        try:
            content = tf_file.read_text(encoding="utf-8")
            # Simple regex for resource "type" "name" { ... }
            for m in re.finditer(r'resource\s+"([^"]+)"\s+"([^"]+)"', content):
                resources.append({
                    "provider": "terraform",
                    "type": m.group(1),
                    "name": m.group(2),
                    "file": str(tf_file.relative_to(project_root)),
                })
        except OSError:
            continue

    # Kubernetes: parse YAML manifests
    k8s_dirs = ["k8s", "kubernetes", "manifests", "deploy"]
    for d in k8s_dirs:
        k8s_dir = project_root / d
        if not k8s_dir.is_dir():
            continue
        for f in k8s_dir.glob("**/*.y*ml"):
            try:
                import yaml

                docs = yaml.safe_load_all(f.read_text(encoding="utf-8"))
                for doc in docs:
                    if not isinstance(doc, dict):
                        continue
                    kind = doc.get("kind", "")
                    name = doc.get("metadata", {}).get("name", "")
                    if kind:
                        resources.append({
                            "provider": "kubernetes",
                            "type": kind,
                            "name": name or "?",
                            "file": str(f.relative_to(project_root)),
                        })
            except Exception:
                continue

    return {"resources": resources, "count": len(resources)}


# ── Combined status ─────────────────────────────────────────────


def infra_status(project_root: Path) -> dict:
    """Combined environment and IaC status.

    Returns both env_status and iac_status in a single call.
    """
    return {
        "env": env_status(project_root),
        "iac": iac_status(project_root),
    }


# ── Aggregated environment card data ────────────────────────────


def env_card_status(project_root: Path) -> dict:
    """Aggregated environment data for the DevOps dashboard card.

    Single call that returns everything the UI needs:
    - Environments from project.yml (name, default)
    - Active environment
    - Per-env: vault state, local key count
    - GitHub environments (names, availability)
    - Per-env: GitHub secret + variable counts
    - Per-env: sync status (local-only keys, github-only keys)
    - .env file inventory

    Returns:
        {
            "environments": [{
                name, default, active, vault_state,
                local_keys, gh_secrets, gh_variables,
                local_only, gh_only, in_sync
            }, ...],
            "active": str,
            "github": {available, reason},
            "env_files": [{name, exists, var_count}, ...],
            "has_env": bool,
            "total_vars": int,
        }
    """
    from src.core.config.loader import find_project_file, load_project
    from src.core.services import secrets_ops, vault_env_ops
    from src.core.services.vault_io import list_env_keys

    # ── 1. Project environments ─────────────────────────────────
    config_path = find_project_file(project_root)
    if config_path is None:
        return {"environments": [], "active": "", "github": {"available": False},
                "env_files": [], "has_env": False, "total_vars": 0}

    project = load_project(config_path)
    env_defs = [{"name": e.name, "default": e.default} for e in project.environments]

    # ── 2. Active environment ───────────────────────────────────
    active = vault_env_ops.read_active_env(project_root)

    # ── 3. GitHub environments ──────────────────────────────────
    gh_data = secrets_ops.list_environments(project_root)
    gh_env_names = set(gh_data.get("environments", []))

    # ── 4. Per-env GitHub secrets ───────────────────────────────
    gh_secrets_cache: dict[str, dict] = {}
    if gh_data.get("available"):
        for e in env_defs:
            try:
                gh_secrets_cache[e["name"]] = secrets_ops.list_gh_secrets(
                    project_root, env_name=e["name"],
                )
            except Exception:
                gh_secrets_cache[e["name"]] = {"secrets": [], "variables": []}

    # ── 5. Per-env local vault state + key counts ───────────────
    enriched_envs: list[dict] = []
    for e in env_defs:
        name = e["name"]
        is_active = name == active

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

        # Local keys
        local_keys_list = list_env_keys(env_path)
        local_key_names = {k["key"] for k in local_keys_list}
        local_count = len(local_key_names)

        # GitHub secret/variable counts + sync
        gh_info = gh_secrets_cache.get(name, {})
        gh_secret_names = set(gh_info.get("secrets", []))
        gh_var_names = set(gh_info.get("variables", []))
        gh_all = gh_secret_names | gh_var_names

        local_only = sorted(local_key_names - gh_all) if gh_data.get("available") else []
        gh_only = sorted(gh_all - local_key_names) if gh_data.get("available") else []
        in_sync = (not local_only and not gh_only) if gh_data.get("available") else None

        enriched_envs.append({
            "name": name,
            "default": e["default"],
            "active": is_active,
            "vault_state": vault_state,
            "local_keys": local_count,
            "gh_secrets": len(gh_secret_names),
            "gh_variables": len(gh_var_names),
            "local_only": local_only,
            "gh_only": gh_only,
            "in_sync": in_sync,
            "on_github": name in gh_env_names,
        })

    # ── 6. .env file inventory ──────────────────────────────────
    env_file_status = env_status(project_root)

    return {
        "environments": enriched_envs,
        "active": active,
        "github": {
            "available": gh_data.get("available", False),
            "reason": gh_data.get("reason"),
        },
        "env_files": env_file_status["files"],
        "has_env": env_file_status["has_env"],
        "total_vars": env_file_status["total_vars"],
    }
