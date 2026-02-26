# Tool Install v2 — Phase 3: Frontend & Pages Unification

## Context

Phase 2 builds the backend: recipes, resolver, execution engine.
Phase 3 replaces the frontend install UI — the `ops-modal`,
`_showDepsModal`, and `streamCommand()` — with a unified plan-based
step modal. It also unifies pages_install.py into the main system.

### Dependencies

```
Phase 2.4 (execution)  ── provides: execute_plan(), POST /audit/install-plan
Phase 2.5 (updates)    ── provides: update_tool(), POST /audit/update-tool
Phase 3 (THIS)         ── provides: showStepModal(), streamSSE(), pages unification
```

### Domains consumed

| Domain | What Phase 3 uses |
|--------|------------------|
| domain-choices | Not yet (Phase 4). Simple tool install only. |
| domain-inputs | Not yet (Phase 4). No user inputs. |
| domain-disabled-options | Not yet (Phase 4). |
| domain-pages-install | Pages unification into TOOL_RECIPES. |
| domain-risk-levels | Risk indicators in plan display. |

---

## What Gets Replaced

### Current frontend (in _globals.html)

| Current piece | Line range | What it does | Replaced by |
|--------------|-----------|-------------|-------------|
| `ops-modal` | ~814-844 | Password prompt modal | `showStepModal()` |
| `ops-modal-action` click handler | ~846-870 | Single install call | Plan execution flow |
| `_showDepsModal()` | ~989-1040 | Missing deps modal | Plan step display |
| `streamCommand()` | ~1141-1230 | SSE stream reader | `streamSSE()` |
| Duplicate SSE readers | scattered | Copy-paste SSE logic | Single `streamSSE()` |
| Remediation option handlers | ~1180-1230 | Multi-step remediation | Plan step execution |

### Current backend

| Current | Replaced by |
|---------|-------------|
| `POST /audit/remediate` (single command) | `POST /audit/execute-plan` (plan execution) |
| `POST /api/tool/install` (single tool) | `POST /audit/install-plan` + `POST /audit/execute-plan` |

---

## New Frontend Components

### 1. streamSSE() — unified SSE reader

```javascript
/**
 * Stream SSE events from a URL. Single implementation for all SSE.
 *
 * @param {string} url - SSE endpoint URL
 * @param {Object} body - POST body
 * @param {Object} callbacks - Event handlers
 * @param {function} callbacks.onLog - (line: string) => void
 * @param {function} callbacks.onStepStart - (step: {index, label}) => void
 * @param {function} callbacks.onStepDone - (step: {index}) => void
 * @param {function} callbacks.onStepFailed - (step: {index, error}) => void
 * @param {function} callbacks.onDone - (result: {ok, message}) => void
 * @param {function} callbacks.onError - (error: string) => void
 * @returns {Promise<{ok: boolean}>}
 */
async function streamSSE(url, body, callbacks) {
    const resp = await fetch(url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
    });

    if (!resp.ok) {
        callbacks.onError?.(`Request failed: ${resp.status}`);
        return {ok: false};
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const {done, value} = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, {stream: true});
        const lines = buffer.split('\n');
        buffer = lines.pop(); // keep incomplete line

        for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
                const event = JSON.parse(line.slice(6));
                switch (event.type) {
                    case 'log':
                        callbacks.onLog?.(event.line);
                        break;
                    case 'step_start':
                        callbacks.onStepStart?.(event);
                        break;
                    case 'step_done':
                        callbacks.onStepDone?.(event);
                        break;
                    case 'step_failed':
                        callbacks.onStepFailed?.(event);
                        break;
                    case 'done':
                        callbacks.onDone?.(event);
                        return {ok: event.ok};
                    case 'error':
                        callbacks.onError?.(event.error);
                        return {ok: false};
                }
            } catch (e) { /* skip malformed lines */ }
        }
    }

    return {ok: true};
}
```

### 2. showStepModal() — unified install modal

