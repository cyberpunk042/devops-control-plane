"""
Multi-language parser — regex-based analysis for languages without dedicated parsers.

Covers:
    Ruby (.rb, .rake)     — require, def, class, module
    PHP  (.php)           — use, function, class, interface, trait, namespace
    C#   (.cs)            — using, class, struct, interface, enum, namespace
    Elixir (.ex, .exs)    — alias/import/use, def/defp, defmodule
    Swift  (.swift)       — import, func, class, struct, enum, protocol
    Zig    (.zig)          — @import, fn, pub fn, struct, enum, union

Each language dispatches to a small analysis function.
All produce the universal FileAnalysis model.

Consumers: ParserRegistry → l2_quality, l2_structure
"""

from __future__ import annotations

import re
from pathlib import Path

from src.core.services.audit.parsers._base import (
    BaseParser,
    FileAnalysis,
    FileMetrics,
    ImportInfo,
    SymbolInfo,
)

# ═══════════════════════════════════════════════════════════════════
#  Extension → language mapping
# ═══════════════════════════════════════════════════════════════════

_EXT_LANG: dict[str, str] = {
    ".rb": "ruby",
    ".rake": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".ex": "elixir",
    ".exs": "elixir",
    ".swift": "swift",
    ".zig": "zig",
}

# ═══════════════════════════════════════════════════════════════════
#  Shared regex patterns
# ═══════════════════════════════════════════════════════════════════

_RE_BLOCK_COMMENT = re.compile(r"/\*[\s\S]*?\*/")
_RE_LINE_COMMENT_SLASH = re.compile(r"^\s*//", re.MULTILINE)
_RE_LINE_COMMENT_HASH = re.compile(r"^\s*#(?![\s]*(?:include|define|import|if|endif|pragma))", re.MULTILINE)


def _line_metrics(source: str, lines: list[str], use_hash: bool = False) -> tuple[int, int, int, int]:
    """Return (total, code, blank, comment) line counts."""
    total = len(lines)
    blocks = _RE_BLOCK_COMMENT.findall(source)
    comment = sum(c.count("\n") + 1 for c in blocks)
    if use_hash:
        comment += len(_RE_LINE_COMMENT_HASH.findall(source))
    else:
        comment += len(_RE_LINE_COMMENT_SLASH.findall(source))
    blank = sum(1 for l in lines if not l.strip())
    code = max(0, total - blank - comment)
    return total, code, blank, comment


def _find_block_end_brace(lines: list[str], start_0: int) -> int:
    depth = 0
    for i in range(start_0, len(lines)):
        for ch in lines[i]:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
    return len(lines) - 1


def _max_nesting_brace(lines: list[str], start_0: int, end_0: int) -> int:
    d = max_d = 0
    for i in range(start_0, min(end_0 + 1, len(lines))):
        for ch in lines[i]:
            if ch == "{":
                d += 1
                if d > max_d:
                    max_d = d
            elif ch == "}":
                d = max(0, d - 1)
    return max(0, max_d - 1)


# ═══════════════════════════════════════════════════════════════════
#  Ruby analysis
# ═══════════════════════════════════════════════════════════════════

_RE_RUBY_REQUIRE = re.compile(r"^\s*require(?:_relative)?\s+['\"]([^'\"]+)", re.MULTILINE)
_RE_RUBY_CLASS = re.compile(r"^\s*class\s+(\w+)", re.MULTILINE)
_RE_RUBY_MODULE = re.compile(r"^\s*module\s+(\w+)", re.MULTILINE)
_RE_RUBY_DEF = re.compile(r"^\s*def\s+(self\.)?(\w+[?!=]?)", re.MULTILINE)
_RE_RUBY_ATTR = re.compile(r"^\s*attr_(?:reader|writer|accessor)\s+(.+)", re.MULTILINE)
_RE_RUBY_BLOCK_COMMENT = re.compile(r"^=begin\b.*?^=end\b", re.MULTILINE | re.DOTALL)


