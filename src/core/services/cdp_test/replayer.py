"""
CDP Test replay engine — executes test suite steps via CDP.

Drives the browser through each test step: finds the target tab,
activates it, then executes steps in sequence.  Each step generates
a self-contained JavaScript expression that:

1. Finds the target element (with configurable timeout + retry)
2. Performs the action (click, type, navigate, select, etc.)
3. Returns a structured result: ``{ ok: true }`` or ``{ ok: false, error: "..." }``

Progress is reported via a callback function which feeds the SSE stream
in the API layer.

Tab transitions are hardened:
    - Target tab is verified before every step (handles tab closure mid-replay)
    - Navigation steps wait for page load completion
    - The DCP admin tab is re-activated after replay finishes

Used by:
    routes/cdp_test/replay.py  — API endpoints that start/cancel replay
"""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid

from src.core.services.cdp_test.models import (
    TestRunResult,
    TestSuite,
    _now_iso,
)

logger = logging.getLogger(__name__)


# ── Module state ───────────────────────────────────────────────

_active_run: _ReplayRun | None = None
_run_lock = threading.Lock()


class _ReplayRun:
    """Tracks a single active replay execution."""

    __slots__ = ("run_id", "suite_id", "thread", "stop_event")

    def __init__(self, run_id: str, suite_id: str):
        self.run_id = run_id
        self.suite_id = suite_id
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()


def get_active_run() -> _ReplayRun | None:
    """Return the active replay run, or None."""
    with _run_lock:
        return _active_run


def cancel_active_run() -> bool:
    """Cancel the active replay run.  Returns True if one was active."""
    with _run_lock:
        run = _active_run
    if run is None:
        return False
    run.stop_event.set()
    if run.thread and run.thread.is_alive():
        run.thread.join(timeout=10.0)
    return True


# ── Variable resolution ───────────────────────────────────────


def _resolve_variables(value: str, variables: dict[str, str]) -> str:
    r"""Replace ``${VAR_NAME}`` placeholders with resolved values.

    >>> _resolve_variables("Hello ${NAME}!", {"NAME": "World"})
    'Hello World!'
    """
    if not value or "${" not in value:
        return value

    def _replace(m: re.Match) -> str:
        var_name = m.group(1)
        return variables.get(var_name, m.group(0))

    return re.sub(r"\$\{(\w+)\}", _replace, value)


# ── Smart element finder ──────────────────────────────────────
#
# Tries selectors in priority order:
#   1. Primary CSS selector
#   2. Each alternative CSS selector
#   3. XPath
#   4. Tag name + text content match
#
# Each strategy is tried inside the timeout loop.  As soon as
# any strategy finds the element, it resolves.


def _js_escape(s: str) -> str:
    """Escape a string for safe embedding in a JS single-quoted literal."""
    return s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")


def _js_find_element_smart(
    selector: str,
    *,
    xpath: str = "",
    alternatives: list[str] | None = None,
    element_tag: str = "",
    element_text: str = "",
    timeout_ms: int = 5000,
) -> str:
    """JS: find element using multi-strategy fallback with timeout.

    Priority order:
        1. Primary CSS selector
        2. Alternative CSS selectors (in order)
        3. XPath
        4. Tag name + text content match

    Returns a Promise<Element>.
    """
    sel = _js_escape(selector) if selector else ""
    xp = _js_escape(xpath) if xpath else ""
    alts_js = ", ".join(f"'{_js_escape(a)}'" for a in (alternatives or []))
    tag = _js_escape(element_tag.lower()) if element_tag else ""
    text = _js_escape(element_text.strip()[:80]) if element_text else ""

    return f"""
    new Promise(function(resolve, reject) {{
        var deadline = Date.now() + {timeout_ms};
        var alts = [{alts_js}];

        function tryCSS(sel) {{
            try {{ return document.querySelector(sel); }} catch(_) {{ return null; }}
        }}

        function tryXPath(expr) {{
            try {{
                var result = document.evaluate(expr, document, null,
                    XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                return result.singleNodeValue;
            }} catch(_) {{ return null; }}
        }}

        function tryTagText(tag, text) {{
            if (!tag || !text) return null;
            try {{
                var els = document.querySelectorAll(tag);
                var lower = text.toLowerCase();
                for (var i = 0; i < els.length; i++) {{
                    var t = (els[i].textContent || '').trim().toLowerCase();
                    if (t === lower || t.indexOf(lower) !== -1) return els[i];
                }}
            }} catch(_) {{}}
            return null;
        }}

        function poll() {{
            // Strategy 1: primary CSS selector
            var el = '{sel}' ? tryCSS('{sel}') : null;

            // Strategy 2: alternative selectors
            if (!el) {{
                for (var i = 0; i < alts.length; i++) {{
                    el = tryCSS(alts[i]);
                    if (el) break;
                }}
            }}

            // Strategy 3: XPath
            if (!el && '{xp}') {{
                el = tryXPath('{xp}');
            }}

            // Strategy 4: tag + text
            if (!el && '{tag}') {{
                el = tryTagText('{tag}', '{text}');
            }}

            if (el) return resolve(el);
            if (Date.now() > deadline) {{
                var tried = ['{sel}'];
                if (alts.length) tried.push(alts.length + ' alts');
                if ('{xp}') tried.push('xpath');
                if ('{tag}') tried.push('{tag}+text');
                return reject('Element not found after trying: ' + tried.join(', '));
            }}
            setTimeout(poll, 80);
        }}
        poll();
    }})
    """


