"""
Outline extraction — strategy-based structural analysis of content files.

Extracts headings (markdown), classes/functions (Python), or other structural
elements from files and returns a uniform tree of outline nodes.  Each node::

    {"text": str, "kind": str, "line": int, "children": list[dict]}

Sub-modules and callers work exclusively with this shape.

Strategies
----------
- MarkdownOutlineStrategy      — regex heading extraction (h1–h6), nested by level
- PythonOutlineStrategy        — ast.parse() for classes, functions, methods, constants
- JavaScriptOutlineStrategy    — regex: classes, functions, arrow fns, methods
- GoOutlineStrategy            — regex: func, method, type struct/interface
- RustOutlineStrategy          — regex: fn, struct, enum, trait, impl
- HtmlOutlineStrategy          — regex: h1–h6 headings, sections with id
- CssOutlineStrategy           — regex: section comments, @media, @keyframes, @mixin
- YamlOutlineStrategy          — regex: top-level keys, section comments
- JsonOutlineStrategy          — json.loads() for top-level keys
- TomlOutlineStrategy          — regex: [table] and [[array-table]] headers
- ShellOutlineStrategy         — regex: function defs, section comments
- SqlOutlineStrategy           — regex: CREATE TABLE/VIEW/FUNCTION/PROCEDURE/INDEX
- EncryptedOutlineStrategy     — stub: returns ``encrypted: true``, no extraction
- FallbackOutlineStrategy      — returns empty outline (file shown as leaf)

Public API
----------
- ``extract_outline(file_path, content=None)``    — single file
- ``extract_folder_glossary(folder, project_root)`` — folder tree with outlines
"""

from __future__ import annotations

import ast
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .crypto import classify_file

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Outline node helpers
# ═══════════════════════════════════════════════════════════════════════

def _node(text: str, kind: str, line: int,
          children: list[dict] | None = None, **extra: Any) -> dict:
    """Build a single outline node in the canonical shape."""
    n: dict[str, Any] = {
        "text": text,
        "kind": kind,
        "line": line,
        "children": children or [],
    }
    n.update(extra)
    return n


# ═══════════════════════════════════════════════════════════════════════
# Strategy interface
# ═══════════════════════════════════════════════════════════════════════

class OutlineStrategy:
    """Base class for outline extraction strategies.

    Subclasses must set ``extensions`` and implement ``extract()``.
    """

    extensions: set[str] = set()

    def extract(self, source: str, file_path: str) -> list[dict]:
        """Extract outline nodes from *source* text.

        Args:
            source: Full file content as a string.
            file_path: Original file path (for diagnostics only).

        Returns:
            List of outline node dicts.
        """
        raise NotImplementedError


# ═══════════════════════════════════════════════════════════════════════
# Markdown strategy — heading extraction
# ═══════════════════════════════════════════════════════════════════════

_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_MD_FENCE_OPEN = re.compile(r"^(`{3,}|~{3,})")
_MD_FENCE_CLOSE_CACHE: dict[str, re.Pattern[str]] = {}


def _md_fence_close_re(fence_char: str, fence_len: int) -> re.Pattern[str]:
    """Return a compiled regex that matches the closing fence."""
    key = f"{fence_char}:{fence_len}"
    if key not in _MD_FENCE_CLOSE_CACHE:
        _MD_FENCE_CLOSE_CACHE[key] = re.compile(
            rf"^{re.escape(fence_char)}{{{fence_len},}}\s*$"
        )
    return _MD_FENCE_CLOSE_CACHE[key]


class MarkdownOutlineStrategy(OutlineStrategy):
    """Extract headings from Markdown files, nested by level.

    Skips headings inside fenced code blocks (``` or ~~~).
    """

    extensions = {".md", ".mdx", ".markdown", ".rst"}

    def extract(self, source: str, file_path: str) -> list[dict]:
        """Return a nested list of heading nodes."""
        lines = source.split("\n")
        flat: list[dict] = []  # (level, node) pairs collected linearly
        in_fence = False
        fence_close_re: re.Pattern[str] | None = None

        for lineno_0, line in enumerate(lines):
            lineno = lineno_0 + 1  # 1-indexed

            # ── Track fenced code blocks ──
            if not in_fence:
                fm = _MD_FENCE_OPEN.match(line)
                if fm:
                    fence_str = fm.group(1)
                    fence_close_re = _md_fence_close_re(
                        fence_str[0], len(fence_str)
                    )
                    in_fence = True
                    continue
            else:
                if fence_close_re and fence_close_re.match(line):
                    in_fence = False
                    fence_close_re = None
                continue  # skip everything inside fence

            # ── Match headings ──
            hm = _MD_HEADING_RE.match(line)
            if hm:
                level = len(hm.group(1))
                text = hm.group(2).strip()
                flat.append({"level": level, "node": _node(
                    text=text,
                    kind="heading",
                    line=lineno,
                    level=level,
                )})

        # ── Nest flat list by heading level ──
        return _nest_by_level(flat)