def _analyze_ruby(source: str, lines: list[str]) -> tuple[list[ImportInfo], list[SymbolInfo], FileMetrics, dict]:
    imports = []
    for m in _RE_RUBY_REQUIRE.finditer(source):
        mod = m.group(1)
        imports.append(ImportInfo(
            module=mod, names=[mod.split("/")[-1]], is_from=False,
            lineno=source[:m.start()].count("\n") + 1,
            is_stdlib=not mod.startswith((".", "/")),
            is_internal=mod.startswith((".", "/")),
            is_relative=mod.startswith("."),
        ))

    symbols = []
    for m in _RE_RUBY_CLASS.finditer(source):
        symbols.append(SymbolInfo(
            name=m.group(1), kind="class",
            lineno=source[:m.start()].count("\n") + 1, end_lineno=source[:m.start()].count("\n") + 1,
            is_public=True, visibility="public",
        ))
    for m in _RE_RUBY_MODULE.finditer(source):
        symbols.append(SymbolInfo(
            name=m.group(1), kind="module",
            lineno=source[:m.start()].count("\n") + 1, end_lineno=source[:m.start()].count("\n") + 1,
            is_public=True, visibility="public",
        ))
    for m in _RE_RUBY_DEF.finditer(source):
        is_class_method = bool(m.group(1))
        name = m.group(2)
        symbols.append(SymbolInfo(
            name=name,
            kind="class_method" if is_class_method else "method",
            lineno=source[:m.start()].count("\n") + 1, end_lineno=source[:m.start()].count("\n") + 1,
            is_public=True, visibility="public",
        ))

    rb_blocks = _RE_RUBY_BLOCK_COMMENT.findall(source)
    total, code, blank, comment = _line_metrics(source, lines, use_hash=True)
    comment += sum(b.count("\n") + 1 for b in rb_blocks)
    code = max(0, total - blank - comment)
    funcs = [s for s in symbols if "method" in s.kind]
    types = [s for s in symbols if s.kind in ("class", "module")]

    metrics = FileMetrics(
        total_lines=total, code_lines=code, blank_lines=blank,
        comment_lines=comment, import_count=len(imports),
        function_count=len(funcs), class_count=len(types),
    )
    lang = {
        "type": "ruby",
        "module_count": sum(1 for s in symbols if s.kind == "module"),
        "class_method_count": sum(1 for s in symbols if s.kind == "class_method"),
        "attr_accessor_count": len(_RE_RUBY_ATTR.findall(source)),
    }
    return imports, symbols, metrics, lang


# ═══════════════════════════════════════════════════════════════════
#  PHP analysis
# ═══════════════════════════════════════════════════════════════════

_RE_PHP_USE = re.compile(r"^\s*use\s+([\w\\]+)", re.MULTILINE)
_RE_PHP_NAMESPACE = re.compile(r"^\s*namespace\s+([\w\\]+)", re.MULTILINE)
_RE_PHP_CLASS = re.compile(r"^\s*(?:abstract\s+)?class\s+(\w+)", re.MULTILINE)
_RE_PHP_INTERFACE = re.compile(r"^\s*interface\s+(\w+)", re.MULTILINE)
_RE_PHP_TRAIT = re.compile(r"^\s*trait\s+(\w+)", re.MULTILINE)
_RE_PHP_FUNC = re.compile(
    r"^\s*((?:public|protected|private|static|abstract|final)\s+)*"
    r"function\s+(\w+)", re.MULTILINE,
)


