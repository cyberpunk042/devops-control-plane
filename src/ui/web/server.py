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
    app.config["PROJECT_ROOT"] = str(project_root or Path.cwd())
    app.config["CONFIG_PATH"] = str(config_path) if config_path else None
    app.config["MOCK_MODE"] = mock_mode
    app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB upload limit

    # Register blueprints
    from src.ui.web.routes_api import api_bp
    from src.ui.web.routes_backup import backup_bp
    from src.ui.web.routes_ci import ci_bp
    from src.ui.web.routes_config import config_bp
    from src.ui.web.routes_content import content_bp
    from src.ui.web.routes_docker import docker_bp
    from src.ui.web.routes_docs import docs_bp
    from src.ui.web.routes_infra import infra_bp
    from src.ui.web.routes_k8s import k8s_bp
    from src.ui.web.routes_terraform import terraform_bp
    from src.ui.web.routes_dns import dns_bp
    from src.ui.web.routes_integrations import integrations_bp
    from src.ui.web.routes_metrics import metrics_bp
    from src.ui.web.routes_packages import packages_bp
    from src.ui.web.routes_quality import quality_bp
    from src.ui.web.routes_security_scan import security_bp2
    from src.ui.web.routes_testing import testing_bp
    from src.ui.web.routes_pages import pages_bp
    from src.ui.web.routes_pages_api import pages_api_bp
    from src.ui.web.routes_secrets import secrets_bp
    from src.ui.web.routes_vault import vault_bp
    from src.ui.web.routes_devops import devops_bp
    from src.ui.web.routes_audit import audit_bp
    from src.ui.web.routes_project import project_bp

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
    app.register_blueprint(audit_bp)

    # Initialize vault with project root (for auto-lock)
    from src.ui.web import vault as vault_module

    vault_module.set_project_root(Path(app.config["PROJECT_ROOT"]))

    # Vault activity tracking — resets auto-lock timer on user actions
    @app.before_request
    def _track_vault_activity():  # type: ignore[no-untyped-def]
        from flask import request as req

        vault_module.touch_activity(req.path, req.method)

    # Data catalogs — inject into every template context
    from src.core.data import get_registry

    _registry = get_registry()
    app.config["DATA_REGISTRY"] = _registry

    @app.context_processor
    def _inject_data_catalogs():  # type: ignore[no-untyped-def]
        return {"dcp_data": _registry.to_js_dict()}

    logger.info("Web admin app created (root=%s)", project_root)
    return app


def run_server(
    app: Flask,
    host: str = "127.0.0.1",
    port: int = 8000,
    debug: bool = False,
) -> None:
    """Run the Flask development server."""
    logger.info("Starting web admin on %s:%d", host, port)
    app.run(host=host, port=port, debug=debug, use_reloader=False, threaded=True)
