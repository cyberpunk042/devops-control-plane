"""
Dependency management API routes.

Read endpoints use the mediator (cached).
Write endpoints use the pipeline (streaming or synchronous).

Routes::

    GET  /dependencies/tree          — Full dependency tree
    GET  /dependencies/summary       — Dashboard card counts
    GET  /dependencies/snapshots     — Rollback snapshot list

    POST /dependencies/install/stream  — SSE: install at scope
    POST /dependencies/update/stream   — SSE: update at scope
    POST /dependencies/rollback/stream — SSE: rollback to snapshot

    POST /dependencies/install         — Synchronous install
    POST /dependencies/update          — Synchronous update
    POST /dependencies/rollback        — Synchronous rollback

    POST   /dependencies/note          — Add/update note
    DELETE /dependencies/note          — Remove note
"""

from __future__ import annotations

import json

from flask import Response, jsonify, request

from src.core.services.events.tracked import tracked
from src.ui.web.helpers import project_root as _project_root

from . import dep_bp


# ═════════════════════════════════════════════════════════════════
#  Read endpoints (mediator-backed)
# ═════════════════════════════════════════════════════════════════


@dep_bp.route("/dependencies/tree")
def dep_tree():
    """Full dependency tree (cached via mediator)."""
    force = request.args.get("bust", "") == "1"

    from src.core.services.mediator import get_mediator
    m = get_mediator()
    result = m.get("dependency.tree", force=force)
    return jsonify(result["data"])


@dep_bp.route("/dependencies/summary")
def dep_summary():
    """Dashboard card summary counts."""
    force = request.args.get("bust", "") == "1"

    from src.core.services.mediator import get_mediator
    m = get_mediator()
    result = m.get("dependency.summary", force=force)
    return jsonify(result["data"])


@dep_bp.route("/dependencies/venvs")
def dep_venvs():
    """Virtual environment info — available venvs, active, Python versions."""
    force = request.args.get("bust", "") == "1"

    from src.core.services.mediator import get_mediator
    m = get_mediator()
    result = m.get("dependency.venvs", force=force)
    return jsonify(result["data"])


@dep_bp.route("/dependencies/installed")
@dep_bp.route("/dependencies/installed/<venv_name>")
def dep_installed(venv_name=None):
    """Installed packages in a venv (or active venv if no name).

    Args:
        venv_name: Venv directory name (e.g. ``.venv-ft``, ``.venv``, ``system``).
            ``None`` = active venv via mediator cache.
    """
    if venv_name:
        from src.core.services.dependency_mgr.venv_info import get_installed_packages
        installed = get_installed_packages(_project_root(), venv_name)
        return jsonify(installed)

    force = request.args.get("bust", "") == "1"
    from src.core.services.mediator import get_mediator
    m = get_mediator()
    result = m.get("dependency.installed", force=force)
    return jsonify(result["data"])


@dep_bp.route("/dependencies/versions")
def dep_versions():
    """Version intelligence (cached, 1hr TTL).

    Query params:
        bust=1 → force refresh (re-queries all registries)
    """
    force = request.args.get("bust", "") == "1"

    from src.core.services.mediator import get_mediator
    m = get_mediator()
    result = m.get("dependency.versions", force=force)
    return jsonify(result["data"])


@dep_bp.route("/dependencies/graph")
def dep_graph():
    """Dependency graph — edges, shared deps, modules."""
    from src.core.services.dependency_mgr.graph import build_graph
    from src.core.services.mediator import get_mediator

    force = request.args.get("bust", "") == "1"
    m = get_mediator()
    tree_result = m.get("dependency.tree", force=force)
    tree_data = tree_result["data"] if tree_result else {}

    graph = build_graph(tree_data)
    return jsonify(graph.to_dict())


@dep_bp.route("/dependencies/impact")
def dep_impact():
    """Impact analysis for upgrading a package.

    Query params:
        ecosystem: e.g. "pip"
        package: e.g. "requests"
        to_version: e.g. "2.32.3"
    """
    from src.core.services.dependency_mgr.graph import build_graph, analyze_impact
    from src.core.services.mediator import get_mediator

    ecosystem = request.args.get("ecosystem", "")
    package = request.args.get("package", "")
    to_version = request.args.get("to_version", "")

    if not ecosystem or not package:
        return jsonify({"error": "ecosystem and package are required"}), 400

    m = get_mediator()
    tree_result = m.get("dependency.tree")
    tree_data = tree_result["data"] if tree_result else {}

    graph = build_graph(tree_data)
    impact = analyze_impact(graph, ecosystem, package, to_version or "latest")

    if impact is None:
        return jsonify({"error": f"Package {package} not found in {ecosystem}"}), 404

    return jsonify(impact.to_dict())


@dep_bp.route("/dependencies/history")
def dep_history():
    """Recent dependency operations from the event store."""
    try:
        from src.core.services.mediator import get_mediator
        m = get_mediator()
        if not m or not getattr(m, '_event_store', None):
            return jsonify({"events": []})
        events = []
        for evt in m._event_store.recent(100):
            if evt.type.startswith('dependency.'):
                events.append({
                    "type": evt.type,
                    "summary": evt.summary,
                    "status": evt.status,
                    "ts": evt.ts,
                    "duration_ms": evt.duration_ms,
                    "detail": evt.detail,
                })
                if len(events) >= 10:
                    break
        return jsonify({"events": events})
    except Exception:
        return jsonify({"events": []})


