"""
DevOps Control Plane — CLI entrypoint.

Usage:
    python -m src.main --help
    python -m src.main status
    python -m src.main config check
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import click

from src.core.observability.logging_config import setup_logging

from src import __version__


@click.group()
@click.version_option(version=__version__, prog_name="controlplane")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output.")
@click.option("--quiet", "-q", is_flag=True, help="Suppress non-essential output.")
@click.option("--debug", is_flag=True, help="Enable debug logging (very verbose).")
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=False),
    default=None,
    help="Path to project.yml (default: auto-detect).",
)
@click.pass_context
def cli(
    ctx: click.Context,
    verbose: bool,
    quiet: bool,
    debug: bool,
    config_path: str | None,
) -> None:
    """DevOps Control Plane — manage your project infrastructure."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet
    ctx.obj["debug"] = debug
    ctx.obj["config_path"] = Path(config_path) if config_path else None

    # Register project root in core context (used by all core services for audit)
    from src.core.config.loader import find_project_file
    from src.core.context import set_project_root as _set_ctx_root
    _cfg = ctx.obj["config_path"] or find_project_file()
    _set_ctx_root(_cfg.parent.resolve() if _cfg else Path.cwd())

    # ── Logging setup (once, at process start) ──────────────────
    if debug:
        level = "DEBUG"
    elif verbose:
        level = "INFO"
    elif quiet:
        level = "ERROR"
    else:
        level = os.environ.get("DCP_LOG_LEVEL", "WARNING")

    setup_logging(
        level=level,
        log_file=os.environ.get("DCP_LOG_FILE"),
        log_file_level=os.environ.get("DCP_LOG_FILE_LEVEL"),
        quiet_third_party=not debug,
    )


@cli.command()
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.option("--env", "environment", default=None, help="Target environment.")
@click.pass_context
def status(ctx: click.Context, as_json: bool, environment: str | None) -> None:
    """Show project status summary."""
    from src.core.use_cases.status import get_status

    result = get_status(config_path=ctx.obj.get("config_path"))

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
        return

    if result.error:
        click.secho(f"❌ {result.error}", fg="red")
        sys.exit(1)

    project = result.project
    assert project is not None  # guaranteed after error check above
    quiet = ctx.obj.get("quiet", False)

    if not quiet:
        click.secho(f"\n📋 {project.name}", fg="cyan", bold=True)
        if project.description:
            click.echo(f"   {project.description}")
        if project.repository:
            click.echo(f"   📦 {project.repository}")
        click.echo()

    # Modules
    click.secho(f"   Modules: {result.module_count}", fg="white", bold=True)
    for mod in project.modules:
        stack_label = f" [{mod.stack}]" if mod.stack else ""
        domain_label = f" ({mod.domain})" if mod.domain != "service" else ""
        # Check if detected
        state_marker = ""
        if result.state and mod.name in result.state.modules:
            ms = result.state.modules[mod.name]
            if ms.detected:
                state_marker = " ✓"
        click.echo(f"     • {mod.name}{stack_label}{domain_label}{state_marker}  → {mod.path}")

    # Environments
    if project.environments:
        click.echo()
        click.secho(f"   Environments: {result.environment_count}", fg="white", bold=True)
        for env in project.environments:
            marker = " ← active" if env.name == result.current_environment else ""
            default = " (default)" if env.default else ""
            click.echo(f"     • {env.name}{default}{marker}")

    # Last operation
    if result.state and result.state.last_operation.operation_id:
        op = result.state.last_operation
        click.echo()
        click.secho("   Last operation:", fg="white", bold=True)
        status_color = {"ok": "green", "partial": "yellow", "failed": "red"}.get(
            op.status, "white"
        )
        click.echo(f"     {op.automation} — ", nl=False)
        click.secho(op.status, fg=status_color)
        if op.ended_at:
            click.echo(f"     at {op.ended_at}")

    click.echo()


@cli.group()
def config() -> None:
    """Project configuration commands."""


@config.command("check")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def config_check(ctx: click.Context, as_json: bool) -> None:
    """Validate project.yml configuration."""
    from src.core.use_cases.config_check import check_config

    result = check_config(config_path=ctx.obj.get("config_path"))

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
        sys.exit(0 if result.valid else 1)
        return

    if result.valid:
        assert result.project is not None  # guaranteed when valid
        click.secho("✅ Configuration is valid", fg="green", bold=True)
        click.echo(f"   Project: {result.project.name}")
        click.echo(f"   Modules: {len(result.project.modules)}")
        click.echo(f"   Environments: {len(result.project.environments)}")
    else:
        click.secho("❌ Configuration errors:", fg="red", bold=True)
        for err in result.errors:
            click.echo(f"   • {err}")

    if result.warnings:
        click.echo()
        click.secho("⚠️  Warnings:", fg="yellow")
        for warn in result.warnings:
            click.echo(f"   • {warn}")

    if not result.valid:
        click.echo()
        sys.exit(1)

    click.echo()


