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

from flask import Blueprint, abort, current_app, make_response, render_template, send_file

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/")
def dashboard():  # type: ignore[no-untyped-def]
    """Render the main dashboard."""
    return render_template("dashboard.html")


# ── Service Worker (Tab Mesh focus engine) ──────────────────────────


@pages_bp.route("/sw.js")
def service_worker():  # type: ignore[no-untyped-def]
    """Serve the Tab Mesh service worker at the root scope.

    The SW must be at ``/sw.js`` (not ``/static/sw.js``) so that
    ``navigator.serviceWorker.register('/sw.js', { scope: '/' })``
    places it at the root scope, giving it control over all pages
    on this origin (admin panel + Docusaurus sites).
    """
    static_dir = Path(current_app.static_folder)
    sw_path = static_dir / "sw.js"
    if not sw_path.is_file():
        abort(404, description="Service worker not found")
    resp = make_response(send_file(sw_path, mimetype="application/javascript"))
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


# ── Tab Mesh light client (injected into Pages HTML) ────────────────

_TAB_MESH_LIGHT_SCRIPT = None


def _get_light_script() -> str:
    """Load the tab mesh light script once and cache it."""
    global _TAB_MESH_LIGHT_SCRIPT
    if _TAB_MESH_LIGHT_SCRIPT is None:
        tmpl_dir = Path(current_app.template_folder)
        script_path = tmpl_dir / "scripts" / "_tab_mesh_light.html"
        if script_path.is_file():
            _TAB_MESH_LIGHT_SCRIPT = script_path.read_text(encoding="utf-8")
        else:
            _TAB_MESH_LIGHT_SCRIPT = ""
    return _TAB_MESH_LIGHT_SCRIPT


def _inject_light_mesh(html_bytes: bytes) -> bytes:
    """Inject the light tab mesh script before </body> in HTML."""
    script = _get_light_script()
    if not script:
        return html_bytes

    html = html_bytes.decode("utf-8", errors="replace")
    # Inject before </body>
    close_body = html.rfind("</body>")
    if close_body == -1:
        return html_bytes

    injected = html[:close_body] + script + "\n" + html[close_body:]
    return injected.encode("utf-8")


# ── Built Pages static serving ──────────────────────────────────────


def _pages_build_dir(segment: str) -> Path:
    """Return the build output directory for a segment."""
    root = Path(current_app.config["PROJECT_ROOT"])
    return root / ".pages" / segment / "build"


def _serve_html(file_path: Path) -> object:
    """Serve an HTML file.

    Previously injected the tab mesh light client, but Docusaurus
    now has useTabMesh.ts built in with full CDP support.
    """
    resp = make_response(send_file(file_path, mimetype="text/html"))
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp


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
        if mime == "text/html":
            return _serve_html(requested)
        return send_file(requested, mimetype=mime)

    # Directory → try index.html
    if requested.is_dir():
        index = requested / "index.html"
        if index.is_file():
            return _serve_html(index)

    # SPA fallback: for paths like /pages/site/docs/some/route
    # try the segment's root index.html (Docusaurus SPA routing)
    root_index = build_dir / "index.html"
    if root_index.is_file():
        return _serve_html(root_index)

    abort(404, description=f"File not found: {filepath}")
