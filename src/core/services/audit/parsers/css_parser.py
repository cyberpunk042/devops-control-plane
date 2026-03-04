"""
CSS / SCSS / SASS / Less parser — regex-based.

Extracts stylesheet-specific metrics:
    - Selector and rule counts
    - Custom property (CSS variable) definitions and usage
    - @import / @use / @forward statements
    - @media query counts
    - @keyframes animation definitions
    - Nesting depth (SCSS/SASS/Less native nesting, CSS nesting)
    - Comment detection (/* */ and //)

Registered extensions:
    .css             → language="css"
    .scss            → language="scss"
    .sass            → language="sass"
    .less            → language="less"
    .styl            → language="stylus"

Consumers: ParserRegistry → l2_quality (_rubrics "css"), l2_structure
"""

from __future__ import annotations

import re
from pathlib import Path

from src.core.services.audit.parsers._base import (
    BaseParser,
    FileAnalysis,
    FileMetrics,
    ImportInfo,
)

# ═══════════════════════════════════════════════════════════════════
#  Extension → language mapping
# ═══════════════════════════════════════════════════════════════════

_EXT_LANG: dict[str, str] = {
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".styl": "stylus",
}

# ═══════════════════════════════════════════════════════════════════
#  Regex patterns
# ═══════════════════════════════════════════════════════════════════

# Rule blocks: selector { ... }
# Matches lines that contain a selector followed by {
_RE_RULE_OPEN = re.compile(
    r"""^[ \t]*"""
    r"""(?![\s*/])"""          # not a comment or blank
    r"""(?!@)"""               # not an @-rule (handled separately)
    r"""[^{}]+\{""",
    re.MULTILINE,
)

# @-rules
_RE_IMPORT = re.compile(
    r"""^[ \t]*@(?:import|use|forward)\s+"""
    r"""(?:url\s*\()?\s*['"]?([^'"\s;)]+)""",
    re.MULTILINE,
)

_RE_MEDIA = re.compile(r"^[ \t]*@media\b", re.MULTILINE)
_RE_KEYFRAMES = re.compile(r"^[ \t]*@keyframes\s+(\w[\w-]*)", re.MULTILINE)
_RE_FONT_FACE = re.compile(r"^[ \t]*@font-face\b", re.MULTILINE)
_RE_SUPPORTS = re.compile(r"^[ \t]*@supports\b", re.MULTILINE)
_RE_LAYER = re.compile(r"^[ \t]*@layer\b", re.MULTILINE)
_RE_CONTAINER = re.compile(r"^[ \t]*@container\b", re.MULTILINE)

# Custom properties (CSS variables)
_RE_VAR_DEF = re.compile(r"--[\w-]+\s*:")           # definition: --color: value
_RE_VAR_USE = re.compile(r"var\s*\(\s*--[\w-]+")    # usage: var(--color)

# SCSS/Less specific
_RE_SCSS_VAR_DEF = re.compile(r"^\s*\$[\w-]+\s*:", re.MULTILINE)  # $var: value
_RE_LESS_VAR_DEF = re.compile(r"^\s*@[\w-]+\s*:", re.MULTILINE)   # @var: value (Less)
_RE_MIXIN_DEF = re.compile(r"^[ \t]*@mixin\s+([\w-]+)", re.MULTILINE)
_RE_MIXIN_INCLUDE = re.compile(r"@include\s+([\w-]+)", re.MULTILINE)
_RE_SCSS_EXTEND = re.compile(r"@extend\s+([.%][\w-]+)")
_RE_SCSS_FUNCTION = re.compile(r"^[ \t]*@function\s+([\w-]+)", re.MULTILINE)
_RE_SCSS_PLACEHOLDER = re.compile(r"^[ \t]*%[\w-]+\s*\{", re.MULTILINE)

# Selectors — count distinct selectors (rough)
_RE_SELECTOR = re.compile(
    r"""^[ \t]*"""
    r"""([.#\w\[\]:&>~+*,@-][\s\S]*?)"""
    r"""\s*\{""",
    re.MULTILINE,
)

