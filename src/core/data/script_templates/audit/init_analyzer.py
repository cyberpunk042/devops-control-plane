"""Init-file analyzer — detect logic leaks in module index files.

This module provides:
- Universal data models for module-index file analysis
- An InitAnalyzer protocol for pluggable language support
- A PythonInitAnalyzer for __init__.py files

Design principle: OBSERVE, DON'T JUDGE.
"This __init__.py has 22 functions" is a fact.
Whether that's acceptable is a human decision.

Multi-language ready: the InitAnalyzer protocol works for any language.
Python has __init__.py, JavaScript has index.js/index.ts,
Go has package-level files, etc.  Each gets its own analyzer.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


# ═══════════════════════════════════════════════════════════════════
#  Universal Data Models
# ═══════════════════════════════════════════════════════════════════


@dataclass
class InitFunctionInfo:
    """A function defined in a module-index file."""

    name: str
    lineno: int
    end_lineno: int
    body_lines: int
    has_docstring: bool = False
    is_trivial: bool = False    # Single return/pass/raise = trivial


@dataclass
class InitClassInfo:
    """A class defined in a module-index file."""

    name: str
    lineno: int
    end_lineno: int
    body_lines: int
    method_count: int = 0


@dataclass
class InitFileAnalysis:
    """Facts about a single module-index file.

    Every field is an observation — no field implies judgment.
    "22 functions in __init__.py" is a fact.
    """

    # ── Identity ──
    file_path: str                     # Relative path
    language: str                      # "python" | "javascript" | etc.

    # ── Size metrics ──
    total_lines: int = 0
    code_lines: int = 0                # Excluding blank + pure comments

    # ── Observations ──
    functions: list[InitFunctionInfo] = field(default_factory=list)
    classes: list[InitClassInfo] = field(default_factory=list)
    import_count: int = 0              # Number of import statements
    has_all_export: bool = False       # Has __all__ / module.exports definition
    has_complex_logic: bool = False    # Loops, non-trivial conditionals

    @property
    def function_count(self) -> int:
        return len(self.functions)

    @property
    def class_count(self) -> int:
        return len(self.classes)

    @property
    def total_function_lines(self) -> int:
        return sum(f.body_lines for f in self.functions)

    @property
    def total_class_lines(self) -> int:
        return sum(c.body_lines for c in self.classes)

    @property
    def logic_lines(self) -> int:
        """Lines of non-import, non-docstring code defined in functions/classes."""
        return self.total_function_lines + self.total_class_lines

    @property
    def is_clean(self) -> bool:
        """True if this init has no functions or classes (only imports/exports)."""
        return self.function_count == 0 and self.class_count == 0


@dataclass
class InitAuditResult:
    """Complete module-index audit result — facts only."""

    language: str
    files: list[InitFileAnalysis] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        return len(self.files)

    @property
    def clean_files(self) -> int:
        return sum(1 for f in self.files if f.is_clean)

    @property
    def files_with_logic(self) -> int:
        return sum(1 for f in self.files if not f.is_clean)

    @property
    def total_leaked_functions(self) -> int:
        return sum(f.function_count for f in self.files)

    @property
    def total_leaked_classes(self) -> int:
        return sum(f.class_count for f in self.files)


# ═══════════════════════════════════════════════════════════════════
#  Protocol
# ═══════════════════════════════════════════════════════════════════


@runtime_checkable
class InitAnalyzer(Protocol):
    """Protocol for language-specific module-index analyzers."""

    @property
    def language(self) -> str:
        """Language name."""
        ...

    @property
    def index_filename(self) -> str:
        """The index filename for this language (e.g., '__init__.py')."""
        ...

    def analyze(self, root: Path, scope: str | None = None) -> InitAuditResult:
        """Analyze all module-index files under root.

        Args:
            root: Project root directory.
            scope: Optional scope to limit search (e.g., "core/services").

        Returns:
            InitAuditResult with all analyzed files.
        """
        ...


# ═══════════════════════════════════════════════════════════════════
#  Python __init__.py Analyzer
# ═══════════════════════════════════════════════════════════════════


class PythonInitAnalyzer:
    """Analyze Python __init__.py files for logic leaks.

    What is considered "clean" for __init__.py:
    - Module docstring
    - Import statements (including re-exports: from .x import Y)
    - __all__ assignment
    - Simple constants (ALL_CAPS = literal)
    - TYPE_CHECKING blocks
    - Blueprint / click.group definitions (framework patterns)

    What is observed as "logic":
    - Function definitions (except trivial one-liners)
    - Class definitions
    - Loops, complex conditionals
    """

    @property
    def language(self) -> str:
        return "python"

    @property
    def index_filename(self) -> str:
        return "__init__.py"

    def analyze(
        self,
        root: Path,
        scope: str | None = None,
        *,
        source_dir: str = "src",
    ) -> InitAuditResult:
        """Analyze all __init__.py files under root/source_dir.

        Args:
            root: Project root.
            scope: Optional directory scope (e.g., "core/services").
            source_dir: Source directory relative to root.

        Returns:
            InitAuditResult with all analyzed init files.
        """
        search_dir = root / source_dir
        if scope:
            search_dir = search_dir / scope.replace(".", "/")

        if not search_dir.is_dir():
            return InitAuditResult(language="python")

        files: list[InitFileAnalysis] = []

        for init_file in sorted(search_dir.rglob("__init__.py")):
            if "__pycache__" in str(init_file):
                continue

            analysis = self._analyze_file(init_file, root)
            if analysis is not None:
                files.append(analysis)

        return InitAuditResult(language="python", files=files)

    def _analyze_file(
        self,
        filepath: Path,
        project_root: Path,
    ) -> InitFileAnalysis | None:
        """Analyze a single __init__.py file."""
        try:
            source = filepath.read_text()
            tree = ast.parse(source, filename=str(filepath))
        except (OSError, SyntaxError):
            return None

        rel_path = str(filepath.relative_to(project_root))
        lines = source.splitlines()
        total_lines = len(lines)
        code_lines = sum(
            1 for l in lines
            if l.strip() and not l.strip().startswith("#")
        )

        analysis = InitFileAnalysis(
            file_path=rel_path,
            language="python",
            total_lines=total_lines,
            code_lines=code_lines,
        )

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef):
                analysis.functions.append(self._analyze_function(node))
            elif isinstance(node, ast.ClassDef):
                analysis.classes.append(self._analyze_class(node))
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                analysis.import_count += 1
            elif isinstance(node, ast.Assign):
                # Check for __all__
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        analysis.has_all_export = True
            elif isinstance(node, (ast.For, ast.While)):
                analysis.has_complex_logic = True
            elif isinstance(node, ast.If):
                # TYPE_CHECKING is fine
                if isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
                    continue
                # Simple import guards (try: import x except ImportError) are fine
                analysis.has_complex_logic = True

        return analysis

    @staticmethod
    def _analyze_function(node: ast.FunctionDef) -> InitFunctionInfo:
        """Extract facts about a function defined in __init__.py."""
        body_lines = (node.end_lineno or node.lineno) - node.lineno

        # Check docstring
        has_docstring = (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        )

        # Check if trivial (single statement: return, pass, raise, or ...)
        real_body = node.body
        if has_docstring:
            real_body = node.body[1:]

        is_trivial = (
            len(real_body) <= 1
            and real_body
            and isinstance(real_body[0], (ast.Return, ast.Pass, ast.Raise, ast.Expr))
        )

        return InitFunctionInfo(
            name=node.name,
            lineno=node.lineno,
            end_lineno=node.end_lineno or node.lineno,
            body_lines=body_lines,
            has_docstring=has_docstring,
            is_trivial=is_trivial,
        )

    @staticmethod
    def _analyze_class(node: ast.ClassDef) -> InitClassInfo:
        """Extract facts about a class defined in __init__.py."""
        body_lines = (node.end_lineno or node.lineno) - node.lineno

        method_count = sum(
            1 for n in ast.iter_child_nodes(node)
            if isinstance(n, ast.FunctionDef)
        )

        return InitClassInfo(
            name=node.name,
            lineno=node.lineno,
            end_lineno=node.end_lineno or node.lineno,
            body_lines=body_lines,
            method_count=method_count,
        )
