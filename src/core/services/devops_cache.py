"""
Server-side cache for DevOps status endpoints.

Caches results to ``.state/devops_cache.json`` with mtime-based
change detection.  Results are returned instantly when nothing
relevant has changed on disk.

Also manages per-card user preferences (auto / manual / hidden).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

_CACHE_FILE = ".state/devops_cache.json"
_PREFS_FILE = ".state/devops_prefs.json"
_ACTIVITY_FILE = ".state/audit_activity.json"
_ACTIVITY_MAX = 200  # keep last N entries

# ── Thread safety ───────────────────────────────────────────────
# Per-key lock: prevents duplicate computation when concurrent
# requests hit the same endpoint (e.g., two tabs both requesting
# /k8s/status on cold cache — only one thread computes, the other
# waits and gets the cached result).
# File lock: prevents write corruption when saving the JSON file.
_key_locks: dict[str, threading.Lock] = {}
_key_locks_guard = threading.Lock()
_file_lock = threading.Lock()


def _get_key_lock(key: str) -> threading.Lock:
    """Get or create a lock for a specific cache key."""
    with _key_locks_guard:
        if key not in _key_locks:
            _key_locks[key] = threading.Lock()
        return _key_locks[key]

# ── Default card preferences ────────────────────────────────────
# Covers both DevOps tab cards and Integrations tab cards.
# Values: "auto" | "manual" | "hidden"

_DEFAULT_PREFS: dict[str, str] = {
    # DevOps tab
    "security": "auto",
    "testing": "auto",
    "quality": "auto",
    "packages": "auto",
    "env": "auto",
    "docs": "auto",
    "k8s": "auto",
    "terraform": "auto",
    "dns": "hidden",       # No integration card yet — hide by default
    # Integrations tab
    "int:git": "auto",
    "int:github": "auto",
    "int:ci": "auto",
    "int:docker": "auto",
    "int:k8s": "auto",
    "int:terraform": "auto",
    "int:pages": "auto",
}

# ── Card scope sets ─────────────────────────────────────────────
# Used for scoped invalidation: each tab only busts its own cards.

DEVOPS_KEYS: set[str] = {
    "security", "testing", "quality", "packages",
    "env", "docs", "k8s", "terraform", "dns",
}

INTEGRATION_KEYS: set[str] = {
    "git", "github", "ci", "docker", "k8s", "terraform", "pages",
}

AUDIT_KEYS: set[str] = {
    "audit:scores", "audit:system", "audit:deps",
    "audit:structure", "audit:clients",
    # L2 on-demand cards — also bust on full audit refresh
    "audit:scores:enriched", "audit:l2:structure",
    "audit:l2:quality", "audit:l2:repo", "audit:l2:risks",
}

# All card keys that go through get_cached()
ALL_CARD_KEYS: set[str] = DEVOPS_KEYS | INTEGRATION_KEYS | AUDIT_KEYS

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
    # ── Audit cache keys ────────────────────────────────────
    "audit:system": [
        "project.yml", "stacks/",
    ],
    "audit:deps": [
        "pyproject.toml", "requirements.txt", "requirements-dev.txt",
        "package.json", "package-lock.json",
        "Cargo.toml", "go.mod", "Gemfile", "mix.exs",
    ],
    "audit:structure": [
        "project.yml", "src/", "Dockerfile",
        "docker-compose.yml", "docker-compose.yaml",
        ".github/workflows/", "Makefile",
    ],
    "audit:clients": [
        "pyproject.toml", "requirements.txt",
        "package.json", "go.mod", "Cargo.toml",
    ],
    "audit:scores": [
        "pyproject.toml", "requirements.txt",
        "package.json", "project.yml",
        "tests/", "docs/", ".gitignore",
    ],
    # ── Wizard detect cache key ────────────────────────────────
    "wiz:detect": [
        "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
        ".github/workflows/", "k8s/", "kubernetes/",
        "terraform/", "main.tf", "project.yml",
        "pyproject.toml", "package.json",
    ],
    # ── Project-level aggregate ────────────────────────────────
    "project-status": [
        ".git/HEAD", ".git/index",
        ".github/workflows/",
        "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
        "k8s/", "kubernetes/",
        "terraform/", "main.tf",
        "project.yml",
        "CNAME", "netlify.toml", "vercel.json",
    ],
    # ── Integration cards ──────────────────────────────────────
    "git": [
        ".git/HEAD", ".git/index", ".gitignore",
    ],
    "github": [
        ".github/", ".git/config",
    ],
    "ci": [
        ".github/workflows/", ".gitlab-ci.yml", "Jenkinsfile",
        ".circleci/", "bitbucket-pipelines.yml",
    ],
    "docker": [
        "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
        ".dockerignore",
    ],
    "pages": [
        "project.yml",
    ],
    # GitHub live-tab data — changes independently of local files.
    # Watch paths are a proxy: bust on push (HEAD) or workflow edits.
    # For truly fresh data, user clicks 🔄 which sends ?bust=1.
    "gh-pulls":     [".git/HEAD", ".git/refs/"],
    "gh-runs":      [".github/workflows/", ".git/HEAD"],
    "gh-workflows": [".github/workflows/"],
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
    """Write cache dict to disk.  Caller MUST hold ``_file_lock``."""
    path = _cache_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, default=str), encoding="utf-8")


def _max_mtime(project_root: Path, watch_paths: list[str]) -> float:
    """Get the most recent mtime among the watch paths.

    For directory entries (paths ending with ``/``), walks the directory
    tree (depth-limited) and checks file mtimes — not just the dir mtime.
    On Linux, a directory's mtime only changes on file create/delete,
    NOT on edits to existing files inside it.
    """
    max_mt = 0.0
    for rel in watch_paths:
        p = project_root / rel
        try:
            if rel.endswith("/") and p.is_dir():
                max_mt = max(max_mt, _walk_max_mtime(p))
            else:
                st = os.stat(p)
                max_mt = max(max_mt, st.st_mtime)
        except (FileNotFoundError, OSError):
            pass
    return max_mt


# Directories to skip during mtime walks — build artifacts, VCS, caches
_WALK_SKIP = frozenset({
    ".git", ".backup", "node_modules", "__pycache__", ".venv", "venv",
    "build", "dist", ".tox", ".mypy_cache", ".ruff_cache",
    ".pytest_cache", ".next", ".nuxt", "site-packages",
    "_build",       # Sphinx
})

_WALK_MAX_DEPTH = 3  # 3 levels deep is enough for meaningful changes


def _walk_max_mtime(directory: Path) -> float:
    """Walk a directory (depth-limited, filtered) and return the max file mtime."""
    max_mt = 0.0
    base = str(directory)

    for root, dirs, files in os.walk(directory):
        # Enforce depth limit
        depth = root[len(base):].count(os.sep)
        if depth >= _WALK_MAX_DEPTH:
            dirs.clear()  # don't recurse deeper
            continue

        # Prune skipped directories (modifies dirs in-place for os.walk)
        dirs[:] = [d for d in dirs if d not in _WALK_SKIP and not d.startswith(".")]

        for fname in files:
            if fname.startswith(".") or fname.endswith(".release.json"):
                continue  # skip hidden files and release artifacts
            try:
                mt = os.stat(os.path.join(root, fname)).st_mtime
                if mt > max_mt:
                    max_mt = mt
            except (FileNotFoundError, OSError):
                pass

    return max_mt

# ── Event bus integration (fail-safe) ───────────────────────────

def _publish_event(event_type: str, **kw: object) -> None:
    """Publish a cache lifecycle event to the SSE bus.

    Fail-safe: if the bus is not available or publish raises,
    the error is silently swallowed.  The cache function must
    never break because of observability.
    """
    try:
        from src.core.services.event_bus import bus
        bus.publish(event_type, **kw)
    except Exception:
        pass  # observability must never break the cache


# ── Public API: caching ─────────────────────────────────────────

def get_cached(
    project_root: Path,
    card_key: str,
    compute_fn: Callable[[], dict],
    *,
    force: bool = False,
) -> dict:
    """Return cached card data, recomputing only when files change.

    Thread-safe: a per-key lock ensures that concurrent requests for
    the same card don't duplicate subprocess work.  Different cards
    can compute in parallel.

    The returned dict gets an extra ``_cache`` key with metadata:

    .. code-block:: json

        {"computed_at": 1707..., "fresh": true, "age_seconds": 42}

    Args:
        project_root: Project root path.
        card_key:     One of the 9 card keys (security, testing, …).
        compute_fn:   Zero-arg callable that returns the status dict.
        force:        If True, ignore cache and recompute.
    """
    lock = _get_key_lock(card_key)
    with lock:
        cache = _load_cache(project_root)
        entry = cache.get(card_key)
        watch = _WATCH_PATHS.get(card_key, [])

        current_mtime = _max_mtime(project_root, watch)

        # ── Check if cache is still valid ───────────────────────
        if not force and entry:
            cached_at: float = entry.get("cached_at", 0)
            cached_mtime: float = entry.get("mtime", 0)

            if current_mtime <= cached_mtime:
                # Nothing changed — return cached data
                data = entry["data"]
                age_s = round(time.time() - cached_at)
                data["_cache"] = {
                    "computed_at": cached_at,
                    "fresh": True,
                    "age_seconds": age_s,
                }
                logger.debug("cache HIT for %s (age %ds)", card_key, age_s)
                _publish_event("cache:hit", key=card_key,
                               data={"age_seconds": age_s, "mtime": current_mtime})
                return data

        # ── Recompute ───────────────────────────────────────────
        reason = "forced" if force else ("expired" if entry else "absent")
        _publish_event("cache:miss", key=card_key, data={"reason": reason})

        t0 = time.time()
        status = "ok"
        error_msg = ""
        caught_exc: Exception | None = None
        try:
            data = compute_fn()
        except Exception as exc:
            status = "error"
            error_msg = str(exc)
            data = {"error": error_msg}
            caught_exc = exc
        elapsed = round(time.time() - t0, 3)

        now = time.time()
        if status == "ok":
            # Re-read cache before writing to avoid losing entries
            # that were computed in parallel by other key locks.
            with _file_lock:
                fresh_cache = _load_cache(project_root)
                fresh_cache[card_key] = {
                    "data": data,
                    "cached_at": now,
                    "mtime": current_mtime if current_mtime > 0 else now,
                    "elapsed_s": elapsed,
                }
                _save_cache(project_root, fresh_cache)
            _publish_event("cache:done", key=card_key, data=data, duration_s=elapsed)
        else:
            _publish_event("cache:error", key=card_key, error=error_msg, duration_s=elapsed)

        data["_cache"] = {
            "computed_at": now,
            "fresh": False,
            "age_seconds": 0,
        }

        # ── Record activity ─────────────────────────────────────
        _record_activity(project_root, card_key, status, elapsed, data, error_msg, bust=force)

        logger.debug("cache MISS for %s (computed in %.2fs, status=%s)", card_key, elapsed, status)
        if caught_exc is not None:
            raise caught_exc
        return data


def invalidate(project_root: Path, card_key: str) -> None:
    """Invalidate a single card's server cache (thread-safe)."""
    with _file_lock:
        cache = _load_cache(project_root)
        if card_key in cache:
            del cache[card_key]
            _save_cache(project_root, cache)


