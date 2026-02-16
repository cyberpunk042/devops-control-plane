"""
Environment infrastructure — IaC detection and environment card aggregation.

Extracted from env_ops.py. Handles:
- IaC provider detection (Terraform, Kubernetes, etc.)
- IaC resource inventory
- Combined env + IaC status
- Aggregated environment card data for the dashboard

Channel-independent.
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  Infrastructure as Code
# ═══════════════════════════════════════════════════════════════════


def _iac_providers() -> dict[str, dict]:
    """IaC provider detection catalog — loaded from DataRegistry."""
    from src.core.data import get_registry
    return get_registry().iac_providers


def iac_status(project_root: Path) -> dict:
    """Detect IaC tools and configurations.

    Returns:
        {
            "providers": [{id, name, cli_available, files_found, dirs_found}, ...],
            "has_iac": bool,
        }
    """
    providers = []

    for prov_id, spec in _iac_providers().items():
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
    from src.core.services.env_ops import env_status

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
    from src.core.services.env_ops import env_status
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
