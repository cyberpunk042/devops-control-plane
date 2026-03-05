# Web Admin Template Architecture

> **Source of truth** for how the web admin UI is structured.
> Derived from actual source: `src/ui/web/templates/`, `src/ui/web/routes/`.
>
> Last verified: 2026-03-05

---

## Template File Structure

```
src/ui/web/templates/
├── dashboard.html              ← Main SPA page (Jinja2 template)
│
├── partials/                   ← HTML fragments (included via Jinja2)
│   ├── _head.html              ← <head> tag, CSS links
│   ├── _nav.html               ← Top navigation bar
│   ├── _tab_dashboard.html     ← Dashboard tab HTML structure
│   ├── _tab_content.html       ← Content tab HTML structure
│   ├── _tab_secrets.html       ← Secrets tab HTML
│   ├── _tab_devops.html        ← DevOps tab HTML
│   ├── _tab_integrations.html  ← Integrations tab HTML
│   ├── _tab_audit.html         ← Audit tab HTML
│   ├── _tab_commands.html      ← Commands tab HTML
│   ├── _tab_debugging.html     ← Debugging tab HTML
│   ├── _tab_wizard.html        ← Wizard tab HTML
│   └── _content_modals.html    ← Content modal dialogs
│
└── scripts/                    ← ⚠️ RAW JAVASCRIPT (not HTML pages)
    ├── globals/                ← Shared utilities (api, cache, modals)
    │   ├── _api.html           ← api() function, base URL setup
    │   ├── _cache.html         ← Session/memory caching helpers
    │   ├── _modal.html         ← Modal show/hide utilities
    │   ├── _card_builders.html ← DevOps card rendering
    │   ├── _auth_modal.html    ← SSH passphrase auth modal
    │   ├── _missing_tools.html ← Tool availability checks
    │   └── _ops_modal.html     ← Operations modal (large)
    │
    ├── content/                ← Content tab JS modules (17 files)
    │   ├── _init.html          ← Global variable declarations
    │   ├── _content.html       ← Tab entry point
    │   ├── _nav.html           ← Folder navigation, contentLoadFolder()
    │   ├── _browser.html       ← File listing renderer
    │   ├── _preview.html       ← File preview pane
    │   ├── _preview_enc.html   ← Encrypted file preview
    │   ├── _glossary.html      ← Glossary/outline panel
    │   ├── _smart_folders.html ← Smart folder system
    │   ├── _upload.html        ← File upload
    │   ├── _actions.html       ← File actions (rename, move, delete)
    │   ├── _chat.html          ← Chat interface
    │   ├── _chat_refs.html     ← Chat reference resolution
    │   ├── _archive.html       ← Archive browser
    │   ├── _archive_actions.html ← Archive operations
    │   ├── _archive_modals.html ← Archive modal dialogs
    │   └── _modal_preview.html ← Modal preview
    │
    ├── assistant/              ← Assistant panel modules (7 files)
    ├── audit/                  ← Audit tab modules (7 files)
    ├── auth/                   ← Auth modules (3 files)
    ├── devops/                 ← DevOps tab modules (13 files)
    ├── docker_wizard/          ← Docker wizard (3 files)
    ├── integrations/           ← Integrations tab modules (30 files)
    ├── k8s_wizard/             ← Kubernetes wizard (9 files)
    ├── secrets/                ← Secrets tab modules (8 files)
    ├── wizard/                 ← Setup wizard modules (10 files)
    │
    ├── _dashboard.html         ← Dashboard tab JS
    ├── _commands.html          ← Commands tab JS
    ├── _debugging.html         ← Debugging tab JS
    ├── _settings.html          ← Settings JS
    ├── _tabs.html              ← Tab switching logic
    ├── _theme.html             ← Theme toggle
    ├── _lang.html              ← Language/i18n
    ├── _monaco.html            ← Monaco editor integration
    ├── _event_stream.html      ← Server-sent events
    ├── _stage_debugger.html    ← Stage debugger
    ├── _dev_mode.html          ← Dev mode toggle
    └── _boot.html              ← Closes </script> block, runs init
```

---

## ⚠️ CRITICAL: How scripts/*.html Works

### These files are RAW JAVASCRIPT, not HTML pages.

The `dashboard.html` template includes them in sequence:

```html
<!-- dashboard.html -->
<script>
{% include 'scripts/globals/_api.html' %}       ← opens context
{% include 'scripts/globals/_cache.html' %}
{% include 'scripts/globals/_modal.html' %}
...
{% include 'scripts/content/_init.html' %}       ← content globals
{% include 'scripts/content/_nav.html' %}
{% include 'scripts/content/_browser.html' %}
...
{% include 'scripts/_boot.html' %}               ← closes context
</script>
```

**Consequences:**
- Do NOT add `<script>` tags inside these files — causes syntax error
- All variables declared with `let` are shared across all included files
- Function names must be globally unique (no module isolation)
- Order matters: a file can only call functions from files included before it

---

## API Routes Structure

```
src/ui/web/routes/
├── __init__.py           ← Blueprint registration
├── api/                  ← /api/* general endpoints
├── content/              ← /api/content/*
│   ├── browse.py         ← /api/content/list, /api/content/preview
│   ├── outline.py        ← /api/content/outline, /api/content/glossary
│   ├── peek.py           ← /api/content/peek
│   ├── edit.py           ← /api/content/edit
│   └── ...
├── smart_folders/        ← /api/smart-folders/*
├── devops/               ← /api/devops/*
├── audit/                ← /api/audit/*
├── vault/                ← /api/vault/*
├── secrets/              ← /api/secrets/*
├── git_auth/             ← /api/git-auth/*
├── chat/                 ← /api/chat/*
└── ... (32 route packages total)
```

### Route Pattern
All routes follow Flask Blueprint pattern:
```python
bp = Blueprint('content_browse', __name__)

@bp.route('/api/content/list')
def content_list():
    path = request.args.get('path', '')
    ...
    return jsonify(result)
```

---

## How Frontend Calls Backend

The `api()` function in `globals/_api.html` is the single entry point:

```javascript
// Usage:
const data = await api('/content/list?path=' + encodeURIComponent(path));
const result = await api('/content/glossary?path=' + encodeURIComponent(path));

// It prefixes with /api and handles errors:
async function api(endpoint, options = {}) {
    const resp = await fetch('/api' + endpoint, options);
    if (!resp.ok) throw new Error(await resp.text());
    return resp.json();
}
```

---

## Tab Lifecycle

```
1. Page load → dashboard.html renders
2. _boot.html runs → calls initApp()
3. User clicks tab → switchTab(tabName) called
4. First time a tab is activated → tab-specific init runs
5. Content tab → contentInit() → contentLoadRoots() → contentLoadFolder()
```
