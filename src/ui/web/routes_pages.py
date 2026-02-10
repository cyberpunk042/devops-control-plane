"""
Page routes — serves the dashboard HTML.
"""

from __future__ import annotations

from flask import Blueprint, render_template

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/")
def dashboard():  # type: ignore[no-untyped-def]
    """Render the main dashboard."""
    return render_template("dashboard.html")
