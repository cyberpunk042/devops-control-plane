"""
Docker routes — container and compose management endpoints.

Blueprint: docker_bp
Prefix: /api

Sub-modules:
    detect.py    — status / detection (1 endpoint)
    observe.py   — containers, images, compose, logs, stats, networks, volumes, inspect
    actions.py   — build, up, down, restart, prune, pull, exec, rm, rmi
    generate.py  — dockerfile, dockerignore, compose, compose-wizard, write
    stream.py    — SSE streaming for long-running operations
"""

from __future__ import annotations

from flask import Blueprint

docker_bp = Blueprint("docker", __name__)

from . import detect, observe, actions, generate, stream  # noqa: E402, F401
