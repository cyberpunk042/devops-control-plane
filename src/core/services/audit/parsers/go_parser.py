"""
Go parser — regex-based analysis for .go source files.

Extracts:
    - Package declarations
    - Import statements (single + grouped)
    - Function declarations (regular + methods with receivers)
    - Type declarations (struct, interface, type alias)
    - Exported vs unexported symbols (uppercase convention)
    - Error return detection (functions returning error)
    - Doc comments (// preceding declarations)
    - Goroutine and defer usage
    - Init function detection

Registered extensions: .go

Consumers: ParserRegistry → l2_quality (_rubrics "go"), l2_structure
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
#  Regex patterns
# ═══════════════════════════════════════════════════════════════════

# Package declaration
_RE_PACKAGE = re.compile(r"^\s*package\s+(\w+)", re.MULTILINE)

# ── Imports ──────────────────────────────────────────────────────

# Single-line import: import "fmt"
_RE_IMPORT_SINGLE = re.compile(
    r"""^\s*import\s+"""
    r"""(?:(\w+)\s+)?"""           # optional alias
    r""""([^"]+)" """.strip(),
    re.MULTILINE,
)

# Grouped import block: import ( ... )
_RE_IMPORT_GROUP = re.compile(
    r"^\s*import\s*\((.*?)\)",
    re.MULTILINE | re.DOTALL,
)

# Individual line inside a grouped import
_RE_IMPORT_LINE = re.compile(
    r"""^\s*"""
    r"""(?:(\w+)\s+)?"""           # optional alias
    r""""([^"]+)" """.strip(),
    re.MULTILINE,
)

# ── Functions ────────────────────────────────────────────────────

# Regular function: func Name(args) (returns) {
# Method: func (r *Receiver) Name(args) (returns) {
_RE_FUNC = re.compile(
    r"^\s*func\s+"
    r"(?:\(\s*\w+\s+\*?(\w+)\s*\)\s+)?"   # optional receiver: (r *Type)
    r"(\w+)\s*"                             # function name
    r"\(([^)]*)\)"                          # parameters
    r"(?:\s*\(([^)]*)\)|\s*(\w[^\s{]*))?",  # return type(s)
    re.MULTILINE,
)

# ── Types ────────────────────────────────────────────────────────

# type Name struct {
_RE_TYPE_STRUCT = re.compile(
    r"^\s*type\s+(\w+)\s+struct\s*\{",
    re.MULTILINE,
)

# type Name interface {
_RE_TYPE_INTERFACE = re.compile(
    r"^\s*type\s+(\w+)\s+interface\s*\{",
    re.MULTILINE,
)

# type Name = OtherType  or  type Name OtherType
_RE_TYPE_ALIAS = re.compile(
    r"^\s*type\s+(\w+)\s+=?\s*\w",
    re.MULTILINE,
)

# ── Constants and variables ──────────────────────────────────────

_RE_CONST = re.compile(r"^\s*const\s+(?:\(|(\w+))", re.MULTILINE)
_RE_VAR = re.compile(r"^\s*var\s+(?:\(|(\w+))", re.MULTILINE)

# ── Go-specific patterns ────────────────────────────────────────

_RE_GOROUTINE = re.compile(r"\bgo\s+\w+")
_RE_DEFER = re.compile(r"\bdefer\s+")
_RE_CHANNEL = re.compile(r"\bchan\s+\w+|<-\s*\w+|\w+\s*<-")
_RE_SELECT = re.compile(r"^\s*select\s*\{", re.MULTILINE)

# ── Comments ─────────────────────────────────────────────────────

_RE_LINE_COMMENT = re.compile(r"^\s*//", re.MULTILINE)
_RE_BLOCK_COMMENT = re.compile(r"/\*[\s\S]*?\*/")
_RE_DOC_COMMENT = re.compile(
    r"((?:^\s*//[^\n]*\n)+)\s*(?:func|type|var|const)\s",
    re.MULTILINE,
)

# ── Standard library packages ───────────────────────────────────

_GO_STDLIB = frozenset({
    "bufio", "bytes", "context", "crypto", "database", "debug",
    "encoding", "errors", "expvar", "flag", "fmt", "go", "hash",
    "html", "image", "index", "io", "log", "maps", "math", "mime",
    "net", "os", "path", "plugin", "reflect", "regexp", "runtime",
    "slices", "sort", "strconv", "strings", "sync", "syscall",
    "testing", "text", "time", "unicode", "unsafe",
    # Sub-packages are detected by prefix
})


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _is_exported(name: str) -> bool:
    """Go convention: exported names start with uppercase."""
    return bool(name) and name[0].isupper()