def _nest_by_level(flat: list[dict]) -> list[dict]:
    """Convert a flat list of ``{level, node}`` dicts into a nested tree.

    Each heading becomes a child of the nearest preceding heading with a
    lower level.  If no parent exists, it becomes a root node.
    """
    root: list[dict] = []
    # Stack: list of (level, node_ref) — tracks the nesting path
    stack: list[tuple[int, dict]] = []

    for item in flat:
        level = item["level"]
        node = item["node"]

        # Pop until we find a parent with strictly lower level
        while stack and stack[-1][0] >= level:
            stack.pop()

        if stack:
            # Append as child of the top of stack
            stack[-1][1]["children"].append(node)
        else:
            # No parent — top-level heading
            root.append(node)

        stack.append((level, node))

    return root


# ═══════════════════════════════════════════════════════════════════════
# Python strategy — AST-based extraction
# ═══════════════════════════════════════════════════════════════════════

class PythonOutlineStrategy(OutlineStrategy):
    """Extract classes, functions, methods, and top-level constants from Python.

    Uses ``ast.parse()`` for precise, reliable extraction.  Handles syntax
    errors gracefully by returning an empty outline (not raising).
    """

    extensions = {".py", ".pyw"}

    def extract(self, source: str, file_path: str) -> list[dict]:
        """Return outline nodes for Python source."""
        try:
            tree = ast.parse(source, filename=file_path)
        except SyntaxError as exc:
            logger.debug("Python parse error in %s: %s", file_path, exc)
            return []

        outline: list[dict] = []

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                methods: list[dict] = []
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        methods.append(_node(
                            text=child.name,
                            kind="method",
                            line=child.lineno,
                        ))
                outline.append(_node(
                    text=node.name,
                    kind="class",
                    line=node.lineno,
                    children=methods,
                ))

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                outline.append(_node(
                    text=node.name,
                    kind="function",
                    line=node.lineno,
                ))

            elif isinstance(node, ast.Assign):
                # Top-level constants: names that are ALL_CAPS
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        outline.append(_node(
                            text=target.id,
                            kind="constant",
                            line=node.lineno,
                        ))

        return outline


# ═══════════════════════════════════════════════════════════════════════
# Encrypted strategy — stub for .enc files
# ═══════════════════════════════════════════════════════════════════════

class EncryptedOutlineStrategy(OutlineStrategy):
    """Encrypted files cannot be parsed without the key.

    Returns no outline, but flags the file as encrypted so the UI can
    show a lock icon.
    """

    extensions = {".enc"}

    def extract(self, source: str, file_path: str) -> list[dict]:
        """Always returns empty — encrypted content is opaque."""
        return []


# ═══════════════════════════════════════════════════════════════════════
# JavaScript / TypeScript strategy — regex-based
# ═══════════════════════════════════════════════════════════════════════

_JS_CLASS = re.compile(
    r"^(?:export\s+(?:default\s+)?)?class\s+(\w+)"
)
_JS_FUNC = re.compile(
    r"^(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+(\w+)"
)
_JS_ARROW = re.compile(
    r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*="
    r"\s*(?:async\s+)?(?:\(|function)"
)
_JS_METHOD = re.compile(r"^\s+(?:async\s+)?(\w+)\s*\(")
_JS_BLOCK_OPEN = re.compile(r"/\*")
_JS_BLOCK_CLOSE = re.compile(r"\*/")


class JavaScriptOutlineStrategy(OutlineStrategy):
    """Extract classes, functions, and arrow-function constants from JS/TS.

    Methods inside classes are detected by indentation heuristic:
    after a ``class`` line, indented lines matching ``name(`` become children.
    The method list resets on the next top-level definition or brace-depth exit.

    TypeScript generics (``class Foo<T>``) are stripped from the captured name.
    Decorator lines (``@decorator``) and ``/* ... */`` block comments are skipped.
    """

    extensions = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}

    def extract(self, source: str, file_path: str) -> list[dict]:
        lines = source.split("\n")
        outline: list[dict] = []
        current_class: dict | None = None
        in_block_comment = False

        for lineno_0, line in enumerate(lines):
            lineno = lineno_0 + 1

            # Track block comments
            if in_block_comment:
                if _JS_BLOCK_CLOSE.search(line):
                    in_block_comment = False
                continue
            if _JS_BLOCK_OPEN.search(line) and not _JS_BLOCK_CLOSE.search(line):
                in_block_comment = True
                continue

            stripped = line.lstrip()
            if not stripped or stripped.startswith("//") or stripped.startswith("@"):
                continue

            # Class
            m = _JS_CLASS.match(line)
            if m:
                name = m.group(1).split("<")[0]  # strip generics
                current_class = _node(text=name, kind="class", line=lineno)
                outline.append(current_class)
                continue

            # Top-level function
            m = _JS_FUNC.match(line)
            if m:
                current_class = None
                outline.append(_node(text=m.group(1), kind="function", line=lineno))
                continue

            # Arrow function / const assignment
            m = _JS_ARROW.match(line)
            if m:
                current_class = None
                outline.append(_node(text=m.group(1), kind="function", line=lineno))
                continue

            # Method inside class (indented, no keyword prefix)
            if current_class and line[0] in (" ", "\t") and stripped[0] != "}":
                m = _JS_METHOD.match(line)
                if m:
                    name = m.group(1)
                    if name not in ("if", "for", "while", "switch", "catch", "return"):
                        current_class["children"].append(
                            _node(text=name, kind="method", line=lineno)
                        )
                        continue

            # Closing brace at column 0 → end of class
            if current_class and stripped == "}":
                if not line[0].isspace():
                    current_class = None

        return outline


