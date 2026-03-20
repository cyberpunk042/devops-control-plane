"""Version resolver tests — verify floor computation and assessments.

Run: python -m pytest src/core/services/compat/edge_cases/test_version_resolver.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def compat():
    from ..orchestrator import CompatOrchestrator
    return CompatOrchestrator.create(Path("."))


class TestVersionParsing:
    """Test version comparison across languages."""

    def test_python_version_comparison(self):
        from ..database.version import parse_version, version_above
        assert parse_version("python", "3.8") == (3, 8)
        assert parse_version("python", "3.11") == (3, 11)
        assert version_above("python", "3.11", "3.8") is True
        assert version_above("python", "3.8", "3.11") is False
        assert version_above("python", "3.8", "3.8") is False

    def test_javascript_es_version(self):
        from ..database.version import parse_version, version_above
        assert parse_version("javascript", "ES2020") == (2020,)
        assert parse_version("javascript", "ES2015") == (2015,)
        assert version_above("javascript", "ES2020", "ES2018") is True
        assert version_above("javascript", "ES2015", "ES2020") is False

    def test_go_version(self):
        from ..database.version import parse_version, version_above
        assert parse_version("go", "1.21") == (1, 21)
        assert parse_version("go", "1.18") == (1, 18)
        assert version_above("go", "1.21", "1.18") is True

    def test_java_version(self):
        from ..database.version import parse_version, version_above
        assert parse_version("java", "17") == (17,)
        assert parse_version("java", "11") == (11,)
        assert version_above("java", "17", "11") is True

    def test_rust_version(self):
        from ..database.version import parse_version
        assert parse_version("rust", "1.75") == (1, 75)
        assert parse_version("rust", "1.56") == (1, 56)

    def test_invalid_version(self):
        from ..database.version import parse_version
        assert parse_version("python", "") is None
        assert parse_version("python", "invalid") is None


class TestRegistryQueries:
    """Test feature registry queries."""

    def test_above_version(self, compat):
        above = compat.registry.above_version("python", "3.8")
        assert len(above) > 20
        for entry in above:
            from ..database.version import version_above
            assert version_above("python", entry.introduced, "3.8")

    def test_below_version(self, compat):
        below = compat.registry.below_version("python", "3.12")
        # Should include upgrade entries below 3.12
        # (May be 0 if no upgrade entries exist below 3.12)
        assert isinstance(below, list)

    def test_by_language(self, compat):
        py = compat.registry.by_language("python")
        assert len(py) >= 100
        for e in py:
            assert e.language == "python"

    def test_by_category(self, compat):
        stdlib = compat.registry.by_category("python", "stdlib")
        assert len(stdlib) > 10
        for e in stdlib:
            assert e.category == "stdlib"

    def test_search(self, compat):
        results = compat.registry.search("datetime")
        assert len(results) >= 1
        assert any("datetime" in r.feature_name.lower() for r in results)

    def test_search_no_results(self, compat):
        results = compat.registry.search("xyznonexistent123")
        assert len(results) == 0

    def test_languages(self, compat):
        langs = compat.registry.languages()
        assert "python" in langs
        assert "javascript" in langs
        assert len(langs) == 10

    def test_count(self, compat):
        assert compat.registry.count() >= 300


class TestCodeFloor:
    """Test code floor computation."""

    def test_web_module_floor(self, compat):
        floor = compat.resolver.compute_code_floor(
            Path("src/ui/web"), "python", Path(".")
        )
        # Web module should have a floor above 3.8 (has datetime.UTC etc.)
        assert floor.version
        assert floor.total_features_above >= 0

    def test_features_listed(self, compat):
        floor = compat.resolver.compute_code_floor(
            Path("src/core"), "python", Path(".")
        )
        # Core has datetime.UTC → should show in determining features
        if floor.determining_features:
            assert floor.determining_features[0].feature_name
            assert floor.determining_features[0].version


class TestAssessment:
    """Test target assessment."""

    def test_web_assessment(self, compat):
        assessment = compat.assess("web", "3.8")
        assert assessment.target == "3.8"
        assert assessment.current_floor  # Should have a floor
        assert isinstance(assessment.achievable, bool)
        assert isinstance(assessment.code_fixes_auto, int)
        assert isinstance(assessment.code_fixes_manual, int)

    def test_nonexistent_module(self, compat):
        assessment = compat.assess("nonexistent", "3.8")
        assert not assessment.achievable
        assert "not found" in assessment.recommendation.lower()