def _is_stdlib(module: str) -> bool:
    """Check if an import path is a Go standard library package."""
    # Stdlib packages don't contain dots (no domain prefix)
    if "." in module.split("/")[0]:
        return False
    root = module.split("/")[0]
    return root in _GO_STDLIB


def _count_params(params_str: str) -> int:
    """Count the number of parameters in a Go function signature."""
    if not params_str or not params_str.strip():
        return 0
    # Split by comma, but be careful with func types in params
    depth = 0
    count = 1
    for ch in params_str:
        if ch in ("(", "["):
            depth += 1
        elif ch in (")", "]"):
            depth -= 1
        elif ch == "," and depth == 0:
            count += 1
    return count


def _returns_error(return_str: str | None) -> bool:
    """Check if a function return type contains 'error'."""
    if not return_str:
        return False
    return "error" in return_str


def _has_preceding_comment(lines: list[str], lineno_0: int) -> bool:
    """Check if the line before lineno (0-indexed) is a // comment."""
    if lineno_0 <= 0:
        return False
    prev = lines[lineno_0 - 1].strip()
    return prev.startswith("//")


def _find_block_end(lines: list[str], start_0: int) -> int:
    """Find the closing brace for a block starting at a line with {.

    Returns the 0-indexed line number of the closing }.
    """
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


def _max_nesting_in_range(lines: list[str], start_0: int, end_0: int) -> int:
    """Calculate max brace nesting depth within a line range.

    The outer function/type braces count as depth 1,
    so we subtract 1 to get body nesting.
    """
    max_depth = 0
    depth = 0
    for i in range(start_0, min(end_0 + 1, len(lines))):
        for ch in lines[i]:
            if ch == "{":
                depth += 1
                if depth > max_depth:
                    max_depth = depth
            elif ch == "}":
                depth = max(0, depth - 1)
    # Subtract 1 for the outer block
    return max(0, max_depth - 1)


# ═══════════════════════════════════════════════════════════════════
#  Parser implementation
# ═══════════════════════════════════════════════════════════════════