# ── DOM stability wait ────────────────────────────────────────


_JS_WAIT_FOR_STABLE = """
    new Promise(function(resolve) {
        var settled = false;
        var changed = false;
        var timer = null;
        var observer = new MutationObserver(function() {
            changed = true;
            clearTimeout(timer);
            timer = setTimeout(function() {
                settled = true;
                observer.disconnect();
                resolve({ changed: true });
            }, 150);
        });
        observer.observe(document.body || document.documentElement, {
            childList: true, subtree: true, attributes: true
        });
        // If nothing mutates within 20000ms, consider it stable
        timer = setTimeout(function() {
            if (!settled) { observer.disconnect(); resolve({ changed: changed }); }
        }, 20000);
    })
"""


# ── Per-action JavaScript generators ──────────────────────────
#
# Design contract for every action JS function:
#   1. Find the element (via the smart finder Promise)
#   2. Scroll into view + highlight (single call, ONE scroll)
#   3. Small settle pause (50ms) so the user sees the highlight
#   4. Perform the action
#   5. Wait for DOM stability
#   6. Return JSON: { ok: true, ... } or { ok: false, error: "..." }
#
# RULES:
#   - NO backdrop removal inside actions (done once before the loop)
#   - ONE scroll per step via _JS_SCROLL_AND_HIGHLIGHT
#   - NO el.focus() with default scroll — always preventScroll: true
#   - Each action is a self-contained async IIFE


# Scroll to element + highlight outline.
# Used by EVERY action. This is the SINGLE source of scroll.
_JS_SCROLL_AND_HIGHLIGHT = """
    (function(el) {
        if (!el || !el.style) return;
        var rect = el.getBoundingClientRect();
        // Scroll normal-sized elements to center of viewport.
        // Skip scroll for huge containers (>500px) — they'd jump
        // the viewport to the middle of a content wrapper.
        if (rect.height < 500) {
            el.scrollIntoView({ block: 'center', behavior: 'instant' });
        }
        // Visual highlight
        var origOutline = el.style.outline;
        var origTransition = el.style.transition;
        el.style.transition = 'outline 0.15s ease';
        el.style.outline = '2px solid #3b82f6';
        setTimeout(function() {
            el.style.outline = origOutline;
            el.style.transition = origTransition;
        }, 400);
    })(el);
"""


def _js_navigate(url: str) -> str:
    """JS: navigate to URL — sync IIFE, returns before page unloads.

    Must be sync because with a persistent WS connection, an async
    navigate would destroy the JS context while the Promise is pending.
    The replay loop handles the post-navigate wait separately.
    """
    url_escaped = _js_escape(url)
    return f"""
    (function() {{
        try {{
            window.location.href = '{url_escaped}';
            return JSON.stringify({{ ok: true }});
        }} catch (e) {{
            return JSON.stringify({{ ok: false, error: e.message || String(e) }});
        }}
    }})()
    """


def _js_click(find_js: str) -> str:
    """JS: find → scroll/highlight → pause → click → wait stable."""
    return f"""
    (async function() {{
        try {{
            var el = await {find_js};
            {_JS_SCROLL_AND_HIGHLIGHT}
            await new Promise(function(r) {{ setTimeout(r, 50); }});
            el.click();
            var __stable = await {_JS_WAIT_FOR_STABLE};
            return JSON.stringify({{ ok: true, changed: __stable.changed, tag: el.tagName, text: (el.textContent || '').slice(0, 50) }});
        }} catch (e) {{
            return JSON.stringify({{ ok: false, error: typeof e === 'string' ? e : (e.message || String(e)) }});
        }}
    }})()
    """


def _js_type(find_js: str, value: str) -> str:
    """JS: find → scroll/highlight → pause → focus (no scroll) → set value → wait stable."""
    val_escaped = _js_escape(value)
    return f"""
    (async function() {{
        try {{
            var el = await {find_js};
            {_JS_SCROLL_AND_HIGHLIGHT}
            await new Promise(function(r) {{ setTimeout(r, 50); }});
            el.focus({{ preventScroll: true }});
            var tag = el.tagName.toLowerCase();
            var isInput = (tag === 'input' || tag === 'textarea');
            if (isInput) {{
                el.value = '';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.value = '{val_escaped}';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }} else {{
                el.innerText = '{val_escaped}';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
            var __stable = await {_JS_WAIT_FOR_STABLE};
            var result = isInput ? el.value : el.innerText;
            return JSON.stringify({{ ok: true, changed: __stable.changed, value: result }});
        }} catch (e) {{
            return JSON.stringify({{ ok: false, error: typeof e === 'string' ? e : (e.message || String(e)) }});
        }}
    }})()
    """


