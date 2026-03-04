"""
Narrative report generator — natural language observations from audit data.

Phase 8.3: Instead of raw metric dumps, this module generates computed
observations that react to actual data patterns:

    "📊 This module scores 8.3/10 overall. Its Python code is
     well-documented (docstrings: 9.2) but has nesting concerns in
     l1_classification.py (depth 8)."

Observations are COMPUTED, not templated strings — they change based
on the data patterns detected.

Consumers: audit_directive.py (render_html), CLI audit commands
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Observation:
    """A single narrative observation about the audit data."""

    icon: str          # Emoji prefix (📊, ⚠, ✅, 💡)
    category: str      # health, quality, complexity, coverage, deps, trend
    priority: int      # 1 = most important, shown first
    text: str          # The natural language sentence


def generate_observations(data: dict) -> list[Observation]:
    """Generate narrative observations from scoped audit data.

    Args:
        data: A dict with keys matching ScopedAuditData fields:
              health_score, hotspots, deps_outbound, deps_inbound,
              file_count, total_lines, language_breakdown,
              subcategory_averages, worst_files, risks, test_data, etc.

    Returns:
        List of Observation objects, sorted by priority (most important first).
    """
    obs: list[Observation] = []

    # ── Health score overview ────────────────────────────────
    score = data.get("health_score")
    if score is not None:
        obs.append(_observe_health(score, data))

    # ── Code quality patterns ────────────────────────────────
    obs.extend(_observe_quality(data))

    # ── Complexity concerns ──────────────────────────────────
    obs.extend(_observe_complexity(data))

    # ── Documentation coverage ───────────────────────────────
    obs.extend(_observe_documentation(data))

    # ── Dependency analysis ──────────────────────────────────
    obs.extend(_observe_dependencies(data))

    # ── Test coverage ────────────────────────────────────────
    obs.extend(_observe_testing(data))

    # ── Language composition ─────────────────────────────────
    obs.extend(_observe_languages(data))

    # ── Cross-module comparison & trends (Phase 8.4) ─────────
    obs.extend(_observe_comparison(data))

    # ── Actionable recommendations (Phase 8.5) ───────────────
    obs.extend(_observe_recommendations(data))

    # Sort by priority (lower = more important)
    obs.sort(key=lambda o: o.priority)
    return obs


# ═══════════════════════════════════════════════════════════════════
#  Observation generators
# ═══════════════════════════════════════════════════════════════════


def _observe_health(score: float, data: dict) -> Observation:
    """Overall health score observation."""
    file_count = data.get("file_count", 0)
    total_lines = data.get("total_lines", 0)

    # Determine sentiment
    if score >= 8.0:
        sentiment = "well-maintained"
        icon = "✅"
    elif score >= 6.0:
        sentiment = "in decent shape"
        icon = "📊"
    elif score >= 4.0:
        sentiment = "showing its age"
        icon = "⚠️"
    else:
        sentiment = "in need of attention"
        icon = "🔴"

    size_note = ""
    if total_lines > 0:
        size_note = f" across {file_count} files ({total_lines:,} lines)"

    return Observation(
        icon=icon,
        category="health",
        priority=1,
        text=f"This module scores **{score:.1f}/10** overall — {sentiment}{size_note}.",
    )


def _observe_quality(data: dict) -> list[Observation]:
    """Quality pattern observations based on subcategory averages."""
    obs: list[Observation] = []
    avgs = data.get("subcategory_averages", {})
    if not avgs:
        return obs

    # Find best and worst subcategories
    if len(avgs) >= 2:
        sorted_cats = sorted(avgs.items(), key=lambda kv: kv[1])
        worst_name, worst_val = sorted_cats[0]
        best_name, best_val = sorted_cats[-1]

        if best_val - worst_val >= 2.0:
            obs.append(Observation(
                icon="📊",
                category="quality",
                priority=3,
                text=(
                    f"Quality varies significantly: **{_friendly_name(best_name)}** "
                    f"is strongest ({best_val:.1f}) while "
                    f"**{_friendly_name(worst_name)}** needs work ({worst_val:.1f})."
                ),
            ))

    return obs


def _observe_complexity(data: dict) -> list[Observation]:
    """Complexity observations from hotspots and worst files."""
    obs: list[Observation] = []
    hotspots = data.get("hotspots", [])

    if hotspots:
        top = hotspots[:3]
        names = ", ".join(
            f"`{_short_path(h.get('file', ''))}`" for h in top
        )
        worst = top[0]
        worst_depth = worst.get("max_nesting_depth", 0)
        worst_lines = worst.get("total_lines", 0)

        if worst_depth >= 6:
            obs.append(Observation(
                icon="⚠️",
                category="complexity",
                priority=4,
                text=(
                    f"Nesting depth concern in {names} — "
                    f"deepest at **{worst_depth} levels**. "
                    f"Consider extracting inner logic into helper functions."
                ),
            ))
        elif worst_lines > 500:
            obs.append(Observation(
                icon="⚠️",
                category="complexity",
                priority=4,
                text=(
                    f"Large files detected: {names} "
                    f"(largest is **{worst_lines} lines**). "
                    f"Consider splitting into smaller, focused modules."
                ),
            ))

    return obs


def _observe_documentation(data: dict) -> list[Observation]:
    """Documentation coverage observations."""
    obs: list[Observation] = []
    avgs = data.get("subcategory_averages", {})

    doc_score = avgs.get("documentation") or avgs.get("docstrings")
    if doc_score is not None:
        if doc_score >= 8.0:
            obs.append(Observation(
                icon="✅",
                category="coverage",
                priority=5,
                text=f"Documentation is strong (**{doc_score:.1f}/10**) — well-documented code.",
            ))
        elif doc_score < 4.0:
            obs.append(Observation(
                icon="⚠️",
                category="coverage",
                priority=3,
                text=(
                    f"Documentation is thin (**{doc_score:.1f}/10**). "
                    f"Adding docstrings to public functions would significantly "
                    f"improve maintainability."
                ),
            ))

    return obs


def _observe_dependencies(data: dict) -> list[Observation]:
    """Dependency analysis observations."""
    obs: list[Observation] = []
    outbound = data.get("deps_outbound", [])
    inbound = data.get("deps_inbound", [])

    n_out = len(outbound)
    n_in = len(inbound)

    if n_out > 5:
        high_deps = [d.get("module_name", "?") for d in outbound[:3]]
        obs.append(Observation(
            icon="⚠️",
            category="deps",
            priority=5,
            text=(
                f"This module depends on **{n_out} other modules** "
                f"(including {', '.join(high_deps)}). "
                f"High coupling may make changes riskier."
            ),
        ))
    elif n_out == 0 and n_in == 0:
        obs.append(Observation(
            icon="💡",
            category="deps",
            priority=7,
            text="This module has no cross-module dependencies — it's fully self-contained.",
        ))

    if n_in > 5:
        obs.append(Observation(
            icon="💡",
            category="deps",
            priority=6,
            text=(
                f"**{n_in} modules depend on this one** — "
                f"changes here have a wide blast radius. "
                f"Consider adding integration tests."
            ),
        ))

    return obs


def _observe_testing(data: dict) -> list[Observation]:
    """Test coverage observations."""
    obs: list[Observation] = []
    test_data = data.get("test_data", {})
    matched_tests = data.get("matched_tests", [])

    if matched_tests:
        obs.append(Observation(
            icon="✅",
            category="coverage",
            priority=6,
            text=(
                f"Has **{len(matched_tests)} test file(s)** "
                f"covering this module."
            ),
        ))
    else:
        file_count = data.get("file_count", 0)
        if file_count > 5:
            obs.append(Observation(
                icon="⚠️",
                category="coverage",
                priority=3,
                text=(
                    f"No test files found for this module "
                    f"({file_count} source files). "
                    f"Adding tests would improve confidence in changes."
                ),
            ))

    return obs


def _observe_languages(data: dict) -> list[Observation]:
    """Language composition observations."""
    obs: list[Observation] = []
    breakdown = data.get("language_breakdown", [])

    if len(breakdown) >= 3:
        langs = [f"**{b.get('language', '?')}** ({b.get('files', 0)})" for b in breakdown[:3]]
        obs.append(Observation(
            icon="📊",
            category="health",
            priority=7,
            text=f"Multi-language module: {', '.join(langs)}.",
        ))

    # Check for JS-heavy HTML templates
    jinja_js_count = sum(
        1 for b in breakdown
        if b.get("language") in ("jinja2-js", "html-js")
    )
    if jinja_js_count > 3:
        obs.append(Observation(
            icon="💡",
            category="quality",
            priority=6,
            text=(
                f"**{jinja_js_count} HTML files** are primarily JavaScript wrapped "
                f"in `<script>` tags. Consider extracting to `.js` modules "
                f"for better tooling support."
            ),
        ))

    return obs


# ═══════════════════════════════════════════════════════════════════
#  Phase 8.4 — Comparison & Trend Context
# ═══════════════════════════════════════════════════════════════════


def _observe_comparison(data: dict) -> list[Observation]:
    """Cross-module comparison and trend observations.

    Uses optional keys:
        project_avg_score:  project-wide average health score
        previous_score:     this module's score from the last scan
        cross_language_scores: dict mapping language → avg quality score
    """
    obs: list[Observation] = []
    score = data.get("health_score")
    if score is None:
        return obs

    # ── Cross-module comparison ──
    project_avg = data.get("project_avg_score")
    if project_avg is not None:
        diff = score - project_avg
        if diff >= 1.0:
            obs.append(Observation(
                icon="✅",
                category="trend",
                priority=6,
                text=(
                    f"This module's quality (**{score:.1f}**) is "
                    f"above the project average (**{project_avg:.1f}**)."
                ),
            ))
        elif diff <= -1.0:
            obs.append(Observation(
                icon="⚠️",
                category="trend",
                priority=4,
                text=(
                    f"This module's quality (**{score:.1f}**) is "
                    f"below the project average (**{project_avg:.1f}**)."
                ),
            ))

    # ── Trend detection ──
    prev_score = data.get("previous_score")
    if prev_score is not None:
        delta = score - prev_score
        if delta >= 0.3:
            obs.append(Observation(
                icon="📈",
                category="trend",
                priority=5,
                text=(
                    f"Quality improved **+{delta:.1f}** since last scan "
                    f"(was {prev_score:.1f}, now {score:.1f})."
                ),
            ))
        elif delta <= -0.3:
            obs.append(Observation(
                icon="📉",
                category="trend",
                priority=3,
                text=(
                    f"Quality degraded **{delta:.1f}** since last scan "
                    f"(was {prev_score:.1f}, now {score:.1f})."
                ),
            ))

    # ── Cross-language insight ──
    cross_lang = data.get("cross_language_scores", {})
    if len(cross_lang) >= 2:
        sorted_langs = sorted(cross_lang.items(), key=lambda kv: kv[1])
        worst_lang, worst_q = sorted_langs[0]
        best_lang, best_q = sorted_langs[-1]
        if best_q - worst_q >= 1.5:
            obs.append(Observation(
                icon="📊",
                category="trend",
                priority=6,
                text=(
                    f"**{best_lang.capitalize()}** code is well-maintained "
                    f"(**{best_q:.1f}**), but **{worst_lang.capitalize()}** "
                    f"code lags (**{worst_q:.1f}**)."
                ),
            ))

    return obs


# ═══════════════════════════════════════════════════════════════════
#  Phase 8.5 — Actionable Recommendations
# ═══════════════════════════════════════════════════════════════════


@dataclass
class Recommendation:
    """A specific actionable recommendation."""

    severity: str   # "warning" or "positive"
    icon: str       # ⚠ or ✓
    text: str       # The recommendation text


def generate_recommendations(data: dict) -> list[Recommendation]:
    """Generate specific improvement recommendations.

    Returns a list of concrete, actionable recommendations based
    on detected patterns in the audit data.
    """
    recs: list[Recommendation] = []

    # ── Nesting depth recommendations ──
    hotspots = data.get("hotspots", [])
    for h in hotspots[:5]:
        depth = h.get("max_nesting_depth", 0)
        if depth >= 6:
            file = _short_path(h.get("file", ""))
            recs.append(Recommendation(
                severity="warning",
                icon="⚠",
                text=(
                    f"`{file}` — depth **{depth}** nesting. "
                    f"Consider extracting the inner loop into a helper function."
                ),
            ))

    # ── Large file recommendations ──
    for h in hotspots[:5]:
        lines = h.get("total_lines", 0)
        if lines > 400:
            file = _short_path(h.get("file", ""))
            recs.append(Recommendation(
                severity="warning",
                icon="⚠",
                text=(
                    f"`{file}` — **{lines} lines**. "
                    f"Consider splitting into focused sub-modules."
                ),
            ))

    # ── JS-in-HTML recommendations ──
    breakdown = data.get("language_breakdown", [])
    js_html_count = sum(
        1 for b in breakdown
        if b.get("language") in ("jinja2-js", "html-js")
    )
    if js_html_count > 3:
        recs.append(Recommendation(
            severity="warning",
            icon="⚠",
            text=(
                f"**{js_html_count} HTML files** contain only JavaScript "
                f"(no HTML/template content). Consider renaming to `.js` or "
                f"adding a clear comment about the convention."
            ),
        ))

    # ── Documentation positive ──
    avgs = data.get("subcategory_averages", {})
    doc_score = avgs.get("documentation") or avgs.get("docstrings")
    if doc_score is not None and doc_score >= 8.0:
        file_count = data.get("file_count", 0)
        recs.append(Recommendation(
            severity="positive",
            icon="✓",
            text=(
                f"All {file_count} source files have good documentation "
                f"coverage (**{doc_score:.1f}/10**)."
            ),
        ))

    # ── Missing tests ──
    matched_tests = data.get("matched_tests", [])
    file_count = data.get("file_count", 0)
    if not matched_tests and file_count > 5:
        recs.append(Recommendation(
            severity="warning",
            icon="⚠",
            text=(
                f"No test files found for {file_count} source files. "
                f"Adding unit tests would improve confidence in changes."
            ),
        ))

    return recs


def _observe_recommendations(data: dict) -> list[Observation]:
    """Convert recommendations into narrative observations."""
    recs = generate_recommendations(data)
    if not recs:
        return []

    # Summarize into a single observation
    warnings = [r for r in recs if r.severity == "warning"]
    positives = [r for r in recs if r.severity == "positive"]

    obs: list[Observation] = []

    if warnings:
        obs.append(Observation(
            icon="💡",
            category="recommendation",
            priority=8,
            text=(
                f"**{len(warnings)} improvement suggestion{'s' if len(warnings) != 1 else ''}** "
                f"detected. See the recommendations section below."
            ),
        ))

    if positives and not warnings:
        obs.append(Observation(
            icon="✅",
            category="recommendation",
            priority=9,
            text="No improvement suggestions — all checks passed.",
        ))

    return obs


def render_recommendations_html(data: dict) -> str:
    """Render actionable recommendations as an HTML block.

    Returns a styled recommendations section, or empty string if none.
    """
    recs = generate_recommendations(data)
    if not recs:
        return ""

    lines = [
        '<div class="audit-recommendations" '
        'style="padding:0.75rem;border-radius:6px;'
        "background:rgba(255,193,7,0.06);"
        'margin-bottom:0.5rem">\n'
        '<div style="font-weight:600;margin-bottom:0.3rem;'
        'font-size:0.85rem;color:var(--clr-heading,#e0e0e0)">'
        "📋 Recommendations</div>\n"
        '<ol style="margin:0.25rem 0;padding-left:1.2rem;'
        'font-size:0.82rem;line-height:1.5;color:var(--clr-text,#ccc)">\n'
    ]

    for rec in recs:
        lines.append(f"<li>{rec.icon} {rec.text}</li>\n")

    lines.append("</ol>\n</div>\n")
    return "".join(lines)


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _friendly_name(subcategory: str) -> str:
    """Convert subcategory keys to human-friendly names."""
    return {
        "documentation": "Documentation",
        "docstrings": "Docstrings",
        "complexity": "Complexity",
        "structure": "Structure",
        "naming": "Naming",
        "error_handling": "Error Handling",
        "testing": "Testing",
        "type_annotations": "Type Annotations",
    }.get(subcategory, subcategory.replace("_", " ").title())


def _short_path(path: str) -> str:
    """Shorten a file path for display."""
    parts = path.split("/")
    if len(parts) > 2:
        return "/".join(parts[-2:])
    return path


def render_observations_html(observations: list[Observation]) -> str:
    """Render observations as an HTML block for the audit card.

    Returns a styled `<div>` with each observation as a paragraph.
    """
    if not observations:
        return ""

    lines = [
        '<div class="audit-observations" '
        'style="padding:0.75rem;border-radius:6px;'
        "background:rgba(59,130,246,0.06);"
        'margin-bottom:0.5rem">\n'
        '<div style="font-weight:600;margin-bottom:0.3rem;'
        'font-size:0.85rem;color:var(--clr-heading,#e0e0e0)">'
        "💡 Insights</div>\n"
    ]

    for ob in observations:
        lines.append(
            f'<p style="margin:0.25rem 0;font-size:0.82rem;'
            f'line-height:1.4;color:var(--clr-text,#ccc)">'
            f"{ob.icon} {ob.text}</p>\n"
        )

    lines.append("</div>\n")
    return "".join(lines)
