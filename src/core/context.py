"""
Project context — the single source of truth for "what project are we working on."

This module IS the infrastructure.  Every core service that needs
the project root imports from here.  The root is set ONCE at startup
by whichever entry point launches the app:

    - Web server:   server.py → context.set_project_root(root)
    - CLI:          main.py  → context.set_project_root(root)
    - Tests:        conftest  → context.set_project_root(tmp_path)

Design notes:
    - Module-level singleton (not a class).  Simple, no over-engineering.
    - get_project_root() returns None when unset — callers that need it
      for optional features (audit) silently skip.  Callers that require
      it can assert.
    - Thread-safe for reads (Python GIL + simple reference assignment).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


_project_root: Optional[Path] = None


def set_project_root(root: Path) -> None:
    """Register the project root for the current process."""
    global _project_root
    _project_root = root


def get_project_root() -> Optional[Path]:
    """Return the current project root, or None if not yet set."""
    return _project_root
