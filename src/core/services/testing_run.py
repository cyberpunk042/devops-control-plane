"""
Testing execution & analysis — inventory, coverage, running, templates.

Complements testing_ops.py which handles detection/status.
Channel-independent: no Flask or HTTP dependency.
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from src.core.services.audit_helpers import make_auditor
from src.core.services.testing_ops import (
    _FRAMEWORK_MARKERS,
    _SKIP_DIRS,
    testing_status,
)

logger = logging.getLogger(__name__)

_audit = make_auditor("testing")


# ═══════════════════════════════════════════════════════════════════
#  Observe: Test inventory
# ═══════════════════════════════════════════════════════════════════


def test_inventory(project_root: Path) -> dict:
    """List all test files with function counts.

    Returns:
        {
            "files": [{
                path, functions, classes, lines, framework
            }, ...],
            "total_files": int,
            "total_functions": int,
        }
    """
    status = testing_status(project_root)
    frameworks = status.get("frameworks", [])

    files: list[dict] = []
    total_functions = 0
    seen_paths: set[str] = set()

    for fw in frameworks:
        marker = _FRAMEWORK_MARKERS.get(fw["name"], {})
        pattern = marker.get("test_pattern")
        func_pattern = marker.get("function_pattern")
        class_pattern = marker.get("class_pattern")

        if not pattern:
            continue

        for dir_name in marker.get("dirs", ["."]):
            dir_path = project_root / dir_name
            if not dir_path.is_dir():
                continue

            for f in dir_path.rglob("*"):
                if not f.is_file() or not pattern.match(f.name):
                    continue

                rel_path = str(f.relative_to(project_root))

                # Deduplicate across frameworks
                if rel_path in seen_paths:
                    continue
                seen_paths.add(rel_path)

                skip = False
                for part in f.relative_to(project_root).parts:
                    if part in _SKIP_DIRS:
                        skip = True
                        break
                if skip:
                    continue

                try:
                    content = f.read_text(encoding="utf-8", errors="ignore")
                    lines = len(content.splitlines())

                    func_count = len(func_pattern.findall(content)) if func_pattern else 0
                    class_count = len(class_pattern.findall(content)) if class_pattern else 0
                    total_functions += func_count

                    files.append({
                        "path": rel_path,
                        "functions": func_count,
                        "classes": class_count,
                        "lines": lines,
                        "framework": fw["name"],
                    })
                except OSError:
                    pass

    # Sort by function count descending
    files.sort(key=lambda x: x["functions"], reverse=True)

    return {
        "files": files,
        "total_files": len(files),
        "total_functions": total_functions,
    }


# ═══════════════════════════════════════════════════════════════════
#  Observe: Coverage analysis
# ═══════════════════════════════════════════════════════════════════


def test_coverage(project_root: Path) -> dict:
    """Run coverage and parse results.

    Returns:
        {
            "ok": bool,
            "tool": str,
            "coverage_percent": float | None,
            "files": [{name, stmts, miss, cover}, ...],
            "output": str,
        }
    """
    # Try pytest-cov first (most common for Python projects)
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "--cov", "src", "--cov-report=term-missing",
             "-q", "--no-header", "--tb=no"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=120,
        )

        output = result.stdout + result.stderr
        if result.returncode in (0, 1) and "TOTAL" in output:
            parsed = _parse_coverage_output(output)
            parsed["tool"] = "pytest-cov"
            parsed["ok"] = True
            _audit(
                "📊 Coverage Run",
                f"Coverage analysis completed ({parsed.get('coverage_percent', '?')}%)",
                action="executed",
                target="coverage",
                after_state={"tool": "pytest-cov", "coverage": parsed.get("coverage_percent")},
            )
            return parsed

    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Try coverage.py report (if .coverage file exists)
    coverage_file = project_root / ".coverage"
    if coverage_file.is_file():
        try:
            result = subprocess.run(
                ["python", "-m", "coverage", "report"],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0 and "TOTAL" in result.stdout:
                parsed = _parse_coverage_output(result.stdout)
                parsed["tool"] = "coverage.py"
                parsed["ok"] = True
                _audit(
                    "📊 Coverage Run",
                    f"Coverage analysis completed ({parsed.get('coverage_percent', '?')}%)",
                    action="executed",
                    target="coverage",
                    after_state={"tool": "coverage.py", "coverage": parsed.get("coverage_percent")},
                )
                return parsed

        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    return {
        "ok": False,
        "tool": None,
        "coverage_percent": None,
        "files": [],
        "output": "No coverage data available. Run tests with --cov first.",
    }


def _parse_coverage_output(output: str) -> dict:
    """Parse coverage.py / pytest-cov tabular output."""
    files: list[dict] = []
    total_percent: float | None = None

    # Match lines like: src/foo.py    100     5    95%   10-12,45
    file_pattern = re.compile(
        r"^(\S+\.py)\s+(\d+)\s+(\d+)\s+(\d+)%"
    )
    total_pattern = re.compile(r"^TOTAL\s+(\d+)\s+(\d+)\s+(\d+)%")

    for line in output.splitlines():
        match = file_pattern.match(line.strip())
        if match:
            files.append({
                "name": match.group(1),
                "stmts": int(match.group(2)),
                "miss": int(match.group(3)),
                "cover": int(match.group(4)),
            })

        total_match = total_pattern.match(line.strip())
        if total_match:
            total_percent = float(total_match.group(3))

    return {
        "coverage_percent": total_percent,
        "files": files,
        "output": output,
    }


# ═══════════════════════════════════════════════════════════════════
#  Observe: Test results parsing
# ═══════════════════════════════════════════════════════════════════


def run_tests(
    project_root: Path,
    *,
    verbose: bool = False,
    file_path: str | None = None,
    keyword: str | None = None,
) -> dict:
    """Run tests and return structured results.

    Returns:
        {
            "ok": bool,
            "passed": int,
            "failed": int,
            "errors": int,
            "skipped": int,
            "duration_seconds": float,
            "output": str,
            "failures": [{name, output}, ...],
        }
    """
    cmd = ["python", "-m", "pytest", "-q", "--tb=short"]

    if verbose:
        cmd.append("-v")

    if file_path:
        cmd.append(file_path)

    if keyword:
        cmd.extend(["-k", keyword])

    try:
        result = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Tests timed out after 120 seconds"}
    except FileNotFoundError:
        return {"ok": False, "error": "pytest not found"}

    output = result.stdout + result.stderr
    parsed = _parse_pytest_output(output, result.returncode)
    parsed["output"] = output.strip()

    _audit(
        "🧪 Tests Run",
        "Tests executed" + (f" ({file_path})" if file_path else ""),
        action="executed",
        target=file_path or "all",
        detail={"file": file_path, "keyword": keyword, "verbose": verbose},
        after_state={
            "passed": parsed.get("passed", 0),
            "failed": parsed.get("failed", 0),
            "errors": parsed.get("errors", 0),
        },
    )

    return parsed


def _parse_pytest_output(output: str, returncode: int) -> dict:
    """Parse pytest output for structured results."""
    passed = failed = errors = skipped = 0
    duration = 0.0
    failures: list[dict] = []

    # Parse summary line: "10 passed, 2 failed, 1 error in 3.45s"
    summary_pattern = re.compile(
        r"(?:(\d+)\s+passed)?"
        r"(?:,?\s*(\d+)\s+failed)?"
        r"(?:,?\s*(\d+)\s+error)?"
        r"(?:,?\s*(\d+)\s+skipped)?"
        r"(?:.*?in\s+([\d.]+)s)?"
    )

    for line in output.splitlines():
        match = summary_pattern.search(line)
        if match and any(match.groups()):
            if match.group(1):
                passed = int(match.group(1))
            if match.group(2):
                failed = int(match.group(2))
            if match.group(3):
                errors = int(match.group(3))
            if match.group(4):
                skipped = int(match.group(4))
            if match.group(5):
                duration = float(match.group(5))

    # Extract failure details
    for line in output.splitlines():
        if line.startswith("FAILED"):
            name = line.replace("FAILED ", "").strip()
            failures.append({"name": name, "output": ""})
        elif line.startswith("ERROR"):
            name = line.replace("ERROR ", "").strip()
            failures.append({"name": name, "output": ""})

    return {
        "ok": returncode == 0,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "total": passed + failed + errors + skipped,
        "duration_seconds": duration,
        "failures": failures[:20],
    }


# ═══════════════════════════════════════════════════════════════════
#  Facilitate: Test template generation
# ═══════════════════════════════════════════════════════════════════


_PYTEST_TEMPLATE = '''"""
Tests for {module_name}.