def _analyze_php(source: str, lines: list[str]) -> tuple[list[ImportInfo], list[SymbolInfo], FileMetrics, dict]:
    imports = []
    for m in _RE_PHP_USE.finditer(source):
        mod = m.group(1)
        imports.append(ImportInfo(
            module=mod, names=[mod.split("\\")[-1]], is_from=False,
            lineno=source[:m.start()].count("\n") + 1,
            is_stdlib=False, is_internal=True, is_relative=False,
        ))

    symbols = []
    for m in _RE_PHP_CLASS.finditer(source):
        symbols.append(SymbolInfo(
            name=m.group(1), kind="class",
            lineno=source[:m.start()].count("\n") + 1, end_lineno=source[:m.start()].count("\n") + 1,
            is_public=True, visibility="public",
        ))
    for m in _RE_PHP_INTERFACE.finditer(source):
        symbols.append(SymbolInfo(
            name=m.group(1), kind="interface",
            lineno=source[:m.start()].count("\n") + 1, end_lineno=source[:m.start()].count("\n") + 1,
            is_public=True, visibility="public",
        ))
    for m in _RE_PHP_TRAIT.finditer(source):
        symbols.append(SymbolInfo(
            name=m.group(1), kind="trait",
            lineno=source[:m.start()].count("\n") + 1, end_lineno=source[:m.start()].count("\n") + 1,
            is_public=True, visibility="public",
        ))
    for m in _RE_PHP_FUNC.finditer(source):
        modifiers = m.group(1) or ""
        vis = "private" if "private" in modifiers else ("protected" if "protected" in modifiers else "public")
        symbols.append(SymbolInfo(
            name=m.group(2), kind="function",
            lineno=source[:m.start()].count("\n") + 1, end_lineno=source[:m.start()].count("\n") + 1,
            is_public=(vis == "public"), visibility=vis,
        ))

    total, code, blank, comment = _line_metrics(source, lines, use_hash=True)
    ns = _RE_PHP_NAMESPACE.search(source)
    funcs = [s for s in symbols if s.kind == "function"]
    types = [s for s in symbols if s.kind in ("class", "interface", "trait")]

    metrics = FileMetrics(
        total_lines=total, code_lines=code, blank_lines=blank,
        comment_lines=comment, import_count=len(imports),
        function_count=len(funcs), class_count=len(types),
    )
    lang = {
        "type": "php",
        "namespace": ns.group(1) if ns else "",
        "trait_count": sum(1 for s in symbols if s.kind == "trait"),
    }
    return imports, symbols, metrics, lang


# ═══════════════════════════════════════════════════════════════════
#  C# analysis
# ═══════════════════════════════════════════════════════════════════

_RE_CS_USING = re.compile(r"^\s*using\s+([\w.]+)\s*;", re.MULTILINE)
_RE_CS_NAMESPACE = re.compile(r"^\s*namespace\s+([\w.]+)", re.MULTILINE)
_RE_CS_CLASS = re.compile(
    r"^\s*((?:public|private|protected|internal|abstract|sealed|static|partial)\s+)*"
    r"(class|struct|interface|enum|record)\s+(\w+)", re.MULTILINE,
)
_RE_CS_METHOD = re.compile(
    r"^\s*((?:(?:public|private|protected|internal|static|virtual|override|"
    r"abstract|sealed|async|partial)\s+)*)"
    r"(?:[\w<>\[\]?,.\s]+?)\s+(\w+)\s*\(", re.MULTILINE,
)
_RE_CS_PROPERTY = re.compile(r"^\s*(?:public|private|protected|internal)\s+[\w<>\[\]?]+\s+(\w+)\s*\{", re.MULTILINE)
_RE_CS_ATTRIBUTE = re.compile(r"^\s*\[(\w+)", re.MULTILINE)

_CS_KEYWORDS = frozenset({
    "if", "else", "for", "foreach", "while", "do", "switch",
    "return", "throw", "try", "catch", "finally", "lock",
    "using", "new", "checked", "unchecked", "fixed",
})


def _analyze_csharp(source: str, lines: list[str]) -> tuple[list[ImportInfo], list[SymbolInfo], FileMetrics, dict]:
    imports = []
    for m in _RE_CS_USING.finditer(source):
        mod = m.group(1)
        is_stdlib = mod.startswith(("System", "Microsoft"))
        imports.append(ImportInfo(
            module=mod, names=[mod.split(".")[-1]], is_from=False,
            lineno=source[:m.start()].count("\n") + 1,
            is_stdlib=is_stdlib, is_internal=not is_stdlib, is_relative=False,
        ))

    symbols = []
    for m in _RE_CS_CLASS.finditer(source):
        modifiers = m.group(1) or ""
        kind = m.group(2)
        name = m.group(3)
        is_public = "public" in modifiers
        symbols.append(SymbolInfo(
            name=name, kind=kind,
            lineno=source[:m.start()].count("\n") + 1, end_lineno=source[:m.start()].count("\n") + 1,
            is_public=is_public,
            visibility="public" if is_public else "private",
        ))
    for m in _RE_CS_METHOD.finditer(source):
        name = m.group(2)
        if name in _CS_KEYWORDS:
            continue
        modifiers = m.group(1) or ""
        is_public = "public" in modifiers
        symbols.append(SymbolInfo(
            name=name, kind="method",
            lineno=source[:m.start()].count("\n") + 1, end_lineno=source[:m.start()].count("\n") + 1,
            is_public=is_public,
            visibility="public" if is_public else "private",
        ))

    total, code, blank, comment = _line_metrics(source, lines)
    ns = _RE_CS_NAMESPACE.search(source)
    methods = [s for s in symbols if s.kind == "method"]
    types = [s for s in symbols if s.kind in ("class", "struct", "interface", "enum", "record")]
    attrs = _RE_CS_ATTRIBUTE.findall(source)

    metrics = FileMetrics(
        total_lines=total, code_lines=code, blank_lines=blank,
        comment_lines=comment, import_count=len(imports),
        function_count=len(methods), class_count=len(types),
    )
    lang = {
        "type": "csharp",
        "namespace": ns.group(1) if ns else "",
        "attribute_count": len(attrs),
        "property_count": len(_RE_CS_PROPERTY.findall(source)),
        "async_method_count": sum(1 for s in symbols if s.kind == "method" and "async" in source),
    }
    return imports, symbols, metrics, lang


