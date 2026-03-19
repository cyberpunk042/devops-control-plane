"""Module-level test fixtures for cli."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def module_root():
    return Path(__file__).parent.parent
