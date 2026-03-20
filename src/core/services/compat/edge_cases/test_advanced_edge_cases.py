"""Advanced edge case tests for detection accuracy.

Tests scenarios that commonly produce false positives or
false negatives in version compatibility scanning.

Run: python -m pytest src/core/services/compat/edge_cases/test_advanced_edge_cases.py -v
"""

from __future__ import annotations

from pathlib import Path


def _detect(code: str, target: str = "3.8") -> list:
    """Run detection on a code string, return findings."""
    from ..backends.python_backend import PythonBackend
    from ..database.registry import FeatureRegistry
    from ..analysis.engine import DetectionEngine

    registry = FeatureRegistry.load()
    backend = PythonBackend()
    engine = DetectionEngine(registry, backend)

    tmp = Path("/tmp/_compat_adv_test.py")
    tmp.write_text(code)
    try:
        return engine.analyze_file(tmp, target, "downgrade", Path("/tmp"))
    finally:
        tmp.unlink(missing_ok=True)


def _count(code: str, feature_id: str, target: str = "3.8") -> int:
    """Count findings for a specific feature."""
    return len([f for f in _detect(code, target) if f.feature_id == feature_id])


# ── String/comment false positives ───────────────────────────────


class TestStringCommentExclusion:
    """AST detection should NOT match inside strings or comments."""

    def test_utc_in_string(self):
        """'datetime.UTC' inside a string literal is not code."""
        assert _count('msg = "use datetime.UTC for timezone"\n', "python.stdlib.datetime_utc") == 0

    def test_utc_in_comment(self):
        """# datetime.UTC in a comment is not code."""
        assert _count('# from datetime import UTC\nx = 1\n', "python.stdlib.datetime_utc") == 0

    def test_utc_in_docstring(self):
        """UTC mentioned in a docstring is not code."""
        code = '"""\nUse datetime.UTC for timezone.\n"""\nimport os\n'
        assert _count(code, "python.stdlib.datetime_utc") == 0

    def test_removeprefix_in_string(self):
        """'removeprefix' inside a string is not code."""
        assert _count('help_text = "use removeprefix to strip"\n', "python.builtins.str_removeprefix") == 0

    def test_match_in_string(self):
        """'match' inside a string is not the match statement."""
        assert _count('pattern = "match this"\n', "python.syntax.match_case", "3.9") == 0


# ── Scope and shadowing ─────────────────────────────────────────


class TestScopeShadowing:
    """Detection should handle name shadowing correctly."""

    def test_local_utc_not_flagged(self):
        """A local variable named UTC is not datetime.UTC."""
        code = 'UTC = "my_timezone"\nprint(UTC)\n'
        # This should NOT be flagged as datetime.UTC (it's a local variable)
        # Note: current implementation may flag this — testing actual behavior
        findings = [f for f in _detect(code) if f.feature_id == "python.stdlib.datetime_utc"]
        # ImportFrom detection won't match here (no import statement)
        assert len(findings) == 0

    def test_imported_utc_is_flagged(self):
        """from datetime import UTC IS the feature."""
        assert _count('from datetime import UTC\n', "python.stdlib.datetime_utc") >= 1


# ── Multiple features in same file ──────────────────────────────


class TestMultipleFeatures:
    """Files can have multiple different incompatible features."""

    def test_utc_and_removeprefix(self):
        """Both datetime.UTC and removeprefix in same file."""
        code = 'from datetime import UTC\nresult = path.removeprefix("/home/")\n'
        findings = _detect(code)
        feature_ids = {f.feature_id for f in findings}
        assert "python.stdlib.datetime_utc" in feature_ids
        assert "python.builtins.str_removeprefix" in feature_ids

    def test_multiple_typing_features(self):
        """Multiple typing imports from different versions."""
        code = 'from typing import Self, ParamSpec, Never\n'
        findings = _detect(code, target="3.9")
        # Self (3.11), ParamSpec (3.10), Never (3.11) — all above 3.9
        assert len(findings) >= 2


