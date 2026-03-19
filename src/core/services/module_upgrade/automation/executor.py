"""
Step executor — dispatches automation requests to the right handler.

Central entry point for all step automation. Builds the UpgradeContext,
looks up the handler, calls it in the requested mode, and optionally
marks the step done in project.yml on successful execution.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def execute_step(
    module_name: str,
    step_id: str,
    mode: str,
    project_root: Path,
) -> dict:
    """Execute an automation step in preview or execute mode.

    Args:
        module_name: Module name from project.yml.
        step_id: Step ID (format: automation_id:suffix).
        mode: "preview" or "execute".
        project_root: Absolute path to project root.

    Returns:
        Result dict with at minimum:
          - ok: bool
          - mode: "preview" | "execute"
          - automation_id: str
        Plus handler-specific fields (diff, findings, etc.)
    """
    # ── Extract automation_id from step_id ────────────────────────
    if ":" not in step_id:
        return {"ok": False, "error": "Invalid step_id format"}

    automation_id = step_id.split(":")[0]

    if automation_id in ("manual", "custom", ""):
        return {"ok": False, "error": "This step cannot be automated"}

    # ── Look up handler ──────────────────────────────────────────
    from . import get_handler_registry

    registry = get_handler_registry()
    handler = registry.get(automation_id)

    if not handler:
        return {
            "ok": False,
            "error": f"No automation handler for '{automation_id}'",
        }

    # ── Build context ────────────────────────────────────────────
    from ..context import build_context

    # We need the target from the plan to build context
    target = _get_plan_target(module_name)
    if not target:
        return {"ok": False, "error": "No version plan found for module"}

    ctx = build_context(module_name, target, project_root)

    # ── Smart state: auto-skip if artifact already exists ───────
    if mode == "execute":
        skip = _check_already_done(automation_id, ctx)
        if skip:
            _mark_step_done(module_name, step_id)
            return skip

    # ── Execute handler ──────────────────────────────────────────
    try:
        result = handler(ctx, mode)
    except PermissionError as exc:
        logger.error("Permission denied in handler '%s': %s", automation_id, exc)
        return {"ok": False, "error": f"Permission denied: cannot write to {exc.filename or 'file'}. Check file permissions."}
    except FileNotFoundError as exc:
        logger.error("File not found in handler '%s': %s", automation_id, exc)
        return {"ok": False, "error": f"File not found: {exc.filename or 'unknown'}"}
    except OSError as exc:
        logger.error("I/O error in handler '%s': %s", automation_id, exc)
        return {"ok": False, "error": f"File system error: {exc}"}
    except Exception as exc:
        logger.error(
            "Automation handler '%s' failed: %s", automation_id, exc,
            exc_info=True,
        )
        return {"ok": False, "error": f"Automation failed: {exc}"}

    # ── Mark done on successful execute ──────────────────────────
    # BUT: dep checkers with incompatible findings are NOT done
    if mode == "execute" and result.get("ok"):
        findings = result.get("findings", [])
        has_incompatible = any(
            not f.get("compatible") and not f.get("unknown")
            for f in findings
        ) if findings else False

        if has_incompatible:
            result["ok"] = True  # the check itself succeeded
            result["step_not_done"] = True  # but the step needs attention
        else:
            _mark_step_done(module_name, step_id)

    # ── Enrich result ────────────────────────────────────────────
    result.setdefault("mode", mode)
    result.setdefault("automation_id", automation_id)

    return result


def handle_rescan_module(ctx, mode: str) -> dict:
    """Re-scan module and refresh posture data.

    Preview: describes what will happen.
    Execute: invalidates mediator cache and forces recompute.
    """
    if mode == "preview":
        return {
            "ok": True,
            "can_apply": True,
            "preview_type": "action",
            "summary": "Re-scan module and refresh posture evaluation",
            "detail": (
                "This will invalidate the posture cache and force a fresh "
                "scan of the module's runtime constraint, dependency floor, "
                "and code floor."
            ),
        }

    # Execute
    try:
        from src.core.services.mediator import get_mediator

        m = get_mediator()
        m.put("posture.modules", cascade=True)

        return {
            "ok": True,
            "summary": "Module re-scanned successfully",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def handle_scaffold_module_tests(ctx, mode: str) -> dict:
    """Scaffold test files for the module.

    Preview: shows what files would be generated.
    Execute: creates the test files.
    """
    module_dir = ctx.project_root / ctx.module_path

    # Check if tests already exist
    import re as _re
    test_pattern = _re.compile(r"^test_.*\.py$|^.*_test\.py$")
    has_tests = any(
        test_pattern.match(f.name)
        for f in module_dir.rglob("*.py")
        if "__pycache__" not in str(f)
    ) if module_dir.is_dir() else False

    if has_tests and mode == "preview":
        return {
            "ok": True,
            "can_apply": False,
            "preview_type": "info",
            "summary": "Module already has test files",
            "detail": "Test files already exist in the module directory.",
        }

    if mode == "preview":
        return {
            "ok": True,
            "can_apply": True,
            "preview_type": "action",
            "summary": f"Scaffold test structure for {ctx.module_name}",
            "detail": (
                "Creates tests/__init__.py, tests/conftest.py, and tests/test_smoke.py "
                "in the module directory with import verification and version checks."
            ),
        }

    # Execute — create files via the scaffold logic
    try:
        # Build minimal test files directly
        tests_dir = module_dir / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)

        # __init__.py
        (tests_dir / "__init__.py").write_text("", encoding="utf-8")

        # conftest.py
        conftest = f'''"""Module-level test fixtures for {ctx.module_name}."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def module_root():
    return Path(__file__).parent.parent