# ═══════════════════════════════════════════════════════════════════
#  Elixir analysis
# ═══════════════════════════════════════════════════════════════════

_RE_EX_IMPORT = re.compile(r"^\s*(?:alias|import|use|require)\s+([\w.]+)", re.MULTILINE)
_RE_EX_MODULE = re.compile(r"^\s*defmodule\s+([\w.]+)", re.MULTILINE)
_RE_EX_DEF = re.compile(r"^\s*(def|defp)\s+(\w+)", re.MULTILINE)
_RE_EX_DEFMACRO = re.compile(r"^\s*(defmacro|defmacrop)\s+(\w+)", re.MULTILINE)
_RE_EX_PIPE = re.compile(r"\|>")
_RE_EX_COMMENT = re.compile(r"^\s*#", re.MULTILINE)
_RE_EX_DOC = re.compile(r'^\s*@(?:doc|moduledoc|spec)\b', re.MULTILINE)


def _analyze_elixir(source: str, lines: list[str]) -> tuple[list[ImportInfo], list[SymbolInfo], FileMetrics, dict]:
    imports = []
    for m in _RE_EX_IMPORT.finditer(source):
        mod = m.group(1)
        imports.append(ImportInfo(
            module=mod, names=[mod.split(".")[-1]], is_from=False,
            lineno=source[:m.start()].count("\n") + 1,
            is_stdlib=False, is_internal=True, is_relative=False,
        ))

    symbols = []
    for m in _RE_EX_MODULE.finditer(source):
        symbols.append(SymbolInfo(
            name=m.group(1), kind="module",
            lineno=source[:m.start()].count("\n") + 1, end_lineno=source[:m.start()].count("\n") + 1,
            is_public=True, visibility="public",
        ))
    for m in _RE_EX_DEF.finditer(source):
        is_private = m.group(1) == "defp"
        symbols.append(SymbolInfo(
            name=m.group(2), kind="function",
            lineno=source[:m.start()].count("\n") + 1, end_lineno=source[:m.start()].count("\n") + 1,
            is_public=not is_private,
            visibility="private" if is_private else "public",
        ))
    for m in _RE_EX_DEFMACRO.finditer(source):
        symbols.append(SymbolInfo(
            name=m.group(2), kind="macro",
            lineno=source[:m.start()].count("\n") + 1, end_lineno=source[:m.start()].count("\n") + 1,
            is_public=m.group(1) == "defmacro",
            visibility="public" if m.group(1) == "defmacro" else "private",
        ))

    total = len(lines)
    comment = len(_RE_EX_COMMENT.findall(source))
    blank = sum(1 for l in lines if not l.strip())
    code = max(0, total - blank - comment)
    funcs = [s for s in symbols if s.kind == "function"]
    modules = [s for s in symbols if s.kind == "module"]

    metrics = FileMetrics(
        total_lines=total, code_lines=code, blank_lines=blank,
        comment_lines=comment, import_count=len(imports),
        function_count=len(funcs), class_count=len(modules),
    )
    lang = {
        "type": "elixir",
        "pipe_count": len(_RE_EX_PIPE.findall(source)),
        "macro_count": sum(1 for s in symbols if s.kind == "macro"),
        "private_function_count": sum(1 for s in funcs if not s.is_public),
        "doc_attribute_count": len(_RE_EX_DOC.findall(source)),
    }
    return imports, symbols, metrics, lang


