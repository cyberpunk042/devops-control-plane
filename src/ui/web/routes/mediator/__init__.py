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
