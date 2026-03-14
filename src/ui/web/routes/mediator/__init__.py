"""
Mediator Debug Dashboard API routes.

Blueprint: ``mediator_bp``
Prefix: ``/api``

Endpoints:
    GET  /mediator/diag             → Full diagnostic summary
    GET  /mediator/diag/<path>      → Detail for one node
    POST /mediator/refresh          → Force recompute path(s)
    POST /mediator/refresh-branch   → Refresh all under prefix
    POST /mediator/refresh-stale    → Refresh only stale nodes
    POST /mediator/bust             → Temporal invalidation
    POST /mediator/dispatch         → Async background recompute

Index-specific endpoints (Phase 8G):
    GET  /mediator/index/status     → Index summary (stats + classify + watcher)
    GET  /mediator/index/delta      → What changed since last scan
    POST /mediator/index/rescan     → Force full rescan
    POST /mediator/index/rebuild-symbols → Force symbol rebuild
    POST /mediator/index/rebuild-peek    → Force peek cache rebuild

All routes return JSON.  If the mediator singleton has not been
initialized (server startup not complete), routes return 503.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

mediator_bp = Blueprint("mediator", __name__)


def _get_mediator():
    """Get mediator instance, returning (mediator, None) or (None, error_response)."""
    try:
        from src.core.services.mediator import get_mediator

        return get_mediator(), None
    except RuntimeError:
        return None, (jsonify({"error": "mediator not initialized"}), 503)


# ── Diagnostic endpoints ──────────────────────────────────────────


@mediator_bp.route("/mediator/diag")
def mediator_diag():  # type: ignore[no-untyped-def]
    """Full mediator diagnostic summary.

    Returns tree stats, cached/stale counts, sequence number,
    subscription count, refreshing paths, executor status, and
    per-entry detail for every registered node.
    """
    m, err = _get_mediator()
    if err:
        return err
    try:
        return jsonify(m.diag())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@mediator_bp.route("/mediator/diag/<path:path>")
def mediator_diag_path(path):  # type: ignore[no-untyped-def]
    """Detail diagnostic for a single node.

    Parameters
    ----------
    path : str
        Dot-separated tree path (e.g. ``posture.toolchain``).

    Returns
    -------
    200 with node detail, or 404 if path not found.
    """
    m, err = _get_mediator()
    if err:
        return err
    try:
        result = m.diag(path)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Refresh endpoints ─────────────────────────────────────────────


@mediator_bp.route("/mediator/refresh", methods=["POST"])
def mediator_refresh():  # type: ignore[no-untyped-def]
    """Force recompute one or more paths.

    Request body::

        {"paths": ["posture.toolchain", "posture.platform"]}

    Returns refreshed paths, errors, and elapsed time.
    """
    m, err = _get_mediator()
    if err:
        return err
    try:
        body = request.get_json(silent=True) or {}
        paths = body.get("paths", [])
        if not paths:
            return jsonify({"error": "paths is required"}), 400
        return jsonify(m.refresh(*paths))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@mediator_bp.route("/mediator/refresh-branch", methods=["POST"])
def mediator_refresh_branch():  # type: ignore[no-untyped-def]
    """Refresh all registered nodes under a prefix.

    Request body::

        {"prefix": "posture"}

    Returns same shape as ``/mediator/refresh``.
    """
    m, err = _get_mediator()
    if err:
        return err
    try:
        body = request.get_json(silent=True) or {}
        prefix = body.get("prefix", "")
        if not prefix:
            return jsonify({"error": "prefix is required"}), 400
        return jsonify(m.refresh_branch(prefix))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@mediator_bp.route("/mediator/refresh-stale", methods=["POST"])
def mediator_refresh_stale():  # type: ignore[no-untyped-def]
    """Refresh only stale (TTL-expired) nodes.

    Request body::

        {"prefix": ""}   ← optional, defaults to all nodes

    Returns same shape as ``/mediator/refresh``.
    """
    m, err = _get_mediator()
    if err:
        return err
    try:
        body = request.get_json(silent=True) or {}
        prefix = body.get("prefix", "")
        return jsonify(m.refresh_stale(prefix))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Invalidation endpoints ────────────────────────────────────────


@mediator_bp.route("/mediator/bust", methods=["POST"])
def mediator_bust():  # type: ignore[no-untyped-def]
    """Temporal invalidation — bust entries older than max_age.

    Request body::

        {"max_age": 300, "prefix": "devops"}

    ``max_age`` is in seconds (required).
    ``prefix`` is optional (defaults to all nodes).

    Returns list of busted paths and count.
    """
    m, err = _get_mediator()
    if err:
        return err
    try:
        body = request.get_json(silent=True) or {}
        max_age = body.get("max_age")
        if max_age is None:
            return jsonify({"error": "max_age is required"}), 400
        prefix = body.get("prefix", "")
        return jsonify(m.bust(float(max_age), prefix))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Dispatch endpoint ─────────────────────────────────────────────


@mediator_bp.route("/mediator/dispatch", methods=["POST"])
def mediator_dispatch():  # type: ignore[no-untyped-def]
    """Queue paths for background recomputation.

    Request body::

        {"paths": ["posture.toolchain"]}

    Returns immediately with task ID and status.
    Uses the executor if configured, falls back to on_stale hook.
    """
    m, err = _get_mediator()
    if err:
        return err
    try:
        body = request.get_json(silent=True) or {}
        paths = body.get("paths", [])
        if not paths:
            return jsonify({"error": "paths is required"}), 400
        return jsonify(m.dispatch(*paths))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Index-specific endpoints (Phase 8G) ───────────────────────────


@mediator_bp.route("/mediator/index/status")
def mediator_index_status():  # type: ignore[no-untyped-def]
    """Aggregated index status for the dashboard.

    Returns a clean summary combining stats, classification, and
    node health information.  Designed for the UI's index panel.

    Response::

        {
            "files": 1298,
            "dirs": 241,
            "symbols": 4521,
            "peek_pages": 223,
            "primary_language": "python",
            "frameworks": ["docker", "python-project"],
            "languages": {"python": 512, "markdown": 223, ...},
            "extensions": {"py": 512, "md": 223, ...},
            "last_delta": {"added": 0, "removed": 0, "modified": 1, "empty": false},
            "nodes": {
                "index.scan": {"cached": true, "stale": false},
                ...
            }
        }
    """
    m, err = _get_mediator()
    if err:
        return err
    try:
        result: dict = {}

        # Stats
        try:
            stats = m.get("index.stats")["data" ]
            if stats:
                result["files"] = stats.get("file_count", 0)
                result["dirs"] = stats.get("dir_count", 0)
                result["symbols"] = stats.get("symbol_count", 0)
                result["primary_language"] = stats.get("primary_language", "")
                result["framework_count"] = stats.get("framework_count", 0)
                result["extensions"] = stats.get("extensions", {})
                result["last_delta"] = stats.get("last_delta", {})
        except Exception:
            result["files"] = 0
            result["dirs"] = 0
            result["symbols"] = 0

        # Classification
        try:
            classify = m.get("index.classify")["data"]
            if classify:
                result["languages"] = classify.get("languages", {})
                result["frameworks"] = classify.get("frameworks", [])
        except Exception:
            result["languages"] = {}
            result["frameworks"] = []

        # Peek page count
        try:
            peek = m.get("index.peek")["data"]
            result["peek_pages"] = len(peek) if peek else 0
        except Exception:
            result["peek_pages"] = 0

        # Node health
        diag = m.diag()
        entries = diag.get("entries", {})
        result["nodes"] = {
            path: {
                "cached": info.get("cached", False),
                "stale": info.get("stale", False),
            }
            for path, info in entries.items()
            if path.startswith("index.")
        }

        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@mediator_bp.route("/mediator/index/delta")
def mediator_index_delta():  # type: ignore[no-untyped-def]
    """Current delta — what changed since the last scan.

    Response::

        {
            "added": ["src/new.py"],
            "removed": ["src/old.py"],
            "modified": ["src/main.py"],
            "empty": false,
            "timestamp": 1741826001.5
        }
    """
    m, err = _get_mediator()
    if err:
        return err
    try:
        delta_result = m.get("index.delta")
        delta = delta_result["data"]
        if delta is None:
            return jsonify({"added": [], "removed": [], "modified": [], "empty": True})

        # ScanDelta has frozenset attributes — convert for JSON
        return jsonify({
            "added": sorted(delta.added),
            "removed": sorted(delta.removed),
            "modified": sorted(delta.modified),
            "empty": delta.empty,
            "timestamp": delta.timestamp,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@mediator_bp.route("/mediator/index/rescan", methods=["POST"])
def mediator_index_rescan():  # type: ignore[no-untyped-def]
    """Force a full rescan — invalidates index.scan and cascades.

    This triggers the full cascade::

        index.scan (recomputed)
          → index.delta  → index.symbols  → index.peek
          → index.files  → index.dirs     → index.paths
          → index.classify  → index.stats

    Returns the refresh result.
    """
    m, err = _get_mediator()
    if err:
        return err
    try:
        result = m.refresh("index.scan")
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@mediator_bp.route("/mediator/index/rebuild-symbols", methods=["POST"])
def mediator_index_rebuild_symbols():  # type: ignore[no-untyped-def]
    """Force rebuild of the symbol index.

    Invalidates index.symbols so it re-parses all files on next access.
    Also cascades to index.peek (which depends on symbols).
    """
    m, err = _get_mediator()
    if err:
        return err
    try:
        result = m.refresh("index.symbols")
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@mediator_bp.route("/mediator/index/rebuild-peek", methods=["POST"])
def mediator_index_rebuild_peek():  # type: ignore[no-untyped-def]
    """Force rebuild of the peek cache.

    Re-computes peek references for all markdown files.
    """
    m, err = _get_mediator()
    if err:
        return err
    try:
        result = m.refresh("index.peek")
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Recent events (past event history) ────────────────────────────

_MEDIATOR_EVENT_PREFIXES = (
    "mediator:",
    "index:",
)


@mediator_bp.route("/mediator/events/recent")
def mediator_events_recent():  # type: ignore[no-untyped-def]
    """Return recent mediator/index events from the EventBus ring buffer.

    Query params:
        limit (int): Max events to return (default 100, max 500).

    Returns a list of event dicts, most recent first.
    """
    limit = request.args.get("limit", 100, type=int)
    limit = min(limit, 500)

    try:
        from src.core.services.event_bus import bus

        with bus._lock:
            events = [
                e for e in bus._buffer
                if e.get("type", "").startswith(_MEDIATOR_EVENT_PREFIXES)
            ]
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    # Most recent first, capped
    events = list(reversed(events))[:limit]
    return jsonify({"events": events, "total": len(events)})

