# CDP Test Recorder — Full Solution Plan

## Problem Statement

The DCP scripts system today handles one thing: discover scripts,
execute them as subprocesses, capture stdout.  The `mode` field on
`ScriptMeta` promises `"fully_automated" | "semi_automated" | "interactive"`
but only `fully_automated` is implemented.  There is no support for:

- **Browser-based testing** — interacting with the user's deployed app
- **Recording** — capturing user actions for replay
- **Execution plans** — multi-step orchestrated test flows
- **Interactivity** — real-time control over what's happening

The user needs the ability to **record a browser session** against their
app (which DCP monitors), **build a reusable test suite** from that
recording, **validate/edit steps** before saving, and **replay it** via
CDP for regression testing.

This makes DCP a **validation tool** — not just a deployment tool.
The user can verify their DevOps solution actually works, not just
that it deployed.

---

## What Already Exists (Infrastructure Audit)

### CDP Client (`src/ui/web/cdp_client.py`)

| Function | Can we use it? | Notes |
|----------|---------------|-------|
| `is_available()` | ✅ | Gate: don't start recording if CDP is down |
| `get_targets()` | ✅ | List tabs, find the target page |
| `find_target_by_url()` | ✅ | Locate the user's app tab |
| `activate_target()` | ✅ | Focus the target tab during replay |
| `create_tab()` | ✅ | Open target app if no tab exists |
| `evaluate_js()` | ✅ | **Core mechanism** — inject recorder, inject replay commands |
| `try_discover_endpoint()` | ✅ | WSL2 auto-detection |

**Key constraint**: `evaluate_js()` opens a WebSocket, sends one command,
closes.  This is fire-and-forget — no persistent connection.  This is
fine because we don't need one: the injected recorder JS communicates
back via HTTP POST to DCP's Flask API.

### SSE Streaming (proven pattern)

Used in:
- `scripts/execution.py` — `scripts_run_stream()` — stage-based pipeline SSE
- `events/__init__.py` — `EventSource('/api/events')` — global event bus
- `artifacts/api.py` — build/publish streams
- `audit/tool_execution.py` — install plan execution SSE
- `docker/stream.py` — docker action streams

**Pattern**: Flask generator function yields `data: {JSON}\n\n` frames.
Frontend uses `fetch()` + `ReadableStream` or `EventSource`.

### Event Bus (`src/core/services/event_bus.py`)

Thread-safe pub/sub with ring buffer replay.  `bus.publish()` sends
to all subscribers (including SSE listeners).  Has `add_listener()`
for internal consumers (e.g., trace recorder).

**We will use this** for broadcasting recording events to all connected
admin panel instances.

### Run Tracker (`src/core/services/run_tracker.py`)

Tracks execution history in `.state/runs.jsonl`.  Has types like
`"script"`, `"deploy"`, `"build"`.

**We will add** a new run type: `"cdp_test"`.

### Script System (`src/core/services/scripts/`)

Models, registry, executor, history.  `ScriptMeta.mode` field already
exists but is unused beyond `"fully_automated"`.

**We will extend** with `mode: "cdp_test"` and new execution path.

---

## Architecture

### The Three Modes

```
┌─────────────────────────────────────────────────────────┐
│  Mode 1: RECORD                                        │
│                                                        │
│  User interacts with their app normally.               │
│  DCP observes via CDP-injected recorder.               │
│  Events stream to DCP → stored as test steps.          │
│  User controls recording from DCP admin panel.         │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Mode 2: VALIDATE                                      │
│                                                        │
│  User reviews recorded steps in DCP admin panel.       │
│  Can edit selectors, values, add assertions.           │
│  Can set variables for parameterized values.           │
│  Can delete/reorder steps.                             │
│  Saves as a TestSuite (JSON file).                     │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Mode 3: REPLAY                                        │
│                                                        │
│  DCP drives the browser via CDP.                       │
│  Executes each step: navigate, click, type, assert.    │
│  Streams pass/fail per step via SSE.                   │
│  Stores results in run history.                        │
└─────────────────────────────────────────────────────────┘
```

### Communication Flow

```
  ┌─────────────────────┐
  │   DCP Admin Panel    │  ← The user's control center
  │   (port 8001)        │
  │                      │
  │  Recording UI        │◄──── SSE stream (live step feed)
  │  Validation UI       │
  │  Replay UI           │◄──── SSE stream (pass/fail feed)
  │                      │
  │  Controls:           │
  │  [Record] [Pause]    │────► POST /api/cdp-test/record/start
  │  [Stop] [Restart]    │────► POST /api/cdp-test/record/stop
  │  [Save] [Run]        │────► POST /api/cdp-test/replay/start
  └──────────┬───────────┘
             │
             │  HTTP (DCP's own API)
             │
  ┌──────────▼───────────┐
  │   DCP Flask Server   │  ← Backend orchestrator
  │                      │
  │  /api/cdp-test/*     │◄──── HTTP POST (events from recorder)
  │                      │
  │  Session Manager     │  ← Tracks active recording session
  │  Event Bus           │  ← Broadcasts to SSE subscribers
  │  Suite Storage       │  ← Read/write test suites as JSON
  │  Replay Engine       │  ← Drives CDP for replay
  └──────────┬───────────┘
             │
             │  CDP (evaluate_js via PowerShell/WebSocket)
             │
  ┌──────────▼───────────┐
  │   User's App         │  ← The foreign application being tested
  │   (port 3000/8000)   │
  │                      │
  │  Injected Recorder   │  ← JS that captures DOM events
  │  (click, type, nav)  │────► POST http://localhost:8001/api/cdp-test/record/event
  │                      │
  │  OR: Replay Driver   │  ← JS that executes test steps
  │  (click, type, wait) │
  └──────────────────────┘
```

