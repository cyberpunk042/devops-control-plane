"""
Auto-mark all tests in this directory as integration tests.

These are TDD requirement tests — they define what "finished" looks like.
Many will FAIL until the code is built to satisfy them.

Run ONLY integration tests:
    pytest tests/integration/ -m integration

Run ONLY unit tests (default):
    pytest -m "not integration"

Run everything:
    pytest -m ""
"""

import pytest


def pytest_collection_modifyitems(items):
    """Auto-apply the 'integration' marker to every test in this directory."""
    for item in items:
        if "/integration/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
