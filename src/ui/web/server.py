"""
Web admin server — Flask app factory.

Creates and configures the Flask application for the local
admin dashboard. Provides REST API endpoints and a single-page
dashboard for project management.
"""

from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask

logger = logging.getLogger(__name__)

# Package directory for templates and static files
_PACKAGE_DIR = Path(__file__).parent


def create_app(
    project_root: Path | None = None,
    config_path: Path | None = None,
    mock_mode: bool = False,
) -> Flask:
    """Create and configure the Flask application.

    Args:
        project_root: Root directory of the project.
        config_path: Path to project.yml.
        mock_mode: Whether to use mock adapters.

    Returns:
        Configured Flask application.
    """
    app = Flask(
        __name__,
        template_folder=str(_PACKAGE_DIR / "templates"),
        static_folder=str(_PACKAGE_DIR / "static"),
    )

    # Store config on app
    app.config["PROJECT_ROOT"] = Path(project_root or Path.cwd())
    app.config["CONFIG_PATH"] = str(config_path) if config_path else None

    # Factory reset: if signal file exists, clear .state/ before anything initializes
    _factory_reset_signal = app.config["PROJECT_ROOT"] / ".factory-reset-signal"
    if _factory_reset_signal.exists():
        import shutil
        _state_dir = app.config["PROJECT_ROOT"] / ".state"
        try:
            _factory_reset_signal.unlink()
            if _state_dir.exists():
                # Preserve server.pid — manage.sh needs it for process tracking
                _pid_file = _state_dir / "server.pid"
                _pid_backup = None
                if _pid_file.exists():
                    _pid_backup = _pid_file.read_text(encoding="utf-8")
                shutil.rmtree(_state_dir)
                _state_dir.mkdir(parents=True, exist_ok=True)
                if _pid_backup is not None:
                    _pid_file.write_text(_pid_backup, encoding="utf-8")
            logging.getLogger(__name__).warning(
                "Factory reset: .state/ cleared on startup (signal file detected)"
            )
        except Exception as _exc:
            logging.getLogger(__name__).error(
                "Factory reset: failed to clear .state/: %s", _exc
            )

    # Register project root in core context (used by all core services)
    from src.core.context import set_project_root as _set_ctx_root
    _set_ctx_root(app.config["PROJECT_ROOT"])
    app.config["MOCK_MODE"] = mock_mode
    app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB upload limit

    # Register blueprints
    # ── Grouped sub-packages ─────────────────────────────────
    from src.ui.web.routes.audit import audit_bp
    from src.ui.web.routes.backup import backup_bp
    from src.ui.web.routes.content import content_bp
    from src.ui.web.routes.devops import devops_bp
    from src.ui.web.routes.pages import pages_bp, pages_api_bp

    # ── Standalone route modules ────────────────────────────
    from src.ui.web.routes.api import api_bp
    from src.ui.web.routes.chat import chat_bp
    from src.ui.web.routes.ci import ci_bp
    from src.ui.web.routes.config import config_bp
    from src.ui.web.routes.dev import dev_bp
    from src.ui.web.routes.dns import dns_bp
    from src.ui.web.routes.docker import docker_bp
    from src.ui.web.routes.docs import docs_bp
    from src.ui.web.routes.events import events_bp
    from src.ui.web.routes.git_auth import git_auth_bp
    from src.ui.web.routes.infra import infra_bp
    from src.ui.web.routes.integrations import integrations_bp
    from src.ui.web.routes.k8s import k8s_bp
    from src.ui.web.routes.metrics import metrics_bp
    from src.ui.web.routes.packages import packages_bp
    from src.ui.web.routes.project import project_bp
    from src.ui.web.routes.quality import quality_bp
    from src.ui.web.routes.secrets import secrets_bp
    from src.ui.web.routes.security_scan import security_bp2
    from src.ui.web.routes.server import server_bp
    from src.ui.web.routes.terraform import terraform_bp
    from src.ui.web.routes.testing import testing_bp
    from src.ui.web.routes.trace import trace_bp
    from src.ui.web.routes.vault import vault_bp
    from src.ui.web.routes.smart_folders import smart_folders_bp
    from src.ui.web.routes.artifacts import bp as artifacts_bp
    from src.ui.web.routes.changelog import changelog_bp
    from src.ui.web.routes.tab_mesh import tab_mesh_bp
    from src.ui.web.routes.notifications import notifications_bp
    from src.ui.web.routes.scripts import scripts_bp
    from src.ui.web.routes.cdp_test import cdp_test_bp
    from src.ui.web.routes.plans import plans_bp
    from src.ui.web.routes.api.batch import batch_bp
    from src.ui.web.routes.posture import posture_bp
    from src.ui.web.routes.mediator import mediator_bp
    from src.ui.web.routes.timeline import timeline_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(config_bp, url_prefix="/api")
    app.register_blueprint(vault_bp, url_prefix="/api")
    app.register_blueprint(secrets_bp, url_prefix="/api")
    app.register_blueprint(content_bp, url_prefix="/api")
    app.register_blueprint(backup_bp, url_prefix="/api")
    app.register_blueprint(ci_bp, url_prefix="/api")
    app.register_blueprint(docker_bp, url_prefix="/api")
    app.register_blueprint(docs_bp, url_prefix="/api")
    app.register_blueprint(infra_bp, url_prefix="/api")
    app.register_blueprint(k8s_bp, url_prefix="/api")
    app.register_blueprint(terraform_bp, url_prefix="/api")
    app.register_blueprint(dns_bp, url_prefix="/api")
    app.register_blueprint(integrations_bp, url_prefix="/api")
    app.register_blueprint(metrics_bp, url_prefix="/api")
    app.register_blueprint(packages_bp, url_prefix="/api")
    app.register_blueprint(quality_bp, url_prefix="/api")
    app.register_blueprint(security_bp2, url_prefix="/api")
    app.register_blueprint(testing_bp, url_prefix="/api")
    app.register_blueprint(pages_api_bp, url_prefix="/api")
    app.register_blueprint(devops_bp, url_prefix="/api")
    app.register_blueprint(project_bp, url_prefix="/api")
    app.register_blueprint(events_bp, url_prefix="/api")
    app.register_blueprint(chat_bp, url_prefix="/api")
    app.register_blueprint(git_auth_bp, url_prefix="/api")
    app.register_blueprint(trace_bp, url_prefix="/api")
    app.register_blueprint(audit_bp)
    app.register_blueprint(dev_bp, url_prefix="/api")
    app.register_blueprint(smart_folders_bp, url_prefix="/api")
    app.register_blueprint(server_bp, url_prefix="/api")
    app.register_blueprint(artifacts_bp)
    app.register_blueprint(changelog_bp, url_prefix="/api")
    app.register_blueprint(tab_mesh_bp, url_prefix="/api")
    app.register_blueprint(notifications_bp, url_prefix="/api")
    app.register_blueprint(scripts_bp)
    app.register_blueprint(cdp_test_bp, url_prefix="/api")
    app.register_blueprint(plans_bp, url_prefix="/api")
    app.register_blueprint(batch_bp, url_prefix="/api")
    app.register_blueprint(posture_bp, url_prefix="/api")
    app.register_blueprint(mediator_bp, url_prefix="/api")
    app.register_blueprint(timeline_bp)

    # Initialize vault with project root (for auto-lock)
    from src.core.services import vault as vault_module

    vault_module.set_project_root(app.config["PROJECT_ROOT"])

    # Initialize posture cache with project root (for file persistence)
    from src.core.services.system_posture.cache import init as posture_cache_init

    posture_cache_init(app.config["PROJECT_ROOT"])

    # Initialize QueryMediator (trilateral data hub)
    from src.core.services.mediator import init as mediator_init

    mediator_inst = mediator_init(app.config["PROJECT_ROOT"])

    # Register domain nodes in the mediator tree
    from src.core.services.mediator.registrations import register_all

    register_all(mediator_inst)

    # Hydrate mediator cache from disk shards (warm start)
    # Architecture §9 — on startup, load persisted index data so
    # m.peek() returns data immediately without resolver computation.
    from src.core.services.mediator.persistence import hydrate_cache as _hydrate_cache

    _hydrated_count = _hydrate_cache(mediator_inst, Path(project_root))
    if _hydrated_count:
        logger.info(
            "mediator warm start: hydrated %d entries from disk shards",
            _hydrated_count,
        )
    else:
        logger.info("mediator cold start: no disk shards found")

    # Vault activity tracking — resets auto-lock timer on user actions
    @app.before_request
    def _track_vault_activity():  # type: ignore[no-untyped-def]
        from flask import request as req

        vault_module.touch_activity(req.path, req.method)

    # Data catalogs — inject into every template context
    from src.core.data import get_registry

    _registry = get_registry()
    app.config["DATA_REGISTRY"] = _registry


    # ── Pre-compute stacks catalog (static — never changes at runtime) ──
    from src.core.config.stack_loader import discover_stacks

    try:
        _stacks_raw = discover_stacks()
        _stacks_js = [
            {
                "name": s.name,
                "description": s.description,
                "detail": s.detail,
                "icon": s.icon,
                "domain": s.domain,
                "parent": s.parent,
                "capabilities": [c.name for c in s.capabilities],
                "capabilityDetails": [
                    {"name": c.name, "command": c.command, "description": c.description, "adapter": c.adapter}
                    for c in s.capabilities
                ],
                "requires": [
                    {"adapter": r.adapter, "minVersion": r.min_version}
                    for r in s.requires
                ],
                "detection": {
                    "filesAnyOf": s.detection.files_any_of,
                    "filesAllOf": s.detection.files_all_of,
                    "contentContains": s.detection.content_contains,
                },
            }
            for s in sorted(_stacks_raw.values(), key=lambda s: s.name)
        ]
    except Exception:
        _stacks_js = []


    # ── Map of inject keys → mediator paths ─────────────────────────
    # All 23 inject keys map to mediator paths across 7 domains.
    _KEY_TO_MEDIATOR: dict[str, str] = {
        # devops domain (13 keys)
        "docker": "devops.docker",
        "k8s": "devops.k8s",
        "git": "devops.git",
        "github": "devops.github",
        "ci": "devops.ci",
        "terraform": "devops.terraform",
        "env": "devops.env",
        "security": "devops.security",
        "packages": "devops.packages",
        "quality": "devops.quality",
        "testing": "devops.testing",
        "docs": "devops.docs",
        "dns": "devops.dns",
        # github domain (3 keys)
        "gh-pulls": "github.pulls",
        "gh-runs": "github.runs",
        "gh-workflows": "github.workflows",
        # detect domain (1 key)
        "wiz:detect": "detect.wizard",
        # devops.status (was extra.project_status — redundant passthrough)
        "project-status": "devops.status",
        # audit domain (5 keys)
        "audit:scores": "audit.scores",
        "audit:system": "audit.system",
        "audit:deps": "audit.deps",
        "audit:structure": "audit.structure",
        "audit:clients": "audit.clients",
        # timeline domain (1 key — single aggregate)
        "timeline": "timeline.data",
    }

    @app.context_processor
    def _inject_data_catalogs():  # type: ignore[no-untyped-def]
        initial: dict[str, dict] = {}

        # Peek at mediator for all inject keys (NEVER blocks).
        # Mediator is hydrated from disk shards on startup (persist=True),
        # so data is available immediately after server init.
        try:
            from src.core.services.mediator import get_mediator
            m = get_mediator()
            for key, mediator_path in _KEY_TO_MEDIATOR.items():
                try:
                    result = m.peek(mediator_path)
                    if result is not None:
                        data = result.get("data")
                        if data is not None:
                            initial[key] = {"data": data}
                except Exception:
                    pass
        except (RuntimeError, Exception):
            pass  # Mediator not initialized — degrade gracefully

        # Merge static catalogs with pre-computed stacks
        dcp = _registry.to_js_dict()
        dcp["stacks"] = _stacks_js

        return {
            "dcp_data": dcp,
            "initial_state": initial,
        }



    # Start index watcher (FS polling → mediator cascade)
    # The index watcher always runs — it drives scan, delta, stats, view, classify.
    # Peek + symbols are gated by the peek_index_enabled setting inside the watcher.
    from src.core.services.mediator.index_watcher import start_index_watcher
    start_index_watcher(app.config["PROJECT_ROOT"], mediator_inst)

    # ── CDP transport warm-up (background, silent) ──────────────
    # Probe all channels and warm the PS bridge BEFORE any CDP
    # operation attempts.  Priority NORMAL (2) — runs during first
    # page load, doesn't block server startup.
    try:
        from src.ui.web import cdp_client as _cdp_client
        from src.core.services.mediator.work_queue import WorkItem, Priority

        _wq = mediator_inst._work_queue
        if _wq is not None:
            _wq.submit(WorkItem(
                priority=Priority.NORMAL,
                size=1,
                path="boot.transport_warmup",
                resolver=lambda: _cdp_client.warm(silent=True),
            ))
            logger.info("Submitted boot.transport_warmup to work queue (NORMAL)")

            # ── CDP status discovery (background, after warm-up) ──
            # Uses mediator.dispatch() — the proper public API for
            # resolving registered nodes in the background.
            # Priority LOW (3) — runs AFTER the NORMAL (2) warm-up.
            mediator_inst.dispatch(
                "tabmesh.cdp_status",
                priority=Priority.LOW,
            )
            logger.info("Dispatched tabmesh.cdp_status to work queue (LOW)")
        else:
            logger.debug("No work queue available, skipping CDP boot tasks")
    except Exception as exc:
        logger.warning("Could not submit CDP boot tasks: %s", exc)

    # Restore file logging if previously enabled
    from src.core.services.server_settings import load_settings, toggle_file_logging
    _startup_settings = load_settings(app.config["PROJECT_ROOT"])
    if _startup_settings.get("file_logging_enabled"):
        toggle_file_logging(app.config["PROJECT_ROOT"], True)

    # WSL→Windows tunnel: NOT auto-started.
    # The user activates it from Tab Mesh → WSL Channel UI.
    # When inactive, the system uses curl.exe bridge (the existing path).

    # ── Python runtime optimization notification ────────────────
    # Detect Python build (GIL vs free-threaded) and notify the
    # user if a performance upgrade path is available.
    try:
        import os
        import sys
        from src.core.services.mediator.work_queue import is_free_threaded

        _py_version = sys.version.split()[0]
        _cpu_count = os.cpu_count() or 1

        if not is_free_threaded() and _cpu_count >= 4:
            from src.core.services.notifications import create_notification

            # Check if free-threaded build is installed AND deps are ready
            # (must match manage.sh check — it looks for .venv-ft/bin/flask)
            _venv_ft = Path(project_root) / ".venv-ft" / "bin" / "flask"
            _ft_installed = _venv_ft.exists()

            if _ft_installed:
                # Installed but server running under GIL Python
                create_notification(
                    project_root,
                    notif_type="python_optimization",
                    title="⚡ Free-threaded Python ready — restart to activate",
                    message=(
                        f"Python {_py_version} (GIL) is running but "
                        f".venv-ft with free-threaded Python is installed. "
                        f"Restart the server to activate it — "
                        f"manage.sh will pick it up automatically. "
                        f"All {_cpu_count} CPUs will run threads in true parallel."
                    ),
                    meta={
                        "current_version": _py_version,
                        "target_version": "3.14t",
                        "cpu_count": _cpu_count,
                        "build": "gil",
                        "venv_ft_installed": True,
                    },
                    dedup=True,
                )
                logger.info(
                    "Python %s (GIL) — free-threaded venv exists at %s, not active",
                    _py_version, _venv_ft,
                )
            else:
                # Not installed yet — offer install plan
                create_notification(
                    project_root,
                    notif_type="python_optimization",
                    title="⚡ Free-threaded Python available",
                    message=(
                        f"Running Python {_py_version} (GIL) on {_cpu_count} CPUs. "
                        f"Python 3.14t enables true parallel threading — "
                        f"mediator dispatch, AST parsing, and audit scans "
                        f"can run across all cores simultaneously. "
                        f"Install via: uv python install 3.14t"
                    ),
                    meta={
                        "action": "install_plan",
                        "recipe": "python3-ft",
                        "current_version": _py_version,
                        "target_version": "3.14t",
                        "cpu_count": _cpu_count,
                        "build": "gil",
                    },
                    dedup=True,
                )
                logger.info(
                    "Python %s (GIL) on %d CPUs — free-threaded upgrade available",
                    _py_version, _cpu_count,
                )
        elif is_free_threaded():
            # Dismiss any stale upgrade notification from a previous GIL session
            from src.core.services.notifications import dismiss_notification_by_type
            dismiss_notification_by_type(project_root, "python_optimization")
            logger.info(
                "Python %s (free-threaded, no-GIL) — true parallel threading active",
                _py_version,
            )
    except Exception as exc:
        logger.debug("Python runtime check: %s", exc)

    logger.info("Web admin app created (root=%s)", project_root)
    return app