### Why HTTP Callbacks (not persistent WebSocket)

The injected recorder JS in the foreign page calls back to DCP's Flask
API via `fetch()`.  This is the simplest, most reliable approach:

1. **No persistent WebSocket needed** — `evaluate_js()` is fire-and-forget
2. **Works with WSL2** — the foreign page runs in Chrome (Windows side),
   DCP runs on WSL2 — but DCP's Flask server is reachable via WSL2's
   forwarded ports
3. **No CORS issues** — DCP controls the foreign page via CDP injection,
   and the recorder's `fetch()` goes to DCP's server which sets
   appropriate CORS headers
4. **Uses existing SSE** — events arrive via HTTP, get pushed to admin
   panel via the existing `event_bus` → SSE pattern

---

## Data Models

### TestStep

A single recorded or authored action.

```python
@dataclass
class TestStep:
    """One step in a test suite.

    Created during recording (from DOM events) or authored
    manually in the validation UI.
    """

    # ── Identity ──
    id: str                            # UUID, unique within suite
    sequence: int                      # Order in the suite (0-indexed)

    # ── Action ──
    action: str                        # "navigate" | "click" | "type" |
                                       # "select" | "wait" | "assert" |
                                       # "scroll" | "hover" | "keypress" |
                                       # "screenshot"

    # ── Target ──
    selector: str = ""                 # CSS selector (preferred)
    xpath: str = ""                    # XPath (fallback/alternative)
    selector_alternatives: list[str] = field(default_factory=list)
                                       # Other selectors that also match
                                       # (for resilience — if primary breaks)

    # ── Value ──
    value: str = ""                    # Text to type, URL to navigate to,
                                       # expected text for assert, etc.
    variable: str = ""                 # Variable name (e.g., "${PASSWORD}")
                                       # Resolved at execution time

    # ── Assertion ──
    assertion_type: str = ""           # "text_contains" | "text_equals" |
                                       # "exists" | "not_exists" |
                                       # "attribute_equals" | "visible"
    assertion_attribute: str = ""      # For "attribute_equals"
    assertion_expected: str = ""       # Expected value

    # ── Timing ──
    wait_before_ms: int = 0           # Explicit wait before this step
    timeout_ms: int = 5000            # Max time to wait for element/condition
    recorded_delay_ms: int = 0        # Actual delay from recording (for pacing)

    # ── Metadata ──
    description: str = ""             # Human description (auto-generated or manual)
    screenshot_before: str = ""       # Path/reference to screenshot (optional)
    screenshot_after: str = ""        # Path/reference to screenshot (optional)
    tag: str = ""                     # User-assigned tag for grouping
    optional: bool = False            # If True, failure doesn't fail the suite

    # ── Recording context ──
    page_url: str = ""                # URL of the page when step was recorded
    element_tag: str = ""             # Tag name of the element (div, input, etc.)
    element_text: str = ""            # Visible text of the element (for debugging)
    element_rect: dict = field(default_factory=dict)
                                      # Bounding rect {x, y, width, height}
```

### TestSuite

An ordered collection of steps with metadata.

```python
@dataclass
class TestSuite:
    """A complete test suite — a named, replayable sequence of steps.

    Stored as JSON in `.state/cdp-tests/` directory.
    Can be created from recording, manual authoring, or import.
    """

    # ── Identity ──
    id: str                            # UUID
    name: str                          # Human name ("Login Flow", "Dashboard Smoke Test")
    description: str = ""              # Longer description

    # ── Target ──
    target_url: str = ""               # Base URL of the app (http://localhost:3000)
    target_description: str = ""       # "React frontend" / "Django admin"

    # ── Steps ──
    steps: list[TestStep] = field(default_factory=list)

    # ── Variables ──
    variables: dict[str, str] = field(default_factory=dict)
                                       # Name → default value
                                       # e.g., {"USERNAME": "admin", "PASSWORD": ""}
                                       # Empty string = must be filled before run

    # ── Configuration ──
    default_timeout_ms: int = 5000     # Default per-step timeout
    navigate_wait_ms: int = 2000       # Wait after navigation before next step
    replay_speed: float = 1.0          # Multiplier on recorded_delay_ms
    stop_on_failure: bool = True       # Stop suite on first step failure
    take_screenshots: bool = False     # Capture screenshots at each step

    # ── Metadata ──
    created_at: str = ""               # ISO timestamp
    updated_at: str = ""               # ISO timestamp
    created_by: str = "recording"      # "recording" | "manual" | "import"
    tags: list[str] = field(default_factory=list)
    category: str = "smoke"            # "smoke" | "regression" | "integration" | "custom"

    # ── History ──
    last_run_at: str = ""              # ISO timestamp of last execution
    last_run_status: str = ""          # "passed" | "failed" | "partial"
    run_count: int = 0                 # Total number of executions
```

### TestRunResult

The result of replaying a test suite.

