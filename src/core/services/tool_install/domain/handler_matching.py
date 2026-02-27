"""
L1 Domain — Handler matching (pure).

Pattern matching against stderr and exit codes. Cascades through all
handler layers and collects every matching option — does NOT stop
at first match.

No I/O, no subprocess, no imports of L2+ modules.
"""

from __future__ import annotations

import re
from typing import Any

from src.core.services.tool_install.data.remediation_handlers import (
    BOOTSTRAP_HANDLERS,
    INFRA_HANDLERS,
    METHOD_FAMILY_HANDLERS,
)
from src.core.services.tool_install.data.tool_failure_handlers import (
    TOOL_FAILURE_HANDLERS,
)


# ── Single handler match ────────────────────────────────────────

def _matches(handler: dict, stderr: str, exit_code: int) -> bool:
    """Check if a handler's detection criteria match the failure.

    A handler matches when:
      - Its ``pattern`` (regex, case-insensitive) matches anywhere
        in ``stderr``, AND
      - If ``exit_code`` is specified in the handler, it must match.

    A handler with an empty pattern matches ONLY by exit_code
    (or by ``detect_fn`` — not yet implemented, reserved for future).

    Args:
        handler: Handler dict with ``pattern`` and optional ``exit_code``.
        stderr: stderr output from the failed command.
        exit_code: Process exit code.

    Returns:
        True if the handler matches the failure.
    """
    # Exit code filter (if specified, must match)
    handler_exit = handler.get("exit_code")
    if handler_exit is not None and handler_exit != exit_code:
        return False

    # Pattern match (empty pattern = match by exit_code only)
    pattern = handler.get("pattern", "")
    if not pattern:
        # Empty pattern: only match if exit_code was specified AND matched
        return handler_exit is not None

    try:
        return bool(re.search(pattern, stderr, re.IGNORECASE))
    except re.error:
        return False


# ── Cascade through all layers ──────────────────────────────────

def _collect_all_options(
    tool_id: str,
    method: str,
    stderr: str,
    exit_code: int,
    recipe: dict | None = None,
) -> tuple[list[dict], list[dict]]:
    """Cascade through all handler layers, collecting matching options.

    Scans ALL layers (recipe → method-family → infra → bootstrap).
    Does NOT stop at first match — collects everything.

    Options are tagged with their source layer for priority sorting.
    Deduplicated by option ``id`` (first occurrence wins, preserving
    recipe > method_family > infra > bootstrap priority).

    Args:
        tool_id: The tool that failed.
        method: Install method used (e.g. ``"pip"``, ``"cargo"``).
        stderr: stderr output from the failed command.
        exit_code: Process exit code.
        recipe: Optional recipe dict (to check ``on_failure``).

    Returns:
        Tuple of:
          - matched_handlers: List of handler dicts that matched
            (with ``_matched_layer`` injected).
          - merged_options: Deduplicated list of option dicts
            (with ``_source_layer`` and ``_source_handler`` injected).
    """
    matched_handlers: list[dict] = []
    merged_options: list[dict] = []
    seen_option_ids: set[str] = set()

    def _scan_handlers(
        handlers: list[dict],
        layer_name: str,
    ) -> None:
        """Scan a list of handlers, collecting matches."""
        for handler in handlers:
            if not _matches(handler, stderr, exit_code):
                continue

            # Tag the handler with its source layer
            tagged_handler = {**handler, "_matched_layer": layer_name}
            matched_handlers.append(tagged_handler)

            # Collect options, dedup by id
            for option in handler.get("options", []):
                opt_id = option.get("id", "")
                if opt_id in seen_option_ids:
                    continue
                seen_option_ids.add(opt_id)
                tagged_option = {
                    **option,
                    "_source_layer": layer_name,
                    "_source_handler": handler.get("failure_id", ""),
                }
                merged_options.append(tagged_option)

    # Layer 3: Tool-specific handlers (highest priority)
    tool_handlers = TOOL_FAILURE_HANDLERS.get(tool_id, [])
    if tool_handlers:
        _scan_handlers(tool_handlers, "recipe")

    # Layer 2b: Install-pattern family (via recipe's install_via field)
    # e.g. phpstan's _default is really "composer global require" →
    #      install_via: {"_default": "composer_global"} →
    #      checks METHOD_FAMILY_HANDLERS["composer_global"]
    if recipe:
        install_via = recipe.get("install_via", {}).get(method)
        if install_via and install_via != method:
            via_handlers = METHOD_FAMILY_HANDLERS.get(install_via, [])
            if via_handlers:
                _scan_handlers(via_handlers, "method_family")

    # Layer 2a: Method-family handlers (by method key)
    method_handlers = METHOD_FAMILY_HANDLERS.get(method, [])
    _scan_handlers(method_handlers, "method_family")

    # Layer 1: Infrastructure handlers
    _scan_handlers(INFRA_HANDLERS, "infra")

    # Layer 0: Bootstrap handlers
    _scan_handlers(BOOTSTRAP_HANDLERS, "bootstrap")

    return matched_handlers, merged_options


def _sort_options(options: list[dict]) -> list[dict]:
    """Sort options by recommendation priority.

    Order:
      1. Recommended options first
      2. Within same recommendation level: recipe > method_family > infra > bootstrap
      3. Ready options before locked, locked before impossible

    Args:
        options: List of option dicts (with ``_source_layer``).

    Returns:
        Sorted list (new list, original not mutated).
    """
    layer_order = {
        "recipe": 0,
        "method_family": 1,
        "infra": 2,
        "bootstrap": 3,
    }

    # Availability sort order (computed at runtime, may not be present yet)
    avail_order = {
        "ready": 0,
        "locked": 1,
        "impossible": 2,
    }

    def sort_key(opt: dict) -> tuple:
        return (
            0 if opt.get("recommended") else 1,
            layer_order.get(opt.get("_source_layer", ""), 9),
            avail_order.get(opt.get("availability", "ready"), 9),
        )

    return sorted(options, key=sort_key)
