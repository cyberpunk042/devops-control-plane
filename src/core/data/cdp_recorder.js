/**
 * DCP CDP Recorder — injected into foreign pages to capture user interactions.
 *
 * This script is parameterized and injected via cdp_client.evaluate_js().
 * Template variables (replaced by Python before injection):
 *   ${SESSION_ID}  — recording session UUID
 *   ${DCP_HOST}    — DCP server host (e.g. "localhost")
 *   ${DCP_PORT}    — DCP server port (e.g. 8001)
 *
 * What it captures:
 *   - Clicks (with intelligent selector building)
 *   - Text input (type events, debounced)
 *   - Select changes
 *   - Key presses (Enter, Escape, Tab)
 *   - Navigation (pushState, popstate, hashchange)
 *
 * Communication:
 *   Events are sent to DCP via navigator.sendBeacon() or fetch().
 *   POST to http://${DCP_HOST}:${DCP_PORT}/api/cdp-test/record/event
 *
 * Control:
 *   window.__dcp_recorder_active = true   — detection flag
 *   window.__dcp_recorder_paused = false  — pause/resume flag
 */
(function () {
    'use strict';

    // ── Guard: don't inject twice ──────────────────────────────
    if (window.__dcp_recorder_active) return 'already_active';
    window.__dcp_recorder_active = true;
    window.__dcp_recorder_paused = false;
    window.__dcp_session_id = '${SESSION_ID}';

    var SESSION_ID = '${SESSION_ID}';
    var DCP_CALLBACK = 'http://${DCP_HOST}:${DCP_PORT}/api/cdp-test/record/event';
    var _lastUrl = location.href;
    var _inputTimers = {};       // debounce timers per element: { timerId, el, isPassword }

    // Flush all pending debounced input events immediately
    function _flushPendingInputs() {
        var keys = Object.keys(_inputTimers);
        for (var fi = 0; fi < keys.length; fi++) {
            var entry = _inputTimers[keys[fi]];
            if (!entry) continue;
            clearTimeout(entry.timerId);
            var el = entry.el;
            var isPassword = entry.isPassword;
            if (el) {
                var sel = buildSelector(el);
                if (!isPassword) _lastTypedValues[sel] = el.value;
                sendEvent({
                    action: 'type',
                    selector: sel,
                    xpath: buildXPath(el),
                    selector_alternatives: buildAlternatives(el),
                    value: isPassword ? '' : el.value,
                    element_tag: el.tagName.toLowerCase(),
                    element_text: '',
                    element_rect: getRect(el),
                    is_password: isPassword,
                });
            }
            delete _inputTimers[keys[fi]];
        }
    }
    var _INPUT_DEBOUNCE = 600;   // ms to wait after typing stops
    var _lastClickTime = 0;

    // ── Always-on console capture ─────────────────────────────
    // Monkey-patch console methods from the moment recording starts.
    // All output is buffered into window.__cdp_console_buffer so it's
    // available when the user requests a console capture.
    if (!window.__cdp_console_originals) {
        window.__cdp_console_originals = {
            log: console.log,
            warn: console.warn,
            error: console.error,
            info: console.info,
        };
        window.__cdp_console_buffer = [];
        ['log', 'warn', 'error', 'info'].forEach(function (method) {
            console[method] = function () {
                var args = Array.prototype.slice.call(arguments);
                var strs = args.map(function (a) {
                    if (typeof a === 'object') {
                        try { return JSON.stringify(a); } catch (_) { return String(a); }
                    }
                    return String(a);
                });
                window.__cdp_console_buffer.push({
                    ts: Date.now(),
                    level: method,
                    msg: strs.join(' '),
                });
                window.__cdp_console_originals[method].apply(console, arguments);
            };
        });
    }


    // ═══════════════════════════════════════════════════════════
    //  Selector Building
    // ═══════════════════════════════════════════════════════════

    /**
     * Build a CSS selector for an element (best effort, unique on page).
     */
    function buildSelector(el) {
        // 1. ID — best (unique by definition)
        if (el.id) {
            return '#' + CSS.escape(el.id);
        }

        // 2. data-testid / data-test / data-cy (test-friendly)
        var testId = el.getAttribute('data-testid')
            || el.getAttribute('data-test')
            || el.getAttribute('data-cy');
        if (testId) {
            return '[data-testid="' + testId + '"]';
        }

        // 3. name attribute (forms)
        if (el.name && (el.tagName === 'INPUT' || el.tagName === 'SELECT'
            || el.tagName === 'TEXTAREA')) {
            var nameSelector = el.tagName.toLowerCase() + '[name="' + el.name + '"]';
            if (document.querySelectorAll(nameSelector).length === 1) {
                return nameSelector;
            }
        }

        // 4. type + role combination for buttons/links
        if (el.tagName === 'BUTTON' || el.getAttribute('role') === 'button') {
            var btnText = (el.textContent || '').trim().slice(0, 30);
            if (btnText) {
                // Try: button with this exact text
                var candidates = document.querySelectorAll(el.tagName.toLowerCase());
                var uniqueText = true;
                for (var i = 0; i < candidates.length; i++) {
                    if (candidates[i] !== el
                        && (candidates[i].textContent || '').trim().slice(0, 30) === btnText) {
                        uniqueText = false;
                        break;
                    }
                }
                if (uniqueText && el.className) {
                    var cls = el.className.split(/\s+/).filter(function (c) {
                        return c && !c.match(/^(active|hover|focus|selected|open)/);
                    }).slice(0, 2).map(function (c) { return '.' + CSS.escape(c); }).join('');
                    if (cls) {
                        var s = el.tagName.toLowerCase() + cls;
                        if (document.querySelectorAll(s).length === 1) return s;
                    }
                }
            }
        }

        // 5. Unique class combination
        if (el.className && typeof el.className === 'string') {
            var classes = el.className.trim().split(/\s+/).filter(function (c) {
                return c && !c.match(/^(active|hover|focus|selected|open|ng-|_)/);
            });
            for (var n = 1; n <= Math.min(classes.length, 3); n++) {
                var combo = classes.slice(0, n).map(function (c) {
                    return '.' + CSS.escape(c);
                }).join('');
                var sel = el.tagName.toLowerCase() + combo;
                if (document.querySelectorAll(sel).length === 1) return sel;
            }
        }

        // 6. nth-child path (most fragile — last resort)
        return buildNthChildPath(el);
    }

    /**
     * Build alternative selectors for resilience.
     */
    function buildAlternatives(el) {
        var alts = [];

        // XPath
        var xpath = buildXPath(el);
        if (xpath) alts.push(xpath);

        // aria-label
        var ariaLabel = el.getAttribute('aria-label');
        if (ariaLabel) {
            alts.push('[aria-label="' + ariaLabel + '"]');
        }

        // placeholder
        var placeholder = el.getAttribute('placeholder');
        if (placeholder) {
            alts.push('[placeholder="' + placeholder + '"]');
        }

        return alts.slice(0, 3);
    }

    /**
     * Build nth-child CSS path from root to element.
     */
    function buildNthChildPath(el) {
        var path = [];
        var current = el;
        while (current && current !== document.documentElement) {
            var parent = current.parentElement;
            if (!parent) break;
            var siblings = Array.from(parent.children);
            var index = siblings.indexOf(current) + 1;
            path.unshift(current.tagName.toLowerCase() + ':nth-child(' + index + ')');
            current = parent;
            if (path.length > 8) break; // don't go too deep
        }
        return path.length > 0 ? path.join(' > ') : el.tagName.toLowerCase();
    }

    /**
     * Build a simple XPath for the element.
     */
    function buildXPath(el) {
        var parts = [];
        var current = el;
        while (current && current.nodeType === 1 && current !== document.body) {
            var tag = current.tagName.toLowerCase();
            var parent = current.parentElement;
            if (!parent) break;
            var siblings = Array.from(parent.children).filter(function (c) {
                return c.tagName === current.tagName;
            });
            if (siblings.length > 1) {
                var idx = siblings.indexOf(current) + 1;
                parts.unshift(tag + '[' + idx + ']');
            } else {
                parts.unshift(tag);
            }
            current = parent;
            if (parts.length > 6) break;
        }
        return parts.length > 0 ? '//' + parts.join('/') : '';
    }

    /**
     * Get bounding rect for an element.
     */
    function getRect(el) {
        try {
            var r = el.getBoundingClientRect();
            return {
                x: Math.round(r.x), y: Math.round(r.y),
                width: Math.round(r.width), height: Math.round(r.height)
            };
        } catch (_) {
            return {};
        }
    }


    // ═══════════════════════════════════════════════════════════
    //  Event Sending
    // ═══════════════════════════════════════════════════════════

    var _sendFailed = false;

    function sendEvent(data) {
        if (window.__dcp_recorder_paused) {
            _dcpLog('warn', 'sendEvent BLOCKED — recorder is paused', { action: data.action || '?' });
            return;
        }

        var payload = JSON.stringify({
            session_id: window.__dcp_session_id || SESSION_ID,
            timestamp_ms: Date.now(),
            page_url: location.href,
            ...data,
        });

        // Use fetch with credentials:'omit' — sendBeacon always sends
        // cookies which triggers stricter CORS rules that block with
        // ad blockers. fetch with omit avoids credential-mode issues.
        try {
            fetch(DCP_CALLBACK, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: payload,
                mode: 'cors',
                credentials: 'omit',
                keepalive: true,
            }).then(function (resp) {
                if (_sendFailed && resp.ok) {
                    _sendFailed = false;
                    _updateIndicator('ok');
                }
            }).catch(function (err) {
                _dcpLog('error', 'sendEvent fetch FAILED', { action: data.action || '?', error: String(err) });
                if (!_sendFailed) {
                    _sendFailed = true;
                    _updateIndicator('blocked');
                }
            });
        } catch (_) { }
    }

    // ── Diagnostic logging — visible in DCP terminal ────────────
    var DCP_LOG_URL = 'http://${DCP_HOST}:${DCP_PORT}/api/cdp-test/record/log';

    function _dcpLog(level, msg, data) {
        // Always log to target page console too
        var prefix = '[DCP recorder] ';
        if (level === 'error') console.error(prefix + msg, data || '');
        else if (level === 'warn') console.warn(prefix + msg, data || '');
        else console.log(prefix + msg, data || '');

        // Send to backend for terminal visibility
        try {
            fetch(DCP_LOG_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ level: level, msg: msg, data: data || {} }),
                mode: 'cors',
                credentials: 'omit',
            }).catch(function () { /* log delivery failed — don't recurse */ });
        } catch (_) { }
    }


    // ═══════════════════════════════════════════════════════════
    //  Event Listeners
    // ═══════════════════════════════════════════════════════════

    // ── Click ─────────────────────────────────────────────────

    var _lastBadge = null;
    var _lastIOBadge = null;
    var _lastTypedValues = {};  // selector → last typed value (for default value when element gone)

    /**
     * Walk up from a leaf element to find the nearest "meaningful" element.
     * Users clicking on a <span> inside a <button> intend to click the button.
     * Without this, we'd record the span selector — fragile and wrong for assertions.
     */
    function _findMeaningfulElement(el) {
        // Tags that are always meaningful click targets
        var interactiveTags = {
            A: 1, BUTTON: 1, INPUT: 1, SELECT: 1, TEXTAREA: 1,
            LABEL: 1, SUMMARY: 1, DETAILS: 1,
        };
        var current = el;
        var maxDepth = 6; // don't walk up forever
        while (current && current !== document.body && maxDepth-- > 0) {
            // Element with id — always meaningful
            if (current.id) return current;
            // Element with test attribute — always meaningful
            if (current.getAttribute('data-testid') ||
                current.getAttribute('data-test') ||
                current.getAttribute('data-cy')) return current;
            // Interactive element — always meaningful
            if (interactiveTags[current.tagName]) return current;
            // Element with role — likely meaningful
            if (current.getAttribute('role')) return current;
            // Element with name — form element
            if (current.getAttribute('name')) return current;
            // Element with onclick/href — interactive
            if (current.getAttribute('onclick') || current.getAttribute('href')) return current;
            current = current.parentElement;
        }
        // No meaningful parent found — use the original element
        return el;
    }

    document.addEventListener('click', function (e) {
        if (window.__dcp_recorder_paused) return;

        var rawEl = e.target;
        // Skip clicks on the recorder's own UI
        if (rawEl.closest && rawEl.closest('#__dcp_recorder_indicator')) return;
        if (rawEl.closest && rawEl.closest('#__dcp_assert_overlay')) return;
        if (rawEl.closest && rawEl.closest('.__dcp_assert_badge')) return;
        if (rawEl.closest && rawEl.closest('.__dcp_io_badge')) return;
        if (rawEl.closest && rawEl.closest('#__dcp_io_overlay')) return;

        // Debounce rapid double-clicks
        var now = Date.now();
        if (now - _lastClickTime < 50) return;
        _lastClickTime = now;

        // Resolve to the nearest meaningful element (button, link, etc.)
        var el = _findMeaningfulElement(rawEl);

        var selector = buildSelector(el);
        var elemText = (el.textContent || '').trim().slice(0, 80);
        var elemRect = getRect(el);

        sendEvent({
            action: 'click',
            selector: selector,
            xpath: buildXPath(el),
            selector_alternatives: buildAlternatives(el),
            element_tag: el.tagName.toLowerCase(),
            element_text: elemText,
            element_rect: elemRect,
        });

        // Show assertion badge on the FOCUSED element after the click settles
        // (user wants to assert on what has focus, not what they clicked)
        setTimeout(function () {
            var focused = document.activeElement;
            // If focus landed on body/html or null, fall back to click target
            if (!focused || focused === document.body || focused === document.documentElement) {
                focused = el;
            }
            var focusSelector = buildSelector(focused);
            var focusText = (focused.textContent || '').trim().slice(0, 80);
            var focusRect = getRect(focused);
            _showAssertBadge(focused, focusSelector, focusText, focusRect);
        }, 150);
    }, true);

    /**
     * Show a floating assertion badge near the clicked element.
     * Clicking the badge opens the assertion config modal.
     */
    function _showAssertBadge(el, selector, elemText, elemRect) {
        // Remove previous badge
        if (_lastBadge) { _lastBadge.remove(); _lastBadge = null; }


        // Build ancestor chain: element + up to 4 parents
        var selectorChain = [];
        var cur = el;
        for (var ci = 0; ci < 5 && cur && cur !== document.body && cur !== document.documentElement; ci++) {
            selectorChain.push({
                selector: buildSelector(cur),
                text: (cur.textContent || '').trim().slice(0, 60),
                rect: getRect(cur),
                tag: cur.tagName.toLowerCase(),
                idx: ci,
            });
            cur = cur.parentElement;
        }

        var badge = document.createElement('div');
        badge.className = '__dcp_assert_badge';
        badge.style.cssText = [
            'position:fixed',
            'z-index:2147483644',
            'background:rgba(34,197,94,0.95)',
            'color:white',
            'font-family:system-ui,-apple-system,sans-serif',
            'font-size:11px',
            'font-weight:600',
            'padding:3px 10px',
            'border-radius:10px',
            'cursor:pointer',
            'box-shadow:0 2px 12px rgba(0,0,0,0.35)',
            'display:flex',
            'align-items:center',
            'gap:4px',
            'animation:__dcp_badge_in 0.2s ease',
            'transition:background 0.15s',
        ].join(';');

        // Position near the element
        var top = Math.max(4, elemRect.y - 28);
        var left = Math.min(window.innerWidth - 140, Math.max(4, elemRect.x));
        badge.style.top = top + 'px';
        badge.style.left = left + 'px';

        badge.innerHTML = '<span style="font-size:13px">✅</span><span>Assert</span>' +
            '<span style="font-size:9px;opacity:0.7;margin-left:2px">📋 💉</span>';
        badge.title = 'Add assertion / capture / diagnostic for this element';

        badge.addEventListener('mouseenter', function () {
            badge.style.background = 'rgba(22,163,74,1)';
        });
        badge.addEventListener('mouseleave', function () {
            badge.style.background = 'rgba(34,197,94,0.95)';
        });

        badge.addEventListener('click', function (e) {
            e.stopPropagation();
            e.preventDefault();
            badge.remove();
            _lastBadge = null;
            _openAssertModal(selector, elemText, elemRect, selectorChain);
        });

        document.body.appendChild(badge);
        _lastBadge = badge;

        // ── I/O badge (purple, appears beside assert badge) ──
        if (_lastIOBadge) { _lastIOBadge.remove(); _lastIOBadge = null; }

        var ioBadge = document.createElement('div');
        ioBadge.className = '__dcp_io_badge';
        ioBadge.style.cssText = [
            'position:fixed',
            'z-index:2147483644',
            'background:rgba(139,92,246,0.95)',
            'color:white',
            'font-family:system-ui,-apple-system,sans-serif',
            'font-size:11px',
            'font-weight:600',
            'padding:3px 10px',
            'border-radius:10px',
            'cursor:pointer',
            'box-shadow:0 2px 12px rgba(0,0,0,0.35)',
            'display:flex',
            'align-items:center',
            'gap:4px',
            'animation:__dcp_badge_in 0.2s ease',
            'transition:background 0.15s',
        ].join(';');

        // Position to the RIGHT of the assert badge — +110px gap to avoid overlap
        ioBadge.style.top = top + 'px';
        ioBadge.style.left = Math.min(window.innerWidth - 60, left + 110) + 'px';

        ioBadge.innerHTML = '<span style="font-size:13px">\ud83d\udd17</span><span>I/O</span>';
        ioBadge.title = 'Configure variable binding / output export for this element';

        ioBadge.addEventListener('mouseenter', function () {
            ioBadge.style.background = 'rgba(109,62,216,1)';
        });
        ioBadge.addEventListener('mouseleave', function () {
            ioBadge.style.background = 'rgba(139,92,246,0.95)';
        });

        ioBadge.addEventListener('click', function (e) {
            e.stopPropagation();
            e.preventDefault();
            ioBadge.remove();
            _lastIOBadge = null;
            _openIOModal(selector, elemText, elemRect, selectorChain);
        });

        document.body.appendChild(ioBadge);
        _lastIOBadge = ioBadge;
    }


    // ═══════════════════════════════════════════════════════════
    //  Assertion Config Modal (injected into target page)
    // ═══════════════════════════════════════════════════════════

    /** Build check type <option> groups filtered by capture type */
    function _buildCheckOptions(checkGroups, captureType) {
        var html = '';
        // Default selection per capture type
        var defaults = {
            text: 'text_contains', html: 'html_contains', value: 'value_equals',
            attribute: 'attribute_equals', screenshot: 'ocr_text_contains',
            state: 'exists', console: 'no_errors',
        };
        var defaultVal = defaults[captureType] || 'text_contains';
        var found = false;
        checkGroups.forEach(function (g) {
            // Skip groups not applicable to this capture type
            if (g.for && g.for.indexOf(captureType) === -1) return;
            html += '<optgroup label="' + g.label + '">';
            g.checks.forEach(function (c) {
                var sel = (!found && c[0] === defaultVal) ? ' selected' : '';
                if (sel) found = true;
                html += '<option value="' + c[0] + '"' + sel + '>' + c[1] + '</option>';
            });
            html += '</optgroup>';
        });
        // Auto-select first option if no default matched
        if (!found && html) {
            html = html.replace('<option ', '<option selected ');
        }
        return html;
    }

    function _openAssertModal(selector, elemText, elemRect, selectorChain) {
        selectorChain = selectorChain || [];
        // Remove existing
        var existing = document.getElementById('__dcp_assert_overlay');
        if (existing) existing.remove();

        // Pause recording while configuring
        window.__dcp_recorder_paused = true;
        _dcpLog('info', 'Assert modal opened', { selector: selector, paused: true });

        var overlay = document.createElement('div');
        overlay.id = '__dcp_assert_overlay';
        overlay.style.cssText = [
            'position:fixed', 'inset:0', 'z-index:2147483645',
            'display:flex', 'align-items:center', 'justify-content:center',
            'background:rgba(0,0,0,0.55)', 'backdrop-filter:blur(6px)',
            'font-family:system-ui,-apple-system,sans-serif',
        ].join(';');

        // Color palette (self-contained, no CSS vars)
        var C = {
            bg: '#1a1a2e', bgCard: '#16213e', bgInput: '#0f3460',
            border: '#2a2a4a', borderLight: '#3a3a5a',
            text: '#e0e0e8', textMuted: '#8888aa', textSecondary: '#b0b0cc',
            accent: '#22c55e', accentHover: '#16a34a',
            error: '#ef4444', warn: '#f59e0b',
            primary: '#6366f1', primaryHover: '#4f46e5',
        };

        // Assertion check types — tagged with which capture types they apply to
        var checkGroups = [
            {
                label: 'Text', for: ['text'], checks: [
                    ['text_equals', 'Text equals'], ['text_contains', 'Text contains'],
                    ['text_not_contains', 'Text not contains'], ['text_starts_with', 'Starts with'],
                    ['text_ends_with', 'Ends with'], ['text_matches', 'Matches regex'],
                    ['text_empty', 'Text empty'], ['text_not_empty', 'Text not empty'],
                ]
            },
            {
                label: 'HTML', for: ['html'], checks: [
                    ['html_equals', 'HTML equals'], ['html_contains', 'HTML contains'],
                    ['html_not_contains', 'HTML not contains'], ['html_matches', 'Matches regex'],
                    ['html_empty', 'HTML empty'], ['html_not_empty', 'HTML not empty'],
                ]
            },
            {
                label: 'Value', for: ['value'], checks: [
                    ['value_equals', 'Value equals'], ['value_contains', 'Value contains'],
                    ['value_empty', 'Value empty'], ['value_not_empty', 'Value not empty'],
                ]
            },
            {
                label: 'Attribute', for: ['attribute'], checks: [
                    ['attribute_equals', 'Attr equals'], ['attribute_contains', 'Attr contains'],
                    ['attribute_exists', 'Attr exists'], ['attribute_not_exists', 'Attr absent'],
                ]
            },
            {
                label: 'Element', for: ['text', 'html', 'value', 'attribute', 'state'], checks: [
                    ['exists', 'Exists'], ['not_exists', 'Absent'],
                    ['visible', 'Visible'], ['hidden', 'Hidden'],
                    ['enabled', 'Enabled'], ['disabled', 'Disabled'],
                    ['checked', 'Checked'], ['not_checked', 'Unchecked'],
                ]
            },
            {
                label: 'CSS', for: ['state'], checks: [
                    ['css_class_present', 'Has class'], ['css_class_absent', 'No class'],
                    ['css_property_equals', 'CSS prop ='],
                ]
            },
            {
                label: 'Count', for: ['text', 'html', 'value', 'attribute'], checks: [
                    ['count_equals', 'Count ='], ['count_gt', 'Count >'], ['count_lt', 'Count <'],
                ]
            },
            {
                label: 'Page', for: ['text', 'html', 'console'], checks: [
                    ['url_equals', 'URL equals'], ['url_contains', 'URL contains'],
                    ['title_equals', 'Title equals'], ['title_contains', 'Title contains'],
                ]
            },
            {
                label: 'Screenshot', for: ['screenshot'], checks: [
                    ['ocr_text_contains', 'OCR text contains'],
                    ['ocr_text_equals', 'OCR text equals'],
                    ['ocr_text_matches', 'OCR text matches regex'],
                    ['capture_only', 'Capture only (no assert)'],
                ]
            },
            {
                label: 'Console', for: ['console'], checks: [
                    ['log_contains', 'Log contains'], ['log_matches', 'Log matches regex'],
                    ['no_errors', 'No errors'], ['no_warnings', 'No warnings'],
                ]
            },
        ];

        // Build initial optgroup HTML for default capture type (text)
        var optgroupHtml = _buildCheckOptions(checkGroups, 'text');

        // Live preview: capture current value
        var liveValue = '';
        try {
            var targetEl = document.querySelector(selector);
            if (targetEl) liveValue = (targetEl.textContent || '').trim();
        } catch (_) { }

        var s = function (obj) {
            return Object.keys(obj).map(function (k) { return k + ':' + obj[k]; }).join(';');
        };

        // Style constants
        var sLabel = s({ 'font-size': '11px', 'font-weight': '700', color: C.textMuted, 'text-transform': 'uppercase', 'letter-spacing': '0.5px', 'margin-bottom': '6px' });
        var sRadioLabel = s({ display: 'flex', 'align-items': 'center', gap: '5px', 'font-size': '12px', cursor: 'pointer', padding: '5px 8px', background: C.bgInput, 'border-radius': '5px', border: '1px solid ' + C.border, color: C.text });
        var sInput = s({ 'font-size': '12px', padding: '5px 8px', background: C.bgInput, border: '1px solid ' + C.border, 'border-radius': '5px', color: C.text, width: '100%', 'box-sizing': 'border-box', outline: 'none' });
        var sSelect = s({ 'font-size': '12px', padding: '5px 8px', background: C.bgInput, border: '1px solid ' + C.border, 'border-radius': '5px', color: C.text, width: '100%', outline: 'none' });
        var sBtn = function (bg) {
            return s({ 'font-size': '12px', 'font-weight': '600', padding: '6px 16px', border: 'none', 'border-radius': '6px', cursor: 'pointer', background: bg, color: '#fff' });
        };

        // Build modal — NO user data goes into innerHTML, it's all
        // set via .textContent and .value AFTER insertion (safe from XSS/breakage)
        overlay.innerHTML =
            '<div style="' + s({
                background: C.bg, border: '1px solid ' + C.border, 'border-radius': '12px',
                width: '480px', 'max-width': '92vw', 'max-height': '85vh', 'overflow-y': 'auto',
                'box-shadow': '0 20px 60px rgba(0,0,0,0.6)', color: C.text,
            }) + '">' +

            // Header
            '<div style="' + s({ padding: '14px 18px 10px', 'border-bottom': '1px solid ' + C.border, display: 'flex', 'align-items': 'center', gap: '8px' }) + '">' +
            '<span style="font-size:16px">🔍</span>' +
            '<div style="flex:1">' +
            '<div style="font-weight:700;font-size:14px">Assertion Configuration</div>' +
            '<div id="__dcp_header_selector" style="font-size:10px;color:' + C.textMuted + ';font-family:monospace;margin-top:2px"></div>' +
            '</div>' +
            '<button id="__dcp_peek_toggle" title="Peek: highlight matched element(s)" style="' + s({
                'font-size': '12px', padding: '4px 10px', border: '1px solid ' + C.border,
                'border-radius': '6px', cursor: 'pointer', background: C.bgInput, color: C.text,
                display: 'flex', 'align-items': 'center', gap: '4px', 'flex-shrink': '0',
            }) + '">👁 Peek</button>' +
            '</div>' +

            '<div style="padding:12px 18px;display:flex;flex-direction:column;gap:12px">' +

            // §0: Target Element picker (when ancestry chain available)
            (selectorChain.length > 1 ? (function () {
                // Check availability of each element NOW (at modal open time)
                var firstAvail = -1;
                selectorChain.forEach(function (item, i) {
                    try {
                        item.available = !!document.querySelector(item.selector);
                    } catch (_) {
                        item.available = false;
                    }
                    if (item.available && firstAvail === -1) firstAvail = i;
                });

                var chainHtml = '<div>' +
                    '<div style="' + sLabel + '">Target Element</div>' +
                    '<div style="display:flex;flex-direction:column;gap:3px">';

                selectorChain.forEach(function (item, i) {
                    var indent = i === 0 ? '' : '↳ '.repeat(i);
                    var selPreview = item.selector.length > 40 ? item.selector.slice(0, 37) + '…' : item.selector;
                    var textPreview = item.text ? '"' + (item.text.length > 30 ? item.text.slice(0, 27) + '…' : item.text) + '"' : '';
                    var isDefault = (i === firstAvail);

                    if (item.available) {
                        chainHtml += '<label style="' + sRadioLabel + ';padding:4px 8px">' +
                            '<input type="radio" name="__dcp_target" value="' + i + '"' + (isDefault ? ' checked' : '') + '>' +
                            '<span style="font-size:11px">' + indent +
                            '<code style="color:' + C.accent + ';font-size:10px">&lt;' + item.tag + '&gt;</code> ' +
                            '<span style="font-family:monospace;font-size:9px;color:' + C.textSecondary + '">' + selPreview + '</span>' +
                            (textPreview ? '<span style="font-size:9px;color:' + C.textMuted + ';margin-left:4px">' + textPreview + '</span>' : '') +
                            '</span>' +
                            '</label>';
                    } else {
                        chainHtml += '<label style="' + sRadioLabel + ';padding:4px 8px;opacity:0.4;cursor:not-allowed" title="Element no longer in DOM — dynamic/focus-dependent elements cannot be asserted">' +
                            '<input type="radio" name="__dcp_target" value="' + i + '" disabled>' +
                            '<span style="font-size:11px">' + indent +
                            '<code style="color:' + C.error + ';font-size:10px">&lt;' + item.tag + '&gt;</code> ' +
                            '<span style="font-family:monospace;font-size:9px;color:' + C.textMuted + ';text-decoration:line-through">' + selPreview + '</span>' +
                            '<span style="font-size:9px;color:' + C.warn + ';margin-left:4px">⚠ gone</span>' +
                            '</span>' +
                            '</label>';
                    }
                });

                chainHtml += '</div>';

                // Show help note if any element is unavailable
                var anyGone = selectorChain.some(function (item) { return !item.available; });
                if (anyGone) {
                    chainHtml += '<div id="__dcp_gone_warning" style="font-size:10px;color:' + C.warn + ';margin-top:4px;padding:4px 8px;background:rgba(245,158,11,0.1);border-radius:4px;transition:all 0.2s">' +
                        '⚠ Grayed elements disappeared when focus was lost. ' +
                        'Dynamic elements (textareas, dropdowns) that only exist on focus cannot be asserted — ' +
                        'select a parent or sibling that persists in the DOM.' +
                        '</div>';
                }

                chainHtml += '</div>';

                // If the original selector (idx 0) is gone, update ctx defaults
                if (firstAvail >= 0 && firstAvail !== 0) {
                    // Will be picked up by ctx initialization below
                    selector = selectorChain[firstAvail].selector;
                    elemText = selectorChain[firstAvail].text;
                    elemRect = selectorChain[firstAvail].rect;
                }

                return chainHtml;
            })() : '') +

            // §1: What to Capture (7 options incl. console)
            '<div>' +
            '<div style="' + sLabel + '">What to Capture</div>' +
            '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:4px">' +
            '<label style="' + sRadioLabel + '"><input type="radio" name="__dcp_cap" value="text" checked> Text</label>' +
            '<label style="' + sRadioLabel + '"><input type="radio" name="__dcp_cap" value="html"> HTML</label>' +
            '<label style="' + sRadioLabel + '"><input type="radio" name="__dcp_cap" value="value"> Value</label>' +
            '<label style="' + sRadioLabel + '"><input type="radio" name="__dcp_cap" value="attribute"> Attribute</label>' +
            '<label style="' + sRadioLabel + '"><input type="radio" name="__dcp_cap" value="screenshot"> Screenshot</label>' +
            '<label style="' + sRadioLabel + '"><input type="radio" name="__dcp_cap" value="state"> State</label>' +
            '<label style="' + sRadioLabel + '"><input type="radio" name="__dcp_cap" value="console"> Console</label>' +
            '</div>' +
            '<div id="__dcp_attr_row" style="display:none;margin-top:5px">' +
            '<input id="__dcp_attr_name" type="text" list="__dcp_attr_list" placeholder="Attribute name (e.g. data-status, href)" style="' + sInput + '">' +
            '<datalist id="__dcp_attr_list"></datalist>' +
            '</div>' +
            '</div>' +

            // §2: Live Preview
            '<div>' +
            '<div style="' + sLabel + '">Live Preview</div>' +
            '<div id="__dcp_preview" style="' + s({ padding: '8px 10px', background: C.bgInput, 'border-radius': '5px', border: '1px solid ' + C.border, 'font-family': 'monospace', 'font-size': '11px', 'max-height': '80px', 'overflow-y': 'auto', 'word-break': 'break-all', color: C.text }) + '"></div>' +
            '</div>' +

            // §3: Assertion Check
            '<div>' +
            '<div style="' + sLabel + '">Assertion Check</div>' +
            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">' +
            '<div>' +
            '<div style="font-size:10px;font-weight:600;color:' + C.textSecondary + ';margin-bottom:3px">Check type</div>' +
            '<select id="__dcp_check_type" style="' + sSelect + '">' + optgroupHtml + '</select>' +
            '</div>' +
            '<div>' +
            '<div style="font-size:10px;font-weight:600;color:' + C.textSecondary + ';margin-bottom:3px">Expected value</div>' +
            '<input id="__dcp_expected" type="text" style="' + sInput + '">' +
            '</div>' +
            '</div>' +
            '<div style="margin-top:6px">' +
            '<label style="font-size:11px;display:flex;align-items:center;gap:4px;cursor:pointer;color:' + C.textSecondary + '"><input type="checkbox" id="__dcp_case" checked> Case sensitive</label>' +
            '</div>' +
            '</div>' +

            // §4: On Failure
            '<div>' +
            '<div style="' + sLabel + '">On Failure</div>' +
            '<div style="display:flex;flex-direction:column;gap:4px">' +
            '<label style="' + sRadioLabel + '"><input type="radio" name="__dcp_fail" value="fail" checked> <span>⛔ <b>Hard fail</b> — stop execution</span></label>' +
            '<label style="' + sRadioLabel + '"><input type="radio" name="__dcp_fail" value="continue"> <span>⚠️ <b>Soft fail</b> — mark failed, continue</span></label>' +
            '</div>' +

            // Diagnose on failure toggle + template picker
            '<div style="margin-top:8px">' +
            '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:12px;color:' + C.text + '">' +
            '<input type="checkbox" id="__dcp_diag_toggle">' +
            '<span>🔍 <b>Diagnose on failure</b> — run diagnostics before failing</span>' +
            '</label>' +
            '<div id="__dcp_diag_panel" style="display:none;margin-top:6px;padding:8px 10px;background:' + C.bgCard + ';border:1px solid ' + C.border + ';border-radius:6px">' +
            '<div style="font-size:10px;font-weight:600;color:' + C.textMuted + ';margin-bottom:6px">Diagnostic templates</div>' +

            // Capture diagnostics
            '<div style="font-size:9px;font-weight:600;color:' + C.textSecondary + ';margin-bottom:3px;text-transform:uppercase;letter-spacing:0.3px">Capture</div>' +
            '<div style="display:flex;flex-direction:column;gap:3px;margin-bottom:6px">' +
            '<label style="' + sRadioLabel + ';padding:3px 8px"><input type="checkbox" class="__dcp_diag_tpl" value="screenshot_element" checked> 📸 Element screenshot</label>' +
            '<label style="' + sRadioLabel + ';padding:3px 8px"><input type="checkbox" class="__dcp_diag_tpl" value="screenshot_full"> 🖼️ Full page screenshot</label>' +
            '<label style="' + sRadioLabel + ';padding:3px 8px"><input type="checkbox" class="__dcp_diag_tpl" value="console"> 🖥️ Console dump</label>' +
            '<label style="' + sRadioLabel + ';padding:3px 8px"><input type="checkbox" class="__dcp_diag_tpl" value="element_state"> 🔍 Element state (styles, attrs, rect)</label>' +
            '<label style="' + sRadioLabel + ';padding:3px 8px"><input type="checkbox" class="__dcp_diag_tpl" value="page_html"> 📄 Page HTML snapshot</label>' +
            '<label style="' + sRadioLabel + ';padding:3px 8px"><input type="checkbox" class="__dcp_diag_tpl" value="network_stack"> 🌐 Network request stack</label>' +
            '</div>' +

            // Debug diagnostics
            '<div style="font-size:9px;font-weight:600;color:' + C.textSecondary + ';margin-bottom:3px;text-transform:uppercase;letter-spacing:0.3px">Debug</div>' +
            '<div style="display:flex;flex-direction:column;gap:3px;margin-bottom:6px">' +
            '<label style="' + sRadioLabel + ';padding:3px 8px"><input type="checkbox" class="__dcp_diag_tpl" value="local_storage"> 🗄️ Dump localStorage</label>' +
            '<label style="' + sRadioLabel + ';padding:3px 8px"><input type="checkbox" class="__dcp_diag_tpl" value="session_storage"> 📦 Dump sessionStorage</label>' +
            '<label style="' + sRadioLabel + ';padding:3px 8px"><input type="checkbox" class="__dcp_diag_tpl" value="cookies"> 🍪 Dump cookies</label>' +
            '<label style="' + sRadioLabel + ';padding:3px 8px"><input type="checkbox" class="__dcp_diag_tpl" value="auth_token"> 🔑 Check auth token</label>' +
            '</div>' +

            // Custom
            '<div style="font-size:9px;font-weight:600;color:' + C.textSecondary + ';margin-bottom:3px;text-transform:uppercase;letter-spacing:0.3px">Custom</div>' +
            '<div style="display:flex;flex-direction:column;gap:3px">' +
            '<label style="' + sRadioLabel + ';padding:3px 8px"><input type="checkbox" class="__dcp_diag_tpl" value="custom_js"> 💉 Custom JS diagnostic</label>' +
            '</div>' +
            '<div id="__dcp_diag_js_editor" style="display:none;margin-top:6px">' +
            '<textarea id="__dcp_diag_js_code" placeholder="// Diagnostic JS — runs on failure to collect debug info…" style="' + s({ width: '100%', 'font-size': '11px', 'font-family': 'monospace', padding: '6px 8px', background: C.bgInput, border: '1px solid ' + C.border, 'border-radius': '5px', color: C.text, resize: 'vertical', 'min-height': '50px', 'box-sizing': 'border-box' }) + '"></textarea>' +
            '</div>' +
            '<div style="font-size:9px;color:' + C.textMuted + ';margin-top:4px">Diagnostics run <b>after</b> the step fails, <b>before</b> the fail mode takes effect.</div>' +
            '</div>' +
            '</div>' +
            '</div>' +

            // §5: Quick Actions
            '<div>' +
            '<div style="' + sLabel + '">Quick Actions</div>' +
            '<div style="display:flex;gap:4px;flex-wrap:wrap">' +
            '<button id="__dcp_qa_capture" style="' + sBtn(C.bgInput) + ';border:1px solid ' + C.border + '">📋 Capture only</button>' +
            '<button id="__dcp_qa_screenshot" style="' + sBtn(C.bgInput) + ';border:1px solid ' + C.border + '">📸 Element</button>' +
            '<button id="__dcp_qa_screenshot_full" style="' + sBtn(C.bgInput) + ';border:1px solid ' + C.border + '">🖼️ Full Page</button>' +
            '<button id="__dcp_qa_console" style="' + sBtn(C.bgInput) + ';border:1px solid ' + C.border + '">🖥️ Console</button>' +
            '<button id="__dcp_qa_inject" style="' + sBtn(C.bgInput) + ';border:1px solid ' + C.border + '">💉 Inject JS</button>' +
            '</div>' +
            '<div id="__dcp_js_editor" style="display:none;margin-top:6px">' +
            '<textarea id="__dcp_js_code" placeholder="// JavaScript to inject into the page…" style="' + s({ width: '100%', 'font-size': '11px', 'font-family': 'monospace', padding: '6px 8px', background: C.bgInput, border: '1px solid ' + C.border, 'border-radius': '5px', color: C.text, resize: 'vertical', 'min-height': '60px', 'box-sizing': 'border-box' }) + '"></textarea>' +
            '<button id="__dcp_qa_inject_save" style="' + sBtn(C.accent) + ';margin-top:4px;font-size:11px;padding:4px 12px">💉 Save JS Step</button>' +
            '</div>' +
            '</div>' +

            '</div>' +

            // Footer
            '<div style="' + s({ padding: '10px 18px 14px', 'border-top': '1px solid ' + C.border, display: 'flex', 'justify-content': 'flex-end', gap: '8px' }) + '">' +
            '<button id="__dcp_cancel_btn" style="' + sBtn(C.bgInput) + ';border:1px solid ' + C.border + '">Cancel</button>' +
            '<button id="__dcp_save_btn" style="' + sBtn(C.primary) + '">💾 Save Assertion</button>' +
            '</div>' +

            '</div>';

        document.body.appendChild(overlay);

        // ── Set user data safely via DOM properties (not innerHTML) ──

        // Recompute liveValue from the (potentially updated) selector
        // The IIFE above may have changed selector due to auto-fallover
        try {
            var targetEl = document.querySelector(selector);
            if (targetEl) liveValue = (targetEl.textContent || '').trim();
        } catch (_) { }

        // Selector in header — textContent is XSS-safe
        var headerSel = document.getElementById('__dcp_header_selector');
        if (headerSel) headerSel.textContent = selector.slice(0, 80);

        // Live preview — textContent is XSS-safe and handles all chars
        var previewEl = document.getElementById('__dcp_preview');
        if (previewEl) previewEl.textContent = liveValue || '[empty]';

        // Expected value — input .value property (safe, no parsing)
        var expectedEl = document.getElementById('__dcp_expected');
        if (expectedEl) expectedEl.value = liveValue.slice(0, 500);

        // ── Wire interactivity (all addEventListener — CSP-safe) ──

        // Mutable context so all quick actions use the CURRENTLY selected target
        var ctx = { selector: selector, elemText: elemText, elemRect: elemRect };

        // Close on backdrop
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) _closeAssertModal();
        });

        // Cancel button
        document.getElementById('__dcp_cancel_btn').addEventListener('click', function (e) {
            e.stopPropagation();
            _closeAssertModal();
        });

        // Save button
        document.getElementById('__dcp_save_btn').addEventListener('click', function (e) {
            e.stopPropagation();
            _saveAssertion(ctx.selector);
        });

        // ── Peek mode ──
        var peekBtn = document.getElementById('__dcp_peek_toggle');
        var _assertModal = overlay.querySelector('div');
        function _assertPeekOn() {
            overlay.style.background = 'rgba(0,0,0,0.05)';
            overlay.style.backdropFilter = 'none';
            overlay.style.webkitBackdropFilter = 'none';
            if (_assertModal) _assertModal.style.opacity = '0.25';
        }
        function _assertPeekOff() {
            overlay.style.background = 'rgba(0,0,0,0.55)';
            overlay.style.backdropFilter = 'blur(6px)';
            overlay.style.webkitBackdropFilter = 'blur(6px)';
            if (_assertModal) _assertModal.style.opacity = '1';
        }
        function _highlightGoneWarning(on) {
            var w = document.getElementById('__dcp_gone_warning');
            if (!w) return;
            if (on) {
                w.style.background = 'rgba(245,158,11,0.55)';
                w.style.boxShadow = '0 0 20px rgba(245,158,11,0.7), inset 0 0 10px rgba(245,158,11,0.3)';
                w.style.borderLeft = '4px solid #f59e0b';
                w.style.color = '#fff';
                w.style.fontSize = '12px';
                w.style.fontWeight = '600';
                w.style.padding = '8px 12px';
                w.style.transform = 'scale(1.03)';
            } else {
                w.style.background = 'rgba(245,158,11,0.1)';
                w.style.boxShadow = 'none';
                w.style.borderLeft = 'none';
                w.style.color = '';
                w.style.fontSize = '10px';
                w.style.fontWeight = '';
                w.style.padding = '4px 8px';
                w.style.transform = 'none';
            }
        }
        if (peekBtn) {
            // Click: toggle peek mode (transparent backdrop, ghosted modal, NO highlight)
            peekBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                _peekActive = !_peekActive;
                if (_peekActive) {
                    this.textContent = '👁 Peek ON';
                    this.style.borderColor = '#06b6d4';
                    this.style.color = '#06b6d4';
                } else {
                    _peekClear();
                    this.textContent = '👁 Peek';
                    this.style.borderColor = C.border;
                    this.style.color = C.text;
                    _assertPeekOff();
                }
            });
            // Hover peek button: preview opposite state
            peekBtn.addEventListener('mouseenter', function () {
                if (_peekActive) {
                    // In peek mode → preview normal
                    _peekClear();
                    _highlightGoneWarning(false);
                    _assertPeekOff();
                } else {
                    // Not in peek → preview peek (highlight current selector)
                    var found = _peekHighlight(ctx.selector);
                    if (found === 0) _highlightGoneWarning(true);
                    _assertPeekOn();
                }
            });
            peekBtn.addEventListener('mouseleave', function () {
                _peekClear();
                _highlightGoneWarning(false);
                _assertPeekOff();
            });
        }

        // Target element picker → update selector/rect/text
        if (selectorChain.length > 1) {
            var targetRadios = overlay.querySelectorAll('input[name="__dcp_target"]');
            for (var ti = 0; ti < targetRadios.length; ti++) {
                targetRadios[ti].addEventListener('change', function () {
                    var idx = parseInt(this.value, 10);
                    var picked = selectorChain[idx];
                    if (picked) {
                        ctx.selector = picked.selector;
                        ctx.elemText = picked.text;
                        ctx.elemRect = picked.rect;
                        var hs = document.getElementById('__dcp_header_selector');
                        if (hs) hs.textContent = picked.selector.slice(0, 80);
                        var curCapType = 'text';
                        var cRadios = document.querySelectorAll('input[name="__dcp_cap"]');
                        for (var ci = 0; ci < cRadios.length; ci++) {
                            if (cRadios[ci].checked) { curCapType = cRadios[ci].value; break; }
                        }
                        _refreshPreview(ctx.selector, curCapType);
                        _dcpLog('info', 'Target changed', { idx: idx, selector: ctx.selector, captureType: curCapType });
                    }
                });

                // Hover-to-peek on chain labels — ONLY when peek mode is ON
                var label = targetRadios[ti].closest('label');
                if (label) {
                    (function (radio) {
                        label.addEventListener('mouseenter', function () {
                            if (!_peekActive) return;
                            var idx = parseInt(radio.value, 10);
                            var item = selectorChain[idx];
                            if (!item) return;
                            if (!item.available) {
                                _highlightGoneWarning(true);
                            } else {
                                _peekHighlight(item.selector);
                                _assertPeekOn();
                            }
                        });
                        label.addEventListener('mouseleave', function () {
                            if (!_peekActive) return;
                            _peekClear();
                            _assertPeekOff();
                            _highlightGoneWarning(false);
                        });
                    })(targetRadios[ti]);
                }
            }
        }

        // Capture type → show/hide attribute input + refresh preview + update check options
        var capRadios = overlay.querySelectorAll('input[name="__dcp_cap"]');
        for (var i = 0; i < capRadios.length; i++) {
            capRadios[i].addEventListener('change', function () {
                var attrRow = document.getElementById('__dcp_attr_row');
                if (attrRow) attrRow.style.display = this.value === 'attribute' ? 'block' : 'none';
                // Update check type options based on capture type
                var selectEl = document.getElementById('__dcp_check_type');
                if (selectEl) selectEl.innerHTML = _buildCheckOptions(checkGroups, this.value);
                // Populate attribute datalist from the element's actual attributes
                if (this.value === 'attribute') {
                    try {
                        var targetEl = document.querySelector(ctx.selector);
                        var datalist = document.getElementById('__dcp_attr_list');
                        if (targetEl && datalist) {
                            datalist.innerHTML = '';
                            var attrs = targetEl.attributes;
                            for (var ai = 0; ai < attrs.length; ai++) {
                                var opt = document.createElement('option');
                                opt.value = attrs[ai].name;
                                datalist.appendChild(opt);
                            }
                        }
                    } catch (_) { }
                }
                _refreshPreview(ctx.selector, this.value);
            });
        }

        // Attribute name input → refresh preview when user types
        var attrInput = document.getElementById('__dcp_attr_name');
        if (attrInput) {
            attrInput.addEventListener('input', function () {
                _refreshPreview(ctx.selector, 'attribute');
            });
        }

        // Check type dropdown → refresh preview (updates OCR note for screenshot)
        var checkTypeSelect = document.getElementById('__dcp_check_type');
        if (checkTypeSelect) {
            checkTypeSelect.addEventListener('change', function () {
                var curCapType = 'text';
                var cRadios = document.querySelectorAll('input[name="__dcp_cap"]');
                for (var ci = 0; ci < cRadios.length; ci++) {
                    if (cRadios[ci].checked) { curCapType = cRadios[ci].value; break; }
                }
                _refreshPreview(ctx.selector, curCapType);
            });
        }

        // ── Wire diagnostic toggle + template interactions ──

        // Diagnose on failure toggle → show/hide diagnostic panel
        var diagToggle = document.getElementById('__dcp_diag_toggle');
        if (diagToggle) {
            diagToggle.addEventListener('change', function () {
                var panel = document.getElementById('__dcp_diag_panel');
                if (panel) panel.style.display = this.checked ? 'block' : 'none';
            });
        }

        // Custom JS template → show/hide JS diagnostic editor
        var diagTpls = overlay.querySelectorAll('input.__dcp_diag_tpl');
        for (var di = 0; di < diagTpls.length; di++) {
            diagTpls[di].addEventListener('change', function () {
                if (this.value === 'custom_js') {
                    var jsEditor = document.getElementById('__dcp_diag_js_editor');
                    if (jsEditor) jsEditor.style.display = this.checked ? 'block' : 'none';
                }
            });
        }

        // Quick action: capture only (respects selected capture type)
        document.getElementById('__dcp_qa_capture').addEventListener('click', function (e) {
            e.stopPropagation();
            var capType = 'text';
            var radios = document.querySelectorAll('input[name="__dcp_cap"]');
            for (var k = 0; k < radios.length; k++) {
                if (radios[k].checked) { capType = radios[k].value; break; }
            }
            var actionMap = {
                text: 'capture_text', html: 'capture_html', value: 'capture_value',
                attribute: 'capture_attribute', screenshot: 'capture_screenshot',
                state: 'capture_computed_style', console: 'capture_console',
            };
            if (capType === 'console') {
                // Console needs start + stop pair
                _dcpLog('info', 'Quick capture: console start+stop');
                window.__dcp_recorder_paused = false;
                sendEvent({ action: 'capture_console', selector: '', value: 'start' });
                sendEvent({ action: 'capture_console', selector: '', value: 'stop' });
            } else {
                _dcpLog('info', 'Quick capture', { type: capType, selector: ctx.selector });
                window.__dcp_recorder_paused = false;
                sendEvent({
                    action: actionMap[capType] || 'capture_text',
                    selector: ctx.selector,
                    value: capType === 'attribute' ? (document.getElementById('__dcp_attr_name') || {}).value || '' : '',
                });
            }
            _closeAssertModal();
        });

        // Quick action: element screenshot (clips to selected element)
        document.getElementById('__dcp_qa_screenshot').addEventListener('click', function (e) {
            e.stopPropagation();
            _dcpLog('info', 'Quick element screenshot', { selector: ctx.selector, rect: ctx.elemRect });
            window.__dcp_recorder_paused = false;
            sendEvent({ action: 'capture_screenshot', selector: ctx.selector, element_rect: ctx.elemRect });
            _closeAssertModal();
        });

        // Quick action: full page screenshot
        document.getElementById('__dcp_qa_screenshot_full').addEventListener('click', function (e) {
            e.stopPropagation();
            _dcpLog('info', 'Quick full-page screenshot');
            window.__dcp_recorder_paused = false;
            sendEvent({ action: 'capture_screenshot_full', selector: '' });
            _closeAssertModal();
        });

        // Quick action: console capture (sends start + stop pair)
        document.getElementById('__dcp_qa_console').addEventListener('click', function (e) {
            e.stopPropagation();
            _dcpLog('info', 'Quick console start+stop');
            window.__dcp_recorder_paused = false;
            sendEvent({ action: 'capture_console', selector: '', value: 'start' });
            sendEvent({ action: 'capture_console', selector: '', value: 'stop' });
            _closeAssertModal();
        });

        // Quick action: inject JS — toggle editor
        document.getElementById('__dcp_qa_inject').addEventListener('click', function (e) {
            e.stopPropagation();
            var editor = document.getElementById('__dcp_js_editor');
            if (editor) editor.style.display = editor.style.display === 'none' ? 'block' : 'none';
        });

        // Quick action: save injected JS step
        document.getElementById('__dcp_qa_inject_save').addEventListener('click', function (e) {
            e.stopPropagation();
            var code = (document.getElementById('__dcp_js_code') || {}).value || '';
            if (!code.trim()) return;
            _dcpLog('info', 'Quick inject JS', { codeLen: code.length });
            window.__dcp_recorder_paused = false;
            sendEvent({ action: 'inject_js', selector: ctx.selector, value: code });
            _closeAssertModal();
        });
    }

    /** Refresh the live preview panel based on capture type */
    function _refreshPreview(selector, captureType) {
        var previewEl = document.getElementById('__dcp_preview');
        if (!previewEl) return;
        try {
            var el = document.querySelector(selector);
            if (!el) { previewEl.textContent = '[element not found]'; return; }
            var val = '';
            if (captureType === 'text') val = (el.textContent || '').trim();
            else if (captureType === 'html') {
                val = (el.innerHTML || '');
                // If innerHTML is just plain text (no markup), tell the user
                if (val && val.trim() === (el.textContent || '').trim()) {
                    val = val.trim() + '\n\n💡 This element contains plain text only — no inner HTML markup. Select "Text" to capture its content.';
                }
            }
            else if (captureType === 'value') val = el.value || '';
            else if (captureType === 'attribute') {
                var attrName = (document.getElementById('__dcp_attr_name') || {}).value || 'class';
                val = el.getAttribute(attrName) || '[null]';
            }
            else if (captureType === 'state') {
                var cs = getComputedStyle(el);
                val = JSON.stringify({
                    visible: cs.display !== 'none' && cs.visibility !== 'hidden',
                    disabled: el.disabled || false,
                    checked: el.checked || false,
                    classes: (el.className || '').slice(0, 100),
                }, null, 2);
            }
            else if (captureType === 'screenshot') {
                var rect = el.getBoundingClientRect();
                var checkSel = document.getElementById('__dcp_check_type');
                var checkVal = checkSel ? checkSel.value : '';
                val = '📸 Capture area: ' + Math.round(rect.width) + ' × ' + Math.round(rect.height) + 'px\n' +
                    'Position: (' + Math.round(rect.left) + ', ' + Math.round(rect.top) + ') from viewport top-left\n' +
                    'Element: <' + el.tagName.toLowerCase() + (el.id ? ' id="' + el.id + '"' : '') + '>';
                // Show OCR note for OCR-based checks
                if (checkVal && checkVal.indexOf('ocr_') === 0) {
                    val += '\n\n💡 Screenshot assertions use OCR (Tesseract) to extract text from the captured image. OCR is highly accurate for standard rendered text but may be imperfect for stylized fonts, very small text, or complex backgrounds.';
                } else if (checkVal === 'capture_only') {
                    val += '\n\n📷 Capture only — screenshot will be stored as a diagnostic artifact. No text assertion performed.';
                }
                // Show bounding box overlay on the page
                _showScreenshotOverlay(rect);
            }
            else if (captureType === 'console') val = '[console capture — logs captured during replay]';

            // Remove screenshot overlay for non-screenshot types
            if (captureType !== 'screenshot') _removeScreenshotOverlay();

            // textContent is safe — no HTML injection possible
            previewEl.textContent = val || '[empty]';

            // Auto-update expected value for text-based types
            var expectedEl = document.getElementById('__dcp_expected');
            if (expectedEl && val && captureType !== 'screenshot' && captureType !== 'state' && captureType !== 'console') {
                expectedEl.value = val;
            }
        } catch (e) {
            previewEl.textContent = '[error: ' + e.message + ']';
        }
    }

    /** Show a pulsing overlay on the page around the element's bounding box */
    function _showScreenshotOverlay(rect) {
        _removeScreenshotOverlay();
        var ov = document.createElement('div');
        ov.id = '__dcp_screenshot_overlay';
        ov.style.cssText = [
            'position:fixed',
            'top:' + rect.top + 'px',
            'left:' + rect.left + 'px',
            'width:' + rect.width + 'px',
            'height:' + rect.height + 'px',
            'border:2px dashed #06b6d4',
            'background:rgba(6,182,212,0.08)',
            'z-index:2147483644',
            'pointer-events:none',
            'box-sizing:border-box',
            'border-radius:3px',
        ].join(';');
        // Pulsing animation via inline style
        ov.animate([
            { borderColor: '#06b6d4', opacity: 1 },
            { borderColor: '#22d3ee', opacity: 0.5 },
            { borderColor: '#06b6d4', opacity: 1 },
        ], { duration: 2000, iterations: Infinity });
        // Dimension label
        var label = document.createElement('div');
        label.style.cssText = [
            'position:absolute', 'bottom:-20px', 'left:0',
            'font-size:10px', 'font-family:system-ui,sans-serif',
            'background:#06b6d4', 'color:#fff',
            'padding:1px 6px', 'border-radius:3px',
            'white-space:nowrap',
        ].join(';');
        label.textContent = Math.round(rect.width) + ' × ' + Math.round(rect.height) + 'px';
        ov.appendChild(label);
        document.body.appendChild(ov);
    }

    /** Remove the screenshot bounding box overlay */
    function _removeScreenshotOverlay() {
        var existing = document.getElementById('__dcp_screenshot_overlay');
        if (existing) existing.remove();
    }


    // ═══════════════════════════════════════════════════════════
    //  Peek Highlight — show which element(s) a selector matches
    // ═══════════════════════════════════════════════════════════

    var _peekActive = false;  // toggle state

    /** Highlight all elements matching a CSS selector on the page */
    function _peekHighlight(selector) {
        _peekClear();
        if (!selector) return 0;
        try {
            var matches = document.querySelectorAll(selector);
            if (matches.length === 0) return 0;

            for (var pi = 0; pi < matches.length; pi++) {
                var el = matches[pi];
                var rect = el.getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) continue;

                var ov = document.createElement('div');
                ov.className = '__dcp_peek_ov';
                ov.style.cssText = [
                    'position:fixed',
                    'top:' + rect.top + 'px',
                    'left:' + rect.left + 'px',
                    'width:' + rect.width + 'px',
                    'height:' + rect.height + 'px',
                    'border:2px solid #06b6d4',
                    'background:rgba(6,182,212,0.12)',
                    'z-index:2147483644',
                    'pointer-events:none',
                    'box-sizing:border-box',
                    'border-radius:3px',
                    'transition:opacity 0.15s',
                ].join(';');
                // Pulsing animation
                ov.animate([
                    { borderColor: '#06b6d4', opacity: 1 },
                    { borderColor: '#22d3ee', opacity: 0.6 },
                    { borderColor: '#06b6d4', opacity: 1 },
                ], { duration: 1500, iterations: Infinity });

                // Index label for groups
                if (matches.length > 1) {
                    var idx = document.createElement('div');
                    idx.style.cssText = [
                        'position:absolute', 'top:-8px', 'right:-8px',
                        'font-size:9px', 'font-family:system-ui,sans-serif',
                        'background:#06b6d4', 'color:#fff',
                        'width:16px', 'height:16px', 'line-height:16px',
                        'text-align:center', 'border-radius:50%',
                        'font-weight:700',
                    ].join(';');
                    idx.textContent = String(pi + 1);
                    ov.appendChild(idx);
                }

                document.body.appendChild(ov);
            }

            return matches.length;
        } catch (e) {
            return 0;
        }
    }

    /** Remove all peek highlight overlays */
    function _peekClear() {
        var overlays = document.querySelectorAll('.__dcp_peek_ov');
        for (var ri = 0; ri < overlays.length; ri++) overlays[ri].remove();
    }

    function _closeAssertModal() {
        _removeScreenshotOverlay();
        _peekClear();
        _peekActive = false;
        var overlay = document.getElementById('__dcp_assert_overlay');
        if (overlay) overlay.remove();
        // Resume recording
        window.__dcp_recorder_paused = false;
        _dcpLog('info', 'Assert modal closed', { paused: false });
    }

    function _saveAssertion(selector) {
        var captureType = 'text';
        var capRadios = document.querySelectorAll('input[name="__dcp_cap"]');
        for (var i = 0; i < capRadios.length; i++) {
            if (capRadios[i].checked) { captureType = capRadios[i].value; break; }
        }

        var checkType = (document.getElementById('__dcp_check_type') || {}).value || 'text_contains';
        var expected = (document.getElementById('__dcp_expected') || {}).value || '';
        var caseSensitive = (document.getElementById('__dcp_case') || {}).checked;
        var attrName = (document.getElementById('__dcp_attr_name') || {}).value || '';

        var failMode = 'fail';
        var failRadios = document.querySelectorAll('input[name="__dcp_fail"]');
        for (var j = 0; j < failRadios.length; j++) {
            if (failRadios[j].checked) { failMode = failRadios[j].value; break; }
        }

        // Collect diagnostic config if diagnose-on-failure is enabled
        var diagnoseEnabled = (document.getElementById('__dcp_diag_toggle') || {}).checked || false;
        var diagnostics = [];
        if (diagnoseEnabled) {
            var tpls = document.querySelectorAll('input.__dcp_diag_tpl');
            for (var k = 0; k < tpls.length; k++) {
                if (tpls[k].checked) {
                    var diag = { type: tpls[k].value };
                    if (tpls[k].value === 'custom_js') {
                        diag.code = (document.getElementById('__dcp_diag_js_code') || {}).value || '';
                    }
                    diagnostics.push(diag);
                }
            }
        }

        // Map capture type to the correct backend action name
        var captureActionMap = {
            text: 'capture_text', html: 'capture_html', value: 'capture_value',
            attribute: 'capture_attribute', screenshot: 'capture_screenshot',
            state: 'capture_computed_style', console: 'capture_console',
        };

        // Resume recording BEFORE sending — sendEvent checks the paused flag
        window.__dcp_recorder_paused = false;
        _dcpLog('info', 'saveAssertion called', { selector: selector, captureType: captureType, checkType: checkType, expected: expected.slice(0, 50), diagnose: diagnoseEnabled });

        // Send assertion step back to DCP
        sendEvent({
            action: 'assert',
            selector: selector,
            assert_config: {
                capture_type: captureType,
                capture_action: captureActionMap[captureType] || 'capture_text',
                attribute_name: attrName,
                check_type: checkType,
                expected: expected,
                case_sensitive: caseSensitive,
                on_fail: {
                    mode: failMode,
                    diagnose: diagnoseEnabled,
                    diagnostics: diagnostics,
                },
            },
        });

        // Close modal (also sets paused=false, but we already did)
        _closeAssertModal();
    }


    // ═══════════════════════════════════════════════════════════
    //  I/O Config Modal (injected into target page)
    // ═══════════════════════════════════════════════════════════

    function _openIOModal(selector, elemText, elemRect, selectorChain) {
        selectorChain = selectorChain || [];
        var existing = document.getElementById('__dcp_io_overlay');
        if (existing) existing.remove();

        // Flush any pending debounced input events so the type step exists
        _flushPendingInputs();
        window.__dcp_recorder_paused = true;
        _dcpLog('info', 'I/O modal opened', { selector: selector, paused: true });

        var overlay = document.createElement('div');
        overlay.id = '__dcp_io_overlay';
        overlay.style.cssText = [
            'position:fixed', 'inset:0', 'z-index:2147483645',
            'display:flex', 'align-items:center', 'justify-content:center',
            'background:rgba(0,0,0,0.55)', 'backdrop-filter:blur(6px)',
            'font-family:system-ui,-apple-system,sans-serif',
        ].join(';');

        var C = {
            bg: '#1a1a2e', bgCard: '#16213e', bgInput: '#0f3460',
            border: '#2a2a4a', borderLight: '#3a3a5a',
            text: '#e0e0e8', textMuted: '#8888aa', textSecondary: '#b0b0cc',
            purple: '#8b5cf6', purpleHover: '#7c3aed',
            green: '#22c55e', warn: '#f59e0b',
        };

        var s = function (obj) {
            return Object.keys(obj).map(function (k) { return k + ':' + obj[k]; }).join(';');
        };

        var sLabel = s({ 'font-size': '11px', 'font-weight': '700', color: C.textMuted, 'text-transform': 'uppercase', 'letter-spacing': '0.5px', 'margin-bottom': '6px' });
        var sRadioLabel = s({ display: 'flex', 'align-items': 'center', gap: '5px', 'font-size': '12px', cursor: 'pointer', padding: '5px 8px', background: C.bgInput, 'border-radius': '5px', border: '1px solid ' + C.border, color: C.text });
        var sInputField = s({ 'font-size': '12px', padding: '5px 8px', background: C.bgInput, border: '1px solid ' + C.border, 'border-radius': '5px', color: C.text, width: '100%', 'box-sizing': 'border-box', outline: 'none', 'font-family': 'monospace' });
        var sBtn = function (bg) {
            return s({ 'font-size': '12px', 'font-weight': '600', padding: '6px 16px', border: 'none', 'border-radius': '6px', cursor: 'pointer', background: bg, color: '#fff' });
        };

        // ── Form element detection ──
        // Only form elements (input, textarea, select) can be INPUT.
        // Everything can be OUTPUT.
        function _isFormElement(sel) {
            try {
                var el = document.querySelector(sel);
                if (!el) return false;
                var tag = el.tagName.toLowerCase();
                if (tag === 'input' || tag === 'textarea' || tag === 'select') return true;
                var child = el.querySelector('input, textarea, select');
                if (child) return true;
            } catch (_) { }
            return false;
        }

        // Read element's live value (for default value / export preview)
        // Falls back to _lastTypedValues if element is gone
        function _readElementValue(sel) {
            try {
                var el = document.querySelector(sel);
                if (el) {
                    var tag = el.tagName.toLowerCase();
                    if (tag === 'input' || tag === 'textarea' || tag === 'select') {
                        return (el.value || '').trim();
                    }
                    return (el.textContent || '').trim().slice(0, 120);
                }
            } catch (_) { }
            // Fallback: use last typed value for this selector
            if (_lastTypedValues[sel]) return _lastTypedValues[sel];
            return '';
        }

        // §0: Target Element picker — always defaults to index 0 (the original element).
        // For I/O, we keep the original element selected even if it's gone from the page.
        // The selector will still work during replay.
        var chainHtml = '';
        if (selectorChain.length > 1) {
            for (var ci = 0; ci < selectorChain.length; ci++) {
                try {
                    selectorChain[ci].available = !!document.querySelector(selectorChain[ci].selector);
                } catch (_) {
                    selectorChain[ci].available = false;
                }
            }

            chainHtml += '<div>' +
                '<div style="' + sLabel + '">Target Element</div>' +
                '<div style="display:flex;flex-direction:column;gap:3px">';

            for (var ci2 = 0; ci2 < selectorChain.length; ci2++) {
                var item = selectorChain[ci2];
                var indent = ci2 === 0 ? '' : '\u21b3 '.repeat(ci2);
                var selPreview = item.selector.length > 40 ? item.selector.slice(0, 37) + '\u2026' : item.selector;
                // Always default to index 0 — the original clicked element
                var isDefault = (ci2 === 0);

                chainHtml += '<label style="' + sRadioLabel + ';padding:4px 8px">' +
                    '<input type="radio" name="__dcp_io_target" value="' + ci2 + '"' + (isDefault ? ' checked' : '') + '>' +
                    '<span style="font-size:11px">' + indent +
                    '<code style="color:' + C.purple + ';font-size:10px">&lt;' + item.tag + '&gt;</code> ' +
                    '<span style="font-family:monospace;font-size:9px;color:' + C.textSecondary + '">' + selPreview + '</span>' +
                    (item.available
                        ? '<span style="font-size:8px;color:' + C.green + ';margin-left:4px">\u2713</span>'
                        : '<span style="font-size:8px;color:' + C.warn + ';margin-left:4px" title="Not on page now \u2014 will work during replay">\u26a0</span>') +
                    '</span>' +
                    '</label>';
            }

            chainHtml += '</div></div>';
        }

        // Determine if INPUT is a valid option for the selected element
        // Check via querySelector first, fall back to selectorChain tag
        var canBeInput = _isFormElement(selector);
        if (!canBeInput && selectorChain.length > 0) {
            var tag0 = (selectorChain[0].tag || '').toLowerCase();
            if (tag0 === 'input' || tag0 === 'textarea' || tag0 === 'select') canBeInput = true;
        }
        // Form element → default INPUT; non-form → OUTPUT only
        var initIsInput = canBeInput;

        // §1: Mode toggle — only show if element can be both INPUT and OUTPUT
        var modeHtml = '';
        if (canBeInput) {
            modeHtml = '<div>' +
                '<div style="' + sLabel + '">I/O Type</div>' +
                '<div style="display:flex;gap:6px">' +
                '<label style="' + sRadioLabel + ';flex:1;justify-content:center;border-color:' + C.purple + '44">' +
                '<input type="radio" name="__dcp_io_mode" value="input" checked>' +
                '<span style="font-size:12px;color:' + C.purple + ';font-weight:600">\ud83d\udce5 Input</span>' +
                '</label>' +
                '<label style="' + sRadioLabel + ';flex:1;justify-content:center;border-color:' + C.green + '44">' +
                '<input type="radio" name="__dcp_io_mode" value="output">' +
                '<span style="font-size:12px;color:' + C.green + ';font-weight:600">\ud83d\udce4 Output</span>' +
                '</label>' +
                '</div>' +
                '</div>';
        }

        // Read current element value for defaults / preview
        var liveValue = _readElementValue(selector);
        var liveValueEsc = liveValue.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

        // §2: INPUT section — with editable default value field
        var inputHtml = '<div id="__dcp_io_input_section" style="' + (initIsInput ? '' : 'display:none') + '">' +
            '<div style="padding:10px;border:1px solid ' + C.purple + '33;border-radius:8px;background:' + C.purple + '0a">' +
            '<div style="font-size:11px;font-weight:600;color:' + C.purple + ';margin-bottom:6px">\ud83d\udce5 Input \u2014 Suite Parameter</div>' +
            '<div style="font-size:10px;color:' + C.textMuted + ';margin-bottom:8px">This value becomes configurable when running the suite</div>' +
            '<div style="' + sLabel + '">Variable Name</div>' +
            '<input id="__dcp_io_var_name" type="text" placeholder="LOGIN_EMAIL" style="' + sInputField + ';margin-bottom:8px">' +
            '<div style="' + sLabel + '">Default Value</div>' +
            '<input id="__dcp_io_default_value" type="text" value="' + liveValueEsc + '" placeholder="Pre-populated from element" style="' + sInputField + '">' +
            '<div style="font-size:9px;color:' + C.textMuted + ';margin-top:4px">Editable \u2014 this default is used when no runtime value is provided</div>' +
            '</div></div>';

        // §3: OUTPUT section — with capture type picker + live preview
        var outputHtml = '<div id="__dcp_io_output_section" style="' + (initIsInput ? 'display:none' : '') + '">' +
            '<div style="padding:10px;border:1px solid ' + C.green + '33;border-radius:8px;background:' + C.green + '0a">' +
            '<div style="font-size:11px;font-weight:600;color:' + C.green + ';margin-bottom:6px">\ud83d\udce4 Output \u2014 Export</div>' +
            '<div style="font-size:10px;color:' + C.textMuted + ';margin-bottom:8px">The captured value will be exported to the plan namespace</div>' +

            // Capture type picker
            '<div style="' + sLabel + '">Capture Type</div>' +
            '<select id="__dcp_io_capture_type" style="' + sInputField + ';margin-bottom:6px">' +
            '<option value="capture_text">\ud83d\udccb Text content</option>' +
            '<option value="capture_html">\ud83d\udcdd HTML</option>' +
            '<option value="capture_value"' + (canBeInput ? ' selected' : '') + '>\ud83d\udd22 Value (form fields)</option>' +
            '<option value="capture_attribute">\ud83c\udff7\ufe0f Attribute (href, data-id\u2026)</option>' +
            '<option value="capture_url">\ud83d\udd17 URL</option>' +
            '<option value="capture_computed_style">\ud83c\udfa8 Computed style</option>' +
            '</select>' +

            // Attribute name — select with auto-detected attrs + Custom option
            '<div id="__dcp_io_attr_row" style="display:none;margin-bottom:6px">' +
            '<div style="' + sLabel + '">Attribute Name</div>' +
            '<select id="__dcp_io_attr_select" style="' + sInputField + ';margin-bottom:4px">' +
            '<option value="" disabled selected>Select attribute\u2026</option>' +
            '</select>' +
            '<input id="__dcp_io_attr_name" type="text" placeholder="Custom attribute name" style="' + sInputField + ';display:none">' +
            '</div>' +

            // CSS property — select with common props + Custom option
            '<div id="__dcp_io_css_row" style="display:none;margin-bottom:6px">' +
            '<div style="' + sLabel + '">CSS Property</div>' +
            '<select id="__dcp_io_css_select" style="' + sInputField + ';margin-bottom:4px">' +
            '<option value="" disabled selected>Select property\u2026</option>' +
            '<option value="color">color</option>' +
            '<option value="background-color">background-color</option>' +
            '<option value="display">display</option>' +
            '<option value="visibility">visibility</option>' +
            '<option value="opacity">opacity</option>' +
            '<option value="font-size">font-size</option>' +
            '<option value="font-weight">font-weight</option>' +
            '<option value="width">width</option>' +
            '<option value="height">height</option>' +
            '<option value="margin">margin</option>' +
            '<option value="padding">padding</option>' +
            '<option value="border">border</option>' +
            '<option value="position">position</option>' +
            '<option value="z-index">z-index</option>' +
            '<option value="overflow">overflow</option>' +
            '<option value="text-align">text-align</option>' +
            '<option value="__custom__">Custom\u2026</option>' +
            '</select>' +
            '<input id="__dcp_io_css_prop" type="text" placeholder="Custom CSS property" style="' + sInputField + ';display:none">' +
            '</div>' +

            // Export name
            '<div style="' + sLabel + '">Export Name</div>' +
            '<input id="__dcp_io_export_name" type="text" placeholder="AUTH_TOKEN" style="' + sInputField + ';margin-bottom:6px">' +

            // Live preview (updated dynamically)
            '<div id="__dcp_io_preview" style="font-size:10px;color:' + C.textMuted + ';margin-top:4px"></div>' +
            '<div style="font-size:9px;color:' + C.textMuted + ';margin-top:2px">Available as a named output for downstream suites</div>' +
            '</div></div>';

        overlay.innerHTML =
            '<div style="' + s({
                background: C.bg, border: '1px solid ' + C.purple + '44', 'border-radius': '12px',
                width: '440px', 'max-width': '92vw', 'max-height': '85vh', 'overflow-y': 'auto',
                'box-shadow': '0 20px 60px rgba(0,0,0,0.6)', color: C.text,
            }) + '">' +
            '<div style="' + s({ padding: '14px 18px 10px', 'border-bottom': '1px solid ' + C.border, display: 'flex', 'align-items': 'center', gap: '8px' }) + '">' +
            '<span style="font-size:16px">\ud83d\udd17</span>' +
            '<div style="flex:1">' +
            '<div style="font-weight:700;font-size:14px">I/O Configuration</div>' +
            '<div id="__dcp_io_header_selector" style="font-size:10px;color:' + C.textMuted + ';font-family:monospace;margin-top:2px"></div>' +
            '</div>' +
            '<button id="__dcp_io_peek_toggle" title="Peek: highlight matched element(s)" style="' + s({
                'font-size': '12px', padding: '4px 10px', border: '1px solid ' + C.border,
                'border-radius': '6px', cursor: 'pointer', background: C.bgInput, color: C.text,
                display: 'flex', 'align-items': 'center', gap: '4px', 'flex-shrink': '0',
            }) + '">👁 Peek</button>' +
            '</div>' +
            '<div style="padding:12px 18px;display:flex;flex-direction:column;gap:12px">' +
            chainHtml +
            modeHtml +
            inputHtml +
            outputHtml +
            '<div style="display:flex;justify-content:flex-end;gap:8px;margin-top:4px">' +
            '<button id="__dcp_io_cancel" style="' + sBtn(C.border) + '">Cancel</button>' +
            '<button id="__dcp_io_save" style="' + sBtn(C.purple) + '">\ud83d\udcbe Save I/O</button>' +
            '</div></div></div>';

        document.body.appendChild(overlay);

        var headerSel = document.getElementById('__dcp_io_header_selector');
        if (headerSel) headerSel.textContent = selector.slice(0, 70);

        var _currentIsInput = initIsInput;

        function _showSection(isInput) {
            var inSec = document.getElementById('__dcp_io_input_section');
            var outSec = document.getElementById('__dcp_io_output_section');
            if (inSec) inSec.style.display = isInput ? '' : 'none';
            if (outSec) outSec.style.display = isInput ? 'none' : '';
            _currentIsInput = isInput;
        }

        // Mark default value as user-edited so we don't overwrite changes
        var defValEl = document.getElementById('__dcp_io_default_value');
        if (defValEl) {
            defValEl.addEventListener('input', function () { this._userEdited = true; });
        }

        // Mode toggle — user clicks INPUT or OUTPUT (only exists for form elements)
        var modeRadios = overlay.querySelectorAll('input[name="__dcp_io_mode"]');
        for (var mi = 0; mi < modeRadios.length; mi++) {
            modeRadios[mi].addEventListener('change', function () {
                _showSection(this.value === 'input');
            });
        }

        // Target element selection — update selector, re-check form status
        var targetRadios = overlay.querySelectorAll('input[name="__dcp_io_target"]');
        for (var ti = 0; ti < targetRadios.length; ti++) {
            targetRadios[ti].addEventListener('change', function () {
                var idx = parseInt(this.value, 10);
                if (selectorChain[idx]) {
                    selector = selectorChain[idx].selector;
                    if (headerSel) headerSel.textContent = selector.slice(0, 70);
                    var nowCanInput = _isFormElement(selector);

                    // If element can't be INPUT, force OUTPUT
                    if (!nowCanInput && _currentIsInput) {
                        _showSection(false);
                        for (var ri = 0; ri < modeRadios.length; ri++) {
                            modeRadios[ri].checked = (modeRadios[ri].value === 'output');
                        }
                    }

                    // Update default value field if not user-edited
                    var dEl = document.getElementById('__dcp_io_default_value');
                    if (dEl && !dEl._userEdited) {
                        dEl.value = _readElementValue(selector);
                    }
                }
            });

            // Hover-to-peek on chain labels — ONLY when peek mode is ON
            var label = targetRadios[ti].closest('label');
            if (label) {
                (function (radio) {
                    // Save original inline styles before any hover modification
                    label._origBg = label.style.background;
                    label._origBorderColor = label.style.borderColor;
                    label._origBoxShadow = label.style.boxShadow || 'none';
                    label._origTransform = label.style.transform || 'none';
                    label.addEventListener('mouseenter', function () {
                        if (!_peekActive) return;
                        var idx = parseInt(radio.value, 10);
                        var item = selectorChain[idx];
                        if (!item) return;
                        if (!item.available) {
                            // Highlight entire label row as gone
                            var warnSpan = this.querySelector('span[title]');
                            if (warnSpan) {
                                warnSpan.style.fontSize = '16px';
                                warnSpan.style.textShadow = '0 0 12px rgba(245,158,11,0.9)';
                            }
                            this.style.background = 'rgba(245,158,11,0.45)';
                            this.style.borderColor = '#f59e0b';
                            this.style.boxShadow = '0 0 16px rgba(245,158,11,0.5)';
                            this.style.transform = 'scale(1.02)';
                        } else {
                            _peekHighlight(item.selector);
                            _ioPeekOn();
                        }
                    });
                    label.addEventListener('mouseleave', function () {
                        if (!_peekActive) return;
                        _peekClear();
                        _ioPeekOff();
                        // Restore original styles
                        var warnSpan = this.querySelector('span[title]');
                        if (warnSpan) {
                            warnSpan.style.fontSize = '8px';
                            warnSpan.style.textShadow = 'none';
                        }
                        this.style.background = this._origBg;
                        this.style.borderColor = this._origBorderColor;
                        this.style.boxShadow = this._origBoxShadow;
                        this.style.transform = this._origTransform;
                    });
                })(targetRadios[ti]);
            }
        }

        // ── Peek mode (IO modal) ──
        var ioPeekBtn = document.getElementById('__dcp_io_peek_toggle');
        var _ioModal = overlay.querySelector('div');
        function _ioPeekOn() {
            overlay.style.background = 'rgba(0,0,0,0.05)';
            overlay.style.backdropFilter = 'none';
            overlay.style.webkitBackdropFilter = 'none';
            if (_ioModal) _ioModal.style.opacity = '0.25';
        }
        function _ioPeekOff() {
            overlay.style.background = 'rgba(0,0,0,0.55)';
            overlay.style.backdropFilter = 'blur(6px)';
            overlay.style.webkitBackdropFilter = 'blur(6px)';
            if (_ioModal) _ioModal.style.opacity = '1';
        }
        if (ioPeekBtn) {
            // Click: toggle peek mode (no immediate highlight)
            ioPeekBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                _peekActive = !_peekActive;
                if (_peekActive) {
                    this.textContent = '👁 Peek ON';
                    this.style.borderColor = '#06b6d4';
                    this.style.color = '#06b6d4';
                } else {
                    _peekClear();
                    this.textContent = '👁 Peek';
                    this.style.borderColor = C.border;
                    this.style.color = C.text;
                    _ioPeekOff();
                }
            });
            // Hover peek button: preview opposite state
            ioPeekBtn.addEventListener('mouseenter', function () {
                if (_peekActive) {
                    _peekClear();
                    _ioPeekOff();
                } else {
                    var found = _peekHighlight(selector);
                    if (found === 0) {
                        // Element is gone — highlight the ⚠ on currently selected label
                        var selRadio = overlay.querySelector('input[name="__dcp_io_target"]:checked');
                        if (selRadio) {
                            var selLabel = selRadio.closest('label');
                            if (selLabel) {
                                var ws = selLabel.querySelector('span[title]');
                                if (ws) {
                                    ws.style.fontSize = '16px';
                                    ws.style.textShadow = '0 0 12px rgba(245,158,11,0.9)';
                                }
                                selLabel.style.background = 'rgba(245,158,11,0.45)';
                                selLabel.style.borderColor = '#f59e0b';
                                selLabel.style.boxShadow = '0 0 16px rgba(245,158,11,0.5)';
                            }
                        }
                    }
                    _ioPeekOn();
                }
            });
            ioPeekBtn.addEventListener('mouseleave', function () {
                _peekClear();
                _ioPeekOff();
                // Restore any gone-element label highlight
                var labels = overlay.querySelectorAll('input[name="__dcp_io_target"]');
                for (var li = 0; li < labels.length; li++) {
                    var lbl = labels[li].closest('label');
                    if (lbl) {
                        var ws = lbl.querySelector('span[title]');
                        if (ws) { ws.style.fontSize = '8px'; ws.style.textShadow = 'none'; }
                        lbl.style.background = lbl._origBg || '';
                        lbl.style.borderColor = lbl._origBorderColor || '';
                        lbl.style.boxShadow = lbl._origBoxShadow || 'none';
                    }
                }
            });
        }

        // ── Capture type picker — show/hide attribute/css fields + populate datalist + update preview ──
        function _updateIOPreview() {
            var previewEl = document.getElementById('__dcp_io_preview');
            if (!previewEl) return;
            var capType = (document.getElementById('__dcp_io_capture_type') || {}).value || 'capture_text';
            try {
                var el = document.querySelector(selector);
                if (!el) {
                    previewEl.innerHTML = 'Element not currently visible \u2014 value will be captured during replay';
                    return;
                }
                var val = '';
                if (capType === 'capture_text') val = (el.textContent || '').trim();
                else if (capType === 'capture_html') val = el.innerHTML.trim();
                else if (capType === 'capture_value') val = el.value || '';
                else if (capType === 'capture_attribute') {
                    var attrSel = document.getElementById('__dcp_io_attr_select');
                    var attrCustom = document.getElementById('__dcp_io_attr_name');
                    var attrName = '';
                    if (attrSel && attrSel.value && attrSel.value !== '__custom__' && attrSel.value !== '') attrName = attrSel.value;
                    else if (attrCustom) attrName = attrCustom.value.trim();
                    val = attrName ? (el.getAttribute(attrName) || '[null]') : '[select attribute]';
                } else if (capType === 'capture_url') val = window.location.href;
                else if (capType === 'capture_computed_style') {
                    var cssSel = document.getElementById('__dcp_io_css_select');
                    var cssCustom = document.getElementById('__dcp_io_css_prop');
                    var cssProp = '';
                    if (cssSel && cssSel.value && cssSel.value !== '__custom__' && cssSel.value !== '') cssProp = cssSel.value;
                    else if (cssCustom) cssProp = cssCustom.value.trim();
                    val = cssProp ? (window.getComputedStyle(el).getPropertyValue(cssProp) || '[empty]') : '[select property]';
                }
                var escaped = val.replace(/</g, '&lt;').replace(/>/g, '&gt;');
                previewEl.innerHTML = 'Preview: <code style="font-size:9px;padding:1px 4px;background:' + C.bgCard + ';border-radius:3px;color:' + C.green + '">' + escaped.slice(0, 80) + '</code>';
            } catch (_) {
                previewEl.innerHTML = 'Element not currently visible \u2014 value will be captured during replay';
            }
        }

        var capTypeSelect = document.getElementById('__dcp_io_capture_type');
        if (capTypeSelect) {
            capTypeSelect.addEventListener('change', function () {
                var v = this.value;
                var attrRow = document.getElementById('__dcp_io_attr_row');
                var cssRow = document.getElementById('__dcp_io_css_row');
                if (attrRow) attrRow.style.display = v === 'capture_attribute' ? '' : 'none';
                if (cssRow) cssRow.style.display = v === 'capture_computed_style' ? '' : 'none';

                // Populate attribute select from element's actual attributes
                if (v === 'capture_attribute') {
                    try {
                        var targetEl = document.querySelector(selector);
                        var attrSelect = document.getElementById('__dcp_io_attr_select');
                        if (targetEl && attrSelect) {
                            attrSelect.innerHTML = '<option value="" disabled selected>Select attribute\u2026</option>';
                            var attrs = targetEl.attributes;
                            for (var ai = 0; ai < attrs.length; ai++) {
                                var opt = document.createElement('option');
                                opt.value = attrs[ai].name;
                                opt.textContent = attrs[ai].name + ' = "' + (attrs[ai].value || '').slice(0, 30) + '"';
                                attrSelect.appendChild(opt);
                            }
                            var customOpt = document.createElement('option');
                            customOpt.value = '__custom__';
                            customOpt.textContent = 'Custom\u2026';
                            attrSelect.appendChild(customOpt);
                        }
                    } catch (_) { }
                }
                _updateIOPreview();
            });
        }

        // Attribute select → show/hide custom input + refresh preview
        var ioAttrSelect = document.getElementById('__dcp_io_attr_select');
        var ioAttrInput = document.getElementById('__dcp_io_attr_name');
        if (ioAttrSelect) {
            ioAttrSelect.addEventListener('change', function () {
                if (this.value === '__custom__') {
                    if (ioAttrInput) { ioAttrInput.style.display = ''; ioAttrInput.focus(); }
                } else {
                    if (ioAttrInput) { ioAttrInput.style.display = 'none'; ioAttrInput.value = ''; }
                }
                _updateIOPreview();
            });
        }
        if (ioAttrInput) {
            ioAttrInput.addEventListener('input', function () { _updateIOPreview(); });
        }

        // CSS select → show/hide custom input + refresh preview
        var ioCssSelect = document.getElementById('__dcp_io_css_select');
        var ioCssInput = document.getElementById('__dcp_io_css_prop');
        if (ioCssSelect) {
            ioCssSelect.addEventListener('change', function () {
                if (this.value === '__custom__') {
                    if (ioCssInput) { ioCssInput.style.display = ''; ioCssInput.focus(); }
                } else {
                    if (ioCssInput) { ioCssInput.style.display = 'none'; ioCssInput.value = ''; }
                }
                _updateIOPreview();
            });
        }
        if (ioCssInput) {
            ioCssInput.addEventListener('input', function () { _updateIOPreview(); });
        }



        // Initial preview
        _updateIOPreview();

        document.getElementById('__dcp_io_cancel').addEventListener('click', function () {
            _closeIOModal();
        });

        document.getElementById('__dcp_io_save').addEventListener('click', function () {
            _saveIO(selector, _currentIsInput);
        });

        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) _closeIOModal();
        });
    }

    function _closeIOModal() {
        _peekClear();
        _peekActive = false;
        var overlay = document.getElementById('__dcp_io_overlay');
        if (overlay) overlay.remove();
        window.__dcp_recorder_paused = false;
        _dcpLog('info', 'I/O modal closed, recording resumed');
    }

    function _saveIO(selector, isInput) {
        var ioType, name, defaultValue = '';
        var captureType = '', attributeName = '', cssProp = '';

        if (isInput) {
            // INPUT: variable name + user-editable default
            var varName = (document.getElementById('__dcp_io_var_name') || {}).value || '';
            varName = varName.trim();
            if (!varName) {
                var inp = document.getElementById('__dcp_io_var_name');
                if (inp) { inp.style.border = '2px solid #ef4444'; setTimeout(function () { inp.style.border = ''; }, 1500); }
                return;
            }
            ioType = 'input';
            name = varName;
            // Read default from the editable field (user may have changed it)
            var defEl = document.getElementById('__dcp_io_default_value');
            defaultValue = defEl ? defEl.value.trim() : '';
        } else {
            // OUTPUT: export name + capture type
            var exportName = (document.getElementById('__dcp_io_export_name') || {}).value || '';
            exportName = exportName.trim();
            if (!exportName) {
                var inp2 = document.getElementById('__dcp_io_export_name');
                if (inp2) { inp2.style.border = '2px solid #ef4444'; setTimeout(function () { inp2.style.border = ''; }, 1500); }
                return;
            }
            ioType = 'output';
            name = exportName;

            // Read capture type
            var capTypeEl = document.getElementById('__dcp_io_capture_type');
            if (capTypeEl) captureType = capTypeEl.value;

            // Read attribute name (for capture_attribute)
            if (captureType === 'capture_attribute') {
                var attrSel = document.getElementById('__dcp_io_attr_select');
                if (attrSel && attrSel.value && attrSel.value !== '__custom__' && attrSel.value !== '') {
                    attributeName = attrSel.value;
                } else {
                    attributeName = (document.getElementById('__dcp_io_attr_name') || {}).value || '';
                    attributeName = attributeName.trim();
                }
                if (!attributeName) {
                    var attrInp = document.getElementById('__dcp_io_attr_select') || document.getElementById('__dcp_io_attr_name');
                    if (attrInp) { attrInp.style.border = '2px solid #ef4444'; setTimeout(function () { attrInp.style.border = ''; }, 1500); }
                    return;
                }
            }

            // Read CSS property (for capture_computed_style)
            if (captureType === 'capture_computed_style') {
                var cssSel = document.getElementById('__dcp_io_css_select');
                if (cssSel && cssSel.value && cssSel.value !== '__custom__' && cssSel.value !== '') {
                    cssProp = cssSel.value;
                } else {
                    cssProp = (document.getElementById('__dcp_io_css_prop') || {}).value || '';
                    cssProp = cssProp.trim();
                }
                if (!cssProp) {
                    var cssInp = document.getElementById('__dcp_io_css_select') || document.getElementById('__dcp_io_css_prop');
                    if (cssInp) { cssInp.style.border = '2px solid #ef4444'; setTimeout(function () { cssInp.style.border = ''; }, 1500); }
                    return;
                }
            }
        }

        // Resume recording BEFORE sending
        window.__dcp_recorder_paused = false;
        _dcpLog('info', 'saveIO called', { selector: selector, isInput: isInput, ioType: ioType, name: name, captureType: captureType });

        // Send I/O config via the event endpoint
        if (isInput) {
            // INPUT modifies an existing step's value → use io_configure
            var payload = {
                action: 'io_configure',
                selector: selector,
                io_type: 'input',
                name: name,
                default_value: defaultValue,
            };
            sendEvent(payload);
        } else {
            // OUTPUT creates a capture step directly (proper recording flow)
            var payload = {
                action: captureType || 'capture_text',
                selector: selector,
                export_as: name,
            };
            if (attributeName) payload.assertion_attribute = attributeName;
            if (cssProp) payload.assertion_attribute = cssProp;
            // Carry element metadata for the capture step
            try {
                var el = document.querySelector(selector);
                if (el) {
                    payload.element_tag = el.tagName.toLowerCase();
                    payload.element_text = (el.textContent || '').slice(0, 200).trim();
                    var rect = el.getBoundingClientRect();
                    payload.element_rect = { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
                }
            } catch (_) { }
            payload.page_url = location.href;
            sendEvent(payload);
        }

        _closeIOModal();
    }


    document.addEventListener('input', function (e) {
        if (window.__dcp_recorder_paused) return;

        var el = e.target;
        if (!el || !el.tagName) return;
        var tag = el.tagName.toLowerCase();
        if (tag !== 'input' && tag !== 'textarea' && !el.isContentEditable) return;

        // For password fields, record that typing happened but not the value
        var isPassword = el.type === 'password';

        // Use element identity for debounce key
        var key = buildSelector(el);
        // Track value immediately (before debounce) — ensures _readElementValue
        // always has the latest value even if the I/O modal opens before debounce fires
        if (!isPassword) _lastTypedValues[key] = el.value;
        if (_inputTimers[key]) clearTimeout(_inputTimers[key].timerId);

        _inputTimers[key] = {
            el: el,
            isPassword: isPassword,
            timerId: setTimeout(function () {
                delete _inputTimers[key];
                var sel = buildSelector(el);
                // Track last typed value for default value fallback
                if (!isPassword) _lastTypedValues[sel] = el.value;
                sendEvent({
                    action: 'type',
                    selector: buildSelector(el),
                    xpath: buildXPath(el),
                    selector_alternatives: buildAlternatives(el),
                    value: isPassword ? '' : el.value,
                    element_tag: tag,
                    element_text: '',
                    element_rect: getRect(el),
                    is_password: isPassword,
                });
            }, _INPUT_DEBOUNCE),
        };
    }, true);


    // ── Focus capture — snapshot element value on focus ────────
    // Captures the current value of any input/textarea/select on focus,
    // regardless of how focus was acquired (click, tab, JS, etc.).
    // This ensures _lastTypedValues always has the freshest value.
    document.addEventListener('focusin', function (e) {
        if (window.__dcp_recorder_paused) return;
        var el = e.target;
        if (!el || !el.tagName) return;
        var tag = el.tagName.toLowerCase();
        if (tag !== 'input' && tag !== 'textarea' && tag !== 'select') return;
        var sel = buildSelector(el);
        _lastTypedValues[sel] = el.value || '';
    }, true);


    // ── Select change ─────────────────────────────────────────

    document.addEventListener('change', function (e) {
        if (window.__dcp_recorder_paused) return;

        var el = e.target;
        if (!el || el.tagName.toLowerCase() !== 'select') return;

        sendEvent({
            action: 'select',
            selector: buildSelector(el),
            xpath: buildXPath(el),
            selector_alternatives: buildAlternatives(el),
            value: el.value,
            element_tag: 'select',
            element_text: el.options[el.selectedIndex]
                ? el.options[el.selectedIndex].text : '',
            element_rect: getRect(el),
        });
    }, true);


    // ── Key press (Enter, Escape, Tab) ────────────────────────

    document.addEventListener('keydown', function (e) {
        if (window.__dcp_recorder_paused) return;

        // Only capture significant keys
        if (e.key !== 'Enter' && e.key !== 'Escape' && e.key !== 'Tab') return;

        var el = e.target;
        sendEvent({
            action: 'keypress',
            selector: buildSelector(el),
            xpath: buildXPath(el),
            value: e.key,
            element_tag: el.tagName.toLowerCase(),
            element_text: '',
            element_rect: getRect(el),
        });
    }, true);


    // ── Navigation ────────────────────────────────────────────

    // SPA: pushState / replaceState interception
    var _origPushState = history.pushState;
    var _origReplaceState = history.replaceState;

    history.pushState = function () {
        _origPushState.apply(this, arguments);
        _checkNavigation();
    };
    history.replaceState = function () {
        _origReplaceState.apply(this, arguments);
        _checkNavigation();
    };

    window.addEventListener('popstate', function () {
        _checkNavigation();
    });

    window.addEventListener('hashchange', function () {
        _checkNavigation();
    });

    // Traditional navigation: beforeunload
    window.addEventListener('beforeunload', function () {
        if (_lastUrl !== location.href) {
            sendEvent({
                action: 'navigate',
                value: location.href,
            });
        }
    });

    function _checkNavigation() {
        var newUrl = location.href;
        if (newUrl !== _lastUrl) {
            _lastUrl = newUrl;
            sendEvent({
                action: 'navigate',
                value: newUrl,
            });
        }
    }


    // ═══════════════════════════════════════════════════════════
    //  Visual Indicator
    // ═══════════════════════════════════════════════════════════

    var indicator = document.createElement('div');
    indicator.id = '__dcp_recorder_indicator';
    indicator.style.cssText = [
        'position:fixed', 'top:8px', 'right:8px', 'z-index:2147483647',
        'background:rgba(220,38,38,0.9)', 'color:white',
        'font-family:system-ui,-apple-system,sans-serif',
        'font-size:11px', 'padding:4px 10px', 'border-radius:12px',
        'display:flex', 'align-items:center', 'gap:6px',
        'box-shadow:0 2px 8px rgba(0,0,0,0.3)',
        'pointer-events:none', 'user-select:none',
    ].join(';');

    function _updateIndicator(status) {
        if (status === 'blocked') {
            indicator.style.background = 'rgba(234,179,8,0.95)';
            indicator.style.color = '#000';
            indicator.style.pointerEvents = 'auto';
            indicator.innerHTML =
                '<span style="font-size:14px">⚠️</span>' +
                '<span>DCP Recording — <b>Ad blocker detected!</b> ' +
                'Disable it for localhost to capture events.</span>';
        } else {
            indicator.style.background = 'rgba(220,38,38,0.9)';
            indicator.style.color = '#fff';
            indicator.style.pointerEvents = 'none';
            indicator.innerHTML =
                '<span style="width:8px;height:8px;background:#fff;border-radius:50%;' +
                'animation:__dcp_rec_pulse 1.5s ease-in-out infinite"></span>' +
                '<span>DCP Recording</span>';
        }
    }

    _updateIndicator('ok');

    // Pulse animation + badge animation
    var style = document.createElement('style');
    style.textContent =
        '@keyframes __dcp_rec_pulse {' +
        '0%,100%{opacity:1} 50%{opacity:0.3}' +
        '}' +
        '@keyframes __dcp_badge_in {' +
        '0%{opacity:0;transform:scale(0.8) translateY(4px)} 100%{opacity:1;transform:scale(1) translateY(0)}' +
        '}';
    document.head.appendChild(style);
    document.body.appendChild(indicator);

    // ── Ad blocker detection: send a test ping ───────────────
    try {
        fetch(DCP_CALLBACK, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: window.__dcp_session_id || SESSION_ID, action: 'ping' }),
            mode: 'cors',
            credentials: 'omit',
        }).catch(function () {
            _sendFailed = true;
            _updateIndicator('blocked');
        });
    } catch (_) {
        _sendFailed = true;
        _updateIndicator('blocked');
    }


    // ═══════════════════════════════════════════════════════════
    //  Cleanup function (called when recording stops)
    // ═══════════════════════════════════════════════════════════

    window.__dcp_recorder_cleanup = function () {
        // Remove listeners by replacing history methods
        history.pushState = _origPushState;
        history.replaceState = _origReplaceState;

        // Remove visual indicator
        var ind = document.getElementById('__dcp_recorder_indicator');
        if (ind) ind.remove();
        var sty = document.querySelector('style');
        if (sty && sty.textContent.indexOf('__dcp_rec_pulse') !== -1) {
            sty.remove();
        }

        // Remove assertion UI
        var assertOverlay = document.getElementById('__dcp_assert_overlay');
        if (assertOverlay) assertOverlay.remove();
        var badges = document.querySelectorAll('.__dcp_assert_badge');
        for (var bi = 0; bi < badges.length; bi++) badges[bi].remove();

        // Remove IO modal
        var ioOverlay = document.getElementById('__dcp_io_overlay');
        if (ioOverlay) ioOverlay.remove();

        // Remove peek overlays
        var peekOvs = document.querySelectorAll('.__dcp_peek_ov');
        for (var pi = 0; pi < peekOvs.length; pi++) peekOvs[pi].remove();

        // Clear state
        window.__dcp_recorder_active = false;
        window.__dcp_recorder_paused = false;
        window.__dcp_recorder_cleanup = null;

        // Restore original console methods
        if (window.__cdp_console_originals) {
            console.log = window.__cdp_console_originals.log;
            console.warn = window.__cdp_console_originals.warn;
            console.error = window.__cdp_console_originals.error;
            console.info = window.__cdp_console_originals.info;
            delete window.__cdp_console_originals;
            delete window.__cdp_console_buffer;
        }
    };

    return 'injected';
})();