```python
@dataclass
class TestRunResult:
    """Result of a single test suite execution."""

    # ── Identity ──
    id: str                            # Run UUID
    suite_id: str                      # Which suite was run
    suite_name: str                    # Suite name (for display)

    # ── Timing ──
    started_at: str = ""               # ISO timestamp
    finished_at: str = ""              # ISO timestamp
    duration_ms: int = 0               # Total execution time

    # ── Results ──
    status: str = "pending"            # "pending" | "running" | "passed" |
                                       # "failed" | "cancelled" | "error"
    total_steps: int = 0
    passed_steps: int = 0
    failed_steps: int = 0
    skipped_steps: int = 0

    # ── Step Results ──
    step_results: list[dict] = field(default_factory=list)
    # Each: {
    #     "step_id": "...",
    #     "sequence": 0,
    #     "action": "click",
    #     "status": "passed" | "failed" | "skipped",
    #     "duration_ms": 150,
    #     "error": null | "Element not found: #login-btn",
    #     "screenshot": null | "path/to/screenshot.png",
    # }

    # ── Variables used ──
    variables_used: dict[str, str] = field(default_factory=dict)
                                       # Resolved variable values (passwords redacted)

    # ── Error info ──
    error: str = ""                    # Global error (CDP unavailable, etc.)
```

---

## Storage

### File Layout

```
.state/
  cdp-tests/
    suites/
      <suite-id>.json          # TestSuite serialized
    results/
      <run-id>.json            # TestRunResult serialized
    recordings/
      <session-id>/            # Active recording temp data
        steps.jsonl            # Streaming step capture
        screenshots/           # Screenshots (if enabled)
```

### Integration with Script System

Test suites are discoverable as scripts with `mode: "cdp_test"`:

```
scripts/
  tests/                       # Convention: tests/ subdirectory
    login_flow.json            # Saved TestSuite (also discoverable)
```

**Or** test suites live in `.state/cdp-tests/suites/` and are accessible
through the scripts UI as a special category.  The script registry already
supports `category: "test"` — we add it to the default categories list.

**Recommendation**: `.state/cdp-tests/` for storage, surfaced in the
scripts UI under a "CDP Tests" category.  Don't mix JSON test suites
with Python/bash scripts in the `scripts/` directory — they're
fundamentally different artifacts.

---

## The Recorder Script (Injected JS)

### What It Captures

The recorder is a self-contained JS module injected into the foreign
page via `cdp_client.evaluate_js()`.  It attaches event listeners to
the document and sends captured events back to DCP's API.

#### Event Types

| DOM Event | TestStep Action | What's Captured |
|-----------|----------------|-----------------|
| `click` | `"click"` | selector, element text, position |
| `dblclick` | `"click"` (double=true) | selector, element text |
| `input` / `change` | `"type"` | selector, new value, input type |
| `keydown` (Enter, Escape, Tab) | `"keypress"` | key name, selector |
| `submit` | `"click"` (on submit button) | form selector |
| `beforeunload` / `popstate` | `"navigate"` | new URL |
| `scroll` | `"scroll"` | scroll position (debounced) |
| `select` (on `<select>`) | `"select"` | selector, selected value |

#### Selector Building Strategy

For each interacted element, the recorder builds multiple selectors
in priority order:

```javascript
function buildSelectors(element) {
    const selectors = [];

    // 1. ID (best — unique by definition)
    if (element.id) {
        selectors.push({ type: 'css', value: '#' + CSS.escape(element.id), priority: 1 });
    }

    // 2. data-testid (recommended for testing)
    const testId = element.getAttribute('data-testid')
                || element.getAttribute('data-test')
                || element.getAttribute('data-cy');
    if (testId) {
        selectors.push({ type: 'css', value: `[data-testid="${testId}"]`, priority: 2 });
    }

    // 3. name attribute (forms)
    if (element.name) {
        selectors.push({
            type: 'css',
            value: `${element.tagName.toLowerCase()}[name="${element.name}"]`,
            priority: 3,
        });
    }

    // 4. Unique class combination
    const uniqueClasses = findUniqueClassCombo(element);
    if (uniqueClasses) {
        selectors.push({ type: 'css', value: uniqueClasses, priority: 4 });
    }

    // 5. role + text (accessibility)
    const role = element.getAttribute('role');
    const text = element.textContent?.trim().slice(0, 50);
    if (role && text) {
        selectors.push({
            type: 'xpath',
            value: `//*[@role="${role}" and contains(text(),"${text}")]`,
            priority: 5,
        });
    }

    // 6. XPath from DOM path (most fragile — last resort)
    selectors.push({ type: 'xpath', value: getXPath(element), priority: 6 });

    return selectors;
}
```

The primary selector (highest priority that's unique on the page) is
stored in `TestStep.selector`.  Alternatives go in
`TestStep.selector_alternatives`.

#### Navigation Tracking

The recorder detects navigation via:
- `beforeunload` event
- `popstate` / `hashchange` events (SPA navigation)
- `MutationObserver` on `document.title` changes
- Polling `location.href` every 500ms (catches all edge cases)

Each navigation creates a `"navigate"` step with the new URL.

#### Sending Events to DCP

```javascript
function sendToDCP(stepData) {
    const dcpUrl = 'http://${DCP_HOST}:${DCP_PORT}/api/cdp-test/record/event';
    navigator.sendBeacon(dcpUrl, JSON.stringify(stepData));
    // sendBeacon is fire-and-forget, survives page unload
    // Fallback to fetch() if sendBeacon unavailable
}
```

Using `navigator.sendBeacon()` instead of `fetch()` for resilience —
it survives page navigation (the event still gets delivered even if
the page is unloading).  Fallback to `fetch()` for browsers that
don't support it (shouldn't happen in modern Chrome).

### Recorder Lifecycle

```
1. User clicks "Start Recording" in DCP admin panel
2. DCP calls POST /api/cdp-test/record/start
3. Backend:
   a. Creates recording session (UUID, target URL, empty steps)
   b. Finds target tab via cdp_client.get_targets()
   c. Injects recorder JS via cdp_client.evaluate_js()
   d. Returns session_id to frontend
   e. Publishes "cdp_test:record_start" to event bus