# ═══════════════════════════════════════════════════════════════════════
# Go strategy — regex-based
# ═══════════════════════════════════════════════════════════════════════

_GO_FUNC = re.compile(r"^func\s+(\w+)\s*\(")
_GO_METHOD = re.compile(r"^func\s+\(\w+\s+\*?(\w+)\)\s+(\w+)\s*\(")
_GO_TYPE_STRUCT = re.compile(r"^type\s+(\w+)\s+struct\b")
_GO_TYPE_IFACE = re.compile(r"^type\s+(\w+)\s+interface\b")
_GO_TYPE_ALIAS = re.compile(r"^type\s+(\w+)\s+")


class GoOutlineStrategy(OutlineStrategy):
    """Extract functions, methods, and type declarations from Go source.

    Methods are grouped under their receiver type by collecting orphan methods
    in a second pass and attaching them to the matching struct/interface node.
    """

    extensions = {".go"}

    def extract(self, source: str, file_path: str) -> list[dict]:
        lines = source.split("\n")
        outline: list[dict] = []
        types: dict[str, dict] = {}  # receiver_name -> type node
        orphan_methods: list[tuple[str, dict]] = []  # (receiver, method_node)

        for lineno_0, line in enumerate(lines):
            lineno = lineno_0 + 1

            # Method (func (r *Type) Name(...))
            m = _GO_METHOD.match(line)
            if m:
                receiver = m.group(1)
                method_node = _node(text=m.group(2), kind="method", line=lineno)
                orphan_methods.append((receiver, method_node))
                continue

            # Function (func Name(...))
            m = _GO_FUNC.match(line)
            if m:
                outline.append(_node(text=m.group(1), kind="function", line=lineno))
                continue

            # Type struct
            m = _GO_TYPE_STRUCT.match(line)
            if m:
                name = m.group(1)
                n = _node(text=name, kind="class", line=lineno)
                types[name] = n
                outline.append(n)
                continue

            # Type interface
            m = _GO_TYPE_IFACE.match(line)
            if m:
                name = m.group(1)
                n = _node(text=name, kind="class", line=lineno)
                types[name] = n
                outline.append(n)
                continue

            # Other type aliases (type Foo = ..., type Foo int)
            m = _GO_TYPE_ALIAS.match(line)
            if m:
                name = m.group(1)
                if name not in types:  # Don't duplicate struct/interface
                    outline.append(
                        _node(text=name, kind="constant", line=lineno)
                    )

        # Attach orphan methods to their receiver types
        for receiver, method_node in orphan_methods:
            if receiver in types:
                types[receiver]["children"].append(method_node)
            else:
                # Receiver type not in this file — show as top-level
                outline.append(method_node)

        return outline


# ═══════════════════════════════════════════════════════════════════════
# Rust strategy — regex-based
# ═══════════════════════════════════════════════════════════════════════

_RS_FN = re.compile(r"^(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+(\w+)")
_RS_STRUCT = re.compile(r"^(?:pub(?:\([^)]*\))?\s+)?struct\s+(\w+)")
_RS_ENUM = re.compile(r"^(?:pub(?:\([^)]*\))?\s+)?enum\s+(\w+)")
_RS_TRAIT = re.compile(r"^(?:pub(?:\([^)]*\))?\s+)?trait\s+(\w+)")
_RS_IMPL = re.compile(r"^impl(?:\s*<[^>]*>)?\s+(\w+)")
_RS_IMPL_FOR = re.compile(r"^impl(?:\s*<[^>]*>)?\s+\w+\s+for\s+(\w+)")


