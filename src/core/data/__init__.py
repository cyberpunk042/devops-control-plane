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
