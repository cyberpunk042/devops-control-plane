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

    var SESSION_ID = '${SESSION_ID}';
    var DCP_CALLBACK = 'http://${DCP_HOST}:${DCP_PORT}/api/cdp-test/record/event';
    var _lastUrl = location.href;
    var _inputTimers = {};       // debounce timers per element
    var _INPUT_DEBOUNCE = 600;   // ms to wait after typing stops
    var _lastClickTime = 0;


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
        while (current && current !== document.body && current !== document.documentElement) {
            var parent = current.parentElement;
            if (!parent) break;
            var siblings = Array.from(parent.children);
            var index = siblings.indexOf(current) + 1;
            path.unshift(current.tagName.toLowerCase() + ':nth-child(' + index + ')');
            current = parent;
            if (path.length > 5) break; // don't go too deep
        }
        return path.length > 0 ? path.join(' > ') : 'body';
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
        if (window.__dcp_recorder_paused) return;

        var payload = JSON.stringify({
            session_id: SESSION_ID,
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
            }).catch(function () {
                if (!_sendFailed) {
                    _sendFailed = true;
                    _updateIndicator('blocked');
                }
            });
        } catch (_) { }
    }


    // ═══════════════════════════════════════════════════════════
    //  Event Listeners
    // ═══════════════════════════════════════════════════════════

    // ── Click ─────────────────────────────────────────────────

    document.addEventListener('click', function (e) {
        if (window.__dcp_recorder_paused) return;

        var el = e.target;
        // Skip clicks on the recorder's own UI (if any)
        if (el.closest && el.closest('#__dcp_recorder_indicator')) return;

        // Debounce rapid double-clicks
        var now = Date.now();
        if (now - _lastClickTime < 50) return;
        _lastClickTime = now;

        sendEvent({
            action: 'click',
            selector: buildSelector(el),
            xpath: buildXPath(el),
            selector_alternatives: buildAlternatives(el),
            element_tag: el.tagName.toLowerCase(),
            element_text: (el.textContent || '').trim().slice(0, 80),
            element_rect: getRect(el),
        });
    }, true);


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

    // Pulse animation
    var style = document.createElement('style');
    style.textContent =
        '@keyframes __dcp_rec_pulse {' +
        '0%,100%{opacity:1} 50%{opacity:0.3}' +
        '}';
    document.head.appendChild(style);
    document.body.appendChild(indicator);

    // ── Ad blocker detection: send a test ping ───────────────
    try {
        fetch(DCP_CALLBACK, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: SESSION_ID, action: 'ping' }),
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

        // Clear state
        window.__dcp_recorder_active = false;
        window.__dcp_recorder_paused = false;
        window.__dcp_recorder_cleanup = null;
    };

    return 'injected';
})();