4. Recorder JS starts capturing events
5. User interacts with their app
6. Recorder POSTs each event to /api/cdp-test/record/event
7. Backend:
   a. Validates event, appends to session steps
   b. Publishes "cdp_test:step_captured" to event bus
   c. SSE delivers step to admin panel in real-time
8. Admin panel shows each step appearing live
9. User can:
   - Pause: POST /api/cdp-test/record/pause
     → evaluate_js() tells recorder to stop capturing
   - Resume: POST /api/cdp-test/record/resume
     → evaluate_js() tells recorder to restart
   - Restart: POST /api/cdp-test/record/restart
     → clears steps, re-injects recorder
   - Stop: POST /api/cdp-test/record/stop
     → evaluate_js() removes recorder from page
     → transitions to validation mode
```

### Re-injection on Navigation

When the user navigates to a new page, the recorder script dies
(it's a new DOM context).  The backend handles this:

1. Backend polls `cdp_client.get_targets()` every 2 seconds during
   active recording
2. If the target tab's URL changes and our recorder is gone,
   re-inject via `evaluate_js()`
3. The recorder JS sets `window.__dcp_recorder_active = true`
4. Before re-injection, check this flag — if already active, skip

This ensures continuous recording across page navigations, even for
traditional multi-page apps.

---

## API Endpoints

### Blueprint: `cdp_test_bp`

Registered at `/api` prefix in `src/ui/web/routes/cdp_test/`.

#### Recording Control

```
POST /api/cdp-test/record/start
    Body: { "target_url": "http://localhost:3000" }
    → Creates session, injects recorder
    ← { "ok": true, "session_id": "abc-123", "target": { tab info } }

POST /api/cdp-test/record/stop
    Body: { "session_id": "abc-123" }
    → Removes recorder, finalizes session
    ← { "ok": true, "steps_count": 15, "suite_draft": { ... } }

POST /api/cdp-test/record/pause
    Body: { "session_id": "abc-123" }
    → Pauses recorder (events still captured but marked paused)
    ← { "ok": true }

POST /api/cdp-test/record/resume
    Body: { "session_id": "abc-123" }
    → Resumes recorder
    ← { "ok": true }

POST /api/cdp-test/record/restart
    Body: { "session_id": "abc-123" }
    → Clears steps, re-injects recorder
    ← { "ok": true, "session_id": "abc-123" }

POST /api/cdp-test/record/event
    Body: {
        "session_id": "abc-123",
        "action": "click",
        "selector": "#login-btn",
        "xpath": "/html/body/div/button[2]",
        "value": "",
        "element_tag": "button",
        "element_text": "Log In",
        "element_rect": { "x": 100, "y": 200, "width": 80, "height": 32 },
        "page_url": "http://localhost:3000/login",
        "timestamp_ms": 1709123456789
    }
    → Appends step to session
    ← { "ok": true, "step_id": "step-uuid", "sequence": 5 }
```

#### Recording Status (SSE)

```
GET /api/cdp-test/record/stream?session_id=abc-123
    → SSE stream of recording events
    Events:
        cdp_test:step_captured    — new step recorded
        cdp_test:record_paused    — recording paused
        cdp_test:record_resumed   — recording resumed
        cdp_test:record_stopped   — recording stopped
        cdp_test:recorder_lost    — recorder died (page navigated)
        cdp_test:recorder_injected — recorder re-injected
```

#### Suite Management (CRUD)

```
GET /api/cdp-test/suites
    → List all saved test suites
    ← { "ok": true, "suites": [ ... ] }

GET /api/cdp-test/suites/<suite_id>
    → Get full suite with all steps
    ← { "ok": true, "suite": { ... } }

POST /api/cdp-test/suites
    Body: { TestSuite fields }
    → Create/save a test suite (from recording or manual)
    ← { "ok": true, "suite_id": "..." }

PUT /api/cdp-test/suites/<suite_id>
    Body: { updated fields }
    → Update suite (edit steps, name, variables, etc.)
    ← { "ok": true }

DELETE /api/cdp-test/suites/<suite_id>
    → Delete a suite
    ← { "ok": true }

POST /api/cdp-test/suites/<suite_id>/duplicate
    → Clone a suite
    ← { "ok": true, "suite_id": "new-id" }
```

#### Suite Step Editing

```
PUT /api/cdp-test/suites/<suite_id>/steps/<step_id>
    Body: { updated step fields }
    → Edit a single step (selector, value, assertion, etc.)
    ← { "ok": true }

DELETE /api/cdp-test/suites/<suite_id>/steps/<step_id>
    → Remove a step
    ← { "ok": true }

POST /api/cdp-test/suites/<suite_id>/steps/<step_id>/move
    Body: { "new_sequence": 3 }
    → Reorder a step
    ← { "ok": true }

POST /api/cdp-test/suites/<suite_id>/steps
    Body: { step fields }
    → Add a new step manually
    ← { "ok": true, "step_id": "..." }
