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
    """JS: assert that an element's text matches expected.

    Supported modes:
        equals, contains, not_contains, starts_with, ends_with,
        matches (regex), one_of (pipe-delimited alternatives),
        empty, not_empty.
    """
    exp_escaped = _js_escape(expected)
    if mode == "equals":
        check = f"text.trim() === '{exp_escaped}'"
    elif mode == "not_contains":
        check = f"text.indexOf('{exp_escaped}') === -1"
    elif mode == "starts_with":
        check = f"text.trimStart().indexOf('{exp_escaped}') === 0"
    elif mode == "ends_with":
        check = f"text.trimEnd().slice(-{len(expected)}) === '{exp_escaped}'"
    elif mode == "matches":
        # expected is a regex pattern — construct RegExp in JS
        check = f"new RegExp('{exp_escaped}').test(text)"
    elif mode == "one_of":
        # expected is pipe-delimited: "val1|val2|val3"
        alternatives = expected.split("|")
        alt_js = ", ".join(f"'{_js_escape(a.strip())}'" for a in alternatives)
        check = f"[{alt_js}].indexOf(text.trim()) !== -1"
    elif mode == "empty":
        check = "text.trim() === ''"
    elif mode == "not_empty":
        check = "text.trim() !== ''"
    else:
        # Default: contains
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


def _js_assert_value(find_js: str, expected: str, mode: str = "equals") -> str:
    """JS: assert that an input/textarea/select element's value matches expected.

    Supported modes: equals, contains, empty, not_empty.
    """
    exp_escaped = _js_escape(expected)
    if mode == "equals":
        check = f"val === '{exp_escaped}'"
    elif mode == "contains":
        check = f"val.indexOf('{exp_escaped}') !== -1"
    elif mode == "empty":
        check = "val === ''"
    elif mode == "not_empty":
        check = "val !== ''"
    else:
        check = f"val === '{exp_escaped}'"
    return f"""
    (async function() {{
        try {{
            var el = await {find_js};
            var val = (el.value || '');
            if ({check}) {{
                return JSON.stringify({{ ok: true, actual: val.slice(0, 100) }});
            }} else {{
                return JSON.stringify({{ ok: false, error: 'Value assertion failed. Expected {mode}: \\'{exp_escaped}\\', got: \\'' + val.slice(0, 100) + '\\'' }});
            }}
        }} catch (e) {{
            return JSON.stringify({{ ok: false, error: typeof e === 'string' ? e : (e.message || String(e)) }});
        }}
    }})()
    """


