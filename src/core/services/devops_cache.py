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
        "project.yml", ".pages/",
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
        "project.yml", ".pages/",
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
                data["_cache"] = {
                    "computed_at": cached_at,
                    "fresh": True,
                    "age_seconds": round(time.time() - cached_at),
                }
                logger.debug("cache HIT for %s (age %ds)", card_key,
                             round(time.time() - cached_at))
                return data

        # ── Recompute ───────────────────────────────────────────
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


