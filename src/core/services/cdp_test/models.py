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


# ── Branch ─────────────────────────────────────────────────────


@dataclass
class Branch:
    """One branch option when an assertion fails.

    Branches are presented to the user (interactive mode) or auto-selected
    (automated mode) when an assertion's ``on_fail`` mode is ``"branch"``.

    If ``action`` is ``"cancel"``, the branch aborts the run — no steps.
    Otherwise, ``first_step_id`` points to the head of the branch's step
    sequence.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    label: str = ""                     # "Diagnose", "Fallback", custom
    icon: str = ""                      # "🔍", "🔄", "⛔", custom
    first_step_id: str = ""             # Head of the branch step sequence
    action: str = ""                    # "cancel" for abort-only branches,
                                        # "" for normal step-based branches

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "icon": self.icon,
            "first_step_id": self.first_step_id,
            "action": self.action,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Branch:
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            label=data.get("label", ""),
            icon=data.get("icon", ""),
            first_step_id=data.get("first_step_id", ""),
            action=data.get("action", ""),
        )


# ── Failure Route ──────────────────────────────────────────────


@dataclass
class FailureRoute:
    """What happens when an assertion fails.

    Modes:
        ``"fail"``     — Hard stop. Mark the run as failed immediately.
        ``"continue"`` — Mark the assertion step as failed, but continue
                         to the next step (soft fail).
        ``"branch"``   — Present branch options. In automated mode, the
                         first non-cancel branch is taken. In interactive
                         mode, the user chooses.
    """

    mode: str = "fail"                  # "fail" | "continue" | "branch"
    branches: list[Branch] = field(default_factory=list)
                                        # Only used when mode == "branch"

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "branches": [b.to_dict() for b in self.branches],
        }

    @classmethod
    def from_dict(cls, data: dict) -> FailureRoute:
        branches_data = data.get("branches", [])
        branches = [Branch.from_dict(b) for b in branches_data]
        return cls(
            mode=data.get("mode", "fail"),
            branches=branches,
        )


# ── Assert Config ──────────────────────────────────────────────


@dataclass
class AssertConfig:
    """Configuration for an assertion step.

    Specifies what to check, what the expected value is, and what to
    do on pass or fail.  Attached to a ``TestStep`` when its action
    is ``"assert"``.

    The ``check_type`` field uses the same values as the step-level
    ``assertion_type`` (text_contains, value_equals, exists, etc.).
    ``on_pass`` and ``on_fail`` provide graph-edge routing for the
    branching engine.
    """

    # ── Capture source ────────────────────────────────────────
    capture_type: str = ""              # "text" | "html" | "value" | "attribute" |
                                        # "screenshot" | "state" | "console" | ""
                                        # Determines HOW data is captured before
                                        # checking.  "screenshot" triggers the OCR
                                        # path via _execute_screenshot_assertion.
    capture_action: str = ""            # Backend action alias, e.g.
                                        # "capture_text", "capture_screenshot"

    # ── What to check ─────────────────────────────────────────
    check_type: str = "exists"          # Same values as assertion_type —
                                        # text_contains, value_equals, etc.
    attribute_name: str = ""            # For attribute_* and css_property_equals
    capture_step_id: str = ""           # For cross-step assertions — the
                                        # step ID whose captured value to compare
    expected: str = ""                  # Expected value (string, number, regex,
                                        # "min,max" for between, pipe-delimited
                                        # for one_of)
    case_sensitive: bool = True         # Whether text comparisons are case-sensitive

    # ── Routing ───────────────────────────────────────────────
    on_pass: str = ""                   # Step ID to continue to on pass
                                        # ("" = next in sequence / end)
    on_fail: FailureRoute = field(default_factory=FailureRoute)
                                        # What to do on failure

    def to_dict(self) -> dict:
        d = {
            "check_type": self.check_type,
            "attribute_name": self.attribute_name,
            "capture_step_id": self.capture_step_id,
            "expected": self.expected,
            "case_sensitive": self.case_sensitive,
            "on_pass": self.on_pass,
            "on_fail": self.on_fail.to_dict(),
        }
        if self.capture_type:
            d["capture_type"] = self.capture_type
        if self.capture_action:
            d["capture_action"] = self.capture_action
        return d

    @classmethod
    def from_dict(cls, data: dict) -> AssertConfig:
        on_fail_data = data.get("on_fail", {})
        on_fail = FailureRoute.from_dict(on_fail_data) if on_fail_data else FailureRoute()
        return cls(
            capture_type=data.get("capture_type", ""),
            capture_action=data.get("capture_action", ""),
            check_type=data.get("check_type", "exists"),
            attribute_name=data.get("attribute_name", ""),
            capture_step_id=data.get("capture_step_id", ""),
            expected=data.get("expected", ""),
            case_sensitive=data.get("case_sensitive", True),
            on_pass=data.get("on_pass", ""),
            on_fail=on_fail,
        )


# ── Diagnostic Config ──────────────────────────────────────────


@dataclass
class DiagnosticConfig:
    """Configuration for a diagnostic step.

    Diagnostic steps are non-destructive probes that collect data
    for debugging.  They can be placed anywhere — inline in the main
    flow or within diagnostic branches.

    Actions:
        ``inject_js``        — Execute user-written JS, capture return value
        ``diag_capture``     — Same as capture_text/html/attr but tagged as diagnostic
        ``diag_screenshot``  — Full-page or element screenshot for evidence
        ``capture_console``  — Start/stop console.log capture scope
    """

    # ── JS Injection ──────────────────────────────────────────
    js_code: str = ""                   # User-written JS to execute in page context
                                        # Return value is captured automatically

    # ── Capture ───────────────────────────────────────────────
    capture_type: str = ""              # "text" | "html" | "attribute" | "value" |
                                        # "screenshot" | "computed_style"
    attribute_name: str = ""            # For attribute / css property captures

    # ── Console capture ───────────────────────────────────────
    console_scope: str = ""             # "start" | "stop" | "" (single-step capture)
                                        # "start" enables capture for all subsequent
                                        # steps until a "stop" is encountered

    # ── Metadata ──────────────────────────────────────────────
    label: str = ""                     # Human label for this diagnostic
                                        # (e.g., "Check appState", "Capture error")

    def to_dict(self) -> dict:
        return {
            "js_code": self.js_code,
            "capture_type": self.capture_type,
            "attribute_name": self.attribute_name,
            "console_scope": self.console_scope,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DiagnosticConfig:
        return cls(
            js_code=data.get("js_code", ""),
            capture_type=data.get("capture_type", ""),
            attribute_name=data.get("attribute_name", ""),
            console_scope=data.get("console_scope", ""),
            label=data.get("label", ""),
        )


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
                                        # "screenshot" | "capture_text" |
                                        # "capture_html" | "capture_value" |
                                        # "capture_attribute" | "capture_url" |
                                        # "capture_computed_style" |
                                        # "inject_js" | "diag_capture" |
                                        # "diag_screenshot" | "capture_console"

    # ── Graph edges ───────────────────────────────────────────
    next_step_id: str | None = None     # Default next step (replaces sequence
                                        # for flow in graph mode). None = use
                                        # sequence ordering (backwards compat)
    branch_id: str | None = None        # Which branch this step belongs to
                                        # (None = main flow)

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
    assertion_type: str = ""            # Text: text_contains | text_equals |
                                        #   text_not_contains | text_starts_with |
                                        #   text_ends_with | text_matches |
                                        #   text_one_of | text_empty | text_not_empty
                                        # Value: value_equals | value_contains |
                                        #   value_empty | value_not_empty
                                        # Attribute: attribute_equals | attribute_contains |
                                        #   attribute_exists | attribute_not_exists
                                        # HTML: html_contains | html_equals |
                                        #   children_count | children_count_gt |
                                        #   children_count_lt
                                        # State: exists | not_exists | visible |
                                        #   hidden | enabled | disabled |
                                        #   checked | not_checked | focused | selected
                                        # CSS: css_class_present | css_class_absent |
                                        #   css_property_equals
                                        # Count: count_equals | count_gt |
                                        #   count_lt | count_gte
                                        # Numeric: numeric_equals | numeric_gt |
                                        #   numeric_lt | numeric_between
                                        # Page: url_equals | url_contains |
                                        #   title_equals | title_contains
                                        # Cross-step: captured_equals |
                                        #   captured_contains | captured_changed |
                                        #   captured_unchanged
    assertion_attribute: str = ""       # For attribute_* and css_property_equals
    assertion_expected: str = ""        # Expected value, "min,max" for between,
                                        # or step_id for captured_* assertions

    # ── Configs (structured, for graph mode) ────────────────────
    assert_config: AssertConfig | None = None
                                        # Full assertion config (routing, branches).
                                        # Only present for action == "assert".
                                        # Flat fields above are still used by the
                                        # replayer for execution; this config adds
                                        # routing and branching on top.
    diagnostic_config: DiagnosticConfig | None = None
                                        # Diagnostic config (inject_js, capture_console).
                                        # Only present for diagnostic actions.

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
        d = {
            "id": self.id,
            "sequence": self.sequence,
            "action": self.action,
            "selector": self.selector,
            "xpath": self.xpath,
            "selector_alternatives": self.selector_alternatives,
            "value": self.value,
            "variable": self.variable,
            "next_step_id": self.next_step_id,
            "branch_id": self.branch_id,
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
        # Only include configs when present (keeps JSON clean for old suites)
        if self.assert_config is not None:
            d["assert_config"] = self.assert_config.to_dict()
        if self.diagnostic_config is not None:
            d["diagnostic_config"] = self.diagnostic_config.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> TestStep:
        """Deserialize from a dict (tolerant of missing keys)."""
        # Parse structured configs if present
        ac_data = data.get("assert_config")
        ac = AssertConfig.from_dict(ac_data) if ac_data else None
        dc_data = data.get("diagnostic_config")
        dc = DiagnosticConfig.from_dict(dc_data) if dc_data else None

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            sequence=data.get("sequence", 0),
            action=data.get("action", ""),
            selector=data.get("selector", ""),
            xpath=data.get("xpath", ""),
            selector_alternatives=data.get("selector_alternatives", []),
            value=data.get("value", ""),
            variable=data.get("variable", ""),
            next_step_id=data.get("next_step_id"),
            branch_id=data.get("branch_id"),
            assertion_type=data.get("assertion_type", ""),
            assertion_attribute=data.get("assertion_attribute", ""),
            assertion_expected=data.get("assertion_expected", ""),
            assert_config=ac,
            diagnostic_config=dc,
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
                                        # Flat list, ordered by sequence.
                                        # Always populated (even in graph mode)
                                        # for backwards compat with replayer.

    # ── Graph mode (optional — built on top of steps) ────────
    steps_dict: dict[str, TestStep] = field(default_factory=dict)
                                        # Dict keyed by step ID. Populated when
                                        # the suite uses graph edges (next_step_id).
                                        # Empty for old linear-only suites.
    start_step_id: str = ""             # Entry point for graph traversal.
                                        # "" = use steps[0] (linear mode).
    branches: dict[str, dict] = field(default_factory=dict)
                                        # Branch metadata keyed by branch_id.
                                        # Each: {"label": str, "color": str}

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
    min_step_delay_ms: int = 700        # Debounce for mutation actions (type, select)
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
        d = {
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
        # Only include graph fields when in graph mode
        if self.steps_dict:
            d["steps_dict"] = {
                sid: s.to_dict() for sid, s in self.steps_dict.items()
            }
        if self.start_step_id:
            d["start_step_id"] = self.start_step_id
        if self.branches:
            d["branches"] = self.branches
        return d

    @classmethod
    def from_dict(cls, data: dict) -> TestSuite:
        """Deserialize from a dict (tolerant of missing keys).

        Handles both old flat-list suites and new graph-mode suites.
        If ``steps_dict`` is present, it's loaded as the graph-mode
        storage and ``steps`` is built from it as a sorted list.
        """
        # Parse steps list (always present, even in graph mode)
        steps_data = data.get("steps", [])
        steps = [TestStep.from_dict(s) for s in steps_data]

        # Parse steps_dict if present (graph mode)
        steps_dict_data = data.get("steps_dict", {})
        steps_dict: dict[str, TestStep] = {}
        if steps_dict_data:
            for sid, sdata in steps_dict_data.items():
                steps_dict[sid] = TestStep.from_dict(sdata)
            # If steps list was empty but steps_dict exists,
            # build steps list from dict (sorted by sequence)
            if not steps:
                steps = sorted(
                    steps_dict.values(), key=lambda s: s.sequence,
                )

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            description=data.get("description", ""),
            target_url=data.get("target_url", ""),
            target_description=data.get("target_description", ""),
            steps=steps,
            steps_dict=steps_dict,
            start_step_id=data.get("start_step_id", ""),
            branches=data.get("branches", {}),
            variables=data.get("variables", {}),
            default_timeout_ms=data.get("default_timeout_ms", 5000),
            navigate_wait_ms=data.get("navigate_wait_ms", 2000),
            replay_speed=data.get("replay_speed", 1.0),
            stop_on_failure=data.get("stop_on_failure", True),
            take_screenshots=data.get("take_screenshots", False),
            visual_delay_ms=data.get("visual_delay_ms", 300),
            min_step_delay_ms=data.get("min_step_delay_ms", 700),
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
    #     "selector": "div.content",
    #     "status": "passed" | "failed" | "skipped",
    #     "duration_ms": 150,
    #     "error": null | "Element not found: #login-btn",
    #     --- capture actions only ---
    #     "captured_value": "Hello World",     # extracted text/html/value/attr
    #     --- assert actions only ---
    #     "assertion_actual": "Hello World",   # what was actually found
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
