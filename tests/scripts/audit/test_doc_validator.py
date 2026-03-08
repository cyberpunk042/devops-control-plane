"""Tests for doc_validator module."""

import textwrap
from pathlib import Path

import pytest

from src.core.data.script_templates.audit.doc_validator import (
    DocAuditResult,
    DocValidator,
)


# ═══════════════════════════════════════════════════════════════════
#  Data model tests
# ═══════════════════════════════════════════════════════════════════


def test_empty_result():
    result = DocAuditResult()
    assert result.total_docs == 0
    assert result.overall_freshness == 1.0


# ═══════════════════════════════════════════════════════════════════
#  DocValidator — file references
# ═══════════════════════════════════════════════════════════════════


def test_valid_file_reference(tmp_path):
    # Create the referenced file
    (tmp_path / "src" / "core").mkdir(parents=True)
    (tmp_path / "src" / "core" / "service.py").write_text("class Service: pass")

    # Create a doc that references it
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "arch.md").write_text(
        "The service is in `src/core/service.py`."
    )

    validator = DocValidator()
    result = validator.analyze(tmp_path, doc_dirs=["docs"])

    assert result.total_references == 1
    assert result.total_valid == 1
    assert result.total_stale == 0


def test_stale_file_reference(tmp_path):
    # Don't create the referenced file
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "arch.md").write_text(
        "The service is in `src/core/old_service.py`."
    )

    validator = DocValidator()
    result = validator.analyze(tmp_path, doc_dirs=["docs"])

    assert result.total_references == 1
    assert result.total_stale == 1
    ref = result.files[0].stale_references[0]
    assert ref.reference_type == "file"
    assert "does not exist" in ref.issue


def test_multiple_references(tmp_path):
    # Create one file, leave the other missing
    (tmp_path / "src" / "core").mkdir(parents=True)
    (tmp_path / "src" / "core" / "good.py").write_text("pass")

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "readme.md").write_text(textwrap.dedent("""
        # Architecture

        The good module: `src/core/good.py`
        The bad module: `src/core/gone.py`
    """))

    validator = DocValidator()
    result = validator.analyze(tmp_path, doc_dirs=["docs"])

    assert result.total_references == 2
    assert result.total_valid == 1
    assert result.total_stale == 1


# ═══════════════════════════════════════════════════════════════════
#  DocValidator — function references
# ═══════════════════════════════════════════════════════════════════


def test_valid_function_reference(tmp_path):
    (tmp_path / "src" / "core").mkdir(parents=True)
    (tmp_path / "src" / "core" / "ops.py").write_text("def process_data(): pass")

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "api.md").write_text(textwrap.dedent("""
        See `src/core/ops.py` for details.
        The main entry point is `process_data()`.
    """))

    validator = DocValidator()
    result = validator.analyze(tmp_path, doc_dirs=["docs"])

    # Should find: 1 file ref (valid) + 1 func ref (valid)
    assert result.total_valid == 2
    assert result.total_stale == 0


def test_stale_function_reference(tmp_path):
    (tmp_path / "src" / "core").mkdir(parents=True)
    (tmp_path / "src" / "core" / "ops.py").write_text("def other_func(): pass")

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "api.md").write_text(textwrap.dedent("""
        See `src/core/ops.py` for details.
        The main entry point is `deleted_function()`.
    """))

    validator = DocValidator()
    result = validator.analyze(tmp_path, doc_dirs=["docs"])

    # File ref valid, func ref stale
    assert result.total_valid == 1
    assert result.total_stale == 1
    stale = result.files[0].stale_references[0]
    assert stale.reference_type == "function"
    assert "not found" in stale.issue


# ═══════════════════════════════════════════════════════════════════
#  DocValidator — freshness
# ═══════════════════════════════════════════════════════════════════


def test_freshness_calculation(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("pass")

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "test.md").write_text(textwrap.dedent("""
        Good: `src/a.py`
        Bad: `src/b.py`
        Also bad: `src/c.py`
    """))

    validator = DocValidator()
    result = validator.analyze(tmp_path, doc_dirs=["docs"])

    # 1 valid, 2 stale → 33.3% fresh
    assert result.total_references == 3
    assert abs(result.overall_freshness - 1 / 3) < 0.01


def test_no_references(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "plain.md").write_text(
        "This document has no code references at all."
    )

    validator = DocValidator()
    result = validator.analyze(tmp_path, doc_dirs=["docs"])

    assert result.total_references == 0
    assert result.overall_freshness == 1.0


# ═══════════════════════════════════════════════════════════════════
#  DocValidator — edge cases
# ═══════════════════════════════════════════════════════════════════


def test_non_source_paths_ignored(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "readme.md").write_text(textwrap.dedent("""
        Visit `https://example.com` for more info.
        The config is in `config.yaml` (no src/ prefix).
        Normal text with `backticks`.
    """))

    validator = DocValidator()
    result = validator.analyze(tmp_path, doc_dirs=["docs"])

    # None of these should be detected as source file references
    assert result.total_references == 0


def test_multiple_doc_dirs(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("pass")

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("See `src/app.py`")

    (tmp_path / "guides").mkdir()
    (tmp_path / "guides" / "b.md").write_text("See `src/missing.py`")

    validator = DocValidator()
    result = validator.analyze(tmp_path, doc_dirs=["docs", "guides"])

    assert result.total_docs == 2
    assert result.total_valid == 1
    assert result.total_stale == 1


# ═══════════════════════════════════════════════════════════════════
#  Integration: real project
# ═══════════════════════════════════════════════════════════════════


def test_real_project_docs():
    root = Path(".")
    if not (root / "docs").is_dir():
        pytest.skip("Not in project root")

    validator = DocValidator()
    result = validator.analyze(root, doc_dirs=["docs"])

    # We know from investigation:
    # - 100+ docs
    # - Some stale references exist (CONSOLIDATION_AUDIT.md, etc.)
    assert result.total_docs >= 10
    assert result.total_stale > 0

    # CONSOLIDATION_AUDIT.md should have stale refs
    consolidation = next(
        (f for f in result.files if "CONSOLIDATION" in f.doc_file),
        None,
    )
    assert consolidation is not None
    assert len(consolidation.stale_references) > 0
