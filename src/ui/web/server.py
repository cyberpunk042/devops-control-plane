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
    from src.ui.web.routes_config import config_bp
    from src.ui.web.routes_content import content_bp
    from src.ui.web.routes_integrations import integrations_bp
    from src.ui.web.routes_pages import pages_bp
    from src.ui.web.routes_pages_api import pages_api_bp
    from src.ui.web.routes_secrets import secrets_bp
    from src.ui.web.routes_vault import vault_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(config_bp, url_prefix="/api")
    app.register_blueprint(vault_bp, url_prefix="/api")
    app.register_blueprint(secrets_bp, url_prefix="/api")
    app.register_blueprint(content_bp, url_prefix="/api")
    app.register_blueprint(backup_bp, url_prefix="/api")
    app.register_blueprint(integrations_bp, url_prefix="/api")
    app.register_blueprint(pages_api_bp, url_prefix="/api")

    # Initialize vault with project root (for auto-lock)
    from src.ui.web import vault as vault_module

    vault_module.set_project_root(Path(app.config["PROJECT_ROOT"]))

    # Vault activity tracking — resets auto-lock timer on user actions
    @app.before_request
    def _track_vault_activity():  # type: ignore[no-untyped-def]
        from flask import request as req

        vault_module.touch_activity(req.path, req.method)

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
    app.run(host=host, port=port, debug=debug, use_reloader=False)
