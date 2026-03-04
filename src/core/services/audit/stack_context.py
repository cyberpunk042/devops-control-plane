"""
Stack context intelligence — use module stack declarations to inform parsing.

Phase 8.2: Instead of treating all files the same, this module uses the
project.yml ``stack`` declarations to provide context-aware intelligence:

    - ``python-flask`` → expect Jinja2 templates in ``templates/``
    - ``python-lib``   → expect pure Python, no templates
    - ``python-cli``   → expect Click commands, no web content
    - ``node-nextjs``  → expect TSX pages in ``pages/`` or ``app/``
    - ``helm``         → expect Go templates in ``templates/``

This context helps disambiguate files like:
    - ``.yaml`` in a Helm chart → Go template YAML
    - ``.yaml`` in ``.github/workflows/`` → GitHub Actions YAML
    - ``.html`` in ``python-flask`` templates dir → Jinja2 template

Consumers: template_parser (Phase 8.1), quality rubrics (Phase 4)
"""

from __future__ import annotations

from pathlib import Path


# ═══════════════════════════════════════════════════════════════════
#  Stack → expected file patterns
# ═══════════════════════════════════════════════════════════════════

# Maps stack name → dict of directory patterns and expected content types.
# Each entry: { "pattern": "expected_type" }
# pattern: relative directory suffix to match
# expected_type: what files in that directory ARE (overrides extension-based guessing)

STACK_EXPECTATIONS: dict[str, dict[str, str]] = {
    "python-flask": {
        "templates/":         "jinja2",           # Jinja2 templates
        "templates/scripts/": "jinja2-js",        # JS wrapped in Jinja2
        "templates/partials/": "jinja2",           # Jinja2 partials
        "static/":            "static-asset",      # CSS/JS/images
    },
    "python-lib": {
        # No special expectations — pure Python
    },
    "python-cli": {
        # No special expectations — pure Python + Click
    },
    "node-nextjs": {
        "pages/":    "tsx-page",       # Next.js pages (TSX)
        "app/":      "tsx-page",       # Next.js app router (TSX)
        "components/": "tsx-component", # React components
    },
    "node-vite": {
        "src/":      "tsx-component",  # Vite entry + components
    },
    "helm": {
        "templates/": "go-template",   # Helm Go templates
        "charts/":    "helm-subchart", # Subcharts
    },
    "markdown": {
        # All files expected to be markdown content
    },
}


def get_stack_context(
    file_path: str,
    modules: list[dict],
) -> dict:
    """Determine stack context for a file based on module declarations.

    Args:
        file_path: Relative file path (e.g. "src/ui/web/templates/base.html")
        modules: List of module dicts from project.yml, each with
                 'name', 'path', 'stack' keys.

    Returns:
        Dict with:
            module_name:    Name of the matching module (or "")
            module_path:    Path prefix of the matching module (or "")
            stack:          Stack declaration (e.g. "python-flask")
            expected_type:  Expected content type based on stack + directory
                           (e.g. "jinja2", "go-template", or "")
    """
    result = {
        "module_name": "",
        "module_path": "",
        "stack": "",
        "expected_type": "",
    }

    # Find which module this file belongs to
    best_match = ""
    best_module: dict = {}
    for mod in modules:
        mod_path = mod.get("path", "")
        if not mod_path:
            continue
        # Normalize: ensure trailing slash for prefix matching
        prefix = mod_path.rstrip("/") + "/"
        if file_path.startswith(prefix) and len(prefix) > len(best_match):
            best_match = prefix
            best_module = mod

    if not best_module:
        return result

    result["module_name"] = best_module.get("name", "")
    result["module_path"] = best_module.get("path", "")
    result["stack"] = best_module.get("stack", "")

    # Look up stack expectations
    stack = result["stack"]
    expectations = STACK_EXPECTATIONS.get(stack, {})
    if not expectations:
        return result

    # Check if the file's relative-to-module path matches any expected pattern
    # Sort by pattern length (longest first) so most-specific match wins
    rel_to_module = file_path[len(best_match):]
    for dir_pattern, expected_type in sorted(
        expectations.items(), key=lambda kv: len(kv[0]), reverse=True,
    ):
        if rel_to_module.startswith(dir_pattern):
            result["expected_type"] = expected_type
            break

    return result


def get_module_for_path(
    file_path: str,
    modules: list[dict],
) -> dict:
    """Find the module that owns a file path.

    Args:
        file_path: Relative file path.
        modules: List of module dicts from project.yml.

    Returns:
        The matching module dict, or empty dict if no match.
    """
    best_match = ""
    best_module: dict = {}
    for mod in modules:
        mod_path = mod.get("path", "")
        if not mod_path:
            continue
        prefix = mod_path.rstrip("/") + "/"
        if file_path.startswith(prefix) and len(prefix) > len(best_match):
            best_match = prefix
            best_module = mod
    return best_module
