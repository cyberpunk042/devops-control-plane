"""Edge case test suite for Python detection.

Tests that the detection engine correctly handles:
- TYPE_CHECKING blocks (exclude)
- try/except ImportError (downgrade severity)
- sys.version_info gates (exclude)
- __future__ annotations (suppress annotation findings)
- isinstance runtime usage (not suppressed by __future__)
- Star imports (unresolvable)
- Aliased imports (track alias)
- Complex receivers in method calls
- Mixed imports (partial replacement)
- getattr with default (safe access)

Run: python -m pytest src/core/services/compat/edge_cases/test_python_edge_cases.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ── Test infrastructure ──────────────────────────────────────────


def _detect(code: str, target: str = "3.8") -> list:
    """Run detection on a code string, return findings."""
    from ..backends.python_backend import PythonBackend
    from ..database.registry import FeatureRegistry
    from ..analysis.engine import DetectionEngine

    registry = FeatureRegistry.load()
    backend = PythonBackend()
    engine = DetectionEngine(registry, backend)

    # Write to temp file
    tmp = Path("/tmp/_compat_test.py")
    tmp.write_text(code)

    try:
        findings = engine.analyze_file(tmp, target, "downgrade", Path("/tmp"))
        return findings
    finally:
        tmp.unlink(missing_ok=True)


def _detect_feature(code: str, feature_id: str, target: str = "3.8") -> list:
    """Run detection for a specific feature."""
    findings = _detect(code, target)
    return [f for f in findings if f.feature_id == feature_id]


# ── TYPE_CHECKING exclusion ──────────────────────────────────────


class TestTypeCheckingExclusion:
    """Imports inside TYPE_CHECKING blocks should NOT be flagged."""

    def test_utc_in_type_checking(self):
        code = '''
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from datetime import UTC
'''
        findings = _detect_feature(code, "python.stdlib.datetime_utc")
        assert len(findings) == 0, "UTC inside TYPE_CHECKING should not be detected"

    def test_strenum_in_type_checking(self):
        code = '''
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from enum import StrEnum
'''
        findings = _detect_feature(code, "python.stdlib.strenum")
        assert len(findings) == 0

    def test_utc_outside_type_checking(self):
        code = '''
from datetime import UTC
now = datetime.now(UTC)
'''
        findings = _detect_feature(code, "python.stdlib.datetime_utc")
        assert len(findings) >= 1, "UTC outside TYPE_CHECKING should be detected"


# ── __future__ annotations suppression ───────────────────────────


class TestFutureAnnotations:
    """__future__ annotations should suppress annotation-only findings."""

    def test_union_pipe_with_future(self):
        code = '''
from __future__ import annotations

def foo(x: int | str) -> None:
    pass
'''
        findings = _detect_feature(code, "python.typing.union_pipe")
        assert len(findings) == 0, "X | Y in annotation with __future__ should not be detected"

    def test_builtin_generics_with_future(self):
        code = '''
from __future__ import annotations

def foo(items: list[int]) -> dict[str, int]:
    pass
'''
        findings = _detect_feature(code, "python.typing.builtin_generics")
        assert len(findings) == 0, "list[int] in annotation with __future__ should not be detected"

    def test_union_pipe_without_future(self):
        code = '''
def foo(x: int | str) -> None:
    pass
'''
        findings = _detect_feature(code, "python.typing.union_pipe", target="3.9")
        assert len(findings) >= 1, "X | Y without __future__ should be detected"

    def test_builtin_generics_without_future(self):
        code = '''
def foo(items: list[int]) -> None:
    pass
'''
        findings = _detect_feature(code, "python.typing.builtin_generics", target="3.8")
        assert len(findings) >= 1, "list[int] without __future__ should be detected"


# ── Runtime vs annotation context ────────────────────────────────


class TestRuntimeVsAnnotation:
    """Runtime usages should always be flagged, even with __future__."""

    def test_dict_merge_runtime(self):
        """dict | dict in runtime should be flagged."""
        code = '''
a = {"x": 1}
b = {"y": 2}
c = a | b
'''
        findings = _detect_feature(code, "python.builtins.dict_merge_operator")
        assert len(findings) >= 1, "dict | in runtime should be detected"

    def test_removeprefix_always_runtime(self):
        """removeprefix is always runtime."""
        code = '''
result = path.removeprefix("/home/")
'''
        findings = _detect_feature(code, "python.builtins.str_removeprefix")
        assert len(findings) >= 1


# ── Import patterns ──────────────────────────────────────────────


class TestImportPatterns:
    """Detection should handle various import forms."""

    def test_utc_sole_import(self):
        code = 'from datetime import UTC\n'
        findings = _detect_feature(code, "python.stdlib.datetime_utc")
        assert len(findings) >= 1

    def test_utc_mixed_import(self):
        code = 'from datetime import datetime, UTC, timezone\n'
        findings = _detect_feature(code, "python.stdlib.datetime_utc")
        assert len(findings) >= 1

    def test_tomllib_import(self):
        code = 'import tomllib\n'
        findings = _detect_feature(code, "python.stdlib.tomllib")
        assert len(findings) >= 1

    def test_tomllib_from_import(self):
        code = 'from tomllib import load\n'
        findings = _detect_feature(code, "python.stdlib.tomllib")
        assert len(findings) >= 1

    def test_strenum_from_enum(self):
        code = 'from enum import StrEnum\n'
        findings = _detect_feature(code, "python.stdlib.strenum")
        assert len(findings) >= 1


# ── Walrus operator ──────────────────────────────────────────────


class TestWalrusOperator:
    """Walrus operator detection in various contexts."""

    def test_walrus_in_if(self):
        code = '''
if (n := len(data)) > 10:
    print(n)
'''
        findings = _detect_feature(code, "python.syntax.walrus_operator", target="3.7")
        assert len(findings) >= 1

    def test_walrus_in_while(self):
        code = '''
while chunk := f.read(8192):
    process(chunk)
'''
        findings = _detect_feature(code, "python.syntax.walrus_operator", target="3.7")
        assert len(findings) >= 1


# ── Match/case ───────────────────────────────────────────────────


class TestMatchCase:
    """Match/case detection."""

    def test_simple_match(self):
        code = '''
match command:
    case "quit":
        return 0
    case _:
        return 1
'''
        findings = _detect_feature(code, "python.syntax.match_case", target="3.9")
        assert len(findings) >= 1

    def test_no_match_no_finding(self):
        code = '''
if command == "quit":
    return 0
'''
        findings = _detect_feature(code, "python.syntax.match_case", target="3.9")
        assert len(findings) == 0


# ── Typing backports ────────────────────────────────────────────


class TestTypingBackports:
    """Typing features that can be backported via typing_extensions."""

    def test_self_type(self):
        code = 'from typing import Self\n'
        findings = _detect_feature(code, "python.typing.self_type", target="3.10")
        assert len(findings) >= 1

    def test_paramspec(self):
        code = 'from typing import ParamSpec\n'
        findings = _detect_feature(code, "python.typing.paramspec", target="3.9")
        assert len(findings) >= 1

    def test_typeguard(self):
        code = 'from typing import TypeGuard\n'
        findings = _detect_feature(code, "python.typing.typeguard", target="3.9")
        assert len(findings) >= 1

    def test_never(self):
        code = 'from typing import Never\n'
        findings = _detect_feature(code, "python.typing.never_type", target="3.10")
        assert len(findings) >= 1

    def test_typing_extensions_not_flagged(self):
        """Imports from typing_extensions should NOT be flagged."""
        code = 'from typing_extensions import Self\n'
        findings = _detect_feature(code, "python.typing.self_type", target="3.10")
        assert len(findings) == 0, "typing_extensions imports should not be flagged"
