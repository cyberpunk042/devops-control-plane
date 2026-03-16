"""
Generic output parser — fallback for ecosystems without specialized parsers.

Uses only the base class generic detection (ERROR, WARNING, DEPRECATED).
No ecosystem-specific patterns. Good enough until a specialized parser
is written for the ecosystem.
"""

from __future__ import annotations

from .base import BaseOutputParser


class GenericParser(BaseOutputParser):
    """Fallback parser — delegates everything to base class generic detection."""

    def __init__(self, scope: str, ecosystem: str = "generic") -> None:
        super().__init__(scope, ecosystem)
