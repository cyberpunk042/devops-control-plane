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

    # Initialize vault with project root (for auto-lock)
    from src.core.services import vault as vault_module

    vault_module.set_project_root(app.config["PROJECT_ROOT"])

    # Vault activity tracking — resets auto-lock timer on user actions
    @app.before_request
    def _track_vault_activity():  # type: ignore[no-untyped-def]
        from flask import request as req

        vault_module.touch_activity(req.path, req.method)

    # Data catalogs — inject into every template context
    from src.core.data import get_registry

    _registry = get_registry()
    app.config["DATA_REGISTRY"] = _registry

    # Keys safe to pre-inject into HTML (~10 KB total).
    # Audit L2 keys (audit:l2:*) are excluded — too large (200+ KB).
    _INJECT_KEYS = frozenset({
        # DevOps tab (9 cards)
        "security", "testing", "quality", "packages", "env", "docs",
        "k8s", "terraform", "dns",
        # Integrations tab
        "git", "github", "ci", "docker",
        "gh-pulls", "gh-runs", "gh-workflows",
        # Dashboard
        "project-status",
        # Audit L0/L1 (small summaries)
        "audit:system", "audit:deps", "audit:structure",
        "audit:clients", "audit:scores",
        # Wizard detect
        "wiz:detect",
    })

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

    @app.context_processor
    def _inject_data_catalogs():  # type: ignore[no-untyped-def]
        from src.core.services.devops.cache import _load_cache

        # Build initial state from disk cache (available even on cold start)
        initial: dict[str, dict] = {}
        try:
            cache = _load_cache(Path(project_root))
            for key in _INJECT_KEYS:
                entry = cache.get(key)
                if entry and "data" in entry:
                    initial[key] = {"data": entry["data"]}
        except Exception:
            pass  # Degrade gracefully — cards will fall back to API

        # Merge static catalogs with pre-computed stacks
        dcp = _registry.to_js_dict()
        dcp["stacks"] = _stacks_js

        return {
            "dcp_data": dcp,
            "initial_state": initial,
        }

    # Start staleness watcher (background mtime polling → state:stale events)
    from src.core.services.staleness_watcher import start_watcher
    start_watcher(app.config["PROJECT_ROOT"])

    # Start project index (background file/symbol/peek indexing)
    # — gated by server setting: when disabled, no background thread
    from src.core.services.server_settings import is_peek_index_enabled
    if is_peek_index_enabled(app.config["PROJECT_ROOT"]):
        from src.core.services.project_index import start_project_index
        start_project_index(app.config["PROJECT_ROOT"])
    else:
        logger.info("Project index disabled by server settings")

    # Restore file logging if previously enabled
    from src.core.services.server_settings import load_settings, toggle_file_logging
    _startup_settings = load_settings(app.config["PROJECT_ROOT"])
    if _startup_settings.get("file_logging_enabled"):
        toggle_file_logging(app.config["PROJECT_ROOT"], True)

    # WSL→Windows tunnel: NOT auto-started.
    # The user activates it from Tab Mesh → WSL Channel UI.
    # When inactive, the system uses curl.exe bridge (the existing path).

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
