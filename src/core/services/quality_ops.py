"""
Code quality operations — channel-independent service.

Covers linting, type-checking, testing, and formatting across
all supported stacks. Maps stack names to the appropriate
quality tools and provides unified results.

Does NOT run builds. Focuses on fast, incremental quality checks.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Quality tool definitions ────────────────────────────────────


_QUALITY_TOOLS: dict[str, dict] = {
    # Python
    "ruff": {
        "name": "Ruff",
        "category": "lint",
        "stacks": ["python"],
        "cli": "ruff",
        "run_args": ["ruff", "check", "."],
        "fix_args": ["ruff", "check", "--fix", "."],
        "config_files": ["ruff.toml", ".ruff.toml", "pyproject.toml"],
        "install_hint": "pip install ruff",
    },
    "mypy": {
        "name": "mypy",
        "category": "typecheck",
        "stacks": ["python"],
        "cli": "mypy",
        "run_args": ["mypy", "src/", "--ignore-missing-imports"],
        "config_files": ["mypy.ini", ".mypy.ini", "pyproject.toml", "setup.cfg"],
        "install_hint": "pip install mypy",
    },
    "pytest": {
        "name": "pytest",
        "category": "test",
        "stacks": ["python"],
        "cli": "pytest",
        "run_args": ["pytest", "--tb=short", "-q"],
        "config_files": ["pytest.ini", "pyproject.toml", "setup.cfg", "conftest.py"],
        "install_hint": "pip install pytest",
    },
    "black": {
        "name": "Black",
        "category": "format",
        "stacks": ["python"],
        "cli": "black",
        "run_args": ["black", "--check", "."],
        "fix_args": ["black", "."],
        "config_files": ["pyproject.toml"],
        "install_hint": "pip install black",
    },
    "ruff-format": {
        "name": "Ruff Format",
        "category": "format",
        "stacks": ["python"],
        "cli": "ruff",
        "run_args": ["ruff", "format", "--check", "."],
        "fix_args": ["ruff", "format", "."],
        "config_files": ["ruff.toml", ".ruff.toml", "pyproject.toml"],
        "install_hint": "pip install ruff",
    },
    # Node / TypeScript
    "eslint": {
        "name": "ESLint",
        "category": "lint",
        "stacks": ["node", "typescript"],
        "cli": "eslint",
        "run_args": ["npx", "eslint", "."],
        "fix_args": ["npx", "eslint", "--fix", "."],
        "config_files": [
            ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.json",
            ".eslintrc.yml", ".eslintrc.yaml", "eslint.config.js",
            "eslint.config.mjs",
        ],
        "install_hint": "npm install -D eslint",
    },
    "prettier": {
        "name": "Prettier",
        "category": "format",
        "stacks": ["node", "typescript"],
        "cli": "prettier",
        "run_args": ["npx", "prettier", "--check", "."],
        "fix_args": ["npx", "prettier", "--write", "."],
        "config_files": [
            ".prettierrc", ".prettierrc.json", ".prettierrc.yml",
            ".prettierrc.js", "prettier.config.js",
        ],
        "install_hint": "npm install -D prettier",
    },
    "tsc": {
        "name": "TypeScript Compiler",
        "category": "typecheck",
        "stacks": ["typescript"],
        "cli": "tsc",
        "run_args": ["npx", "tsc", "--noEmit"],
        "config_files": ["tsconfig.json"],
        "install_hint": "npm install -D typescript",
    },
    "jest": {
        "name": "Jest",
        "category": "test",
        "stacks": ["node", "typescript"],
        "cli": "jest",
        "run_args": ["npx", "jest", "--passWithNoTests"],
        "config_files": ["jest.config.js", "jest.config.ts", "jest.config.json"],
        "install_hint": "npm install -D jest",
    },
    "vitest": {
        "name": "Vitest",
        "category": "test",
        "stacks": ["node", "typescript"],
        "cli": "vitest",
        "run_args": ["npx", "vitest", "run"],
        "config_files": ["vitest.config.ts", "vitest.config.js", "vite.config.ts"],
        "install_hint": "npm install -D vitest",
    },
    # Go
    "go-vet": {
        "name": "go vet",
        "category": "lint",
        "stacks": ["go"],
        "cli": "go",
        "run_args": ["go", "vet", "./..."],
        "config_files": [],
    },
    "golangci-lint": {
        "name": "golangci-lint",
        "category": "lint",
        "stacks": ["go"],
        "cli": "golangci-lint",
        "run_args": ["golangci-lint", "run"],
        "config_files": [".golangci.yml", ".golangci.yaml", ".golangci.toml"],
    },
    "go-test": {
        "name": "go test",
        "category": "test",
        "stacks": ["go"],
        "cli": "go",
        "run_args": ["go", "test", "-race", "-count=1", "./..."],
        "config_files": [],
    },
    # Rust
    "clippy": {
        "name": "Clippy",
        "category": "lint",
        "stacks": ["rust"],
        "cli": "cargo",
        "run_args": ["cargo", "clippy", "--", "-D", "warnings"],
        "config_files": [],
    },
    "rustfmt": {
        "name": "rustfmt",
        "category": "format",
        "stacks": ["rust"],
        "cli": "cargo",
        "run_args": ["cargo", "fmt", "--", "--check"],
        "fix_args": ["cargo", "fmt"],
        "config_files": ["rustfmt.toml", ".rustfmt.toml"],
    },
    "cargo-test": {
        "name": "cargo test",
        "category": "test",
        "stacks": ["rust"],
        "cli": "cargo",
        "run_args": ["cargo", "test"],
        "config_files": [],
    },
}


def _run(
    args: list[str],
    cwd: Path,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    """Run a command and return the result."""
    return subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _tool_matches_stack(tool: dict, stack_name: str) -> bool:
    """Check if a tool is relevant for a given stack."""
    for s in tool.get("stacks", []):
        if stack_name == s or stack_name.startswith(s + "-") or stack_name.startswith(s):
            return True
    return False


# ═══════════════════════════════════════════════════════════════════
#  Detect
# ═══════════════════════════════════════════════════════════════════


def quality_status(project_root: Path, *, stack_names: list[str] | None = None) -> dict:
    """Detect quality tools configured and available.

    Returns:
        {
            "tools": [{
                id, name, category, cli_available,
                config_found, config_file, relevant
            }, ...],
            "categories": {lint: int, typecheck: int, test: int, format: int},
            "has_quality": bool,
        }
    """
    tools: list[dict] = []
    categories: dict[str, int] = {"lint": 0, "typecheck": 0, "test": 0, "format": 0}

    for tool_id, spec in _QUALITY_TOOLS.items():
        cli_available = shutil.which(spec["cli"]) is not None

        # Check config files
        config_found = False
        config_file = ""
        for cf in spec.get("config_files", []):
            if (project_root / cf).is_file():
                config_found = True
                config_file = cf
                break

        # Relevance to detected stacks
        relevant = True
        if stack_names:
            relevant = any(_tool_matches_stack(spec, s) for s in stack_names)

        # Only include if tool is relevant or has config
        if not relevant and not config_found:
            continue

        tool_info = {
            "id": tool_id,
            "name": spec["name"],
            "category": spec["category"],
            "cli_available": cli_available,
            "config_found": config_found,
            "config_file": config_file,
            "relevant": relevant,
            "install_hint": spec.get("install_hint", ""),
        }
        tools.append(tool_info)

        if cli_available and relevant:
            categories[spec["category"]] = categories.get(spec["category"], 0) + 1

    # ── Missing tools (for installable quality tools) ───────────────
    from src.core.services.tool_requirements import check_required_tools

    # Determine which tool IDs from our registry are relevant
    quality_tool_ids = ["ruff", "mypy", "pytest", "black", "eslint", "prettier"]
    missing_tools = check_required_tools(quality_tool_ids)

    return {
        "tools": tools,
        "categories": categories,
        "has_quality": any(t["cli_available"] and t["relevant"] for t in tools),
        "missing_tools": missing_tools,
    }


# ═══════════════════════════════════════════════════════════════════
#  Observe / Act
# ═══════════════════════════════════════════════════════════════════


def quality_run(
    project_root: Path,
    *,
    tool: str | None = None,
    category: str | None = None,
    fix: bool = False,
) -> dict:
    """Run quality checks.

    Args:
        tool: Specific tool to run (e.g. 'ruff', 'mypy').
        category: Run all tools in a category ('lint', 'typecheck', 'test', 'format').
        fix: If True, run auto-fix where supported.

    Returns:
        {
            "results": [{
                tool, name, category, passed, exit_code,
                stdout, stderr, fixable
            }, ...],
            "all_passed": bool,
        }
    """
    results: list[dict] = []

    tools_to_run: list[tuple[str, dict]] = []

    if tool:
        spec = _QUALITY_TOOLS.get(tool)
        if spec:
            tools_to_run.append((tool, spec))
        else:
            return {"error": f"Unknown tool: {tool}", "available": list(_QUALITY_TOOLS.keys())}
    elif category:
        for tid, spec in _QUALITY_TOOLS.items():
            if spec["category"] == category:
                tools_to_run.append((tid, spec))
    else:
        # Run all available tools
        for tid, spec in _QUALITY_TOOLS.items():
            tools_to_run.append((tid, spec))

    for tool_id, spec in tools_to_run:
        if not shutil.which(spec["cli"]):
            continue

        if fix and spec.get("fix_args"):
            args = spec["fix_args"]
        else:
            args = spec["run_args"]

        try:
            r = _run(args, cwd=project_root, timeout=120)
            passed = r.returncode == 0
            has_fix = "fix_args" in spec

            results.append({
                "tool": tool_id,
                "name": spec["name"],
                "category": spec["category"],
                "passed": passed,
                "exit_code": r.returncode,
                "stdout": r.stdout.strip()[:3000],
                "stderr": r.stderr.strip()[:1000],
                "fixable": has_fix and not passed and not fix,
            })
        except subprocess.TimeoutExpired:
            results.append({
                "tool": tool_id,
                "name": spec["name"],
                "category": spec["category"],
                "passed": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "Timed out",
                "fixable": False,
            })
        except FileNotFoundError:
            continue

    return {
        "results": results,
        "all_passed": all(r["passed"] for r in results) if results else True,
        "total": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "failed": sum(1 for r in results if not r["passed"]),
    }


def quality_lint(project_root: Path, *, fix: bool = False) -> dict:
    """Run lint checks only."""
    return quality_run(project_root, category="lint", fix=fix)


def quality_typecheck(project_root: Path) -> dict:
    """Run type-checking only."""
    return quality_run(project_root, category="typecheck")


def quality_test(project_root: Path) -> dict:
    """Run tests only."""
    return quality_run(project_root, category="test")


def quality_format(project_root: Path, *, fix: bool = False) -> dict:
    """Check formatting (or fix if fix=True)."""
    return quality_run(project_root, category="format", fix=fix)


# ═══════════════════════════════════════════════════════════════════
#  Facilitate (generate)
# ═══════════════════════════════════════════════════════════════════


_RUFF_CONFIG = """\
# Ruff configuration — generated by DevOps Control Plane
# https://docs.astral.sh/ruff/

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # pyflakes
    "I",    # isort
    "N",    # pep8-naming
    "UP",   # pyupgrade
    "B",    # flake8-bugbear
    "SIM",  # flake8-simplify
    "RUF",  # ruff-specific
]
ignore = [
    "E501",   # line too long (handled by formatter)
]

