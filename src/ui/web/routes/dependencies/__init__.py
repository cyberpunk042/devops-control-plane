"""Dependency management routes — tree, operations, notes."""

from flask import Blueprint

dep_bp = Blueprint("dependencies", __name__)

from . import api  # noqa: E402, F401
