"""Tests for code_hygiene audit script."""

import json
from pathlib import Path

import pytest

from src.core.data.script_templates.audit.code_hygiene import (
    _render_json,
    _render_markdown,
    _render_smart_markdown,
)
from src.core.data.script_templates.audit.init_analyzer import (
    InitAuditResult,
    InitFileAnalysis,
    InitFunctionInfo,
    InitClassInfo,
)
from src.core.data.script_templates.audit.doc_validator import (
    DocAuditResult,
    DocFileAnalysis,
    DocReference,
)


# ═══════════════════════════════════════════════════════════════════
#  Test fixtures
# ═══════════════════════════════════════════════════════════════════


def _make_init_result() -> InitAuditResult:
    clean = InitFileAnalysis(
        file_path="src/core/__init__.py",
        language="python",
        total_lines=5,
        code_lines=3,
        import_count=2,
    )
    with_funcs = InitFileAnalysis(
        file_path="src/ui/web/routes/tab_mesh/__init__.py",
        language="python",
        total_lines=966,
        code_lines=742,
        functions=[
            InitFunctionInfo("_is_wsl", 10, 20, 10, has_docstring=True),
            InitFunctionInfo("kill_chrome", 25, 50, 25, has_docstring=True),
            InitFunctionInfo("restart_chrome", 55, 140, 87, has_docstring=True),
        ],
        has_complex_logic=False,
    )
    with_class = InitFileAnalysis(
        file_path="src/core/data/__init__.py",
        language="python",
        total_lines=298,
        code_lines=209,
        classes=[
            InitClassInfo("DataManager", 50, 150, 100, method_count=5),
        ],
    )
    return InitAuditResult(
        language="python",
        files=[clean, with_funcs, with_class],
    )


def _make_doc_result() -> DocAuditResult:
    good_ref = DocReference(
        doc_file="docs/ARCH.md",
        doc_line=10,
        reference_type="file",
        reference_text="`src/core/service.py`",
        target_file="src/core/service.py",
        is_valid=True,
    )
    stale_ref = DocReference(
        doc_file="docs/ARCH.md",
        doc_line=25,
        reference_type="file",
        reference_text="`src/core/old_service.py`",
        target_file="src/core/old_service.py",
        is_valid=False,
        issue="File does not exist",
    )
    fa = DocFileAnalysis(
        doc_file="docs/ARCH.md",
        total_references=2,
        valid_references=1,
        stale_references=[stale_ref],
        all_references=[good_ref, stale_ref],
    )
    return DocAuditResult(files=[fa])


# ═══════════════════════════════════════════════════════════════════
#  Markdown — both sub-audits
# ═══════════════════════════════════════════════════════════════════


def test_markdown_both():
    md = _render_markdown(_make_init_result(), _make_doc_result())
    assert "# Code Hygiene Audit" in md
    assert "Module-Index Leak Detection" in md
    assert "Documentation Freshness" in md


def test_markdown_init_only():
    md = _render_markdown(_make_init_result(), None)
    assert "Module-Index Leak Detection" in md
    assert "Documentation Freshness" not in md


def test_markdown_docs_only():
    md = _render_markdown(None, _make_doc_result())
    assert "Module-Index Leak Detection" not in md
    assert "Documentation Freshness" in md


# ═══════════════════════════════════════════════════════════════════
#  Markdown — init section
# ═══════════════════════════════════════════════════════════════════


def test_markdown_init_summary():
    md = _render_markdown(_make_init_result(), None)
    assert "Total `__init__.py` files | 3" in md
    assert "Clean (imports/exports only) | 1" in md
    assert "With functions or classes | 2" in md


def test_markdown_init_files_table():
    md = _render_markdown(_make_init_result(), None)
    assert "tab_mesh" in md
    assert "966" in md
    assert "core/data" in md


def test_markdown_init_function_details():
    md = _render_markdown(_make_init_result(), None)
    assert "`kill_chrome`" in md
    assert "`restart_chrome`" in md


# ═══════════════════════════════════════════════════════════════════
#  Markdown — docs section
# ═══════════════════════════════════════════════════════════════════


