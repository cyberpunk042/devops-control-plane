"""
Testing operations — channel-independent service.

Deep test analysis beyond what quality_ops provides: test file
inventory, function counting, coverage configuration detection,
result parsing, test-to-source mapping, and test template generation.

Complements:
- quality_ops.quality_test() — runs test commands
- quality_ops.quality_run() — runs all quality checks

This module focuses on OBSERVATION and INTELLIGENCE about tests
rather than execution.
"""

from __future__ import annotations

import ast
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


from src.core.services.audit_helpers import make_auditor

_audit = make_auditor("testing")


# ═══════════════════════════════════════════════════════════════════
#  Config / Constants
# ═══════════════════════════════════════════════════════════════════


_SKIP_DIRS = frozenset({
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".mypy_cache", ".ruff_cache", ".pytest_cache", ".tox",
    "dist", "build", ".eggs", ".terraform", ".pages",
    "htmlcov", ".backup", "state",
})

# Test framework detection patterns
_FRAMEWORK_MARKERS: dict[str, dict[str, Any]] = {
    "pytest": {
        "config_files": ["pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini"],
        "config_key": "pytest",
        "test_pattern": re.compile(r"^test_.*\.py$|^.*_test\.py$"),
        "function_pattern": re.compile(r"^\s*def\s+(test_\w+)", re.MULTILINE),
        "class_pattern": re.compile(r"^\s*class\s+(Test\w+)", re.MULTILINE),
        "dirs": ["tests", "test"],
        "stack": "python",
    },
    "unittest": {
        "config_files": [],
        "test_pattern": re.compile(r"^test_.*\.py$"),
        "function_pattern": re.compile(r"^\s*def\s+(test_\w+)", re.MULTILINE),
        "class_pattern": re.compile(r"^\s*class\s+(Test\w+)", re.MULTILINE),
        "dirs": ["tests", "test"],
        "stack": "python",
    },
    "jest": {
        "config_files": ["jest.config.js", "jest.config.ts", "jest.config.mjs"],
        "config_key": "jest",
        "test_pattern": re.compile(r".*\.(test|spec)\.(js|ts|jsx|tsx)$"),
        "function_pattern": re.compile(r"""(?:it|test)\s*\(\s*['"](.+?)['"]"""),
        "dirs": ["__tests__", "tests", "test", "src"],
        "stack": "node",
    },
    "vitest": {
        "config_files": ["vitest.config.ts", "vitest.config.js", "vite.config.ts"],
        "config_key": "vitest",
        "test_pattern": re.compile(r".*\.(test|spec)\.(js|ts|jsx|tsx)$"),
        "function_pattern": re.compile(r"""(?:it|test)\s*\(\s*['"](.+?)['"]"""),
        "dirs": ["__tests__", "tests", "test", "src"],
        "stack": "node",
    },
    "go_test": {
        "config_files": ["go.mod"],
        "test_pattern": re.compile(r".*_test\.go$"),
        "function_pattern": re.compile(r"^\s*func\s+(Test\w+)", re.MULTILINE),
        "dirs": ["."],
        "stack": "go",
    },
    "cargo_test": {
        "config_files": ["Cargo.toml"],
        "test_pattern": re.compile(r".*\.rs$"),
        "function_pattern": re.compile(r"#\[test\]"),
        "dirs": ["src", "tests"],
        "stack": "rust",
    },
}

# Coverage tool detection
_COVERAGE_CONFIGS: dict[str, dict[str, Any]] = {
    "coverage.py": {
        "config_files": [".coveragerc", "pyproject.toml", "setup.cfg"],
        "config_key": "coverage",
        "command": ["python", "-m", "coverage", "report"],
        "stack": "python",
    },
    "pytest-cov": {
        "config_files": ["pyproject.toml", "pytest.ini"],
        "config_key": "pytest",
        "command": ["python", "-m", "pytest", "--cov", "--cov-report=term-missing", "-q"],
        "stack": "python",
    },
    "istanbul/nyc": {
        "config_files": [".nycrc", ".nycrc.json", ".nycrc.yml"],
        "config_key": "nyc",
        "command": ["npx", "nyc", "report"],
        "stack": "node",
    },
    "c8": {
        "config_files": ["vitest.config.ts"],
        "config_key": "c8",
        "command": ["npx", "c8", "report"],
        "stack": "node",
    },
}


# ═══════════════════════════════════════════════════════════════════
#  Detect: Test framework detection
# ═══════════════════════════════════════════════════════════════════


