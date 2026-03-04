"""
Parsers package — language-specific source code analyzers.

Each parser extracts:
  - imports (internal + external)
  - symbols (functions, classes, constants)
  - code metrics (lines, docstrings, nesting depth, etc.)

Architecture:
  - _base.py        — universal data model (FileAnalysis, ImportInfo, etc.)
                       and BaseParser ABC
  - python_parser.py — Python AST parser (original, being migrated)
  - __init__.py      — ParserRegistry (this file)

Usage:
    from src.core.services.audit.parsers import registry
    analysis = registry.parse_file(some_path, project_root)
    all_analyses = registry.parse_tree(project_root)
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.core.services.audit.parsers._base import (
    BaseParser,
    FileAnalysis,
    FileMetrics,
    ImportInfo,
    SymbolInfo,
    SymbolLocation,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  Parser Registry
# ═══════════════════════════════════════════════════════════════════


class ParserRegistry:
    """Routes files to the correct language parser based on extension.

    Parsers register themselves via ``register(parser)``.  When
    ``parse_file()`` is called, the registry looks up the file's
    extension and delegates to the matching parser.  If no parser
    matches, it delegates to the fallback parser (if set).

    Usage:
        registry = ParserRegistry()
        registry.register(PythonParser())
        registry.set_fallback(FallbackParser())

        analysis = registry.parse_file(Path("src/server.py"), project_root)
    """

    def __init__(self) -> None:
        self._parsers: dict[str, BaseParser] = {}    # ext → parser
        self._fallback: BaseParser | None = None
        self._languages: dict[str, BaseParser] = {}  # lang → parser
        self._file_cache: dict[str, tuple[float, FileAnalysis]] = {}  # rel_path → (mtime, analysis)

    def register(self, parser: BaseParser) -> None:
        """Register a parser for all its declared extensions.

        If an extension is already registered, the new parser replaces it
        (last-write-wins). This is intentional — allows overriding defaults.
        """
        lang = parser.language
        exts = parser.extensions()

        for ext in exts:
            ext_clean = ext.lstrip(".")
            self._parsers[ext_clean] = parser

        self._languages[lang] = parser
        logger.debug(
            "Registered %s parser for extensions: %s",
            lang,
            ", ".join(sorted(exts)),
        )

    def set_fallback(self, parser: BaseParser) -> None:
        """Set the fallback parser for unrecognized extensions."""
        self._fallback = parser
        logger.debug("Set fallback parser: %s", parser.language)

    def get_parser(self, path: Path) -> BaseParser | None:
        """Get the parser for a file path, or None if no match.

        Checks extension-based registration first, then falls back.
        """
        ext = path.suffix.lstrip(".")
        return self._parsers.get(ext, self._fallback)

    def get_parser_for_language(self, language: str) -> BaseParser | None:
        """Get the parser for a language by name."""
        return self._languages.get(language)

    @property
    def registered_extensions(self) -> set[str]:
        """All extensions with a registered parser."""
        return set(self._parsers.keys())

    @property
    def registered_languages(self) -> list[str]:
        """All registered language names."""
        return sorted(self._languages.keys())

    @property
    def has_fallback(self) -> bool:
        """Whether a fallback parser is set."""
        return self._fallback is not None

    def parse_file(
        self,
        path: Path,
        project_root: Path | None = None,
        project_prefix: str = "src",
    ) -> FileAnalysis | None:
        """Parse a single file through the appropriate parser.

        Returns:
            FileAnalysis if a parser handled the file, None if no parser
            matched and no fallback is set.
        """
        parser = self.get_parser(path)
        if parser is None:
            return None
        return parser.parse_file(path, project_root, project_prefix)

    def parse_tree(
        self,
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
            ".agent",
            ".pages",
        ),
        use_cache: bool = True,
    ) -> dict[str, FileAnalysis]:
        """Parse all recognized files under project_root.

        Walks the directory tree, skipping excluded directories,
        and routes each file to the correct parser via extension.

        When ``use_cache`` is True (the default), only files whose
        mtime has changed since the last call are re-parsed.  Unchanged
        files are served from the per-file cache.

        Returns:
            dict mapping relative path → FileAnalysis.
        """
        results: dict[str, FileAnalysis] = {}
        cache_hits = 0
        cache_misses = 0
        seen_paths: set[str] = set()

        for file_path in sorted(project_root.rglob("*")):
            # Skip directories
            if file_path.is_dir():
                continue

            # Skip excluded directories
            parts = file_path.relative_to(project_root).parts
            if any(exc in parts for exc in exclude_patterns):
                continue

            # Find parser
            parser = self.get_parser(file_path)
            if parser is None:
                continue

            rel_path = str(file_path.relative_to(project_root))
            seen_paths.add(rel_path)

            # ── Per-file mtime cache check ──
            if use_cache:
                try:
                    mtime = file_path.stat().st_mtime
                except OSError:
                    mtime = 0.0

                cached = self._file_cache.get(rel_path)
                if cached is not None and cached[0] == mtime:
                    results[cached[1].path] = cached[1]
                    cache_hits += 1
                    continue

            # Parse the file
            analysis = parser.parse_file(file_path, project_root, project_prefix)
            results[analysis.path] = analysis
            cache_misses += 1

            # Update the cache
            if use_cache:
                self._file_cache[rel_path] = (mtime, analysis)

        # ── Evict deleted files from cache ──
        if use_cache:
            stale_keys = set(self._file_cache.keys()) - seen_paths
            for key in stale_keys:
                del self._file_cache[key]

        if cache_hits > 0 or cache_misses > 0:
            logger.debug(
                "parse_tree: %d cached, %d parsed, %d evicted",
                cache_hits, cache_misses, len(stale_keys) if use_cache else 0,
            )

        return results

    def bust_cache(self) -> int:
        """Clear the per-file parse cache. Returns number of entries cleared."""
        n = len(self._file_cache)
        self._file_cache.clear()
        return n

    def __repr__(self) -> str:
        langs = ", ".join(self.registered_languages) or "(none)"
        fallback = f", fallback={self._fallback.language}" if self._fallback else ""
        return f"ParserRegistry(languages=[{langs}]{fallback})"


# ═══════════════════════════════════════════════════════════════════
#  Module-level singleton registry
# ═══════════════════════════════════════════════════════════════════

registry = ParserRegistry()
"""Module-level singleton. Parsers register themselves at import time."""


# ═══════════════════════════════════════════════════════════════════
#  Public re-exports
# ═══════════════════════════════════════════════════════════════════

__all__ = [
    "BaseParser",
    "CFamilyParser",
    "ConfigParser",
    "CSSParser",
    "FallbackParser",
    "FileAnalysis",
    "FileMetrics",
    "GoParser",
    "ImportInfo",
    "JavaScriptParser",
    "JVMParser",
    "MultiLangParser",
    "ParserRegistry",
    "PythonParser",
    "RustParser",
    "SymbolInfo",
    "SymbolLocation",
    "TemplateParser",
    "registry",
]


# ═══════════════════════════════════════════════════════════════════
#  Auto-registration: import parsers so their _register() runs
# ═══════════════════════════════════════════════════════════════════

from src.core.services.audit.parsers._fallback import FallbackParser  # noqa: E402, F811
from src.core.services.audit.parsers.c_parser import CFamilyParser  # noqa: E402, F811
from src.core.services.audit.parsers.config_parser import ConfigParser  # noqa: E402, F811
from src.core.services.audit.parsers.css_parser import CSSParser  # noqa: E402, F811
from src.core.services.audit.parsers.go_parser import GoParser  # noqa: E402, F811
from src.core.services.audit.parsers.js_parser import JavaScriptParser  # noqa: E402, F811
from src.core.services.audit.parsers.jvm_parser import JVMParser  # noqa: E402, F811
from src.core.services.audit.parsers.multilang_parser import MultiLangParser  # noqa: E402, F811
from src.core.services.audit.parsers.rust_parser import RustParser  # noqa: E402, F811
from src.core.services.audit.parsers.template_parser import TemplateParser  # noqa: E402, F811
from src.core.services.audit.parsers.python_parser import PythonParser  # noqa: E402, F811

