"""
Page builders — pluggable static site generators.

Registry of all available builders. Import this module to get
access to the builder registry.
"""

from __future__ import annotations

from .base import (
    BuilderInfo,
    BuildResult,
    ConfigField,
    LogStream,
    PageBuilder,
    PipelineResult,
    SegmentConfig,
    StageInfo,
    StageResult,
    run_pipeline,
)
from .custom import CustomBuilder
from .docusaurus import DocusaurusBuilder
from .hugo import HugoBuilder
from .mkdocs import MkDocsBuilder
from .raw import RawBuilder
from .sphinx import SphinxBuilder

# ── Builder registry ────────────────────────────────────────────────

_BUILDERS: dict[str, PageBuilder] = {}


def _register_defaults() -> None:
    """Register all built-in builders."""
    for cls in (RawBuilder, MkDocsBuilder, HugoBuilder, DocusaurusBuilder, SphinxBuilder, CustomBuilder):
        builder = cls()
        _BUILDERS[builder.info().name] = builder


def get_builder(name: str) -> PageBuilder | None:
    """Get a builder by name."""
    if not _BUILDERS:
        _register_defaults()
    return _BUILDERS.get(name)


def list_builders() -> list[BuilderInfo]:
    """List all builders with availability status."""
    if not _BUILDERS:
        _register_defaults()

    result = []
    for builder in _BUILDERS.values():
        info = builder.info()
        info.available = builder.detect()
        result.append(info)
    return result


__all__ = [
    "BuilderInfo",
    "BuildResult",
    "ConfigField",
    "LogStream",
    "PageBuilder",
    "PipelineResult",
    "SegmentConfig",
    "StageInfo",
    "StageResult",
    "get_builder",
    "list_builders",
    "run_pipeline",
]
