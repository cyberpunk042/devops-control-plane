"""Testing — framework detection, test runner, coverage, templates."""
from __future__ import annotations
from .ops import (  # noqa: F401
    testing_status,
    test_inventory, test_coverage, run_tests,
    generate_test_template, generate_coverage_config,
)
