# Phase 6: Pre-Embed Preview

> **Status**: Draft  
> **Depends on**: Phase 3 (audit refs), Phase 5 (run refs)

---

## Goal

When composing a chat message, automatically resolve `@audit:` and `@run:` references and show an inline preview card below the textarea BEFORE the user submits.

## Concept

Currently, the compose flow is:
```
User types message with @ref → clicks Send → message renders with chip
```

New flow:
```
User types message with @ref → ref autocomplete inserts token
  → pre-embed area resolves the ref in real-time
  → shows inline preview card(s) below textarea
  → user reviews → clicks Send → message renders with chip + embed
```

## What Changes

### 1. Pre-Embed Preview Area (HTML)

Add a container between the textarea and the compose footer:

```html
<div class="chat-compose-wrap">
    <textarea id="chat-input" class="chat-textarea" ...></textarea>
    <!-- NEW: pre-embed preview area -->
    <div id="chat-pre-embed" class="chat-pre-embed" style="display:none"></div>
</div>
```

### 2. Ref Detection on Input (JavaScript)

On `input` event in the textarea, scan for `@type:id` patterns and resolve them:

```javascript
let _preEmbedCache = {};  // avoid re-resolving on every keystroke
let _preEmbedTimer = null;

function _chatCheckPreEmbed() {
    clearTimeout(_preEmbedTimer);
    _preEmbedTimer = setTimeout(_chatResolvePreEmbeds, 400);  // debounce
}

async function _chatResolvePreEmbeds() {
    const text = document.getElementById('chat-input').value;
    const refPat = /@(audit|run|commit|branch|thread|trace):([A-Za-z0-9_\-\/.]+)/g;
    const refs = [];
    let m;
    while ((m = refPat.exec(text)) !== null) {
        refs.push('@' + m[1] + ':' + m[2]);
    }
    
    if (refs.length === 0) {
        document.getElementById('chat-pre-embed').style.display = 'none';
        return;
    }
    
    // Resolve only new refs (not already cached)
    const toResolve = refs.filter(r => !_preEmbedCache[r]);
    for (const ref of toResolve) {
        try {
            const data = await api('/chat/refs/resolve?ref=' + encodeURIComponent(ref));
            _preEmbedCache[ref] = data;
        } catch (e) {
            _preEmbedCache[ref] = { exists: false };
        }
    }
    
    // Render preview cards
    _renderPreEmbeds(refs);
}
```

### 3. Preview Card Rendering

```javascript
function _renderPreEmbeds(refs) {
    const container = document.getElementById('chat-pre-embed');
    let html = '';
    
    for (const ref of refs) {
        const data = _preEmbedCache[ref];
        if (!data || !data.exists) continue;
        
        html += '<div class="chat-pre-embed-card">'
            + '<span class="chat-pre-embed-type">' + _preEmbedIcon(data.type) + ' ' + data.type + '</span>'
            + '<span class="chat-pre-embed-id">' + esc(data.id) + '</span>';
        
        if (data.summary) {
            html += '<span class="chat-pre-embed-summary">' + esc(data.summary) + '</span>';
        }
        if (data.status) {
            html += '<span class="chat-pre-embed-status ' + data.status + '">' + data.status + '</span>';
        }
        html += '<button class="chat-pre-embed-remove" onclick="_removePreEmbed(\'' + esc(ref) + '\')" title="Remove reference">✕</button>';
        html += '</div>';
    }
    
    container.innerHTML = html;
    container.style.display = html ? 'flex' : 'none';
}
```

### 4. CSS

```css
.chat-pre-embed {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-xs);
    padding: var(--space-xs) 0;
    max-height: 120px;
    overflow-y: auto;
}

.chat-pre-embed-card {
    display: flex;
    align-items: center;
    gap: 0.4em;
    padding: 0.3em 0.6em;
    border-radius: var(--radius-sm);
    background: var(--bg-inset);
    border: 1px solid var(--border-subtle);
    font-size: 0.75rem;
    color: var(--text-secondary);
    animation: fadeIn 0.15s ease;
}

.chat-pre-embed-type {
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    font-size: 0.65rem;
}

.chat-pre-embed-id {
    font-family: var(--font-mono);
    color: var(--accent);
    font-size: 0.72rem;
}

.chat-pre-embed-summary {
    color: var(--text-muted);
    font-size: 0.72rem;
    max-width: 200px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.chat-pre-embed-status {
    font-size: 0.62rem;
    padding: 0.05em 0.35em;
    border-radius: 100px;
    font-weight: 600;
}
.chat-pre-embed-status.ok { background: hsla(120, 60%, 40%, 0.15); color: var(--success); }
.chat-pre-embed-status.failed { background: hsla(0, 60%, 40%, 0.15); color: var(--error); }

.chat-pre-embed-remove {
    background: none;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 0.65rem;
    padding: 0 0.2em;
    opacity: 0.5;
    transition: opacity 0.15s;
}
.chat-pre-embed-remove:hover { opacity: 1; }
```

### 5. Wire into existing input handler

The chat input already has event listeners. Add `_chatCheckPreEmbed()` call:

```javascript
// In the existing input event handler
chatInput.addEventListener('input', function(e) {
    // ... existing ref popup logic ...
    _chatCheckPreEmbed();  // NEW
});
```

Also clear the pre-embed area on message send:

```javascript
// In chatSendMessage() after successful send
_preEmbedCache = {};
document.getElementById('chat-pre-embed').style.display = 'none';
```

## File Checklist

| File | Action | Lines est. |
|------|--------|-----------|
| `_content_chat.html` | ADD pre-embed container + wire input handler | ~10 |
| `_content_chat_refs.html` | ADD pre-embed resolve + render logic | ~80 |
| `admin.css` | ADD pre-embed card styles | ~50 |

## Test Criteria

1. Type `@audit:xxx` in compose → preview card appears showing audit detail
2. Type `@run:xxx` → preview card appears showing run status + summary
3. Delete the ref from text → preview card disappears
4. Multiple refs → multiple preview cards
5. Unknown ref → no preview card (graceful)
6. Send message → pre-embed area clears
7. Debounce works — no API spam on fast typing
