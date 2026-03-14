"""
Detection domain registration — wires detect/probe functions into the mediator tree.

Registers 13 nodes matching the devops cache's compute registry::

    detect.docker     — Docker daemon, compose, images        (TTL=120s)
    detect.k8s        — kubectl, helm, manifests, cluster     (TTL=120s)
    detect.git        — Remote, branch, HEAD, status          (TTL=30s)
    detect.github     — GitHub CLI, auth, repo                (TTL=120s)
    detect.ci         — CI workflows, pipeline status         (TTL=120s)
    detect.terraform  — Terraform files, state                (TTL=120s)
    detect.env        — Environment variables, .env files     (TTL=60s)
    detect.security   — Secret scan + security posture        (TTL=120s)
    detect.packages   — Package status                        (TTL=120s)
    detect.quality    — Code quality metrics                  (TTL=120s)
    detect.testing    — Test status                           (TTL=120s)
    detect.docs       — Documentation status                  (TTL=120s)
    detect.dns        — DNS/CDN configuration                 (TTL=120s)

All nodes depend on ``index.classify`` — when the project's file
composition changes (detected by the FS watcher), the cascade
invalidates all detection cache entries::

    index.scan → index.classify → detect.* → devops.* → posture.*

This is the trilateral bridge: one filesystem signal at the root
propagates through the entire mediator tree.

Phase 3 added devops.* nodes that depend on these, enabling automatic
cascade invalidation through devops into posture.

Resolvers point to the RAW ops functions (same as the devops cache's
``_ensure_registry()`` in ``routes/devops/__init__.py``).
"""

from __future__ import annotations

import logging

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.tree import TreeRegistration

logger = logging.getLogger(__name__)


def register_detect(mediator: QueryMediator) -> None:
    """Register detect.* nodes in the mediator tree.

    Each node wraps an existing ops function that performs environment
    detection via subprocess calls, file scanning, or API checks.
    The mediator provides TTL-based caching where none existed before.

    Parameters
    ----------
    mediator : QueryMediator
        The initialized mediator instance.
    """
    tree = mediator.tree
    root = mediator.project_root

    # ── Deferred imports (avoid circular imports at module load) ──
    from src.core.services import (
        dns_cdn_ops,
        docker_ops,
        docs_ops,
        env_ops,
        k8s_ops,
        package_ops,
        quality_ops,
        security_ops,
        testing_ops,
    )
    from src.core.services import ci_ops
    from src.core.services import git_ops
    from src.core.services.terraform import ops as terraform_ops

    # ── Security has a composite resolver ──────────────────────────
    def _compute_security():
        scan = security_ops.scan_secrets(root)
        posture = security_ops.security_posture(root)
        return {
            "findings": scan.get("findings", []),
            "finding_count": scan.get("count", 0),
            "posture": posture,
        }

    # ── Infrastructure detection (subprocess-heavy) ────────────────

    tree.register(TreeRegistration(
        path="detect.docker",
        resolver=lambda: docker_ops.docker_status(root),
        ttl=120,
        persist=True,
        mtime_paths=[
            "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
            ".dockerignore",
        ],
    ))

    tree.register(TreeRegistration(
        path="detect.k8s",
        resolver=lambda: k8s_ops.k8s_status(root),
        ttl=120,
        persist=True,
        mtime_paths=[
            "k8s/", "kubernetes/", "deploy/", "charts/",
            "kustomization.yaml", "kustomization.yml",
        ],
    ))

    tree.register(TreeRegistration(
        path="detect.terraform",
        resolver=lambda: terraform_ops.terraform_status(root),
        ttl=120,
        persist=True,
        mtime_paths=[
            "terraform/", "infra/",
            "main.tf", "variables.tf", "outputs.tf",
        ],
    ))

    tree.register(TreeRegistration(
        path="detect.dns",
        resolver=lambda: dns_cdn_ops.dns_cdn_status(root),
        ttl=120,
        persist=True,
        mtime_paths=[
            "netlify.toml", "vercel.json", "wrangler.toml",
            "CNAME", "cloudflare/",
        ],
    ))

    # ── VCS detection ──────────────────────────────────────────────

    tree.register(TreeRegistration(
        path="detect.git",
        resolver=lambda: git_ops.git_status(root),
        ttl=30,              # shorter — git status changes frequently
        mtime_paths=[".git/HEAD", ".git/index", ".gitignore"],
    ))

    tree.register(TreeRegistration(
        path="detect.github",
        resolver=lambda: git_ops.gh_status(root),
        ttl=120,
        persist=True,
        mtime_paths=[".github/"],
    ))

    tree.register(TreeRegistration(
        path="detect.ci",
        resolver=lambda: ci_ops.ci_status(root),
        ttl=120,
        persist=True,
        mtime_paths=[
            ".github/workflows/", ".gitlab-ci.yml",
            "Jenkinsfile", ".circleci/",
        ],
    ))

    # ── Code analysis detection ────────────────────────────────────

    tree.register(TreeRegistration(
        path="detect.security",
        resolver=_compute_security,
        ttl=120,
        persist=True,
        mtime_paths=[".gitignore", ".gitignore.global", "src/"],
    ))

    tree.register(TreeRegistration(
        path="detect.packages",
        resolver=lambda: package_ops.package_status_enriched(root),
        ttl=120,
        persist=True,
        mtime_paths=[
            "requirements.txt", "requirements-dev.txt", "pyproject.toml",
            "package.json", "package-lock.json",
            "Cargo.toml", "go.mod", "Pipfile",
        ],
    ))

    tree.register(TreeRegistration(
        path="detect.quality",
        resolver=lambda: quality_ops.quality_status(root),
        ttl=120,
        persist=True,
        mtime_paths=[
            "pyproject.toml", ".ruff.toml", "ruff.toml",
            "mypy.ini", ".mypy.ini",
            ".eslintrc.json", ".eslintrc.js", ".prettierrc",
            "biome.json", "setup.cfg",
        ],
    ))

    tree.register(TreeRegistration(
        path="detect.testing",
        resolver=lambda: testing_ops.testing_status(root),
        ttl=120,
        persist=True,
        mtime_paths=[
            "tests/", "pyproject.toml", "package.json", "setup.cfg",
        ],
    ))

    tree.register(TreeRegistration(
        path="detect.docs",
        resolver=lambda: docs_ops.docs_status(root),
        ttl=120,
        persist=True,
        mtime_paths=[
            "docs/", "README.md", "CHANGELOG.md", "LICENSE",
            "CONTRIBUTING.md", "openapi.yaml", "openapi.json",
        ],
    ))

    # ── Environment detection ──────────────────────────────────────

    tree.register(TreeRegistration(
        path="detect.env",
        resolver=lambda: env_ops.env_card_status(root),
        ttl=60,              # shorter — env files change occasionally
        mtime_paths=[
            ".env", ".env.active", ".env.vault",
            "project.yml", "project.yaml",
        ],
    ))

    # ── Wizard detection ────────────────────────────────────────────

    def _resolve_wiz_detect():
        from src.core.services.wizard_ops import wizard_detect
        return wizard_detect(root)

    tree.register(TreeRegistration(
        path="detect.wizard",
        resolver=_resolve_wiz_detect,
        ttl=120,
        persist=True,
        mtime_paths=[
            "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
            ".github/workflows/", "k8s/", "kubernetes/",
            "terraform/", "main.tf", "project.yml",
            "pyproject.toml", "package.json",
        ],
    ))

    logger.debug("registered detect.* nodes (14 total)")