class RustOutlineStrategy(OutlineStrategy):
    """Extract functions, structs, enums, traits, and impl blocks from Rust.

    Functions inside ``impl`` blocks are detected by indentation heuristic.
    """

    extensions = {".rs"}

    def extract(self, source: str, file_path: str) -> list[dict]:
        lines = source.split("\n")
        outline: list[dict] = []
        current_impl: dict | None = None

        for lineno_0, line in enumerate(lines):
            lineno = lineno_0 + 1
            stripped = line.lstrip()
            if not stripped or stripped.startswith("//"):
                continue

            # impl Trait for Type  or  impl Type
            m = _RS_IMPL_FOR.match(line)
            if m:
                name = f"impl … for {m.group(1)}"
                current_impl = _node(text=name, kind="class", line=lineno)
                outline.append(current_impl)
                continue
            m = _RS_IMPL.match(line)
            if m and not stripped.startswith("impl ") or (
                stripped.startswith("impl ") and "{" in line
            ):
                # Only top-level impl (column 0)
                if not line[0].isspace():
                    name = f"impl {m.group(1)}"
                    current_impl = _node(text=name, kind="class", line=lineno)
                    outline.append(current_impl)
                    continue

            # Struct
            m = _RS_STRUCT.match(line)
            if m and not line[0].isspace():
                current_impl = None
                outline.append(_node(text=m.group(1), kind="class", line=lineno))
                continue

            # Enum
            m = _RS_ENUM.match(line)
            if m and not line[0].isspace():
                current_impl = None
                outline.append(_node(text=m.group(1), kind="class", line=lineno))
                continue

            # Trait
            m = _RS_TRAIT.match(line)
            if m and not line[0].isspace():
                current_impl = None
                outline.append(_node(text=m.group(1), kind="class", line=lineno))
                continue

            # Function
            m = _RS_FN.match(line)
            if m:
                fn_node = _node(text=m.group(1), kind="function", line=lineno)
                if current_impl and line[0].isspace():
                    current_impl["children"].append(fn_node)
                else:
                    current_impl = None
                    outline.append(fn_node)
                continue

            # Closing brace at column 0 → end of impl block
            if current_impl and stripped == "}" and not line[0].isspace():
                current_impl = None

        return outline


# ═══════════════════════════════════════════════════════════════════════
# HTML strategy — heading and section extraction
# ═══════════════════════════════════════════════════════════════════════

_HTML_HEADING = re.compile(
    r"<h([1-6])[^>]*>(.*?)</h\1>", re.IGNORECASE
)
_HTML_SECTION_ID = re.compile(
    r"<section[^>]*id=[\"']([^\"']+)[\"']", re.IGNORECASE
)


class HtmlOutlineStrategy(OutlineStrategy):
    """Extract headings and named sections from HTML files.

    Headings are nested by level (h1 > h2 > h3) using the same
    ``_nest_by_level`` helper as the Markdown strategy.
    """

    extensions = {".html", ".htm"}

    def extract(self, source: str, file_path: str) -> list[dict]:
        lines = source.split("\n")
        flat: list[dict] = []

        for lineno_0, line in enumerate(lines):
            lineno = lineno_0 + 1

            # Headings
            for m in _HTML_HEADING.finditer(line):
                level = int(m.group(1))
                # Strip HTML tags from heading text
                text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
                if text:
                    flat.append({"level": level, "node": _node(
                        text=text, kind="heading", line=lineno, level=level,
                    )})

            # Named sections
            m = _HTML_SECTION_ID.search(line)
            if m:
                flat.append({"level": 2, "node": _node(
                    text=m.group(1), kind="section", line=lineno, level=2,
                )})

        return _nest_by_level(flat)


# ═══════════════════════════════════════════════════════════════════════
# CSS / SCSS / LESS strategy — section and at-rule extraction
# ═══════════════════════════════════════════════════════════════════════

_CSS_SECTION = re.compile(r"/\*\s*[═─=─]{2,}\s*(.+?)\s*[═─=─]{2,}\s*\*/")
_CSS_MEDIA = re.compile(r"^@media\s+(.+)\s*\{")
_CSS_KEYFRAMES = re.compile(r"^@keyframes\s+(\w+)")
_CSS_MIXIN = re.compile(r"^@mixin\s+([\w-]+)")


class CssOutlineStrategy(OutlineStrategy):
    """Extract section comments and CSS at-rules.

    Recognises section-separator comments in the form
    ``/* ═══ Section Name ═══ */`` and prominent at-rules like
    ``@media``, ``@keyframes``, ``@mixin``.
    """

    extensions = {".css", ".scss", ".less", ".sass"}

    def extract(self, source: str, file_path: str) -> list[dict]:
        lines = source.split("\n")
        outline: list[dict] = []

        for lineno_0, line in enumerate(lines):
            lineno = lineno_0 + 1

            m = _CSS_SECTION.search(line)
            if m:
                outline.append(_node(text=m.group(1).strip(), kind="section", line=lineno))
                continue

            m = _CSS_MEDIA.match(line)
            if m:
                outline.append(_node(text=f"@media {m.group(1).strip()}", kind="media", line=lineno))
                continue

            m = _CSS_KEYFRAMES.match(line)
            if m:
                outline.append(_node(text=m.group(1), kind="animation", line=lineno))
                continue

            m = _CSS_MIXIN.match(line)
            if m:
                outline.append(_node(text=m.group(1), kind="function", line=lineno))

        return outline