```

#### Replay

```
POST /api/cdp-test/replay/start
    Body: {
        "suite_id": "...",
        "variables": { "PASSWORD": "secret123" },
        "options": {
            "speed": 1.0,
            "stop_on_failure": true,
            "take_screenshots": false
        }
    }
    → Starts replay, returns SSE stream

    SSE Events:
        cdp_test:replay_start     — suite execution begins
        cdp_test:step_start       — step N about to execute
        cdp_test:step_passed      — step N succeeded
        cdp_test:step_failed      — step N failed (with error)
        cdp_test:step_skipped     — step N skipped (optional + previous failure)
        cdp_test:replay_done      — suite execution complete

POST /api/cdp-test/replay/cancel
    Body: { "run_id": "..." }
    → Cancel an active replay
    ← { "ok": true }

GET /api/cdp-test/results
    → List replay results (history)
    ← { "ok": true, "results": [ ... ] }

GET /api/cdp-test/results/<run_id>
    → Detail for one replay result
    ← { "ok": true, "result": { ... } }
```

#### Utility

```
POST /api/cdp-test/validate-selector
    Body: { "selector": "#login-btn", "target_url": "http://localhost:3000" }
    → Check if selector finds an element on the page
    ← { "ok": true, "found": true, "count": 1, "element_text": "Log In" }

POST /api/cdp-test/highlight-element
    Body: { "selector": "#login-btn", "target_url": "http://localhost:3000" }
    → Visually highlight the element on the foreign page (via CDP)
    ← { "ok": true }

GET /api/cdp-test/targets
    → List browser tabs available for recording
    ← { "ok": true, "targets": [ { url, title, id } ] }
```

---

## Backend Services

### New Files

```
src/core/services/cdp_test/
    __init__.py                # Package init
    models.py                  # TestStep, TestSuite, TestRunResult
    session.py                 # RecordingSession — active recording state
    storage.py                 # Suite/result CRUD (JSON file I/O)
    recorder.py                # Recorder injection + event processing
    replayer.py                # Replay engine (CDP-driven step execution)
    selector.py                # Selector validation + highlights

src/ui/web/routes/cdp_test/
    __init__.py                # Blueprint: cdp_test_bp
    recording.py               # Recording control endpoints
    suites.py                  # Suite CRUD endpoints
    replay.py                  # Replay endpoints + SSE stream

src/ui/web/templates/scripts/
    _cdp_test.html             # Recording/validation/replay UI
    _cdp_test_record.html      # Recording mode UI components
    _cdp_test_validate.html    # Step editing/validation UI
    _cdp_test_replay.html      # Replay viewer UI

src/core/data/
    cdp_recorder.js            # The recorder script (injected into foreign pages)
```

### `session.py` — Recording Session Manager

```python
"""Active recording session management.

Manages the lifecycle of a recording session — from injection
to step capture to finalization.  Thread-safe: the recorder
POSTs events from a browser thread while the admin panel
reads state from the Flask request thread.
"""

import threading
import uuid
from dataclasses import dataclass, field

@dataclass
class RecordingSession:
    """An active recording session."""
    id: str
    target_url: str
    target_id: str                         # Chrome target ID
    status: str = "recording"              # "recording" | "paused" | "stopped"
    steps: list[dict] = field(default_factory=list)
    started_at: str = ""
    paused_at: str = ""

    _lock: threading.Lock = field(
        default_factory=threading.Lock, repr=False
    )

    def add_step(self, step_data: dict) -> dict:
        """Thread-safe step addition."""
        with self._lock:
            step = {
                "id": str(uuid.uuid4()),
                "sequence": len(self.steps),
                **step_data,
            }
            self.steps.append(step)
            return step

    def clear_steps(self) -> None:
        """Clear all recorded steps (restart)."""
        with self._lock:
            self.steps.clear()


# Module-level active session (one recording at a time)
_active_session: RecordingSession | None = None
_session_lock = threading.Lock()

def get_active_session() -> RecordingSession | None: ...
def create_session(target_url: str, target_id: str) -> RecordingSession: ...
def end_session() -> RecordingSession | None: ...
```

### `recorder.py` — Recorder Injection

```python
"""CDP recorder injection — injects and manages the recorder script
in the foreign page.

Handles:
- Initial injection via evaluate_js()
- Re-injection on page navigation
- Pause/resume via JS flag manipulation
- Recorder removal on stop
"""

def inject_recorder(
    target_ws_url: str,
    session_id: str,
    dcp_host: str,
    dcp_port: int,
) -> bool:
    """Inject the recorder script into a Chrome tab.

    The recorder script is loaded from src/core/data/cdp_recorder.js,
    parameterized with session_id and DCP callback URL, then
    executed via cdp_client.evaluate_js().
    """
    ...

def remove_recorder(target_ws_url: str) -> bool:
    """Remove the recorder from a Chrome tab."""
    ...

def check_recorder_alive(target_ws_url: str) -> bool:
    """Check if the recorder is still active in the tab."""
    ...

def pause_recorder(target_ws_url: str) -> bool:
    """Tell the recorder to stop capturing (but stay injected)."""
    ...

def resume_recorder(target_ws_url: str) -> bool:
    """Tell the recorder to resume capturing."""
    ...
```

### `replayer.py` — Replay Engine

```python
"""CDP replay engine — executes test suite steps via CDP.

Drives the browser through each test step, executing the
appropriate JS for each action type, checking assertions,
and reporting results via the event bus.
"""