```javascript
/**
 * Show a step-by-step install modal.
 *
 * @param {Object} plan - Install plan from /audit/install-plan
 * @param {Object} options - Modal options
 * @param {function} options.onComplete - Callback on successful install
 */
function showStepModal(plan, options = {}) {
    // Remove existing modal
    document.getElementById('step-modal')?.remove();

    const modal = document.createElement('div');
    modal.id = 'step-modal';
    modal.className = 'modal-overlay';

    const needsSudo = plan.steps.some(s => s.needs_sudo);
    const riskLevel = _planRisk(plan);

    modal.innerHTML = `
        <div class="modal-content step-modal-content">
            <div class="modal-header">
                <h3>📦 Install ${plan.tool}</h3>
                <button class="modal-close" onclick="document.getElementById('step-modal')?.remove()">✕</button>
            </div>
            <div class="modal-body">
                ${riskLevel !== 'low' ? `<div class="risk-banner risk-${riskLevel}">
                    ${riskLevel === 'high' ? '🔴' : '⚠️'} This plan contains ${riskLevel}-risk operations
                </div>` : ''}
                <div class="step-list" id="step-list">
                    ${plan.steps.map((s, i) => `
                        <div class="step-row" id="step-row-${i}" data-status="pending">
                            <span class="step-icon">⏳</span>
                            <span class="step-label">${s.label}</span>
                            ${s.needs_sudo ? '<span class="step-badge sudo">sudo</span>' : ''}
                            ${s.risk && s.risk !== 'low' ? `<span class="step-badge risk-${s.risk}">${s.risk}</span>` : ''}
                        </div>
                    `).join('')}
                </div>
                ${needsSudo ? `
                    <div class="sudo-input-row">
                        <input id="step-modal-pw" type="password" placeholder="sudo password"
                               autocomplete="off"
                               onkeydown="if(event.key==='Enter'){document.getElementById('step-modal-go').click()}" />
                    </div>
                ` : ''}
                <div class="step-log" id="step-log" style="display:none"></div>
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary" onclick="document.getElementById('step-modal')?.remove()">Cancel</button>
                <button class="btn btn-primary" id="step-modal-go">📦 Install</button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    if (needsSudo) {
        setTimeout(() => document.getElementById('step-modal-pw')?.focus(), 100);
    }

    document.getElementById('step-modal-go').addEventListener('click', async () => {
        await executeInstallPlan(plan, options);
    });
}
```

### 3. executeInstallPlan() — modal execution driver

```javascript
/**
 * Execute an install plan within the step modal.
 */
async function executeInstallPlan(plan, options = {}) {
    const btn = document.getElementById('step-modal-go');
    const log = document.getElementById('step-log');
    const pw = document.getElementById('step-modal-pw')?.value || '';

    // Disable button
    btn.disabled = true;
    btn.textContent = '⏳ Installing...';
    log.style.display = 'block';

    // Clear password from DOM
    const pwInput = document.getElementById('step-modal-pw');
    if (pwInput) pwInput.value = '';

    const result = await streamSSE('/audit/execute-plan', {
        tool: plan.tool,
        sudo_password: pw,
    }, {
        onLog(line) {
            log.textContent += line + '\n';
            log.scrollTop = log.scrollHeight;
        },
        onStepStart(event) {
            _updateStepRow(event.step, 'running', '🔄');
        },
        onStepDone(event) {
            _updateStepRow(event.step, 'done', '✅');
        },
        onStepFailed(event) {
            _updateStepRow(event.step, 'failed', '❌');
            log.textContent += `ERROR: ${event.error}\n`;
        },
        onDone(event) {
            if (event.ok) {
                btn.textContent = '✅ Done';
                btn.className = 'btn btn-success';
                setTimeout(() => {
                    document.getElementById('step-modal')?.remove();
                    // Clear caches
                    sessionStorage.removeItem('l0_detection');
                    // Callback
                    options.onComplete?.();
                }, 1500);
            } else {
                btn.textContent = '❌ Failed';
                btn.disabled = false;
                btn.textContent = '🔄 Retry';
            }
        },
        onError(error) {
            btn.disabled = false;
            btn.textContent = '🔄 Retry';
            log.textContent += `ERROR: ${error}\n`;
        },
    });
}

function _updateStepRow(index, status, icon) {
    const row = document.getElementById(`step-row-${index}`);
    if (row) {
        row.dataset.status = status;
        row.querySelector('.step-icon').textContent = icon;
    }
}