# ═══════════════════════════════════════════════════════════════════════
# YAML strategy — top-level keys and section comments
# ═══════════════════════════════════════════════════════════════════════

_YAML_KEY = re.compile(r"^(\w[\w_-]*)\s*:")
_YAML_SECTION_COMMENT = re.compile(r"^#\s*[═─=]{2,}\s*(.+?)\s*[═─=]{2,}")


class YamlOutlineStrategy(OutlineStrategy):
    """Extract top-level keys and section-separator comments from YAML.

    Only keys at column 0 (no leading whitespace) are extracted to avoid
    noise from deeply-nested structures.
    """

    extensions = {".yaml", ".yml"}

    def extract(self, source: str, file_path: str) -> list[dict]:
        lines = source.split("\n")
        outline: list[dict] = []

        for lineno_0, line in enumerate(lines):
            lineno = lineno_0 + 1
            if not line or line[0] == " " or line[0] == "\t":
                continue

            m = _YAML_SECTION_COMMENT.match(line)
            if m:
                outline.append(_node(text=m.group(1).strip(), kind="section", line=lineno))
                continue

            m = _YAML_KEY.match(line)
            if m:
                outline.append(_node(text=m.group(1), kind="section", line=lineno))

        return outline


# ═══════════════════════════════════════════════════════════════════════
# JSON strategy — top-level object keys
# ═══════════════════════════════════════════════════════════════════════

_JSON_KEY_RE = re.compile(r'^\s*"([^"]+)"\s*:')


class JsonOutlineStrategy(OutlineStrategy):
    """Extract top-level keys from JSON objects.

    Uses ``json.loads()`` to get key names, then scans the source to find
    line numbers for each key.  Arrays or unparseable JSON yield empty outlines.
    """

    extensions = {".json"}

    def extract(self, source: str, file_path: str) -> list[dict]:
        try:
            data = json.loads(source)
        except (json.JSONDecodeError, ValueError):
            return []
        if not isinstance(data, dict):
            return []

        outline: list[dict] = []
        # Find line numbers by scanning source
        lines = source.split("\n")
        found_keys: set[str] = set()
        for key in data:
            line_num = self._find_key_line(lines, key, found_keys)
            outline.append(_node(text=key, kind="section", line=line_num))
            found_keys.add(key)
        return outline

    @staticmethod
    def _find_key_line(lines: list[str], key: str,
                       found: set[str]) -> int:
        """Find the first line containing ``"key":`` that hasn't been claimed."""
        target = f'"{ key}"'
        for i, line in enumerate(lines):
            if target in line:
                # Rudimentary check: make sure it looks like a key position
                m = _JSON_KEY_RE.match(line)
                if m and m.group(1) == key and key not in found:
                    return i + 1
        return 1  # fallback


# ═══════════════════════════════════════════════════════════════════════
# TOML strategy — table headers
# ═══════════════════════════════════════════════════════════════════════

_TOML_ARRAY_TABLE = re.compile(r"^\[\[([^\]]+)\]\]")
_TOML_TABLE = re.compile(r"^\[([^\]]+)\]")


class TomlOutlineStrategy(OutlineStrategy):
    """Extract ``[table]`` and ``[[array-table]]`` headers from TOML."""

    extensions = {".toml"}

    def extract(self, source: str, file_path: str) -> list[dict]:
        lines = source.split("\n")
        outline: list[dict] = []

        for lineno_0, line in enumerate(lines):
            lineno = lineno_0 + 1

            m = _TOML_ARRAY_TABLE.match(line)
            if m:
                outline.append(_node(text=f"[[{m.group(1)}]]", kind="section", line=lineno))
                continue

            m = _TOML_TABLE.match(line)
            if m:
                outline.append(_node(text=f"[{m.group(1)}]", kind="section", line=lineno))

        return outline


# ═══════════════════════════════════════════════════════════════════════
# Shell / Bash strategy — function defs and section comments
# ═══════════════════════════════════════════════════════════════════════

_SH_FUNC_KW = re.compile(r"^function\s+(\w+)")
_SH_FUNC_PAREN = re.compile(r"^(\w+)\s*\(\s*\)")
_SH_SECTION = re.compile(r"^#\s*[═─=]{2,}\s*(.+?)\s*[═─=]{2,}")


class ShellOutlineStrategy(OutlineStrategy):
    """Extract function definitions and section comments from shell scripts.

    Supports both ``function name`` and ``name()`` syntax.
    """

    extensions = {".sh", ".bash", ".zsh", ".fish"}

    def extract(self, source: str, file_path: str) -> list[dict]:
        lines = source.split("\n")
        outline: list[dict] = []

        for lineno_0, line in enumerate(lines):
            lineno = lineno_0 + 1
            stripped = line.strip()
            if not stripped:
                continue

            m = _SH_SECTION.match(line)
            if m:
                outline.append(_node(text=m.group(1).strip(), kind="section", line=lineno))
                continue

            m = _SH_FUNC_KW.match(line)
            if m:
                outline.append(_node(text=m.group(1), kind="function", line=lineno))
                continue

            m = _SH_FUNC_PAREN.match(line)
            if m:
                name = m.group(1)
                # Exclude common shell keywords that look like functions
                if name not in ("if", "for", "while", "until", "case", "do",
                                "then", "else", "elif", "fi", "done", "esac"):
                    outline.append(_node(text=name, kind="function", line=lineno))

        return outline