@dep_bp.route("/dependencies/subdeps/<package_name>")
def dep_subdeps(package_name):
    """Sub-dependencies for a single package.

    Query params:
        venv: target venv (e.g. .venv-ft). Default = active.
        eco: ecosystem (pip/npm). Auto-detected if not set.
        path: module path for npm (e.g. .pages/code-docs).
    """
    from src.core.services.dependency_mgr.subdeps import get_package_deps

    venv = request.args.get("venv", None)
    eco = request.args.get("eco", None)
    mod_path = request.args.get("path", None)
    deps = get_package_deps(
        _project_root(), package_name,
        venv_path=venv, ecosystem=eco, module_path=mod_path,
    )
    return jsonify(deps)


@dep_bp.route("/dependencies/snapshots/<snapshot_id>/packages")
def dep_snapshot_packages(snapshot_id):
    """Parse the backed up manifest in a snapshot to show what packages were at what versions."""
    from pathlib import Path as _P
    snap_dir = _project_root() / ".state" / "dependency_snapshots" / snapshot_id
    if not snap_dir.is_dir():
        return jsonify({"error": "Snapshot not found"}), 404

    packages = []
    # Find and parse any manifest file in the snapshot
    for f in snap_dir.rglob("*"):
        if not f.is_file() or f.name == "manifest.json":
            continue
        try:
            if f.name == "pyproject.toml":
                from src.core.services.dependency_mgr.adapters.pip_adapter import PipAdapter
                pm = PipAdapter().parse_manifest(f, None)
                for dep in list(pm.dependencies) + list(pm.dev_dependencies):
                    packages.append({"name": dep.name, "version": dep.version_spec, "group": dep.group})
            elif f.name == "requirements.txt":
                from src.core.services.dependency_mgr.adapters.pip_adapter import PipAdapter
                pm = PipAdapter().parse_manifest(f, None)
                for dep in list(pm.dependencies) + list(pm.dev_dependencies):
                    packages.append({"name": dep.name, "version": dep.version_spec, "group": dep.group})
            elif f.name == "package.json":
                from src.core.services.dependency_mgr.adapters.npm_adapter import NpmAdapter
                pm = NpmAdapter().parse_manifest(f, None)
                for dep in list(pm.dependencies) + list(pm.dev_dependencies):
                    packages.append({"name": dep.name, "version": dep.version_spec, "group": dep.group})
        except Exception:
            pass

    return jsonify({"packages": packages, "snapshot_id": snapshot_id})


@dep_bp.route("/dependencies/snapshots")
def dep_snapshots():
    """List rollback snapshots."""
    from src.core.services.dependency_mgr.state import list_snapshots

    snaps = list_snapshots(_project_root())
    return jsonify({"snapshots": [s.to_dict() for s in snaps]})


# ═════════════════════════════════════════════════════════════════
#  Write endpoints — SSE streaming
# ═════════════════════════════════════════════════════════════════


def _get_registry():
    from src.core.services.dependency_mgr import get_registry
    return get_registry()


def _stream_operation(action):
    """Shared SSE streaming handler for install/update/rollback."""
    from src.core.services.dependency_mgr.pipeline import run_operation, run_batch_operation

    body = request.get_json(silent=True) or {}
    scope = body.get("scope", "")
    if not scope:
        return jsonify({"error": "scope is required"}), 400

    root = _project_root()
    registry = _get_registry()

    # Resolve target Python from venv path
    target_venv = body.get("target_venv")
    target_python = None
    break_system = body.get("break_system", False)

    if target_venv == "system":
        from src.core.services.dependency_mgr.venv_info import _find_system_python
        target_python = _find_system_python()
    elif target_venv:
        tp = root / target_venv / "bin" / "python"
        if tp.is_file():
            target_python = str(tp)

    common_kwargs = dict(
        registry=registry,
        packages=body.get("packages"),
        dev=body.get("dev", False),
        frozen=body.get("frozen", True),
        snapshot_id=body.get("snapshot_id"),
        correlation_id=body.get("correlation_id"),
        target_python=target_python,
        break_system=break_system,
        force_reinstall=body.get("force_reinstall", False),
    )

    def sse():
        # Batch mode: global scope with multiple ecosystems
        if scope == "global" and action in ("install", "update", "clean"):
            scopes = body.get("scopes", [])
            if not scopes:
                # Fallback: get all ecosystems from tree
                try:
                    from src.core.services.mediator import get_mediator
                    m = get_mediator()
                    tree_result = m.get("dependency.tree")
                    if tree_result and tree_result.get("data"):
                        scopes = [c["id"] for c in tree_result["data"].get("children", [])]
                except Exception:
                    pass

            if scopes:
                for event in run_batch_operation(
                    root, scopes, action, **common_kwargs,
                ):
                    yield f"data: {json.dumps(event.to_dict())}\n\n"
                return

        # Single ecosystem
        for event in run_operation(
            root, scope, action, **common_kwargs,
        ):
            yield f"data: {json.dumps(event.to_dict())}\n\n"

    return Response(sse(), mimetype="text/event-stream")


