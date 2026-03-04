"""
Fallback parser — generic line-counter for any unrecognized file type.

Handles ALL files that no specialized parser matches.  Provides:
  - Line counts (total, code, blank, comment)
  - Language detection by file extension
  - File type classification (source, config, template, etc.)
  - Comment line detection using per-language comment syntax

Does NOT provide:
  - Import extraction
  - Symbol extraction
  - Nesting analysis
  - Any language-specific metrics

This parser is registered as the registry fallback, ensuring that
every file in the project gets at least basic metrics.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.core.services.audit.parsers._base import (
    BaseParser,
    FileAnalysis,
    FileMetrics,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  Extension → Language mapping
# ═══════════════════════════════════════════════════════════════════

_EXTENSION_LANGUAGE: dict[str, str] = {
    # Source languages
    "py": "python", "pyw": "python", "pyi": "python",
    "js": "javascript", "mjs": "javascript", "cjs": "javascript", "jsx": "javascript",
    "ts": "typescript", "mts": "typescript", "cts": "typescript", "tsx": "typescript",
    "go": "go",
    "rs": "rust",
    "rb": "ruby", "rake": "ruby",
    "java": "java",
    "kt": "kotlin", "kts": "kotlin",
    "scala": "scala", "sc": "scala",
    "cs": "csharp",
    "fs": "fsharp", "fsx": "fsharp",
    "php": "php",
    "ex": "elixir", "exs": "elixir",
    "erl": "erlang", "hrl": "erlang",
    "swift": "swift",
    "c": "c", "h": "c",
    "cpp": "cpp", "hpp": "cpp", "cc": "cpp", "hh": "cpp", "cxx": "cpp", "hxx": "cpp",
    "zig": "zig",
    "lua": "lua",
    "hs": "haskell", "lhs": "haskell",
    "ml": "ocaml", "mli": "ocaml",
    "r": "r",
    "R": "r",
    "pl": "perl", "pm": "perl",
    "sh": "shell", "bash": "shell", "zsh": "shell", "fish": "shell",
    "ps1": "powershell", "psm1": "powershell",
    "dart": "dart",
    "v": "vlang",
    "nim": "nim",
    "cr": "crystal",
    "clj": "clojure", "cljs": "clojure", "cljc": "clojure",
    "proto": "protobuf",
    "wat": "wasm-text",

    # Config / Infrastructure
    "yml": "yaml", "yaml": "yaml",
    "json": "json", "jsonl": "json",
    "toml": "toml",
    "ini": "ini", "cfg": "ini",
    "xml": "xml",
    "tf": "hcl", "tfvars": "hcl",
    "sql": "sql",
    "graphql": "graphql", "gql": "graphql",
    "mk": "makefile",

    # Templates
    "html": "html",
    "htm": "html",
    "j2": "jinja2", "jinja": "jinja2", "jinja2": "jinja2",
    "erb": "erb",
    "ejs": "ejs",
    "hbs": "handlebars", "handlebars": "handlebars", "mustache": "mustache",
    "pug": "pug", "jade": "pug",
    "slim": "slim",
    "haml": "haml",
    "heex": "heex", "eex": "eex", "leex": "leex",
    "tmpl": "go-template", "gohtml": "go-template",
    "twig": "twig",
    "cshtml": "razor", "razor": "razor",
    "svelte": "svelte",
    "vue": "vue",
    "mdx": "mdx",

    # Styles
    "css": "css",
    "scss": "scss", "sass": "sass",
    "less": "less",
    "styl": "stylus",

    # Markup / Docs
    "md": "markdown", "markdown": "markdown",
    "rst": "restructuredtext",
    "adoc": "asciidoc",
    "tex": "latex",

    # Data
    "csv": "csv",
    "tsv": "tsv",
}

# Extensionless file name → language
_FILENAME_LANGUAGE: dict[str, str] = {
    "Dockerfile": "dockerfile",
    "Makefile": "makefile",
    "Gemfile": "ruby",
    "Rakefile": "ruby",
    "Vagrantfile": "ruby",
    "Procfile": "procfile",
    "Justfile": "justfile",
    ".gitignore": "gitignore",
    ".dockerignore": "dockerignore",
    ".editorconfig": "editorconfig",
    ".env": "dotenv",
    ".env.example": "dotenv",
}


# ═══════════════════════════════════════════════════════════════════
#  Extension → File type classification
# ═══════════════════════════════════════════════════════════════════

_EXTENSION_FILE_TYPE: dict[str, str] = {
    # Source
    "py": "source", "pyw": "source", "pyi": "source",
    "js": "source", "mjs": "source", "cjs": "source", "jsx": "source",
    "ts": "source", "mts": "source", "cts": "source", "tsx": "source",
    "go": "source", "rs": "source", "rb": "source", "rake": "source",
    "java": "source", "kt": "source", "kts": "source",
    "scala": "source", "sc": "source",
    "cs": "source", "fs": "source", "fsx": "source",
    "php": "source", "ex": "source", "exs": "source",
    "erl": "source", "hrl": "source",
    "swift": "source", "c": "source", "h": "source",
    "cpp": "source", "hpp": "source", "cc": "source", "hh": "source",
    "cxx": "source", "hxx": "source",
    "zig": "source", "lua": "source",
    "hs": "source", "lhs": "source",
    "ml": "source", "mli": "source",
    "r": "source", "R": "source",
    "pl": "source", "pm": "source",
    "sh": "source", "bash": "source", "zsh": "source", "fish": "source",
    "ps1": "source", "psm1": "source",
    "dart": "source", "v": "source", "nim": "source", "cr": "source",
    "clj": "source", "cljs": "source", "cljc": "source",
    "proto": "source", "wat": "source",

    # Config
    "yml": "config", "yaml": "config",
    "json": "config", "jsonl": "data",
    "toml": "config",
    "ini": "config", "cfg": "config",
    "xml": "config",
    "tf": "config", "tfvars": "config",

    # Templates
    "html": "template", "htm": "template",
    "j2": "template", "jinja": "template", "jinja2": "template",
    "erb": "template", "ejs": "template",
    "hbs": "template", "handlebars": "template", "mustache": "template",
    "pug": "template", "jade": "template",
    "slim": "template", "haml": "template",
    "heex": "template", "eex": "template", "leex": "template",
    "tmpl": "template", "gohtml": "template",
    "twig": "template",
    "cshtml": "template", "razor": "template",
    "svelte": "template", "vue": "template",
    "mdx": "template",

    # Styles
    "css": "style", "scss": "style", "sass": "style",
    "less": "style", "styl": "style",

    # Markup
    "md": "markup", "markdown": "markup",
    "rst": "markup", "adoc": "markup", "tex": "markup",

    # Data
    "csv": "data", "tsv": "data",
    "sql": "data", "graphql": "data", "gql": "data",

    # Build
    "mk": "build",
}

_FILENAME_FILE_TYPE: dict[str, str] = {
    "Dockerfile": "build",
    "Makefile": "build",
    "Gemfile": "config",
    "Rakefile": "build",
    "Vagrantfile": "config",
    "Procfile": "config",
    "Justfile": "build",
    ".gitignore": "config",
    ".dockerignore": "config",
    ".editorconfig": "config",
    ".env": "config",
    ".env.example": "config",
}


# ═══════════════════════════════════════════════════════════════════
#  Comment syntax per language
# ═══════════════════════════════════════════════════════════════════

# Maps language → tuple of (single-line comment prefix(es))
_COMMENT_PREFIXES: dict[str, tuple[str, ...]] = {
    # Hash-style
    "python": ("#",), "ruby": ("#",), "shell": ("#",), "perl": ("#",),
    "yaml": ("#",), "toml": ("#",), "ini": ("#", ";"),
    "makefile": ("#",), "dockerfile": ("#",),
    "r": ("#",), "elixir": ("#",), "crystal": ("#",), "nim": ("#",),
    "gitignore": ("#",), "dockerignore": ("#",), "editorconfig": ("#",),
    "dotenv": ("#",), "procfile": ("#",), "justfile": ("#",),

    # Double-slash style
    "javascript": ("//",), "typescript": ("//",),
    "go": ("//",), "rust": ("//",), "java": ("//",),
    "kotlin": ("//",), "scala": ("//",), "csharp": ("//",), "fsharp": ("//",),
    "swift": ("//",), "c": ("//",), "cpp": ("//",),
    "php": ("//", "#"),
    "dart": ("//",), "vlang": ("//",), "zig": ("//",),
    "protobuf": ("//",),

    # Double-dash style
    "sql": ("--",), "haskell": ("--",), "lua": ("--",),

    # Percent style
    "latex": ("%",), "erlang": ("%",),

    # Semicolon style
    "clojure": (";",), "wasm-text": (";;",),

    # XML-style (handled differently — not line-based)
    # "html", "xml", "svg" — skipped, block comments only

    # OCaml uses (* ... *) block comments — not line-based
    # "ocaml" — skipped

    # Template engines — usually have no comment concept of their own,
    # they embed the host language's comments
}


# ═══════════════════════════════════════════════════════════════════
#  Fallback Parser implementation
# ═══════════════════════════════════════════════════════════════════


def _detect_language(path: Path) -> str:
    """Detect language from file extension or name."""
    # Check by filename first (Dockerfile, Makefile, etc.)
    name = path.name
    if name in _FILENAME_LANGUAGE:
        return _FILENAME_LANGUAGE[name]

    # Check by extension
    ext = path.suffix.lstrip(".")
    if ext in _EXTENSION_LANGUAGE:
        return _EXTENSION_LANGUAGE[ext]

    return "unknown"


def _detect_file_type(path: Path) -> str:
    """Detect file type from file extension or name."""
    name = path.name
    if name in _FILENAME_FILE_TYPE:
        return _FILENAME_FILE_TYPE[name]

    ext = path.suffix.lstrip(".")
    if ext in _EXTENSION_FILE_TYPE:
        return _EXTENSION_FILE_TYPE[ext]

    return "source"


class FallbackParser(BaseParser):
    """Generic line-counter for any file type.

    Provides basic metrics (total lines, code lines, blank lines,
    comment lines) for files that don't have a specialized parser.
    Does NOT extract imports, symbols, or language-specific metrics.

    Handles:
      - Language detection by extension
      - File type classification by extension
      - Comment detection using language-appropriate prefixes
      - Graceful handling of binary files and encoding errors
    """

    @property
    def language(self) -> str:
        return "_fallback"

    def extensions(self) -> set[str]:
        # The fallback doesn't register for specific extensions —
        # it handles everything via registry.set_fallback().
        return set()

    def parse_file(
        self,
        path: Path,
        project_root: Path | None = None,
        project_prefix: str = "src",
    ) -> FileAnalysis:
        """Parse a file with generic line counting."""
        rel_path = str(path.relative_to(project_root)) if project_root else str(path)
        language = _detect_language(path)
        file_type = _detect_file_type(path)

        result = FileAnalysis(
            path=rel_path,
            language=language,
            file_type=file_type,
        )

        # Read the file
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            result.parse_error = str(e)
            return result
        except UnicodeDecodeError:
            result.parse_error = "Binary file (not UTF-8 decodable)"
            return result

        # Detect binary content (null bytes = likely binary)
        if "\x00" in source[:1024]:
            result.parse_error = "Binary file"
            result.metrics = FileMetrics(total_lines=0)
            return result

        lines = source.splitlines()
        total = len(lines)
        blank = sum(1 for line in lines if not line.strip())

        # Count comments using language-appropriate prefixes
        comment_prefixes = _COMMENT_PREFIXES.get(language, ())
        comment = 0
        if comment_prefixes:
            for line in lines:
                stripped = line.strip()
                if stripped and any(stripped.startswith(p) for p in comment_prefixes):
                    comment += 1

        code = total - blank - comment

        result.metrics = FileMetrics(
            total_lines=total,
            code_lines=max(0, code),
            blank_lines=blank,
            comment_lines=comment,
        )

        return result


# ═══════════════════════════════════════════════════════════════════
#  Public helpers for use by other parsers
# ═══════════════════════════════════════════════════════════════════

def detect_language(path: Path) -> str:
    """Public API: detect language from file path."""
    return _detect_language(path)


def detect_file_type(path: Path) -> str:
    """Public API: detect file type from file path."""
    return _detect_file_type(path)


# ═══════════════════════════════════════════════════════════════════
#  Registry self-registration (as fallback)
# ═══════════════════════════════════════════════════════════════════


_fallback_parser = FallbackParser()


def _register():
    """Register FallbackParser as the registry fallback."""
    from src.core.services.audit.parsers import registry
    registry.set_fallback(_fallback_parser)


_register()