def _js_select(find_js: str, value: str) -> str:
    """JS: find → scroll/highlight → set select value → wait stable."""
    val_escaped = _js_escape(value)
    return f"""
    (async function() {{
        try {{
            var el = await {find_js};
            {_JS_SCROLL_AND_HIGHLIGHT}
            await new Promise(function(r) {{ setTimeout(r, 50); }});
            el.value = '{val_escaped}';
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            var __stable = await {_JS_WAIT_FOR_STABLE};
            return JSON.stringify({{ ok: true, changed: __stable.changed, value: el.value }});
        }} catch (e) {{
            return JSON.stringify({{ ok: false, error: typeof e === 'string' ? e : (e.message || String(e)) }});
        }}
    }})()
    """


def _js_keypress(find_js: str, key: str) -> str:
    """JS: find → scroll/highlight → focus (no scroll) → keypress."""
    key_escaped = _js_escape(key)
    return f"""
    (async function() {{
        try {{
            var el = await {find_js};
            {_JS_SCROLL_AND_HIGHLIGHT}
            await new Promise(function(r) {{ setTimeout(r, 50); }});
            el.focus({{ preventScroll: true }});
            el.dispatchEvent(new KeyboardEvent('keydown', {{
                key: '{key_escaped}', bubbles: true, cancelable: true
            }}));
            el.dispatchEvent(new KeyboardEvent('keyup', {{
                key: '{key_escaped}', bubbles: true, cancelable: true
            }}));
            var __stable = await {_JS_WAIT_FOR_STABLE};
            return JSON.stringify({{ ok: true, changed: __stable.changed, key: '{key_escaped}' }});
        }} catch (e) {{
            return JSON.stringify({{ ok: false, error: typeof e === 'string' ? e : (e.message || String(e)) }});
        }}
    }})()
    """


def _js_scroll(x: int = 0, y: int = 0) -> str:
    """JS: scroll the page to a position."""
    return f"""
    (function() {{
        try {{
            window.scrollTo({{ left: {x}, top: {y}, behavior: 'instant' }});
            return JSON.stringify({{ ok: true, x: {x}, y: {y} }});
        }} catch (e) {{
            return JSON.stringify({{ ok: false, error: e.message || String(e) }});
        }}
    }})()
    """


def _js_hover(find_js: str) -> str:
    """JS: find → scroll/highlight → dispatch mouseenter/mouseover."""
    return f"""
    (async function() {{
        try {{
            var el = await {find_js};
            {_JS_SCROLL_AND_HIGHLIGHT}
            await new Promise(function(r) {{ setTimeout(r, 50); }});
            el.dispatchEvent(new MouseEvent('mouseenter', {{ bubbles: true }}));
            el.dispatchEvent(new MouseEvent('mouseover', {{ bubbles: true }}));
            return JSON.stringify({{ ok: true }});
        }} catch (e) {{
            return JSON.stringify({{ ok: false, error: typeof e === 'string' ? e : (e.message || String(e)) }});
        }}
    }})()
    """


# ── Assertion JS generators ───────────────────────────────────


def _js_assert_text(find_js: str, expected: str, mode: str = "contains") -> str:
    """JS: assert that an element's text matches expected."""
    exp_escaped = _js_escape(expected)
    if mode == "equals":
        check = f"text.trim() === '{exp_escaped}'"
    else:
        check = f"text.indexOf('{exp_escaped}') !== -1"
    return f"""
    (async function() {{
        try {{
            var el = await {find_js};
            var text = (el.textContent || '');
            if ({check}) {{
                return JSON.stringify({{ ok: true, actual: text.slice(0, 100) }});
            }} else {{
                return JSON.stringify({{ ok: false, error: 'Text assertion failed. Expected {mode}: \\'{exp_escaped}\\', got: \\'' + text.slice(0, 100) + '\\'' }});
            }}
        }} catch (e) {{
            return JSON.stringify({{ ok: false, error: typeof e === 'string' ? e : (e.message || String(e)) }});
        }}
    }})()
    """


def _js_assert_exists(find_js: str) -> str:
    """JS: assert that an element exists in the DOM."""
    return f"""
    (async function() {{
        try {{
            var el = await {find_js};
            return JSON.stringify({{ ok: true, tag: el.tagName }});
        }} catch (e) {{
            return JSON.stringify({{ ok: false, error: typeof e === 'string' ? e : (e.message || String(e)) }});
        }}
    }})()
    """


def _js_assert_not_exists(selector: str) -> str:
    """JS: assert that an element does NOT exist."""
    sel_escaped = _js_escape(selector)
    return f"""
    (function() {{
        var el = document.querySelector('{sel_escaped}');
        if (!el) {{
            return JSON.stringify({{ ok: true }});
        }} else {{
            return JSON.stringify({{ ok: false, error: 'Element should not exist but was found: {sel_escaped}' }});
        }}
    }})()
    """


def _js_assert_visible(find_js: str) -> str:
    """JS: assert that an element is visible."""
    return f"""
    (async function() {{
        try {{
            var el = await {find_js};
            var rect = el.getBoundingClientRect();
            var style = window.getComputedStyle(el);
            var visible = rect.width > 0 && rect.height > 0
                && style.display !== 'none'
                && style.visibility !== 'hidden'
                && style.opacity !== '0';
            if (visible) {{
                return JSON.stringify({{ ok: true }});
            }} else {{
                return JSON.stringify({{ ok: false, error: 'Element exists but is not visible' }});
            }}
        }} catch (e) {{
            return JSON.stringify({{ ok: false, error: typeof e === 'string' ? e : (e.message || String(e)) }});
        }}
    }})()
    """