@cli.command()
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.option("--no-save", is_flag=True, help="Don't save detection results to state.")
@click.pass_context
def detect(ctx: click.Context, as_json: bool, no_save: bool) -> None:
    """Detect modules and match stacks in the project."""
    from src.core.use_cases.detect import run_detect

    result = run_detect(
        config_path=ctx.obj.get("config_path"),
        save=not no_save,
    )

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
        return

    if result.error:
        click.secho(f"❌ {result.error}", fg="red")
        sys.exit(1)

    detection = result.detection
    assert detection is not None
    assert result.project is not None

    click.secho(f"\n🔍 Detection: {result.project.name}", fg="cyan", bold=True)
    click.echo(f"   Stacks loaded: {result.stacks_loaded}")
    click.echo(
        f"   Modules: {detection.total_detected}/{detection.total_modules} detected"
    )
    click.echo()

    for module in detection.modules:
        if module.detected:
            stack_label = f"[{module.effective_stack}]" if module.effective_stack else "[?]"
            version_label = f" v{module.version}" if module.version else ""
            lang_label = f" ({module.language})" if module.language else ""
            click.secho(f"   ✓ {module.name} ", fg="green", nl=False)
            click.echo(f"{stack_label}{version_label}{lang_label}  → {module.path}")
        else:
            click.secho(f"   ✗ {module.name} ", fg="red", nl=False)
            click.echo(f"(not found)  → {module.path}")

    if detection.unmatched_refs:
        click.echo()
        click.secho("   ⚠️  Missing module paths:", fg="yellow")
        for name in detection.unmatched_refs:
            click.echo(f"     • {name}")

    if result.state_saved:
        click.echo()
        click.secho("   💾 State saved to .state/current.json", fg="cyan")

    click.echo()


@cli.command()
@click.argument("capability")
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.option("--module", "-m", "modules", multiple=True, help="Target specific modules.")
@click.option("--env", "environment", default="dev", help="Target environment.")
@click.option("--dry-run", is_flag=True, help="Plan but don't execute.")
@click.option("--mock", is_flag=True, help="Use mock adapter (no real execution).")
@click.pass_context
def run(
    ctx: click.Context,
    capability: str,
    as_json: bool,
    modules: tuple[str, ...],
    environment: str,
    dry_run: bool,
    mock: bool,
) -> None:
    """Run a capability across project modules.

    Examples:

        controlplane run test

        controlplane run lint --module api --module web

        controlplane run build --dry-run
    """
    from src.core.use_cases.run import run_automation

    result = run_automation(
        capability=capability,
        config_path=ctx.obj.get("config_path"),
        modules=list(modules) if modules else None,
        environment=environment,
        dry_run=dry_run,
        mock_mode=mock,
    )

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
        if result.report and result.report.failed > 0:
            sys.exit(1)
        return

    if result.error:
        click.secho(f"❌ {result.error}", fg="red")
        sys.exit(1)

    report = result.report
    assert report is not None
    assert result.project is not None

    mode_label = "[dry-run] " if dry_run else "[mock] " if mock else ""
    click.secho(
        f"\n⚡ {mode_label}{capability} — {result.project.name}",
        fg="cyan",
        bold=True,
    )
    click.echo(
        f"   Modules: {result.modules_targeted} | "
        f"Actions: {report.total}"
    )
    click.echo()

    # Per-module results
    for module_name, receipts in report.module_receipts.items():
        for receipt in receipts:
            if receipt.ok:
                click.secho(f"   ✓ {module_name}", fg="green", nl=False)
                timing = f" ({receipt.duration_ms}ms)" if receipt.duration_ms else ""
                click.echo(f"{timing}")
                if ctx.obj.get("verbose") and receipt.output:
                    for line in receipt.output.split("\n")[:10]:
                        click.echo(f"     │ {line}")
            elif receipt.failed:
                click.secho(f"   ✗ {module_name}", fg="red", nl=False)
                timing = f" ({receipt.duration_ms}ms)" if receipt.duration_ms else ""
                click.echo(f"{timing}")
                if receipt.error:
                    for line in receipt.error.split("\n")[:5]:
                        click.echo(f"     │ {line}")
            else:
                click.secho(f"   ⊘ {module_name} ", fg="yellow", nl=False)
                click.echo(f"({receipt.output})")

    # Summary
    click.echo()
    status_color = {"ok": "green", "partial": "yellow", "failed": "red"}.get(
        report.status, "white"
    )
    click.secho(
        f"   Result: {report.succeeded}/{report.total} succeeded",
        fg=status_color,
        bold=True,
    )

    if report.failed > 0:
        click.echo()
        sys.exit(1)

    click.echo()