# ── Conditional imports ──────────────────────────────────────────


class TestConditionalImports:
    """try/except and version-gated imports should be handled."""

    def test_try_except_with_fallback(self):
        """try/except with fallback is already handled — info severity."""
        code = '''
try:
    from datetime import UTC
except ImportError:
    from datetime import timezone
    UTC = timezone.utc
'''
        findings = [f for f in _detect(code) if f.feature_id == "python.stdlib.datetime_utc"]
        # Should either not be flagged or be info severity
        if findings:
            assert findings[0].severity in ("info", "warning"), \
                f"Expected info/warning severity, got {findings[0].severity}"

    def test_version_gate_excluded(self):
        """sys.version_info gated code should not be flagged."""
        code = '''
import sys
if sys.version_info >= (3, 11):
    from datetime import UTC
else:
    from datetime import timezone
    UTC = timezone.utc
'''
        findings = [f for f in _detect(code) if f.feature_id == "python.stdlib.datetime_utc"]
        assert len(findings) == 0, "Version-gated import should not be flagged"


# ── Annotation vs runtime in same file ───────────────────────────


class TestAnnotationRuntime:
    """Same feature used in both annotation and runtime contexts."""

    def test_union_annotation_only_with_future(self):
        """X | Y only in annotations + __future__ → no findings."""
        code = '''
from __future__ import annotations

def foo(x: int | str) -> list[int]:
    return [x]
'''
        union = _count(code, "python.typing.union_pipe", "3.9")
        generic = _count(code, "python.typing.builtin_generics")
        assert union == 0, "Union in annotation with __future__ should not be flagged"
        assert generic == 0, "Builtin generic in annotation with __future__ should not be flagged"

    def test_union_annotation_without_future(self):
        """X | Y in annotations WITHOUT __future__ → flagged."""
        code = '''
def foo(x: int | str) -> None:
    pass
'''
        assert _count(code, "python.typing.union_pipe", "3.9") >= 1


# ── Backport imports not flagged ─────────────────────────────────


class TestBackportImports:
    """Imports from backport packages should NOT be flagged."""

    def test_typing_extensions_self(self):
        """from typing_extensions import Self is NOT from typing."""
        assert _count('from typing_extensions import Self\n', "python.typing.self_type", "3.10") == 0

    def test_typing_extensions_paramspec(self):
        assert _count('from typing_extensions import ParamSpec\n', "python.typing.paramspec", "3.9") == 0

    def test_backports_strenum(self):
        """from backports.strenum import StrEnum is NOT from enum."""
        assert _count('from backports.strenum import StrEnum\n', "python.stdlib.strenum") == 0

    def test_tomli_not_tomllib(self):
        """import tomli is NOT import tomllib."""
        assert _count('import tomli\n', "python.stdlib.tomllib") == 0

    def test_tomli_as_tomllib_is_backport(self):
        """import tomli as tomllib is a backport pattern — should be detected for upgrade."""
        # For downgrade this is the FIX, so it should NOT be flagged as tomllib
        assert _count('import tomli as tomllib\n', "python.stdlib.tomllib") == 0


# ── Empty/minimal files ─────────────────────────────────────────


class TestEdgeCaseFiles:
    """Handle edge case file contents."""

    def test_empty_file(self):
        """Empty file should produce 0 findings."""
        assert len(_detect('')) == 0

    def test_only_comments(self):
        """File with only comments."""
        assert len(_detect('# just comments\n# nothing here\n')) == 0

    def test_only_docstring(self):
        """File with only a docstring."""
        assert len(_detect('"""Module docstring."""\n')) == 0

    def test_syntax_error_file(self):
        """File with syntax errors should not crash detection."""
        findings = _detect('def foo(\n')  # Incomplete syntax
        # Should return empty (parse error) or handle gracefully
        assert isinstance(findings, list)
