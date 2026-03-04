"""
Python AST parser — extract imports, symbols, and code metrics from .py files.

Uses stdlib ``ast`` for reliable, fast parsing.  Never executes the code.

Public API:
    parse_file(path)   → FileAnalysis for one Python file
    parse_tree(root)   → dict[relative_path, FileAnalysis] for all .py files

Also exposes PythonParser(BaseParser) for use via the parser registry.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

from src.core.services.audit.parsers._base import (
    BaseParser,
    FileAnalysis,
    FileMetrics,
    ImportInfo,
    SymbolInfo,
)

logger = logging.getLogger(__name__)




# ═══════════════════════════════════════════════════════════════════
#  Stdlib detection (Python 3.10+)
# ═══════════════════════════════════════════════════════════════════

_STDLIB_MODULES: set[str] | None = None


def _get_stdlib_modules() -> set[str]:
    """Get the set of stdlib module names."""
    global _STDLIB_MODULES
    if _STDLIB_MODULES is None:
        try:
            import sys
            _STDLIB_MODULES = set(sys.stdlib_module_names)
        except AttributeError:
            # Python < 3.10 fallback
            _STDLIB_MODULES = {
                "os", "sys", "re", "json", "pathlib", "typing", "collections",
                "functools", "itertools", "logging", "subprocess", "shutil",
                "time", "datetime", "hashlib", "hmac", "base64", "io",
                "abc", "dataclasses", "enum", "math", "random", "string",
                "textwrap", "copy", "pprint", "inspect", "ast", "dis",
                "unittest", "argparse", "configparser", "csv", "sqlite3",
                "xml", "html", "http", "urllib", "email", "socket",
                "threading", "multiprocessing", "concurrent", "asyncio",
                "contextlib", "traceback", "warnings", "tempfile", "glob",
                "fnmatch", "stat", "struct", "codecs", "pickle", "shelve",
                "platform", "ctypes", "importlib", "pkgutil", "zipfile",
                "tarfile", "gzip", "bz2", "lzma", "hashlib", "secrets",
                "uuid", "pdb", "cProfile", "timeit", "doctest", "types",
                "weakref", "array", "queue", "heapq", "bisect", "operator",
                "decimal", "fractions", "statistics", "signal", "mmap",
                "select", "selectors", "ssl", "xmlrpc", "ftplib", "smtplib",
                "poplib", "imaplib", "telnetlib", "socketserver",
            }
    return _STDLIB_MODULES


# ═══════════════════════════════════════════════════════════════════
#  AST walking helpers
# ═══════════════════════════════════════════════════════════════════


def _nesting_depth(node: ast.AST, current: int = 0) -> int:
    """Compute max nesting depth inside a function/class body."""
    max_depth = current
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.If, ast.For, ast.While, ast.With,
                              ast.Try, ast.ExceptHandler,
                              ast.AsyncFor, ast.AsyncWith)):
            child_depth = _nesting_depth(child, current + 1)
            max_depth = max(max_depth, child_depth)
        else:
            child_depth = _nesting_depth(child, current)
            max_depth = max(max_depth, child_depth)
    return max_depth


def _has_docstring(node: ast.AST) -> bool:
    """Check if a function/class node has a docstring."""
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return False
    if node.body and isinstance(node.body[0], ast.Expr):
        val = node.body[0].value
        if isinstance(val, ast.Constant) and isinstance(val.value, str):
            return True
    return False


def _count_docstring_lines(node: ast.AST) -> int:
    """Count lines in a node's docstring."""
    if not _has_docstring(node):
        return 0
    val = node.body[0].value
    return val.value.count("\n") + 1


def _decorator_names(node: ast.AST) -> list[str]:
    """Extract decorator names from a function/class node."""
    decorators = []
    for dec in getattr(node, "decorator_list", []):
        if isinstance(dec, ast.Name):
            decorators.append(dec.id)
        elif isinstance(dec, ast.Attribute):
            decorators.append(f"{_attr_chain(dec)}")
        elif isinstance(dec, ast.Call):
            func = dec.func
            if isinstance(func, ast.Name):
                decorators.append(func.id)
            elif isinstance(func, ast.Attribute):
                decorators.append(_attr_chain(func))
    return decorators


