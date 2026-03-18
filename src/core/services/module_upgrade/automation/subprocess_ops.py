"""
Subprocess operation handlers — run package manager commands.

Each handler supports preview (show what will run) and execute (run it).
Commands run in the module directory, not project root.

Handlers:
  - go mod tidy
  - bundle update (Ruby)
  - composer update (PHP)
  - dotnet restore (C#)
  - mix deps.get (Elixir)
  - cargo check (Rust)
  - npm install (Node.js)

All handlers check if the binary exists before running.
Execute mode uses _run_subprocess for safe, centralized execution.
"""

from __future__ import annotations

import logging
import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..context import UpgradeContext

logger = logging.getLogger(__name__)


def handle_run_go_mod_tidy(ctx: UpgradeContext, mode: str) -> dict:
    """Run `go mod tidy` in the module directory."""
    return _run_pkg_cmd(
        ctx, mode,
        binary="go",
        cmd=["go", "mod", "tidy"],
        label="go mod tidy",
        description="Clean up go.sum and verify all dependencies resolve",
    )


def handle_run_bundle_update(ctx: UpgradeContext, mode: str) -> dict:
    """Run `bundle update` in the module directory."""
    return _run_pkg_cmd(
        ctx, mode,
        binary="bundle",
        cmd=["bundle", "update"],
        label="bundle update",
        description="Update Gemfile.lock with latest compatible gem versions",
    )


def handle_run_composer_update(ctx: UpgradeContext, mode: str) -> dict:
    """Run `composer update` in the module directory."""
    return _run_pkg_cmd(
        ctx, mode,
        binary="composer",
        cmd=["composer", "update", "--no-interaction"],
        label="composer update",
        description="Update composer.lock with latest compatible package versions",
    )


def handle_run_dotnet_restore(ctx: UpgradeContext, mode: str) -> dict:
    """Run `dotnet restore` in the module directory."""
    return _run_pkg_cmd(
        ctx, mode,
        binary="dotnet",
        cmd=["dotnet", "restore"],
        label="dotnet restore",
        description="Restore NuGet packages and verify resolution",
    )


def handle_run_mix_deps_get(ctx: UpgradeContext, mode: str) -> dict:
    """Run `mix deps.get` in the module directory."""
    return _run_pkg_cmd(
        ctx, mode,
        binary="mix",
        cmd=["mix", "deps.get"],
        label="mix deps.get",
        description="Fetch and update Hex dependencies",
    )


def handle_run_cargo_check(ctx: UpgradeContext, mode: str) -> dict:
    """Run `cargo check` in the module directory."""
    return _run_pkg_cmd(
        ctx, mode,
        binary="cargo",
        cmd=["cargo", "check"],
        label="cargo check",
        description="Verify the project compiles with the current Rust toolchain",
    )


def handle_run_npm_install(ctx: UpgradeContext, mode: str) -> dict:
    """Run `npm install` in the module directory."""
    return _run_pkg_cmd(
        ctx, mode,
        binary="npm",
        cmd=["npm", "install"],
        label="npm install",
        description="Install and update node_modules from package.json",
    )


# ── Test suite runners ───────────────────────────────────────────


def handle_run_pytest(ctx: UpgradeContext, mode: str) -> dict:
    """Run `pytest` in the module directory."""
    return _run_pkg_cmd(
        ctx, mode,
        binary="pytest",
        cmd=["pytest", "--tb=short", "-q"],
        label="pytest",
        description="Run Python test suite with pytest",
    )


def handle_run_npm_test(ctx: UpgradeContext, mode: str) -> dict:
    """Run `npm test` in the module directory."""
    return _run_pkg_cmd(
        ctx, mode,
        binary="npm",
        cmd=["npm", "test"],
        label="npm test",
        description="Run Node.js test suite",
    )


def handle_run_go_test(ctx: UpgradeContext, mode: str) -> dict:
    """Run `go test ./...` in the module directory."""
    return _run_pkg_cmd(
        ctx, mode,
        binary="go",
        cmd=["go", "test", "./..."],
        label="go test ./...",
        description="Run Go test suite",
    )