def _js_assert_attribute(
    find_js: str, attr_name: str, expected: str, mode: str = "equals",
) -> str:
    """JS: assert on an element's attribute value.

    Supported modes: equals, contains, attr_exists, attr_not_exists.
    """
    attr_escaped = _js_escape(attr_name)
    exp_escaped = _js_escape(expected)
    if mode == "equals":
        check = f"attrVal === '{exp_escaped}'"
    elif mode == "contains":
        check = f"attrVal !== null && attrVal.indexOf('{exp_escaped}') !== -1"
    elif mode == "attr_exists":
        check = "attrVal !== null"
    elif mode == "attr_not_exists":
        check = "attrVal === null"
    else:
        check = f"attrVal === '{exp_escaped}'"
    return f"""
    (async function() {{
        try {{
            var el = await {find_js};
            var attrVal = el.getAttribute('{attr_escaped}');
            if ({check}) {{
                return JSON.stringify({{ ok: true, actual: attrVal }});
            }} else {{
                return JSON.stringify({{ ok: false, error: 'Attribute assertion failed. Attribute \\'{attr_escaped}\\' expected {mode}: \\'{exp_escaped}\\', got: \\'' + String(attrVal) + '\\'' }});
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


def _js_assert_state(find_js: str, mode: str) -> str:
    """JS: assert on an element's boolean state.

    Supported modes: hidden, enabled, disabled, checked, not_checked,
    focused, selected.
    """
    if mode == "hidden":
        check = (
            "!(rect.width > 0 && rect.height > 0 "
            "&& style.display !== 'none' "
            "&& style.visibility !== 'hidden' "
            "&& style.opacity !== '0')"
        )
        # hidden needs computed style + rect
        return f"""
    (async function() {{
        try {{
            var el = await {find_js};
            var rect = el.getBoundingClientRect();
            var style = window.getComputedStyle(el);
            var hidden = {check};
            if (hidden) {{
                return JSON.stringify({{ ok: true }});
            }} else {{
                return JSON.stringify({{ ok: false, error: 'Element is visible but expected hidden' }});
            }}
        }} catch (e) {{
            return JSON.stringify({{ ok: false, error: typeof e === 'string' ? e : (e.message || String(e)) }});
        }}
    }})()
    """
    # All other modes are simple property checks
    checks = {
        "enabled": ("!el.disabled", "Element is disabled but expected enabled"),
        "disabled": ("el.disabled === true", "Element is enabled but expected disabled"),
        "checked": ("el.checked === true", "Element is not checked but expected checked"),
        "not_checked": ("!el.checked", "Element is checked but expected not checked"),
        "focused": (
            "document.activeElement === el",
            "Element is not focused but expected focused",
        ),
        "selected": ("el.selected === true", "Element is not selected but expected selected"),
    }
    js_check, fail_msg = checks.get(mode, ("true", f"Unknown state mode: {mode}"))
    return f"""
    (async function() {{
        try {{
            var el = await {find_js};
            if ({js_check}) {{
                return JSON.stringify({{ ok: true }});
            }} else {{
                return JSON.stringify({{ ok: false, error: '{_js_escape(fail_msg)}' }});
            }}
        }} catch (e) {{
            return JSON.stringify({{ ok: false, error: typeof e === 'string' ? e : (e.message || String(e)) }});
        }}
    }})()
    """


def _js_assert_css(
    find_js: str, expected: str, mode: str = "class_present",
    attr_name: str = "",
) -> str:
    """JS: assert on CSS classes or computed style properties.

    Supported modes: class_present, class_absent, property_equals.
    For property_equals, attr_name is the CSS property name.
    """
    exp_escaped = _js_escape(expected)
    attr_escaped = _js_escape(attr_name)
    if mode == "class_present":
        return f"""
    (async function() {{
        try {{
            var el = await {find_js};
            if (el.classList.contains('{exp_escaped}')) {{
                return JSON.stringify({{ ok: true }});
            }} else {{
                return JSON.stringify({{ ok: false, error: 'Element does not have class \\'{exp_escaped}\\'. Classes: ' + el.className }});
            }}
        }} catch (e) {{
            return JSON.stringify({{ ok: false, error: typeof e === 'string' ? e : (e.message || String(e)) }});
        }}
    }})()
    """
    if mode == "class_absent":
        return f"""
    (async function() {{
        try {{
            var el = await {find_js};
            if (!el.classList.contains('{exp_escaped}')) {{
                return JSON.stringify({{ ok: true }});
            }} else {{
                return JSON.stringify({{ ok: false, error: 'Element should not have class \\'{exp_escaped}\\' but does' }});
            }}
        }} catch (e) {{
            return JSON.stringify({{ ok: false, error: typeof e === 'string' ? e : (e.message || String(e)) }});
        }}
    }})()
    """
    # property_equals — check getComputedStyle
    return f"""
    (async function() {{
        try {{
            var el = await {find_js};
            var val = window.getComputedStyle(el)['{attr_escaped}'];
            if (val === '{exp_escaped}') {{
                return JSON.stringify({{ ok: true, actual: val }});
            }} else {{
                return JSON.stringify({{ ok: false, error: 'CSS property \\'{attr_escaped}\\' expected \\'{exp_escaped}\\', got: \\'' + val + '\\'' }});
            }}
        }} catch (e) {{
            return JSON.stringify({{ ok: false, error: typeof e === 'string' ? e : (e.message || String(e)) }});
        }}
    }})()
    """


def _js_assert_html(find_js: str, expected: str, mode: str = "html_contains") -> str:
    """JS: assert on innerHTML content or children count.

    Supported modes: html_contains, html_equals,
    children_count, children_count_gt, children_count_lt.
    """
    exp_escaped = _js_escape(expected)
    if mode in ("children_count", "children_count_gt", "children_count_lt"):
        # expected is an integer string
        op = {"children_count": "===", "children_count_gt": ">", "children_count_lt": "<"}
        return f"""
    (async function() {{
        try {{
            var el = await {find_js};
            var count = el.children.length;
            if (count {op[mode]} {int(expected)}) {{
                return JSON.stringify({{ ok: true, actual: count }});
            }} else {{
                return JSON.stringify({{ ok: false, error: 'Children count: ' + count + ', expected {mode.replace("children_count", "").replace("_", "") or "=="} {expected}' }});
            }}
        }} catch (e) {{
            return JSON.stringify({{ ok: false, error: typeof e === 'string' ? e : (e.message || String(e)) }});
        }}
    }})()
    """
    # html_contains / html_equals
    if mode == "html_equals":
        check = f"html.trim() === '{exp_escaped}'"
    else:
        check = f"html.indexOf('{exp_escaped}') !== -1"
    return f"""
    (async function() {{
        try {{
            var el = await {find_js};
            var html = (el.innerHTML || '');
            if ({check}) {{
                return JSON.stringify({{ ok: true, actual: html.slice(0, 200) }});
            }} else {{
                return JSON.stringify({{ ok: false, error: 'HTML assertion failed. Expected {mode}: got: ' + html.slice(0, 200) }});
            }}
        }} catch (e) {{
            return JSON.stringify({{ ok: false, error: typeof e === 'string' ? e : (e.message || String(e)) }});
        }}
    }})()
    """


def _js_assert_count(selector: str, expected: str, mode: str = "count_equals") -> str:
    """JS: assert on the count of elements matching a selector.

    Supported modes: count_equals, count_gt, count_lt, count_gte.
    Uses querySelectorAll — does NOT need find_js (operates on selector).
    """
    sel_escaped = _js_escape(selector)
    op = {
        "count_equals": "===",
        "count_gt": ">",
        "count_lt": "<",
        "count_gte": ">=",
    }
    operator = op.get(mode, "===")
    return f"""
    (function() {{
        var els = document.querySelectorAll('{sel_escaped}');
        var count = els.length;
        if (count {operator} {int(expected)}) {{
            return JSON.stringify({{ ok: true, actual: count }});
        }} else {{
            return JSON.stringify({{ ok: false, error: 'Count assertion failed. Found ' + count + ' elements matching \\'{sel_escaped}\\', expected {mode.replace("count_", "")} {expected}' }});
        }}
    }})()
    """


def _js_assert_numeric(find_js: str, expected: str, mode: str = "numeric_equals") -> str:
    """JS: assert on an element's text parsed as a number.

    Supported modes: numeric_equals, numeric_gt, numeric_lt, numeric_between.
    For numeric_between, expected is "min,max".
    """
    if mode == "numeric_between":
        parts = expected.split(",")
        lo, hi = parts[0].strip(), parts[1].strip()
        check = f"num >= {lo} && num <= {hi}"
        label = f"between {lo} and {hi}"
    else:
        op = {"numeric_equals": "===", "numeric_gt": ">", "numeric_lt": "<"}
        operator = op.get(mode, "===")
        check = f"num {operator} {expected}"
        label = f"{mode.replace('numeric_', '')} {expected}"
    return f"""
    (async function() {{
        try {{
            var el = await {find_js};
            var raw = (el.textContent || el.value || '').trim();
            var num = parseFloat(raw);
            if (isNaN(num)) {{
                return JSON.stringify({{ ok: false, error: 'Cannot parse as number: ' + raw.slice(0, 50) }});
            }}
            if ({check}) {{
                return JSON.stringify({{ ok: true, actual: num }});
            }} else {{
                return JSON.stringify({{ ok: false, error: 'Numeric assertion failed. Got ' + num + ', expected {label}' }});
            }}
        }} catch (e) {{
            return JSON.stringify({{ ok: false, error: typeof e === 'string' ? e : (e.message || String(e)) }});
        }}
    }})()
    """


def _js_assert_page(expected: str, mode: str = "url_equals") -> str:
    """JS: assert on page-level properties (URL, title). No element needed.

    Supported modes: url_equals, url_contains, title_equals, title_contains.
    """
    exp_escaped = _js_escape(expected)
    sources = {
        "url_equals": "window.location.href",
        "url_contains": "window.location.href",
        "title_equals": "document.title",
        "title_contains": "document.title",
    }
    source = sources.get(mode, "window.location.href")
    if mode in ("url_equals", "title_equals"):
        check = f"val === '{exp_escaped}'"
    else:
        check = f"val.indexOf('{exp_escaped}') !== -1"
    return f"""
    (function() {{
        var val = {source};
        if ({check}) {{
            return JSON.stringify({{ ok: true, actual: val }});
        }} else {{
            return JSON.stringify({{ ok: false, error: 'Page assertion failed. {mode}: expected \\'{exp_escaped}\\', got: \\'' + val + '\\'' }});
        }}
    }})()
    """


def _js_assert_captured(
    find_js: str, captured_value: str, mode: str = "captured_equals",
) -> str:
    """JS: assert current element text against a previously captured value.

    The captured_value is injected from Python's captures context dict.
    Supported modes: captured_equals, captured_contains,
    captured_changed, captured_unchanged.
    """
    cv_escaped = _js_escape(captured_value)
    if mode == "captured_equals":
        check = f"current === '{cv_escaped}'"
    elif mode == "captured_contains":
        check = f"current.indexOf('{cv_escaped}') !== -1"
    elif mode == "captured_changed":
        check = f"current !== '{cv_escaped}'"
    elif mode == "captured_unchanged":
        check = f"current === '{cv_escaped}'"
    else:
        check = f"current === '{cv_escaped}'"
    return f"""
    (async function() {{
        try {{
            var el = await {find_js};
            var current = (el.textContent || el.value || '').trim();
            if ({check}) {{
                return JSON.stringify({{ ok: true, actual: current.slice(0, 100), captured: '{cv_escaped}' }});
            }} else {{
                return JSON.stringify({{ ok: false, error: 'Cross-step assertion failed ({mode}). Current: ' + current.slice(0, 100) + ', captured was: {cv_escaped}' }});
            }}
        }} catch (e) {{
            return JSON.stringify({{ ok: false, error: typeof e === 'string' ? e : (e.message || String(e)) }});
        }}
    }})()
    """


# ── Capture JS generators ─────────────────────────────────────


def _js_capture_text(find_js: str) -> str:
    """JS: capture element textContent."""
    return f"""
    (async function() {{
        try {{
            var el = await {find_js};
            var text = (el.textContent || '');
            return JSON.stringify({{ ok: true, captured: text }});
        }} catch (e) {{
            return JSON.stringify({{ ok: false, error: typeof e === 'string' ? e : (e.message || String(e)) }});
        }}
    }})()
    """


def _js_capture_html(find_js: str) -> str:
    """JS: capture element innerHTML."""
    return f"""
    (async function() {{
        try {{
            var el = await {find_js};
            var html = (el.innerHTML || '');
            return JSON.stringify({{ ok: true, captured: html }});
        }} catch (e) {{
            return JSON.stringify({{ ok: false, error: typeof e === 'string' ? e : (e.message || String(e)) }});
        }}
    }})()
    """


def _js_capture_value(find_js: str) -> str:
    """JS: capture input/textarea/select element value."""
    return f"""
    (async function() {{
        try {{
            var el = await {find_js};
            var val = (el.value || '');
            return JSON.stringify({{ ok: true, captured: val }});
        }} catch (e) {{
            return JSON.stringify({{ ok: false, error: typeof e === 'string' ? e : (e.message || String(e)) }});
        }}
    }})()
    """


def _js_capture_attribute(find_js: str, attr_name: str) -> str:
    """JS: capture a specific attribute from an element."""
    attr_escaped = _js_escape(attr_name)
    return f"""
    (async function() {{
        try {{
            var el = await {find_js};
            var val = el.getAttribute('{attr_escaped}');
            return JSON.stringify({{ ok: true, captured: val }});
        }} catch (e) {{
            return JSON.stringify({{ ok: false, error: typeof e === 'string' ? e : (e.message || String(e)) }});
        }}
    }})()
    """


def _js_capture_url() -> str:
    """JS: capture the current page URL. No element needed."""
    return """
    (function() {
        return JSON.stringify({ ok: true, captured: window.location.href });
    })()
    """


def _js_capture_computed_style(find_js: str, prop_name: str) -> str:
    """JS: capture a computed CSS property value."""
    prop_escaped = _js_escape(prop_name)
    return f"""
    (async function() {{
        try {{
            var el = await {find_js};
            var val = window.getComputedStyle(el)['{prop_escaped}'];
            return JSON.stringify({{ ok: true, captured: val }});
        }} catch (e) {{
            return JSON.stringify({{ ok: false, error: typeof e === 'string' ? e : (e.message || String(e)) }});
        }}
    }})()
    """


def _js_capture_console_start() -> str:
    """JS: start console capture by monkey-patching console methods.

    Patches console.log, console.warn, console.error, and console.info
    to buffer all output into ``window.__cdp_console_buffer``.
    Original methods are preserved and still called (non-destructive).
    """
    return """
    (function() {
        if (window.__cdp_console_originals) {
            return JSON.stringify({ ok: true, captured: 'already_active' });
        }
        window.__cdp_console_originals = {
            log: console.log,
            warn: console.warn,
            error: console.error,
            info: console.info
        };
        window.__cdp_console_buffer = [];
        ['log', 'warn', 'error', 'info'].forEach(function(method) {
            console[method] = function() {
                var args = Array.prototype.slice.call(arguments);
                var strs = args.map(function(a) {
                    if (typeof a === 'object') {
                        try { return JSON.stringify(a); } catch(e) { return String(a); }
                    }
                    return String(a);
                });
                window.__cdp_console_buffer.push({
                    ts: Date.now(),
                    level: method,
                    msg: strs.join(' ')
                });
                window.__cdp_console_originals[method].apply(console, arguments);
            };
        });
        return JSON.stringify({ ok: true, captured: 'started' });
    })()
    """


def _js_capture_console_stop() -> str:
    """JS: stop console capture — read buffer, restore originals.

    Returns all captured console entries as a JSON array.
    Each entry has: ``ts`` (epoch ms), ``level``, ``msg``.
    """
    return """
    (function() {
        var entries = window.__cdp_console_buffer || [];
        var originals = window.__cdp_console_originals;
        if (originals) {
            console.log = originals.log;
            console.warn = originals.warn;
            console.error = originals.error;
            console.info = originals.info;
        }
        delete window.__cdp_console_originals;
        delete window.__cdp_console_buffer;
        return JSON.stringify({ ok: true, captured: JSON.stringify(entries) });
    })()
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


