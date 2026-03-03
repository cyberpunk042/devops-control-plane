"""
Chat @-reference parsing, resolution, and autocomplete.

BACKWARD COMPATIBILITY SHIM — implementation has moved to:
    - ``refs_parse.py``       — parsing and regex patterns
    - ``refs_resolve.py``     — entity resolution
    - ``refs_autocomplete.py`` — autocomplete engine

This file re-exports everything so existing imports continue to work:
    from src.core.services.chat.chat_refs import parse_refs
    from src.core.services.chat.chat_refs import resolve_ref
    from src.core.services.chat.chat_refs import autocomplete
"""

# ── Parsing (refs_parse.py) ─────────────────────────────────────
from src.core.services.chat.refs_parse import (  # noqa: F401
    _REF_PATTERN,
    _VALID_TYPES,
    _relative_time,
    parse_ref_parts,
    parse_refs,
)

# ── Resolution (refs_resolve.py) ────────────────────────────────
from src.core.services.chat.refs_resolve import (  # noqa: F401
    _format_size,
    _resolve_audit,
    _resolve_branch,
    _resolve_code,
    _resolve_commit,
    _resolve_release,
    _resolve_run,
    _resolve_thread,
    _resolve_trace,
    resolve_ref,
)

# ── Autocomplete (refs_autocomplete.py) ─────────────────────────
from src.core.services.chat.refs_autocomplete import (  # noqa: F401
    autocomplete,
)
