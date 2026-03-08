"""
Scripts registry — discovery, metadata parsing, and query functions.

Discovers scripts from both the project root (user-owned) and the
program template directory, merges them (root overrides templates),
parses @script/@param metadata headers, and provides query functions.

Caches results per project_root (invalidated by refresh_registry).
Thread-safe via threading.Lock (consistent with event_bus pattern).
"""

from __future__ import annotations

import logging

import re
import threading
from pathlib import Path

from src.core.services.scripts.config import load_scripts_config
from src.core.services.scripts.models import ScriptConfig, ScriptMeta, ScriptParameter

logger = logging.getLogger(__name__)


# ── Constants ───────────────────────────────────────────────────────

SCRIPT_EXTENSIONS = {".py", ".sh", ".bash", ".ps1"}
"""File extensions recognized as potential scripts."""

SHEBANG_LANGUAGES = {
    "python": "python",
    "python3": "python",
    "bash": "bash",
    "sh": "bash",
    "pwsh": "powershell",
    "powershell": "powershell",
}
"""Mapping from shebang interpreter names to language identifiers."""

TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "script_templates"
"""Absolute path to the built-in template scripts directory.
Resolves to: src/core/data/script_templates/
"""


# ── Cache ───────────────────────────────────────────────────────────

_lock = threading.Lock()
_registry_cache: dict[str, list[ScriptMeta]] = {}
"""Module-level cache: project_root string → discovered scripts list."""


# ── Discovery ───────────────────────────────────────────────────────


def discover_scripts(
    project_root: Path,
    config: ScriptConfig | None = None,
) -> list[ScriptMeta]:
    """Discover all scripts from root + templates, merge, return metadata list.

    Discovery order:
    1. Load config (from project.yml or defaults)
    2. Scan templates (Layer 2) first — unless template_source="never"
    3. Scan root (Layer 1) second — from config.root path
    4. Root overrides templates with matching @override declarations

    Scanned file extensions: .py, .sh, .bash, .ps1
    Also scans files with no extension that have a recognized shebang line.

    Files without @script headers are silently skipped (helpers, libs, etc.)

    Returns:
        List of ScriptMeta, one per discovered script.
    """
    cfg = config or load_scripts_config(project_root)

    # Layer 2: Templates
    templates: dict[str, ScriptMeta] = {}
    if _should_load_templates(cfg):
        if TEMPLATE_DIR.is_dir():
            for meta in _scan_directory(TEMPLATE_DIR, source="template"):
                templates[meta.id] = meta

    # Layer 1: Root scripts
    root_scripts: dict[str, ScriptMeta] = {}
    root_dir = project_root / cfg.root
    if root_dir.is_dir():
        for meta in _scan_directory(root_dir, source="root"):
            root_scripts[meta.id] = meta

    # Merge: root overrides templates
    result = _merge_scripts(templates, root_scripts)

    return result


def _should_load_templates(config: ScriptConfig) -> bool:
    """Determine whether to load template scripts based on config."""
    if config.template_source == "never":
        return False
    if config.template_source == "always":
        return True
    # "auto" — load if the template directory exists
    return TEMPLATE_DIR.is_dir()


def _scan_directory(base_dir: Path, source: str) -> list[ScriptMeta]:
    """Scan a directory recursively for script files with @script headers.

    Skips:
    - Files inside lib/ directories (shared modules, not scripts)
    - Files inside __pycache__/ directories
    - Files without @script headers
    """
    results: list[ScriptMeta] = []

    for filepath in sorted(base_dir.rglob("*")):
        if not filepath.is_file():
            continue

        # Skip lib/ and __pycache__/ directories
        rel = filepath.relative_to(base_dir)
        parts = rel.parts
        if any(p in ("lib", "__pycache__") for p in parts[:-1]):
            continue

        # Check extension or shebang
        if filepath.suffix not in SCRIPT_EXTENSIONS:
            if filepath.suffix:
                continue  # Has an extension but not a recognized one
            # No extension — check for shebang
            if not _has_script_shebang(filepath):
                continue

        # Parse metadata
        meta = parse_script_meta(filepath, source)
        if meta is None:
            continue  # No @script header — not a managed script

        # Set path info
        meta.path = str(filepath.resolve())
        meta.relative_path = str(rel)

        # For templates, use relative path as ID (e.g., "generators/class_diagrams")
        if source == "template":
            meta.id = str(rel.with_suffix(""))
            # Normalize path separators for Windows compat
            meta.id = meta.id.replace("\\", "/")

        results.append(meta)

    return results


