"""
Quality rubrics — per-language scoring dimensions and scorer functions.

Each language gets its own quality rubric: a set of weighted dimensions
that measure what matters FOR THAT LANGUAGE.  The universal scorer
function looks up the file's language, gets the rubric, evaluates each
dimension, and returns a weighted composite score.

This replaces the hardcoded 5-Python-dimension scorer in l2_quality.py.

Usage:
    from src.core.services.audit.parsers._rubrics import score_file
    result = score_file(analysis)
    # {"score": 7.8, "breakdown": {"documentation": 9.0, ...}, "rubric": "python"}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from src.core.services.audit.parsers._base import FileAnalysis


# ═══════════════════════════════════════════════════════════════════
#  QualityDimension — one axis of code quality
# ═══════════════════════════════════════════════════════════════════


@dataclass
class QualityDimension:
    """A single quality dimension within a language rubric.

    Each dimension has a scorer that takes a FileAnalysis and returns
    a score from 0.0 (worst) to 10.0 (best).
    """

    name: str                        # "docstrings", "nesting", etc.
    weight: float                    # Relative weight within rubric (sum should be ~1.0)
    description: str                 # Human-readable description
    scorer: Callable[[FileAnalysis], float] = field(repr=False, default=lambda _: 5.0)


# ═══════════════════════════════════════════════════════════════════
#  Universal scorer functions
#
#  These work with FileAnalysis.metrics — available from ANY parser,
#  including the fallback.  They form the backbone of scoring even
#  before specialized parsers exist.
# ═══════════════════════════════════════════════════════════════════


def _score_documentation(analysis: FileAnalysis) -> float:
    """Score documentation coverage: docstrings/doc comments on symbols.

    Works for all languages: ratio of symbols with has_docstring=True.
    If no symbols, returns 10.0 (no penalty for simple/config files).
    """
    funcs_and_classes = [
        s for s in analysis.symbols
        if s.kind in (
            "function", "async_function", "class", "struct",
            "trait", "interface", "enum", "module", "method",
        )
    ]
    if not funcs_and_classes:
        return 10.0  # No symbols → no penalty

    ratio = sum(1 for s in funcs_and_classes if s.has_docstring) / len(funcs_and_classes)
    return min(10.0, ratio * 10.0)


def _score_function_length(analysis: FileAnalysis) -> float:
    """Score function length discipline.

    Thresholds (universal — calibrated for most languages):
        0-20 lines  → 10.0
       20-50 lines  → 10→7
       50-100 lines → 7→4
       100+ lines   → 4→2
    """
    avg = analysis.metrics.avg_function_length
    if avg == 0:
        return 10.0
    if avg <= 20:
        return 10.0
    if avg <= 50:
        return 10.0 - (avg - 20) * 0.1  # 10→7
    if avg <= 100:
        return 7.0 - (avg - 50) * 0.06  # 7→4
    return max(2.0, 4.0 - (avg - 100) * 0.02)


def _score_nesting(analysis: FileAnalysis) -> float:
    """Score nesting depth control.

    Thresholds (universal):
        ≤2  → 10.0
       3-4  → 10→7
       5-6  → 7→4
       7+   → 4→2
    """
    depth = analysis.metrics.max_nesting_depth
    if depth <= 2:
        return 10.0
    if depth <= 4:
        return 10.0 - (depth - 2) * 1.5
    if depth <= 6:
        return 7.0 - (depth - 4) * 1.5
    return max(2.0, 4.0 - (depth - 6))


def _score_comments(analysis: FileAnalysis) -> float:
    """Score comment density.

    Sweet spot: 5-15% of code lines are comments.
    Too few → under-documented.  Too many → noise.
    """
    if analysis.metrics.code_lines <= 0:
        return 10.0  # Empty/tiny file

    ratio = analysis.metrics.comment_lines / analysis.metrics.code_lines
    if 0.05 <= ratio <= 0.15:
        return 10.0
    if ratio < 0.05:
        return max(5.0, 5.0 + ratio * 100)  # 0%→5.0, 5%→10.0
    return max(5.0, 10.0 - (ratio - 0.15) * 20)  # 15%→10, 40%→5


def _score_file_size(analysis: FileAnalysis) -> float:
    """Score file size appropriateness.

    Ideal: 50-300 lines.  Penalize very large files.
        ≤300  → 10.0
       300-500 → 10→7
       500-1000 → 7→4
       1000+ → 4→2
    """
    lines = analysis.metrics.total_lines
    if lines <= 300:
        return 10.0
    if lines <= 500:
        return 10.0 - (lines - 300) * 0.015  # 300→10, 500→7
    if lines <= 1000:
        return 7.0 - (lines - 500) * 0.006  # 500→7, 1000→4
    return max(2.0, 4.0 - (lines - 1000) * 0.002)


# ═══════════════════════════════════════════════════════════════════
#  Language-specific scorer functions
#
#  These read from FileAnalysis.language_metrics.  If the specialized
#  parser hasn't populated the data yet, they return a neutral 5.0
#  (neither penalizing nor rewarding).
# ═══════════════════════════════════════════════════════════════════


def _score_type_hints(analysis: FileAnalysis) -> float:
    """Score Python type hint coverage (from FileMetrics.has_type_hints)."""
    # has_type_hints is a float 0.0-1.0 representing fraction with annotations
    ratio = analysis.metrics.has_type_hints
    return min(10.0, ratio * 10.0)


def _score_python_docstrings(analysis: FileAnalysis) -> float:
    """Score Python docstring coverage specifically.

    Python-specific: also considers the symbols' kind to weight
    classes higher than helper functions.
    """
    funcs_and_classes = [
        s for s in analysis.symbols
        if s.kind in ("function", "async_function", "class")
    ]
    if not funcs_and_classes:
        return 10.0

    ratio = sum(1 for s in funcs_and_classes if s.has_docstring) / len(funcs_and_classes)
    return min(10.0, ratio * 10.0)


def _score_exported_ratio(analysis: FileAnalysis) -> float:
    """Score API surface control (Go, Rust, Python).

    Measures: what fraction of symbols are public?
    Ideal: 20-60% exported. Too much = leaky API. Too little = dead code.
    """
    if not analysis.symbols:
        return 10.0

    public = sum(1 for s in analysis.symbols if s.is_public)
    ratio = public / len(analysis.symbols)

    if 0.2 <= ratio <= 0.6:
        return 10.0
    if ratio < 0.2:
        return max(5.0, 5.0 + ratio * 25)  # Very few exports, might be dead code
    return max(5.0, 10.0 - (ratio - 0.6) * 12.5)  # Too many exports


def _score_error_handling(analysis: FileAnalysis) -> float:
    """Score error handling patterns (Go, Rust, Elixir).

    Reads from language_metrics["error_handling_ratio"].
    Neutral 5.0 if data not yet available.
    """
    ratio = analysis.language_metrics.get("error_handling_ratio")
    if ratio is None:
        return 5.0  # Neutral — parser hasn't populated this yet
    return min(10.0, ratio * 10.0)


def _score_unsafe_usage(analysis: FileAnalysis) -> float:
    """Score Rust unsafe block usage.

    Reads from language_metrics["unsafe_block_count"].
    0 unsafe blocks = 10.0.  Each block costs 1.5 points.
    """
    count = analysis.language_metrics.get("unsafe_block_count")
    if count is None:
        return 5.0  # Neutral
    if count == 0:
        return 10.0
    return max(2.0, 10.0 - count * 1.5)


def _score_modern_syntax(analysis: FileAnalysis) -> float:
    """Score JavaScript/TypeScript modern syntax usage.

    Reads from language_metrics["es_module"], ["const_let_ratio"].
    Neutral 5.0 if data not yet available.
    """
    es_module = analysis.language_metrics.get("es_module")
    const_let = analysis.language_metrics.get("const_let_ratio")

    if es_module is None and const_let is None:
        return 5.0  # Neutral

    score = 5.0
    if es_module is True:
        score += 2.5
    if const_let is not None:
        score += const_let * 2.5  # 0-1 ratio → 0-2.5 bonus

    return min(10.0, score)


def _score_any_usage(analysis: FileAnalysis) -> float:
    """Score TypeScript 'any' type avoidance.

    Reads from language_metrics["any_count"].
    0 any = 10.0.  Each 'any' costs 1 point.
    """
    count = analysis.language_metrics.get("any_count")
    if count is None:
        return 5.0  # Neutral
    if count == 0:
        return 10.0
    return max(2.0, 10.0 - count * 1.0)


def _score_type_coverage(analysis: FileAnalysis) -> float:
    """Score TypeScript type annotation completeness.

    Reads from language_metrics["type_coverage"].
    """
    coverage = analysis.language_metrics.get("type_coverage")
    if coverage is None:
        return 5.0
    return min(10.0, coverage * 10.0)


def _score_visibility(analysis: FileAnalysis) -> float:
    """Score visibility modifier usage (Java, C#, Kotlin).

    Checks if symbols use explicit visibility rather than defaults.
    """
    if not analysis.symbols:
        return 10.0

    explicit = sum(1 for s in analysis.symbols if s.visibility != "default")
    ratio = explicit / len(analysis.symbols)
    return min(10.0, ratio * 10.0)


def _score_template_logic_complexity(analysis: FileAnalysis) -> float:
    """Score template logic complexity.

    Templates should have minimal logic. Reads language_metrics["directive_count"].
    """
    directives = analysis.language_metrics.get("directive_count")
    if directives is None:
        # Estimate from code_lines — templates with high code density are complex
        if analysis.metrics.total_lines <= 0:
            return 10.0
        ratio = analysis.metrics.code_lines / analysis.metrics.total_lines
        if ratio <= 0.5:
            return 10.0  # Mostly whitespace/HTML structure
        if ratio <= 0.75:
            return 7.0
        return 5.0

    # Directives per 100 lines
    if analysis.metrics.total_lines <= 0:
        return 10.0
    density = (directives / analysis.metrics.total_lines) * 100
    if density <= 10:
        return 10.0
    if density <= 25:
        return 7.0
    if density <= 50:
        return 5.0
    return 3.0


def _score_template_reuse(analysis: FileAnalysis) -> float:
    """Score template block/macro reuse.

    Reads language_metrics["block_count"], ["macro_count"].
    """
    blocks = analysis.language_metrics.get("block_count", 0)
    macros = analysis.language_metrics.get("macro_count", 0)

    if analysis.metrics.total_lines <= 20:
        return 10.0  # Small template, no penalty

    reuse_indicators = blocks + macros
    if reuse_indicators >= 3:
        return 10.0
    if reuse_indicators >= 1:
        return 7.0
    return 5.0  # No reuse patterns detected


def _score_config_structure(analysis: FileAnalysis) -> float:
    """Score config file structural organization.

    Reads language_metrics["section_count"], ["key_count"].
    Falls back to nesting-based estimation.
    """
    sections = analysis.language_metrics.get("section_count")
    if sections is not None:
        if sections >= 2:
            return 10.0
        if sections >= 1:
            return 7.0
        return 5.0

    # Fallback: well-structured configs have moderate nesting
    depth = analysis.metrics.max_nesting_depth
    if 1 <= depth <= 4:
        return 10.0
    if depth == 0:
        return 7.0  # Flat — might lack structure
    return max(3.0, 10.0 - depth)  # Too deeply nested


# ═══════════════════════════════════════════════════════════════════
#  QUALITY_RUBRICS — the registry
# ═══════════════════════════════════════════════════════════════════


QUALITY_RUBRICS: dict[str, list[QualityDimension]] = {

    # ── Python ─────────────────────────────────────────────
    "python": [
        QualityDimension("docstrings", 0.25, "Docstring coverage", _score_python_docstrings),
        QualityDimension("function_length", 0.25, "Function size discipline", _score_function_length),
        QualityDimension("nesting", 0.20, "Nesting depth control", _score_nesting),
        QualityDimension("comments", 0.15, "Comment density", _score_comments),
        QualityDimension("type_hints", 0.15, "Type annotation coverage", _score_type_hints),
    ],

    # ── JavaScript ─────────────────────────────────────────
    "javascript": [
        QualityDimension("documentation", 0.15, "JSDoc coverage", _score_documentation),
        QualityDimension("function_length", 0.25, "Function size discipline", _score_function_length),
        QualityDimension("nesting", 0.20, "Callback/nesting depth", _score_nesting),
        QualityDimension("modern_syntax", 0.20, "ES6+ patterns", _score_modern_syntax),
        QualityDimension("comments", 0.20, "Comment quality", _score_comments),
    ],

    # ── TypeScript ─────────────────────────────────────────
    "typescript": [
        QualityDimension("type_coverage", 0.20, "Type annotation completeness", _score_type_coverage),
        QualityDimension("function_length", 0.20, "Function size discipline", _score_function_length),
        QualityDimension("nesting", 0.20, "Nesting depth control", _score_nesting),
        QualityDimension("documentation", 0.15, "Documentation comments", _score_documentation),
        QualityDimension("any_usage", 0.10, "Avoidance of 'any' type", _score_any_usage),
        QualityDimension("comments", 0.15, "Comment quality", _score_comments),
    ],

    # ── Go ─────────────────────────────────────────────────
    "go": [
        QualityDimension("documentation", 0.20, "Godoc coverage", _score_documentation),
        QualityDimension("error_handling", 0.25, "Error return checking", _score_error_handling),
        QualityDimension("exported_ratio", 0.15, "API surface control", _score_exported_ratio),
        QualityDimension("function_length", 0.20, "Function size discipline", _score_function_length),
        QualityDimension("nesting", 0.20, "Nesting depth control", _score_nesting),
    ],

    # ── Rust ───────────────────────────────────────────────
    "rust": [
        QualityDimension("documentation", 0.20, "Doc comment coverage", _score_documentation),
        QualityDimension("unsafe_usage", 0.25, "Unsafe block discipline", _score_unsafe_usage),
        QualityDimension("nesting", 0.20, "Nesting depth control", _score_nesting),
        QualityDimension("function_length", 0.20, "Function size discipline", _score_function_length),
        QualityDimension("error_handling", 0.15, "Result/Option usage", _score_error_handling),
    ],

    # ── Java ───────────────────────────────────────────────
    "java": [
        QualityDimension("documentation", 0.20, "Javadoc coverage", _score_documentation),
        QualityDimension("function_length", 0.20, "Method size discipline", _score_function_length),
        QualityDimension("nesting", 0.20, "Nesting depth control", _score_nesting),
        QualityDimension("visibility", 0.20, "Access modifier usage", _score_visibility),
        QualityDimension("file_size", 0.20, "Class size discipline", _score_file_size),
    ],

    # ── Kotlin ─────────────────────────────────────────────
    "kotlin": [
        QualityDimension("documentation", 0.20, "KDoc coverage", _score_documentation),
        QualityDimension("function_length", 0.25, "Function size discipline", _score_function_length),
        QualityDimension("nesting", 0.20, "Nesting depth control", _score_nesting),
        QualityDimension("visibility", 0.15, "Access modifier usage", _score_visibility),
        QualityDimension("comments", 0.20, "Comment quality", _score_comments),
    ],

    # ── Ruby ───────────────────────────────────────────────
    "ruby": [
        QualityDimension("documentation", 0.20, "YARD/RDoc coverage", _score_documentation),
        QualityDimension("function_length", 0.25, "Method size discipline", _score_function_length),
        QualityDimension("nesting", 0.20, "Nesting depth control", _score_nesting),
        QualityDimension("comments", 0.15, "Comment quality", _score_comments),
        QualityDimension("file_size", 0.20, "File size discipline", _score_file_size),
    ],

    # ── PHP ────────────────────────────────────────────────
    "php": [
        QualityDimension("documentation", 0.20, "PHPDoc coverage", _score_documentation),
        QualityDimension("function_length", 0.25, "Function size discipline", _score_function_length),
        QualityDimension("nesting", 0.20, "Nesting depth control", _score_nesting),
        QualityDimension("visibility", 0.15, "Visibility modifier usage", _score_visibility),
        QualityDimension("comments", 0.20, "Comment quality", _score_comments),
    ],

    # ── C# ─────────────────────────────────────────────────
    "csharp": [
        QualityDimension("documentation", 0.20, "XML doc coverage", _score_documentation),
        QualityDimension("function_length", 0.20, "Method size discipline", _score_function_length),
        QualityDimension("nesting", 0.20, "Nesting depth control", _score_nesting),
        QualityDimension("visibility", 0.20, "Access modifier usage", _score_visibility),
        QualityDimension("file_size", 0.20, "Class size discipline", _score_file_size),
    ],

    # ── Elixir ─────────────────────────────────────────────
    "elixir": [
        QualityDimension("documentation", 0.25, "@doc/@moduledoc coverage", _score_documentation),
        QualityDimension("function_length", 0.25, "Function size discipline", _score_function_length),
        QualityDimension("nesting", 0.20, "Pattern match nesting", _score_nesting),
        QualityDimension("exported_ratio", 0.15, "Public API control", _score_exported_ratio),
        QualityDimension("comments", 0.15, "Comment quality", _score_comments),
    ],

    # ── Swift ──────────────────────────────────────────────
    "swift": [
        QualityDimension("documentation", 0.20, "Documentation comments", _score_documentation),
        QualityDimension("function_length", 0.25, "Function size discipline", _score_function_length),
        QualityDimension("nesting", 0.20, "Nesting depth control", _score_nesting),
        QualityDimension("visibility", 0.15, "Access control", _score_visibility),
        QualityDimension("file_size", 0.20, "File size discipline", _score_file_size),
    ],

    # ── C ──────────────────────────────────────────────────
    "c": [
        QualityDimension("documentation", 0.15, "Header documentation", _score_documentation),
        QualityDimension("function_length", 0.30, "Function size discipline", _score_function_length),
        QualityDimension("nesting", 0.25, "Nesting depth control", _score_nesting),
        QualityDimension("comments", 0.15, "Comment quality", _score_comments),
        QualityDimension("file_size", 0.15, "File size discipline", _score_file_size),
    ],

    # ── C++ ────────────────────────────────────────────────
    "cpp": [
        QualityDimension("documentation", 0.15, "Doxygen coverage", _score_documentation),
        QualityDimension("function_length", 0.25, "Function size discipline", _score_function_length),
        QualityDimension("nesting", 0.25, "Nesting depth control", _score_nesting),
        QualityDimension("comments", 0.15, "Comment quality", _score_comments),
        QualityDimension("file_size", 0.20, "File size discipline", _score_file_size),
    ],

    # ── Zig ────────────────────────────────────────────────
    "zig": [
        QualityDimension("documentation", 0.20, "Doc comment coverage", _score_documentation),
        QualityDimension("function_length", 0.25, "Function size discipline", _score_function_length),
        QualityDimension("nesting", 0.20, "Nesting depth control", _score_nesting),
        QualityDimension("error_handling", 0.15, "Error handling patterns", _score_error_handling),
        QualityDimension("comments", 0.20, "Comment quality", _score_comments),
    ],

    # ── Shell ──────────────────────────────────────────────
    "shell": [
        QualityDimension("function_length", 0.30, "Function size discipline", _score_function_length),
        QualityDimension("nesting", 0.25, "Nesting depth control", _score_nesting),
        QualityDimension("comments", 0.25, "Comment quality", _score_comments),
        QualityDimension("file_size", 0.20, "Script size discipline", _score_file_size),
    ],

    # ── Template Engines (Jinja2, ERB, HEEx, etc.) ─────────
    "template": [
        QualityDimension("logic_complexity", 0.30, "Template logic complexity", _score_template_logic_complexity),
        QualityDimension("reuse", 0.25, "Block/macro/partial reuse", _score_template_reuse),
        QualityDimension("nesting", 0.25, "Template nesting depth", _score_nesting),
        QualityDimension("comments", 0.20, "Template documentation", _score_comments),
    ],

    # ── Config / Infrastructure (YAML, JSON, TOML, HCL, Dockerfile) ──
    "config": [
        QualityDimension("structure", 0.30, "Logical organization", _score_config_structure),
        QualityDimension("nesting", 0.30, "Nesting depth", _score_nesting),
        QualityDimension("comments", 0.20, "Documentation/comments", _score_comments),
        QualityDimension("file_size", 0.20, "File size appropriateness", _score_file_size),
    ],

    # ── Markup (Markdown, RST, AsciiDoc) ──────────────────
    "markup": [
        QualityDimension("file_size", 0.40, "Document length", _score_file_size),
        QualityDimension("comments", 0.30, "Internal documentation", _score_comments),
        QualityDimension("nesting", 0.30, "Structural depth", _score_nesting),
    ],

    # ── Style (CSS, SCSS, Less) ───────────────────────────
    "style": [
        QualityDimension("nesting", 0.30, "Selector nesting depth", _score_nesting),
        QualityDimension("file_size", 0.30, "Stylesheet size", _score_file_size),
        QualityDimension("comments", 0.20, "Documentation", _score_comments),
        QualityDimension("function_length", 0.20, "Rule set size", _score_function_length),
    ],

    # ── Generic fallback (for any language without a specific rubric) ──
    "_generic": [
        QualityDimension("documentation", 0.20, "Documentation coverage", _score_documentation),
        QualityDimension("function_length", 0.30, "Function size discipline", _score_function_length),
        QualityDimension("nesting", 0.30, "Nesting depth control", _score_nesting),
        QualityDimension("comments", 0.20, "Comment quality", _score_comments),
    ],
}

# Languages that should use a type-based rubric instead of their own
# (e.g., all template engines use "template", config formats use "config")
_FILE_TYPE_RUBRIC_MAP: dict[str, str] = {
    "template": "template",
    "config": "config",
    "markup": "markup",
    "style": "style",
    "data": "config",   # Data files scored like config
    "build": "config",  # Build files scored like config
}


# ═══════════════════════════════════════════════════════════════════
#  Public API: score a single file
# ═══════════════════════════════════════════════════════════════════


def get_rubric(analysis: FileAnalysis) -> tuple[str, list[QualityDimension]]:
    """Get the appropriate rubric for a file analysis.

    Resolution order:
    1. Language-specific rubric (if the language has one)
    2. File-type rubric (template, config, markup, style)
    3. Generic fallback

    Returns:
        (rubric_name, dimensions)
    """
    lang = analysis.language

    # Check language-specific rubric first
    if lang in QUALITY_RUBRICS:
        return lang, QUALITY_RUBRICS[lang]

    # Check file-type-based rubric
    file_type = analysis.file_type
    if file_type in _FILE_TYPE_RUBRIC_MAP:
        rubric_key = _FILE_TYPE_RUBRIC_MAP[file_type]
        if rubric_key in QUALITY_RUBRICS:
            return rubric_key, QUALITY_RUBRICS[rubric_key]

    # Fallback
    return "_generic", QUALITY_RUBRICS["_generic"]


def score_file(analysis: FileAnalysis) -> dict:
    """Score a single file using its language's quality rubric.

    Args:
        analysis: Complete file analysis from any parser.

    Returns:
        {
            "score": 7.8,                     # Weighted composite (0-10)
            "rubric": "python",               # Which rubric was used
            "breakdown": {
                "docstrings": 9.0,            # Per-dimension scores
                "function_length": 7.5,
                ...
            }
        }
    """
    rubric_name, dimensions = get_rubric(analysis)

    scores: dict[str, float] = {}
    weighted_total = 0.0

    for dim in dimensions:
        try:
            raw = dim.scorer(analysis)
        except Exception:
            raw = 5.0  # Neutral on scorer failure

        clamped = max(0.0, min(10.0, raw))
        scores[dim.name] = round(clamped, 1)
        weighted_total += clamped * dim.weight

    return {
        "score": round(max(0.0, min(10.0, weighted_total)), 1),
        "rubric": rubric_name,
        "breakdown": scores,
    }


def get_rubric_info(language: str) -> list[dict]:
    """Get rubric dimension info for display purposes.

    Returns:
        [{"name": "docstrings", "weight": 0.25, "description": "..."}, ...]
    """
    if language in QUALITY_RUBRICS:
        dims = QUALITY_RUBRICS[language]
    elif language in _FILE_TYPE_RUBRIC_MAP:
        dims = QUALITY_RUBRICS.get(_FILE_TYPE_RUBRIC_MAP[language], QUALITY_RUBRICS["_generic"])
    else:
        dims = QUALITY_RUBRICS["_generic"]

    return [
        {"name": d.name, "weight": d.weight, "description": d.description}
        for d in dims
    ]