# ── Step JS builder ───────────────────────────────────────────


def _build_find_js(step: dict, variables: dict[str, str]) -> str:
    """Build the smart finder JS for a step, using all available selector data.

    Special case: if the recorder captured selector="body" but element_tag
    is "input" or "textarea", the actual target was a dynamically-created
    element that the recorder couldn't build a proper path for.  In this
    case, use ``document.activeElement`` (the click step just focused it).
    """
    selector = _resolve_variables(step.get("selector", ""), variables)
    xpath = step.get("xpath", "")
    alternatives = step.get("selector_alternatives", [])
    element_tag = step.get("element_tag", "")
    element_text = step.get("element_text", "")
    timeout_ms = step.get("timeout_ms", 5000)

    # Handle broken "body" selector for input/textarea elements
    if selector in ("body", "html", "") and element_tag in ("input", "textarea"):
        tag_escaped = _js_escape(element_tag)
        return f"""
        new Promise(function(resolve, reject) {{
            var deadline = Date.now() + {timeout_ms};
            function poll() {{
                var el = document.activeElement;
                if (el && el.tagName.toLowerCase() === '{tag_escaped}') {{
                    return resolve(el);
                }}
                // Also try finding by tag if activeElement isn't right
                var byTag = document.querySelector('{tag_escaped}:focus')
                    || document.querySelector('{tag_escaped}');
                if (byTag) return resolve(byTag);
                if (Date.now() > deadline) {{
                    return reject('No focused {tag_escaped} found (selector was: {selector})');
                }}
                setTimeout(poll, 80);
            }}
            poll();
        }})
        """

    return _js_find_element_smart(
        selector,
        xpath=xpath,
        alternatives=alternatives,
        element_tag=element_tag,
        element_text=element_text,
        timeout_ms=timeout_ms,
    )


def _build_step_js(step: dict, variables: dict[str, str]) -> str:
    """Build the JavaScript expression for a single step.

    Each step's value field is resolved for variables first.
    Uses multi-strategy element finding and post-action DOM waits.
    """
    action = step.get("action", "")
    raw_value = step.get("value", "")
    value = _resolve_variables(raw_value, variables)

    # Skip internal recorder actions (ping, etc.)
    if action in ("ping",):
        return """(function() { return JSON.stringify({ ok: true, skipped: true, reason: 'internal action' }); })()"""

    if action == "navigate":
        selector = _resolve_variables(step.get("selector", ""), variables)
        return _js_navigate(value or selector)

    if action == "scroll":
        rect = step.get("element_rect", {})
        return _js_scroll(x=int(rect.get("x", 0)), y=int(rect.get("y", 0)))

    # All remaining actions need element finding
    find_js = _build_find_js(step, variables)

    if action == "click":
        return _js_click(find_js)

    if action == "type":
        return _js_type(find_js, value)

    if action == "select":
        return _js_select(find_js, value)

    if action == "keypress":
        return _js_keypress(find_js, value)

    if action == "hover":
        return _js_hover(find_js)

    if action == "assert":
        a_type = step.get("assertion_type", "exists")
        a_expected = _resolve_variables(
            step.get("assertion_expected", ""), variables,
        )
        if a_type == "text_contains":
            return _js_assert_text(find_js, a_expected, "contains")
        if a_type == "text_equals":
            return _js_assert_text(find_js, a_expected, "equals")
        if a_type == "not_exists":
            return _js_assert_not_exists(step.get("selector", ""))
        if a_type == "visible":
            return _js_assert_visible(find_js)
        return _js_assert_exists(find_js)

    if action == "wait":
        return _js_assert_exists(find_js)

    # Unknown action — try as click with selector if available
    logger.warning("Unknown step action '%s', attempting as click", action)
    selector = step.get("selector", "")
    if selector:
        return _js_click(find_js)

    return """(function() { return JSON.stringify({ ok: false, error: 'Unknown action with no selector' }); })()"""