@cli.command()
@click.option("--json-output", "--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def health(ctx: click.Context, as_json: bool) -> None:
    "Show system health — circuit breakers, retry queue, components."
    from src.core.observability.health import check_system_health
    from src.core.reliability.circuit_breaker import CircuitBreakerRegistry
    from src.core.reliability.retry_queue import RetryQueue

    config_path: Path | None = ctx.obj.get("config_path")
    if config_path is None:
        from src.core.config.loader import find_project_file

        config_path = find_project_file()

    project_root = config_path.parent.resolve() if config_path else Path.cwd()

    # Initialize components
    cb_registry = CircuitBreakerRegistry()
    retry_path = project_root / ".state" / "retry_queue.json"
    retry_q = RetryQueue(path=retry_path)

    system_health = check_system_health(
        cb_registry=cb_registry,
        retry_queue=retry_q,
    )

    if as_json:
        click.echo(json.dumps(system_health.to_dict(), indent=2))
        return

    # Pretty output
    status_icons = {
        "healthy": ("💚", "green"),
        "degraded": ("🟡", "yellow"),
        "unhealthy": ("🔴", "red"),
        "unknown": ("❔", "white"),
    }
    icon, color = status_icons.get(system_health.status, ("❔", "white"))

    click.echo()
    click.secho(f"{icon} System Health: {system_health.status.upper()}", fg=color, bold=True)
    click.echo(f"   {system_health.timestamp}")
    click.echo()

    for component in system_health.components:
        c_icon, c_color = status_icons.get(component.status, ("❔", "white"))
        click.secho(f"   {c_icon} {component.name}", fg=c_color, bold=True)
        click.echo(f"      {component.message}")

        if ctx.obj.get("verbose") and component.details:
            for key, val in component.details.items():
                if key == "items":
                    continue
                click.echo(f"      {key}: {val}")

    click.echo()



@cli.command()
@click.option("--host", default="127.0.0.1", help="Bind address.")
@click.option("--port", "-p", default=8000, type=int, help="Port number.")
@click.option("--mock", is_flag=True, help="Use mock adapter (no real execution).")
@click.pass_context
def web(ctx: click.Context, host: str, port: int, mock: bool) -> None:
    "Start the web admin dashboard."
    from src.ui.web.server import create_app, run_server

    config_path: Path | None = ctx.obj.get("config_path")
    if config_path is None:
        from src.core.config.loader import find_project_file

        config_path = find_project_file()

    project_root = config_path.parent.resolve() if config_path else Path.cwd()

    app = create_app(
        project_root=project_root,
        config_path=config_path,
        mock_mode=mock,
    )

    debug = ctx.obj.get("debug", False)

    click.echo()
    click.secho("⚡ DevOps Control Plane — Web Admin", bold=True)
    click.echo(f"   Dashboard: http://{host}:{port}")
    click.echo(f"   Project:   {project_root}")
    if mock:
        click.secho("   Mode: mock (no real execution)", fg="yellow")
    if debug:
        click.secho("   Logging: DEBUG (all output)", fg="yellow")
    click.echo()

    run_server(app, host=host, port=port, debug=debug)


# ── Register sub-command groups from src/ui/cli/ ──────────────────

from src.ui.cli.vault import vault
from src.ui.cli.content import content
from src.ui.cli.pages import pages
from src.ui.cli.git import git
from src.ui.cli.backup import backup
from src.ui.cli.secrets import secrets
from src.ui.cli.docker import docker
from src.ui.cli.ci import ci
from src.ui.cli.packages import packages
from src.ui.cli.infra import infra
from src.ui.cli.quality import quality
from src.ui.cli.metrics import metrics
from src.ui.cli.security import security
from src.ui.cli.docs import docs
from src.ui.cli.testing import testing
from src.ui.cli.k8s import k8s
from src.ui.cli.terraform import terraform
from src.ui.cli.dns import dns

cli.add_command(vault)
cli.add_command(content)
cli.add_command(pages)
cli.add_command(git)
cli.add_command(backup)
cli.add_command(secrets)
cli.add_command(docker)
cli.add_command(ci)
cli.add_command(packages)
cli.add_command(infra)
cli.add_command(quality)
cli.add_command(metrics)
cli.add_command(security)
cli.add_command(docs)
cli.add_command(testing)
cli.add_command(k8s)
cli.add_command(terraform)
cli.add_command(dns)


if __name__ == "__main__":
    cli()