def invalidate_all(project_root: Path) -> None:
    """Invalidate all server-side caches (thread-safe)."""
    with _file_lock:
        _save_cache(project_root, {})


def invalidate_scope(project_root: Path, scope: str) -> list[str]:
    """Invalidate a named scope of cards (thread-safe).

    Scopes:
        "devops"       — security, testing, quality, packages, env, docs, k8s, tf, dns
        "integrations" — git, github, ci, docker, k8s, terraform, pages
        "all"          — everything

    Returns the list of busted keys.
    """
    scope_map: dict[str, set[str]] = {
        "devops": DEVOPS_KEYS,
        "integrations": INTEGRATION_KEYS,
        "audit": AUDIT_KEYS,
        "all": ALL_CARD_KEYS,
    }
    keys = scope_map.get(scope, set())
    if not keys:
        return []

    busted: list[str] = []
    with _file_lock:
        cache = _load_cache(project_root)
        for key in list(cache.keys()):
            if key in keys:
                del cache[key]
                busted.append(key)
        _save_cache(project_root, cache)

    _publish_event("cache:bust", data={"scope": scope, "keys": busted})
    return busted


# ── Compute function registry ───────────────────────────────────
# Route modules register their compute functions so the cache
# module can recompute cards sequentially in a background thread
# after bust-all — eliminating I/O contention.

