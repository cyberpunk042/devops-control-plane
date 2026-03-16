# Phase 2: Audit UI — Badge + Audit Manager Modal

> **Status**: Draft  
> **Depends on**: Phase 1 (backend staging + SSE event)

---

## Goal

Show a badge on each DevOps/Integration card when an unsaved audit exists. Clicking the badge opens a dedicated Audit Manager Modal for batch save/discard operations.

## What Changes

### 1. Card Badge (HTML)

Add a hidden `<span>` to each card header in `_tab_devops.html` and `_tab_integrations.html`:

```html
<!-- In each card-header, after the status-badge -->
<span class="audit-pending-badge" id="audit-badge-{key}" 
      onclick="openAuditManager()" 
      title="Unsaved audit — click to manage"
      style="display:none">📋</span>
```

Pattern: `audit-badge-security`, `audit-badge-testing`, `audit-badge-k8s`, etc.

This goes in ALL 9 DevOps cards + ALL 7 Integration cards = 16 badges.

### 2. SSE Handler (JavaScript)

In `_event_stream.html`, add `'audit:pending'` to `_eventTypes` and handle it:

```javascript
case 'audit:pending': this._onAuditPending(payload); break;

_onAuditPending(payload) {
    const key = payload.key;
    if (!key) return;
    const badge = document.getElementById('audit-badge-' + key);
    if (badge) {
        badge.style.display = 'inline-flex';
        badge.title = 'Unsaved audit scan — click to manage';
    }
    // Update global pending count
    _auditPendingCount = (_auditPendingCount || 0) + 1;
    _updateAuditManagerBadge();
}
```

### 3. Audit Manager Modal (New file)

`src/ui/web/templates/scripts/_audit_manager_modal.html`

**Layout:**
```
┌─────────────────────────────────────────────────┐
│  📋 Audit Manager                    [✕ Close]  │
├─────────────────────────────────────────────────┤
│  ☐ Select All    [💾 Save All] [🗑 Discard All] │
├─────────────────────────────────────────────────┤
│  ☐ 🔐 Security Posture                          │
│    Score: 78 (B) · 3 findings · 12s ago         │
│    ──────────────────────── [💾 Save] [🗑 Disc]  │
│                                                  │
│  ☐ 🧪 Testing                                   │
│    pytest detected · 42 tests · coverage: 68%    │
│    ──────────────────────── [💾 Save] [🗑 Disc]  │
│                                                  │
│  ☐ 📦 Packages                                  │
│    pip, npm · 156 deps · 3 outdated              │
│    ──────────────────────── [💾 Save] [🗑 Disc]  │
├─────────────────────────────────────────────────┤
│  💾 Saved (2)                                    │
│  ✅ 🔧 Quality — saved 5m ago · @audit:qual_... │
│  ✅ ☸️ K8s — saved 12m ago · @audit:k8s_17...    │
└─────────────────────────────────────────────────┘
```

**Behavior:**
- Opens as a dedicated overlay (not via `modalOpen()` — has list/batch semantics)
- Loads pending list from `GET /api/audits/pending`
- Individual and batch save/discard via checkboxes
- Save calls `POST /api/audits/save` → on success, item moves to "Saved" section
- Discard calls `POST /api/audits/discard` → item disappears
- After save, shows the `@audit:<id>` reference so user can copy it for chat
- Pressing Escape or clicking Close dismisses

**JavaScript functions:**
```
openAuditManager()           — open modal, fetch pending list
_auditManagerRender(data)    — render the list
auditManagerSave(ids)        — save selected
auditManagerDiscard(ids)     — discard selected
auditManagerSaveAll()        — save all pending
auditManagerDiscardAll()     — discard all pending
_updateAuditManagerBadge()   — update card badges after save/discard
```

### 4. CSS Additions (`admin.css`)

```css
/* Audit pending badge — small pill on card header */
.audit-pending-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 0.7rem;
    padding: 1px 5px;
    border-radius: 100px;
    background: hsla(45, 100%, 60%, 0.15);
    color: #fbbf24;
    cursor: pointer;
    transition: all 0.15s;
    border: 1px solid hsla(45, 100%, 60%, 0.25);
}
.audit-pending-badge:hover {
    background: hsla(45, 100%, 60%, 0.25);
    transform: translateY(-1px);
}

/* Audit Manager Modal — dedicated overlay */
.audit-manager-overlay { ... }
.audit-manager-panel { ... }
.audit-manager-item { ... }
.audit-manager-item-actions { ... }
.audit-manager-saved-section { ... }
```

## File Checklist

| File | Action | Lines est. |
|------|--------|-----------|
| `_tab_devops.html` | ADD badge span to 9 cards | ~18 |
| `_tab_integrations.html` | ADD badge span to 7 cards | ~14 |
| `_event_stream.html` | ADD `audit:pending` event type + handler | ~20 |
| `_audit_manager_modal.html` | CREATE — modal HTML + JS | ~200 |
| `admin.css` | ADD badge + modal styles | ~80 |
| `base.html` or `layout.html` | INCLUDE `_audit_manager_modal.html` | ~1 |

## Test Criteria

1. Refresh a DevOps card → badge appears on that card
2. Click badge → Audit Manager Modal opens with pending list
3. Click "Save" on a single item → item moves to "Saved" section, badge clears
4. Click "Discard" → item disappears, badge clears
5. "Save All" / "Discard All" work for batch operations
6. Saved items show `@audit:<id>` reference string
7. Modal survives multiple open/close cycles without stale data