def test_markdown_doc_summary():
    md = _render_markdown(None, _make_doc_result())
    assert "Documents scanned | 1" in md
    assert "Stale references | 1" in md


def test_markdown_stale_references():
    md = _render_markdown(None, _make_doc_result())
    assert "old_service.py" in md
    assert "File does not exist" in md


def test_markdown_no_judgment():
    md = _render_markdown(_make_init_result(), _make_doc_result())
    md_lower = md.lower()
    assert "violation" not in md_lower
    assert "non-compliant" not in md_lower
    assert "failing" not in md_lower


# ═════════════════════════════════════════════════════════════════
#  Smart markdown
# ═════════════════════════════════════════════════════════════════


def test_smart_header():
    md = _render_smart_markdown(_make_init_result(), _make_doc_result())
    assert "# Code Hygiene Audit" in md
    assert "Style: **smart**" in md


def test_smart_executive_summary():
    md = _render_smart_markdown(_make_init_result(), _make_doc_result())
    assert "## Executive Summary" in md
    assert "**3**" in md  # total leaked functions
    assert "**1**" in md  # clean files


def test_smart_severity_tiers():
    md = _render_smart_markdown(_make_init_result(), None)
    assert "## Severity Tiers" in md
    assert "🔴 Critical" in md  # 966 lines = critical
    assert "🟡 Major" in md
    assert "🟢 Minor" in md


def test_smart_domain_analysis():
    md = _render_smart_markdown(_make_init_result(), None)
    assert "## Domain Analysis" in md
    assert "🌐 Web Routes" in md  # tab_mesh is in ui/web/routes


def test_smart_doc_freshness_dashboard():
    md = _render_smart_markdown(None, _make_doc_result())
    assert "## Documentation Freshness Dashboard" in md
    assert "█" in md  # visual bars
    assert "░" in md


def test_smart_cross_reference():
    md = _render_smart_markdown(_make_init_result(), _make_doc_result())
    assert "## Cross-Reference" in md


def test_smart_no_judgment():
    md = _render_smart_markdown(_make_init_result(), _make_doc_result())
    md_lower = md.lower()
    assert "violation" not in md_lower
    assert "non-compliant" not in md_lower
    assert "failing" not in md_lower


# ═══════════════════════════════════════════════════════════════════
#  JSON
# ═══════════════════════════════════════════════════════════════════


def test_json_valid():
    raw = _render_json(_make_init_result(), _make_doc_result())
    data = json.loads(raw)
    assert isinstance(data, dict)


def test_json_both_sections():
    raw = _render_json(_make_init_result(), _make_doc_result())
    data = json.loads(raw)
    assert "init_leaks" in data
    assert "doc_freshness" in data


def test_json_init_only():
    raw = _render_json(_make_init_result(), None)
    data = json.loads(raw)
    assert "init_leaks" in data
    assert "doc_freshness" not in data


def test_json_init_data():
    raw = _render_json(_make_init_result(), None)
    data = json.loads(raw)
    init = data["init_leaks"]
    assert init["total_files"] == 3
    assert init["clean_files"] == 1
    assert init["total_leaked_functions"] == 3
    # Only files with logic should be in the list
    assert len(init["files"]) == 2


def test_json_doc_data():
    raw = _render_json(None, _make_doc_result())
    data = json.loads(raw)
    docs = data["doc_freshness"]
    assert docs["total_references"] == 2
    assert docs["stale_references"] == 1
    assert len(docs["stale_details"]) == 1


# ═══════════════════════════════════════════════════════════════════
#  Integration: real project
# ═══════════════════════════════════════════════════════════════════


def test_realproject_full():
    root = Path(".")
    if not (root / "src").is_dir():
        pytest.skip("Not in project root")

    from src.core.data.script_templates.audit.init_analyzer import PythonInitAnalyzer
    from src.core.data.script_templates.audit.doc_validator import DocValidator

    init_result = PythonInitAnalyzer().analyze(root)
    doc_result = DocValidator().analyze(root, doc_dirs=["docs"])

    md = _render_markdown(init_result, doc_result)

    assert "# Code Hygiene Audit" in md
    assert "tab_mesh" in md
    lines = md.split("\n")
    assert len(lines) > 100
