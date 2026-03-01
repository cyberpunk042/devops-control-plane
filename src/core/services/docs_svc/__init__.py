"""Docs service — coverage, link checking, changelog/README generation."""
from __future__ import annotations
from .ops import (  # noqa: F401
    docs_status, docs_coverage, check_links,
    generate_changelog, generate_readme,
)
