"""
Central data registry for static catalogs and patterns.

Loads base catalogs from ``src/core/data/catalogs/`` once at first access
and caches them for the process lifetime.  Everything downstream (CLI,
TUI, Web) reads from this single source of truth.

Usage::

    from src.core.data import DataRegistry

    registry = DataRegistry()
    services = registry.infra_services   # list[dict]
    patterns = registry.secret_patterns  # frozenset[str]

    # For Jinja injection into the web layer:
    js_data = registry.to_js_dict()
"""

from __future__ import annotations

import json
import logging
from functools import cached_property
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent


def _load_json(relative_path: str) -> list | dict:
    """Load a JSON file relative to the data directory."""
    path = _DATA_DIR / relative_path
    if not path.exists():
        logger.warning("Data file not found: %s", path)
        return [] if relative_path.endswith("s.json") else {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class DataRegistry:
    """Central registry for all static data catalogs.

    Each property lazily loads its JSON file on first access and caches
    the result for the lifetime of the instance.  Create one instance
    per process (store on ``app.config`` for Flask, or as a module-level
    singleton for CLI).
    """

    # ── Infrastructure services ──────────────────────────────────

    @cached_property
    def infra_services(self) -> list[dict]:
        """60+ infrastructure service definitions (Postgres, Redis, …)."""
        data = _load_json("catalogs/infra_services.json")
        logger.debug("Loaded %d infrastructure service definitions", len(data))
        return data

    @cached_property
    def infra_categories(self) -> dict[str, str]:
        """Category key → display label mapping (e.g. 'db-rel' → '🗄️ …')."""
        data = _load_json("catalogs/infra_categories.json")
        logger.debug("Loaded %d infrastructure categories", len(data))
        return data

    # ── Docker ───────────────────────────────────────────────────

    @cached_property
    def docker_defaults(self) -> dict[str, dict]:
        """Stack family → Dockerfile defaults (images, cmd, port, …)."""
        data = _load_json("catalogs/docker_defaults.json")
        logger.debug("Loaded %d Docker stack family defaults", len(data))
        return data

    @cached_property
    def docker_options(self) -> dict[str, list]:
        """Docker wizard options (restart policies, platforms)."""
        data = _load_json("catalogs/docker_options.json")
        logger.debug("Loaded Docker options: %s", list(data.keys()))
        return data

    # ── Kubernetes ────────────────────────────────────────────────

    @cached_property
    def storage_classes(self) -> list[dict]:
        """Well-known K8s StorageClass catalog, grouped by provider."""
        data = _load_json("catalogs/storage_classes.json")
        logger.debug("Loaded %d StorageClass groups", len(data))
        return data

    @cached_property
    def k8s_kinds(self) -> list[str]:
        """K8s resource kinds for the manifest wizard."""
        data = _load_json("catalogs/k8s_kinds.json")
        logger.debug("Loaded %d K8s resource kinds", len(data))
        return data

    # ── Card labels ──────────────────────────────────────────────

    @cached_property
    def card_labels(self) -> dict[str, str]:
        """Card key → display label (e.g. 'security' → '🔐 Security Posture')."""
        data = _load_json("catalogs/card_labels.json")
        logger.debug("Loaded %d card labels", len(data))
        return data

    # ── IaC providers ────────────────────────────────────────────

    @cached_property
    def iac_providers(self) -> dict[str, dict]:
        """IaC provider detection catalog (Terraform, K8s, Helm, …)."""
        data = _load_json("catalogs/iac_providers.json")
        logger.debug("Loaded %d IaC provider definitions", len(data))
        return data

    # ── Mesh annotations ─────────────────────────────────────────

    @cached_property
    def mesh_annotations(self) -> dict[str, dict]:
        """Service mesh annotation prefixes (Istio, Linkerd, Consul, Kuma)."""
        data = _load_json("catalogs/mesh_annotations.json")
        logger.debug("Loaded %d mesh annotation providers", len(data))
        return data

    # ── Terraform ────────────────────────────────────────────────

    @cached_property
    def terraform_providers(self) -> dict[str, dict]:
        """Cloud provider configs for Terraform scaffolding."""
        data = _load_json("catalogs/terraform_providers.json")
        logger.debug("Loaded %d Terraform provider configs", len(data))
        return data

    @cached_property
    def terraform_backends(self) -> dict[str, str]:
        """HCL backend templates for Terraform scaffolding."""
        data = _load_json("catalogs/terraform_backends.json")
        logger.debug("Loaded %d Terraform backend templates", len(data))
        return data

    # ── Security catalogs ────────────────────────────────────────

    @cached_property
    def sensitive_files(self) -> list[list]:
        """Sensitive file detection patterns [glob, description]."""
        data = _load_json("catalogs/sensitive_files.json")
        logger.debug("Loaded %d sensitive file patterns", len(data))
        return data

    @cached_property
    def gitignore_patterns(self) -> dict:
        """Stack-specific + universal .gitignore patterns."""
        data = _load_json("catalogs/gitignore_patterns.json")
        logger.debug("Loaded gitignore patterns for %d stacks",
                      len(data.get("stacks", {})))
        return data

    # ── Docs ─────────────────────────────────────────────────────

    @cached_property
    def api_spec_files(self) -> list[list]:
        """API spec file detection patterns [filename, type, format]."""
        data = _load_json("catalogs/api_spec_files.json")
        logger.debug("Loaded %d API spec patterns", len(data))
        return data

    # ── Environment ──────────────────────────────────────────────

    @cached_property
    def env_files(self) -> list[str]:
        """Standard .env file variants to scan for."""
        data = _load_json("catalogs/env_files.json")
        logger.debug("Loaded %d env file patterns", len(data))
        return data

    # ── Metrics ──────────────────────────────────────────────────

    @cached_property
    def health_weights(self) -> dict[str, int]:
        """Health score weights per dimension (sums to 100)."""
        data = _load_json("catalogs/health_weights.json")
        logger.debug("Loaded %d health weight dimensions", len(data))
        return data

    # ── Integration graph ────────────────────────────────────────

    @cached_property
    def integration_graph(self) -> dict:
        """Integration setup order and dependency map."""
        data = _load_json("catalogs/integration_graph.json")
        logger.debug("Loaded integration graph: %d integrations",
                      len(data.get("order", [])))
        return data

    # ── Secret file patterns ─────────────────────────────────────

    @cached_property
    def secret_file_patterns(self) -> list[str]:
        """Static secret file patterns for vault detection."""
        data = _load_json("catalogs/secret_file_patterns.json")
        logger.debug("Loaded %d secret file patterns", len(data))
        return data

    # ── Patterns ─────────────────────────────────────────────────

    @cached_property
    def secret_patterns(self) -> frozenset[str]:
        """Substrings that indicate a key holds a secret value."""
        data = _load_json("patterns/secret_patterns.json")
        result = frozenset(data)
        logger.debug("Loaded %d secret key patterns", len(result))
        return result

    # ── .env Templates ───────────────────────────────────────────

    @cached_property
    def env_templates(self) -> list[dict]:
        """.env template sections (Content Vault, Database, API Keys, …)."""
        data = _load_json("templates/env_sections.json")
        logger.debug("Loaded %d .env template sections", len(data))
        return data

    # ── Serialization for JS injection ───────────────────────────

    def to_js_dict(self) -> dict:
        """Return all catalogs as a JSON-serializable dict.

        Used by the web layer to inject static data into Jinja templates::

            window._dcp = {{ registry.to_js_dict() | tojson | safe }};
        """
        return {
            "infraOptions": self.infra_services,
            "infraCategories": self.infra_categories,
            "dockerDefaults": self.docker_defaults,
            "dockerOptions": self.docker_options,
            "storageClasses": self.storage_classes,
            "k8sKinds": self.k8s_kinds,
            "secretPatterns": list(self.secret_patterns),
            "cardLabels": self.card_labels,
        }


# ── Module-level singleton ───────────────────────────────────────

_registry: DataRegistry | None = None


def get_registry() -> DataRegistry:
    """Return the process-level DataRegistry singleton.

    Creates the instance on first call; subsequent calls return the
    same object.  Thread-safe enough for CPython (GIL protects the
    simple attribute check).
    """
    global _registry  # noqa: PLW0603
    if _registry is None:
        _registry = DataRegistry()
    return _registry


# ── Convenience helpers ──────────────────────────────────────────


def classify_key(key_name: str) -> str:
    """Classify a key as ``'secret'`` or ``'config'`` based on name patterns.

    This is the single source of truth — importable from anywhere::

        from src.core.data import classify_key
        kind = classify_key("DATABASE_PASSWORD")  # → "secret"
    """
    lower = key_name.lower()
    for pattern in get_registry().secret_patterns:
        if pattern in lower:
            return "secret"
    return "config"
