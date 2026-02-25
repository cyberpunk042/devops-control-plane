"""
L1 Domain — Input and output validation (pure).

Validates user-provided inputs and rendered template output.
No I/O, no subprocess.
"""

from __future__ import annotations

import json
import re
from typing import Any


def _check_unsubstituted(rendered: str) -> list[str]:
    """Return list of unsubstituted ``{var}`` placeholders.

    Scans the rendered output for remaining ``{word}`` tokens that
    were not replaced by either built-in or user-provided inputs.
    Ignores JSON-like braces (``{}``, ``{{``, ``}}``) and known
    safe patterns like ``{0}``, ``{1}`` (format string indices).

    Returns:
        List of unresolved variable names (empty = all good).
    """
    # Match {word} but not {{ or }} or {0} or empty {}
    pattern = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
    return pattern.findall(rendered)


def _validate_input(input_def: dict, value: Any) -> str | None:
    """Validate a single input value against its schema.

    Args:
        input_def: Input definition from the recipe
                   (``type``, ``options``, ``validation``, etc.).
        value: User-provided value to check.

    Returns:
        Error message string, or ``None`` if valid.
    """
    input_type = input_def.get("type", "text")

    if input_type == "select":
        options = input_def.get("options", [])
        if value not in options:
            return f"Must be one of: {options}"

    elif input_type == "number":
        v = input_def.get("validation", {})
        try:
            num = int(value) if isinstance(value, str) else value
        except (ValueError, TypeError):
            return f"Must be a number"
        if "min" in v and num < v["min"]:
            return f"Must be >= {v['min']}"
        if "max" in v and num > v["max"]:
            return f"Must be <= {v['max']}"

    elif input_type == "text":
        if not isinstance(value, str):
            return "Must be a string"
        v = input_def.get("validation", {})
        if "min_length" in v and len(value) < v["min_length"]:
            return f"Must be at least {v['min_length']} characters"
        if "max_length" in v and len(value) > v["max_length"]:
            return f"Must be at most {v['max_length']} characters"
        if "pattern" in v:
            if not re.match(v["pattern"], value):
                return f"Must match pattern: {v['pattern']}"

    elif input_type == "path":
        if not isinstance(value, str):
            return "Must be a string"
        if not value.startswith("/"):
            return "Must be an absolute path"

    elif input_type == "boolean":
        if not isinstance(value, bool):
            return "Must be true or false"

    elif input_type == "password":
        if not isinstance(value, str):
            return "Must be a string"
        v = input_def.get("validation", {})
        min_len = v.get("min_length", 1)
        if len(value) < min_len:
            return f"Must be at least {min_len} characters"
        # password fields are implicitly sensitive — the value must
        # never be logged, returned in plan state, or sent to frontend

    return None


def _validate_output(content: str, fmt: str) -> str | None:
    """Validate rendered template content against its declared format.

    Args:
        content: Rendered file content to check.
        fmt: One of ``"json"``, ``"yaml"``, ``"ini"``, ``"raw"``.

    Returns:
        Error message if invalid, or ``None`` if valid.
    """
    if fmt == "json":
        try:
            json.loads(content)
        except json.JSONDecodeError as exc:
            return f"Invalid JSON: {exc}"

    elif fmt == "yaml":
        try:
            import yaml  # type: ignore[import-untyped]
            yaml.safe_load(content)
        except Exception as exc:
            return f"Invalid YAML: {exc}"

    elif fmt == "ini":
        import configparser
        parser = configparser.ConfigParser()
        try:
            parser.read_string(content)
        except configparser.Error as exc:
            return f"Invalid INI: {exc}"

    # "raw" → no validation
    return None
