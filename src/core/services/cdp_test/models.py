"""
CDP Test data models — TestStep, TestSuite, TestRunResult.

Pure data shapes with no I/O.  These define:
- What a test step looks like (action, selector, value, assertion)
- What a test suite is (ordered steps with metadata and variables)
- What a test run result contains (per-step pass/fail + summary)

Used by:
    storage.py   — serialization to/from JSON
    session.py   — building steps during recording
    recorder.py  — populating steps from DOM events
    replayer.py  — reading steps for execution
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


# ── Test Step ──────────────────────────────────────────────────


@dataclass
class TestStep:
    """One step in a test suite.

    Created during recording (from DOM events) or authored
    manually in the validation UI.
    """

    # ── Identity ──────────────────────────────────────────────
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sequence: int = 0                   # Order in the suite (0-indexed)

    # ── Action ────────────────────────────────────────────────
    action: str = ""                    # "navigate" | "click" | "type" |
                                        # "select" | "wait" | "assert" |
                                        # "scroll" | "hover" | "keypress" |
                                        # "screenshot"

    # ── Target ────────────────────────────────────────────────
    selector: str = ""                  # CSS selector (preferred)
    xpath: str = ""                     # XPath (fallback/alternative)
    selector_alternatives: list[str] = field(default_factory=list)
                                        # Other selectors that also match
                                        # (for resilience — if primary breaks)

    # ── Value ─────────────────────────────────────────────────
    value: str = ""                     # Text to type, URL to navigate to,
                                        # expected text for assert, etc.
    variable: str = ""                  # Variable name (e.g., "${PASSWORD}")
                                        # Resolved at execution time

    # ── Assertion ─────────────────────────────────────────────
    assertion_type: str = ""            # "text_contains" | "text_equals" |
                                        # "exists" | "not_exists" |
                                        # "attribute_equals" | "visible"
    assertion_attribute: str = ""       # For "attribute_equals"
    assertion_expected: str = ""        # Expected value

    # ── Timing ────────────────────────────────────────────────
    wait_before_ms: int = 0             # Explicit wait before this step
    timeout_ms: int = 5000              # Max time to wait for element/condition
    recorded_delay_ms: int = 0          # Actual delay from recording (for pacing)

    # ── Metadata ──────────────────────────────────────────────
    description: str = ""               # Human description
    tag: str = ""                       # User-assigned tag for grouping
    optional: bool = False              # If True, failure doesn't fail the suite

    # ── Recording context ─────────────────────────────────────
    page_url: str = ""                  # URL when step was recorded
    element_tag: str = ""               # Tag name (div, input, button, etc.)
    element_text: str = ""              # Visible text of the element
    element_rect: dict[str, float] = field(default_factory=dict)
                                        # Bounding rect {x, y, width, height}

    def to_dict(self) -> dict:
        """Serialize to a JSON-friendly dict."""
        return {
            "id": self.id,
            "sequence": self.sequence,
            "action": self.action,
            "selector": self.selector,
            "xpath": self.xpath,
            "selector_alternatives": self.selector_alternatives,
            "value": self.value,
            "variable": self.variable,
            "assertion_type": self.assertion_type,
            "assertion_attribute": self.assertion_attribute,
            "assertion_expected": self.assertion_expected,
            "wait_before_ms": self.wait_before_ms,
            "timeout_ms": self.timeout_ms,
            "recorded_delay_ms": self.recorded_delay_ms,
            "description": self.description,
            "tag": self.tag,
            "optional": self.optional,
            "page_url": self.page_url,
            "element_tag": self.element_tag,
            "element_text": self.element_text,
            "element_rect": self.element_rect,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TestStep:
        """Deserialize from a dict (tolerant of missing keys)."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            sequence=data.get("sequence", 0),
            action=data.get("action", ""),
            selector=data.get("selector", ""),
            xpath=data.get("xpath", ""),
            selector_alternatives=data.get("selector_alternatives", []),
            value=data.get("value", ""),
            variable=data.get("variable", ""),
            assertion_type=data.get("assertion_type", ""),
            assertion_attribute=data.get("assertion_attribute", ""),
            assertion_expected=data.get("assertion_expected", ""),
            wait_before_ms=data.get("wait_before_ms", 0),
            timeout_ms=data.get("timeout_ms", 5000),
            recorded_delay_ms=data.get("recorded_delay_ms", 0),
            description=data.get("description", ""),
            tag=data.get("tag", ""),
            optional=data.get("optional", False),
            page_url=data.get("page_url", ""),
            element_tag=data.get("element_tag", ""),
            element_text=data.get("element_text", ""),
            element_rect=data.get("element_rect", {}),
        )


# ── Test Suite ─────────────────────────────────────────────────


