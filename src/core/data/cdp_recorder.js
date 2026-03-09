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
    var _inputTimers = {};       // debounce timers per element
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
    var _badgeTimer = null;

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
        if (_badgeTimer) { clearTimeout(_badgeTimer); _badgeTimer = null; }

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
            'z-index:2147483646',
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

        // Auto-dismiss after 4s
        _badgeTimer = setTimeout(function () {
            if (_lastBadge === badge) {
                badge.style.opacity = '0';
                badge.style.transition = 'opacity 0.3s';
                setTimeout(function () { badge.remove(); }, 300);
                _lastBadge = null;
            }
        }, 4000);
    }


    // ═══════════════════════════════════════════════════════════
    //  Assertion Config Modal (injected into target page)
    // ═══════════════════════════════════════════════════════════

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

        // Assertion check types
        var checkGroups = [
            {
                label: 'Text', checks: [
                    ['text_equals', 'Text equals'], ['text_contains', 'Text contains'],
                    ['text_not_contains', 'Text not contains'], ['text_starts_with', 'Starts with'],
                    ['text_ends_with', 'Ends with'], ['text_matches', 'Matches regex'],
                    ['text_empty', 'Text empty'], ['text_not_empty', 'Text not empty'],
                ]
            },
            {
                label: 'Value', checks: [
                    ['value_equals', 'Value equals'], ['value_contains', 'Value contains'],
                    ['value_empty', 'Value empty'], ['value_not_empty', 'Value not empty'],
                ]
            },
            {
                label: 'Attribute', checks: [
                    ['attribute_equals', 'Attr equals'], ['attribute_contains', 'Attr contains'],
                    ['attribute_exists', 'Attr exists'], ['attribute_not_exists', 'Attr absent'],
                ]
            },
            {
                label: 'Element', checks: [
                    ['exists', 'Exists'], ['not_exists', 'Absent'],
                    ['visible', 'Visible'], ['hidden', 'Hidden'],
                    ['enabled', 'Enabled'], ['disabled', 'Disabled'],
                    ['checked', 'Checked'], ['not_checked', 'Unchecked'],
                ]
            },
            {
                label: 'CSS', checks: [
                    ['css_class_present', 'Has class'], ['css_class_absent', 'No class'],
                    ['css_property_equals', 'CSS prop ='],
                ]
            },
            {
                label: 'Count', checks: [
                    ['count_equals', 'Count ='], ['count_gt', 'Count >'], ['count_lt', 'Count <'],
                ]
            },
            {
                label: 'Page', checks: [
                    ['url_equals', 'URL equals'], ['url_contains', 'URL contains'],
                    ['title_equals', 'Title equals'], ['title_contains', 'Title contains'],
                ]
            },
        ];

        var optgroupHtml = '';
        checkGroups.forEach(function (g) {
            optgroupHtml += '<optgroup label="' + g.label + '">';
            g.checks.forEach(function (c) {
                var sel = c[0] === 'text_contains' ? ' selected' : '';
                optgroupHtml += '<option value="' + c[0] + '"' + sel + '>' + c[1] + '</option>';
            });
            optgroupHtml += '</optgroup>';
        });

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
            '<div>' +
            '<div style="font-weight:700;font-size:14px">Assertion Configuration</div>' +
            '<div id="__dcp_header_selector" style="font-size:10px;color:' + C.textMuted + ';font-family:monospace;margin-top:2px"></div>' +
            '</div>' +
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
                    chainHtml += '<div style="font-size:10px;color:' + C.warn + ';margin-top:4px;padding:4px 8px;background:rgba(245,158,11,0.1);border-radius:4px">' +
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
            '<input id="__dcp_attr_name" type="text" placeholder="Attribute name (e.g. data-status, href)" style="' + sInput + '">' +
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
            '<div style="display:flex;flex-direction:column;gap:3px">' +
            '<label style="' + sRadioLabel + ';padding:3px 8px"><input type="checkbox" class="__dcp_diag_tpl" value="screenshot" checked> 📸 Screenshot</label>' +
            '<label style="' + sRadioLabel + ';padding:3px 8px"><input type="checkbox" class="__dcp_diag_tpl" value="console"> 🖥️ Console dump</label>' +
            '<label style="' + sRadioLabel + ';padding:3px 8px"><input type="checkbox" class="__dcp_diag_tpl" value="element_state"> 🔍 Element state (styles, attrs)</label>' +
            '<label style="' + sRadioLabel + ';padding:3px 8px"><input type="checkbox" class="__dcp_diag_tpl" value="page_html"> 📄 Page HTML snapshot</label>' +
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
                        // Update header
                        var hs = document.getElementById('__dcp_header_selector');
                        if (hs) hs.textContent = picked.selector.slice(0, 80);
                        // Read current capture type (don't assume 'text')
                        var curCapType = 'text';
                        var cRadios = document.querySelectorAll('input[name="__dcp_cap"]');
                        for (var ci = 0; ci < cRadios.length; ci++) {
                            if (cRadios[ci].checked) { curCapType = cRadios[ci].value; break; }
                        }
                        // Update live preview with the correct capture type
                        _refreshPreview(ctx.selector, curCapType);
                        _dcpLog('info', 'Target changed', { idx: idx, selector: ctx.selector, captureType: curCapType });
                    }
                });
            }
        }

        // Capture type → show/hide attribute input + refresh preview
        var capRadios = overlay.querySelectorAll('input[name="__dcp_cap"]');
        for (var i = 0; i < capRadios.length; i++) {
            capRadios[i].addEventListener('change', function () {
                var attrRow = document.getElementById('__dcp_attr_row');
                if (attrRow) attrRow.style.display = this.value === 'attribute' ? 'block' : 'none';
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
            else if (captureType === 'html') val = (el.innerHTML || '');
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
            else if (captureType === 'screenshot') val = '[screenshot — captured during replay]';
            else if (captureType === 'console') val = '[console capture — logs captured during replay]';

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

    function _closeAssertModal() {
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


    // ── Input (debounced) ─────────────────────────────────────

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
        if (_inputTimers[key]) clearTimeout(_inputTimers[key]);

        _inputTimers[key] = setTimeout(function () {
            delete _inputTimers[key];
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
        }, _INPUT_DEBOUNCE);
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