def replay_suite(
    suite: TestSuite,
    variables: dict[str, str],
    options: dict,
    stop_event: threading.Event,
    callback: Callable[[str, dict], None],  # (event_type, data)
) -> TestRunResult:
    """Execute a full test suite.

    Runs in a background thread. Uses `callback` to report
    progress (which feeds the SSE stream).

    For each step:
    1. Wait (wait_before_ms or pacing delay)
    2. Find element (selector, with timeout)
    3. Execute action (click, type, navigate, etc.)
    4. Check assertion (if any)
    5. Report result via callback
    """
    ...

def _execute_step(
    ws_url: str,
    step: TestStep,
    variables: dict[str, str],
) -> dict:
    """Execute a single test step via CDP.

    Returns:
        {
            "status": "passed" | "failed",
            "duration_ms": 150,
            "error": None | "Element not found: #login-btn",
        }
    """
    ...

def _resolve_variables(value: str, variables: dict[str, str]) -> str:
    """Replace ${VAR_NAME} placeholders with values."""
    ...

# ── Per-action JS generators ──

def _js_navigate(url: str) -> str: ...
def _js_click(selector: str) -> str: ...
def _js_type(selector: str, value: str) -> str: ...
def _js_select(selector: str, value: str) -> str: ...
def _js_wait_for(selector: str, timeout_ms: int) -> str: ...
def _js_assert_text(selector: str, expected: str, mode: str) -> str: ...
def _js_assert_exists(selector: str) -> str: ...
def _js_assert_visible(selector: str) -> str: ...
def _js_scroll(x: int, y: int) -> str: ...
def _js_screenshot() -> str: ...
```

---

## Frontend UI

### Integration Point

The CDP Test module lives under the scripts/integrations tab as a new
card (same as existing Scripts card).  Additionally, it has its own
modal workflow for recording → validation → replay.

### Recording UI

```
┌─────────────────────────────────────────────────────────┐
│  🔴 Recording: http://localhost:3000                   │
│                                                        │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Step │ Action    │ Target          │ Value        │ │
│  │ ─────┼───────────┼─────────────────┼──────────────│ │
│  │   1  │ navigate  │ /login          │              │ │
│  │   2  │ type      │ #username       │ admin        │ │
│  │   3  │ type      │ #password       │ ••••••       │ │
│  │   4  │ click     │ button.submit   │              │ │
│  │   5  │ navigate  │ /dashboard      │              │ │
│  │   6  │ ●         │ (recording...)  │              │ │
│  └────────────────────────────────────────────────────┘ │
│                                                        │
│  Duration: 00:42     Steps: 5                          │
│                                                        │
│  [⏸ Pause] [⏹ Stop] [🔄 Restart]                      │
└─────────────────────────────────────────────────────────┘
```

### Validation UI

```
┌─────────────────────────────────────────────────────────┐
│  📝 Validate: Login Flow (5 steps)                     │
│                                                        │
│  Suite Name: [Login Flow_____________]                  │
│  Target URL: [http://localhost:3000___]                 │
│  Category:   [smoke ▼]                                 │
│                                                        │
│  ┌────────────────────────────────────────────────────┐ │
│  │                                                    │ │
│  │  Step 1: Navigate to /login                        │ │
│  │  ┌──────────────────────────────────────────────┐  │ │
│  │  │ Action:   navigate                           │  │ │
│  │  │ URL:      /login                             │  │ │
│  │  │ Timeout:  [5000] ms                          │  │ │
│  │  │                                              │  │ │
│  │  │ [✓ Validate Selector] [🔍 Highlight]         │  │ │
│  │  │ [➕ Add Assertion] [🗑 Delete]               │  │ │
│  │  └──────────────────────────────────────────────┘  │ │
│  │                                                    │ │
│  │  Step 2: Type "admin" into #username               │ │
│  │  ┌──────────────────────────────────────────────┐  │ │
│  │  │ Action:   type                               │  │ │
│  │  │ Selector: [#username_______________] ✅       │  │ │
│  │  │ Value:    [admin___________________]         │  │ │
│  │  │ Variable: [${USERNAME}___] (optional)         │  │ │
│  │  │ Alt selectors:                               │  │ │
│  │  │   • input[name="username"]                   │  │ │
│  │  │   • [data-testid="login-username"]           │  │ │
│  │  │                                              │  │ │
│  │  │ [✓ Validate] [🔍 Highlight] [🗑 Delete]      │  │ │
│  │  └──────────────────────────────────────────────┘  │ │
│  │                                                    │ │
│  │  ... more steps ...                                │ │
│  │                                                    │ │
│  └────────────────────────────────────────────────────┘ │
│                                                        │
│  ┌─ Variables ────────────────────────────────────────┐ │
│  │ USERNAME = [admin_______]                         │ │
│  │ PASSWORD = [_____________] (required at runtime)  │ │
│  └───────────────────────────────────────────────────┘ │
│                                                        │
│  [Cancel] [💾 Save Suite] [▶ Run Now]                  │
└─────────────────────────────────────────────────────────┘
```

### Replay UI

```
┌─────────────────────────────────────────────────────────┐
│  ▶ Replaying: Login Flow                               │
│                                                        │
│  Progress: ████████░░ 4/5 steps (80%)                  │
│                                                        │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Step │ Action    │ Target          │ Status       │ │
│  │ ─────┼───────────┼─────────────────┼──────────────│ │
│  │   1  │ navigate  │ /login          │ ✅ 120ms     │ │
│  │   2  │ type      │ #username       │ ✅ 45ms      │ │
│  │   3  │ type      │ #password       │ ✅ 42ms      │ │
│  │   4  │ click     │ button.submit   │ ✅ 2100ms    │ │
│  │   5  │ assert    │ h1              │ ⏳ running   │ │
│  └────────────────────────────────────────────────────┘ │
│                                                        │
│  Time: 2.3s / ~3.0s                                    │
│                                                        │
│  [⏹ Cancel]                                            │
└─────────────────────────────────────────────────────────┘
```

---

## Replay Engine — Step Execution Detail

### Per-Action JS

Each action type is translated to JavaScript that's executed via
`evaluate_js()`.  The JS is a self-contained IIFE that returns a
result object.

#### Click

```javascript
(function() {
    var el = document.querySelector('${SELECTOR}');
    if (!el) return { ok: false, error: 'Element not found: ${SELECTOR}' };
    el.scrollIntoView({ block: 'center', behavior: 'instant' });
    el.click();
    return { ok: true };
})()
```

#### Type

```javascript
(function() {
    var el = document.querySelector('${SELECTOR}');
    if (!el) return { ok: false, error: 'Element not found: ${SELECTOR}' };
    el.focus();
    el.value = '';
    // Simulate real typing (triggers React/Vue change detection)
    var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value'
    ).set;
    nativeInputValueSetter.call(el, '${VALUE}');
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return { ok: true };
})()
```

**Critical detail**: React, Vue, and Angular intercept `input.value = x`
assignments.  We use the native setter + synthetic events to trigger
their change detection.  This is the same trick Puppeteer/Playwright use.

#### Navigate

```javascript
(function() {
    window.location.href = '${URL}';
    return { ok: true };
})()
```

After navigation, the replayer must wait for the new page to load.
It does this by polling `get_targets()` until the tab's URL matches,
then waiting for `evaluate_js("document.readyState")` to return
`"complete"`.

#### Wait For Element

```javascript
(function() {
    return new Promise(function(resolve) {
        var start = Date.now();
        var check = function() {
            var el = document.querySelector('${SELECTOR}');
            if (el) return resolve({ ok: true });
            if (Date.now() - start > ${TIMEOUT_MS}) {
                return resolve({
                    ok: false,
                    error: 'Timeout waiting for: ${SELECTOR} (${TIMEOUT_MS}ms)'
                });
            }
            requestAnimationFrame(check);
        };
        check();
    });
})()
```

**Note**: `evaluate_js()` can handle Promises — CDP's `Runtime.evaluate`
with `awaitPromise: true`.  We may need to extend `evaluate_js()` to
pass this flag.  **This is the one extension to `cdp_client.py` we need.**

#### Assert Text

```javascript
(function() {
    var el = document.querySelector('${SELECTOR}');
    if (!el) return { ok: false, error: 'Element not found: ${SELECTOR}' };
    var text = el.textContent.trim();
    // mode: "contains" | "equals"
    var match = ${MODE_IS_CONTAINS}
        ? text.includes('${EXPECTED}')
        : text === '${EXPECTED}';
    if (!match) {
        return {
            ok: false,
            error: 'Expected: "${EXPECTED}", got: "' + text.slice(0, 100) + '"'
        };
    }
    return { ok: true, actual: text };
})()
```

---

## CDP Client Extension

### One Change Needed: `awaitPromise` flag

For the `wait` action (and potentially others that return Promises),
we need `evaluate_js()` to pass `"awaitPromise": true` in the
`Runtime.evaluate` params.

```python
def evaluate_js(
    ws_url: str,
    expression: str,
    timeout: float = 5.0,
    await_promise: bool = False,    # NEW parameter
) -> dict | None:
    # ... existing code ...
    # Change the JSON command to include awaitPromise
    cmd = json.dumps({
        "id": 1,
        "method": "Runtime.evaluate",
        "params": {
            "expression": expression,
            "awaitPromise": await_promise,
        },
    })
```

This is the **only** change needed in `cdp_client.py`.

---

## Event Bus Integration

### New Event Types

```
cdp_test:record_start      — Recording session started
cdp_test:record_stop       — Recording session stopped
cdp_test:record_pause      — Recording paused
cdp_test:record_resume     — Recording resumed
cdp_test:step_captured      — New step recorded (during recording)
cdp_test:recorder_lost      — Recorder died (page navigation)
cdp_test:recorder_injected  — Recorder (re-)injected
cdp_test:replay_start       — Suite replay started
cdp_test:step_start         — Replay step started
cdp_test:step_passed        — Replay step passed
cdp_test:step_failed        — Replay step failed
cdp_test:step_skipped       — Replay step skipped
cdp_test:replay_done        — Suite replay complete
```

---

## Run Tracker Integration

### New Run Type

Add `"cdp_test"` to `RUN_TYPES` in `run_tracker.py`:

```python
RUN_TYPES = {
    # ... existing types ...
    "cdp_test":  "CDP browser test execution",
}
```

### Recording in Ledger

Each replay creates a run entry:

```python
with tracked_run(
    root, "cdp_test", "cdp_test:replay",
    summary=f"Replay: {suite.name}",
    suite_id=suite.id,
    total_steps=len(suite.steps),
) as run:
    result = replayer.replay_suite(suite, variables, options, ...)
    run["metadata"]["passed_steps"] = result.passed_steps
    run["metadata"]["failed_steps"] = result.failed_steps
    run["metadata"]["status"] = result.status
```

---

## Script System Integration

### New Category

Add `"test"` to `ScriptConfig.categories`:

```python
categories: list[str] = field(default_factory=lambda: [
    "audit", "generator", "analyzer", "debug", "ops", "general",
    "test",  # CDP browser tests
])
```

### Script UI Integration

The scripts integrations card gets a new button: **"CDP Tests"**
alongside existing "Run…" and "History". This opens the CDP Test
module with its three modes.

---

## Implementation Phases

### Phase 1: Foundation (Data + Storage + API skeleton)

**New files:**
- `src/core/services/cdp_test/__init__.py`
- `src/core/services/cdp_test/models.py` — TestStep, TestSuite, TestRunResult
- `src/core/services/cdp_test/storage.py` — JSON CRUD for suites/results
- `src/ui/web/routes/cdp_test/__init__.py` — Blueprint
- `src/ui/web/routes/cdp_test/suites.py` — Suite CRUD endpoints

**Modified files:**
- `src/core/services/run_tracker.py` — Add "cdp_test" run type
- `src/ui/web/server.py` — Register cdp_test_bp

**Testable**: API returns empty suite list, can create/read/update/delete
suites manually via API.

### Phase 2: Recorder (Injection + Event Capture)

**New files:**
- `src/core/data/cdp_recorder.js` — The injected recorder script
- `src/core/services/cdp_test/session.py` — RecordingSession manager
- `src/core/services/cdp_test/recorder.py` — Injection + lifecycle
- `src/ui/web/routes/cdp_test/recording.py` — Recording control endpoints

**Modified files:**
- `src/ui/web/cdp_client.py` — Add `await_promise` parameter

**Testable**: Start recording against `python -m http.server 8000`,
interact with file listing, see events arrive at DCP API.

### Phase 3: Recording UI (Live Step Viewer)

**New files:**
- `src/ui/web/templates/scripts/_cdp_test.html` — Main UI entry
- `src/ui/web/templates/scripts/_cdp_test_record.html` — Recording mode

**Modified files:**
- `src/ui/web/templates/scripts/integrations/_scripts.html` — Add CDP Tests button

**Testable**: Full recording workflow visible in admin panel —
start, see steps appear live, pause, resume, stop.

### Phase 4: Validation UI (Step Editor)

**New files:**
- `src/ui/web/templates/scripts/_cdp_test_validate.html` — Step editor
- `src/core/services/cdp_test/selector.py` — Selector validation

**Modified files:**
- `src/ui/web/routes/cdp_test/suites.py` — Step editing endpoints
- `src/ui/web/routes/cdp_test/recording.py` — validate-selector, highlight

**Testable**: After recording, review each step, edit selectors,
add assertions, set variables, save as suite.

### Phase 5: Replay Engine

**New files:**
- `src/core/services/cdp_test/replayer.py` — Step execution engine
- `src/ui/web/routes/cdp_test/replay.py` — Replay endpoints + SSE

**Testable**: Select a saved suite, fill variables, run it, see
pass/fail per step streaming in real-time.

### Phase 6: Replay UI + Polish

**New files:**
- `src/ui/web/templates/scripts/_cdp_test_replay.html` — Replay viewer

**Modified files:**
- Run history integration — CDP test runs appear in script history
- Suite list UI — shows last run status per suite

**Testable**: Full end-to-end: record → validate → save → replay →
see results → view in history.

---

## WSL2 Considerations

All CDP operations use `evaluate_js()` which already handles the
WSL2 bridge via PowerShell.  The recorder's HTTP callback
(`sendBeacon` / `fetch`) goes from Chrome (Windows) to DCP (WSL2) —
this works if DCP binds to `0.0.0.0` (which it does by default in
dev mode) because Chrome can reach WSL2 via `localhost` port
forwarding.

**If binding to `127.0.0.1`:** The recorder would need to use the
WSL2 VM's IP instead of `localhost`.  The injection template can
detect this and use the correct address.

---

## Edge Cases

| Scenario | Handling |
|----------|---------|
| **Page navigates during recording** | Recorder re-injection via polling |
| **SPA navigation (pushState)** | Recorder survives (same DOM context) |
| **Tab closed during recording** | Detect via get_targets(), stop session |
| **CDP becomes unavailable** | Session enters "degraded" state, auto-retry |
| **Multiple recording sessions** | One at a time (single active session) |
| **iframe interactions** | Phase 1: skip. Phase 2+: inject into iframes |
| **Shadow DOM elements** | Use `element.shadowRoot.querySelector()` variant |
| **File upload inputs** | Record as "type" with file path — CDP can set via protocol |
| **Alerts/confirms/prompts** | CDP has `Page.javascriptDialogOpening` — future enhancement |
| **Auth-protected pages** | User records after manual login — recorder captures the flow |
| **Dynamic selectors** | Multiple alternatives stored — fallback chain during replay |

---

## Future Parking Lot (Not in scope)

- **Visual regression** — screenshot comparison (golden image vs current)
- **Network interception** — mock API responses during replay
- **Parallel execution** — run suites across multiple tabs
- **CI/CD integration** — run suites from CLI (headless Chrome)
- **Import/export** — Playwright/Cypress test import
- **Custom JS steps** — user-authored JavaScript evaluation steps
- **Conditional steps** — if/else based on page state
- **Loop steps** — repeat a group of steps N times
- **Data-driven testing** — CSV/JSON data sources for variables
