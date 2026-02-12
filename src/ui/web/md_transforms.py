"""
Markdown transforms — backward-compatible re-export shim.

The canonical logic now lives in ``src.core.services.md_transforms``.
"""

from src.core.services.md_transforms import (  # noqa: F401
    admonitions_to_docusaurus,
    admonitions_to_mkdocs,
    enrich_frontmatter,
    rewrite_links,
    transform_directory,
    _ADMONITION_RE,
    _MKDOCS_ADMONITION_RE,
    _FRONTMATTER_RE,
    _MD_LINK_RE,
)