# Comments
_RE_BLOCK_COMMENT = re.compile(r"/\*[\s\S]*?\*/")
_RE_LINE_COMMENT = re.compile(r"^[ \t]*//", re.MULTILINE)  # SCSS/Less only

# !important usage
_RE_IMPORTANT = re.compile(r"!\s*important\b", re.IGNORECASE)

# ID selectors (specificity concern)
_RE_ID_SELECTOR = re.compile(r"#[\w-]+")

# Vendor prefixes
_RE_VENDOR_PREFIX = re.compile(r"-(?:webkit|moz|ms|o)-\w+")


# ═══════════════════════════════════════════════════════════════════
#  Parser implementation
# ═══════════════════════════════════════════════════════════════════


class CSSParser(BaseParser):
    """Parser for CSS, SCSS, SASS, Less, and Stylus files.

    Extracts:
    - Rule/selector counts
    - Custom property definitions and usage
    - @import/@use/@forward statements
    - @media, @keyframes, @font-face counts
    - SCSS/Less: mixin definitions, includes, variables, functions
    - Nesting depth analysis
    - Comment detection
    """

    @property
    def language(self) -> str:
        return "css"

    def extensions(self) -> set[str]:
        return set(_EXT_LANG.keys())

    def parse_file(
        self,
        file_path: Path,
        project_root: Path | None = None,
        project_prefix: str = "src",
    ) -> FileAnalysis:
        """Parse a stylesheet file into the universal FileAnalysis model."""
        rel_path = (
            str(file_path.relative_to(project_root))
            if project_root
            else str(file_path)
        )
        ext = file_path.suffix.lower()
        lang = _EXT_LANG.get(ext, "css")
        is_preprocessor = lang in ("scss", "sass", "less", "stylus")

        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return FileAnalysis(
                path=rel_path,
                language=lang,
                file_type="style",
                parse_error=str(exc),
            )

        lines = source.splitlines()
        total_lines = len(lines)

        # ── Imports ──────────────────────────────────────────
        imports = self._extract_imports(source)

        # ── Metrics ──────────────────────────────────────────
        metrics, lang_metrics = self._compute_metrics(
            source, lines, imports, is_preprocessor, lang,
        )

        return FileAnalysis(
            path=rel_path,
            language=lang,
            file_type="style",
            imports=imports,
            metrics=metrics,
            language_metrics=lang_metrics,
        )

    # ── Import extraction ─────────────────────────────────────

    def _extract_imports(self, source: str) -> list[ImportInfo]:
        """Extract @import, @use, @forward statements."""
        imports: list[ImportInfo] = []

        for m in _RE_IMPORT.finditer(source):
            module = m.group(1).strip("'\"")
            lineno = source[:m.start()].count("\n") + 1

            # Determine if internal
            is_internal = module.startswith(("./", "../"))
            # CSS @import of URLs is external
            is_url = module.startswith(("http://", "https://", "//"))

            imports.append(ImportInfo(
                module=module,
                names=[],
                is_from=False,
                lineno=lineno,
                is_internal=is_internal and not is_url,
                is_stdlib=False,
                is_relative=module.startswith("."),
            ))

        return imports

    # ── Metrics computation ───────────────────────────────────

    def _compute_metrics(
        self,
        source: str,
        lines: list[str],
        imports: list[ImportInfo],
        is_preprocessor: bool,
        lang: str,
    ) -> tuple[FileMetrics, dict]:
        """Compute file-level metrics and language-specific data."""
        total_lines = len(lines)

        # ── Comment detection ─────────────────────────────────
        block_comments = _RE_BLOCK_COMMENT.findall(source)
        comment_lines = sum(c.count("\n") + 1 for c in block_comments)

        # SCSS/Less line comments
        if is_preprocessor:
            comment_lines += len(_RE_LINE_COMMENT.findall(source))

        blank_lines = sum(1 for line in lines if not line.strip())
        code_lines = max(0, total_lines - blank_lines - comment_lines)

        # ── Rule / selector counts ────────────────────────────
        rule_count = len(_RE_RULE_OPEN.findall(source))

        # ── @-rule counts ─────────────────────────────────────
        media_count = len(_RE_MEDIA.findall(source))
        keyframe_defs = _RE_KEYFRAMES.findall(source)
        font_face_count = len(_RE_FONT_FACE.findall(source))
        supports_count = len(_RE_SUPPORTS.findall(source))
        layer_count = len(_RE_LAYER.findall(source))
        container_count = len(_RE_CONTAINER.findall(source))

        # ── CSS custom properties ─────────────────────────────
        var_defs = len(_RE_VAR_DEF.findall(source))
        var_uses = len(_RE_VAR_USE.findall(source))

        # ── Specificity concerns ──────────────────────────────
        important_count = len(_RE_IMPORTANT.findall(source))
        id_selector_count = len(_RE_ID_SELECTOR.findall(source))
        vendor_prefix_count = len(_RE_VENDOR_PREFIX.findall(source))

        # ── Nesting depth ─────────────────────────────────────
        max_nesting = 0
        current_depth = 0
        for line in lines:
            for ch in line:
                if ch == "{":
                    current_depth += 1
                    if current_depth > max_nesting:
                        max_nesting = current_depth
                elif ch == "}":
                    current_depth = max(0, current_depth - 1)

        # ── Preprocessor-specific ─────────────────────────────
        mixin_defs: list[str] = []
        mixin_includes: list[str] = []
        scss_var_count = 0
        function_count = 0
        extend_count = 0
        placeholder_count = 0

        if is_preprocessor:
            mixin_defs = _RE_MIXIN_DEF.findall(source)
            mixin_includes = _RE_MIXIN_INCLUDE.findall(source)
            scss_var_count = len(_RE_SCSS_VAR_DEF.findall(source))
            if lang == "less":
                scss_var_count = len(_RE_LESS_VAR_DEF.findall(source))
            function_count = len(_RE_SCSS_FUNCTION.findall(source))
            extend_count = len(_RE_SCSS_EXTEND.findall(source))
            placeholder_count = len(_RE_SCSS_PLACEHOLDER.findall(source))

        # ── Build metrics ─────────────────────────────────────
        metrics = FileMetrics(
            total_lines=total_lines,
            code_lines=code_lines,
            blank_lines=blank_lines,
            comment_lines=comment_lines,
            import_count=len(imports),
            function_count=function_count,  # SCSS @function count
            max_nesting_depth=max_nesting,
        )

        lang_metrics = {
            "type": lang,
            "rule_count": rule_count,
            "media_query_count": media_count,
            "keyframe_count": len(keyframe_defs),
            "keyframe_names": keyframe_defs[:20],  # Cap for sanity
            "font_face_count": font_face_count,
            "supports_count": supports_count,
            "layer_count": layer_count,
            "container_query_count": container_count,
            "custom_property_defs": var_defs,
            "custom_property_uses": var_uses,
            "important_count": important_count,
            "id_selector_count": id_selector_count,
            "vendor_prefix_count": vendor_prefix_count,
            "max_nesting": max_nesting,
        }

        if is_preprocessor:
            lang_metrics.update({
                "mixin_def_count": len(mixin_defs),
                "mixin_include_count": len(mixin_includes),
                "variable_count": scss_var_count,
                "function_count": function_count,
                "extend_count": extend_count,
                "placeholder_count": placeholder_count,
            })

        return metrics, lang_metrics


# ═══════════════════════════════════════════════════════════════════
#  Registry self-registration
# ═══════════════════════════════════════════════════════════════════

_css_parser = CSSParser()


def _register():
    """Register CSSParser for all style extensions."""
    from src.core.services.audit.parsers import registry
    registry.register(_css_parser)


_register()
