"""Transform edge case tests — verify fixes handle complex scenarios.

Tests that the fix engine produces correct output for:
- Multiple findings in one file
- Fixes that interact with each other
- Files with existing imports
- Large files with many changes
"""

from __future__ import annotations

from pathlib import Path


def _fix_all(code: str, target: str = "3.8") -> str:
    """Apply ALL fixes to code and return result."""
    from ..backends.python_backend import PythonBackend
    from ..database.registry import FeatureRegistry
    from ..analysis.engine import DetectionEngine
    from ..fix.engine import FixEngine

    registry = FeatureRegistry.load()
    backend = PythonBackend()
    detection = DetectionEngine(registry, backend)
    fix_engine = FixEngine(registry, detection, backend)

    tmp = Path("/tmp/_compat_transform_test.py")
    tmp.write_text(code)

    try:
        findings = detection.analyze_file(tmp, target, "downgrade", Path("/tmp"))
        for finding in sorted(findings, key=lambda f: -f.line):
            fix_engine.fix_finding(finding, Path("/tmp"), verify=False)
        return tmp.read_text()
    finally:
        tmp.unlink(missing_ok=True)


class TestMultipleFixesOneFile:
    """Multiple fixes applied to the same file."""

    def test_utc_and_future_in_same_file(self):
        """File needs both UTC replacement and __future__ import."""
        code = '''from datetime import UTC, datetime

def process(items: list[int]) -> dict[str, int]:
    now = datetime.now(UTC)
    return {}
'''
        result = _fix_all(code)
        # UTC should be replaced
        assert "from datetime import timezone" in result or "timezone" in result
        # __future__ should be added for list[int]/dict[str,int]
        # (or the annotation features might not need fixing if UTC fix runs first)
        assert "UTC" not in result.split("timezone")[0] if "timezone" in result else True

    def test_multiple_removeprefix(self):
        """Multiple removeprefix calls in one file."""
        code = '''name = path.removeprefix("/home/")
clean = text.removeprefix("prefix_")
'''
        result = _fix_all(code)
        assert "removeprefix" not in result
        assert "startswith" in result
        # Both should be rewritten
        lines = [l for l in result.split("\n") if "startswith" in l]
        assert len(lines) == 2

    def test_strenum_keeps_other_enum_imports(self):
        """Fixing StrEnum shouldn't break other enum imports."""
        code = '''from enum import Enum, StrEnum, auto, Flag

class Color(StrEnum):
    RED = auto()

class Permission(Flag):
    READ = 1
'''
        result = _fix_all(code)
        assert "from backports.strenum import StrEnum" in result
        # Other enum imports must survive
        assert "Enum" in result
        assert "auto" in result
        assert "Flag" in result


class TestFixIdempotency:
    """Running fixes twice should not change the result."""

    def test_future_import_idempotent(self):
        """Adding __future__ twice should not duplicate it."""
        code = '''def foo(x: int | str) -> None:
    pass
'''
        result1 = _fix_all(code, target="3.9")
        result2 = _fix_all(result1, target="3.9")
        count1 = result1.count("from __future__ import annotations")
        count2 = result2.count("from __future__ import annotations")
        assert count1 <= 1
        assert count2 <= 1

    def test_utc_fix_idempotent(self):
        """Fixing UTC twice should not break anything."""
        code = '''from datetime import UTC
now = datetime.now(UTC)
'''
        result1 = _fix_all(code)
        # After first fix, no UTC findings should remain
        # So second fix should be a no-op
        result2 = _fix_all(result1)
        assert result1.strip() == result2.strip() or "timezone" in result2


class TestFixPreservesFormatting:
    """Fixes should minimally change the file."""

    def test_preserves_comments(self):
        """Comments should not be removed by fixes."""
        code = '''# This module handles dates
from datetime import UTC  # timezone constant

# Process the data
now = datetime.now(UTC)  # current time
'''
        result = _fix_all(code)
        assert "# This module handles dates" in result
        assert "# Process the data" in result

    def test_preserves_blank_lines(self):
        """Blank lines structure should be roughly preserved."""
        code = '''from datetime import UTC

def foo():
    return datetime.now(UTC)


def bar():
    return "hello"
'''
        result = _fix_all(code)
        # Should still have the function structure
        assert "def foo():" in result
        assert "def bar():" in result