# ═══════════════════════════════════════════════════════════════════════
# SQL strategy — DDL statement extraction
# ═══════════════════════════════════════════════════════════════════════

_SQL_TABLE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)", re.IGNORECASE
)
_SQL_VIEW = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(\w+)", re.IGNORECASE
)
_SQL_FUNC = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(\w+)", re.IGNORECASE
)
_SQL_PROC = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?PROCEDURE\s+(\w+)", re.IGNORECASE
)
_SQL_INDEX = re.compile(
    r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(\w+)", re.IGNORECASE
)


class SqlOutlineStrategy(OutlineStrategy):
    """Extract DDL statements (CREATE TABLE, VIEW, FUNCTION, etc.) from SQL."""

    extensions = {".sql"}

    def extract(self, source: str, file_path: str) -> list[dict]:
        lines = source.split("\n")
        outline: list[dict] = []

        for lineno_0, line in enumerate(lines):
            lineno = lineno_0 + 1

            m = _SQL_TABLE.search(line)
            if m:
                outline.append(_node(text=m.group(1), kind="class", line=lineno))
                continue

            m = _SQL_VIEW.search(line)
            if m:
                outline.append(_node(text=m.group(1), kind="class", line=lineno))
                continue

            m = _SQL_FUNC.search(line)
            if m:
                outline.append(_node(text=m.group(1), kind="function", line=lineno))
                continue

            m = _SQL_PROC.search(line)
            if m:
                outline.append(_node(text=m.group(1), kind="function", line=lineno))
                continue

            m = _SQL_INDEX.search(line)
            if m:
                outline.append(_node(text=m.group(1), kind="constant", line=lineno))

        return outline


# ═══════════════════════════════════════════════════════════════════════
# Fallback strategy — no extraction
# ═══════════════════════════════════════════════════════════════════════

class FallbackOutlineStrategy(OutlineStrategy):
    """Default strategy for file types without a dedicated extractor.

    Returns an empty outline — the file is listed as a leaf node in the
    glossary tree but has no internal structure to display.
    """

    extensions = set()  # Catch-all — not registered by extension

    def extract(self, source: str, file_path: str) -> list[dict]:
        """Return empty outline."""
        return []


# ═══════════════════════════════════════════════════════════════════════
# Strategy registry + dispatcher
# ═══════════════════════════════════════════════════════════════════════

_STRATEGIES: dict[str, OutlineStrategy] = {}
_FALLBACK = FallbackOutlineStrategy()


def _register_strategy(strategy: OutlineStrategy) -> None:
    """Register a strategy for all its declared extensions."""
    for ext in strategy.extensions:
        _STRATEGIES[ext] = strategy


# Register built-in strategies
_register_strategy(MarkdownOutlineStrategy())
_register_strategy(PythonOutlineStrategy())
_register_strategy(JavaScriptOutlineStrategy())
_register_strategy(GoOutlineStrategy())
_register_strategy(RustOutlineStrategy())
_register_strategy(HtmlOutlineStrategy())
_register_strategy(CssOutlineStrategy())
_register_strategy(YamlOutlineStrategy())
_register_strategy(JsonOutlineStrategy())
_register_strategy(TomlOutlineStrategy())
_register_strategy(ShellOutlineStrategy())
_register_strategy(SqlOutlineStrategy())
_register_strategy(EncryptedOutlineStrategy())


def _get_strategy(file_path: Path) -> OutlineStrategy:
    """Look up the strategy for a file path by extension.

    For ``.enc`` files, checks the inner extension first so that
    ``foo.md.enc`` uses EncryptedOutlineStrategy (not Markdown).
    """
    suffix = file_path.suffix.lower()

    # .enc always → EncryptedOutlineStrategy
    if suffix == ".enc":
        return _STRATEGIES.get(".enc", _FALLBACK)

    return _STRATEGIES.get(suffix, _FALLBACK)


# ═══════════════════════════════════════════════════════════════════════
# Cache — mtime-based invalidation
# ═══════════════════════════════════════════════════════════════════════

_OUTLINE_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_MAX_SIZE = 500  # max entries

_GLOSSARY_CACHE: dict[str, tuple[float, dict]] = {}
_GLOSSARY_CACHE_MAX_SIZE = 50


def _cache_get(cache: dict[str, tuple[float, dict]],
               key: str, mtime: float) -> dict | None:
    """Return cached value if mtime matches, else None."""
    entry = cache.get(key)
    if entry and entry[0] == mtime:
        return entry[1]
    return None