class GoParser(BaseParser):
    """Regex-based parser for Go source files.

    Extracts:
    - Package declaration
    - Import statements (single + grouped, stdlib detection)
    - Function declarations (regular + methods with receivers)
    - Type declarations (struct, interface, alias)
    - Exported vs unexported symbols
    - Error return detection
    - Doc comments (// preceding declarations)
    - Goroutine, defer, channel, select usage counts
    """

    @property
    def language(self) -> str:
        return "go"

    def extensions(self) -> set[str]:
        return {".go"}

    def parse_file(
        self,
        file_path: Path,
        project_root: Path | None = None,
        project_prefix: str = "src",
    ) -> FileAnalysis:
        """Parse a Go source file into the universal FileAnalysis model."""
        rel_path = (
            str(file_path.relative_to(project_root))
            if project_root
            else str(file_path)
        )

        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return FileAnalysis(
                path=rel_path,
                language="go",
                file_type="source",
                parse_error=str(exc),
            )

        lines = source.splitlines()

        # ── Package ──────────────────────────────────────────
        pkg_match = _RE_PACKAGE.search(source)
        package_name = pkg_match.group(1) if pkg_match else ""

        # ── Imports ──────────────────────────────────────────
        imports = self._extract_imports(source)

        # ── Symbols ──────────────────────────────────────────
        symbols = self._extract_symbols(source, lines)

        # ── Metrics ──────────────────────────────────────────
        metrics, lang_metrics = self._compute_metrics(
            source, lines, imports, symbols, package_name,
        )

        return FileAnalysis(
            path=rel_path,
            language="go",
            file_type="source",
            imports=imports,
            symbols=symbols,
            metrics=metrics,
            language_metrics=lang_metrics,
        )

    # ── Import extraction ─────────────────────────────────────

    def _extract_imports(self, source: str) -> list[ImportInfo]:
        """Extract all import statements."""
        imports: list[ImportInfo] = []

        # Single-line imports
        for m in _RE_IMPORT_SINGLE.finditer(source):
            alias = m.group(1) or ""
            module = m.group(2)
            lineno = source[:m.start()].count("\n") + 1

            imports.append(ImportInfo(
                module=module,
                names=[alias] if alias else [module.split("/")[-1]],
                is_from=False,
                lineno=lineno,
                is_stdlib=_is_stdlib(module),
                is_internal=not _is_stdlib(module) and "." not in module.split("/")[0],
                is_relative=False,
            ))

        # Grouped imports
        for group_m in _RE_IMPORT_GROUP.finditer(source):
            group_start_line = source[:group_m.start()].count("\n") + 1
            group_body = group_m.group(1)

            for line_m in _RE_IMPORT_LINE.finditer(group_body):
                alias = line_m.group(1) or ""
                module = line_m.group(2)
                # Calculate actual line number within the group
                offset = group_body[:line_m.start()].count("\n")
                lineno = group_start_line + 1 + offset

                imports.append(ImportInfo(
                    module=module,
                    names=[alias] if alias else [module.split("/")[-1]],
                    is_from=False,
                    lineno=lineno,
                    is_stdlib=_is_stdlib(module),
                    is_internal=not _is_stdlib(module) and "." not in module.split("/")[0],
                    is_relative=False,
                ))

        return imports

    # ── Symbol extraction ─────────────────────────────────────

    def _extract_symbols(
        self, source: str, lines: list[str],
    ) -> list[SymbolInfo]:
        """Extract function and type declarations."""
        symbols: list[SymbolInfo] = []

        # ── Functions ─────────────────────────────────────────
        for m in _RE_FUNC.finditer(source):
            receiver = m.group(1)       # receiver type, or None
            name = m.group(2)
            params = m.group(3)         # parameter string
            return_multi = m.group(4)   # multi-return: (int, error)
            return_single = m.group(5)  # single return: error

            lineno_0 = source[:m.start()].count("\n")
            lineno = lineno_0 + 1

            # Determine kind
            if receiver:
                kind = "method"
            elif name == "init":
                kind = "function"  # init functions are special
            else:
                kind = "function"

            # Find end of function body
            end_0 = _find_block_end(lines, lineno_0)
            end_lineno = end_0 + 1
            body_lines = max(0, end_0 - lineno_0 - 1)  # exclude func line + closing }

            # Nesting depth
            max_nesting = _max_nesting_in_range(lines, lineno_0, end_0)

            # Doc comment
            has_doc = _has_preceding_comment(lines, lineno_0)

            # Parameter count
            num_args = _count_params(params)

            # Error return
            return_str = return_multi or return_single or ""

            # Decorators → none in Go, but we note receiver
            decorators: list[str] = []
            if receiver:
                decorators.append(f"receiver:{receiver}")

            symbols.append(SymbolInfo(
                name=f"{receiver}.{name}" if receiver else name,
                kind=kind,
                lineno=lineno,
                end_lineno=end_lineno,
                body_lines=body_lines,
                max_nesting=max_nesting,
                has_docstring=has_doc,
                is_public=_is_exported(name),
                visibility="public" if _is_exported(name) else "private",
                num_args=num_args,
                decorators=decorators,
            ))

        # ── Structs ───────────────────────────────────────────
        for m in _RE_TYPE_STRUCT.finditer(source):
            name = m.group(1)
            lineno_0 = source[:m.start()].count("\n")
            lineno = lineno_0 + 1
            end_0 = _find_block_end(lines, lineno_0)
            end_lineno = end_0 + 1
            body_lines = max(0, end_0 - lineno_0 - 1)
            has_doc = _has_preceding_comment(lines, lineno_0)

            # Extract method names for this struct from the symbols
            # (methods are found by receiver type matching)
            methods = [
                s.name.split(".")[-1]
                for s in symbols
                if s.kind == "method"
                and s.decorators
                and s.decorators[0] == f"receiver:{name}"
            ]

            symbols.append(SymbolInfo(
                name=name,
                kind="struct",
                lineno=lineno,
                end_lineno=end_lineno,
                body_lines=body_lines,
                max_nesting=0,
                has_docstring=has_doc,
                is_public=_is_exported(name),
                visibility="public" if _is_exported(name) else "private",
                methods=methods,
            ))

        # ── Interfaces ────────────────────────────────────────
        for m in _RE_TYPE_INTERFACE.finditer(source):
            name = m.group(1)
            lineno_0 = source[:m.start()].count("\n")
            lineno = lineno_0 + 1
            end_0 = _find_block_end(lines, lineno_0)
            end_lineno = end_0 + 1
            body_lines = max(0, end_0 - lineno_0 - 1)
            has_doc = _has_preceding_comment(lines, lineno_0)

            # Interface methods: lines inside the block that look like method signatures
            methods = []
            for i in range(lineno_0 + 1, end_0):
                stripped = lines[i].strip()
                if stripped and not stripped.startswith("//") and stripped != "}":
                    # Interface method: Name(args) returns
                    method_name = stripped.split("(")[0].strip()
                    if method_name and method_name[0].isalpha():
                        methods.append(method_name)

            symbols.append(SymbolInfo(
                name=name,
                kind="interface",
                lineno=lineno,
                end_lineno=end_lineno,
                body_lines=body_lines,
                max_nesting=0,
                has_docstring=has_doc,
                is_public=_is_exported(name),
                visibility="public" if _is_exported(name) else "private",
                methods=methods,
            ))

        return symbols

    # ── Metrics computation ───────────────────────────────────

    def _compute_metrics(
        self,
        source: str,
        lines: list[str],
        imports: list[ImportInfo],
        symbols: list[SymbolInfo],
        package_name: str,
    ) -> tuple[FileMetrics, dict]:
        """Compute file-level and Go-specific metrics."""
        total_lines = len(lines)

        # ── Line classification ───────────────────────────────
        block_comments = _RE_BLOCK_COMMENT.findall(source)
        comment_lines = sum(c.count("\n") + 1 for c in block_comments)
        comment_lines += len(_RE_LINE_COMMENT.findall(source))

        blank_lines = sum(1 for line in lines if not line.strip())
        code_lines = max(0, total_lines - blank_lines - comment_lines)

        # ── Function metrics ──────────────────────────────────
        functions = [s for s in symbols if s.kind in ("function", "method")]
        structs = [s for s in symbols if s.kind == "struct"]
        interfaces = [s for s in symbols if s.kind == "interface"]

        func_lengths = [s.body_lines for s in functions]
        avg_func_len = (
            sum(func_lengths) / len(func_lengths) if func_lengths else 0.0
        )

        # ── Max nesting ───────────────────────────────────────
        max_nesting = max((s.max_nesting for s in symbols), default=0)

        # ── Exported ratio ────────────────────────────────────
        exported = sum(1 for s in symbols if s.is_public)
        total_symbols = len(symbols)
        exported_ratio = (
            round(exported / total_symbols * 100, 1) if total_symbols else 0.0
        )

        # ── Error handling ────────────────────────────────────
        error_returns = 0
        for m in _RE_FUNC.finditer(source):
            return_multi = m.group(4) or ""
            return_single = m.group(5) or ""
            if _returns_error(return_multi) or _returns_error(return_single):
                error_returns += 1

        # ── Doc coverage ──────────────────────────────────────
        documented = sum(1 for s in symbols if s.has_docstring)
        docstring_pct = (
            round(documented / total_symbols * 100, 1) if total_symbols else 0.0
        )

        # ── Go-specific patterns ─────────────────────────────
        goroutine_count = len(_RE_GOROUTINE.findall(source))
        defer_count = len(_RE_DEFER.findall(source))
        channel_count = len(_RE_CHANNEL.findall(source))
        select_count = len(_RE_SELECT.findall(source))
        has_init = any(s.name == "init" for s in functions)
        is_test = any(
            s.name.startswith("Test") or s.name.startswith("Benchmark")
            for s in functions
        )

        # ── Build metrics ─────────────────────────────────────
        metrics = FileMetrics(
            total_lines=total_lines,
            code_lines=code_lines,
            blank_lines=blank_lines,
            comment_lines=comment_lines,
            import_count=len(imports),
            function_count=len(functions),
            class_count=len(structs) + len(interfaces),
            avg_function_length=round(avg_func_len, 1),
            max_function_length=max(func_lengths, default=0),
            max_nesting_depth=max_nesting,
        )

        lang_metrics = {
            "package": package_name,
            "struct_count": len(structs),
            "interface_count": len(interfaces),
            "method_count": sum(1 for s in functions if s.kind == "method"),
            "exported_count": exported,
            "unexported_count": total_symbols - exported,
            "exported_ratio": exported_ratio,
            "error_return_count": error_returns,
            "doc_coverage": docstring_pct,
            "goroutine_count": goroutine_count,
            "defer_count": defer_count,
            "channel_count": channel_count,
            "select_count": select_count,
            "has_init_func": has_init,
            "is_test_file": is_test,
        }

        return metrics, lang_metrics


# ═══════════════════════════════════════════════════════════════════
#  Registry self-registration
# ═══════════════════════════════════════════════════════════════════

_go_parser = GoParser()


def _register():
    """Register GoParser for .go files."""
    from src.core.services.audit.parsers import registry
    registry.register(_go_parser)


_register()