_COMPUTE_REGISTRY: dict[str, Callable[[Path], dict]] = {}


def register_compute(card_key: str, fn: Callable[[Path], dict]) -> None:
    """Register a compute function for a cache key.

    The function receives ``project_root`` and returns the card data dict.
    Called by route modules at import time.
    """
    _COMPUTE_REGISTRY[card_key] = fn
    logger.debug("registered compute fn for %s", card_key)


# Ordered list of card keys for sequential recompute.
# SLOWEST first: the background thread grabs the per-key lock for
# slow cards BEFORE browser GETs reach them (browser semaphore
# queues slow cards behind fast ones).  This ensures slow cards
# compute without contention in the background, while fast cards
# (packages, quality, git) are trivially computed by browser GETs.
_RECOMPUTE_ORDER: list[str] = [
    # Slowest (6-30s alone, 30s+ under contention)
    "testing",
    # Slow (5-20s)
    "dns", "terraform", "docs",
    # Medium (1-5s)
    "env", "k8s", "docker", "security",
    # Fast (< 1s) — browser can handle these, bg thread skips if done
    "ci", "git", "quality", "packages",
    # Integration-only
    "github",
    # Audit L0/L1 (fast, 0.5-2s each)
    "audit:scores", "audit:system", "audit:deps",
    "audit:structure", "audit:clients",
]