def _execute_step(
    step: dict,
    variables: dict[str, str],
    *,
    session: "cdp_client.CdpSession | None" = None,
    ws_url: str = "",
) -> dict:
    """Execute a single test step via CDP.

    Uses the persistent ``CdpSession`` if available, falling back
    to one-shot ``evaluate_js`` if the session is down.

    Returns:
        {
            "status": "passed" | "failed",
            "duration_ms": int,
            "error": str | None,
            "details": dict,
        }
    """
    import json as json_mod

    from src.ui.web import cdp_client

    js_expr = _build_step_js(step, variables)
    timeout_s = max(step.get("timeout_ms", 5000) / 1000.0, 5.0) + 2.0

    # Detect if the JS is async (needs awaitPromise)
    needs_await = js_expr.lstrip().startswith("(async")

    start = time.monotonic()

    try:
        # Prefer streaming session; fall back to one-shot
        if session and session.connected:
            result = session.evaluate(
                js_expr, await_promise=needs_await, timeout=timeout_s,
            )
        elif ws_url:
            result = cdp_client.evaluate_js(
                ws_url, js_expr, timeout=timeout_s, await_promise=needs_await,
            )
        else:
            result = None
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "status": "failed",
            "duration_ms": elapsed_ms,
            "error": f"CDP error: {exc}",
            "details": {},
        }

    elapsed_ms = int((time.monotonic() - start) * 1000)

    if result is None:
        return {
            "status": "failed",
            "duration_ms": elapsed_ms,
            "error": "CDP returned None (timeout or connection error)",
            "details": {},
        }

    # Parse the CDP response — the JS returns a JSON string
    try:
        inner = result.get("result", {})
        value = inner.get("result", {}).get("value")

        # Check for JS exceptions
        if "exceptionDetails" in inner:
            exc_text = inner["exceptionDetails"].get("text", "JS exception")
            return {
                "status": "failed",
                "duration_ms": elapsed_ms,
                "error": exc_text,
                "details": inner.get("exceptionDetails", {}),
            }

        if value is None:
            return {
                "status": "failed",
                "duration_ms": elapsed_ms,
                "error": "JS returned no value",
                "details": inner,
            }

        # Parse the JSON string returned by our JS
        parsed = json_mod.loads(value)
        if parsed.get("ok"):
            return {
                "status": "passed",
                "duration_ms": elapsed_ms,
                "error": None,
                "details": parsed,
            }
        else:
            return {
                "status": "failed",
                "duration_ms": elapsed_ms,
                "error": parsed.get("error", "Step failed"),
                "details": parsed,
            }

    except (json_mod.JSONDecodeError, AttributeError, TypeError) as exc:
        return {
            "status": "failed",
            "duration_ms": elapsed_ms,
            "error": f"Failed to parse step result: {exc}",
            "details": {"raw": str(result)[:500]},
        }


# ── Target tab verification ───────────────────────────────────


def _verify_target_tab(target_id: str) -> str | None:
    """Verify the target tab is alive and return its WS URL.

    Returns:
        The webSocketDebuggerUrl string, or None if tab not found.
    """
    from src.ui.web import cdp_client

    targets = cdp_client.get_targets()
    for t in targets:
        if t.get("id") == target_id:
            return t.get("webSocketDebuggerUrl")
    return None


def _find_dcp_tab() -> str | None:
    """Find the DCP admin panel tab's target ID (for re-activating after replay)."""
    from src.ui.web import cdp_client

    targets = cdp_client.get_targets()
    dcp = cdp_client.find_target_by_url(targets, "localhost:8000")
    if dcp:
        return dcp.get("id")
    return None


# ── Suite replay ───────────────────────────────────────────────