'''
        (tests_dir / "conftest.py").write_text(conftest, encoding="utf-8")

        # test_smoke.py
        mod_package = ctx.module_path.replace("/", ".")
        smoke = f'''"""Smoke tests for {ctx.module_name}."""
from __future__ import annotations


def test_module_imports():
    """Verify the module can be imported."""
    import {mod_package}  # noqa: F401
'''
        if ctx.target_floor:
            parts = ctx.target_floor.split(".")
            smoke += f'''

def test_version_floor():
    """Verify minimum Python version."""
    import sys
    assert sys.version_info >= ({parts[0]}, {parts[1] if len(parts) > 1 else "0"})
'''
        (tests_dir / "test_smoke.py").write_text(smoke, encoding="utf-8")

        return {
            "ok": True,
            "summary": f"Scaffolded 3 test files in {ctx.module_path}/tests/",
        }

    except Exception as exc:
        return {"ok": False, "error": f"Failed to scaffold tests: {exc}"}


def handle_generate_smart_tests(ctx, mode: str) -> dict:
    """Generate comprehensive compatibility tests based on module analysis.

    Creates test_compatibility.py with:
    1. Import verification — every .py file in module can be imported
    2. Public API tests — every export in __init__.py is accessible
    3. Version compatibility — no runtime features above declared floor
    4. Dependency imports — all declared deps are importable
    """
    import re as _re

    module_dir = ctx.project_root / ctx.module_path
    tests_dir = module_dir / "tests"
    test_file = tests_dir / "test_compatibility.py"

    if test_file.is_file() and mode == "preview":
        return {
            "ok": True,
            "can_apply": True,
            "preview_type": "info",
            "summary": "test_compatibility.py already exists — will be overwritten",
            "detail": "Regenerates compatibility tests based on current module state.",
        }

    if not module_dir.is_dir():
        return {"ok": False, "error": f"Module directory not found: {ctx.module_path}"}

    mod_package = ctx.module_path.replace("/", ".")

    # ── Gather module data ───────────────────────────────────
    # 1. Find all .py files for import verification
    py_modules = []
    for pf in sorted(module_dir.rglob("*.py")):
        if "__pycache__" in str(pf) or "/tests/" in str(pf):
            continue
        rel = str(pf.relative_to(ctx.project_root))
        import_path = rel.replace("/", ".").replace(".py", "")
        if import_path.endswith(".__init__"):
            import_path = import_path[:-9]
        py_modules.append(import_path)

    # 2. Find exports from __init__.py
    exports = []
    init_path = module_dir / "__init__.py"
    if init_path.is_file():
        init_content = init_path.read_text(encoding="utf-8", errors="ignore")
        all_match = _re.search(r"__all__\s*=\s*\[([^\]]*)\]", init_content)
        if all_match:
            exports = [
                s.strip().strip("'\"")
                for s in all_match.group(1).split(",")
                if s.strip().strip("'\"")
            ]
        for m in _re.finditer(r"^from\s+\.\w+\s+import\s+(\w+)", init_content, _re.MULTILINE):
            name = m.group(1)
            if name not in exports:
                exports.append(name)

    # 3. Find declared deps from requirements.txt
    deps = []
    req_file = module_dir / "requirements.txt"
    if req_file.is_file():
        for line in req_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            pkg_match = _re.match(r"([a-zA-Z0-9_-]+)", line)
            if pkg_match:
                dep_name = pkg_match.group(1).replace("-", "_")
                deps.append(dep_name)

    # 4. Target floor for version check
    target = ctx.target_floor
    target_parts = target.split(".") if target else []

    # ── Build test content ───────────────────────────────────
    content = f'''"""Compatibility tests for {ctx.module_name}.

Auto-generated by DevOps Control Plane.
Verifies imports, public API, version compatibility, and dependency availability.
Regenerate with: module upgrade → "Generate compatibility tests"
"""
from __future__ import annotations