_recompute_thread: threading.Thread | None = None


def recompute_all(
    project_root: Path,
    *,
    keys: set[str] | None = None,
) -> None:
    """Recompute registered cards sequentially in a background thread.

    Called after bust to pre-fill the cache without I/O contention.
    If the browser's GET requests arrive while this is running, they
    block on the per-key lock and get the fresh result instantly once
    the background thread finishes that card.

    Parameters
    ----------
    project_root : Path
        Project root path.
    keys : set[str] | None
        If provided, only recompute these keys.  If None, recompute
        all registered keys.
    """
    global _recompute_thread

    # Don't stack recompute threads
    if _recompute_thread is not None and _recompute_thread.is_alive():
        logger.info("recompute already in progress, skipping")
        return

    # Build ordered list of keys to recompute
    target_keys = [
        k for k in _RECOMPUTE_ORDER
        if k in _COMPUTE_REGISTRY and (keys is None or k in keys)
    ]

    def _worker() -> None:
        t0 = time.time()
        computed = 0
        _publish_event("sys:warming", data={
            "keys": target_keys,
            "total": len(target_keys),
        })
        for key in target_keys:
            fn = _COMPUTE_REGISTRY[key]
            try:
                get_cached(project_root, key, lambda: fn(project_root))
                computed += 1
            except Exception as exc:
                logger.warning("recompute %s failed: %s", key, exc)
        elapsed = round(time.time() - t0, 2)
        _publish_event("sys:warm", duration_s=elapsed, data={
            "keys_computed": computed,
            "total": len(_COMPUTE_REGISTRY),
        })
        logger.info(
            "background recompute done: %d keys in %.1fs", computed, elapsed,
        )

    _recompute_thread = threading.Thread(
        target=_worker, daemon=True, name="cache-recompute",
    )
    _recompute_thread.start()



# ── Cascade invalidation ────────────────────────────────────────

# Reverse dependency map: when key X is invalidated, also invalidate these.
# Mirrors DEPENDENCY_MAP from project_probes.py in reverse direction.
_CASCADE: dict[str, list[str]] = {
    "git":    ["github", "docker", "ci", "pages"],
    "docker": ["ci", "k8s"],
    "github": ["ci"],
    "pages":  ["dns"],
}

# Aggregate keys that must be invalidated whenever ANY integration card changes.
_AGGREGATE_KEYS = ["project-status"]

# All integration card keys (for detecting aggregate cascade).
_INTEGRATION_KEYS = {"git", "github", "ci", "docker", "k8s", "terraform", "pages", "dns"}


def invalidate_with_cascade(project_root: Path, card_key: str) -> list[str]:
    """Invalidate a card and all its dependents, plus aggregates.

    Thread-safe: performs a single read-modify-write cycle under
    ``_file_lock`` to avoid N separate I/O operations.

    Returns the list of all keys that were busted.
    """
    # Collect all keys to bust
    keys_to_bust: list[str] = [card_key]

    # Health probe for this card
    hp_key = f"hp:{card_key}"
    if hp_key in _WATCH_PATHS:
        keys_to_bust.append(hp_key)

    # Direct cascade
    for dep in _CASCADE.get(card_key, []):
        keys_to_bust.append(dep)
        dep_hp = f"hp:{dep}"
        if dep_hp in _WATCH_PATHS:
            keys_to_bust.append(dep_hp)

    # Aggregate cascade: any integration card bust → also bust aggregates
    if card_key in _INTEGRATION_KEYS:
        keys_to_bust.extend(_AGGREGATE_KEYS)

    # Single read-modify-write
    with _file_lock:
        cache = _load_cache(project_root)
        changed = False
        for k in keys_to_bust:
            if k in cache:
                del cache[k]
                changed = True
        if changed:
            _save_cache(project_root, cache)

    return keys_to_bust