def _execute_capture_screenshot(
    step: dict,
    variables: dict[str, str],
    *,
    session,
    run_id: str = "",
    project_root: str = "",
) -> dict:
    """Capture an element screenshot via CDP protocol commands.

    Flow:
        1. Find element + get bounding rect via JS evaluation
        2. Call ``Page.captureScreenshot`` with ``clip`` parameter
        3. Save base64 PNG to ``.state/cdp-tests/screenshots/``
        4. Return result dict with ``screenshot_path``

    This cannot be done through JS alone — ``Page.captureScreenshot``
    is a CDP domain command, not a browser API.

    Returns:
        Standard step result dict with ``details.screenshot_path``.
    """
    import base64
    import json as json_mod
    from pathlib import Path

    start = time.monotonic()

    if not session or not session.connected:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "status": "failed",
            "duration_ms": elapsed_ms,
            "error": "No CDP session for screenshot capture",
            "details": {},
        }

    # ── Step 1: Find element and get bounding rect ────────────
    find_js = _build_find_js(step, variables)
    rect_js = f"""(async function() {{
        try {{
            var el = await {find_js};
            if (!el) return JSON.stringify({{ ok: false, error: 'Element not found' }});
            var r = el.getBoundingClientRect();
            return JSON.stringify({{
                ok: true,
                x: r.x + window.scrollX,
                y: r.y + window.scrollY,
                width: r.width,
                height: r.height,
                devicePixelRatio: window.devicePixelRatio || 1
            }});
        }} catch (e) {{
            return JSON.stringify({{ ok: false, error: typeof e === 'string' ? e : (e.message || String(e)) }});
        }}
    }})()"""

    try:
        rect_result = session.evaluate(rect_js, await_promise=True, timeout=10.0)
        rect_val = (
            rect_result.get("result", {}).get("result", {}).get("value", "{}")
            if rect_result else "{}"
        )
        rect_parsed = json_mod.loads(rect_val) if rect_val else {}
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "status": "failed",
            "duration_ms": elapsed_ms,
            "error": f"Failed to get element rect: {exc}",
            "details": {},
        }

    if not rect_parsed.get("ok"):
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "status": "failed",
            "duration_ms": elapsed_ms,
            "error": rect_parsed.get("error", "Element not found"),
            "details": {},
        }

    # ── Step 2: Capture screenshot with clip ──────────────────
    dpr = rect_parsed.get("devicePixelRatio", 1)
    clip = {
        "x": rect_parsed["x"],
        "y": rect_parsed["y"],
        "width": max(rect_parsed["width"], 1),
        "height": max(rect_parsed["height"], 1),
        "scale": dpr,
    }

    try:
        screenshot_result = session.send_command(
            "Page.captureScreenshot",
            {
                "format": "png",
                "clip": clip,
                "captureBeyondViewport": True,
            },
            timeout=10.0,
        )
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "status": "failed",
            "duration_ms": elapsed_ms,
            "error": f"CDP screenshot command failed: {exc}",
            "details": {},
        }

    if not screenshot_result:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "status": "failed",
            "duration_ms": elapsed_ms,
            "error": "CDP returned None for screenshot",
            "details": {},
        }

    # Extract base64 data from CDP response
    b64_data = (
        screenshot_result.get("result", {}).get("data", "")
        if screenshot_result else ""
    )
    if not b64_data:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "status": "failed",
            "duration_ms": elapsed_ms,
            "error": "No screenshot data in CDP response",
            "details": {},
        }

    # ── Step 3: Save to disk ──────────────────────────────────
    step_id = step.get("id", "unknown")
    filename = f"{run_id}_{step_id}.png" if run_id else f"{step_id}.png"

    if project_root:
        screenshots_dir = Path(project_root) / ".state" / "cdp-tests" / "screenshots"
    else:
        screenshots_dir = Path(".state") / "cdp-tests" / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    screenshot_path = screenshots_dir / filename
    try:
        screenshot_path.write_bytes(base64.b64decode(b64_data))
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "status": "failed",
            "duration_ms": elapsed_ms,
            "error": f"Failed to save screenshot: {exc}",
            "details": {},
        }

    elapsed_ms = int((time.monotonic() - start) * 1000)
    rel_path = str(screenshot_path)
    logger.info("Screenshot captured: %s (%dx%d)", rel_path,
                int(rect_parsed["width"]), int(rect_parsed["height"]))

    return {
        "status": "passed",
        "duration_ms": elapsed_ms,
        "error": None,
        "details": {
            "screenshot_path": rel_path,
            "width": int(rect_parsed["width"]),
            "height": int(rect_parsed["height"]),
        },
    }


