"""
Generated file model — used by all generators.
"""

from __future__ import annotations

from pydantic import BaseModel


class GeneratedFile(BaseModel):
    """A file produced by the facilitate/generate phase.

    Attributes:
        path:      Relative path from project root.
        content:   Full file content.
        overwrite: Whether to overwrite if already exists.
        reason:    Why this file was generated.
    """

    path: str
    content: str
    overwrite: bool = False
    reason: str = ""
