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
    """Dependency graph — edges, shared deps, modules.

    Query params:
        venv: target venv for status resolution. Default = tree's baked state.
    """
    from src.core.services.dependency_mgr.graph import build_graph
    from src.core.services.mediator import get_mediator

    force = request.args.get("bust", "") == "1"
    venv = request.args.get("venv", None)
    m = get_mediator()
    tree_result = m.get("dependency.tree", force=force)
    tree_data = tree_result["data"] if tree_result else {}

    # If a target venv was specified, patch tree data with that venv's installed state
    if venv and tree_data:
        from src.core.services.dependency_mgr.venv_info import get_installed_packages
        target_installed = get_installed_packages(_project_root(), venv)
        for eco_node in tree_data.get("children", []):
            for pkg in eco_node.get("children", []):
                name = pkg.get("label", "").split(" ")[0]
                if not name:
                    continue
                inst_ver = target_installed.get(name.lower(), "")
                latest = pkg.get("latestVersion", "")
                if not inst_ver:
                    pkg["status"] = "missing"
                elif latest and inst_ver != latest:
                    pkg["status"] = "outdated"
                else:
                    pkg["status"] = "current"
                pkg["installedVersion"] = inst_ver

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
        # Only show completed/failed user operations, not starts or cache recomputations
        _OP_SUFFIXES = (".completed", ".failed")
        _OP_PREFIXES = (
            "dependency.install.", "dependency.update.",
            "dependency.clean.", "dependency.rollback.",
        )
        raw = m._event_store.query(types=["dependency."], limit=50)
        events = []
        for evt in raw:
            if (any(evt.type.startswith(p) for p in _OP_PREFIXES)
                    and any(evt.type.endswith(s) for s in _OP_SUFFIXES)):
                events.append({
                    "type": evt.type,
                    "summary": evt.summary,
                    "status": evt.status,
                    "ts": evt.ts,
                    "duration_ms": evt.duration_ms,
                    "detail": evt.detail,
                    "correlation_id": evt.correlation_id,
                })
                if len(events) >= 10:
                    break
        return jsonify({"events": events})
    except Exception:
        return jsonify({"events": []})


@dep_bp.route("/dependencies/dep-graph")
def dep_full_graph():
    """Full dependency graph with sub-dependency relationships.

    Returns all packages (declared + transitive) with their
    requires/required_by links for graph visualization.

    Query params:
        venv: target venv. Default = active.
        eco: ecosystem filter (pip/npm). Default = all.
        path: module path for npm.
    """
    from src.core.services.dependency_mgr.subdeps import get_package_deps_batch

    venv = request.args.get("venv", None)
    eco = request.args.get("eco", None)

    # Get the tree for declared packages
    from src.core.services.mediator import get_mediator
    m = get_mediator()
    tree_result = m.get("dependency.tree")
    if not tree_result or not tree_result.get("data"):
        return jsonify({"nodes": [], "edges": []})

    tree_data = tree_result["data"]

    # Fetch installed packages for the requested target venv
    from src.core.services.dependency_mgr.venv_info import get_installed_packages
    target_installed = get_installed_packages(_project_root(), venv) if venv else {}

    # Collect all declared package names per ecosystem
    declared = {}  # name → {ecosystem, group, version, path}
    for eco_node in tree_data.get("children", []):
        if eco and eco_node.get("ecosystem") != eco:
            continue
        for pkg in eco_node.get("children", []):
            name = pkg.get("label", "").split(" ")[0]
            if name:
                # If a target venv was specified, compute status from that venv's installed data
                if venv and target_installed:
                    inst_ver = target_installed.get(name.lower(), "")
                    latest = pkg.get("latestVersion", "")
                    declared_ver = pkg.get("version", "")
                    if not inst_ver:
                        status = "missing"
                    elif latest and inst_ver != latest:
                        status = "outdated"
                    else:
                        status = "current"
                else:
                    inst_ver = pkg.get("installedVersion", "")
                    status = pkg.get("status", "")

                declared[name.lower()] = {
                    "name": name,
                    "ecosystem": eco_node.get("ecosystem", ""),
                    "group": pkg.get("group", "main"),
                    "version": pkg.get("version", ""),
                    "path": eco_node.get("path", "."),
                    "declared": True,
                    "status": status,
                    "installedVersion": inst_ver,
                    "latestVersion": pkg.get("latestVersion", ""),
                }

    # Get sub-deps for all declared packages
    pkg_names = [d["name"] for d in declared.values()]
    eco_filter = eco or (list(set(d["ecosystem"] for d in declared.values())) or ["pip"])[0]

    # For pip, use batch lookup — prefer mediator cache when no venv override
    if eco_filter == "pip":
        subdeps_cached = None
        if not venv:
            subdeps_result = m.peek("dependency.subdeps")
            if subdeps_result and subdeps_result.get("data"):
                subdeps_cached = subdeps_result["data"]

        if subdeps_cached:
            all_deps = subdeps_cached
        else:
            all_deps = get_package_deps_batch(
                _project_root(), pkg_names, venv_path=venv,
                installed=target_installed or None,
            )
    else:
        # npm — individual lookups with module path
        from src.core.services.dependency_mgr.subdeps import get_package_deps
        mod_path = request.args.get("path", None) or (list(set(d["path"] for d in declared.values())) or [None])[0]
        all_deps = {}
        for name in pkg_names:
            all_deps[name] = get_package_deps(_project_root(), name, ecosystem=eco_filter, module_path=mod_path)

    # Build nodes and edges
    nodes = {}  # name → node dict
    edges = []  # {source, target}

    # Add declared packages as nodes
    for key, info in declared.items():
        nodes[info["name"].lower()] = {
            "id": info["name"],
            "label": info["name"],
            "declared": True,
            "group": info["group"],
            "version": info["version"],
            "ecosystem": info["ecosystem"],
            "status": info.get("status", ""),
            "installedVersion": info.get("installedVersion", ""),
            "latestVersion": info.get("latestVersion", ""),
        }

    # Add sub-deps as nodes + edges
    for pkg_name, deps in all_deps.items():
        pkg_key = pkg_name.lower()
        if pkg_key in nodes:
            nodes[pkg_key]["requires_count"] = len(deps.get("requires", []))
            nodes[pkg_key]["required_by_count"] = len(deps.get("required_by", []))
            nodes[pkg_key]["summary"] = deps.get("summary", "")
            nodes[pkg_key]["homePage"] = deps.get("home_page", "")
            nodes[pkg_key]["author"] = deps.get("author", "")
            nodes[pkg_key]["license"] = deps.get("license", "")

        for sub in deps.get("requires_detail", []):
            sub_key = sub["name"].lower()
            if sub_key not in nodes:
                nodes[sub_key] = {
                    "id": sub["name"],
                    "label": sub["name"],
                    "declared": False,
                    "group": "transitive",
                    "version": sub.get("installed", ""),
                    "ecosystem": eco_filter,
                }
            edges.append({"source": pkg_name, "target": sub["name"]})

    return jsonify({
        "nodes": list(nodes.values()),
        "edges": edges,
        "declared_count": len(declared),
        "total_count": len(nodes),
        "transitive_count": len(nodes) - len(declared),
    })


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