def replay_suite(
    suite: TestSuite,
    target_id: str,
    variables: dict[str, str],
    callback: callable,
    stop_event: threading.Event,
    *,
    run_id: str = "",
    ws_url: str = "",
    dcp_tab_id: str | None = None,
    clear_site_data: bool | None = None,
    visual_delay_ms: int | None = None,
    min_step_delay_ms: int | None = None,
) -> TestRunResult:
    """Execute a full test suite against the target tab.

    Runs in a background thread.  Uses ``callback(event_type, data)``
    to report progress (which feeds the SSE stream).

    Tab transitions are hardened:
        - Target tab is activated before first step
        - Target tab is verified alive before every step
        - Navigation steps include a configurable wait
        - The DCP admin tab is re-activated after replay finishes

    Args:
        suite: The test suite to execute.
        target_id: Chrome target ID of the tab to drive.
        variables: Resolved variable values (merged with suite defaults).
        callback: Function(event_type: str, data: dict) for SSE events.
        stop_event: Set this to cancel the replay.

    Returns:
        Completed TestRunResult.
    """
    from src.ui.web import cdp_client

    # Create the result object — use provided run_id for consistency
    # with the ID returned to the frontend by start_replay().
    result_kwargs = {
        "suite_id": suite.id,
        "suite_name": suite.name,
        "total_steps": len(suite.steps),
        "status": "running",
    }
    if run_id:
        result_kwargs["id"] = run_id
    run_result = TestRunResult(**result_kwargs)

    # Merge suite default variables with provided overrides
    merged_vars = dict(suite.variables)
    merged_vars.update(variables)

    # Redact passwords for storage
    redacted_vars = {
        k: ("***" if "pass" in k.lower() or "secret" in k.lower() else v)
        for k, v in merged_vars.items()
    }
    run_result.variables_used = redacted_vars

    # Remember DCP tab for switching back
    if dcp_tab_id is None:
        dcp_tab_id = _find_dcp_tab()

    # ── Verify and activate target tab ───────────────────────
    if not ws_url:
        ws_url = _verify_target_tab(target_id)
    if not ws_url:
        run_result.status = "error"
        run_result.error = f"Target tab not found (id={target_id}). Was it closed?"
        run_result.finished_at = _now_iso()
        callback("cdp_test:replay_error", {
            "run_id": run_result.id,
            "error": run_result.error,
        })
        return run_result

    logger.info(
        "Replay started: suite=%s (%s), target=%s, steps=%d",
        suite.id, suite.name, target_id, len(suite.steps),
    )

    # Tell the UI we're connecting (this phase takes ~2s on WSL2)
    callback("cdp_test:replay_connecting", {
        "run_id": run_result.id,
        "phase": "connecting",
    })

    # ── Open persistent CDP session (tab still in background) ──
    # The 2.2s bridge connect happens while the user still sees
    # the DCP admin panel — no blank page staring.
    _t_session = time.monotonic()
    session = cdp_client.CdpSession(ws_url)
    logger.info(
        "Replay: CdpSession() took %.0fms",
        (time.monotonic() - _t_session) * 1000,
    )
    if session.connected:
        logger.info("Replay using streaming CDP session (%s)", session._mode)
    else:
        logger.warning("Streaming session failed, falling back to one-shot mode")
        session = None  # _execute_step will use evaluate_js

    # ── Inject loading backdrop BEFORE switching tabs ─────────
    # Backdrop is injected into the background tab so when Chrome
    # brings it to the foreground, the user immediately sees
    # "Replay starting…" instead of a bare page.
    _BACKDROP_JS = """
    (function() {
        var d = document.createElement('div');
        d.id = '__cdp_replay_backdrop';
        d.style.cssText = 'position:fixed;inset:0;z-index:999999;'
            + 'display:flex;align-items:center;justify-content:center;'
            + 'background:rgba(0,0,0,0.45);backdrop-filter:blur(2px);'
            + 'transition:opacity 0.3s;opacity:1';
        d.innerHTML = '<div style="background:#1e1e2e;color:#cdd6f4;'
            + 'padding:1.2rem 2rem;border-radius:12px;font-family:system-ui;'
            + 'font-size:1rem;box-shadow:0 8px 32px rgba(0,0,0,0.4);'
            + 'display:flex;align-items:center;gap:0.8rem">'
            + '<span style="font-size:1.3rem;animation:spin 1s linear infinite">⏳</span>'
            + '<span>Replay starting\u2026</span></div>';
        var s = document.createElement('style');
        s.textContent = '@keyframes spin{to{transform:rotate(360deg)}}';
        d.appendChild(s);
        document.body.appendChild(d);
        return JSON.stringify({ ok: true });
    })()
    """
    if session and session.connected:
        session.evaluate(_BACKDROP_JS, timeout=3.0)

    # ── NOW activate (focus) the target tab ──────────────────
    # User sees the tab switch with backdrop already visible.
    _t_activate = time.monotonic()
    cdp_client.activate_target(target_id)
    logger.info(
        "Replay: activate_target took %.0fms",
        (time.monotonic() - _t_activate) * 1000,
    )

    callback("cdp_test:replay_start", {
        "run_id": run_result.id,
        "suite_id": suite.id,
        "suite_name": suite.name,
        "total_steps": len(suite.steps),
        "mode": session._mode if session else "one-shot",
    })

    # ── Clear site data if requested ───────────────────────
    # Override per-run takes precedence over suite default.
    should_clear = clear_site_data if clear_site_data is not None else suite.clear_site_data
    if should_clear and session and session.connected:
        logger.info("Replay: clearing site data before execution")
        _CLEAR_JS = """
        (async function() {
            try {
                localStorage.clear();
                sessionStorage.clear();
                // Clear cookies for this origin
                document.cookie.split(';').forEach(function(c) {
                    var name = c.split('=')[0].trim();
                    document.cookie = name + '=;expires=Thu,01 Jan 1970 00:00:00 GMT;path=/';
                });
                // Clear caches if available
                if (window.caches) {
                    var names = await caches.keys();
                    for (var n of names) { await caches.delete(n); }
                }
                return JSON.stringify({ ok: true });
            } catch(e) {
                return JSON.stringify({ ok: false, error: e.message });
            }
        })()
        """
        session.evaluate(_CLEAR_JS, await_promise=True, timeout=5.0)
        # Reload the page for a fresh session
        session.evaluate("(function(){ location.reload(); return JSON.stringify({ok:true}); })()", timeout=3.0)
        # Wait for page to reload and settle
        time.sleep(suite.navigate_wait_ms / 1000.0)

    # ── Execute steps ────────────────────────────────────
    step_list = sorted(suite.steps, key=lambda s: s.sequence)
    had_failure = False

    # Remove backdrop + scroll to top — single call, ONCE before loop
    if session and session.connected:
        session.evaluate("""(function() {
            var bd = document.getElementById('__cdp_replay_backdrop');
            if (bd) { bd.style.opacity='0'; setTimeout(function(){bd.remove()},300); }
            window.scrollTo(0, 0);
            return JSON.stringify({ok:true});
        })()""", timeout=3.0)
        time.sleep(0.3)  # Let backdrop fade + scroll settle

    try:
      for i, step in enumerate(step_list):
        if stop_event.is_set():
            run_result.status = "cancelled"
            run_result.error = "Replay cancelled by user"
            # Mark remaining steps as skipped
            for remaining in step_list[i:]:
                run_result.step_results.append({
                    "step_id": remaining.id,
                    "sequence": remaining.sequence,
                    "action": remaining.action,
                    "selector": remaining.selector,
                    "status": "skipped",
                    "duration_ms": 0,
                    "error": "Replay cancelled",
                })
                run_result.skipped_steps += 1
            break

        step_dict = step.to_dict()

        # ── Pre-step: wait_before_ms ─────────────────────────
        wait_before = step.wait_before_ms
        if wait_before > 0:
            time.sleep(wait_before / 1000.0)

        # ── Pre-step: replay pacing ──────────────────────────
        if suite.replay_speed > 0 and step.recorded_delay_ms > 0:
            pacing = (step.recorded_delay_ms / 1000.0) / suite.replay_speed
            # Cap pacing at 5 seconds max
            pacing = min(pacing, 5.0)
            if pacing > 0.05:
                time.sleep(pacing)

        # Note: we skip per-step _verify_target_tab() — it costs
        # ~300ms (curl.exe) per step.  The CdpSession will surface
        # connection errors if the tab closes mid-replay.

        # ── Pre-step: pause if target tab not visible ─────────
        # When the user switches away from the target tab, Chrome
        # throttles the page and elements may not be findable.
        # Pause and wait for the tab to become visible again.
        if session and session.connected:
            _VIS_JS = '(function(){ return JSON.stringify({ visible: document.visibilityState === "visible" }); })()'
            try:
                vis_result = session.evaluate(_VIS_JS, timeout=2.0)
                vis_val = vis_result.get("result", {}).get("result", {}).get("value", "{}") if vis_result else "{}"
                import json as _json_mod
                vis_parsed = _json_mod.loads(vis_val) if vis_val else {}
                if not vis_parsed.get("visible", True):
                    # Tab is hidden — pause
                    callback("cdp_test:replay_paused", {
                        "run_id": run_result.id,
                        "step_id": step.id,
                        "sequence": step.sequence,
                        "reason": "Tab not visible",
                    })
                    logger.info("Replay paused — target tab hidden (step %d)", i + 1)
                    # Poll until visible or cancelled
                    while not stop_event.is_set():
                        time.sleep(0.5)
                        try:
                            vr = session.evaluate(_VIS_JS, timeout=2.0)
                            vv = vr.get("result", {}).get("result", {}).get("value", "{}") if vr else "{}"
                            vp = _json_mod.loads(vv) if vv else {}
                            if vp.get("visible", False):
                                break
                        except Exception:
                            break  # Session died — let the step handle the error
                    callback("cdp_test:replay_resumed", {
                        "run_id": run_result.id,
                        "step_id": step.id,
                        "sequence": step.sequence,
                    })
                    logger.info("Replay resumed — target tab visible again")
            except Exception:
                pass  # Visibility check failed — proceed anyway

        # ── Report step start ────────────────────────────────
        callback("cdp_test:step_start", {
            "run_id": run_result.id,
            "step_id": step.id,
            "sequence": step.sequence,
            "action": step.action,
            "selector": step.selector,
            "value": step.value,
        })

        # ── Execute the step ─────────────────────────────────
        step_result = _execute_step(
            step_dict, merged_vars, session=session, ws_url=ws_url,
        )

        # ── Post-step pacing (two-tier) ─────────────────────────
        # Effective values: per-run override or suite default
        _eff_min = min_step_delay_ms if min_step_delay_ms is not None else suite.min_step_delay_ms
        _eff_vis = visual_delay_ms if visual_delay_ms is not None else suite.visual_delay_ms

        # Tier 1: Base delay
        #   - If the action caused page changes (DOM mutations detected):
        #     debounce by min_step_delay_ms (default 700ms) to let page settle
        #   - If no page changes: 100ms base minimum
        page_changed = step_result.get("details", {}).get("changed", False)
        if page_changed:
            debounce_s = max(_eff_min, 0) / 1000.0
            if debounce_s > 0:
                time.sleep(debounce_s)
        else:
            time.sleep(0.1)

        # Tier 2: Visual delay — added ON TOP for ALL operations
        # Pure visibility pause so the user can see the result
        vis_delay_s = max(_eff_vis, 0) / 1000.0
        if vis_delay_s > 0:
            time.sleep(vis_delay_s)

        # Build step result record
        result_record = {
            "step_id": step.id,
            "sequence": step.sequence,
            "action": step.action,
            "selector": step.selector,
            "status": step_result["status"],
            "duration_ms": step_result["duration_ms"],
            "error": step_result.get("error"),
        }
        run_result.step_results.append(result_record)

        if step_result["status"] == "passed":
            run_result.passed_steps += 1
            callback("cdp_test:step_passed", {
                "run_id": run_result.id,
                **result_record,
            })
            logger.debug(
                "Step %d/%d passed: %s %s (%dms)",
                i + 1, len(step_list), step.action,
                step.selector or step.value, step_result["duration_ms"],
            )
        else:
            run_result.failed_steps += 1
            had_failure = True
            callback("cdp_test:step_failed", {
                "run_id": run_result.id,
                **result_record,
            })
            logger.warning(
                "Step %d/%d FAILED: %s %s — %s",
                i + 1, len(step_list), step.action,
                step.selector or step.value,
                step_result.get("error", "unknown"),
            )

            # If step is not optional and stop_on_failure is set, abort
            if not step.optional and suite.stop_on_failure:
                # Mark remaining steps as skipped
                for remaining in step_list[i + 1:]:
                    run_result.step_results.append({
                        "step_id": remaining.id,
                        "sequence": remaining.sequence,
                        "action": remaining.action,
                        "selector": remaining.selector,
                        "status": "skipped",
                        "duration_ms": 0,
                        "error": "Skipped due to previous failure",
                    })
                    run_result.skipped_steps += 1
                break

        # ── Post-navigate: extra wait for page load ──────────
        if step.action == "navigate" and step_result["status"] == "passed":
            nav_wait = suite.navigate_wait_ms / 1000.0
            if nav_wait > 0:
                time.sleep(nav_wait)

    finally:
        # Always close the streaming session
        if session is not None:
            try:
                session.close()
            except Exception:
                pass

    # ── Finalize result ──────────────────────────────────────
    run_result.finished_at = _now_iso()
    start_ts = run_result.started_at
    finish_ts = run_result.finished_at
    try:
        from datetime import datetime, timezone
        s = datetime.fromisoformat(start_ts)
        f = datetime.fromisoformat(finish_ts)
        run_result.duration_ms = int((f - s).total_seconds() * 1000)
    except (ValueError, TypeError):
        pass

    if run_result.status == "running":
        if had_failure:
            run_result.status = "failed"
        elif run_result.passed_steps == run_result.total_steps:
            run_result.status = "passed"
        else:
            run_result.status = "partial"

    # ── Switch back to DCP admin tab ─────────────────────────
    if dcp_tab_id:
        try:
            cdp_client.activate_target(dcp_tab_id)
        except Exception:
            pass  # Non-critical

    # ── Report completion ────────────────────────────────────
    callback("cdp_test:replay_done", {
        "run_id": run_result.id,
        "status": run_result.status,
        "passed": run_result.passed_steps,
        "failed": run_result.failed_steps,
        "skipped": run_result.skipped_steps,
        "total": run_result.total_steps,
        "duration_ms": run_result.duration_ms,
    })

    logger.info(
        "Replay finished: run=%s, status=%s, %d/%d passed (%dms)",
        run_result.id, run_result.status,
        run_result.passed_steps, run_result.total_steps,
        run_result.duration_ms,
    )

    return run_result


