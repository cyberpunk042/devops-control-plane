"""
Kubernetes routes — manifest status, validation, cluster probing, Helm, wizard.

Blueprint: k8s_bp
Prefix: /api

Sub-modules:
    detect.py   — status, validate (offline manifest analysis)
    cluster.py  — resources, namespaces, events, describe, pod-logs, storageclasses
    actions.py  — apply, delete, scale
    helm.py     — list, values, install, upgrade, template
    generate.py — manifest generation, wizard generation
    wizard.py   — wizard state load/save/wipe
    skaffold.py — skaffold status
"""

from __future__ import annotations

from flask import Blueprint

k8s_bp = Blueprint("k8s", __name__)

from . import detect, cluster, actions, helm, generate, wizard, skaffold  # noqa: E402, F401