def _execute_screenshot_assertion(
    step: dict,
    variables: dict[str, str],
    *,
    session,
    run_id: str = "",
    project_root: str = "",
) -> dict:
    """Execute a screenshot-based assertion using OCR.

    Flow:
        1. Capture element screenshot via CDP (reuses existing infra)
        2. If check_type is ``capture_only`` → pass immediately
        3. Otherwise → run Tesseract OCR to extract text
        4. Evaluate extracted text against the assertion check type

    Returns:
        Standard step result dict with ``details.screenshot_path``,
        ``details.ocr_text``, and assertion status.
    """
    import re as re_mod

    start = time.monotonic()

    # Step 1: Capture the element screenshot
    screenshot_result = _execute_capture_screenshot(
        step, variables, session=session,
        run_id=run_id, project_root=project_root,
    )

    if screenshot_result["status"] == "failed":
        return screenshot_result

    screenshot_path = screenshot_result["details"].get("screenshot_path", "")

    # Read assertion params from assert_config (graph mode, where recorder
    # puts them), falling back to flat step fields for backward compat.
    _ac = step.get("assert_config") or {}
    check_type = _ac.get("check_type") or step.get("assertion_type", "ocr_text_contains")
    if check_type == "capture_only":
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "status": "passed",
            "duration_ms": elapsed_ms,
            "error": None,
            "details": {
                "screenshot_path": screenshot_path,
                "check_type": "capture_only",
                "actual": "[screenshot captured — no assertion]",
            },
        }

    # Step 3: Multi-level OCR dependency detection
    # Level 1: System binary (tesseract-ocr)
    # Level 2: Python wrapper (pytesseract)
    # Level 3: Image library (Pillow)
    import importlib.util
    import shutil

    missing_deps: list[dict] = []

    # Level 1: tesseract binary
    if not shutil.which("tesseract"):
        missing_deps.append({
            "level": 1,
            "name": "tesseract-ocr",
            "type": "system",
            "description": "Tesseract OCR engine (system binary)",
            "install_hint": "apt install tesseract-ocr",
            "recipe_id": "tesseract",
        })

    # Level 2: pytesseract Python package
    if not importlib.util.find_spec("pytesseract"):
        missing_deps.append({
            "level": 2,
            "name": "pytesseract",
            "type": "pip",
            "description": "Python wrapper for Tesseract OCR",
            "install_hint": "pip install pytesseract",
            "recipe_id": "pytesseract",
        })

    # Level 3: Pillow (image loading)
    if not importlib.util.find_spec("PIL"):
        missing_deps.append({
            "level": 3,
            "name": "Pillow",
            "type": "pip",
            "description": "Image processing library (required for OCR input)",
            "install_hint": "pip install Pillow",
            "recipe_id": None,  # Pillow is a Pillow-specific dep, no recipe
        })

    if missing_deps:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        # Build human-readable checklist
        lines = ["Screenshot OCR assertions require dependencies that are not installed:"]
        for dep in missing_deps:
            lines.append(
                f"  {'❌' if dep['type'] == 'system' else '📦'} "
                f"Level {dep['level']}: {dep['name']} — {dep['description']}"
            )
            lines.append(f"     → {dep['install_hint']}")
        lines.append("")
        lines.append("Install these dependencies to enable OCR screenshot assertions.")

        return {
            "status": "failed",
            "duration_ms": elapsed_ms,
            "error": "\n".join(lines),
            "details": {
                "screenshot_path": screenshot_path,
                "missing_dependencies": missing_deps,
                "install_plan": {
                    "tool": "pytesseract",
                    "steps": [d for d in missing_deps],
                    "can_auto_install": all(
                        d["type"] == "pip" for d in missing_deps
                    ),
                },
            },
        }

    import pytesseract
    from PIL import Image

    try:
        img = Image.open(screenshot_path)
        ocr_text = pytesseract.image_to_string(img).strip()
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "status": "failed",
            "duration_ms": elapsed_ms,
            "error": f"OCR extraction failed: {exc}",
            "details": {"screenshot_path": screenshot_path},
        }

    logger.info("OCR extracted %d chars from %s", len(ocr_text), screenshot_path)

    # Step 4: Evaluate OCR text against expected value
    expected = _resolve_variables(
        _ac.get("expected") or step.get("assertion_expected", ""), variables,
    )
    case_sensitive = _ac.get("case_sensitive", step.get("case_sensitive", False))

    actual_cmp = ocr_text if case_sensitive else ocr_text.lower()
    expected_cmp = expected if case_sensitive else expected.lower()

    passed = False
    if check_type == "ocr_text_contains":
        passed = expected_cmp in actual_cmp
    elif check_type == "ocr_text_equals":
        passed = actual_cmp == expected_cmp
    elif check_type == "ocr_text_matches":
        try:
            flags = 0 if case_sensitive else re_mod.IGNORECASE
            passed = bool(re_mod.search(expected, ocr_text, flags))
        except re_mod.error as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return {
                "status": "failed",
                "duration_ms": elapsed_ms,
                "error": f"Invalid regex pattern: {exc}",
                "details": {
                    "screenshot_path": screenshot_path,
                    "ocr_text": ocr_text,
                },
            }
    else:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "status": "failed",
            "duration_ms": elapsed_ms,
            "error": f"Unknown screenshot check type: {check_type}",
            "details": {
                "screenshot_path": screenshot_path,
                "ocr_text": ocr_text,
            },
        }

    elapsed_ms = int((time.monotonic() - start) * 1000)

    if passed:
        return {
            "status": "passed",
            "duration_ms": elapsed_ms,
            "error": None,
            "details": {
                "screenshot_path": screenshot_path,
                "ocr_text": ocr_text,
                "actual": ocr_text,
                "expected": expected,
                "check_type": check_type,
            },
        }
    else:
        return {
            "status": "failed",
            "duration_ms": elapsed_ms,
            "error": (
                f"OCR assertion failed: expected {check_type.replace('ocr_text_', '')} "
                f"'{expected}' but OCR extracted: '{ocr_text}'"
            ),
            "details": {
                "screenshot_path": screenshot_path,
                "ocr_text": ocr_text,
                "actual": ocr_text,
                "expected": expected,
                "check_type": check_type,
            },
        }