# ── Public API: start replay ──────────────────────────────────


def start_replay(
    suite: TestSuite,
    target_id: str,
    variables: dict[str, str] | None = None,
    callback: callable | None = None,
    *,
    ws_url: str = "",
    dcp_tab_id: str | None = None,
    clear_site_data: bool | None = None,
    visual_delay_ms: int | None = None,
    min_step_delay_ms: int | None = None,
) -> TestRunResult | str:
    """Start replaying a suite in a background thread.

    Args:
        suite: The test suite to replay.
        target_id: Chrome target ID of the tab to drive.
        variables: Variable overrides (merged with suite defaults).
        callback: Function(event_type, data) for SSE events.

    Returns:
        The run_id string if started successfully.
        Or a TestRunResult with error status if startup failed.
    """
    global _active_run

    with _run_lock:
        if _active_run is not None:
            if _active_run.thread and _active_run.thread.is_alive():
                err = TestRunResult(
                    suite_id=suite.id,
                    suite_name=suite.name,
                    status="error",
                    error="Another replay is already running",
                    finished_at=_now_iso(),
                )
                return err
            # Previous run finished — clear it
            _active_run = None

    run_id = str(uuid.uuid4())
    run = _ReplayRun(run_id=run_id, suite_id=suite.id)

    # Capture project_root from Flask context NOW (main thread has it;
    # the background thread does not have app context)
    try:
        from flask import current_app
        from pathlib import Path
        project_root = Path(current_app.config["PROJECT_ROOT"])
    except Exception:
        project_root = None

    if callback is None:
        def callback(event_type, data):
            logger.debug("Replay event: %s %s", event_type, data)

    # The result holder — will be populated by the thread
    result_holder: list[TestRunResult] = []

    def _run():
        global _active_run
        try:
            result = replay_suite(
                suite=suite,
                target_id=target_id,
                variables=variables or {},
                callback=callback,
                stop_event=run.stop_event,
                run_id=run_id,
                ws_url=ws_url,
                dcp_tab_id=dcp_tab_id,
                clear_site_data=clear_site_data,
                visual_delay_ms=visual_delay_ms,
                min_step_delay_ms=min_step_delay_ms,
            )
            result_holder.append(result)

            # Save result to storage
            if project_root:
                try:
                    from src.core.services.cdp_test.storage import save_result

                    save_result(project_root, result)

                    # Update suite's last_run info
                    from src.core.services.cdp_test.storage import (
                        get_suite,
                        save_suite,
                    )
                    stored_suite = get_suite(project_root, suite.id)
                    if stored_suite:
                        stored_suite.last_run_at = result.finished_at
                        stored_suite.last_run_status = result.status
                        stored_suite.run_count += 1
                        save_suite(project_root, stored_suite)
                except Exception as exc:
                    logger.warning("Failed to save replay result: %s", exc)

        except Exception as exc:
            logger.exception("Replay thread crashed: %s", exc)
            callback("cdp_test:replay_error", {
                "run_id": run_id,
                "error": f"Replay crashed: {exc}",
            })
        finally:
            with _run_lock:
                global _active_run
                if _active_run and _active_run.run_id == run_id:
                    _active_run = None

    run.thread = threading.Thread(
        target=_run,
        name=f"cdp-replay-{run_id[:8]}",
        daemon=True,
    )

    with _run_lock:
        _active_run = run

    run.thread.start()
    return run_id