function _planRisk(plan) {
    const risks = plan.steps.map(s => s.risk || 'low');
    if (risks.includes('high')) return 'high';
    if (risks.includes('medium')) return 'medium';
    return 'low';
}
```

---

## New Backend Endpoint

### POST /audit/execute-plan (SSE)

```python
@app.post("/audit/execute-plan")
def execute_plan_sse():
    """Execute an install plan with SSE streaming."""
    tool = request.json.get("tool")
    sudo_password = request.json.get("sudo_password", "")

    profile = get_system_profile()
    plan = resolve_install_plan(tool, profile)

    if plan.get("error"):
        return jsonify({"ok": False, "error": plan["error"]}), 400

    def generate():
        for i, step in enumerate(plan["steps"]):
            yield _sse({"type": "step_start", "step": i,
                        "label": step["label"]})

            result = execute_plan_step(
                step,
                sudo_password=sudo_password,
                env_overrides=plan.get("post_env"),
            )

            if result.get("skipped"):
                yield _sse({"type": "step_done", "step": i,
                            "skipped": True})
                continue

            if result.get("stdout"):
                for line in result["stdout"].splitlines():
                    yield _sse({"type": "log", "step": i,
                                "line": line})

            if result["ok"]:
                yield _sse({"type": "step_done", "step": i})
            else:
                yield _sse({"type": "step_failed", "step": i,
                            "error": result["error"]})
                yield _sse({"type": "done", "ok": False,
                            "error": result["error"]})
                return

        yield _sse({"type": "done", "ok": True,
                    "message": f"{tool} installed successfully"})

    return Response(generate(), mimetype='text/event-stream')


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"
```

---

## Pages Unification

### What changes

| Current | Phase 3 |
|---------|---------|
| Separate `POST /api/pages/install/{name}` | Same route, calls unified system |
| `pages_install.py` generators | TOOL_RECIPES entries for Hugo, MkDocs, Docusaurus |
| Custom SSE format | Same SSE format (already compatible) |
| Custom arch detection | Uses system profile |

### Migration

```python
# routes_pages.py (existing endpoint, updated implementation)
@app.post("/api/pages/install/<name>")
def install_page_builder(name: str):
    """Install a page builder — unified path."""
    # Map builder name to tool recipe name
    builder_map = {
        "mkdocs": "mkdocs",
        "docusaurus": "docusaurus",
        "hugo": "hugo",
    }
    tool = builder_map.get(name)
    if not tool:
        return jsonify({"ok": False, "error": f"Unknown builder: {name}"}), 404

    # Use unified install plan
    profile = get_system_profile()
    plan = resolve_install_plan(tool, profile)

    # Return SSE stream (same format as pages_install.py used)
    def generate():
        for event in execute_plan_stream(plan):
            yield f"data: {json.dumps(event)}\n\n"

    return Response(generate(), mimetype='text/event-stream')
```

### Frontend pages tab

```javascript
// Before (pages-specific):
async function installBuilder(name) {
    const resp = await fetch(`/api/pages/install/${name}`, {method: 'POST'});
    // custom SSE reading...
}

// After (unified):
async function installBuilder(name) {
    // Fetch plan
    const planResp = await fetch('/audit/install-plan', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({tool: name}),
    });
    const plan = await planResp.json();

    // Show unified step modal
    showStepModal(plan, {
        onComplete: () => refreshBuilderStatus(name),
    });
}
```

---

## CSS for Step Modal

### Style system

```css
/* Step modal */
.step-modal-content {
    max-width: 520px;
}

.step-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-xs);
    margin-bottom: var(--space-md);
}

.step-row {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    padding: var(--space-xs) var(--space-sm);
    border-radius: var(--radius-sm);
    background: var(--bg-inset);
    font-size: 0.85rem;
    transition: background 0.2s, opacity 0.2s;
}

.step-row[data-status="running"] {
    background: var(--bg-hover);
    box-shadow: inset 3px 0 0 var(--accent);
}

.step-row[data-status="done"] {
    opacity: 0.7;
}

.step-row[data-status="failed"] {
    background: hsl(0 40% 15%);
    box-shadow: inset 3px 0 0 hsl(0 70% 50%);
}

.step-icon {
    width: 20px;
    text-align: center;
    flex-shrink: 0;
}

.step-badge {
    font-size: 0.65rem;
    padding: 1px 6px;
    border-radius: 8px;
    margin-left: auto;
    flex-shrink: 0;
}

.step-badge.sudo {
    background: hsl(40 60% 20%);
    color: hsl(40 90% 70%);
}