def handle_run_cargo_test(ctx: UpgradeContext, mode: str) -> dict:
    """Run `cargo test` in the module directory."""
    return _run_pkg_cmd(
        ctx, mode,
        binary="cargo",
        cmd=["cargo", "test"],
        label="cargo test",
        description="Run Rust test suite",
    )


def handle_run_bundle_exec_rspec(ctx: UpgradeContext, mode: str) -> dict:
    """Run `bundle exec rspec` in the module directory."""
    return _run_pkg_cmd(
        ctx, mode,
        binary="bundle",
        cmd=["bundle", "exec", "rspec"],
        label="bundle exec rspec",
        description="Run Ruby test suite with RSpec",
    )


def handle_run_mvn_test(ctx: UpgradeContext, mode: str) -> dict:
    """Run `mvn test` in the module directory."""
    return _run_pkg_cmd(
        ctx, mode,
        binary="mvn",
        cmd=["mvn", "test", "-q"],
        label="mvn test",
        description="Run Java test suite with Maven",
    )


def handle_run_dotnet_test(ctx: UpgradeContext, mode: str) -> dict:
    """Run `dotnet test` in the module directory."""
    return _run_pkg_cmd(
        ctx, mode,
        binary="dotnet",
        cmd=["dotnet", "test"],
        label="dotnet test",
        description="Run .NET test suite",
    )


def handle_run_composer_test(ctx: UpgradeContext, mode: str) -> dict:
    """Run `composer test` in the module directory."""
    return _run_pkg_cmd(
        ctx, mode,
        binary="composer",
        cmd=["composer", "test", "--no-interaction"],
        label="composer test",
        description="Run PHP test suite via Composer script",
    )


def handle_run_mix_test(ctx: UpgradeContext, mode: str) -> dict:
    """Run `mix test` in the module directory."""
    return _run_pkg_cmd(
        ctx, mode,
        binary="mix",
        cmd=["mix", "test"],
        label="mix test",
        description="Run Elixir test suite",
    )


# ── Internal ─────────────────────────────────────────────────────


def _run_pkg_cmd(
    ctx: UpgradeContext,
    mode: str,
    *,
    binary: str,
    cmd: list[str],
    label: str,
    description: str,
) -> dict:
    """Generic package manager command runner.

    Preview: shows the command, working directory, and checks binary exists.
    Execute: runs the command via _run_subprocess, returns stdout/stderr.
    """
    module_dir = ctx.project_root / ctx.module_path
    rel_dir = str(module_dir.relative_to(ctx.project_root))

    # Check if binary exists
    binary_path = shutil.which(binary)
    if not binary_path:
        return {
            "ok": True,
            "can_apply": False,
            "preview_type": "info",
            "summary": f"`{binary}` not found on PATH",
            "detail": f"Install {binary} to use this automation.",
        }

    if not module_dir.is_dir():
        return {"ok": False, "error": f"Module directory not found: {rel_dir}"}

    if mode == "preview":
        return {
            "ok": True,
            "can_apply": True,
            "preview_type": "diff",
            "summary": f"Run `{label}` in {rel_dir}",
            "detail": description,
            "file": rel_dir,
            "old_value": f"$ cd {rel_dir}",
            "new_value": f"$ {' '.join(cmd)}",
        }

    # Execute
    try:
        from src.core.services.tool_install.execution.subprocess_runner import (
            _run_subprocess,
        )

        result = _run_subprocess(
            cmd,
            cwd=str(module_dir),
            timeout=120,
        )

        ok = result.get("ok", False)
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        elapsed = result.get("elapsed_ms", 0)

        if ok:
            output_lines = (stdout or "").strip().split("\n")
            # Show last 10 lines of output for context
            tail = output_lines[-10:] if len(output_lines) > 10 else output_lines
            return {
                "ok": True,
                "summary": f"`{label}` completed in {elapsed}ms",
                "output": "\n".join(tail),
            }
        else:
            return {
                "ok": False,
                "error": f"`{label}` failed (exit {result.get('exit_code', '?')})",
                "detail": stderr or stdout or "No output",
            }

    except Exception as exc:
        return {"ok": False, "error": f"Failed to run `{label}`: {exc}"}