def _has_script_shebang(filepath: Path) -> bool:
    """Check if a file without extension has a recognized shebang line."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            first_line = f.readline(256)
        if not first_line.startswith("#!"):
            return False
        return _language_from_shebang(first_line) is not None
    except (OSError, UnicodeDecodeError):
        return False


def _language_from_shebang(shebang_line: str) -> str | None:
    """Extract language from a shebang line.

    Handles:
        #!/usr/bin/env python3  → "python"
        #!/bin/bash             → "bash"
        #!/usr/bin/env pwsh     → "powershell"
    """
    parts = shebang_line.strip().lstrip("#!").split()
    if not parts:
        return None

    # Handle /usr/bin/env <interpreter>
    if parts[0].endswith("/env") and len(parts) > 1:
        interpreter = Path(parts[1]).name
    else:
        interpreter = Path(parts[0]).name

    return SHEBANG_LANGUAGES.get(interpreter)


def _merge_scripts(
    templates: dict[str, ScriptMeta],
    root_scripts: dict[str, ScriptMeta],
) -> list[ScriptMeta]:
    """Merge root scripts over templates.

    A root script overrides a template if it declares @override: <template_id>.
    The template is removed from results, and the root script gets source="override".
    """
    # Start with templates
    merged: dict[str, ScriptMeta] = dict(templates)

    for script_id, meta in root_scripts.items():
        if meta.override_target:
            # This root script overrides a template
            if meta.override_target in merged:
                del merged[meta.override_target]
                logger.debug(
                    "Script %s overrides template %s",
                    script_id, meta.override_target,
                )
            else:
                logger.warning(
                    "Script %s declares @override: %s, but no such template exists",
                    script_id, meta.override_target,
                )
            meta.source = "override"

        merged[script_id] = meta

    return list(merged.values())


# ── Metadata Parser ─────────────────────────────────────────────────


def parse_script_meta(filepath: Path, source: str) -> ScriptMeta | None:
    """Parse the @script header from a script file.

    Reads the first docstring or comment block, extracts
    @script and @param declarations.

    Returns None if the file has no @script header (not a managed script).
    Files without @script are silently skipped — they might be
    helper modules, lib files, or non-managed scripts.
    """
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    # Determine language from extension or shebang
    language = _detect_language(filepath, content)

    # Extract the header block
    header_text = _extract_header_block(content, language)
    if header_text is None:
        return None

    # Check for @script marker
    if "@script" not in header_text:
        return None

    # Parse fields and params
    return _parse_header_fields(header_text, filepath, source, language)


def _detect_language(filepath: Path, content: str) -> str:
    """Detect script language from extension or shebang."""
    ext = filepath.suffix.lower()
    if ext == ".py":
        return "python"
    if ext in (".sh", ".bash"):
        return "bash"
    if ext == ".ps1":
        return "powershell"

    # No extension — try shebang
    first_line = content.split("\n", 1)[0] if content else ""
    if first_line.startswith("#!"):
        lang = _language_from_shebang(first_line)
        if lang:
            return lang

    return "python"  # Fallback


def _extract_header_block(content: str, language: str) -> str | None:
    """Extract the metadata header block from file content.

    For Python: reads the module docstring (first triple-quoted string).
    For Bash/Shell: reads the leading # comment block.
    For PowerShell: reads the first <# ... #> block.

    Returns None if no suitable block is found.
    """
    if language == "python":
        return _extract_python_docstring(content)
    elif language == "bash":
        return _extract_shell_comment_block(content)
    elif language == "powershell":
        return _extract_powershell_comment_block(content)
    return None


def _extract_python_docstring(content: str) -> str | None:
    """Extract the first triple-quoted docstring from Python content."""
    # Skip shebang and blank/comment lines to find the docstring
    for delimiter in ['"""', "'''"]:
        idx = content.find(delimiter)
        if idx == -1:
            continue
        end_idx = content.find(delimiter, idx + 3)
        if end_idx == -1:
            continue
        return content[idx + 3 : end_idx]
    return None