# ═══════════════════════════════════════════════════════════════════
#  Swift analysis
# ═══════════════════════════════════════════════════════════════════

_RE_SWIFT_IMPORT = re.compile(r"^\s*import\s+(\w+)", re.MULTILINE)
_RE_SWIFT_CLASS = re.compile(
    r"^\s*((?:public|private|internal|open|final)\s+)?"
    r"(class|struct|enum|protocol|actor)\s+(\w+)", re.MULTILINE,
)
_RE_SWIFT_FUNC = re.compile(
    r"^\s*((?:public|private|internal|open|static|class|override|mutating)\s+)*"
    r"func\s+(\w+)", re.MULTILINE,
)
_RE_SWIFT_PROPERTY = re.compile(
    r"^\s*((?:public|private|internal|open|static|lazy)\s+)?"
    r"(let|var)\s+(\w+)", re.MULTILINE,
)

_SWIFT_STDLIB = frozenset({
    "Foundation", "UIKit", "SwiftUI", "Combine", "CoreData",
    "CoreGraphics", "CoreLocation", "MapKit", "AVFoundation",
    "Swift", "Darwin", "Dispatch",
})


def _analyze_swift(source: str, lines: list[str]) -> tuple[list[ImportInfo], list[SymbolInfo], FileMetrics, dict]:
    imports = []
    for m in _RE_SWIFT_IMPORT.finditer(source):
        mod = m.group(1)
        imports.append(ImportInfo(
            module=mod, names=[mod], is_from=False,
            lineno=source[:m.start()].count("\n") + 1,
            is_stdlib=mod in _SWIFT_STDLIB,
            is_internal=mod not in _SWIFT_STDLIB,
            is_relative=False,
        ))

    symbols = []
    for m in _RE_SWIFT_CLASS.finditer(source):
        modifiers = m.group(1) or ""
        kind = m.group(2)
        name = m.group(3)
        is_public = "public" in modifiers or "open" in modifiers
        symbols.append(SymbolInfo(
            name=name, kind=kind,
            lineno=source[:m.start()].count("\n") + 1, end_lineno=source[:m.start()].count("\n") + 1,
            is_public=is_public,
            visibility="public" if is_public else "internal",
        ))
    for m in _RE_SWIFT_FUNC.finditer(source):
        name = m.group(2)
        modifiers = m.group(1) or ""
        is_public = "public" in modifiers or "open" in modifiers
        symbols.append(SymbolInfo(
            name=name, kind="function",
            lineno=source[:m.start()].count("\n") + 1, end_lineno=source[:m.start()].count("\n") + 1,
            is_public=is_public,
            visibility="public" if is_public else "internal",
        ))

    total, code, blank, comment = _line_metrics(source, lines)
    funcs = [s for s in symbols if s.kind == "function"]
    types = [s for s in symbols if s.kind in ("class", "struct", "enum", "protocol", "actor")]

    metrics = FileMetrics(
        total_lines=total, code_lines=code, blank_lines=blank,
        comment_lines=comment, import_count=len(imports),
        function_count=len(funcs), class_count=len(types),
    )
    lang = {
        "type": "swift",
        "protocol_count": sum(1 for s in types if s.kind == "protocol"),
        "actor_count": sum(1 for s in types if s.kind == "actor"),
        "property_count": len(_RE_SWIFT_PROPERTY.findall(source)),
    }
    return imports, symbols, metrics, lang


# ═══════════════════════════════════════════════════════════════════
#  Zig analysis
# ═══════════════════════════════════════════════════════════════════

_RE_ZIG_IMPORT = re.compile(r'@import\s*\(\s*"([^"]+)"', re.MULTILINE)
_RE_ZIG_FN = re.compile(
    r"^\s*(pub\s+)?fn\s+(\w+)\s*\(",
    re.MULTILINE,
)
_RE_ZIG_STRUCT = re.compile(r"^\s*(pub\s+)?const\s+(\w+)\s*=\s*(?:extern\s+)?struct\b", re.MULTILINE)
_RE_ZIG_ENUM = re.compile(r"^\s*(pub\s+)?const\s+(\w+)\s*=\s*enum\b", re.MULTILINE)
_RE_ZIG_UNION = re.compile(r"^\s*(pub\s+)?const\s+(\w+)\s*=\s*union\b", re.MULTILINE)
_RE_ZIG_ERROR = re.compile(r"^\s*(pub\s+)?const\s+(\w+)\s*=\s*error\b", re.MULTILINE)
_RE_ZIG_TEST = re.compile(r'^\s*test\s+"', re.MULTILINE)


