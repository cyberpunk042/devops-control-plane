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

    @app.context_processor
    def _inject_data_catalogs():  # type: ignore[no-untyped-def]
        from src.core.services.devops.cache import _load_cache
        from src.core.config.stack_loader import discover_stacks

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

        # Merge static catalogs with project-level stacks
        dcp = _registry.to_js_dict()
        try:
            stacks = discover_stacks(Path(project_root) / "stacks")
            dcp["stacks"] = [
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
                for s in sorted(stacks.values(), key=lambda s: s.name)
            ]
        except Exception:
            dcp["stacks"] = []

        return {
            "dcp_data": dcp,
            "initial_state": initial,
        }

    # Start staleness watcher (background mtime polling → state:stale events)
    from src.core.services.staleness_watcher import start_watcher
    start_watcher(app.config["PROJECT_ROOT"])

    # Start project index (background file/symbol/peek indexing)
    from src.core.services.project_index import start_project_index
    start_project_index(app.config["PROJECT_ROOT"])

    logger.info("Web admin app created (root=%s)", project_root)
    return app


def run_server(
    app: Flask,
    host: str = "127.0.0.1",
    port: int = 8000,
    debug: bool = False,
) -> None:
    """Run the Flask development server."""
    # Store host/port for server_status()
    app.config["SERVER_HOST"] = host
    app.config["SERVER_PORT"] = port

    # Install signal handlers for graceful shutdown
    from src.core.services.server_lifecycle import install_signal_handlers
    install_signal_handlers()

    logger.info("Starting web admin on %s:%d", host, port)
    app.run(host=host, port=port, debug=debug, use_reloader=False, threaded=True)
