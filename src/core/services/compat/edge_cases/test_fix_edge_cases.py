"""Edge case tests for the fix engine.

Tests that fixes handle complex scenarios correctly:
- Mixed imports (UTC alongside other names)
- Aliased imports
- Complex receivers in method calls
- Multiple usages in one file
- Files with __future__ annotations
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _fix(code: str, feature_id: str) -> str:
    """Apply fix to code and return the result."""
    from ..backends.python_backend import PythonBackend
    from ..database.registry import FeatureRegistry
    from ..analysis.engine import DetectionEngine
    from ..fix.engine import FixEngine

    registry = FeatureRegistry.load()
    backend = PythonBackend()
    detection = DetectionEngine(registry, backend)
    fix_engine = FixEngine(registry, detection, backend)

    tmp = Path("/tmp/_compat_fix_test.py")
    tmp.write_text(code)

    try:
        findings = detection.analyze_file(tmp, "3.8", "downgrade", Path("/tmp"))
        target_findings = [f for f in findings if f.feature_id == feature_id]

        for finding in target_findings:
            fix_engine.fix_finding(finding, Path("/tmp"), verify=False)

        return tmp.read_text()
    finally:
        tmp.unlink(missing_ok=True)


class TestDatetimeUTCFix:
    """datetime.UTC fix edge cases."""

    def test_sole_import(self):
        result = _fix(
            "from datetime import UTC\nnow = datetime.now(UTC)\n",
            "python.stdlib.datetime_utc",
        )
        assert "from datetime import timezone" in result
        assert "timezone.utc" in result
        assert "UTC" not in result.replace("timezone.utc", "")

    def test_mixed_import_keeps_others(self):
        result = _fix(
            "from datetime import datetime, UTC, timezone\nnow = datetime.now(UTC)\n",
            "python.stdlib.datetime_utc",
        )
        assert "datetime" in result
        # UTC should be replaced, timezone should remain
        assert "timezone.utc" in result

    def test_multiple_usages(self):
        result = _fix(
            "from datetime import UTC, datetime\na = datetime.now(UTC)\nb = datetime(2024, 1, 1, tzinfo=UTC)\nc = datetime.now(tz=UTC)\n",
            "python.stdlib.datetime_utc",
        )
        # All UTC usages should be replaced
        lines = result.split("\n")
        utc_only = [l for l in lines if "UTC" in l and "timezone.utc" not in l and "import" not in l]
        assert len(utc_only) == 0, f"Found unreplaced UTC: {utc_only}"


class TestRemoveprefixFix:
    """removeprefix fix edge cases."""

    def test_simple_receiver(self):
        result = _fix(
            'result = path.removeprefix("/home/")\n',
            "python.builtins.str_removeprefix",
        )
        assert "removeprefix" not in result
        assert "startswith" in result
        assert 'len("/home/")' in result

    def test_complex_receiver(self):
        result = _fix(
            'result = get_name().removeprefix("/home/")\n',
            "python.builtins.str_removeprefix",
        )
        assert "_tmp" in result
        assert "removeprefix" not in result


class TestStrEnumFix:
    """StrEnum fix edge cases."""

    def test_sole_import(self):
        result = _fix(
            "from enum import StrEnum\nclass Color(StrEnum):\n    RED = 'red'\n",
            "python.stdlib.strenum",
        )
        assert "from backports.strenum import StrEnum" in result
        assert "from enum import StrEnum" not in result

    def test_mixed_import(self):
        result = _fix(
            "from enum import Enum, StrEnum, auto\nclass Color(StrEnum):\n    RED = auto()\n",
            "python.stdlib.strenum",
        )
        assert "from backports.strenum import StrEnum" in result
        assert "from enum import Enum, auto" in result or "from enum import Enum,  auto" in result


class TestTomllibFix:
    """tomllib fix edge cases."""

    def test_import_tomllib(self):
        result = _fix(
            "import tomllib\ndata = tomllib.load(open('f.toml', 'rb'))\n",
            "python.stdlib.tomllib",
        )
        assert "import tomli as tomllib" in result
        assert "tomllib.load" in result  # Usage unchanged — uses alias

    def test_from_tomllib(self):
        result = _fix(
            "from tomllib import load\ndata = load(open('f.toml', 'rb'))\n",
            "python.stdlib.tomllib",
        )
        assert "tomli" in result


class TestFutureAnnotationsFix:
    """__future__ annotations fix."""

    def test_adds_future_import(self):
        result = _fix(
            "def foo(x: int | str) -> None:\n    pass\n",
            "python.typing.union_pipe",
        )
        assert "from __future__ import annotations" in result

    def test_no_duplicate_future(self):
        result = _fix(
            "from __future__ import annotations\n\ndef foo(x: int | str) -> None:\n    pass\n",
            "python.typing.union_pipe",
        )
        # Should not add a second __future__ import
        count = result.count("from __future__ import annotations")
        assert count == 1, f"Found {count} __future__ imports"
