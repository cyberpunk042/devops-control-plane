"""
Execution Plan data models — ExecutionPlan, PlanStep, BrowserConfig,
PlanRunResult, StepResult.

Pure data shapes with no I/O.  These define:
- What a plan step looks like (script, cdp_test, checkpoint, conditional)
- What a plan is (ordered steps with browser config and variables)
- What a plan run result contains (per-step status + accumulated variables)

Used by:
    plan_storage.py     — serialization to/from JSON
    plan_executor.py    — reading plans for execution
    routes/plans/       — API serialization
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ── Helpers ────────────────────────────────────────────────────


def _now_iso() -> str:
    """Current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


# ── Browser Config ─────────────────────────────────────────────


@dataclass
class BrowserConfig:
    """How Chrome is managed for a plan's browser-dependent steps.

    Modes:
        ``"separate_instance"``  — Launch a fresh Chrome instance (DEFAULT).
                                   Isolated, reproducible, auto-killed on finish.
        ``"same_browser"``       — Use the existing CDP browser (the one
                                   running the admin panel).
        ``"none"``               — No browser needed (script-only plans).
    """

    mode: str = "separate_instance"     # separate_instance | same_browser | none

    # For separate_instance:
    headless: bool = False
    port: int = 0                       # 0 = auto-allocate
    keep_alive: bool = False            # DEFAULT: kill browser when plan finishes

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "headless": self.headless,
            "port": self.port,
            "keep_alive": self.keep_alive,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BrowserConfig:
        return cls(
            mode=data.get("mode", "separate_instance"),
            headless=data.get("headless", False),
            port=data.get("port", 0),
            keep_alive=data.get("keep_alive", False),
        )


# ── Plan Step ──────────────────────────────────────────────────


@dataclass
class PlanStep:
    """One step in an execution plan.

    Step types:
        ``"script"``       — Run a registered script via M1 executor.
        ``"cdp_test"``     — Replay a CDP test suite.
        ``"checkpoint"``   — Pause for user review (semi_automated/interactive).
        ``"conditional"``  — Branch based on a previous step's result.
    """

    # ── Identity ──────────────────────────────────────────────
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sequence: int = 0
    type: str = ""                      # script | cdp_test | checkpoint | conditional
    name: str = ""                      # Human label ("Run Docker audit")

    # ── For type="script" ─────────────────────────────────────
    script_id: str = ""                 # From M1 registry (e.g. "audit-docker")
    script_params: dict[str, str] = field(default_factory=dict)

    # ── For type="cdp_test" ───────────────────────────────────
    suite_id: str = ""                  # CDP test suite UUID
    suite_variables: dict[str, str] = field(default_factory=dict)

    # ── For type="checkpoint" ─────────────────────────────────
    checkpoint_message: str = ""        # Message shown to user at pause

    # ── For type="conditional" ────────────────────────────────
    condition_step_id: str = ""         # Which step's result to check
    condition: str = "passed"           # "passed" | "failed"
    then_step_id: str = ""              # Step to jump to if condition met
    else_step_id: str = ""              # Step to jump to otherwise (or skip)

    # ── Common ────────────────────────────────────────────────
    optional: bool = False              # If True, failure doesn't fail the plan
    timeout_seconds: int = 0            # 0 = use default from executor

    # ── Variable chaining ─────────────────────────────────────
    produces: list[str] = field(default_factory=list)
    """Variable names this step is expected to output."""

    consumes: list[str] = field(default_factory=list)
    """Variable names this step needs from the shared namespace."""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "sequence": self.sequence,
            "type": self.type,
            "name": self.name,
            "script_id": self.script_id,
            "script_params": self.script_params,
            "suite_id": self.suite_id,
            "suite_variables": self.suite_variables,
            "checkpoint_message": self.checkpoint_message,
            "condition_step_id": self.condition_step_id,
            "condition": self.condition,
            "then_step_id": self.then_step_id,
            "else_step_id": self.else_step_id,
            "optional": self.optional,
            "timeout_seconds": self.timeout_seconds,
            "produces": self.produces,
            "consumes": self.consumes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PlanStep:
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            sequence=data.get("sequence", 0),
            type=data.get("type", ""),
            name=data.get("name", ""),
            script_id=data.get("script_id", ""),
            script_params=data.get("script_params", {}),
            suite_id=data.get("suite_id", ""),
            suite_variables=data.get("suite_variables", {}),
            checkpoint_message=data.get("checkpoint_message", ""),
            condition_step_id=data.get("condition_step_id", ""),
            condition=data.get("condition", "passed"),
            then_step_id=data.get("then_step_id", ""),
            else_step_id=data.get("else_step_id", ""),
            optional=data.get("optional", False),
            timeout_seconds=data.get("timeout_seconds", 0),
            produces=data.get("produces", []),
            consumes=data.get("consumes", []),
        )


