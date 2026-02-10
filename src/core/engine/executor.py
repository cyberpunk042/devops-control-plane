"""
Engine executor — the central orchestration loop.

The engine is the heartbeat of the control plane. It takes an
automation request, resolves targets, builds actions from stack
capabilities, executes them through the adapter registry, collects
receipts, and persists everything.

Flow:
    request → resolve modules → build actions → execute → collect receipts → persist
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.adapters.registry import AdapterRegistry
from src.core.models.action import Action, Receipt
from src.core.models.module import Module
from src.core.models.stack import Stack
from src.core.persistence.audit import AuditEntry, AuditWriter

logger = logging.getLogger(__name__)


@dataclass
class ExecutionPlan:
    """A planned set of actions to execute."""

    operation_id: str = ""
    automation: str = ""
    actions: list[Action] = field(default_factory=list)
    module_actions: dict[str, list[Action]] = field(default_factory=dict)

    @property
    def total_actions(self) -> int:
        return len(self.actions)


@dataclass
class ExecutionReport:
    """Result of executing a plan."""

    operation_id: str = ""
    automation: str = ""
    receipts: list[Receipt] = field(default_factory=list)
    module_receipts: dict[str, list[Receipt]] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.receipts)

    @property
    def succeeded(self) -> int:
        return sum(1 for r in self.receipts if r.ok)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.receipts if r.failed)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.receipts if r.status == "skipped")

    @property
    def all_ok(self) -> bool:
        return self.failed == 0

    @property
    def status(self) -> str:
        if self.failed == 0:
            return "ok"
        if self.succeeded > 0:
            return "partial"
        return "failed"

    def to_dict(self) -> dict:
        return {
            "operation_id": self.operation_id,
            "automation": self.automation,
            "status": self.status,
            "total": self.total,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "skipped": self.skipped,
            "receipts": [r.model_dump(mode="json") for r in self.receipts],
        }


def _resolve_stack(name: str, stacks: dict[str, Stack]) -> Stack | None:
    """Resolve a stack name, with fallback to base name.

    Tries exact match first, then strips the suffix after the last
    hyphen. E.g., 'python-lib' → 'python'.

    This allows users to declare fine-grained stack variants
    (python-lib, python-fastapi) while reusing coarse stack definitions.
    """
    # Exact match
    if name in stacks:
        return stacks[name]

    # Try base name (strip after last hyphen)
    if "-" in name:
        base = name.rsplit("-", 1)[0]
        if base in stacks:
            return stacks[base]

    return None


def build_actions(
    capability_name: str,
    modules: list[Module],
    stacks: dict[str, Stack],
    operation_id: str,
) -> ExecutionPlan:
    """Build an execution plan from a capability name and target modules.

    For each module, looks up its effective stack, finds the named
    capability, and creates an Action.

    Args:
        capability_name: The capability to execute (e.g., 'test', 'lint').
        modules: Target modules.
        stacks: Available stack definitions.
        operation_id: Unique operation identifier.

    Returns:
        ExecutionPlan with actions ready to execute.
    """
    plan = ExecutionPlan(
        operation_id=operation_id,
        automation=capability_name,
    )

    for module in modules:
        stack_name = module.effective_stack
        if not stack_name:
            logger.debug("Module '%s' has no stack, skipping", module.name)
            continue

        stack = _resolve_stack(stack_name, stacks)
        if stack is None:
            logger.debug("Stack '%s' not found for module '%s'", stack_name, module.name)
            continue

        capability = stack.get_capability(capability_name)
        if capability is None:
            logger.debug(
                "Stack '%s' has no capability '%s'", stack_name, capability_name
            )
            continue

        action = Action(
            id=f"{operation_id}:{module.name}:{capability_name}",
            adapter=capability.adapter or "shell",
            capability=capability_name,
            for_module=module.name,
            params={
                "command": capability.command,
                "capability": capability_name,
                "_stack": stack_name,
                "_module_path": module.path,
                "_description": capability.description,
            },
        )
        plan.actions.append(action)
        plan.module_actions.setdefault(module.name, []).append(action)

    return plan


def execute_plan(
    plan: ExecutionPlan,
    registry: AdapterRegistry,
    project_root: str = ".",
    environment: str = "dev",
    dry_run: bool = False,
) -> ExecutionReport:
    """Execute all actions in a plan through the adapter registry.

    Args:
        plan: The execution plan.
        registry: Adapter registry for dispatch.
        project_root: Project root directory.
        environment: Target environment.
        dry_run: If True, validate but don't execute.

    Returns:
        ExecutionReport with all receipts.
    """
    report = ExecutionReport(
        operation_id=plan.operation_id,
        automation=plan.automation,
    )

    for action in plan.actions:
        module_path = action.params.get("_module_path")

        receipt = registry.execute_action(
            action=action,
            project_root=project_root,
            environment=environment,
            module_path=module_path,
            dry_run=dry_run,
        )

        report.receipts.append(receipt)
        module_name = action.for_module or "unknown"
        report.module_receipts.setdefault(module_name, []).append(receipt)

        # Log result
        status_marker = "✓" if receipt.ok else "✗" if receipt.failed else "⊘"
        logger.info(
            "%s %s:%s → %s",
            status_marker,
            module_name,
            plan.automation,
            receipt.status,
        )

    return report


def write_audit_entries(
    report: ExecutionReport,
    audit_writer: AuditWriter,
) -> None:
    """Write execution results to the audit ledger.

    Args:
        report: Execution report to audit.
        audit_writer: The audit writer instance.
    """
    entry = AuditEntry(
        operation_id=report.operation_id,
        operation_type=report.automation,
        automation=report.automation,
        status=report.status,
        actions_total=report.total,
        actions_succeeded=report.succeeded,
        actions_failed=report.failed,
        modules_affected=list(report.module_receipts.keys()),
    )
    audit_writer.write(entry)


def generate_operation_id() -> str:
    """Generate a unique operation ID."""
    now = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    short = uuid.uuid4().hex[:6]
    return f"op-{now}-{short}"