def _cache_put(cache: dict[str, tuple[float, dict]],
               key: str, mtime: float, value: dict,
               max_size: int) -> None:
    """Store a value in the cache, evicting oldest if full."""
    if len(cache) >= max_size:
        # Evict oldest entry (by insertion order — Python 3.7+ dicts)
        oldest_key = next(iter(cache))
        del cache[oldest_key]
    cache[key] = (mtime, value)


# ═══════════════════════════════════════════════════════════════════════
# Performance guards
# ═══════════════════════════════════════════════════════════════════════

MAX_FILE_SIZE_BYTES = 512 * 1024      # 512 KB — skip outline for larger files
MAX_FILES_PER_GLOSSARY = 200          # max files processed per glossary request
MAX_WORKERS = 4                       # thread pool size for parallel extraction


# ═══════════════════════════════════════════════════════════════════════
# Public API — single file outline
# ═══════════════════════════════════════════════════════════════════════

def extract_outline(file_path: Path,
                    content: str | None = None) -> dict:
    """Extract the structural outline from a single file.

    Args:
        file_path: Absolute path to the file.
        content:   Optional pre-loaded content (avoids re-reading the file).

    Returns:
        Dict with keys: ``path``, ``type``, ``line_count``, ``size_bytes``,
        ``encrypted``, ``outline``.
    """
    path_str = str(file_path)
    suffix = file_path.suffix.lower()
    is_encrypted = suffix == ".enc"

    # ── File metadata ──
    try:
        stat = file_path.stat()
        size_bytes = stat.st_size
        mtime = stat.st_mtime
    except OSError:
        return {
            "path": path_str,
            "type": "unknown",
            "line_count": None,
            "size_bytes": 0,
            "encrypted": is_encrypted,
            "outline": [],
        }

    # ── Cache check ──
    cached = _cache_get(_OUTLINE_CACHE, path_str, mtime)
    if cached is not None:
        return cached

    # ── Encrypted files — no extraction ──
    if is_encrypted:
        inner_name = Path(file_path.stem).name  # e.g. "secrets.md" from "secrets.md.enc"
        result: dict[str, Any] = {
            "path": path_str,
            "type": "encrypted",
            "line_count": None,
            "size_bytes": size_bytes,
            "encrypted": True,
            "original_name": inner_name,
            "outline": [],
        }
        _cache_put(_OUTLINE_CACHE, path_str, mtime, result, _CACHE_MAX_SIZE)
        return result

    # ── Size guard ──
    if size_bytes > MAX_FILE_SIZE_BYTES:
        file_type = classify_file(file_path)
        result = {
            "path": path_str,
            "type": file_type,
            "line_count": None,
            "size_bytes": size_bytes,
            "encrypted": False,
            "outline": [],
            "skipped": "file_too_large",
        }
        _cache_put(_OUTLINE_CACHE, path_str, mtime, result, _CACHE_MAX_SIZE)
        return result

    # ── Read content if not provided ──
    if content is None:
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("Cannot read %s for outline: %s", path_str, exc)
            return {
                "path": path_str,
                "type": "unknown",
                "line_count": None,
                "size_bytes": size_bytes,
                "encrypted": False,
                "outline": [],
            }

    line_count = content.count("\n") + (1 if content and not content.endswith("\n") else 0)

    # ── Dispatch to strategy ──
    strategy = _get_strategy(file_path)
    file_type = classify_file(file_path)

    try:
        outline = strategy.extract(content, path_str)
    except Exception as exc:
        logger.warning("Outline extraction failed for %s: %s", path_str, exc)
        outline = []

    result = {
        "path": path_str,
        "type": file_type,
        "line_count": line_count,
        "size_bytes": size_bytes,
        "encrypted": False,
        "outline": outline,
    }
    _cache_put(_OUTLINE_CACHE, path_str, mtime, result, _CACHE_MAX_SIZE)
    return result


# ═══════════════════════════════════════════════════════════════════════
# Public API — folder glossary (tree with outlines)
# ═══════════════════════════════════════════════════════════════════════

