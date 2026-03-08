"""Tests for route_quality audit script."""

import json
import textwrap
from pathlib import Path

import pytest

from src.core.data.script_templates.audit.route_analyzer import (
    BlueprintInfo,
    RouteAuditResult,
    RouteInfo,
)
from src.core.data.script_templates.audit.route_quality import (
    _render_json,
    _render_markdown,
    _render_smart_markdown,
)


# ═══════════════════════════════════════════════════════════════════
#  Test fixtures
# ═══════════════════════════════════════════════════════════════════


def _make_result() -> RouteAuditResult:
    """Build a small but realistic RouteAuditResult for testing."""
    r1 = RouteInfo(
        function_name="vault_list",
        endpoint="/api/vault/list",
        blueprint="vault",
        file_path="src/ui/web/routes/vault/keys.py",
        lineno=10,
        end_lineno=25,
        http_methods=["GET"],
        methods_explicit=True,
        has_docstring=True,
        docstring_lines=3,
        has_auth=False,
        has_run_tracking=True,
        has_error_handling=True,
        return_type="json",
        decorators=["route", "run_tracked"],
        body_lines=15,
    )
    r2 = RouteInfo(
        function_name="vault_create",
        endpoint="/api/vault/create",
        blueprint="vault",
        file_path="src/ui/web/routes/vault/keys.py",
        lineno=30,
        end_lineno=50,
        http_methods=["POST"],
        methods_explicit=True,
        has_docstring=True,
        docstring_lines=2,
        has_auth=True,
        has_run_tracking=True,
        has_error_handling=True,
        return_type="json",
        decorators=["route", "requires_gh_auth", "run_tracked"],
        body_lines=20,
    )
    r3 = RouteInfo(
        function_name="dev_status",
        endpoint="/api/dev/status",
        blueprint="dev",
        file_path="src/ui/web/routes/dev/__init__.py",
        lineno=5,
        end_lineno=15,
        http_methods=["GET"],
        methods_explicit=False,
        has_docstring=False,
        has_auth=False,
        has_run_tracking=False,
        has_error_handling=False,
        return_type="json",
        decorators=["route"],
        body_lines=10,
    )

    bp_vault = BlueprintInfo(
        name="vault",
        package_path="src/ui/web/routes/vault",
        routes=[r1, r2],
        init_lines=20,
        init_has_route_handlers=False,
    )
    bp_dev = BlueprintInfo(
        name="dev",
        package_path="src/ui/web/routes/dev",
        routes=[r3],
        init_lines=86,
        init_has_route_handlers=True,
    )

    return RouteAuditResult(
        framework="flask",
        blueprints=[bp_vault, bp_dev],
    )


# ═══════════════════════════════════════════════════════════════════
#  Markdown report
# ═══════════════════════════════════════════════════════════════════


def test_markdown_has_header():
    result = _make_result()
    md = _render_markdown(result)
    assert "# Route Quality Audit" in md
    assert "Framework: flask" in md
    assert "2 blueprints" in md
    assert "3 routes" in md


def test_markdown_has_toc():
    result = _make_result()
    md = _render_markdown(result)
    assert "## Table of Contents" in md
    assert "Coverage Summary" in md
    assert "Blueprint Details" in md


def test_markdown_coverage_facts():
    result = _make_result()
    md = _render_markdown(result)
    # Docstring: 2 out of 3
    assert "Docstring" in md
    assert "66.7%" in md
    # Auth: 1 out of 3
    assert "Auth decorator" in md
    assert "33.3%" in md


def test_markdown_return_types():
    result = _make_result()
    md = _render_markdown(result)
    assert "## Return Type Distribution" in md
    assert "json" in md


def test_markdown_init_observations():
    result = _make_result()
    md = _render_markdown(result)
    assert "## Init-File Observations" in md
    # dev has route handlers in __init__
    assert "dev" in md
    assert "86" in md  # init_lines for dev


def test_markdown_blueprint_details():
    result = _make_result()
    md = _render_markdown(result)
    assert "### vault" in md
    assert "### dev" in md
    # dev should have the init marker
    assert "📌" in md
    # vault should not
    vault_section = md.split("### vault")[1].split("###")[0]
    assert "📌" not in vault_section


def test_markdown_route_table():
    result = _make_result()
    md = _render_markdown(result)
    assert "`vault_list`" in md
    assert "`/api/vault/list`" in md
    assert "`vault_create`" in md


