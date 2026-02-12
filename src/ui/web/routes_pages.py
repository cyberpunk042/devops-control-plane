"""
Page routes — serves the dashboard HTML and built Pages sites.

Two concerns:
  1. Dashboard: GET / → the admin panel
  2. Pages sites: GET /pages/site/<segment>/<path:filepath> → the built
     static output for a segment (served directly by Flask, no random ports)
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from flask import Blueprint, abort, current_app, render_template, send_file

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/")
def dashboard():  # type: ignore[no-untyped-def]
    """Render the main dashboard."""
    return render_template("dashboard.html")


# ── Built Pages static serving ──────────────────────────────────────


def _pages_build_dir(segment: str) -> Path:
    """Return the build output directory for a segment."""
    root = Path(current_app.config["PROJECT_ROOT"])
    return root / ".pages" / segment / "build"


@pages_bp.route("/pages/site/<segment>/")
@pages_bp.route("/pages/site/<segment>/<path:filepath>")
def serve_pages_site(segment: str, filepath: str = "index.html"):  # type: ignore[no-untyped-def]
    """Serve built pages output as a static site.

    This is the integrated hosting — the built output is served
    directly by Flask at a stable URL. No random ports, no
    separate processes, works after restart.

    Handles:
      - Direct file requests (CSS, JS, images, etc.)
      - SPA fallback: if the file doesn't exist but an index.html
        exists in the requested directory, serve that instead
        (needed for Docusaurus client-side routing)
    """
    build_dir = _pages_build_dir(segment)
    if not build_dir.is_dir():
        abort(404, description=f"No build output for segment '{segment}'. Build it first.")

    requested = build_dir / filepath

    # Direct file match
    if requested.is_file():
        mime = mimetypes.guess_type(str(requested))[0] or "application/octet-stream"
        return send_file(requested, mimetype=mime)

    # Directory → try index.html
    if requested.is_dir():
        index = requested / "index.html"
        if index.is_file():
            return send_file(index, mimetype="text/html")

    # SPA fallback: for paths like /pages/site/docs/some/route
    # try the segment's root index.html (Docusaurus SPA routing)
    root_index = build_dir / "index.html"
    if root_index.is_file():
        return send_file(root_index, mimetype="text/html")

    abort(404, description=f"File not found: {filepath}")