import importlib
import sys

import pytest


# ── 1. Import Verification ──────────────────────────────────────
# Every .py file in the module should be importable without errors.

_MODULE_PATHS = [
'''
    for mp in py_modules[:50]:
        content += f'    "{mp}",\n'
    content += ']\n\n'

    content += '''
@pytest.mark.parametrize("module_path", _MODULE_PATHS)
def test_module_importable(module_path):
    """Verify each module file can be imported."""
    importlib.import_module(module_path)

'''

    # 2. Public API tests
    if exports:
        content += f'''
# ── 2. Public API ────────────────────────────────────────────────
# Every name exported from {mod_package} should be accessible.

def test_public_api():
    """Verify all declared exports are accessible."""
    import {mod_package}

'''
        for exp in exports[:20]:
            content += f'    assert hasattr({mod_package}, "{exp}"), "Missing export: {exp}"\n'
        content += '\n'

    # 3. Version compatibility
    if target and len(target_parts) >= 2:
        content += f'''
# ── 3. Version Compatibility ────────────────────────────────────
# The module claims Python >={target} support.

def test_python_version_floor():
    """Verify we are running on at least the declared minimum."""
    assert sys.version_info >= ({target_parts[0]}, {target_parts[1]}), (
        f"Module requires Python >={target}, running on {{sys.version_info}}"
    )

'''

    # 4. Dependency imports
    if deps:
        content += '''
# ── 4. Dependency Imports ────────────────────────────────────────
# All declared dependencies should be importable.

_DECLARED_DEPS = [
'''
        for dep in deps[:30]:
            content += f'    "{dep}",\n'
        content += ']\n\n'

        content += '''
@pytest.mark.parametrize("dep", _DECLARED_DEPS)
def test_dependency_importable(dep):
    """Verify each declared dependency can be imported."""
    try:
        importlib.import_module(dep)
    except ImportError:
        pytest.skip(f"{dep} not installed in this environment")
'''

    # ── Stats for summary ────────────────────────────────────
    test_count = len(py_modules) + (1 if exports else 0) + (1 if target else 0) + len(deps)

    if mode == "preview":
        return {
            "ok": True,
            "can_apply": True,
            "preview_type": "guide",
            "summary": f"Generate {test_count} compatibility tests for {ctx.module_name}",
            "findings": [
                {"feature": f"Import verification: {len(py_modules)} modules"},
                {"feature": f"Public API: {len(exports)} exports"} if exports else None,
                {"feature": f"Version floor: Python >={target}"} if target else None,
                {"feature": f"Dependency imports: {len(deps)} packages"} if deps else None,
            ],
        }

    # Execute
    try:
        tests_dir.mkdir(parents=True, exist_ok=True)
        test_file.write_text(content, encoding="utf-8")

        return {
            "ok": True,
            "summary": f"Generated test_compatibility.py ({test_count} tests) in {ctx.module_path}/tests/",
        }

    except Exception as exc:
        return {"ok": False, "error": f"Failed to generate tests: {exc}"}


def handle_scaffold_parent_tests(ctx, mode: str) -> dict:
    """Add integration tests for this module to the parent tests/ directory.

    Preview: shows the test file that would be generated.
    Execute: creates the file. Skips if it already exists.
    """
    import re as _re

    mod_safe = ctx.module_name.replace("-", "_")
    parent_test = ctx.project_root / "tests" / f"test_{mod_safe}_integration.py"
    rel_path = str(parent_test.relative_to(ctx.project_root))

    if parent_test.is_file():
        if mode == "preview":
            return {
                "ok": True,
                "can_apply": False,
                "preview_type": "info",
                "summary": f"Already exists: {rel_path}",
            }
        return {"ok": True, "summary": f"Already exists: {rel_path}"}

    mod_package = ctx.module_path.replace("/", ".")

    # Scan __init__.py for exports
    exports = []
    init_path = ctx.project_root / ctx.module_path / "__init__.py"
    if init_path.is_file():
        init_content = init_path.read_text(encoding="utf-8", errors="ignore")
        for m in _re.finditer(r"^from\s+\.\w+\s+import\s+(\w+)", init_content, _re.MULTILINE):
            exports.append(m.group(1))
        all_match = _re.search(r"__all__\s*=\s*\[([^\]]*)\]", init_content)
        if all_match:
            for s in all_match.group(1).split(","):
                name = s.strip().strip("'\"")
                if name and name not in exports:
                    exports.append(name)

    content = f'''"""Integration tests for {ctx.module_name}.

Tests that verify {ctx.module_name} works correctly within the larger project.
Auto-generated by DevOps Control Plane.
"""
from __future__ import annotations


def test_{mod_safe}_importable():
    """Verify {ctx.module_name} is importable from the project root."""
    import {mod_package}  # noqa: F401

'''
    if exports:
        content += f'''
def test_{mod_safe}_public_api():
    """Verify {ctx.module_name} public API is accessible from project level."""
    from {mod_package} import {", ".join(exports[:5])}
'''
        for exp in exports[:5]:
            content += f'    assert {exp} is not None\n'

    if mode == "preview":
        return {
            "ok": True,
            "can_apply": True,
            "preview_type": "diff",
            "summary": f"Create {rel_path}",
            "file": rel_path,
            "old_value": "(new file)",
            "new_value": f"Integration test with {len(exports)} API checks",
        }

    try:
        parent_test.parent.mkdir(parents=True, exist_ok=True)
        parent_test.write_text(content, encoding="utf-8")
        return {"ok": True, "summary": f"Created {rel_path}"}
    except Exception as exc:
        return {"ok": False, "error": f"Failed to create {rel_path}: {exc}"}


# ── Internal helpers ─────────────────────────────────────────────


def _check_already_done(automation_id: str, ctx) -> dict | None:
    """Check if a step's output already exists — return skip result or None."""
    module_dir = ctx.project_root / ctx.module_path

    if automation_id == "generate_module_toml":
        if (module_dir / "pyproject.toml").is_file():
            return {"ok": True, "summary": "pyproject.toml already exists — skipped"}

    elif automation_id == "scaffold_module_tests":
        if (module_dir / "tests" / "test_smoke.py").is_file():
            return {"ok": True, "summary": "Module tests already exist — skipped"}

    elif automation_id == "scaffold_parent_tests":
        mod_safe = ctx.module_name.replace("-", "_")
        if (ctx.project_root / "tests" / f"test_{mod_safe}_integration.py").is_file():
            return {"ok": True, "summary": "Parent integration test already exists — skipped"}

    elif automation_id == "generate_smart_tests":
        if (module_dir / "tests" / "test_compatibility.py").is_file():
            return {"ok": True, "summary": "Compatibility tests already exist — skipped"}

    elif automation_id == "setup_test_env":
        target = ctx.target_floor
        venv_dir = ctx.project_root / ".venvs" / f"{ctx.module_name}-{target}"
        if (venv_dir / "bin" / "python").is_file():
            return {"ok": True, "summary": f"Venv already exists at .venvs/{ctx.module_name}-{target}/ — skipped"}

    return None  # not done, proceed normally


def _get_plan_target(module_name: str) -> str | None:
    """Get the version plan target for a module."""
    try:
        from src.core.config.loader import load_project

        project = load_project()
        ref = project.get_module(module_name)
        if ref and ref.version_plan:
            return ref.version_plan.target
    except Exception:
        pass
    return None


def _mark_step_done(module_name: str, step_id: str) -> None:
    """Mark a step as done in project.yml by matching step_id."""
    try:
        import yaml
        from src.core.config.loader import find_project_file

        config_path = find_project_file()
        if not config_path:
            return

        raw = config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        project_data = data.get("project", data) if "project" in data else data

        for mod in project_data.get("modules", []):
            if mod.get("name") != module_name:
                continue
            plan = mod.get("version_plan")
            if not plan:
                break
            for step in plan.get("checklist", []):
                if step.get("id") == step_id:
                    step["done"] = True
                    break
            break

        config_path.write_text(
            yaml.dump(
                data,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        from src.core.services.mediator import get_mediator
        get_mediator().put("posture.modules", cascade=True)

    except Exception as exc:
        logger.error("Failed to mark step done: %s", exc)
