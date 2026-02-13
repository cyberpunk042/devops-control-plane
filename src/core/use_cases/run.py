"""
Run use case — execute an automation across the project.

This is the top-level orchestrator: it loads config, discovers stacks,
detects modules, plans actions, executes them, and persists results.
The full vertical slice from user intent to audited execution.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from src.adapters.registry import AdapterRegistry
from src.core.config.loader import ConfigError, find_project_file, load_project
from src.core.config.stack_loader import discover_stacks
from src.core.engine.executor import (
    ExecutionPlan,
    ExecutionReport,
    build_actions,
    execute_plan,
    generate_operation_id,
    write_audit_entries,
)
from src.core.models.project import Project
from src.core.persistence.audit import AuditWriter
from src.core.persistence.state_file import default_state_path, load_state, save_state
from src.core.services.detection import detect_modules

logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    """Result of running an automation."""

    report: ExecutionReport | None = None
    plan: ExecutionPlan | None = None
    project: Project | None = None
    project_root: Path | None = None
    modules_targeted: int = 0
    actions_planned: int = 0
    error: str | None = None

    def to_dict(self) -> dict:
        result: dict = {}
        if self.error:
            result["error"] = self.error
            return result

        result["project_name"] = self.project.name if self.project else ""
        result["project_root"] = str(self.project_root)
        result["modules_targeted"] = self.modules_targeted
        result["actions_planned"] = self.actions_planned

        if self.report:
            result["report"] = self.report.to_dict()

        return result


def run_automation(
    capability: str,
    config_path: Path | None = None,
    stacks_dir: Path | None = None,
    modules: list[str] | None = None,
    environment: str = "dev",
    dry_run: bool = False,
    mock_mode: bool = False,
    registry: AdapterRegistry | None = None,
) -> RunResult:
    """Execute an automation capability across project modules.

    Args:
        capability: Capability name to execute (e.g., 'test', 'lint', 'build').
        config_path: Optional explicit path to project.yml.
        stacks_dir: Optional override for stacks directory.
        modules: Optional list of module names to target. None = all.
        environment: Target environment name.
        dry_run: If True, plan but don't execute.
        mock_mode: If True, use mock adapter responses.
        registry: Optional pre-configured adapter registry.

    Returns:
        RunResult with execution report.
    """
    result = RunResult()

    # ── Load project config ──────────────────────────────────────
    try:
        if config_path is None:
            config_path = find_project_file()
        if config_path is None:
            result.error = "No project.yml found."
            return result

        project = load_project(config_path)
        result.project = project
        result.project_root = config_path.parent.resolve()

    except ConfigError as e:
        result.error = str(e)
        return result

    project_root = result.project_root
    assert project_root is not None

    # ── Discover stacks ──────────────────────────────────────────
    if stacks_dir is None:
        stacks_dir = project_root / "stacks"
    stacks = discover_stacks(stacks_dir)

    # ── Detect modules ───────────────────────────────────────────
    detection = detect_modules(project, project_root, stacks)
    target_modules = detection.modules

    # Filter to specific modules if requested
    if modules:
        target_modules = [m for m in target_modules if m.name in modules]

    # Only target detected modules
    target_modules = [m for m in target_modules if m.detected]
    result.modules_targeted = len(target_modules)

    # ── Build execution plan ─────────────────────────────────────
    operation_id = generate_operation_id()
    plan = build_actions(capability, target_modules, stacks, operation_id)
    result.plan = plan
    result.actions_planned = plan.total_actions

    if plan.total_actions == 0:
        result.error = f"No actions to execute: capability '{capability}' not found in any targeted module's stack."
        return result

    # ── Set up adapter registry ──────────────────────────────────
    if registry is None:
        from src.adapters.shell.command import ShellCommandAdapter
        from src.adapters.shell.filesystem import FilesystemAdapter
        from src.adapters.vcs.git import GitAdapter
        from src.adapters.containers.docker import DockerAdapter
        from src.adapters.languages.python import PythonAdapter
        from src.adapters.languages.node import NodeAdapter

        registry = AdapterRegistry(mock_mode=mock_mode)
        registry.register(ShellCommandAdapter())
        registry.register(FilesystemAdapter())
        registry.register(GitAdapter())
        registry.register(DockerAdapter())
        registry.register(PythonAdapter())
        registry.register(NodeAdapter())

    # ── Execute ──────────────────────────────────────────────────
    report = execute_plan(
        plan=plan,
        registry=registry,
        project_root=str(project_root),
        environment=environment,
        dry_run=dry_run,
    )
    result.report = report

    # ── Persist state ────────────────────────────────────────────
    state_path = default_state_path(project_root)
    state = load_state(state_path)
    state.project_name = project.name
    state.last_operation.operation_id = operation_id
    state.last_operation.automation = capability
    state.last_operation.status = report.status
    state.last_operation.actions_total = report.total
    state.last_operation.actions_succeeded = report.succeeded
    state.last_operation.actions_failed = report.failed

    for module_name, receipts in report.module_receipts.items():
        last = receipts[-1]
        state.set_module_state(
            module_name,
            last_action_at=last.started_at,
            last_action_status=last.status,
        )

    save_state(state, state_path)

    # ── Write audit log ──────────────────────────────────────────
    audit_path = project_root / ".state" / "audit.ndjson"
    audit_writer = AuditWriter(audit_path)
    write_audit_entries(report, audit_writer)

    return result