[tool.ruff.lint.isort]
known-first-party = ["src"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
"""


_MYPY_CONFIG = """\
# mypy configuration — generated by DevOps Control Plane
# https://mypy.readthedocs.io/

[mypy]
python_version = 3.12
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = false
ignore_missing_imports = true
check_untyped_defs = true
"""

_ESLINT_CONFIG = """\
// ESLint flat config — generated by DevOps Control Plane
import js from "@eslint/js";

export default [
  js.configs.recommended,
  {
    rules: {
      "no-unused-vars": "warn",
      "no-undef": "error",
    },
  },
  {
    ignores: ["node_modules/", "dist/", "build/"],
  },
];
"""

_PRETTIER_CONFIG = """\
{
  "semi": true,
  "singleQuote": false,
  "tabWidth": 2,
  "trailingComma": "es5",
  "printWidth": 100
}
"""


def generate_quality_config(
    project_root: Path,
    stack_name: str,
) -> dict:
    """Generate quality tool configuration for a stack.

    Returns:
        {"ok": True, "files": [{path, content, reason}, ...]}
    """
    from src.core.models.template import GeneratedFile

    files: list[dict] = []

    if stack_name.startswith("python") or stack_name == "python":
        # Ruff config (as pyproject.toml section) — standalone ruff.toml
        files.append(
            GeneratedFile(
                path="ruff.toml",
                content=_RUFF_CONFIG.replace("[tool.ruff]", "[ruff]")
                .replace("[tool.ruff.lint]", "[lint]")
                .replace("[tool.ruff.lint.isort]", "[lint.isort]")
                .replace("[tool.ruff.format]", "[format]"),
                overwrite=False,
                reason="Ruff linter/formatter configuration",
            ).model_dump()
        )

        files.append(
            GeneratedFile(
                path="mypy.ini",
                content=_MYPY_CONFIG,
                overwrite=False,
                reason="mypy type-checker configuration",
            ).model_dump()
        )

    elif stack_name.startswith("node") or stack_name == "typescript":
        files.append(
            GeneratedFile(
                path="eslint.config.mjs",
                content=_ESLINT_CONFIG,
                overwrite=False,
                reason="ESLint linter configuration (flat config)",
            ).model_dump()
        )

        files.append(
            GeneratedFile(
                path=".prettierrc",
                content=_PRETTIER_CONFIG,
                overwrite=False,
                reason="Prettier formatter configuration",
            ).model_dump()
        )

    else:
        return {"error": f"No quality config templates for stack: {stack_name}"}

    return {"ok": True, "files": files, "count": len(files)}