def _attr_chain(node: ast.Attribute) -> str:
    """Reconstruct dotted name from Attribute node chain."""
    parts = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def _count_args(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Count the number of arguments (excluding self/cls)."""
    args = node.args
    total = len(args.args) + len(args.posonlyargs) + len(args.kwonlyargs)
    if args.vararg:
        total += 1
    if args.kwarg:
        total += 1
    # Subtract self/cls
    if args.args and args.args[0].arg in ("self", "cls"):
        total -= 1
    return total


def _has_return_annotation(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check if a function has a return type annotation."""
    return node.returns is not None


# ═══════════════════════════════════════════════════════════════════
#  Core: parse a single file
# ═══════════════════════════════════════════════════════════════════


def _parse_python_file(
    path: Path,
    project_root: Path | None = None,
    project_prefix: str = "src",
) -> FileAnalysis:
    """Parse a single Python file and extract imports, symbols, and metrics.

    Args:
        path: Absolute path to the .py file.
        project_root: Project root for computing relative paths and
                      detecting internal imports.
        project_prefix: Top-level source package (e.g., "src") used to
                        identify internal imports.
    """
    rel_path = str(path.relative_to(project_root)) if project_root else str(path)
    result = FileAnalysis(path=rel_path, language="python", file_type="source")

    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        result.parse_error = str(e)
        return result

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        result.parse_error = f"SyntaxError: {e.msg} (line {e.lineno})"
        # Still compute basic line metrics
        lines = source.splitlines()
        result.metrics.total_lines = len(lines)
        result.metrics.blank_lines = sum(1 for l in lines if not l.strip())
        result.metrics.comment_lines = sum(
            1 for l in lines if l.strip().startswith("#")
        )
        result.metrics.code_lines = (
            result.metrics.total_lines
            - result.metrics.blank_lines
            - result.metrics.comment_lines
        )
        return result

    stdlib = _get_stdlib_modules()
    lines = source.splitlines()

    # ── Imports ─────────────────────────────────────────────
    imports: list[ImportInfo] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name
                imp = ImportInfo(
                    module=mod,
                    names=[alias.asname or alias.name.split(".")[-1]],
                    alias=alias.asname,
                    is_from=False,
                    lineno=node.lineno,
                    is_internal=mod.startswith(project_prefix + ".") or mod == project_prefix,
                    is_stdlib=mod.split(".")[0] in stdlib,
                )
                imports.append(imp)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            # Handle relative imports
            if node.level > 0:
                # Relative import — always internal
                mod = f"{'.' * node.level}{mod}"
                is_internal = True
            else:
                is_internal = mod.startswith(project_prefix + ".") or mod == project_prefix
            names = [alias.name for alias in node.names]
            imp = ImportInfo(
                module=mod,
                names=names,
                is_from=True,
                lineno=node.lineno,
                is_internal=is_internal,
                is_stdlib=mod.lstrip(".").split(".")[0] in stdlib if mod else False,
                is_relative=node.level > 0,
            )
            imports.append(imp)

    # ── Symbols ─────────────────────────────────────────────
    symbols: list[SymbolInfo] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function"
            end = getattr(node, "end_lineno", node.lineno)
            body_lines = max(0, end - node.lineno)
            sym = SymbolInfo(
                name=node.name,
                kind=kind,
                lineno=node.lineno,
                end_lineno=end,
                decorators=_decorator_names(node),
                is_public=not node.name.startswith("_"),
                has_docstring=_has_docstring(node),
                num_args=_count_args(node),
                body_lines=body_lines,
                max_nesting=_nesting_depth(node),
            )
            symbols.append(sym)
        elif isinstance(node, ast.ClassDef):
            end = getattr(node, "end_lineno", node.lineno)
            methods = []
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append(child.name)
            sym = SymbolInfo(
                name=node.name,
                kind="class",
                lineno=node.lineno,
                end_lineno=end,
                decorators=_decorator_names(node),
                is_public=not node.name.startswith("_"),
                has_docstring=_has_docstring(node),
                body_lines=max(0, end - node.lineno),
                methods=methods,
            )
            symbols.append(sym)

    # ── Metrics ─────────────────────────────────────────────
    total = len(lines)
    blank = sum(1 for l in lines if not l.strip())
    comment = sum(1 for l in lines if l.strip().startswith("#"))

    # Count docstring lines across all functions/classes + module docstring
    ds_lines = 0
    if _has_docstring(tree):
        ds_lines += _count_docstring_lines(tree)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            ds_lines += _count_docstring_lines(node)

    # Function metrics
    func_nodes = [
        s for s in symbols if s.kind in ("function", "async_function")
    ]
    func_lengths = [s.body_lines for s in func_nodes]
    avg_func_len = sum(func_lengths) / len(func_lengths) if func_lengths else 0.0
    max_func_len = max(func_lengths) if func_lengths else 0
    max_nesting = max((s.max_nesting for s in func_nodes), default=0)

    # Type hint coverage
    funcs_with_hints = sum(1 for node in ast.walk(tree)
                          if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                          and _has_return_annotation(node))
    total_funcs = sum(1 for node in ast.walk(tree)
                      if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)))
    hint_ratio = funcs_with_hints / total_funcs if total_funcs > 0 else 0.0

    # Main guard
    has_main = any(
        isinstance(node, ast.If) and _is_main_guard(node)
        for node in ast.iter_child_nodes(tree)
    )

    result.imports = imports
    result.symbols = symbols
    result.metrics = FileMetrics(
        total_lines=total,
        code_lines=total - blank - comment,
        blank_lines=blank,
        comment_lines=comment,
        docstring_lines=ds_lines,
        avg_function_length=avg_func_len,
        max_function_length=max_func_len,
        max_nesting_depth=max_nesting,
        import_count=len(imports),
        function_count=len(func_nodes),
        class_count=sum(1 for s in symbols if s.kind == "class"),
        has_main_guard=has_main,
        has_type_hints=hint_ratio,
    )
    return result


