"""
Server-side cache for DevOps status endpoints.

Caches results to ``state/devops_cache.json`` with mtime-based
change detection.  Results are returned instantly when nothing
relevant has changed on disk.

Also manages per-card user preferences (auto / manual / hidden).
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

_CACHE_FILE = "state/devops_cache.json"
_PREFS_FILE = "state/devops_prefs.json"

# ── Default card preferences ────────────────────────────────────

_DEFAULT_PREFS: dict[str, str] = {
    "security": "auto",
    "testing": "auto",
    "quality": "auto",
    "packages": "auto",
    "env": "auto",
    "docs": "auto",
    "k8s": "auto",
    "terraform": "auto",
    "dns": "auto",
}

# ── Watch paths per card ────────────────────────────────────────
#
# If ANY of these files/dirs has mtime > cache timestamp, the
# cached result is stale and must be recomputed.

_WATCH_PATHS: dict[str, list[str]] = {
    "security": [
        ".gitignore", ".gitignore.global", "src/",
    ],
    "testing": [
        "tests/", "pyproject.toml", "package.json", "setup.cfg",
    ],
    "quality": [
        "pyproject.toml", ".ruff.toml", "ruff.toml",
        "mypy.ini", ".mypy.ini",
        ".eslintrc.json", ".eslintrc.js", ".prettierrc",
        "biome.json", "setup.cfg",
    ],
    "packages": [
        "requirements.txt", "requirements-dev.txt", "pyproject.toml",
        "package.json", "package-lock.json",
        "Cargo.toml", "go.mod", "Pipfile",
    ],
    "env": [
        ".env", ".env.active", ".env.vault",
        "project.yml", "project.yaml",
    ],
    "docs": [
        "docs/", "README.md", "CHANGELOG.md", "LICENSE",
        "CONTRIBUTING.md", "openapi.yaml", "openapi.json",
    ],
    "k8s": [
        "k8s/", "kubernetes/", "deploy/", "charts/",
        "kustomization.yaml", "kustomization.yml",
    ],
    "terraform": [
        "terraform/", "infra/",
        "main.tf", "variables.tf", "outputs.tf",
    ],
    "dns": [
        "netlify.toml", "vercel.json", "wrangler.toml",
        "CNAME", "cloudflare/",
    ],
}


# ── Internal helpers ────────────────────────────────────────────


def _cache_path(project_root: Path) -> Path:
    return project_root / _CACHE_FILE


def _prefs_path(project_root: Path) -> Path:
    return project_root / _PREFS_FILE


def _load_cache(project_root: Path) -> dict:
    path = _cache_path(project_root)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _save_cache(project_root: Path, cache: dict) -> None:
    path = _cache_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, default=str), encoding="utf-8")


def _max_mtime(project_root: Path, watch_paths: list[str]) -> float:
    """Get the most recent mtime among the watch paths."""
    max_mt = 0.0
    for rel in watch_paths:
        p = project_root / rel
        try:
            st = os.stat(p)
            max_mt = max(max_mt, st.st_mtime)
        except (FileNotFoundError, OSError):
            pass
    return max_mt


# ── Public API: caching ─────────────────────────────────────────


def get_cached(
    project_root: Path,
    card_key: str,
    compute_fn: Callable[[], dict],
    *,
    force: bool = False,
) -> dict:
    """Return cached card data, recomputing only when files change.

    The returned dict gets an extra ``_cache`` key with metadata:

    .. code-block:: json

        {"computed_at": 1707..., "fresh": true, "age_seconds": 42}

    Args:
        project_root: Project root path.
        card_key:     One of the 9 card keys (security, testing, …).
        compute_fn:   Zero-arg callable that returns the status dict.
        force:        If True, ignore cache and recompute.
    """
    cache = _load_cache(project_root)
    entry = cache.get(card_key)
    watch = _WATCH_PATHS.get(card_key, [])

    current_mtime = _max_mtime(project_root, watch)

    # ── Check if cache is still valid ───────────────────────────
    if not force and entry:
        cached_at: float = entry.get("cached_at", 0)
        cached_mtime: float = entry.get("mtime", 0)

        if current_mtime <= cached_mtime:
            # Nothing changed — return cached data
            data = entry["data"]
            data["_cache"] = {
                "computed_at": cached_at,
                "fresh": True,
                "age_seconds": round(time.time() - cached_at),
            }
            logger.debug("cache HIT for %s (age %ds)", card_key,
                         round(time.time() - cached_at))
            return data

    # ── Recompute ───────────────────────────────────────────────
    t0 = time.time()
    data = compute_fn()
    elapsed = round(time.time() - t0, 3)

    now = time.time()
    cache[card_key] = {
        "data": data,
        "cached_at": now,
        "mtime": current_mtime if current_mtime > 0 else now,
        "elapsed_s": elapsed,
    }
    _save_cache(project_root, cache)

    data["_cache"] = {
        "computed_at": now,
        "fresh": False,
        "age_seconds": 0,
    }
    logger.debug("cache MISS for %s (computed in %.2fs)", card_key, elapsed)
    return data


def invalidate(project_root: Path, card_key: str) -> None:
    """Invalidate a single card's server cache."""
    cache = _load_cache(project_root)
    if card_key in cache:
        del cache[card_key]
        _save_cache(project_root, cache)


def invalidate_all(project_root: Path) -> None:
    """Invalidate all server-side caches."""
    _save_cache(project_root, {})


# ── Public API: preferences ─────────────────────────────────────


def load_prefs(project_root: Path) -> dict:
    """Load card preferences (auto / manual / hidden per card)."""
    path = _prefs_path(project_root)
    prefs = dict(_DEFAULT_PREFS)
    if path.exists():
        try:
            user_prefs = json.loads(path.read_text(encoding="utf-8"))
            for key in _DEFAULT_PREFS:
                if key in user_prefs and user_prefs[key] in ("auto", "manual", "hidden"):
                    prefs[key] = user_prefs[key]
        except (json.JSONDecodeError, IOError):
            pass
    return prefs


def save_prefs(project_root: Path, prefs: dict) -> dict:
    """Save card preferences.  Returns the validated result."""
    valid: dict[str, str] = {}
    for key in _DEFAULT_PREFS:
        if key in prefs and prefs[key] in ("auto", "manual", "hidden"):
            valid[key] = prefs[key]
        else:
            valid[key] = _DEFAULT_PREFS[key]

    path = _prefs_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(valid, indent=2), encoding="utf-8")
    return valid