def _analyze_zig(source: str, lines: list[str]) -> tuple[list[ImportInfo], list[SymbolInfo], FileMetrics, dict]:
    imports = []
    for m in _RE_ZIG_IMPORT.finditer(source):
        mod = m.group(1)
        is_stdlib = mod.startswith("std")
        imports.append(ImportInfo(
            module=mod, names=[mod.split(".")[-1]], is_from=False,
            lineno=source[:m.start()].count("\n") + 1,
            is_stdlib=is_stdlib, is_internal=not is_stdlib, is_relative=False,
        ))

    symbols = []
    for m in _RE_ZIG_FN.finditer(source):
        is_pub = bool(m.group(1))
        symbols.append(SymbolInfo(
            name=m.group(2), kind="function",
            lineno=source[:m.start()].count("\n") + 1, end_lineno=source[:m.start()].count("\n") + 1,
            is_public=is_pub, visibility="public" if is_pub else "private",
        ))
    for regex, kind in [
        (_RE_ZIG_STRUCT, "struct"), (_RE_ZIG_ENUM, "enum"),
        (_RE_ZIG_UNION, "union"), (_RE_ZIG_ERROR, "error_set"),
    ]:
        for m in regex.finditer(source):
            is_pub = bool(m.group(1))
            symbols.append(SymbolInfo(
                name=m.group(2), kind=kind,
                lineno=source[:m.start()].count("\n") + 1, end_lineno=source[:m.start()].count("\n") + 1,
                is_public=is_pub, visibility="public" if is_pub else "private",
            ))

    total, code, blank, comment = _line_metrics(source, lines)
    funcs = [s for s in symbols if s.kind == "function"]
    types = [s for s in symbols if s.kind in ("struct", "enum", "union", "error_set")]
    test_count = len(_RE_ZIG_TEST.findall(source))

    metrics = FileMetrics(
        total_lines=total, code_lines=code, blank_lines=blank,
        comment_lines=comment, import_count=len(imports),
        function_count=len(funcs), class_count=len(types),
    )
    lang = {
        "type": "zig",
        "test_count": test_count,
        "error_set_count": sum(1 for s in symbols if s.kind == "error_set"),
    }
    return imports, symbols, metrics, lang


# ═══════════════════════════════════════════════════════════════════
#  Dispatcher
# ═══════════════════════════════════════════════════════════════════

_ANALYZERS = {
    "ruby": _analyze_ruby,
    "php": _analyze_php,
    "csharp": _analyze_csharp,
    "elixir": _analyze_elixir,
    "swift": _analyze_swift,
    "zig": _analyze_zig,
}


class MultiLangParser(BaseParser):
    """Parser for Ruby, PHP, C#, Elixir, Swift, and Zig."""

    @property
    def language(self) -> str:
        return "multi"

    def extensions(self) -> set[str]:
        return set(_EXT_LANG.keys())

    def parse_file(
        self,
        file_path: Path,
        project_root: Path | None = None,
        project_prefix: str = "src",
    ) -> FileAnalysis:
        rel_path = (
            str(file_path.relative_to(project_root))
            if project_root
            else str(file_path)
        )
        ext = file_path.suffix.lower()
        lang = _EXT_LANG.get(ext, "unknown")

        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return FileAnalysis(
                path=rel_path, language=lang, file_type="source",
                parse_error=str(exc),
            )

        lines = source.splitlines()
        analyzer = _ANALYZERS.get(lang)
        if analyzer is None:
            return FileAnalysis(path=rel_path, language=lang, file_type="source")

        imports, symbols, metrics, lang_metrics = analyzer(source, lines)

        return FileAnalysis(
            path=rel_path,
            language=lang,
            file_type="source",
            imports=imports,
            symbols=symbols,
            metrics=metrics,
            language_metrics=lang_metrics,
        )


# ═══════════════════════════════════════════════════════════════════
#  Registry self-registration
# ═══════════════════════════════════════════════════════════════════

_multilang_parser = MultiLangParser()


def _register():
    from src.core.services.audit.parsers import registry
    registry.register(_multilang_parser)


_register()
