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
            "preview_type": "diff",
            "summary": f"Run pytest on Python {target}",
            "file": str(tests_dir.relative_to(ctx.project_root)),
            "old_value": f"$ cd {ctx.module_path}",
            "new_value": f"$ {venv_python} -m pytest tests/ -v",
        }

    # Execute
    if not venv_python.is_file():
        return {"ok": False, "error": f"Venv not found at {venv_dir}. Set up test environment first."}

    test_target = str(tests_dir) if tests_dir.is_dir() else str(module_dir)

    try:
        result = subprocess.run(
            [str(venv_python), "-m", "pytest", test_target, "-v", "--tb=short"],
            capture_output=True, text=True, timeout=300,
            cwd=str(ctx.project_root),
        )

        stdout = result.stdout or ""
        stderr = result.stderr or ""
        output = stdout + stderr

        # Parse pytest summary
        import re
        summary_match = re.search(
            r"(\d+) passed(?:.*?(\d+) failed)?(?:.*?(\d+) error)?(?:.*?(\d+) skipped)?",
            output,
        )
        passed = int(summary_match.group(1)) if summary_match else 0
        failed = int(summary_match.group(2) or 0) if summary_match else 0
        errors = int(summary_match.group(3) or 0) if summary_match else 0
        skipped = int(summary_match.group(4) or 0) if summary_match else 0

        # Show last 30 lines
        output_lines = output.strip().split("\n")
        tail = "\n".join(output_lines[-30:]) if len(output_lines) > 30 else output

        ok = result.returncode == 0 or result.returncode == 5  # 5 = no tests collected

        return {
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

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Test execution timed out (300s)"}
    except Exception as exc:
        return {"ok": False, "error": f"Failed to run tests: {exc}"}