def run_server(
    app: Flask,
    host: str | None = None,
    port: int | None = None,
    debug: bool = False,
) -> None:
    """Run the Flask development server with smart port resolution.

    If ``port`` is None (no CLI override), reads the preferred port
    and fallback list from project.yml ``web:`` settings.  If the
    preferred port is busy, tries fallbacks automatically.

    If ``port`` is explicitly set (CLI ``--port``), uses that port
    only — no fallback.
    """
    from src.core.services.server_lifecycle import (
        install_signal_handlers,
        resolve_port,
        PortResolutionError,
    )

    project_root = app.config["PROJECT_ROOT"]

    # ── Load web settings from project config ──
    try:
        from src.core.config.loader import load_project
        project = load_project(project_root / "project.yml")
        web_cfg = project.web
    except Exception:
        from src.core.models.project import WebSettings
        web_cfg = WebSettings()

    # Use config host if CLI didn't specify
    if host is None:
        host = web_cfg.host

    # ── Resolve port ──
    cli_override = port  # None if user didn't pass --port
    try:
        resolved_port = resolve_port(
            project_root,
            preferred_port=web_cfg.port,
            fallback_ports=web_cfg.fallback_ports,
            host=host,
            cli_port_override=cli_override,
        )
    except PortResolutionError as exc:
        logger.error("Port resolution failed: %s", exc)
        raise SystemExit(1) from exc

    # ── Detect fallback mode ──
    is_fallback = resolved_port != web_cfg.port and cli_override is None

    if is_fallback:
        logger.warning(
            "Preferred port %d was busy — using fallback port %d",
            web_cfg.port, resolved_port,
        )

        # Layer 1: Identify what process holds the preferred port
        from src.core.services.server_lifecycle import identify_port_occupant

        occupant = identify_port_occupant(host, web_cfg.port)
        if occupant["name"]:
            logger.info(
                "Port %d held by %s (PID %s)",
                web_cfg.port, occupant["name"], occupant["pid"],
            )

        # Store fallback info for the frontend banner
        app.config["PORT_FALLBACK"] = {
            "active": True,
            "preferred_port": web_cfg.port,
            "actual_port": resolved_port,
            "host": host,
            "config_path": "project.yml",
            "occupant_pid": occupant["pid"],
            "occupant_name": occupant["name"],
            "occupant_cmd": occupant["cmdline"],
        }

        # Build notification message with occupant info
        if occupant["name"]:
            notif_msg = (
                f"Port {web_cfg.port} held by {occupant['name']} "
                f"(PID {occupant['pid']}) — running on "
                f"port {resolved_port}."
            )
        else:
            notif_msg = (
                f"Port {web_cfg.port} was occupied — running on "
                f"port {resolved_port}. Update web.port in "
                f"project.yml or free port {web_cfg.port}."
            )

        # Create a persistent notification (deduped — one at a time)
        try:
            from src.core.services.notifications import create_notification

            create_notification(
                project_root,
                notif_type="port_fallback",
                title="Admin panel on fallback port",
                message=notif_msg,
                meta={
                    "preferred_port": web_cfg.port,
                    "actual_port": resolved_port,
                    "host": host,
                    "config_path": "project.yml",
                    "occupant_pid": occupant["pid"],
                    "occupant_name": occupant["name"],
                    "occupant_cmd": occupant["cmdline"],
                },
                dedup=True,
            )
        except Exception as exc:
            logger.debug("Could not create fallback notification: %s", exc)

        # Layer 2: CDP injection into foreign browser tabs
        try:
            from src.core.services.cdp_port_injector import start_injector

            start_injector(
                host=host,
                preferred_port=web_cfg.port,
                actual_port=resolved_port,
            )
        except Exception as exc:
            logger.debug("CDP port injector: %s", exc)
    else:
        app.config["PORT_FALLBACK"] = {"active": False}

    # Store resolved values for server_status()
    app.config["SERVER_HOST"] = host
    app.config["SERVER_PORT"] = resolved_port

    # Install signal handlers for graceful shutdown
    install_signal_handlers()

    logger.info("Starting web admin on %s:%d", host, resolved_port)
    app.run(
        host=host, port=resolved_port,
        debug=debug, use_reloader=False, threaded=True,
    )