Auto-generated by DevOps Control Plane.
"""

from __future__ import annotations

import pytest


class Test{class_name}:
    """Test suite for {module_name}."""

    def test_placeholder(self) -> None:
        """TODO: Replace with real test."""
        assert True

    def test_import(self) -> None:
        """Verify module can be imported."""
        # import {module_import}  # uncomment and adjust
        pass
'''

_JEST_TEMPLATE = '''// Tests for {module_name}
// Auto-generated by DevOps Control Plane

describe('{module_name}', () => {{
  test('placeholder', () => {{
    expect(true).toBe(true);
  }});

  test('imports correctly', () => {{
    // const mod = require('./{module_name}');
    // expect(mod).toBeDefined();
  }});
}});
'''

_GO_TEST_TEMPLATE = '''package {package_name}

import "testing"

// TestPlaceholder is a placeholder test.
// Auto-generated by DevOps Control Plane.
func TestPlaceholder(t *testing.T) {{
\t// TODO: Replace with real test
\tif false {{
\t\tt.Error("placeholder")
\t}}
}}
'''


def generate_test_template(
    project_root: Path,
    module_name: str,
    stack: str = "python",
) -> dict:
    """Generate a test template for a module.

    Returns:
        {"ok": True, "file": {path, content, reason, overwrite}}
    """
    from src.core.models.template import GeneratedFile

    if "python" in stack:
        class_name = "".join(w.title() for w in module_name.replace("-", "_").split("_"))
        module_import = module_name.replace("-", "_")
        content = _PYTEST_TEMPLATE.format(
            module_name=module_name,
            class_name=class_name,
            module_import=module_import,
        )
        path = f"tests/test_{module_name.replace('-', '_')}.py"

    elif stack in ("node", "typescript"):
        content = _JEST_TEMPLATE.format(module_name=module_name)
        path = f"tests/{module_name}.test.ts"

    elif stack == "go":
        package_name = module_name.replace("-", "_")
        content = _GO_TEST_TEMPLATE.format(package_name=package_name)
        path = f"{module_name}/{module_name}_test.go"

    else:
        return {"error": f"No test template for stack: {stack}"}

    file_data = GeneratedFile(
        path=path,
        content=content,
        overwrite=False,
        reason=f"Test template for {module_name} ({stack})",
    )

    _audit(
        "📝 Test Template Generated",
        f"Test template generated for module '{module_name}'",
        action="generated",
        target=module_name,
        detail={"module": module_name, "stack": stack},
    )

    return {"ok": True, "file": file_data.model_dump()}


def generate_coverage_config(project_root: Path, stack: str = "python") -> dict:
    """Generate coverage configuration.

    Returns:
        {"ok": True, "file": {path, content, reason, overwrite}}
    """
    from src.core.models.template import GeneratedFile

    if "python" in stack:
        content = """# Coverage configuration — generated by DevOps Control Plane

[tool.coverage.run]
source = ["src"]
omit = [
    "*/tests/*",
    "*/__pycache__/*",
    "*/conftest.py",
]

[tool.coverage.report]
show_missing = true
fail_under = 80
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "if __name__ == .__main__.",
    "@overload",
]
"""
        path = "pyproject.toml"  # Appended section
        reason = "Python coverage configuration (append to pyproject.toml)"

    elif stack in ("node", "typescript"):
        content = """{
  "all": true,
  "include": ["src/**/*.{js,ts}"],
  "exclude": ["**/*.test.{js,ts}", "node_modules/**"],
  "reporter": ["text", "lcov"],
  "check-coverage": true,
  "branches": 80,
  "lines": 80,
  "functions": 80,
  "statements": 80
}
"""
        path = ".nycrc.json"
        reason = "NYC/Istanbul coverage configuration"

    else:
        return {"error": f"No coverage config template for stack: {stack}"}

    file_data = GeneratedFile(
        path=path,
        content=content,
        overwrite=False,
        reason=reason,
    )

    return {"ok": True, "file": file_data.model_dump()}