def _is_main_guard(node: ast.If) -> bool:
    """Check if an If node is `if __name__ == '__main__':`."""
    try:
        test = node.test
        if isinstance(test, ast.Compare):
            left = test.left
            if isinstance(left, ast.Name) and left.id == "__name__":
                if test.ops and isinstance(test.ops[0], ast.Eq):
                    comp = test.comparators[0]
                    if isinstance(comp, ast.Constant) and comp.value == "__main__":
                        return True
    except (AttributeError, IndexError):
        pass
    return False


# ═══════════════════════════════════════════════════════════════════
#  PythonParser — BaseParser implementation
# ═══════════════════════════════════════════════════════════════════


class PythonParser(BaseParser):
    """Python AST parser — extracts imports, symbols, and code metrics.

    Uses stdlib ``ast`` for reliable, fast parsing. Never executes the code.
    Handles .py, .pyw, and .pyi files.
    """

    @property
    def language(self) -> str:
        return "python"

    def extensions(self) -> set[str]:
        return {"py", "pyw", "pyi"}

    def parse_file(
        self,
        path: Path,
        project_root: Path | None = None,
        project_prefix: str = "src",
    ) -> FileAnalysis:
        """Parse a single Python file via AST."""
        return _parse_python_file(path, project_root, project_prefix)


# ═══════════════════════════════════════════════════════════════════
#  Backward-compat module-level functions
#
#  l2_quality.py and l2_structure.py import these directly:
#      from src.core.services.audit.parsers.python_parser import parse_tree
#  They will be migrated to use the registry in a later step.
# ═══════════════════════════════════════════════════════════════════

_python_parser = PythonParser()


def parse_file(
    path: Path,
    project_root: Path | None = None,
    project_prefix: str = "src",
) -> FileAnalysis:
    """Backward-compat wrapper — delegates to _parse_python_file."""
    return _parse_python_file(path, project_root, project_prefix)


def parse_tree(
    project_root: Path,
    *,
    project_prefix: str = "src",
    exclude_patterns: tuple[str, ...] = (
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
        ".git",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        "build",
        "dist",
        ".eggs",
    ),
    max_files: int = 0,
) -> dict[str, FileAnalysis]:
    """Parse all Python files under project_root.

    Backward-compat wrapper. Will be replaced by registry.parse_tree()
    in a later step.

    Args:
        project_root: Root directory to scan.
        project_prefix: Top-level source package for internal import detection.
        exclude_patterns: Directory names to skip.
        max_files: Ignored — kept for API compat. No cap applied.

    Returns:
        dict mapping relative path → FileAnalysis.
    """
    results: dict[str, FileAnalysis] = {}

    for py_file in sorted(project_root.rglob("*.py")):
        # Skip excluded directories
        parts = py_file.relative_to(project_root).parts
        if any(exc in parts for exc in exclude_patterns):
            continue

        analysis = _parse_python_file(py_file, project_root, project_prefix)
        results[analysis.path] = analysis

    return results


# ═══════════════════════════════════════════════════════════════════
#  Registry self-registration
# ═══════════════════════════════════════════════════════════════════


def _register():
    """Register PythonParser with the module-level registry."""
    from src.core.services.audit.parsers import registry
    registry.register(_python_parser)


_register()
