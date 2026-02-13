"""
L2 — Code quality analysis (on-demand, 1-5s).

Computes code health metrics from the parsed AST data:
docstring coverage, function complexity, naming consistency,
and per-file health scores.

Public API:
    l2_quality(project_root)  → code health report
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from src.core.services.audit.models import wrap_result

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  Naming convention detection
# ═══════════════════════════════════════════════════════════════════

_SNAKE_CASE = re.compile(r"^[a-z][a-z0-9_]*$")
_CAMEL_CASE = re.compile(r"^[A-Z][a-zA-Z0-9]*$")
_UPPER_SNAKE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_DUNDER = re.compile(r"^__[a-z][a-z0-9_]*__$")


def _classify_name(name: str, kind: str) -> str:
    """Classify a symbol name's convention.

    Returns 'correct', 'wrong_case', or 'unconventional'.
    """
    if _DUNDER.match(name):
        return "correct"  # Dunder is always OK

    # Ignore private names that start with underscore
    bare = name.lstrip("_")
    if not bare:
        return "correct"

    if kind == "class":
        # Classes should be CamelCase
        if _CAMEL_CASE.match(bare):
            return "correct"
        elif _SNAKE_CASE.match(bare):
            return "wrong_case"
        return "unconventional"
    else:
        # Functions should be snake_case
        if _SNAKE_CASE.match(bare):
            return "correct"
        elif _CAMEL_CASE.match(bare):
            return "wrong_case"
        return "unconventional"


# ═══════════════════════════════════════════════════════════════════
#  Per-file health scoring
# ═══════════════════════════════════════════════════════════════════


def _file_health(analysis: object) -> dict:
    """Compute a health score (0–10) for a single file.

    Dimensions:
        1. Docstring coverage (0-10)
        2. Function length (0-10)
        3. Nesting depth (0-10)
        4. Comment density (0-10)
        5. Type hint coverage (0-10)
    """
    m = analysis.metrics

    # 1. Docstring coverage
    funcs_and_classes = [s for s in analysis.symbols
                         if s.kind in ("function", "async_function", "class")]
    if funcs_and_classes:
        ds_ratio = sum(1 for s in funcs_and_classes if s.has_docstring) / len(funcs_and_classes)
    else:
        ds_ratio = 1.0  # No symbols → no penalty
    ds_score = min(10.0, ds_ratio * 10)

    # 2. Function length — penalize long functions
    # 0-20 lines = 10, 20-50 = 7, 50-100 = 4, 100+ = 2
    avg = m.avg_function_length
    if avg == 0:
        len_score = 10.0
    elif avg <= 20:
        len_score = 10.0
    elif avg <= 50:
        len_score = 10.0 - (avg - 20) * 0.1  # 10→7
    elif avg <= 100:
        len_score = 7.0 - (avg - 50) * 0.06   # 7→4
    else:
        len_score = max(2.0, 4.0 - (avg - 100) * 0.02)

    # 3. Nesting depth — penalize deeply nested code
    depth = m.max_nesting_depth
    if depth <= 2:
        nest_score = 10.0
    elif depth <= 4:
        nest_score = 10.0 - (depth - 2) * 1.5
    elif depth <= 6:
        nest_score = 7.0 - (depth - 4) * 1.5
    else:
        nest_score = max(2.0, 4.0 - (depth - 6))

    # 4. Comment density — some comments are healthy
    if m.code_lines > 0:
        comment_ratio = m.comment_lines / m.code_lines
    else:
        comment_ratio = 0
    # Sweet spot: 5-15% comments
    if 0.05 <= comment_ratio <= 0.15:
        comment_score = 10.0
    elif comment_ratio < 0.05:
        comment_score = max(5.0, 5.0 + comment_ratio * 100)
    else:
        comment_score = max(5.0, 10.0 - (comment_ratio - 0.15) * 20)

    # 5. Type hints
    hint_score = min(10.0, m.has_type_hints * 10)

    # Weighted average
    weights = {"docstrings": 0.25, "function_length": 0.25,
               "nesting": 0.2, "comments": 0.15, "type_hints": 0.15}
    scores = {
        "docstrings": round(ds_score, 1),
        "function_length": round(len_score, 1),
        "nesting": round(nest_score, 1),
        "comments": round(comment_score, 1),
        "type_hints": round(hint_score, 1),
    }
    total = sum(scores[k] * weights[k] for k in weights)

    return {
        "score": round(total, 1),
        "breakdown": scores,
    }


# ═══════════════════════════════════════════════════════════════════
#  Hotspot detection
# ═══════════════════════════════════════════════════════════════════


def _detect_hotspots(analyses: dict[str, object]) -> list[dict]:
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
                "detail": f"{m.code_lines} code lines",
                "value": m.code_lines,
            })

        # Too many imports
        if m.import_count > 15:
            hotspots.append({
                "type": "many_imports",
                "severity": "info" if m.import_count < 25 else "warning",
                "file": rel_path,
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
                        "symbol": sym.name,
                        "lineno": sym.lineno,
                        "detail": f"{len(sym.methods)} methods",
                        "value": len(sym.methods),
                    })

        # No docstrings (only flag non-trivial files)
        funcs_and_classes = [s for s in analysis.symbols
                            if s.kind in ("function", "async_function", "class")]
        if len(funcs_and_classes) > 3:
            doc_count = sum(1 for s in funcs_and_classes if s.has_docstring)
            if doc_count == 0:
                hotspots.append({
                    "type": "no_docstrings",
                    "severity": "info",
                    "file": rel_path,
                    "detail": f"0/{len(funcs_and_classes)} symbols documented",
                    "value": 0,
                })

    # Sort by severity (critical > warning > info)
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    hotspots.sort(key=lambda h: (severity_order.get(h["severity"], 3), -h["value"]))

    return hotspots


# ═══════════════════════════════════════════════════════════════════
#  Naming consistency analysis
# ═══════════════════════════════════════════════════════════════════


def _naming_analysis(analyses: dict[str, object]) -> dict:
    """Analyze naming convention consistency.

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
        for sym in analysis.symbols:
            total += 1
            result = _classify_name(sym.name, sym.kind)
            if result == "correct":
                correct += 1
            elif result == "wrong_case":
                wrong += 1
                if len(violations) < 50:  # Cap to avoid huge lists
                    violations.append({
                        "file": rel_path,
                        "symbol": sym.name,
                        "kind": sym.kind,
                        "lineno": sym.lineno,
                        "expected": "CamelCase" if sym.kind == "class" else "snake_case",
                    })
            else:
                unconv += 1
                if len(violations) < 50:
                    violations.append({
                        "file": rel_path,
                        "symbol": sym.name,
                        "kind": sym.kind,
                        "lineno": sym.lineno,
                        "expected": "CamelCase" if sym.kind == "class" else "snake_case",
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
#  Aggregate quality summary
# ═══════════════════════════════════════════════════════════════════


def _quality_summary(
    file_scores: list[dict],
    hotspots: list[dict],
    naming: dict,
) -> dict:
    """Compute aggregate quality summary.

    Returns:
        {
            "overall_score": float (0-10),
            "dimension_scores": {
                "docstrings": float,
                "function_length": float,
                "nesting": float,
                "comments": float,
                "type_hints": float,
                "naming": float,
            },
            "hotspot_summary": {
                "critical": int,
                "warning": int,
                "info": int,
            },
        }
    """
    if not file_scores:
        return {
            "overall_score": 0.0,
            "dimension_scores": {},
            "hotspot_summary": {"critical": 0, "warning": 0, "info": 0},
        }

    # Average across all file breakdowns
    dims = ["docstrings", "function_length", "nesting", "comments", "type_hints"]
    avg_dims = {}
    for dim in dims:
        values = [fs["breakdown"][dim] for fs in file_scores if dim in fs["breakdown"]]
        avg_dims[dim] = round(sum(values) / len(values), 1) if values else 0.0

    avg_dims["naming"] = naming.get("consistency_score", 10.0)

    # Overall: weighted average of all dimensions
    weights = {
        "docstrings": 0.20,
        "function_length": 0.20,
        "nesting": 0.15,
        "comments": 0.10,
        "type_hints": 0.15,
        "naming": 0.20,
    }
    overall = sum(avg_dims[k] * weights[k] for k in weights)

    # Hotspot counts
    hs_counts = {"critical": 0, "warning": 0, "info": 0}
    for h in hotspots:
        sev = h.get("severity", "info")
        hs_counts[sev] = hs_counts.get(sev, 0) + 1

    return {
        "overall_score": round(overall, 1),
        "dimension_scores": avg_dims,
        "hotspot_summary": hs_counts,
    }


# ═══════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════


def l2_quality(project_root: Path) -> dict:
    """L2: Code quality analysis — health scores, hotspots, naming.

    On-demand, takes 1-5s depending on project size.

    Returns:
        {
            "_meta": AuditMeta,
            "summary": {overall_score, dimension_scores, hotspot_summary},
            "file_scores": [{file, score, breakdown}, ...],
            "hotspots": [{type, severity, file, detail}, ...],
            "naming": {total_symbols, correct, wrong_case, consistency_score, violations},
        }
    """
    from src.core.services.audit.parsers.python_parser import parse_tree

    started = time.time()

    # Parse all Python files
    analyses = parse_tree(project_root)

    # Compute per-file health
    file_scores = []
    for rel_path, analysis in sorted(analyses.items()):
        if analysis.parse_error:
            continue
        health = _file_health(analysis)
        file_scores.append({
            "file": rel_path,
            **health,
        })

    # Detect hotspots
    hotspots = _detect_hotspots(analyses)

    # Naming analysis
    naming = _naming_analysis(analyses)

    # Aggregate
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