def _now_iso() -> str:
    """Current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TestSuite:
    """A complete test suite — a named, replayable sequence of steps.

    Stored as JSON in ``.state/cdp-tests/suites/`` directory.
    Can be created from recording, manual authoring, or import.
    """

    # ── Identity ──────────────────────────────────────────────
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""                      # Human name ("Login Flow")
    description: str = ""               # Longer description

    # ── Target ────────────────────────────────────────────────
    target_url: str = ""                # Base URL (http://localhost:3000)
    target_description: str = ""        # "React frontend" / "Django admin"

    # ── Steps ─────────────────────────────────────────────────
    steps: list[TestStep] = field(default_factory=list)

    # ── Variables ─────────────────────────────────────────────
    variables: dict[str, str] = field(default_factory=dict)
                                        # Name → default value
                                        # Empty string = required at runtime

    # ── Configuration ─────────────────────────────────────────
    default_timeout_ms: int = 5000      # Default per-step timeout
    navigate_wait_ms: int = 2000        # Wait after navigation
    replay_speed: float = 1.0           # Multiplier on recorded delays
    stop_on_failure: bool = True        # Stop suite on first failure
    take_screenshots: bool = False      # Capture screenshots at each step
    visual_delay_ms: int = 300          # Pause between steps for user to see
    min_step_delay_ms: int = 100        # Internal floor — let page keep up
    clear_site_data: bool = False       # Flush cookies/storage + refresh before run

    # ── Metadata ──────────────────────────────────────────────
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    created_by: str = "recording"       # "recording" | "manual" | "import"
    tags: list[str] = field(default_factory=list)
    category: str = "smoke"             # "smoke" | "regression" | "integration" | "custom"

    # ── History ───────────────────────────────────────────────
    last_run_at: str = ""               # ISO timestamp of last execution
    last_run_status: str = ""           # "passed" | "failed" | "partial"
    run_count: int = 0                  # Total number of executions

    def to_dict(self) -> dict:
        """Serialize to a JSON-friendly dict."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "target_url": self.target_url,
            "target_description": self.target_description,
            "steps": [s.to_dict() for s in self.steps],
            "variables": self.variables,
            "default_timeout_ms": self.default_timeout_ms,
            "navigate_wait_ms": self.navigate_wait_ms,
            "replay_speed": self.replay_speed,
            "stop_on_failure": self.stop_on_failure,
            "take_screenshots": self.take_screenshots,
            "visual_delay_ms": self.visual_delay_ms,
            "min_step_delay_ms": self.min_step_delay_ms,
            "clear_site_data": self.clear_site_data,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "created_by": self.created_by,
            "tags": self.tags,
            "category": self.category,
            "last_run_at": self.last_run_at,
            "last_run_status": self.last_run_status,
            "run_count": self.run_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TestSuite:
        """Deserialize from a dict (tolerant of missing keys)."""
        steps_data = data.get("steps", [])
        steps = [TestStep.from_dict(s) for s in steps_data]

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            description=data.get("description", ""),
            target_url=data.get("target_url", ""),
            target_description=data.get("target_description", ""),
            steps=steps,
            variables=data.get("variables", {}),
            default_timeout_ms=data.get("default_timeout_ms", 5000),
            navigate_wait_ms=data.get("navigate_wait_ms", 2000),
            replay_speed=data.get("replay_speed", 1.0),
            stop_on_failure=data.get("stop_on_failure", True),
            take_screenshots=data.get("take_screenshots", False),
            visual_delay_ms=data.get("visual_delay_ms", 300),
            min_step_delay_ms=data.get("min_step_delay_ms", 100),
            clear_site_data=data.get("clear_site_data", False),
            created_at=data.get("created_at", _now_iso()),
            updated_at=data.get("updated_at", _now_iso()),
            created_by=data.get("created_by", "recording"),
            tags=data.get("tags", []),
            category=data.get("category", "smoke"),
            last_run_at=data.get("last_run_at", ""),
            last_run_status=data.get("last_run_status", ""),
            run_count=data.get("run_count", 0),
        )


# ── Test Run Result ────────────────────────────────────────────


@dataclass
class TestRunResult:
    """Result of a single test suite execution."""

    # ── Identity ──────────────────────────────────────────────
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    suite_id: str = ""                  # Which suite was run
    suite_name: str = ""                # Suite name (for display)

    # ── Timing ────────────────────────────────────────────────
    started_at: str = field(default_factory=_now_iso)
    finished_at: str = ""               # Set when done
    duration_ms: int = 0                # Total execution time

    # ── Results ───────────────────────────────────────────────
    status: str = "pending"             # "pending" | "running" | "passed" |
                                        # "failed" | "cancelled" | "error"
    total_steps: int = 0
    passed_steps: int = 0
    failed_steps: int = 0
    skipped_steps: int = 0

    # ── Step Results ──────────────────────────────────────────
    step_results: list[dict] = field(default_factory=list)
    # Each: {
    #     "step_id": "...",
    #     "sequence": 0,
    #     "action": "click",
    #     "status": "passed" | "failed" | "skipped",
    #     "duration_ms": 150,
    #     "error": null | "Element not found: #login-btn",
    # }

    # ── Variables used ────────────────────────────────────────
    variables_used: dict[str, str] = field(default_factory=dict)
                                        # Resolved values (passwords redacted)

    # ── Error info ────────────────────────────────────────────
    error: str = ""                     # Global error (CDP unavailable, etc.)

    def to_dict(self) -> dict:
        """Serialize to a JSON-friendly dict."""
        return {
            "id": self.id,
            "suite_id": self.suite_id,
            "suite_name": self.suite_name,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "total_steps": self.total_steps,
            "passed_steps": self.passed_steps,
            "failed_steps": self.failed_steps,
            "skipped_steps": self.skipped_steps,
            "step_results": self.step_results,
            "variables_used": self.variables_used,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TestRunResult:
        """Deserialize from a dict."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            suite_id=data.get("suite_id", ""),
            suite_name=data.get("suite_name", ""),
            started_at=data.get("started_at", _now_iso()),
            finished_at=data.get("finished_at", ""),
            duration_ms=data.get("duration_ms", 0),
            status=data.get("status", "pending"),
            total_steps=data.get("total_steps", 0),
            passed_steps=data.get("passed_steps", 0),
            failed_steps=data.get("failed_steps", 0),
            skipped_steps=data.get("skipped_steps", 0),
            step_results=data.get("step_results", []),
            variables_used=data.get("variables_used", {}),
            error=data.get("error", ""),
        )