def _extract_shell_comment_block(content: str) -> str | None:
    """Extract the leading # comment block from shell content.

    Strips the '# ' prefix from each line. Stops at the first
    non-comment line (excluding shebang and blank lines).
    """
    lines = content.splitlines()
    comment_lines: list[str] = []
    started = False

    for line in lines:
        stripped = line.strip()
        # Skip shebang
        if stripped.startswith("#!"):
            continue
        # Skip blank lines before comment block starts
        if not started and not stripped:
            continue
        # Comment line
        if stripped.startswith("#"):
            started = True
            # Strip leading '# ' or '#'
            text = stripped[1:]
            if text.startswith(" "):
                text = text[1:]
            comment_lines.append(text)
        elif started:
            # Non-comment line — end of block
            break
        else:
            # Non-comment, non-blank before any comment → no comment block
            break

    return "\n".join(comment_lines) if comment_lines else None


def _extract_powershell_comment_block(content: str) -> str | None:
    """Extract the first <# ... #> comment block from PowerShell content."""
    match = re.search(r"<#(.*?)#>", content, re.DOTALL)
    if match:
        return match.group(1)
    return None


def _parse_header_fields(
    header_text: str,
    filepath: Path,
    source: str,
    language: str,
) -> ScriptMeta:
    """Parse @script fields and @param declarations from header text."""
    # Derive ID from filename
    stem = filepath.stem
    script_id = stem

    # Detect numbering
    number: int | None = None
    is_permanent = False
    num_match = re.match(r"^(\d+)_", stem)
    if num_match:
        number = int(num_match.group(1))
        is_permanent = True

    # Parse @script fields
    fields: dict[str, str] = {}
    params: list[ScriptParameter] = []

    lines = header_text.splitlines()
    in_script_block = False

    for line in lines:
        stripped = line.strip()

        if stripped == "@script":
            in_script_block = True
            continue

        if stripped.startswith("@param"):
            param = _parse_param_line(stripped)
            if param:
                params.append(param)
            continue

        if in_script_block and ":" in stripped:
            key, _, value = stripped.partition(":")
            key = key.strip().lower()
            value = value.strip()
            if key and value:
                fields[key] = value

    # Build ScriptMeta
    tags = [t.strip() for t in fields.get("tags", "").split(",") if t.strip()]
    output_formats = [f.strip() for f in fields.get("output_formats", "").split(",") if f.strip()]

    return ScriptMeta(
        id=script_id,
        name=fields.get("name", stem),
        description=fields.get("description", ""),
        category=fields.get("category", "general"),
        tags=tags,
        language=language,
        mode=fields.get("mode", "fully_automated"),
        timeout=int(fields.get("timeout", "300")),
        parameters=params,
        default_output=fields.get("default_output", ""),
        output_formats=output_formats,
        source=source,
        override_target=fields.get("override", ""),
        dependencies=[d.strip() for d in fields.get("dependencies", "").split(",") if d.strip()],
        requires_tools=[t.strip() for t in fields.get("requires_tools", "").split(",") if t.strip()],
        number=number,
        is_permanent=is_permanent,
    )


