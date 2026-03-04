"""Artifacts API blueprint."""

from flask import Blueprint

bp = Blueprint("artifacts", __name__, url_prefix="/api/artifacts")

from . import api  # noqa: F401, E402