# ── Audit scan activity log ─────────────────────────────────────

# Human-friendly labels for card keys
_CARD_LABELS: dict[str, str] = {
    "security": "🔐 Security Posture",
    "testing": "🧪 Testing",
    "quality": "🔧 Code Quality",
    "packages": "📦 Packages",
    "env": "⚙️ Environment",
    "docs": "📚 Documentation",
    "k8s": "☸️ Kubernetes",
    "terraform": "🏗️ Terraform",
    "dns": "🌐 DNS & CDN",
    "audit:system": "🖥️ System Profile",
    "audit:deps": "📦 Dependencies",
    "audit:structure": "🏗️ Structure & Modules",
    "audit:clients": "🔌 Clients & Services",
    "audit:scores": "📊 Audit Scores",
    "audit:scores:enriched": "📊 Enriched Scores",
    "audit:l2:structure": "🔬 Structure Analysis",
    "audit:l2:quality": "💎 Code Health",
    "audit:l2:repo": "📁 Repo Health",
    "audit:l2:risks": "⚠️ Risks & Issues",
    "wiz:detect": "🧙 Wizard Detect",
    # ── Phase 4 audit expansion cards ──
    "vault": "🔐 Vault",
    "backup": "💾 Backup",
    "content": "📝 Content",
    "event": "📋 Event",
    "dismissal": "🚫 Dismissal",
    "docker": "🐳 Docker",
    "secrets": "🔑 Secrets",
    "ci": "⚙️ CI/CD",
    "wizard": "🧙 Wizard",
    "config": "⚙️ Config",
}


def _activity_path(project_root: Path) -> Path:
    return project_root / _ACTIVITY_FILE


