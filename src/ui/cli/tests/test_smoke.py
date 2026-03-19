"""Smoke tests for cli."""
from __future__ import annotations


def test_module_imports():
    """Verify the module can be imported."""
    import src.ui.cli  # noqa: F401


def test_version_floor():
    """Verify minimum Python version."""
    import sys
    assert sys.version_info >= (3, 8)
