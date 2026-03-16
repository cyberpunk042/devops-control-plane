# Phase 5: Run Operations — UI

> **Status**: Draft  
> **Depends on**: Phase 4 (run records exist)

---

## Goal

Show run activity on integration cards and make `@run:` references rich in chat.

## What Changes

### 1. Run Badge on Integration Cards

Similar to audit badges, but for runs. Each integration card gets a run indicator:

```html
<span class="run-activity-badge" id="run-badge-{key}" 
      onclick="openRunDetail('{key}')"
      title="Recent run activity"
      style="display:none">
    <span class="run-status-dot"></span>
    <span class="run-badge-label"></span>
</span>
```

The badge shows:
- 🟢 Green dot + "ok" for successful last run
- 🔴 Red dot + "failed" for failed last run  
- 🔵 Blue dot + spinner for in-progress run

### 2. SSE Handlers

```javascript
case 'run:started':   this._onRunStarted(payload);   break;
case 'run:completed': this._onRunCompleted(payload);  break;

_onRunStarted(payload) {
    // Show spinner on the relevant card's run badge
    const key = _runTypeToCardKey(payload.type, payload.subtype);
    const badge = document.getElementById('run-badge-' + key);
    if (badge) {
        badge.style.display = 'inline-flex';
        badge.querySelector('.run-status-dot').className = 'run-status-dot running';
        badge.querySelector('.run-badge-label').textContent = 'running…';
    }
}

_onRunCompleted(payload) {
    // Update badge to show result
    const key = _runTypeToCardKey(payload.type, payload.subtype);
    const badge = document.getElementById('run-badge-' + key);
    if (badge) {
        const ok = payload.status === 'ok';
        badge.querySelector('.run-status-dot').className = 
            'run-status-dot ' + (ok ? 'success' : 'failed');
        badge.querySelector('.run-badge-label').textContent = 
            ok ? 'ok' : 'failed';
        // Add tooltip with run reference
        badge.title = `Last run: ${payload.summary || payload.subtype} — @run:${payload.run_id}`;
    }
}
```

### 3. Run Detail Click Handler

Clicking the run badge shows a small popover or modal with:
- Run type + subtype
- Status + duration
- Summary
- `@run:<id>` reference (copy button)
- Last 5 events from the event stream
- Link to full run history for that card

### 4. Chat `@run:` Reference Enhancement

The `chatRefClick('run', ...)` handler already opens a modal. Upgrade the data display:

```javascript
case 'run':
    const data = await api('/chat/refs/resolve?ref=@run:' + refId);
    if (data.exists) {
        modalOpen({
            title: _runIcon(data.run_type) + ' Run: ' + data.subtype,
            body: `
                <div class="chat-ref-modal-detail">
                    <div class="chat-ref-modal-row">
                        <span class="chat-ref-modal-key">Status</span>
                        <span class="chat-ref-modal-val">${statusBadge(data.status)}</span>
                    </div>
                    <div class="chat-ref-modal-row">
                        <span class="chat-ref-modal-key">Started</span>
                        <span class="chat-ref-modal-val">${data.started_at}</span>
                    </div>
                    <div class="chat-ref-modal-row">
                        <span class="chat-ref-modal-key">Summary</span>
                        <span class="chat-ref-modal-val">${esc(data.summary)}</span>
                    </div>
                </div>
            `,
        });
    }
```

### 5. CSS

```css
.run-activity-badge { ... }
.run-status-dot { width: 6px; height: 6px; border-radius: 50%; }
.run-status-dot.running { background: var(--accent); animation: pulse 1.5s infinite; }
.run-status-dot.success { background: var(--success); }
.run-status-dot.failed { background: var(--error); }
```

## File Checklist

| File | Action | Lines est. |
|------|--------|-----------|
| `_tab_integrations.html` | ADD run badges to cards | ~14 |
| `_tab_devops.html` | ADD run badges to action-capable cards | ~10 |
| `_event_stream.html` | ADD `run:started`, `run:completed` handlers | ~30 |
| `_content_chat_refs.html` | MODIFY `chatRefClick('run', ...)` | ~30 |
| `admin.css` | ADD run badge + status dot styles | ~30 |
| New or existing script file | `openRunDetail()`, `_runTypeToCardKey()` | ~60 |

## Test Criteria

1. Trigger an action (e.g. run tests) → run badge appears on Testing card with spinner
2. Action completes → badge updates to green/red
3. Click badge → shows run detail with `@run:` reference
4. Type `@run:` in chat → autocomplete shows recent runs
5. Click `@run:` chip → modal shows run detail
