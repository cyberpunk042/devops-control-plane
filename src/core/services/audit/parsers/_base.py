"""
Base parser — universal data model and ABC for all language parsers.

Every parser in this package outputs the same universal types defined here.
This ensures consumers (l2_quality, l2_structure, scoring, directives) work
identically regardless of the source language being analyzed.

Data model hierarchy:
    FileAnalysis
    ├── imports: list[ImportInfo]     — import/require/use statements
    ├── symbols: list[SymbolInfo]     — functions, classes, structs, traits
    ├── metrics: FileMetrics          — line counts, complexity aggregates
    └── symbol_locations: list[SymbolLocation]  — for code peeking

Parser contract:
    BaseParser (ABC)
    ├── language (property)           — "python", "javascript", "go", etc.
    ├── extensions() → set[str]       — file extensions this parser handles
    └── parse_file(path, root) → FileAnalysis
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


# ═══════════════════════════════════════════════════════════════════
#  ImportInfo — a single import/require/use statement
# ═══════════════════════════════════════════════════════════════════


@dataclass
class ImportInfo:
    """A single import statement, language-agnostic.

    Works for Python ``import X``, JS ``import X from 'Y'``,
    Go ``import "pkg"``, Rust ``use crate::X``, etc.
    """

    module: str                      # "flask" or "src.core.services" or "lodash"
    names: list[str]                 # ["Flask", "jsonify"] or ["*"] or []
    alias: str | None = None         # import X as alias
    is_from: bool = False            # True for "from X import ..." (Python/Elixir)
    lineno: int = 0                  # Line number in file
    is_internal: bool = False        # True if module is within the project
    is_stdlib: bool = False          # True if module is in the language's stdlib
    is_relative: bool = False        # True for relative imports (Python: from . import)

    @property
    def top_level(self) -> str:
        """Top-level package name (e.g., 'flask' from 'flask.views').

        For Go: 'github.com/gin-gonic/gin' → 'github.com/gin-gonic/gin'
        For Python: 'flask.views' → 'flask'
        For JS: '@scope/pkg' → '@scope/pkg'
        """
        # Handle scoped npm packages: @scope/pkg
        if self.module.startswith("@") and "/" in self.module:
            parts = self.module.split("/")
            return f"{parts[0]}/{parts[1]}" if len(parts) >= 2 else self.module
        return self.module.split(".")[0]


# ═══════════════════════════════════════════════════════════════════
#  SymbolInfo — a function, class, struct, trait, module definition
# ═══════════════════════════════════════════════════════════════════


@dataclass
class SymbolInfo:
    """A function, class, struct, or other named definition.

    Language-agnostic: works for Python def/class, JS function/class,
    Go func/type, Rust fn/struct/impl, etc.
    """

    name: str
    kind: str                        # "function", "async_function", "class",
                                     # "struct", "trait", "interface", "enum",
                                     # "module", "method", "type_alias"
    lineno: int                      # Start line
    end_lineno: int                  # End line
    decorators: list[str] = field(default_factory=list)     # Python decorators, Java annotations
    is_public: bool = True           # True if name doesn't start with _ (Python convention)
    visibility: str = "default"      # "public", "private", "protected", "internal", "default"
                                     # "default" means language convention applies (e.g., Python
                                     # uses _ prefix, Go uses capitalization)
    has_docstring: bool = False      # Has documentation comment
    num_args: int = 0                # For functions: parameter count (excl. self/cls/this)
    body_lines: int = 0             # Lines in the body
    max_nesting: int = 0             # Max nesting depth within the body
    methods: list[str] = field(default_factory=list)  # For classes: method names

    @property
    def length(self) -> int:
        """Total length in lines (end_lineno - lineno + 1)."""
        return max(0, self.end_lineno - self.lineno + 1)


# ═══════════════════════════════════════════════════════════════════
#  FileMetrics — aggregate code metrics for a single file
# ═══════════════════════════════════════════════════════════════════


@dataclass
class FileMetrics:
    """Code metrics for a single file.

    All fields are language-agnostic counts and ratios.
    Language-specific metrics go in FileAnalysis.language_metrics.
    """

    total_lines: int = 0             # Total line count
    code_lines: int = 0              # Non-blank, non-comment lines
    blank_lines: int = 0             # Empty lines
    comment_lines: int = 0           # Comment-only lines
    docstring_lines: int = 0         # Lines inside docstrings/doc comments

    avg_function_length: float = 0.0  # Average function body length
    max_function_length: int = 0     # Longest function body in lines
    max_nesting_depth: int = 0       # Deepest nesting in the file

    import_count: int = 0            # Number of import statements
    function_count: int = 0          # Number of functions/methods
    class_count: int = 0             # Number of classes/structs/traits

    # Python-specific (kept for backward compat during migration)
    has_main_guard: bool = False      # if __name__ == "__main__"
    has_type_hints: float = 0.0       # Fraction of functions with type annotations


# ═══════════════════════════════════════════════════════════════════
#  SymbolLocation — for code peeking and navigation
# ═══════════════════════════════════════════════════════════════════


@dataclass
class SymbolLocation:
    """Links a symbol to its source position for code peeking.

    Used by the audit-data directive to show inline previews
    and navigate to specific symbols in the preview panel.
    """

    symbol: str                      # Symbol name
    kind: str                        # "function", "class", etc.
    file: str                        # Relative file path
    line_start: int                  # First line of definition
    line_end: int                    # Last line of definition
    preview: str = ""                # First 3-5 lines of the body (for inline peek)


# ═══════════════════════════════════════════════════════════════════
#  FileAnalysis — complete analysis result for one file
# ═══════════════════════════════════════════════════════════════════


@dataclass
class FileAnalysis:
    """Complete analysis result for one source file.

    This is the universal output type for ALL parsers. Every field
    is language-agnostic. Language-specific data goes in the
    ``language_metrics`` dict.

    Consumers (l2_quality, l2_structure, scoring) access this type
    without knowing which parser produced it.
    """

    # ── Identity ──────────────────────────────────────────────
    path: str                        # Relative path from project root

    language: str = "unknown"        # "python", "javascript", "go", "rust", etc.
    file_type: str = "source"        # "source", "template", "config", "markup",
                                     # "style", "script", "data", "build"
    template_engine: str | None = None  # "jinja2", "erb", "heex", "go-tmpl", None

    # ── Parsed data ───────────────────────────────────────────
    imports: list[ImportInfo] = field(default_factory=list)
    symbols: list[SymbolInfo] = field(default_factory=list)
    metrics: FileMetrics = field(default_factory=FileMetrics)

    # ── Parse status ──────────────────────────────────────────
    parse_error: str | None = None   # Error message if parsing failed

    # ── Language-specific extensions ──────────────────────────
    language_metrics: dict = field(default_factory=dict)
    # Python: {"docstring_coverage": 0.85, "type_hint_coverage": 0.7, ...}
    # Go: {"exported_ratio": 0.6, "error_handling_ratio": 0.9, ...}
    # Rust: {"unsafe_block_count": 0, "lifetime_count": 3, ...}
    # JS: {"callback_depth": 2, "es_module": True, ...}
    # Template: {"directive_count": 15, "block_count": 3, ...}

    # ── Code navigation ───────────────────────────────────────
    symbol_locations: list[SymbolLocation] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to a JSON-friendly dict.

        Includes all universal fields plus language_metrics.
        """
        return {
            "path": self.path,
            "language": self.language,
            "file_type": self.file_type,
            "template_engine": self.template_engine,
            "imports": [
                {
                    "module": imp.module,
                    "names": imp.names,
                    "alias": imp.alias,
                    "is_from": imp.is_from,
                    "lineno": imp.lineno,
                    "is_internal": imp.is_internal,
                    "is_stdlib": imp.is_stdlib,
                    "is_relative": imp.is_relative,
                    "top_level": imp.top_level,
                }
                for imp in self.imports
            ],
            "symbols": [
                {
                    "name": sym.name,
                    "kind": sym.kind,
                    "lineno": sym.lineno,
                    "end_lineno": sym.end_lineno,
                    "is_public": sym.is_public,
                    "visibility": sym.visibility,
                    "has_docstring": sym.has_docstring,
                    "body_lines": sym.body_lines,
                    "decorators": sym.decorators,
                    "num_args": sym.num_args,
                    "max_nesting": sym.max_nesting,
                    "methods": sym.methods,
                    "length": sym.length,
                }
                for sym in self.symbols
            ],
            "metrics": {
                "total_lines": self.metrics.total_lines,
                "code_lines": self.metrics.code_lines,
                "blank_lines": self.metrics.blank_lines,
                "comment_lines": self.metrics.comment_lines,
                "docstring_lines": self.metrics.docstring_lines,
                "avg_function_length": round(self.metrics.avg_function_length, 1),
                "max_function_length": self.metrics.max_function_length,
                "max_nesting_depth": self.metrics.max_nesting_depth,
                "import_count": self.metrics.import_count,
                "function_count": self.metrics.function_count,
                "class_count": self.metrics.class_count,
                "has_main_guard": self.metrics.has_main_guard,
                "has_type_hints": round(self.metrics.has_type_hints, 2),
            },
            "parse_error": self.parse_error,
            "language_metrics": self.language_metrics,
            "symbol_locations": [
                {
                    "symbol": loc.symbol,
                    "kind": loc.kind,
                    "file": loc.file,
                    "line_start": loc.line_start,
                    "line_end": loc.line_end,
                    "preview": loc.preview,
                }
                for loc in self.symbol_locations
            ],
        }