def _parse_param_line(line: str) -> ScriptParameter | None:
    """Parse a @param line into a ScriptParameter.

    Format: @param name: type = default [choice1, choice2] | description

    Examples:
        @param output: path = docs/diagrams/ | Output directory for diagrams
        @param scope: string | Limit to specific package
        @param format: choice = mermaid [mermaid, json, markdown] | Output format
        @param dry-run: boolean = true | Show what would happen
    """
    # Strip @param prefix
    text = line[len("@param"):].strip()
    if not text:
        return None

    # Split description from the rest: everything after |
    description = ""
    if "|" in text:
        text, _, description = text.rpartition("|")
        description = description.strip()
        text = text.strip()

    # Split name from type/default: name: rest
    if ":" not in text:
        return ScriptParameter(name=text.strip(), description=description)

    name, _, rest = text.partition(":")
    name = name.strip()
    rest = rest.strip()

    # Parse type, default, choices from rest
    param_type = "string"
    default = ""
    choices: list[str] = []

    # Extract choices [choice1, choice2, ...]
    choices_match = re.search(r"\[([^\]]+)\]", rest)
    if choices_match:
        choices = [c.strip() for c in choices_match.group(1).split(",") if c.strip()]
        rest = rest[:choices_match.start()] + rest[choices_match.end():]
        rest = rest.strip()

    # Extract default value: type = default
    if "=" in rest:
        type_part, _, default_part = rest.partition("=")
        param_type = type_part.strip() or "string"
        default = default_part.strip()
    else:
        param_type = rest.strip() or "string"

    return ScriptParameter(
        name=name,
        type=param_type,
        description=description,
        required=not bool(default),
        default=default,
        choices=choices,
    )


# ── Query Functions ─────────────────────────────────────────────────


def get_all_scripts(project_root: Path) -> list[ScriptMeta]:
    """Return all discovered scripts (cached after first discovery)."""
    key = str(project_root.resolve())
    with _lock:
        if key in _registry_cache:
            return list(_registry_cache[key])

    # Discover outside the lock (I/O-heavy)
    scripts = discover_scripts(project_root)

    with _lock:
        _registry_cache[key] = scripts

    return list(scripts)


def get_script(project_root: Path, script_id: str) -> ScriptMeta | None:
    """Get a single script by ID."""
    for meta in get_all_scripts(project_root):
        if meta.id == script_id:
            return meta
    return None


def get_scripts_by_category(project_root: Path, category: str) -> list[ScriptMeta]:
    """Filter scripts by category."""
    return [m for m in get_all_scripts(project_root) if m.category == category]


def get_scripts_by_tag(project_root: Path, tag: str) -> list[ScriptMeta]:
    """Filter scripts by tag."""
    return [m for m in get_all_scripts(project_root) if tag in m.tags]


def refresh_registry(project_root: Path) -> list[ScriptMeta]:
    """Force re-discovery (invalidate cache)."""
    key = str(project_root.resolve())
    with _lock:
        _registry_cache.pop(key, None)
    return get_all_scripts(project_root)


def get_scripts_summary(project_root: Path) -> dict:
    """Return a summary dict for wizard/API consumption.

    Returns:
        {
            "total": int,
            "by_category": {"audit": 3, "generator": 1, ...},
            "by_source": {"root": 2, "template": 3, "override": 1},
            "scripts": [{"id": ..., "name": ..., "category": ...}, ...],
        }
    """
    scripts = get_all_scripts(project_root)

    by_category: dict[str, int] = {}
    by_source: dict[str, int] = {}
    script_list: list[dict] = []

    for meta in scripts:
        by_category[meta.category] = by_category.get(meta.category, 0) + 1
        by_source[meta.source] = by_source.get(meta.source, 0) + 1
        script_list.append({
            "id": meta.id,
            "name": meta.name,
            "category": meta.category,
            "source": meta.source,
            "language": meta.language,
        })

    return {
        "total": len(scripts),
        "by_category": by_category,
        "by_source": by_source,
        "scripts": script_list,
    }