.step-badge.risk-medium {
    background: hsl(40 60% 20%);
    color: hsl(40 90% 70%);
}

.step-badge.risk-high {
    background: hsl(0 60% 20%);
    color: hsl(0 90% 70%);
}

.risk-banner {
    padding: var(--space-sm);
    border-radius: var(--radius-sm);
    margin-bottom: var(--space-md);
    font-size: 0.82rem;
}

.risk-banner.risk-medium {
    background: hsl(40 60% 15%);
    border-left: 3px solid hsl(40 90% 60%);
}

.risk-banner.risk-high {
    background: hsl(0 60% 15%);
    border-left: 3px solid hsl(0 90% 60%);
}

.step-log {
    font-family: var(--font-mono, monospace);
    font-size: 0.72rem;
    padding: var(--space-sm);
    border-radius: var(--radius-sm);
    background: var(--bg-inset);
    max-height: 150px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-all;
}

.sudo-input-row {
    margin-bottom: var(--space-sm);
}

.sudo-input-row input {
    width: 100%;
    padding: var(--space-xs) var(--space-sm);
    border-radius: var(--radius-sm);
    border: 1px solid var(--border);
    background: var(--bg-inset);
    color: var(--text);
    font-size: 0.85rem;
}
```

---

## What Callers Need to Change

### Audit dashboard install button

```javascript
// Before:
button.onclick = () => showSudoModalAndInstall(tool);

// After:
button.onclick = async () => {
    const planResp = await fetch('/audit/install-plan', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({tool}),
    });
    const plan = await planResp.json();
    showStepModal(plan, {onComplete: refreshAudit});
};
```

### Remediation options

```javascript
// Before: each option has its own handler with streamCommand()
// After: remediation returns a mini-plan, same modal

button.onclick = () => {
    const remediationPlan = {
        tool: tool,
        steps: option.steps || [{
            label: option.label,
            command: option.command,
            needs_sudo: option.needs_sudo,
        }],
    };
    showStepModal(remediationPlan, {onComplete: refreshAudit});
};
```

---

## Files Touched

| File | Changes |
|------|---------|
| `_globals.html` | Add `streamSSE()`, `showStepModal()`, `executeInstallPlan()`. Remove old `ops-modal`, `_showDepsModal`, `streamCommand()`. |
| `_globals.html` (CSS) | Add step modal styles. |
| `routes_audit.py` | Add `POST /audit/execute-plan` (SSE). |
| `routes_pages.py` | Update `/api/pages/install/{name}` to use unified system. |
| `_dashboard.html` | Update install buttons to use `showStepModal()`. |
| `_integrations_setup_cicd.html` | Update install buttons if any. |

---

## Backward Compatibility

### Deprecation approach

| Phase 3a | Phase 3b |
|----------|----------|
| Add new components alongside old | Wire all callers to new components |
| `showStepModal()` + `streamSSE()` added | Remove old `ops-modal` + `streamCommand()` |
| Both work simultaneously | Old code removed |

All callers must be updated BEFORE old code is removed.

---

## Edge Cases

| Case | Impact | Handling |
|------|--------|---------|
| Modal already open | Double modal | Remove existing before creating new |
| SSE connection drops | Stuck progress | Timeout detection, show reconnect option |
| Password wrong at step 3 | Steps 1-2 done, 3 fails | Show "Wrong password" at step 3, retry button |
| Plan has 0 steps | Empty modal | Show "Already installed" instead of modal |
| Tool not in TOOL_RECIPES | No plan generated | Show error: "No recipe available" |
| Pages builder install | Different route | Same modal via unified backend |
| Very long step output | Log overflow | max-height + scroll on log element |
| User closes modal mid-install | Background process continues | subprocess runs to completion anyway |

---

## Traceability

| Topic | Source |
|-------|--------|
| ops-modal (current) | _globals.html lines 814-844 |
| _showDepsModal (current) | _globals.html lines 989-1040 |
| streamCommand (current) | _globals.html lines 1141-1230 |
| SSE event format | domain-pages-install §SSE events |
| Risk indicators | domain-risk-levels §UI treatment |
| Pages unification | domain-pages-install §migration plan |
| execute_plan() (backend) | Phase 2.4 execution engine |
| install-plan endpoint | Phase 2.4 §new route |
| Step format | Phase 2.3 resolver output |
