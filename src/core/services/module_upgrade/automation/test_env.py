"""
Test environment setup — create venvs and run isolated tests.

Handles:
  - Detecting available Python versions on the system
  - Creating a venv with a specific Python version
  - Installing module deps in the venv
  - Running tests using the venv's Python

Uses tool_install infrastructure for missing Python detection.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..context import UpgradeContext

logger = logging.getLogger(__name__)


def detect_python_versions() -> dict:
    """Detect available Python versions on the system.

    Returns:
        {
            "versions": [{"version": "3.8", "path": "/usr/bin/python3.8"}, ...],
            "default": "3.12",
            "default_path": "/usr/bin/python3",
        }
    """
    versions = []

    # Check common version binaries
    for minor in range(7, 15):
        ver = f"3.{minor}"
        path = shutil.which(f"python{ver}")
        if path:
            # Verify it actually works
            try:
                result = subprocess.run(
                    [path, "--version"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    actual = result.stdout.strip().replace("Python ", "")
                    versions.append({
                        "version": ver,
                        "full_version": actual,
                        "path": path,
                    })
            except Exception:
                pass

    # Default python3
    default_path = shutil.which("python3") or shutil.which("python")
    default_ver = ""
    if default_path:
        try:
            result = subprocess.run(
                [default_path, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                full = result.stdout.strip().replace("Python ", "")
                parts = full.split(".")
                default_ver = f"{parts[0]}.{parts[1]}" if len(parts) >= 2 else full
        except Exception:
            pass

    return {
        "versions": versions,
        "default": default_ver,
        "default_path": default_path or "",
    }


def handle_setup_test_env(ctx: UpgradeContext, mode: str) -> dict:
    """Set up a test environment for the target Python version.

    Preview: shows what Python versions are available, whether a venv
    will be created, and what deps will be installed.

    Execute: creates the venv and installs deps.
    """
    target = ctx.target_floor
    module_dir = ctx.project_root / ctx.module_path

    # Detect available versions
    py_info = detect_python_versions()
    available = {v["version"]: v["path"] for v in py_info["versions"]}
    target_path = available.get(target)

    # Check for existing venv
    venv_dir = ctx.project_root / ".venvs" / f"{ctx.module_name}-{target}"
    venv_exists = (venv_dir / "bin" / "python").is_file()

    # Check for requirements
    req_file = None
    for candidate in ["requirements.txt", "pyproject.toml"]:
        if (module_dir / candidate).is_file():
            req_file = candidate
            break

    if mode == "preview":
        result = {
            "ok": True,
            "can_apply": bool(target_path),
            "preview_type": "guide",
            "summary": "",
            "findings": [],
        }

        if target_path:
            result["summary"] = f"Python {target} available at {target_path}"
            result["findings"].append({
                "feature": f"Python {target}",
                "file": target_path,
                "version": target,
            })
            if venv_exists:
                result["findings"].append({
                    "feature": "Venv already exists",
                    "file": str(venv_dir.relative_to(ctx.project_root)),
                })
                result["summary"] += " — venv already exists"
            else:
                result["findings"].append({
                    "feature": f"Will create venv at .venvs/{ctx.module_name}-{target}/",
                })
            if req_file:
                result["findings"].append({
                    "feature": f"Will install deps from {req_file}",
                })
        else:
            # Target Python not available
            avail_list = ", ".join(v["version"] for v in py_info["versions"]) or "none"
            result["summary"] = f"Python {target} not found on system"
            result["can_apply"] = False
            result["findings"].append({
                "feature": f"Available: {avail_list}",
                "note": f"Install Python {target} to create an isolated test environment",
            })
            # Offer system Python as alternative
            if py_info["default"]:
                result["findings"].append({
                    "feature": f"System Python: {py_info['default']} at {py_info['default_path']}",
                    "note": "You can use the system Python instead (won't validate target compat)",
                })

        return result

    # Execute
    if not target_path:
        return {
            "ok": False,
            "error": f"Python {target} not found. Available: {', '.join(available.keys()) or 'none'}",
        }

    try:
        # Create venv
        if not venv_exists:
            logger.info("Creating venv: %s -m venv %s", target_path, venv_dir)
            venv_dir.parent.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                [target_path, "-m", "venv", str(venv_dir), "--clear"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                return {"ok": False, "error": f"Failed to create venv: {result.stderr}"}

        venv_pip = str(venv_dir / "bin" / "pip")
        venv_python = str(venv_dir / "bin" / "python")

        # Upgrade pip
        subprocess.run(
            [venv_python, "-m", "pip", "install", "--upgrade", "pip"],
            capture_output=True, text=True, timeout=120,
        )

        # Install deps
        installed = []
        if req_file == "requirements.txt":
            req_path = module_dir / "requirements.txt"
            result = subprocess.run(
                [venv_pip, "install", "-r", str(req_path)],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                return {
                    "ok": False,
                    "error": f"Failed to install deps: {result.stderr[-500:]}",
                    "output": result.stdout[-500:],
                }
            installed.append(f"requirements.txt ({req_path})")

        elif req_file == "pyproject.toml":
            result = subprocess.run(
                [venv_pip, "install", "-e", str(module_dir)],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                return {
                    "ok": False,
                    "error": f"Failed to install module: {result.stderr[-500:]}",
                    "output": result.stdout[-500:],
                }
            installed.append(f"pyproject.toml (editable install)")

        # Install pytest in the venv
        subprocess.run(
            [venv_pip, "install", "pytest"],
            capture_output=True, text=True, timeout=120,
        )
        installed.append("pytest")

        rel_venv = str(venv_dir.relative_to(ctx.project_root))
        return {
            "ok": True,
            "summary": f"Test environment ready: {rel_venv} (Python {target})",
            "venv_path": rel_venv,
            "installed": installed,
        }

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Timed out creating test environment"}
    except Exception as exc:
        return {"ok": False, "error": f"Failed to set up test environment: {exc}"}


def handle_run_isolated_tests(ctx: UpgradeContext, mode: str) -> dict:
    """Run tests using the target Python venv.

    Preview: shows what will be run and where.
    Execute: runs pytest in the venv and returns results.
    """
    target = ctx.target_floor
    venv_dir = ctx.project_root / ".venvs" / f"{ctx.module_name}-{target}"
    venv_python = venv_dir / "bin" / "python"
    module_dir = ctx.project_root / ctx.module_path
    tests_dir = module_dir / "tests"

    if mode == "preview":
        if not venv_python.is_file():
            return {
                "ok": True,
                "can_apply": False,
                "preview_type": "info",
                "summary": f"No venv found for Python {target}",
                "detail": "Run 'Set up test environment' first to create the venv.",
            }

        if not tests_dir.is_dir():
            return {
                "ok": True,
                "can_apply": False,
                "preview_type": "info",
                "summary": "No tests directory found",
                "detail": "Run 'Scaffold module tests' first to create test files.",
            }

        return {
            "ok": True,
            "can_apply": True,
            "preview_type": "info",
            "summary": f"Run pytest on Python {target}",
            "detail": (
                f"Will execute the test suite using the Python {target} venv.\n"
                f"Venv: .venvs/{ctx.module_name}-{target}/\n"
                f"Tests: {tests_dir.relative_to(ctx.project_root)}/"
            ),
        }

    # Check if compat fix steps are done before running tests
    try:
        from src.core.config.loader import load_project
        proj = load_project(ctx.project_root)
        for mod in (proj.get("modules") or []):
            if mod.get("name") == ctx.module_name:
                plan = mod.get("version_plan") or {}
                for step in (plan.get("checklist") or []):
                    aid = (step.get("automation_id") or "").split("__")[0]
                    if aid == "fix_compat_auto" and not step.get("done"):
                        return {
                            "ok": False,
                            "error": "Code fixes haven't been applied yet. Apply compat fixes first, then re-run tests.",
                        }
                break
    except Exception:
        pass  # best effort — don't block tests if project.yml read fails

    # Execute
    if not venv_python.is_file():
        return {"ok": False, "error": f"Venv not found at {venv_dir}. Set up test environment first."}

    test_target = str(tests_dir) if tests_dir.is_dir() else str(module_dir)

    try:
        # Set PYTHONPATH so the module (and project root) are importable
        # in the isolated venv without needing `pip install -e .`
        import os as _os
        env = _os.environ.copy()
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(ctx.project_root) + (_os.pathsep + existing if existing else "")

        result = subprocess.run(
            [str(venv_python), "-m", "pytest", test_target, "-v", "--tb=short"],
            capture_output=True, text=True, timeout=300,
            cwd=str(ctx.project_root),
            env=env,
        )

        stdout = result.stdout or ""
        stderr = result.stderr or ""
        output = stdout + stderr

        # Parse pytest summary line (order varies: "39 failed, 16 passed" or "16 passed, 39 failed")
        import re
        passed = 0
        failed = 0
        errors = 0
        skipped = 0
        pm = re.search(r"(\d+) passed", output)
        fm = re.search(r"(\d+) failed", output)
        em = re.search(r"(\d+) error", output)
        sm = re.search(r"(\d+) skipped", output)
        if pm: passed = int(pm.group(1))
        if fm: failed = int(fm.group(1))
        if em: errors = int(em.group(1))
        if sm: skipped = int(sm.group(1))
        summary_match = pm or fm  # at least one must exist for a valid summary

        # Show last 30 lines
        output_lines = output.strip().split("\n")
        tail = "\n".join(output_lines[-30:]) if len(output_lines) > 30 else output

        ok = result.returncode == 0 or result.returncode == 5  # 5 = no tests collected

        res = {
            "ok": ok,
            "summary": (
                f"Python {target}: {passed} passed, {failed} failed, {skipped} skipped"
                if summary_match
                else f"pytest exited with code {result.returncode}"
            ),
            "output": tail,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "skipped": skipped,
            "exit_code": result.returncode,
        }

        # Detect common compat failures and suggest fixes
        if not ok:
            compat_hints = _detect_compat_failures(output, target)
            if compat_hints:
                res["compat_hints"] = compat_hints

        return res

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Test execution timed out (300s)"}
    except Exception as exc:
        return {"ok": False, "error": f"Failed to run tests: {exc}"}


# ── Compat failure detection ────────────────────────────────────

# Common Python error patterns that indicate version incompatibility.
# These match error MESSAGES in test output — not code patterns.
_ERROR_PATTERNS = [
    (r"cannot import name '(\w+)' from '([\w.]+)'", "import_error"),
    (r"No module named '([\w.]+)'", "module_error"),
    (r"'(\w+)' object has no attribute '(\w+)'", "attribute_error"),
    (r"unsupported operand type.*for \|.*'dict'", "operator_error"),
]


def _detect_compat_failures(output: str, target: str) -> list[dict]:
    """Scan test output for Python version compat failures.

    Matches error messages against common patterns, then looks up
    the compat database for feature information and fix availability.
    """
    import re

    hints = []
    seen_features = set()

    for pattern, error_type in _ERROR_PATTERNS:
        for match in re.finditer(pattern, output):
            # Extract feature info from the error
            hint = None

            if error_type == "import_error":
                name = match.group(1)
                module = match.group(2)
                hint = {
                    "feature": f"{module}.{name}",
                    "since": "?",
                    "fix": f"'{name}' is not available in the target Python version",
                }
            elif error_type == "module_error":
                module = match.group(1)
                # Check if it's a pip package (not a stdlib version feature)
                _stdlib = {"os", "sys", "re", "json", "pathlib", "typing", "collections",
                           "functools", "itertools", "logging", "subprocess", "shutil",
                           "time", "datetime", "hashlib", "io", "abc", "dataclasses",
                           "enum", "math", "random", "string", "copy", "inspect", "ast",
                           "unittest", "argparse", "csv", "sqlite3", "xml", "html", "http",
                           "urllib", "email", "socket", "threading", "asyncio", "contextlib",
                           "traceback", "warnings", "tempfile", "glob", "struct", "pickle",
                           "platform", "importlib", "uuid", "pdb", "textwrap", "calendar"}
                if module.split(".")[0] not in _stdlib:
                    hint = {
                        "feature": module,
                        "since": "package",
                        "fix": f"Missing package — run: pip install {module}",
                    }
                else:
                    hint = {
                        "feature": module,
                        "since": "?",
                        "fix": f"Module '{module}' is not available in the target Python version",
                    }
            elif error_type == "attribute_error":
                obj_type = match.group(1)
                attr = match.group(2)
                hint = {
                    "feature": f"{obj_type}.{attr}",
                    "since": "?",
                    "fix": f"'{attr}' is not available on '{obj_type}' in the target Python version",
                }
            elif error_type == "operator_error":
                hint = {
                    "feature": "dict merge operator (|)",
                    "since": "3.9",
                    "fix": "Replace `a | b` with `{**a, **b}`",
                }

            if hint and hint["feature"] not in seen_features:
                # Try to enrich from compat database
                try:
                    from src.core.services.mediator import get_mediator
                    m = get_mediator()
                    compat_data = m.peek("compat.orchestrator")
                    if compat_data and compat_data.get("data"):
                        compat = compat_data["data"]
                        entries = compat.registry.search(hint["feature"])
                        if entries:
                            entry = entries[0]
                            hint["since"] = entry.introduced
                            hint["fix"] = entry.description or hint["fix"]
                            hint["fix_available"] = entry.fix.strategy.value != "manual"
                except Exception:
                    pass

                seen_features.add(hint["feature"])
                hints.append(hint)

    return hints
