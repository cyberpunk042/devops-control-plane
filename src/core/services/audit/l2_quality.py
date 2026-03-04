"""
L2 — Code quality analysis (on-demand, 1-5s).

Computes code health metrics from parsed file data:
per-language quality scoring, hotspot detection, naming consistency.
Supports ALL languages via the parser registry and rubric system.

Public API:
    l2_quality(project_root)  → code health report
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from src.core.services.audit.models import wrap_result
from src.core.services.audit.parsers._base import FileAnalysis
from src.core.services.audit.parsers._rubrics import score_file

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  Naming convention detection
# ═══════════════════════════════════════════════════════════════════

_SNAKE_CASE = re.compile(r"^[a-z][a-z0-9_]*$")
_CAMEL_CASE = re.compile(r"^[A-Z][a-zA-Z0-9]*$")
_UPPER_SNAKE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_DUNDER = re.compile(r"^__[a-z][a-z0-9_]*__$")

# Per-language naming conventions.
# "snake" = functions snake_case, classes CamelCase
# "camel" = everything CamelCase
# "mixed" = either convention is acceptable
_LANG_NAMING_STYLE: dict[str, str] = {
    "python": "snake",
    "ruby": "snake",
    "elixir": "snake",
    "rust": "snake",
    "c": "snake",
    "go": "camel",       # Go uses CamelCase for exported, camelCase for unexported
    "java": "camel",
    "kotlin": "camel",
    "csharp": "camel",
    "swift": "camel",
    "scala": "camel",
    "javascript": "camel",
    "typescript": "camel",
    "php": "camel",
    "dart": "camel",
}


def _classify_name(name: str, kind: str, language: str = "python") -> str:
    """Classify a symbol name's convention.

    Uses language-appropriate conventions:
    - Python/Ruby/Rust/C/Elixir: snake_case for functions, CamelCase for classes
    - Go/Java/Kotlin/C#/Swift/JS/TS: CamelCase for everything
    - Unknown: skip (return 'correct')

    Returns 'correct', 'wrong_case', or 'unconventional'.
    """
    if _DUNDER.match(name):
        return "correct"  # Dunder is always OK

    # Ignore private names that start with underscore
    bare = name.lstrip("_")
    if not bare:
        return "correct"

    style = _LANG_NAMING_STYLE.get(language, "mixed")

    if style == "mixed":
        # No convention enforced for unknown languages
        return "correct"

    if style == "snake":
        # Snake-case languages: functions=snake_case, classes=CamelCase
        if kind == "class":
            if _CAMEL_CASE.match(bare):
                return "correct"
            elif _SNAKE_CASE.match(bare):
                return "wrong_case"
            return "unconventional"
        else:
            if _SNAKE_CASE.match(bare):
                return "correct"
            elif _CAMEL_CASE.match(bare):
                return "wrong_case"
            return "unconventional"

    if style == "camel":
        # CamelCase languages: classes=PascalCase, functions=camelCase or PascalCase
        if kind == "class":
            if _CAMEL_CASE.match(bare):
                return "correct"
            elif _SNAKE_CASE.match(bare):
                return "wrong_case"
            return "unconventional"
        else:
            # Accept both camelCase and snake_case (many JS/TS projects use either)
            if _CAMEL_CASE.match(bare) or _SNAKE_CASE.match(bare):
                return "correct"
            return "unconventional"

    return "correct"


# ═══════════════════════════════════════════════════════════════════
#  Hotspot detection (all languages)
# ═══════════════════════════════════════════════════════════════════


def _detect_hotspots(analyses: dict[str, FileAnalysis]) -> list[dict]:
    """Detect code quality hotspots — files or functions that need attention.

    Types:
        - long_function: function > 80 lines
        - deep_nesting: function with nesting > 4
        - many_imports: file with > 15 imports
        - large_file: file with > 500 code lines
        - no_docstrings: file with 0% docstring coverage and > 3 symbols
        - god_class: class with > 15 methods
    """
    hotspots = []

    for rel_path, analysis in analyses.items():
        m = analysis.metrics

        # Large file
        if m.code_lines > 500:
            hotspots.append({
                "type": "large_file",
                "severity": "warning" if m.code_lines < 800 else "critical",
                "file": rel_path,
                "language": analysis.language,
                "detail": f"{m.code_lines} code lines",
                "value": m.code_lines,
            })

        # Too many imports
        if m.import_count > 15:
            hotspots.append({
                "type": "many_imports",
                "severity": "info" if m.import_count < 25 else "warning",
                "file": rel_path,
                "language": analysis.language,
                "detail": f"{m.import_count} imports",
                "value": m.import_count,
            })

        # Per-symbol hotspots
        for sym in analysis.symbols:
            if sym.kind in ("function", "async_function"):
                if sym.body_lines > 80:
                    hotspots.append({
                        "type": "long_function",
                        "severity": "warning" if sym.body_lines < 150 else "critical",
                        "file": rel_path,
                        "language": analysis.language,
                        "symbol": sym.name,
                        "lineno": sym.lineno,
                        "detail": f"{sym.body_lines} lines",
                        "value": sym.body_lines,
                    })
                if sym.max_nesting > 4:
                    hotspots.append({
                        "type": "deep_nesting",
                        "severity": "warning" if sym.max_nesting < 7 else "critical",
                        "file": rel_path,
                        "language": analysis.language,
                        "symbol": sym.name,
                        "lineno": sym.lineno,
                        "detail": f"depth {sym.max_nesting}",
                        "value": sym.max_nesting,
                    })
            elif sym.kind == "class":
                if len(sym.methods) > 15:
                    hotspots.append({
                        "type": "god_class",
                        "severity": "warning" if len(sym.methods) < 25 else "critical",
                        "file": rel_path,
                        "language": analysis.language,
                        "symbol": sym.name,
                        "lineno": sym.lineno,
                        "detail": f"{len(sym.methods)} methods",
                        "value": len(sym.methods),
                    })

        # No docstrings (only flag non-trivial files with symbols)
        funcs_and_classes = [s for s in analysis.symbols
                            if s.kind in ("function", "async_function", "class")]
        if len(funcs_and_classes) > 3:
            doc_count = sum(1 for s in funcs_and_classes if s.has_docstring)
            if doc_count == 0:
                hotspots.append({
                    "type": "no_docstrings",
                    "severity": "info",
                    "file": rel_path,
                    "language": analysis.language,
                    "detail": f"0/{len(funcs_and_classes)} symbols documented",
                    "value": 0,
                })

    # Sort by severity (critical > warning > info)
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    hotspots.sort(key=lambda h: (severity_order.get(h["severity"], 3), -h["value"]))

    return hotspots


# ═══════════════════════════════════════════════════════════════════
#  Naming consistency analysis (language-aware)
# ═══════════════════════════════════════════════════════════════════


def _naming_analysis(analyses: dict[str, FileAnalysis]) -> dict:
    """Analyze naming convention consistency.

    Uses per-language naming conventions (snake_case for Python/Rust,
    CamelCase for Go/Java, etc.).

    Returns:
        {
            "total_symbols": int,
            "correct": int,
            "wrong_case": int,
            "unconventional": int,
            "consistency_score": float (0-10),
            "violations": [{file, symbol, kind, expected, got}, ...],
        }
    """
    total = 0
    correct = 0
    wrong = 0
    unconv = 0
    violations = []

    for rel_path, analysis in analyses.items():
        lang = analysis.language

        for sym in analysis.symbols:
            total += 1
            result = _classify_name(sym.name, sym.kind, lang)
            if result == "correct":
                correct += 1
            elif result == "wrong_case":
                wrong += 1
                if len(violations) < 50:  # Cap to avoid huge lists
                    style = _LANG_NAMING_STYLE.get(lang, "mixed")
                    if sym.kind == "class":
                        expected = "CamelCase"
                    elif style == "snake":
                        expected = "snake_case"
                    else:
                        expected = "camelCase"

                    violations.append({
                        "file": rel_path,
                        "symbol": sym.name,
                        "kind": sym.kind,
                        "language": lang,
                        "lineno": sym.lineno,
                        "expected": expected,
                    })
            else:
                unconv += 1
                if len(violations) < 50:
                    violations.append({
                        "file": rel_path,
                        "symbol": sym.name,
                        "kind": sym.kind,
                        "language": lang,
                        "lineno": sym.lineno,
                        "expected": "language convention",
                    })

    consistency = (correct / total * 10) if total > 0 else 10.0

    return {
        "total_symbols": total,
        "correct": correct,
        "wrong_case": wrong,
        "unconventional": unconv,
        "consistency_score": round(consistency, 1),
        "violations": violations,
    }


# ═══════════════════════════════════════════════════════════════════
#  Aggregate quality summary (multi-language)
# ═══════════════════════════════════════════════════════════════════


def _quality_summary(
    file_scores: list[dict],
    hotspots: list[dict],
    naming: dict,
) -> dict:
    """Compute aggregate quality summary across all languages.

    Returns:
        {
            "overall_score": float (0-10),
            "dimension_scores": {dim_name: float, ...},
            "per_language": {lang: {"score": float, "files": int}, ...},
            "hotspot_summary": {"critical": int, "warning": int, "info": int},
        }
    """
    if not file_scores:
        return {
            "overall_score": 0.0,
            "dimension_scores": {},
            "per_language": {},
            "hotspot_summary": {"critical": 0, "warning": 0, "info": 0},
        }

    # Collect all dimension names across all rubrics used
    all_dims: dict[str, list[float]] = {}
    per_lang: dict[str, dict] = {}

    for fs in file_scores:
        breakdown = fs.get("breakdown", {})
        lang = fs.get("language", "unknown")

        # Aggregate per-dimension
        for dim, val in breakdown.items():
            if dim not in all_dims:
                all_dims[dim] = []
            all_dims[dim].append(val)

        # Aggregate per-language
        if lang not in per_lang:
            per_lang[lang] = {"scores": [], "files": 0}
        per_lang[lang]["scores"].append(fs["score"])
        per_lang[lang]["files"] += 1

    # Average each dimension across all files that have it
    dimension_scores = {}
    for dim, values in sorted(all_dims.items()):
        dimension_scores[dim] = round(sum(values) / len(values), 1) if values else 0.0

    # Add naming as a cross-cutting dimension
    dimension_scores["naming"] = naming.get("consistency_score", 10.0)

    # Compute per-language summary
    per_language_summary = {}
    for lang, data in sorted(per_lang.items()):
        scores = data["scores"]
        per_language_summary[lang] = {
            "score": round(sum(scores) / len(scores), 1),
            "files": data["files"],
        }

    # Overall score: simple average of all file scores + naming weight
    all_scores = [fs["score"] for fs in file_scores]
    code_avg = sum(all_scores) / len(all_scores) if all_scores else 0.0
    naming_score = naming.get("consistency_score", 10.0)

    # Code health = 80% code scores + 20% naming
    overall = code_avg * 0.80 + naming_score * 0.20

    # Hotspot counts
    hs_counts = {"critical": 0, "warning": 0, "info": 0}
    for h in hotspots:
        sev = h.get("severity", "info")
        hs_counts[sev] = hs_counts.get(sev, 0) + 1

    return {
        "overall_score": round(overall, 1),
        "dimension_scores": dimension_scores,
        "per_language": per_language_summary,
        "hotspot_summary": hs_counts,
    }


# ═══════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════


def l2_quality(project_root: Path) -> dict:
    """L2: Code quality analysis — health scores, hotspots, naming.

    Parses ALL file types in the project via the parser registry.
    Scores each file using language-appropriate quality rubrics.
    Detects hotspots across all languages.

    Returns:
        {
            "_meta": AuditMeta,
            "summary": {overall_score, dimension_scores, per_language, hotspot_summary},
            "file_scores": [{file, language, rubric, score, breakdown}, ...],
            "hotspots": [{type, severity, file, language, detail}, ...],
            "naming": {total_symbols, correct, wrong_case, consistency_score, violations},
        }
    """
    from src.core.services.audit.parsers import registry

    started = time.time()

    # Parse ALL files through the registry (Python via PythonParser,
    # everything else via FallbackParser)
    analyses = registry.parse_tree(project_root)

    # Compute per-file health using language-appropriate rubrics
    file_scores = []
    for rel_path, analysis in sorted(analyses.items()):
        if analysis.parse_error:
            continue

        result = score_file(analysis)
        file_scores.append({
            "file": rel_path,
            "language": analysis.language,
            "rubric": result["rubric"],
            "score": result["score"],
            "breakdown": result["breakdown"],
        })

    # Detect hotspots (works across all languages)
    hotspots = _detect_hotspots(analyses)

    # Naming analysis (language-aware conventions)
    naming = _naming_analysis(analyses)

    # Aggregate summary
    summary = _quality_summary(file_scores, hotspots, naming)

    # Sort file scores by score ascending (worst first)
    file_scores.sort(key=lambda f: f["score"])

    data = {
        "summary": summary,
        "file_scores": file_scores,
        "hotspots": hotspots,
        "naming": naming,
    }
    return wrap_result(data, "L2", "quality", started)