def extract_folder_glossary(folder: Path,
                            project_root: Path,
                            recursive: bool = True) -> dict:
    """Build a glossary tree for all files in *folder*.

    Each file entry includes its outline.  Directories are represented as
    nested nodes with ``is_dir: True`` and a ``children`` list.

    Args:
        folder:       Absolute path to the folder to scan.
        project_root: Project root for relative path computation.
        recursive:    If True, descend into subdirectories.

    Returns:
        Dict with keys: ``path``, ``total_files``, ``entries``.
    """
    rel_folder = str(folder.relative_to(project_root))

    # ── Cache check (use max mtime of folder tree) ──
    try:
        folder_mtime = _get_folder_mtime(folder, recursive)
    except OSError:
        folder_mtime = 0.0

    cache_key = f"{rel_folder}:recursive={recursive}"
    cached = _cache_get(_GLOSSARY_CACHE, cache_key, folder_mtime)
    if cached is not None:
        return cached

    # ── Collect files ──
    files: list[Path] = []
    if recursive:
        _collect_files_recursive(folder, files, MAX_FILES_PER_GLOSSARY)
    else:
        try:
            for child in sorted(folder.iterdir()):
                if child.is_file() and not child.name.startswith("."):
                    files.append(child)
                    if len(files) >= MAX_FILES_PER_GLOSSARY:
                        break
        except OSError:
            pass

    # ── Extract outlines in parallel ──
    outlines: dict[str, dict] = {}  # path_str -> outline result
    t0 = time.monotonic()

    if len(files) <= 5:
        # Small folder — extract sequentially (no thread overhead)
        for f in files:
            outlines[str(f)] = extract_outline(f)
    else:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(extract_outline, f): f for f in files}
            for future in as_completed(futures):
                f = futures[future]
                try:
                    outlines[str(f)] = future.result()
                except Exception as exc:
                    logger.warning("Outline failed for %s: %s", f, exc)
                    outlines[str(f)] = {
                        "path": str(f),
                        "type": "unknown",
                        "line_count": None,
                        "size_bytes": 0,
                        "encrypted": False,
                        "outline": [],
                    }

    elapsed_ms = (time.monotonic() - t0) * 1000
    logger.debug(
        "Glossary for %s: %d files in %.1fms",
        rel_folder, len(files), elapsed_ms,
    )

    # ── Build nested tree ──
    entries = _build_glossary_tree(folder, project_root, outlines, recursive)
    total_files = len(files)

    result = {
        "path": rel_folder,
        "total_files": total_files,
        "entries": entries,
    }
    _cache_put(
        _GLOSSARY_CACHE, cache_key, folder_mtime,
        result, _GLOSSARY_CACHE_MAX_SIZE,
    )
    return result


def _collect_files_recursive(folder: Path, files: list[Path],
                             limit: int) -> None:
    """Walk *folder* recursively, collecting files up to *limit*."""
    try:
        children = sorted(folder.iterdir())
    except OSError:
        return

    for child in children:
        if len(files) >= limit:
            return
        if child.name.startswith("."):
            continue
        if child.name == "__pycache__":
            continue
        if child.is_file():
            files.append(child)
        elif child.is_dir():
            _collect_files_recursive(child, files, limit)


def _get_folder_mtime(folder: Path, recursive: bool) -> float:
    """Return the max mtime across all files in *folder*.

    Used as a cache invalidation key — if any file changed, the glossary
    is regenerated.
    """
    max_mtime = folder.stat().st_mtime

    try:
        for child in folder.iterdir():
            if child.name.startswith(".") or child.name == "__pycache__":
                continue
            if child.is_file():
                max_mtime = max(max_mtime, child.stat().st_mtime)
            elif recursive and child.is_dir():
                max_mtime = max(max_mtime, _get_folder_mtime(child, True))
    except OSError:
        pass

    return max_mtime


def _build_glossary_tree(folder: Path, project_root: Path,
                         outlines: dict[str, dict],
                         recursive: bool) -> list[dict]:
    """Build a nested entry list mirroring the folder's directory structure.

    Files get their outline data attached.  Directories become nodes with
    ``is_dir: True`` and ``children``.
    """
    entries: list[dict] = []

    try:
        children = sorted(folder.iterdir())
    except OSError:
        return entries

    for child in children:
        if child.name.startswith(".") or child.name == "__pycache__":
            continue

        rel_path = str(child.relative_to(project_root))

        if child.is_file():
            outline_data = outlines.get(str(child), {})
            entry: dict[str, Any] = {
                "name": child.name,
                "path": rel_path,
                "is_dir": False,
                "type": outline_data.get("type", classify_file(child)),
                "size_bytes": outline_data.get("size_bytes", 0),
                "line_count": outline_data.get("line_count"),
                "encrypted": outline_data.get("encrypted", False),
                "outline": outline_data.get("outline", []),
            }
            # Add original_name for encrypted files
            if outline_data.get("original_name"):
                entry["original_name"] = outline_data["original_name"]
            # Add skipped reason if applicable
            if outline_data.get("skipped"):
                entry["skipped"] = outline_data["skipped"]
            entries.append(entry)

        elif child.is_dir() and recursive:
            # Recurse into subdirectory
            sub_entries = _build_glossary_tree(
                child, project_root, outlines, recursive,
            )
            if sub_entries:  # Only include non-empty directories
                entries.append({
                    "name": child.name,
                    "path": rel_path,
                    "is_dir": True,
                    "children": sub_entries,
                })
            else:
                # Empty dir with no scannable files — still show as leaf dir
                entries.append({
                    "name": child.name,
                    "path": rel_path,
                    "is_dir": True,
                    "children": [],
                })

    return entries