# ── Execution Plan ─────────────────────────────────────────────


@dataclass
class ExecutionPlan:
    """A named, executable chain of steps with shared variable namespace.

    Plans are stored as JSON in ``.state/cdp-plans/plans/`` directory.

    Execution modes:
        ``"fully_automated"``  — Run all steps, no pauses.
        ``"semi_automated"``   — Pause at checkpoint steps.
        ``"interactive"``      — Pause after every step.
    """

    # ── Identity ──────────────────────────────────────────────
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""

    # ── Steps ─────────────────────────────────────────────────
    steps: list[PlanStep] = field(default_factory=list)

    # ── Configuration ─────────────────────────────────────────
    mode: str = "fully_automated"       # fully_automated | semi_automated | interactive
    browser_config: BrowserConfig | None = None

    # ── Variables ─────────────────────────────────────────────
    variables: dict[str, Any] = field(default_factory=dict)
    """Initial/default variable values. These seed the shared namespace.
    Values are usually strings but may be JSON objects (dict, list) for
    variables produced by DCP_JSON_ convention."""

    # ── Metadata ──────────────────────────────────────────────
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    # ── History ───────────────────────────────────────────────
    last_run_at: str = ""
    last_run_status: str = ""           # passed | failed | partial | cancelled
    run_count: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "mode": self.mode,
            "browser_config": self.browser_config.to_dict()
                if self.browser_config else None,
            "variables": self.variables,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_run_at": self.last_run_at,
            "last_run_status": self.last_run_status,
            "run_count": self.run_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ExecutionPlan:
        bc_data = data.get("browser_config")
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            description=data.get("description", ""),
            steps=[
                PlanStep.from_dict(s)
                for s in data.get("steps", [])
            ],
            mode=data.get("mode", "fully_automated"),
            browser_config=BrowserConfig.from_dict(bc_data)
                if bc_data else None,
            variables=data.get("variables", {}),
            created_at=data.get("created_at", _now_iso()),
            updated_at=data.get("updated_at", _now_iso()),
            last_run_at=data.get("last_run_at", ""),
            last_run_status=data.get("last_run_status", ""),
            run_count=data.get("run_count", 0),
        )


# ── Step Result ────────────────────────────────────────────────


