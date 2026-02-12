"""
Page builders — backward-compatible re-export shim.

The canonical page builders now live in
``src.core.services.pages_builders``. This module re-exports everything.
"""

from src.core.services.pages_builders import (  # noqa: F401
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
    get_builder,
    list_builders,
    _BUILDERS,
    _register_defaults,
)

# Re-export builder classes
from src.core.services.pages_builders.custom import CustomBuilder  # noqa: F401
from src.core.services.pages_builders.docusaurus import DocusaurusBuilder  # noqa: F401
from src.core.services.pages_builders.hugo import HugoBuilder  # noqa: F401
from src.core.services.pages_builders.mkdocs import MkDocsBuilder  # noqa: F401
from src.core.services.pages_builders.raw import RawBuilder  # noqa: F401
from src.core.services.pages_builders.sphinx import SphinxBuilder  # noqa: F401

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