@dep_bp.route("/dependencies/install/stream", methods=["POST"])
@tracked("dependency.install.started")
def dep_install_stream():
    """SSE stream: install dependencies at scope."""
    return _stream_operation("install")


@dep_bp.route("/dependencies/update/stream", methods=["POST"])
@tracked("dependency.update.started")
def dep_update_stream():
    """SSE stream: update dependencies at scope."""
    return _stream_operation("update")


@dep_bp.route("/dependencies/rollback/stream", methods=["POST"])
@tracked("dependency.rollback.started")
def dep_rollback_stream():
    """SSE stream: rollback to a snapshot."""
    return _stream_operation("rollback")


@dep_bp.route("/dependencies/clean/stream", methods=["POST"])
@tracked("dependency.install.started")
def dep_clean_stream():
    """SSE stream: uninstall/clean packages at scope."""
    return _stream_operation("clean")


# ═════════════════════════════════════════════════════════════════
#  Write endpoints — synchronous
# ═════════════════════════════════════════════════════════════════


def _sync_operation(action):
    """Shared synchronous handler — collects all events, returns summary."""
    from src.core.services.dependency_mgr.pipeline import run_operation

    body = request.get_json(silent=True) or {}
    scope = body.get("scope", "")
    if not scope:
        return jsonify({"error": "scope is required"}), 400

    root = _project_root()
    registry = _get_registry()

    # Resolve target Python
    target_venv = body.get("target_venv")
    target_python = None
    break_system = body.get("break_system", False)
    if target_venv == "system":
        from src.core.services.dependency_mgr.venv_info import _find_system_python
        target_python = _find_system_python()
    elif target_venv:
        tp = root / target_venv / "bin" / "python"
        if tp.is_file():
            target_python = str(tp)

    events = list(run_operation(
        root, scope, action,
        registry=registry,
        packages=body.get("packages"),
        dev=body.get("dev", False),
        frozen=body.get("frozen", True),
        snapshot_id=body.get("snapshot_id"),
        correlation_id=body.get("correlation_id"),
        target_python=target_python,
        break_system=break_system,
    ))

    # Find the done event
    done = next((e for e in reversed(events) if e.type in
                 ("operation_done", "rollback_done", "error")), None)

    if done is None:
        return jsonify({"ok": False, "error": "No completion event"}), 500

    if done.type == "error":
        return jsonify({"ok": False, "error": done.message}), 400

    ok = done.status == "ok"
    result = {
        "ok": ok,
        "scope": scope,
        "action": action,
        "count": done.count,
        "duration_ms": done.duration_ms,
        "warnings": done.detail.get("warnings", 0),
        "errors": done.detail.get("errors", 0),
    }
    if not ok:
        result["error"] = done.message

    return jsonify(result), 200 if ok else 400


@dep_bp.route("/dependencies/install", methods=["POST"])
@tracked("dependency.install.started")
def dep_install():
    """Synchronous install at scope."""
    return _sync_operation("install")


@dep_bp.route("/dependencies/update", methods=["POST"])
@tracked("dependency.update.started")
def dep_update():
    """Synchronous update at scope."""
    return _sync_operation("update")


@dep_bp.route("/dependencies/rollback", methods=["POST"])
@tracked("dependency.rollback.started")
def dep_rollback():
    """Synchronous rollback to a snapshot."""
    return _sync_operation("rollback")


# ═════════════════════════════════════════════════════════════════
#  Notes
# ═════════════════════════════════════════════════════════════════


@dep_bp.route("/dependencies/note", methods=["POST"])
@tracked("dependency.note.added")
def dep_note_add():
    """Add or update a note on a package version."""
    from src.core.services.dependency_mgr.state import set_note

    body = request.get_json(silent=True) or {}
    ecosystem = body.get("ecosystem", "").strip()
    package = body.get("package", "").strip()
    version = body.get("version", "").strip()
    note = body.get("note", "").strip()

    if not all([ecosystem, package, version, note]):
        return jsonify({"error": "ecosystem, package, version, and note are required"}), 400

    set_note(
        _project_root(),
        ecosystem, package, version, note,
        dismiss_until=body.get("dismiss_until"),
    )
    return jsonify({"ok": True})


@dep_bp.route("/dependencies/note", methods=["DELETE"])
@tracked("dependency.note.removed")
def dep_note_remove():
    """Remove a note from a package version."""
    from src.core.services.dependency_mgr.state import remove_note

    body = request.get_json(silent=True) or {}
    ecosystem = body.get("ecosystem", "").strip()
    package = body.get("package", "").strip()
    version = body.get("version", "").strip()

    if not all([ecosystem, package, version]):
        return jsonify({"error": "ecosystem, package, and version are required"}), 400

    existed = remove_note(_project_root(), ecosystem, package, version)
    return jsonify({"ok": True, "existed": existed})
