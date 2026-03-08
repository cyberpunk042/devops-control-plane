"""Tests for init_analyzer module."""

import textwrap
from pathlib import Path

import pytest

from src.core.data.script_templates.audit.init_analyzer import (
    InitAuditResult,
    InitFileAnalysis,
    InitFunctionInfo,
    PythonInitAnalyzer,
)


# ═══════════════════════════════════════════════════════════════════
#  Data model tests
# ═══════════════════════════════════════════════════════════════════


def test_init_file_analysis_defaults():
    a = InitFileAnalysis(file_path="test/__init__.py", language="python")
    assert a.function_count == 0
    assert a.class_count == 0
    assert a.is_clean is True
    assert a.logic_lines == 0


def test_init_file_analysis_with_functions():
    a = InitFileAnalysis(
        file_path="test/__init__.py",
        language="python",
        functions=[
            InitFunctionInfo("foo", 1, 10, 9),
            InitFunctionInfo("bar", 12, 20, 8),
        ],
    )
    assert a.function_count == 2
    assert a.is_clean is False
    assert a.total_function_lines == 17


def test_audit_result_counts():
    clean = InitFileAnalysis(
        file_path="a/__init__.py", language="python",
    )
    with_logic = InitFileAnalysis(
        file_path="b/__init__.py", language="python",
        functions=[InitFunctionInfo("x", 1, 5, 4)],
    )
    result = InitAuditResult(language="python", files=[clean, with_logic])
    assert result.total_files == 2
    assert result.clean_files == 1
    assert result.files_with_logic == 1
    assert result.total_leaked_functions == 1


# ═══════════════════════════════════════════════════════════════════
#  PythonInitAnalyzer — single file analysis
# ═══════════════════════════════════════════════════════════════════


def test_clean_init(tmp_path):
    pkg = tmp_path / "src" / "mypackage"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(textwrap.dedent("""
        \"\"\"My package.\"\"\"
        from .module_a import ClassA
        from .module_b import ClassB

        __all__ = ["ClassA", "ClassB"]
    """))

    analyzer = PythonInitAnalyzer()
    result = analyzer.analyze(tmp_path)

    assert result.total_files == 1
    assert result.clean_files == 1
    f = result.files[0]
    assert f.is_clean is True
    assert f.import_count == 2
    assert f.has_all_export is True


def test_init_with_functions(tmp_path):
    pkg = tmp_path / "src" / "mypackage"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(textwrap.dedent('''
        """My package."""
        from flask import Blueprint

        bp = Blueprint("mypackage", __name__)

        @bp.route("/status")
        def status():
            """Get status."""
            return {"ok": True}

        @bp.route("/create", methods=["POST"])
        def create():
            """Create something."""
            data = validate()
            result = process(data)
            return {"id": result.id}
    '''))

    analyzer = PythonInitAnalyzer()
    result = analyzer.analyze(tmp_path)

    assert result.files_with_logic == 1
    f = result.files[0]
    assert f.function_count == 2
    assert not f.is_clean


def test_init_with_class(tmp_path):
    pkg = tmp_path / "src" / "mypackage"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(textwrap.dedent("""
        class MyParser:
            def parse(self, data):
                return data.split(",")

            def validate(self, data):
                return len(data) > 0
    """))

    analyzer = PythonInitAnalyzer()
    result = analyzer.analyze(tmp_path)

    assert result.total_leaked_classes == 1
    f = result.files[0]
    assert f.class_count == 1
    assert f.classes[0].method_count == 2


def test_trivial_function(tmp_path):
    pkg = tmp_path / "src" / "mypackage"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(textwrap.dedent("""
        def get_version():
            return "1.0.0"
    """))

    analyzer = PythonInitAnalyzer()
    result = analyzer.analyze(tmp_path)

    f = result.files[0]
    assert f.functions[0].is_trivial is True


def test_complex_logic(tmp_path):
    pkg = tmp_path / "src" / "mypackage"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(textwrap.dedent("""
        import os

        for key in os.environ:
            if key.startswith("MY_"):
                print(key)
    """))

    analyzer = PythonInitAnalyzer()
    result = analyzer.analyze(tmp_path)

    f = result.files[0]
    assert f.has_complex_logic is True


def test_type_checking_not_complex(tmp_path):
    pkg = tmp_path / "src" / "mypackage"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(textwrap.dedent("""
        from __future__ import annotations
        from typing import TYPE_CHECKING

        if TYPE_CHECKING:
            from .types import MyType
    """))

    analyzer = PythonInitAnalyzer()
    result = analyzer.analyze(tmp_path)

    f = result.files[0]
    assert f.has_complex_logic is False
    assert f.is_clean is True


def test_scope_filter(tmp_path):
    (tmp_path / "src" / "core" / "services").mkdir(parents=True)
    (tmp_path / "src" / "ui" / "web").mkdir(parents=True)

    (tmp_path / "src" / "core" / "services" / "__init__.py").write_text(
        "def foo(): pass"
    )
    (tmp_path / "src" / "ui" / "web" / "__init__.py").write_text(
        "def bar(): pass"
    )

    analyzer = PythonInitAnalyzer()

    # Full scan
    full = analyzer.analyze(tmp_path)
    assert full.total_files == 2

    # Scoped to core
    scoped = analyzer.analyze(tmp_path, scope="core")
    assert scoped.total_files == 1
    assert scoped.files[0].file_path.endswith("core/services/__init__.py")


# ═══════════════════════════════════════════════════════════════════
#  Integration: real project
# ═══════════════════════════════════════════════════════════════════


def test_real_project():
    root = Path(".")
    if not (root / "src").is_dir():
        pytest.skip("Not in project root")

    analyzer = PythonInitAnalyzer()
    result = analyzer.analyze(root)

    # We know from investigation:
    assert result.total_files >= 100
    assert result.clean_files >= 80
    assert result.files_with_logic >= 30
    assert result.total_leaked_functions >= 100

    # tab_mesh is the biggest offender
    tab_mesh = next(
        (f for f in result.files if "tab_mesh" in f.file_path),
        None,
    )
    assert tab_mesh is not None
    assert tab_mesh.function_count >= 20
    assert tab_mesh.total_lines >= 900