def _build_step_js(
    step: dict,
    variables: dict[str, str],
    captures: dict[str, str] | None = None,
) -> str:
    """Build the JavaScript expression for a single step.

    Each step's value field is resolved for variables first.
    Uses multi-strategy element finding and post-action DOM waits.
    captures: dict of previously captured values keyed by step_id
    (used for cross-step assertions).
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

    # ── Capture actions ───────────────────────────────────────
    if action == "capture_text":
        return _js_capture_text(find_js)

    if action == "capture_html":
        return _js_capture_html(find_js)

    if action == "capture_value":
        return _js_capture_value(find_js)

    if action == "capture_attribute":
        attr_name = step.get("assertion_attribute", "")
        return _js_capture_attribute(find_js, attr_name)

    if action == "capture_url":
        return _js_capture_url()

    if action == "capture_computed_style":
        prop_name = step.get("assertion_attribute", "")
        return _js_capture_computed_style(find_js, prop_name)

    if action == "capture_console":
        # Mode: "start" begins capture, "stop" reads buffer and restores
        diag_cfg = step.get("diagnostic_config", {})
        mode = diag_cfg.get("mode", step.get("value", "start"))
        if mode == "stop":
            return _js_capture_console_stop()
        return _js_capture_console_start()

    # ── Diagnostic actions ─────────────────────────────────────
    if action == "inject_js":
        # Execute user-written JS from diagnostic_config or value field
        diag_cfg = step.get("diagnostic_config", {})
        js_code = diag_cfg.get("js_code", "") or value
        if not js_code:
            return """(function() { return JSON.stringify({ ok: false, error: 'No JS code to inject' }); })()"""
        # Wrap in try/catch, capture return value
        escaped_code = js_code.replace("\\", "\\\\").replace("`", "\\`")
        return f"""(function() {{
            try {{
                var __result = (function() {{ {escaped_code} }})();
                if (__result !== undefined && __result !== null) {{
                    var __str = (typeof __result === 'object')
                        ? JSON.stringify(__result)
                        : String(__result);
                    return JSON.stringify({{ ok: true, captured: __str }});
                }}
                return JSON.stringify({{ ok: true, captured: null }});
            }} catch (e) {{
                return JSON.stringify({{ ok: false, error: 'inject_js error: ' + e.message }});
            }}
        }})()"""

    if action == "diag_capture":
        # Diagnostic capture — same as capture_* but tagged as diagnostic
        diag_cfg = step.get("diagnostic_config", {})
        cap_type = diag_cfg.get("capture_type", "text")
        if cap_type == "html":
            return _js_capture_html(find_js)
        elif cap_type == "attribute":
            attr_name = diag_cfg.get("attribute_name", "")
            return _js_capture_attribute(find_js, attr_name)
        elif cap_type == "value":
            return _js_capture_value(find_js)
        elif cap_type == "computed_style":
            prop = diag_cfg.get("attribute_name", "")
            return _js_capture_computed_style(find_js, prop)
        else:
            # Default to text capture
            return _js_capture_text(find_js)

    if action == "assert":
        a_type = step.get("assertion_type", "exists")
        a_expected = _resolve_variables(
            step.get("assertion_expected", ""), variables,
        )
        # ── Text assertions — all map to _js_assert_text(mode) ──
        _text_modes = {
            "text_contains": "contains",
            "text_equals": "equals",
            "text_not_contains": "not_contains",
            "text_starts_with": "starts_with",
            "text_ends_with": "ends_with",
            "text_matches": "matches",
            "text_one_of": "one_of",
            "text_empty": "empty",
            "text_not_empty": "not_empty",
        }
        if a_type in _text_modes:
            return _js_assert_text(find_js, a_expected, _text_modes[a_type])
        # ── Value assertions — all map to _js_assert_value(mode) ──
        _value_modes = {
            "value_equals": "equals",
            "value_contains": "contains",
            "value_empty": "empty",
            "value_not_empty": "not_empty",
        }
        if a_type in _value_modes:
            return _js_assert_value(find_js, a_expected, _value_modes[a_type])
        # ── Attribute assertions — need assertion_attribute name ──
        _attr_modes = {
            "attribute_equals": "equals",
            "attribute_contains": "contains",
            "attribute_exists": "attr_exists",
            "attribute_not_exists": "attr_not_exists",
        }
        if a_type in _attr_modes:
            a_attr = step.get("assertion_attribute", "")
            return _js_assert_attribute(
                find_js, a_attr, a_expected, _attr_modes[a_type],
            )
        # ── Element state assertions ─────────────────────────────
        _state_modes = {
            "hidden", "enabled", "disabled",
            "checked", "not_checked", "focused", "selected",
        }
        if a_type in _state_modes:
            return _js_assert_state(find_js, a_type)
        # ── CSS / style assertions ───────────────────────────────
        if a_type == "css_class_present":
            return _js_assert_css(find_js, a_expected, "class_present")
        if a_type == "css_class_absent":
            return _js_assert_css(find_js, a_expected, "class_absent")
        if a_type == "css_property_equals":
            a_attr = step.get("assertion_attribute", "")
            return _js_assert_css(
                find_js, a_expected, "property_equals", attr_name=a_attr,
            )
        # ── HTML / structure assertions ──────────────────────────
        _html_modes = {
            "html_contains", "html_equals",
            "children_count", "children_count_gt", "children_count_lt",
        }
        if a_type in _html_modes:
            return _js_assert_html(find_js, a_expected, a_type)
        # ── Count assertions — uses raw selector, not find_js ────
        _count_modes = {"count_equals", "count_gt", "count_lt", "count_gte"}
        if a_type in _count_modes:
            return _js_assert_count(
                step.get("selector", ""), a_expected, a_type,
            )
        # ── Numeric assertions — parse element text as number ────
        _numeric_modes = {
            "numeric_equals", "numeric_gt", "numeric_lt", "numeric_between",
        }
        if a_type in _numeric_modes:
            return _js_assert_numeric(find_js, a_expected, a_type)
        # ── Page-level assertions — no element needed ────────────
        _page_modes = {
            "url_equals", "url_contains", "title_equals", "title_contains",
        }
        if a_type in _page_modes:
            return _js_assert_page(a_expected, a_type)
        # ── Cross-step assertions — compare with captured value ──
        _captured_modes = {
            "captured_equals", "captured_contains",
            "captured_changed", "captured_unchanged",
        }
        if a_type in _captured_modes:
            # a_expected holds the capture_step_id to reference
            capture_ref = a_expected
            _caps = captures or {}
            if capture_ref not in _caps:
                # Return a failing JS if the capture doesn't exist
                return f"""(function() {{ return JSON.stringify({{ ok: false, error: 'No captured value found for step_id: {_js_escape(capture_ref)}' }}); }})()"""
            return _js_assert_captured(
                find_js, _caps[capture_ref], a_type,
            )
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
    captures: dict[str, str] | None = None,
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

    # ── Protocol-level actions (bypass JS path) ───────────────
    action = step.get("action", "")
    if action in ("capture_screenshot", "diag_screenshot"):
        return _execute_capture_screenshot(
            step, variables, session=session,
            run_id=step.get("_run_id", ""),
            project_root=step.get("_project_root", ""),
        )

    # ── Screenshot assertion via OCR (bypass JS path) ─────────
    _ac = step.get("assert_config") or {}
    if action == "assert" and _ac.get("capture_type") == "screenshot":
        return _execute_screenshot_assertion(
            step, variables, session=session,
            run_id=step.get("_run_id", ""),
            project_root=step.get("_project_root", ""),
        )

    js_expr = _build_step_js(step, variables, captures=captures)
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


def _verify_target_tab(
    target_id: str,
    *,
    cdp_port: int | None = None,
) -> str | None:
    """Verify the target tab is alive and return its WS URL.

    Args:
        cdp_port: When provided, query this Chrome instance instead of
                  the global endpoint.

    Returns:
        The webSocketDebuggerUrl string, or None if tab not found.
    """
    from src.ui.web import cdp_client

    targets = cdp_client.get_targets(port=cdp_port)
    for t in targets:
        if t.get("id") == target_id:
            return t.get("webSocketDebuggerUrl")
    return None


def _find_dcp_tab(*, cdp_port: int | None = None) -> str | None:
    """Find the DCP admin panel tab's target ID (for re-activating after replay).

    When replaying against a separate Chrome instance (cdp_port is set),
    the DCP tab won't exist in that browser — returns None gracefully.
    """
    from src.ui.web import cdp_client

    targets = cdp_client.get_targets(port=cdp_port)
    dcp = cdp_client.find_target_by_url(targets, "localhost:8000")
    if dcp:
        return dcp.get("id")
    return None


# ── Graph-mode step routing ───────────────────────────────────

# Sentinel returned by _route_after_step to signal hard stop
_ROUTE_STOP = "__STOP__"


def _route_after_step(
    step,
    step_result: dict,
) -> str | None:
    """Determine the next step ID in graph-mode traversal.

    For normal (non-assert) steps, returns the step's ``next_step_id``
    (which may be None to signal end-of-branch / end-of-suite).

    For assert steps with an ``assert_config``, the routing depends
    on pass/fail and the configured ``on_fail`` mode:

        * **pass** → ``assert_config.on_pass``
        * **fail + mode "fail"** → ``_ROUTE_STOP`` (hard stop)
        * **fail + mode "continue"** → ``assert_config.on_pass``
          (continue despite failure)
        * **fail + mode "branch"** → first non-cancel branch's
          ``first_step_id`` (automated mode)

    Returns:
        Step ID string, ``_ROUTE_STOP`` to abort, or ``None`` to end.
    """
    passed = step_result["status"] == "passed"

    # If the step has no assert_config, follow the default edge
    ac = getattr(step, "assert_config", None)
    if ac is None:
        return getattr(step, "next_step_id", None)

    # Assert step with routing config
    if passed:
        return ac.on_pass or None

    # Failed assertion — apply failure route
    fr = ac.on_fail
    if fr.mode == "fail":
        return _ROUTE_STOP
    elif fr.mode == "continue":
        # Soft fail — continue to on_pass target
        return ac.on_pass or None
    elif fr.mode == "branch":
        # Automated mode: take first non-cancel branch
        for branch in fr.branches:
            if branch.action != "cancel":
                return branch.first_step_id or None
        # All branches are cancel — hard stop
        return _ROUTE_STOP

    # Unknown mode — default to hard stop
    return _ROUTE_STOP


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
    keep_background: bool = False,
    project_root: str = "",
    cdp_port: int | None = None,
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
        dcp_tab_id = _find_dcp_tab(cdp_port=cdp_port)

    # ── Verify and activate target tab ───────────────────────
    if not ws_url:
        ws_url = _verify_target_tab(target_id, cdp_port=cdp_port)
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
    # In graph mode, walk the main flow from start_step_id.
    # In linear mode, sort by sequence (existing behavior).
    if suite.steps_dict and suite.start_step_id:
        # Graph mode: walk main flow edges
        step_list = []
        _visited = set()
        _cur = suite.start_step_id
        while _cur and _cur in suite.steps_dict and _cur not in _visited:
            _visited.add(_cur)
            _st = suite.steps_dict[_cur]
            # Only include main-flow steps (not branch steps)
            if not _st.branch_id:
                step_list.append(_st)
            _cur = _st.next_step_id
        # Update total_steps to reflect the initial traversal
        run_result.total_steps = len(step_list)
    else:
        step_list = sorted(suite.steps, key=lambda s: s.sequence)
    had_failure = False

    # ── Layer 2 (always): prevent Chrome timer throttling ───
    # Keep page lifecycle active so timers/rAF aren't slowed
    # in background tabs. Does NOT affect visibilityState.
    if session and session.connected:
        session.send_command(
            "Page.setWebLifecycleState",
            {"state": "active"},
            timeout=2.0,
        )

    # ── Layers 1 & 3 (background mode only) ───────────────
    # When keep_background is True, prevent the page from knowing
    # the tab lost focus — replay runs regardless of tab visibility.
    if keep_background and session and session.connected:
        # Layer 1: Emulate focused page (prevents blur/visibility
        #          events when switching between DevTools & target)
        session.send_command(
            "Emulation.setFocusEmulationEnabled",
            {"enabled": True},
            timeout=2.0,
        )
        # Layer 3: JS-level visibility override (prevents the web
        #          app itself from reacting to visibilitychange)
        _VIS_OVERRIDE_JS = """(function() {
            Object.defineProperty(document, 'visibilityState', {
                get: function() { return 'visible'; },
                configurable: true,
            });
            Object.defineProperty(document, 'hidden', {
                get: function() { return false; },
                configurable: true,
            });
            document.addEventListener('visibilitychange', function(e) {
                e.stopImmediatePropagation();
            }, true);
            return JSON.stringify({ok: true});
        })()"""
        session.evaluate(_VIS_OVERRIDE_JS, timeout=2.0)
        logger.info("Replay: background mode layers applied (1+3)")

    # Remove backdrop + scroll to top — single call, ONCE before loop
    if session and session.connected:
        session.evaluate("""(function() {
            var bd = document.getElementById('__cdp_replay_backdrop');
            if (bd) { bd.style.opacity='0'; setTimeout(function(){bd.remove()},300); }
            window.scrollTo(0, 0);
            return JSON.stringify({ok:true});
        })()""", timeout=3.0)
        time.sleep(0.3)  # Let backdrop fade + scroll settle

    captures = {}  # Captured values keyed by step_id (for cross-step assertions)

    # ── Graph-mode detection ──────────────────────────────────
    # If the suite has a steps_dict and start_step_id, we're in
    # graph mode: follow next_step_id edges instead of sequence.
    _graph_mode = bool(suite.steps_dict and suite.start_step_id)
    _step_lookup: dict[str, object] = {}  # step_id → TestStep
    if _graph_mode:
        _step_lookup = suite.steps_dict
        logger.info("Replay: graph mode enabled (start=%s, %d steps in graph)",
                    suite.start_step_id, len(_step_lookup))
    else:
        # Build lookup from step_list for Layer 4/5 retry (already exists)
        for _s in step_list:
            _step_lookup[_s.id] = _s

    try:
      i = 0
      while i < len(step_list):
        step = step_list[i]
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
        # Inject replay context for protocol-level actions (screenshots)
        step_dict["_run_id"] = run_result.id
        step_dict["_project_root"] = str(project_root) if project_root else ""

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
        # Skipped in background mode (layers handle it).
        if not keep_background and session and session.connected:
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
                        "target_id": target_id,
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
            captures=captures,
        )

        # Retry settle time — shorter than normal pacing, just DOM reaction
        _retry_settle = max(suite.min_step_delay_ms // 2, 350) / 1000.0

        # ── Layer 4 safety: retry after re-executing previous click ──
        # If the step failed with "not found" and the previous step was
        # a click (which likely opened the element we're targeting),
        # re-execute the previous click to restore transient DOM state,
        # then retry this step once.
        if (
            step_result["status"] == "failed"
            and "not found" in (step_result.get("error") or "").lower()
            and i > 0
            and step_list[i - 1].action == "click"
        ):
            prev_step = step_list[i - 1]
            prev_dict = prev_step.to_dict()
            logger.info(
                "Layer 4 retry: re-executing previous click (step %d) "
                "before retrying step %d",
                i, i + 1,
            )
            _execute_step(
                prev_dict, merged_vars, session=session, ws_url=ws_url,
            )
            time.sleep(_retry_settle)
            step_result = _execute_step(
                step_dict, merged_vars, session=session, ws_url=ws_url,
                captures=captures,
            )
            if step_result["status"] == "passed":
                logger.info("Layer 4 retry succeeded for step %d", i + 1)

        # ── Layer 5 safety: rewind 2 steps ───────────────────────
        # If Layer 4 didn't fix it, the context may depend on an
        # earlier click (e.g. click article → click markdown → type).
        # Re-execute steps N-2 and N-1, then retry N.
        if (
            step_result["status"] == "failed"
            and "not found" in (step_result.get("error") or "").lower()
            and i > 1
            and step_list[i - 2].action == "click"
        ):
            step_n2 = step_list[i - 2]
            step_n1 = step_list[i - 1]
            logger.info(
                "Layer 5 retry: re-executing steps %d+%d "
                "before retrying step %d",
                i - 1, i, i + 1,
            )
            _execute_step(
                step_n2.to_dict(), merged_vars, session=session, ws_url=ws_url,
            )
            time.sleep(_retry_settle)
            _execute_step(
                step_n1.to_dict(), merged_vars, session=session, ws_url=ws_url,
            )
            time.sleep(_retry_settle)
            step_result = _execute_step(
                step_dict, merged_vars, session=session, ws_url=ws_url,
                captures=captures,
            )
            if step_result["status"] == "passed":
                logger.info("Layer 5 retry succeeded for step %d", i + 1)

        # ── Post-step pacing (action-aware) ─────────────────────
        # Effective values: per-run override or suite default
        _eff_min = min_step_delay_ms if min_step_delay_ms is not None else suite.min_step_delay_ms
        _eff_vis = visual_delay_ms if visual_delay_ms is not None else suite.visual_delay_ms

        page_changed = step_result.get("details", {}).get("changed", False)
        _is_mutation = step.action in ("type", "select", "key")

        if _is_mutation and page_changed:
            # Mutation actions need full debounce for page to settle
            _pace_ms = max(_eff_min, _eff_vis)
        elif page_changed:
            # Clicks that trigger DOM changes — shorter settle
            _pace_ms = max(_eff_vis, 200)
        else:
            # No DOM changes — minimal pause for visual tracking
            _pace_ms = max(_eff_vis, 100)

        if _pace_ms > 0:
            time.sleep(_pace_ms / 1000.0)

        # Build step result record
        details = step_result.get("details", {})
        result_record = {
            "step_id": step.id,
            "sequence": step.sequence,
            "action": step.action,
            "selector": step.selector,
            "status": step_result["status"],
            "duration_ms": step_result["duration_ms"],
            "error": step_result.get("error"),
        }

        # Store captured value from capture_* actions
        if step.action.startswith("capture_") and step_result["status"] == "passed":
            captured_val = details.get("captured")
            if captured_val is not None:
                captures[step.id] = captured_val
                result_record["captured_value"] = captured_val

        # Store assertion metadata for assert steps
        if step.action == "assert":
            actual = details.get("actual")
            if actual is not None:
                result_record["assertion_actual"] = actual
            # Include check config from flat fields or assert_config
            ac = getattr(step, "assert_config", None)
            if ac:
                result_record["assertion_check"] = ac.check_type
                result_record["assertion_expected"] = ac.expected
            elif step.assertion_type:
                result_record["assertion_check"] = step.assertion_type
                result_record["assertion_expected"] = step.assertion_expected

        # Tag branch membership
        if getattr(step, "branch_id", None):
            result_record["branch_id"] = step.branch_id

        # Store screenshot path from capture_screenshot / diag_screenshot
        screenshot_path = details.get("screenshot_path")
        if screenshot_path:
            result_record["screenshot_path"] = screenshot_path

        # Parse console capture data into structured entries
        if step.action == "capture_console" and step_result["status"] == "passed":
            captured_raw = details.get("captured", "")
            if captured_raw and captured_raw not in ("started", "already_active"):
                import json as _json
                try:
                    console_entries = _json.loads(captured_raw)
                    if isinstance(console_entries, list):
                        result_record["console_log"] = console_entries
                except (ValueError, TypeError):
                    result_record["console_log"] = [{"msg": captured_raw}]

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
            if step.optional:
                # Optional step failed — report it but don't count as hard failure
                run_result.passed_steps += 1  # count as "soft pass"
                callback("cdp_test:step_failed", {
                    "run_id": run_result.id,
                    "optional": True,
                    **result_record,
                })
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

            # ── Missing dependency remediation ──────────────────
            # If the step failed because a tool/package is missing,
            # emit a dedicated event so the frontend can auto-trigger
            # the install flow via installWithPlan().
            _missing_deps = step_result.get("details", {}).get(
                "missing_dependencies",
            )
            if _missing_deps:
                # Find the top-level recipe to install (the one that
                # transitively pulls everything else via requires.binaries)
                _recipe_id = None
                _recipe_label = None
                for _dep in _missing_deps:
                    if _dep.get("recipe_id"):
                        _recipe_id = _dep["recipe_id"]
                        _recipe_label = _dep.get("description", _dep["name"])
                        break
                if _recipe_id:
                    callback("cdp_test:missing_dependency", {
                        "run_id": run_result.id,
                        "step_id": step.id,
                        "recipe_id": _recipe_id,
                        "recipe_label": _recipe_label,
                        "missing": [
                            {
                                "name": d["name"],
                                "type": d["type"],
                                "level": d["level"],
                                "hint": d["install_hint"],
                            }
                            for d in _missing_deps
                        ],
                    })

            # If step is not optional and stop_on_failure is set, abort
            # In graph mode with assert_config, routing is handled below;
            # only apply linear stop logic for steps without assert_config.
            _has_routing = (
                _graph_mode
                and step.action == "assert"
                and getattr(step, "assert_config", None) is not None
            )
            if not _has_routing and not step.optional and suite.stop_on_failure:
                # Mark remaining steps as skipped (linear mode)
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

        # ── Graph-mode routing: determine next step ──────────
        if _graph_mode and getattr(step, "next_step_id", None) is not None:
            next_id = _route_after_step(step, step_result)
            if next_id == _ROUTE_STOP:
                logger.info("Graph routing: hard stop at step %s", step.id)
                # Mark as failed and break (remaining steps aren't
                # deterministic in graph mode — no skip markers)
                break
            elif next_id is None:
                # End of branch / end of suite
                logger.info("Graph routing: end of branch at step %s", step.id)
                break
            elif next_id in _step_lookup:
                # Jump to the target step
                target_step = _step_lookup[next_id]
                _target_branch = getattr(target_step, "branch_id", None)
                if _target_branch:
                    logger.info(
                        "Graph routing: branch taken at step %s → %s (branch %s)",
                        step.id, next_id, _target_branch,
                    )
                    # Record branch_taken in the last result record
                    run_result.step_results[-1]["branch_taken"] = _target_branch
                    callback("cdp_test:branch_taken", {
                        "run_id": run_result.id,
                        "step_id": step.id,
                        "target_step_id": next_id,
                        "branch_id": _target_branch,
                    })
                else:
                    logger.debug(
                        "Graph routing: step %s → %s", step.id, next_id,
                    )
                # Find its index in step_list (if it exists there)
                _found_idx = None
                for _j, _s in enumerate(step_list):
                    if _s.id == next_id:
                        _found_idx = _j
                        break
                if _found_idx is not None:
                    i = _found_idx
                    continue  # Skip the i += 1 below
                else:
                    # Step is in steps_dict but not in step_list
                    # (branch step). Execute it inline.
                    step_list.insert(i + 1, target_step)
                    # i += 1 below will land on the inserted step
            else:
                logger.warning(
                    "Graph routing: step %s references unknown step %s",
                    step.id, next_id,
                )
                break

        # ── Linear mode: advance to next step ────────────────
        i += 1

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
    keep_background: bool = False,
    cdp_port: int | None = None,
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
                keep_background=keep_background,
                project_root=str(project_root) if project_root else "",
                cdp_port=cdp_port,
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