def _extract_summary(card_key: str, data: dict) -> str:
    """Extract a one-line summary from the scan result for display."""
    if "error" in data and isinstance(data["error"], str):
        return f"Error: {data['error'][:100]}"

    # Audit-specific summaries
    if card_key == "audit:l2:risks":
        findings = data.get("findings", [])
        by_sev = {}
        for f in findings:
            s = f.get("severity", "info")
            by_sev[s] = by_sev.get(s, 0) + 1
        parts = [f"{c} {s}" for s, c in sorted(by_sev.items(), key=lambda x: {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get(x[0], 5))]
        return f"{len(findings)} findings ({', '.join(parts)})" if parts else f"{len(findings)} findings"

    if card_key == "audit:scores" or card_key == "audit:scores:enriched":
        scores = data.get("scores", {})
        if isinstance(scores, dict):
            overall = scores.get("overall", scores.get("total"))
            if overall is not None:
                return f"Overall score: {overall}"

    if card_key == "audit:system":
        return f"{data.get('os', '?')} · Python {data.get('python_version', '?')}"

    if card_key == "audit:deps":
        deps = data.get("dependencies", data.get("packages", []))
        if isinstance(deps, list):
            return f"{len(deps)} dependencies found"

    if card_key == "audit:l2:quality":
        hotspots = data.get("hotspots", [])
        return f"{len(hotspots)} hotspots" if hotspots else "No hotspots"

    # DevOps card summaries
    if card_key == "security":
        score = data.get("score")
        issues = data.get("issues", [])
        return f"Score: {score}, {len(issues)} issues" if score is not None else f"{len(issues)} issues"

    if card_key == "testing":
        total = data.get("test_files", data.get("total_files", 0))
        funcs = data.get("test_functions", data.get("total_functions", 0))
        return f"{total} test files, {funcs} functions"

    if card_key == "packages":
        managers = data.get("managers", [])
        return f"{len(managers)} package managers" if managers else "No package managers"

    # Generic — try to find any count-like key
    for key in ("total", "count", "items"):
        if key in data:
            return f"{data[key]} {key}"

    return "completed"


def _record_activity(
    project_root: Path,
    card_key: str,
    status: str,
    elapsed_s: float,
    data: dict,
    error_msg: str = "",
    *,
    bust: bool = False,
) -> None:
    """Record a scan computation in the activity log."""
    import datetime

    entry = {
        "ts": time.time(),
        "iso": datetime.datetime.now(datetime.UTC).isoformat(),
        "card": card_key,
        "label": _CARD_LABELS.get(card_key, card_key),
        "status": status,
        "duration_s": elapsed_s,
        "summary": _extract_summary(card_key, data) if status == "ok" else error_msg,
        "bust": bust,
    }

    path = _activity_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing
    entries: list[dict] = []
    if path.exists():
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            entries = []

    entries.append(entry)

    # Trim to max
    if len(entries) > _ACTIVITY_MAX:
        entries = entries[-_ACTIVITY_MAX:]

    try:
        path.write_text(json.dumps(entries, default=str), encoding="utf-8")
    except IOError as e:
        logger.warning("Failed to write audit activity: %s", e)


def record_event(
    project_root: Path,
    label: str,
    summary: str,
    *,
    detail: dict | None = None,
    card: str = "event",
    action: str | None = None,
    target: str | None = None,
    before_state: dict | None = None,
    after_state: dict | None = None,
) -> None:
    """Record a user-initiated action in the audit activity log.

    Unlike ``_record_activity`` (scan computations), this logs
    arbitrary events like finding dismissals, so they appear
    in the Debugging → Audit Log tab.

    Optional audit fields (when provided, enrich the log entry):
        action       — verb: created, modified, deleted, renamed, etc.
        target       — what was acted on (file path, resource name)
        before_state — state before the change (size, lines, hash, etc.)
        after_state  — state after the change
    """
    import datetime

    entry = {
        "ts": time.time(),
        "iso": datetime.datetime.now(datetime.UTC).isoformat(),
        "card": card,
        "label": label,
        "status": "ok",
        "duration_s": 0,
        "summary": summary,
        "bust": False,
    }
    if detail:
        entry["detail"] = detail
    if action:
        entry["action"] = action
    if target:
        entry["target"] = target
    if before_state:
        entry["before"] = before_state
    if after_state:
        entry["after"] = after_state

    path = _activity_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    entries: list[dict] = []
    if path.exists():
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            entries = []

    entries.append(entry)
    if len(entries) > _ACTIVITY_MAX:
        entries = entries[-_ACTIVITY_MAX:]

    try:
        path.write_text(json.dumps(entries, default=str), encoding="utf-8")
    except IOError as e:
        logger.warning("Failed to write audit event: %s", e)


def load_activity(project_root: Path, n: int = 50) -> list[dict]:
    """Load the latest N audit scan activity entries.

    If no activity file exists yet but cached data does, seed
    the activity log from existing cache metadata so the user
    sees historical scan info rather than an empty log.
    """
    import datetime

    path = _activity_path(project_root)
    entries: list[dict] = []

    if path.exists():
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            entries = []

    # ── Seed from cache if empty ────────────────────────────────
    if not entries:
        cache = _load_cache(project_root)
        if cache:
            for card_key, entry in cache.items():
                cached_at = entry.get("cached_at", 0)
                elapsed = entry.get("elapsed_s", 0)
                if not cached_at:
                    continue
                iso = datetime.datetime.fromtimestamp(
                    cached_at, tz=datetime.UTC
                ).isoformat()
                entries.append({
                    "ts": cached_at,
                    "iso": iso,
                    "card": card_key,
                    "label": _CARD_LABELS.get(card_key, card_key),
                    "status": "ok",
                    "duration_s": elapsed,
                    "summary": "loaded from cache (historical)",
                    "bust": False,
                })
            # Sort by timestamp
            entries.sort(key=lambda e: e.get("ts", 0))
            # Persist the seeded data
            if entries:
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(
                        json.dumps(entries, default=str), encoding="utf-8"
                    )
                except IOError:
                    pass

    return entries[-n:]



# ── Public API: preferences ─────────────────────────────────────


# Valid pref values
_VALID_PREFS = ("auto", "manual", "hidden", "visible")


def load_prefs(project_root: Path) -> dict:
    """Load card preferences (auto / manual / visible / hidden per card)."""
    path = _prefs_path(project_root)
    prefs = dict(_DEFAULT_PREFS)
    if path.exists():
        try:
            user_prefs = json.loads(path.read_text(encoding="utf-8"))
            for key in _DEFAULT_PREFS:
                if key in user_prefs and user_prefs[key] in _VALID_PREFS:
                    prefs[key] = user_prefs[key]
        except (json.JSONDecodeError, IOError):
            pass
    return prefs


def save_prefs(project_root: Path, prefs: dict) -> dict:
    """Save card preferences.  Returns the validated result."""
    valid: dict[str, str] = {}
    for key in _DEFAULT_PREFS:
        if key in prefs and prefs[key] in _VALID_PREFS:
            valid[key] = prefs[key]
        else:
            valid[key] = _DEFAULT_PREFS[key]

    path = _prefs_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(valid, indent=2), encoding="utf-8")
    return valid