# ═══════════════════════════════════════════════════════════════════
#  BaseParser — ABC for all language parsers
# ═══════════════════════════════════════════════════════════════════


class BaseParser(ABC):
    """Abstract base for all language parsers.

    Each parser implementation:
    1. Declares which file extensions it handles via ``extensions()``.
    2. Declares its language via the ``language`` property.
    3. Implements ``parse_file()`` to produce a ``FileAnalysis``.

    Parsers MUST NOT execute or import the code they parse.
    Parsers MUST handle malformed files gracefully (return FileAnalysis
    with parse_error set, never raise).
    """

    @property
    @abstractmethod
    def language(self) -> str:
        """The language this parser handles (e.g., 'python', 'javascript')."""
        ...

    @abstractmethod
    def extensions(self) -> set[str]:
        """File extensions this parser handles (without dots).

        Example: {"py", "pyw", "pyi"} for Python.
        """
        ...

    @abstractmethod
    def parse_file(
        self,
        path: Path,
        project_root: Path | None = None,
        project_prefix: str = "src",
    ) -> FileAnalysis:
        """Parse a single file and return a FileAnalysis.

        Args:
            path: Absolute path to the file.
            project_root: Project root for computing relative paths and
                          detecting internal imports.
            project_prefix: Top-level source package (e.g., "src") used to
                            identify internal imports.

        Returns:
            FileAnalysis with all available data populated.
            On parse failure, returns FileAnalysis with parse_error set.
        """
        ...

    def file_type(self) -> str:
        """Default file type for files handled by this parser.

        Override in subclasses for template/config/style parsers.
        """
        return "source"
