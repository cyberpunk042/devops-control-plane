"""
Re-export shared web helpers into the content package namespace.

Sub-modules (files.py, preview.py, manage.py) import from ``.helpers``
so they get ``project_root``, ``resolve_safe_path``, and ``get_enc_key``
without reaching two packages up.
"""

from src.ui.web.helpers import (       # noqa: F401 — re-exports
    project_root,
    resolve_safe_path,
    get_enc_key,
)
