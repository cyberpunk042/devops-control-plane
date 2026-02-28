"""
Wizard dispatcher — routes setup actions + config deletion.

Maps action strings ("setup_git", "setup_docker", …) to their
handler functions and provides bulk config deletion.

Channel-independent: no Flask or HTTP dependency.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.core.services.wizard.setup_git import setup_git, setup_github
from src.core.services.wizard.setup_infra import (
    setup_docker,
    setup_k8s,
    setup_terraform,
    setup_pages,
)
from src.core.services.wizard.setup_ci import setup_ci
from src.core.services.wizard.setup_dns import setup_dns

logger = logging.getLogger(__name__)


# ── Dispatcher ──────────────────────────────────────────────────────

_SETUP_ACTIONS = {
    "setup_git": setup_git,
    "setup_github": setup_github,
    "setup_docker": setup_docker,
    "setup_k8s": setup_k8s,
    "setup_ci": setup_ci,
    "setup_terraform": setup_terraform,
    "setup_dns": setup_dns,
    "setup_pages": setup_pages,
}


def wizard_setup(root: Path, action: str, data: dict) -> dict:
    """Dispatch a wizard setup action.

    Returns:
        {"ok": True, ...} on success
        {"ok": False, "error": "..."} on failure
    """
    fn = _SETUP_ACTIONS.get(action)
    if not fn:
        return {"ok": False, "error": f"Unknown action: {action}"}
    return fn(root, data)


# ── Delete generated configs ───────────────────────────────────────


def delete_generated_configs(root: Path, target: str) -> dict:
    """Delete wizard-generated config files.

    Args:
        target: "docker" | "k8s" | "ci" | "skaffold" | "terraform" | "dns" | "all"
    """
    import shutil as _shutil

    from src.core.services import devops_cache

    deleted: list[str] = []
    errors: list[str] = []

    targets = [target] if target != "all" else [
        "docker", "k8s", "ci", "skaffold", "terraform", "dns",
    ]

    for t in targets:
        try:
            if t == "docker":
                for f in ["Dockerfile", ".dockerignore"]:
                    fp = root / f
                    if fp.is_file():
                        fp.unlink()
                        deleted.append(f)
                for f in root.glob("docker-compose*.y*ml"):
                    rel = str(f.relative_to(root))
                    f.unlink()
                    deleted.append(rel)
            elif t == "k8s":
                k8s_dir = root / "k8s"
                if k8s_dir.is_dir():
                    _shutil.rmtree(k8s_dir)
                    deleted.append("k8s/")
            elif t == "ci":
                for ci_file in ["ci.yml", "lint.yml"]:
                    ci = root / ".github" / "workflows" / ci_file
                    if ci.is_file():
                        ci.unlink()
                        deleted.append(f".github/workflows/{ci_file}")
            elif t == "terraform":
                tf_dir = root / "terraform"
                if tf_dir.is_dir():
                    _shutil.rmtree(tf_dir)
                    deleted.append("terraform/")
            elif t == "skaffold":
                sf = root / "skaffold.yaml"
                if sf.is_file():
                    sf.unlink()
                    deleted.append("skaffold.yaml")
            elif t == "dns":
                dns_dir = root / "dns"
                if dns_dir.is_dir():
                    _shutil.rmtree(dns_dir)
                    deleted.append("dns/")
                cdn_dir = root / "cdn"
                if cdn_dir.is_dir():
                    _shutil.rmtree(cdn_dir)
                    deleted.append("cdn/")
                cname = root / "CNAME"
                if cname.is_file():
                    cname.unlink()
                    deleted.append("CNAME")
            else:
                errors.append(f"Unknown target: {t}")
        except Exception as e:
            errors.append(f"{t}: {e}")

    devops_cache.record_event(
        root,
        label="🗑️ Wizard Config Deleted",
        summary=(
            f"Wizard config deleted: {', '.join(deleted) or 'nothing'}"
            + (f" ({len(errors)} error(s))" if errors else "")
        ),
        detail={"target": target, "deleted": deleted, "errors": errors},
        card="wizard",
        action="deleted",
        target=target,
    )

    return {
        "ok": len(errors) == 0,
        "deleted": deleted,
        "errors": errors,
    }