def test_markdown_no_judgment_language():
    """Report should observe, not judge — no 'violation', 'fail', 'error' language."""
    result = _make_result()
    md = _render_markdown(result)
    md_lower = md.lower()
    # These words should NOT appear — this is an observation report
    assert "violation" not in md_lower
    assert "non-compliant" not in md_lower
    assert "failing" not in md_lower


# ═══════════════════════════════════════════════════════════════════
#  Smart markdown report
# ═══════════════════════════════════════════════════════════════════


def test_smart_has_header():
    result = _make_result()
    md = _render_smart_markdown(result)
    assert "# Route Quality Audit" in md
    assert "Style: **smart**" in md


def test_smart_executive_summary():
    result = _make_result()
    md = _render_smart_markdown(result)
    assert "## Executive Summary" in md
    assert "**3**" in md  # total routes
    assert "**2**" in md  # total blueprints


def test_smart_coverage_dashboard():
    result = _make_result()
    md = _render_smart_markdown(result)
    assert "## Coverage Dashboard" in md
    assert "█" in md  # visual bars
    assert "░" in md  # visual bars


def test_smart_maturity_matrix():
    result = _make_result()
    md = _render_smart_markdown(result)
    assert "## Blueprint Maturity Matrix" in md
    assert "**vault**" in md
    assert "**dev**" in md


def test_smart_hotspot_analysis():
    result = _make_result()
    md = _render_smart_markdown(result)
    assert "## Hotspot Analysis" in md
    assert "Largest Route Handlers" in md


def test_smart_pattern_analysis():
    result = _make_result()
    md = _render_smart_markdown(result)
    assert "## Pattern Analysis" in md
    assert "HTTP Method Distribution" in md
    assert "Decorator Patterns" in md


def test_smart_no_judgment():
    result = _make_result()
    md = _render_smart_markdown(result)
    md_lower = md.lower()
    assert "violation" not in md_lower
    assert "non-compliant" not in md_lower
    assert "failing" not in md_lower


# ═══════════════════════════════════════════════════════════════════
#  JSON report
# ═══════════════════════════════════════════════════════════════════


def test_json_valid():
    result = _make_result()
    raw = _render_json(result)
    data = json.loads(raw)
    assert isinstance(data, dict)


def test_json_structure():
    result = _make_result()
    raw = _render_json(result)
    data = json.loads(raw)

    assert data["framework"] == "flask"
    assert data["total_blueprints"] == 2
    assert data["total_routes"] == 3
    assert "coverage" in data
    assert "blueprints" in data


def test_json_coverage():
    result = _make_result()
    raw = _render_json(result)
    data = json.loads(raw)

    cov = data["coverage"]
    assert cov["has_docstring"]["with"] == 2
    assert cov["has_docstring"]["without"] == 1
    assert cov["has_docstring"]["total"] == 3
    assert cov["has_auth"]["with"] == 1


def test_json_blueprints():
    result = _make_result()
    raw = _render_json(result)
    data = json.loads(raw)

    bps = {bp["name"]: bp for bp in data["blueprints"]}
    assert "vault" in bps
    assert "dev" in bps
    assert len(bps["vault"]["routes"]) == 2
    assert bps["dev"]["init_has_route_handlers"] is True


# ═══════════════════════════════════════════════════════════════════
#  Integration: real project
# ═══════════════════════════════════════════════════════════════════


def test_realproject_markdown():
    """Integration: generate markdown report from real project routes."""
    root = Path(".")
    if not (root / "src" / "ui" / "web" / "routes").is_dir():
        pytest.skip("Not in project root")

    from src.core.data.script_templates.audit.route_analyzer import (
        FlaskRouteAnalyzer,
    )

    analyzer = FlaskRouteAnalyzer()
    result = analyzer.analyze(root)

    md = _render_markdown(result)

    # Basic structure checks
    assert "# Route Quality Audit" in md
    assert "## Coverage Summary" in md
    assert "## Blueprint Details" in md

    # Should have substantial content
    lines = md.split("\n")
    assert len(lines) > 100

    # Should report the tab_mesh init leak
    assert "tab_mesh" in md
    assert "📌" in md


def test_realproject_json():
    """Integration: generate JSON report from real project routes."""
    root = Path(".")
    if not (root / "src" / "ui" / "web" / "routes").is_dir():
        pytest.skip("Not in project root")

    from src.core.data.script_templates.audit.route_analyzer import (
        FlaskRouteAnalyzer,
    )

    analyzer = FlaskRouteAnalyzer()
    result = analyzer.analyze(root)

    raw = _render_json(result)
    data = json.loads(raw)

    assert data["total_routes"] >= 400
    assert data["coverage"]["has_docstring"]["percent"] > 95
