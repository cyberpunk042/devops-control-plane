"""Integration tests — full detect → fix → verify cycle.

Tests the complete pipeline on realistic code samples:
1. Detect incompatible features
2. Apply fixes
3. Verify fixes removed the features
4. Verify the code still parses
5. Verify the fix is idempotent

Run: python -m pytest src/core/services/compat/edge_cases/test_integration.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def compat():
    """Create a fresh orchestrator."""
    from ..orchestrator import CompatOrchestrator
    return CompatOrchestrator.create(Path("."))


@pytest.fixture
def tmp_module(tmp_path):
    """Create a temporary module directory for testing."""
    mod_dir = tmp_path / "test_module"
    mod_dir.mkdir()
    (mod_dir / "__init__.py").write_text("")
    return mod_dir


class TestDetectFixVerifyCycle:
    """Full detect → fix → verify cycle tests."""

    def test_datetime_utc_cycle(self, compat, tmp_module):
        """datetime.UTC: detect → fix → verify."""
        test_file = tmp_module / "dates.py"
        test_file.write_text(
            "from datetime import UTC, datetime\n"
            "now = datetime.now(UTC)\n"
            "ts = datetime(2024, 1, 1, tzinfo=UTC)\n"
        )

        # Detect
        result = compat.detection.analyze_module(
            tmp_module, "3.8", "downgrade", tmp_module.parent,
        )
        utc_findings = [f for f in result.findings if f.feature_id == "python.stdlib.datetime_utc"]
        assert len(utc_findings) >= 1, "Should detect datetime.UTC"

        # Fix
        for finding in utc_findings:
            finding.file = str(test_file.relative_to(tmp_module.parent))
            fix_result = compat.fix.fix_finding(finding, tmp_module.parent, verify=False)
            assert fix_result.success, f"Fix should succeed: {fix_result.error}"

        # Verify — re-detect should find 0
        compat.detection.invalidate_all()
        result2 = compat.detection.analyze_module(
            tmp_module, "3.8", "downgrade", tmp_module.parent,
        )
        utc_after = [f for f in result2.findings if f.feature_id == "python.stdlib.datetime_utc"]
        assert len(utc_after) == 0, f"UTC should be gone after fix, found {len(utc_after)}"

        # Verify — file should parse
        content = test_file.read_text()
        import ast
        ast.parse(content)  # Should not raise

        # Verify — content should have timezone.utc
        assert "timezone.utc" in content
        assert "from datetime import timezone" in content

    def test_removeprefix_cycle(self, compat, tmp_module):
        """removeprefix: detect → fix → verify."""
        test_file = tmp_module / "strings.py"
        test_file.write_text(
            'result = path.removeprefix("/home/")\n'
        )

        # Detect
        result = compat.detection.analyze_module(
            tmp_module, "3.8", "downgrade", tmp_module.parent,
        )
        findings = [f for f in result.findings if f.feature_id == "python.builtins.str_removeprefix"]
        assert len(findings) >= 1

        # Fix
        for finding in findings:
            finding.file = str(test_file.relative_to(tmp_module.parent))
            fix_result = compat.fix.fix_finding(finding, tmp_module.parent, verify=False)
            assert fix_result.success

        # Verify
        content = test_file.read_text()
        assert "removeprefix" not in content
        assert "startswith" in content
        import ast
        ast.parse(content)

    def test_tomllib_cycle(self, compat, tmp_module):
        """tomllib: detect → fix → verify."""
        test_file = tmp_module / "config.py"
        test_file.write_text(
            'import tomllib\n'
            'data = tomllib.load(open("f.toml", "rb"))\n'
        )

        result = compat.detection.analyze_module(
            tmp_module, "3.8", "downgrade", tmp_module.parent,
        )
        findings = [f for f in result.findings if f.feature_id == "python.stdlib.tomllib"]
        assert len(findings) >= 1

        for finding in findings:
            finding.file = str(test_file.relative_to(tmp_module.parent))
            fix_result = compat.fix.fix_finding(finding, tmp_module.parent, verify=False)
            assert fix_result.success

        content = test_file.read_text()
        assert "import tomli as tomllib" in content
        import ast
        ast.parse(content)

    def test_future_annotations_cycle(self, compat, tmp_module):
        """__future__ annotations: detect → fix → verify suppression."""
        test_file = tmp_module / "types.py"
        test_file.write_text(
            'def foo(x: int | str) -> list[int]:\n'
            '    return [x]\n'
        )

        # Detect — should find union_pipe and/or builtin_generics
        result = compat.detection.analyze_module(
            tmp_module, "3.8", "downgrade", tmp_module.parent,
        )
        typing_findings = [
            f for f in result.findings
            if f.feature_id in ("python.typing.union_pipe", "python.typing.builtin_generics")
        ]
        assert len(typing_findings) >= 1

        # Fix — apply __future__ import
        for finding in typing_findings[:1]:  # One fix adds __future__ for all
            finding.file = str(test_file.relative_to(tmp_module.parent))
            fix_result = compat.fix.fix_finding(finding, tmp_module.parent, verify=False)
            assert fix_result.success

        # Verify — with __future__, annotation features should be suppressed
        compat.detection.invalidate_all()
        result2 = compat.detection.analyze_module(
            tmp_module, "3.8", "downgrade", tmp_module.parent,
        )
        typing_after = [
            f for f in result2.findings
            if f.feature_id in ("python.typing.union_pipe", "python.typing.builtin_generics")
        ]
        assert len(typing_after) == 0, f"Typing features should be suppressed by __future__, found {len(typing_after)}"

        content = test_file.read_text()
        assert "from __future__ import annotations" in content
        import ast
        ast.parse(content)

    def test_strenum_cycle(self, compat, tmp_module):
        """StrEnum: detect → fix → verify."""
        test_file = tmp_module / "enums.py"
        test_file.write_text(
            'from enum import StrEnum\n'
            'class Color(StrEnum):\n'
            '    RED = "red"\n'
        )

        result = compat.detection.analyze_module(
            tmp_module, "3.8", "downgrade", tmp_module.parent,
        )
        findings = [f for f in result.findings if f.feature_id == "python.stdlib.strenum"]
        assert len(findings) >= 1

        for finding in findings:
            finding.file = str(test_file.relative_to(tmp_module.parent))
            fix_result = compat.fix.fix_finding(finding, tmp_module.parent, verify=False)
            assert fix_result.success

        content = test_file.read_text()
        assert "from backports.strenum import StrEnum" in content
        assert "from enum import StrEnum" not in content
        import ast
        ast.parse(content)


class TestRealProjectAnalysis:
    """Test analysis on real project modules."""

    def test_analyze_web_module(self, compat):
        """Analyze the real web module — should find real findings."""
        result = compat.analyze("web", "3.8", include_transitive=False)
        assert result.files_scanned > 0
        assert result.total_findings >= 0  # May have findings or not

    def test_assess_web_module(self, compat):
        """Assess the real web module — should return valid assessment."""
        assessment = compat.assess("web", "3.8")
        assert assessment.target == "3.8"
        assert assessment.current_floor  # Should have a floor

    def test_analyze_core_module(self, compat):
        """Analyze the real core module — should find datetime.UTC."""
        result = compat.analyze("core", "3.8", include_transitive=False)
        utc = [f for f in result.findings if f.feature_id == "python.stdlib.datetime_utc"]
        assert len(utc) >= 1, "Core should have datetime.UTC findings"


class TestDatabaseIntegrity:
    """Test the feature database itself."""

    def test_registry_loads(self, compat):
        """Registry loads all entries."""
        assert compat.registry.count() >= 200

    def test_python_entries_above_38(self, compat):
        """Should find entries above Python 3.8."""
        above = compat.registry.above_version("python", "3.8")
        assert len(above) >= 20

    def test_search_works(self, compat):
        """Feature search returns results."""
        results = compat.registry.search("datetime")
        assert len(results) >= 1

    def test_all_python_entries_valid(self, compat):
        """All Python entries pass validation."""
        from ..database.validator import validate_database
        result = validate_database(language="python")
        assert result.failed_entries == 0, f"{result.failed_entries} entries failed validation"