@dataclass
class StepResult:
    """Result of one step within a plan run."""

    # ── Identity ──────────────────────────────────────────────
    step_id: str = ""
    step_name: str = ""
    step_type: str = ""                 # script | cdp_test | checkpoint | conditional
    sequence: int = 0

    # ── Status ────────────────────────────────────────────────
    status: str = "pending"             # pending | running | passed | failed | skipped | cancelled
    started_at: str = ""
    finished_at: str = ""
    duration_ms: int = 0
    error: str = ""

    # ── Script step outputs ───────────────────────────────────
    script_run_id: str = ""
    script_stream_id: str = ""
    script_exit_code: int = 0
    script_lines: list[str] = field(default_factory=list)

    # ── CDP test step outputs ─────────────────────────────────
    replay_run_id: str = ""
    replay_passed: int = 0
    replay_failed: int = 0
    replay_total: int = 0
    replay_step_results: list[dict] = field(default_factory=list)

    # ── Variables produced ────────────────────────────────────
    variables_produced: dict[str, Any] = field(default_factory=dict)

    # ── Variables consumed (input) ────────────────────────────
    variables_consumed: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "step_name": self.step_name,
            "step_type": self.step_type,
            "sequence": self.sequence,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "script_run_id": self.script_run_id,
            "script_stream_id": self.script_stream_id,
            "script_exit_code": self.script_exit_code,
            "script_lines": self.script_lines,
            "replay_run_id": self.replay_run_id,
            "replay_passed": self.replay_passed,
            "replay_failed": self.replay_failed,
            "replay_total": self.replay_total,
            "replay_step_results": self.replay_step_results,
            "variables_produced": self.variables_produced,
            "variables_consumed": self.variables_consumed,
        }

    @classmethod
    def from_dict(cls, data: dict) -> StepResult:
        return cls(
            step_id=data.get("step_id", ""),
            step_name=data.get("step_name", ""),
            step_type=data.get("step_type", ""),
            sequence=data.get("sequence", 0),
            status=data.get("status", "pending"),
            started_at=data.get("started_at", ""),
            finished_at=data.get("finished_at", ""),
            duration_ms=data.get("duration_ms", 0),
            error=data.get("error", ""),
            script_run_id=data.get("script_run_id", ""),
            script_stream_id=data.get("script_stream_id", ""),
            script_exit_code=data.get("script_exit_code", 0),
            script_lines=data.get("script_lines", []),
            replay_run_id=data.get("replay_run_id", ""),
            replay_passed=data.get("replay_passed", 0),
            replay_failed=data.get("replay_failed", 0),
            replay_total=data.get("replay_total", 0),
            replay_step_results=data.get("replay_step_results", []),
            variables_produced=data.get("variables_produced", {}),
            variables_consumed=data.get("variables_consumed", {}),
        )


# ── Plan Run Result ────────────────────────────────────────────


@dataclass
class PlanRunResult:
    """Result of a full plan execution."""

    # ── Identity ──────────────────────────────────────────────
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    plan_id: str = ""
    plan_name: str = ""

    # ── Configuration used ────────────────────────────────────
    mode: str = ""                      # Execution mode used

    # ── Timing ────────────────────────────────────────────────
    started_at: str = field(default_factory=_now_iso)
    finished_at: str = ""
    duration_ms: int = 0

    # ── Results ───────────────────────────────────────────────
    status: str = "running"             # running | passed | failed | partial | cancelled
    total_steps: int = 0
    passed_steps: int = 0
    failed_steps: int = 0
    skipped_steps: int = 0

    # ── Step-level results ────────────────────────────────────
    step_results: list[StepResult] = field(default_factory=list)

    # ── Variables ─────────────────────────────────────────────
    variables: dict[str, Any] = field(default_factory=dict)
    """Final accumulated variable namespace after all steps.
    Values are usually strings but may include JSON objects."""

    # ── Browser info ──────────────────────────────────────────
    chrome_instance: dict | None = None  # port, pid, endpoint if separate

    # ── Error info ────────────────────────────────────────────
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "plan_id": self.plan_id,
            "plan_name": self.plan_name,
            "mode": self.mode,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "total_steps": self.total_steps,
            "passed_steps": self.passed_steps,
            "failed_steps": self.failed_steps,
            "skipped_steps": self.skipped_steps,
            "step_results": [sr.to_dict() for sr in self.step_results],
            "variables": self.variables,
            "chrome_instance": self.chrome_instance,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PlanRunResult:
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            plan_id=data.get("plan_id", ""),
            plan_name=data.get("plan_name", ""),
            mode=data.get("mode", ""),
            started_at=data.get("started_at", _now_iso()),
            finished_at=data.get("finished_at", ""),
            duration_ms=data.get("duration_ms", 0),
            status=data.get("status", "running"),
            total_steps=data.get("total_steps", 0),
            passed_steps=data.get("passed_steps", 0),
            failed_steps=data.get("failed_steps", 0),
            skipped_steps=data.get("skipped_steps", 0),
            step_results=[
                StepResult.from_dict(sr)
                for sr in data.get("step_results", [])
            ],
            variables=data.get("variables", {}),
            chrome_instance=data.get("chrome_instance"),
            error=data.get("error", ""),
        )