def testing_status(project_root: Path) -> dict:
    """Detect test frameworks, count test files and functions.

    Returns:
        {
            "has_tests": bool,
            "frameworks": [{name, detected_by, test_dir, stack}, ...],
            "coverage_tools": [{name, config}, ...],
            "stats": {
                test_files, test_functions, test_classes,
                source_files, test_ratio
            },
        }
    """
    frameworks: list[dict] = []
    coverage_tools: list[dict] = []

    # Detect frameworks
    for name, marker in _FRAMEWORK_MARKERS.items():
        detection = _detect_framework(project_root, name, marker)
        if detection:
            frameworks.append(detection)

    # Detect coverage tools
    for name, config in _COVERAGE_CONFIGS.items():
        detection = _detect_coverage_tool(project_root, name, config)
        if detection:
            coverage_tools.append(detection)

    # Count test files and functions
    stats = _count_tests(project_root, frameworks)

    return {
        "has_tests": len(frameworks) > 0 and stats["test_files"] > 0,
        "frameworks": frameworks,
        "coverage_tools": coverage_tools,
        "stats": stats,
    }


def _detect_framework(
    project_root: Path, name: str, marker: dict[str, Any]
) -> dict | None:
    """Check if a test framework is configured."""
    detected_by: list[str] = []

    # Check config files
    for cfg_file in marker.get("config_files", []):
        path = project_root / cfg_file
        if path.is_file():
            # Check if the specific key exists (for multi-purpose configs like pyproject.toml)
            config_key = marker.get("config_key")
            if config_key:
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                    if config_key in content:
                        detected_by.append(f"{cfg_file} ({config_key} section)")
                except OSError:
                    pass
            else:
                detected_by.append(cfg_file)

    # Check for test directories
    test_dir = None
    for dir_name in marker.get("dirs", []):
        dir_path = project_root / dir_name
        if dir_path.is_dir():
            # Check if dir contains test files
            pattern = marker["test_pattern"]
            for f in dir_path.rglob("*"):
                if f.is_file() and pattern.match(f.name):
                    test_dir = dir_name
                    detected_by.append(f"{dir_name}/ directory")
                    break

    if not detected_by:
        return None

    return {
        "name": name,
        "detected_by": detected_by,
        "test_dir": test_dir,
        "stack": marker.get("stack", "unknown"),
    }


def _detect_coverage_tool(
    project_root: Path, name: str, config: dict[str, Any]
) -> dict | None:
    """Check if a coverage tool is configured."""
    for cfg_file in config.get("config_files", []):
        path = project_root / cfg_file
        if path.is_file():
            config_key = config.get("config_key")
            if config_key:
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                    if config_key in content:
                        return {
                            "name": name,
                            "config": cfg_file,
                            "stack": config.get("stack"),
                        }
                except OSError:
                    pass
    return None


def _count_tests(project_root: Path, frameworks: list[dict]) -> dict:
    """Count test files, functions, and classes."""
    test_files = 0
    test_functions = 0
    test_classes = 0
    source_files = 0

    # Count source files (for ratio)
    for ext in (".py", ".js", ".ts", ".go", ".rs"):
        for f in project_root.rglob(f"*{ext}"):
            skip = False
            for part in f.relative_to(project_root).parts:
                if part in _SKIP_DIRS:
                    skip = True
                    break
            if skip:
                continue

            rel = str(f.relative_to(project_root))

            # Determine if this is a test file
            is_test = False
            for fw in frameworks:
                marker = _FRAMEWORK_MARKERS.get(fw["name"], {})
                pattern = marker.get("test_pattern")
                if pattern and pattern.match(f.name):
                    is_test = True
                    break

            if is_test:
                test_files += 1

                # Count test functions/methods
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore")
                    for fw in frameworks:
                        marker = _FRAMEWORK_MARKERS.get(fw["name"], {})
                        func_pattern = marker.get("function_pattern")
                        class_pattern = marker.get("class_pattern")

                        if func_pattern:
                            test_functions += len(func_pattern.findall(content))
                        if class_pattern:
                            test_classes += len(class_pattern.findall(content))
                        break  # Don't double-count
                except OSError:
                    pass
            else:
                source_files += 1

    test_ratio = test_files / source_files if source_files > 0 else 0

    return {
        "test_files": test_files,
        "test_functions": test_functions,
        "test_classes": test_classes,
        "source_files": source_files,
        "test_ratio": round(test_ratio, 2),
    }


# ═══════════════════════════════════════════════════════════════════
# Re-exports — backward compatibility
# ═══════════════════════════════════════════════════════════════════

from src.core.services.testing_run import (  # noqa: F401, E402
    test_inventory,
    test_coverage,
    run_tests,
    generate_test_template,
    generate_coverage_config,
)

