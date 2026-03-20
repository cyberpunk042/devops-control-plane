"""Abstract language backend interface.

Every language backend implements this interface.
The detection engine calls these methods — it never does
language-specific operations itself.
"""

from __future__ import annotations

import ast as _unused_ast  # noqa: F401 — just for type reference
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterator


class LanguageBackend(ABC):
    """Abstract interface for language-specific operations."""

    @property
    @abstractmethod
    def language_id(self) -> str:
        """Unique language identifier: 'python', 'javascript', etc."""

    @property
    @abstractmethod
    def file_extensions(self) -> list[str]:
        """Source file extensions: ['.py'], ['.js', '.jsx'], etc."""

    # ── Parsing ──────────────────────────────────────────────────

    @abstractmethod
    def parse_file(self, path: Path) -> Any:
        """Parse a source file into an AST.

        Returns the language-specific AST root node.
        Raises ParseError if the file can't be parsed.
        """

    @abstractmethod
    def parse_source(self, source: str, filename: str = "<string>") -> Any:
        """Parse source code string into an AST."""

    @abstractmethod
    def walk_ast(self, tree: Any) -> Iterator[Any]:
        """Depth-first walk of all AST nodes."""

    @abstractmethod
    def node_type_name(self, node: Any) -> str:
        """Get the type name of an AST node: 'ImportFrom', 'Match', etc."""

    @abstractmethod
    def node_location(self, node: Any) -> tuple[int, int]:
        """Get (line, column) of a node. Lines are 1-based."""

    @abstractmethod
    def get_source_line(self, source: str, line: int) -> str:
        """Get a specific line from source text. Lines are 1-based."""

    # ── Matching ─────────────────────────────────────────────────

    @abstractmethod
    def node_matches(self, node: Any, ast_type: str, match: dict) -> bool:
        """Check if a node matches an AST type and attribute constraints.

        Args:
            node: The AST node to check.
            ast_type: Expected node type name.
            match: Dict of attribute constraints to check.

        Returns:
            True if the node matches all constraints.
        """

    @abstractmethod
    def get_node_context(self, node: Any, tree: Any) -> str:
        """Determine the context of a node in the AST.

        Returns one of:
            'module_level', 'function_body', 'class_body',
            'annotation', 'runtime', 'type_checking_block',
            'try_block', 'except_block', 'version_gate', 'any'
        """

    @abstractmethod
    def has_future_annotations(self, tree: Any) -> bool:
        """Check if the file has 'from __future__ import annotations'.

        Python-specific but part of the interface for annotation
        context detection. Other languages return False.
        """

    # ── Import resolution ────────────────────────────────────────

    @abstractmethod
    def extract_imports(self, tree: Any, file_path: Path) -> list[dict]:
        """Extract all import statements from an AST.

        Returns list of dicts with:
            module: str — the imported module/package
            names: list[str] — specific names imported
            line: int — line number
            import_type: str — 'import', 'from_import', 'from_import_star', 'dynamic'
            is_conditional: bool — inside try/except
            is_type_only: bool — inside TYPE_CHECKING
        """

    @abstractmethod
    def resolve_import_path(
        self,
        module_name: str,
        source_file: Path,
        project_root: Path,
    ) -> Path | None:
        """Resolve an import to a file path.

        Returns None if the import is stdlib, third-party, or unresolvable.
        Only returns paths for project-internal imports.
        """

    # ── Verification ─────────────────────────────────────────────

    @abstractmethod
    def check_syntax(self, file_path: Path) -> tuple[bool, str]:
        """Verify file has valid syntax.

        Returns (passed, error_message).
        """

    @abstractmethod
    def check_importable(self, file_path: Path, project_root: Path) -> tuple[bool, str]:
        """Verify file can be imported/compiled.

        Returns (passed, error_message).
        """


class BackendRegistry:
    """Registry of available language backends."""

    _backends: dict[str, type[LanguageBackend]] = {}

    @classmethod
    def register(cls, backend_class: type[LanguageBackend]) -> None:
        """Register a backend class."""
        lang_id = backend_class.language_id.fget(None)  # type: ignore[union-attr]
        # Instantiate to get language_id properly
        try:
            instance = backend_class()
            cls._backends[instance.language_id] = backend_class
        except Exception:
            pass

    @classmethod
    def get(cls, language: str) -> LanguageBackend | None:
        """Get a backend instance for a language."""
        backend_class = cls._backends.get(language)
        if backend_class:
            return backend_class()
        return None

    @classmethod
    def supported_languages(cls) -> list[str]:
        """List all supported language IDs."""
        return sorted(cls._backends.keys())

    @classmethod
    def for_extension(cls, extension: str) -> LanguageBackend | None:
        """Find backend by file extension."""
        for backend_class in cls._backends.values():
            instance = backend_class()
            if extension in instance.file_extensions:
                return instance
        return None
