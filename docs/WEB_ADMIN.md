# Web Admin Dashboard

> The web admin is a Flask-based single-page application for managing your
> project through a browser.

---

## Starting the Dashboard

```bash
# Normal mode
./manage.sh web

# Mock mode (no real execution)
./manage.sh web --mock

# Custom port
./manage.sh web --port 9000
```

The dashboard opens at [http://127.0.0.1:8000](http://127.0.0.1:8000).

Press **SPACE** in the terminal to live-reload the server after code changes.
Press **Ctrl+C** or **q** to shut down gracefully (vault auto-locks on exit).

---

## Tabs

### 📊 Dashboard

Project overview:
- Status cards (project name, modules detected, last operation)
- Module list with stack assignments
- Activity feed from the audit ledger
- Adapter health summary

### 🧙 Setup Wizard

Guided multi-step onboarding:
1. **Welcome** — project name, description
2. **Modules** — scan and confirm detected modules
3. **Stacks** — assign stack types
4. **Environments** — configure dev/staging/prod
5. **Secrets** — set up vault passphrase
6. **Content** — configure content folders
7. **Review** — summary + generate `project.yml`

### 🔐 Secrets

`.env` file management with AES-256-GCM encryption:

- **Vault controls** — lock/unlock/quick-lock with passphrase
- **Auto-lock** — configurable inactivity timer
- **Secrets editor** — view keys (masked values), add/edit/delete
- **Sync** — push/pull secrets between environments
- **Export/Import** — portable encrypted vault file

The vault status (🔒/🔓) is always visible in the nav bar.

See [VAULT.md](VAULT.md) for encryption details.

### ⚡ Commands

Execute capabilities across modules:
- Select capability (test, lint, build, deploy)
- Target modules or run against all
- Mock mode and dry-run support
- Live output streaming
- Result history

### 📁 Content

File browser for project content with encryption support:

- **Browse** — navigate docs, media, archive directories
- **Preview** — inline preview for images, video, audio, markdown
- **Encrypt/Decrypt** — per-file AES-256-GCM encryption
- **Optimize** — image compression and video transcoding
- **Release** — upload large files to GitHub Releases
- **Archive** — move files to versioned archive

See [CONTENT.md](CONTENT.md) for details.

### 🔌 Integrations

External service management:

- **Git** — branch status, commit, pull, push, log
- **GitHub** — repo link, PR count, Actions status
- **Pages** — multi-segment site builder with SSG support
- **CI/CD** — workflow dispatch, run history

See [PAGES.md](PAGES.md) for the Pages builder system.

### 🐛 Debugging

Diagnostic tools:
- Audit log viewer with filters
- State inspector (view raw JSON)
- Health detail (circuit breaker states, retry queue)
- Config dump

---

## Template Architecture

The web admin uses a **partial-per-tab** pattern borrowed from production SPAs:

```
templates/
├── dashboard.html              # Master layout (includes everything)
├── partials/                   # HTML structure
│   ├── _head.html              #   <head>, CSS, meta
│   ├── _nav.html               #   Tab bar + vault toggle
│   ├── _tab_dashboard.html     #   📊 Dashboard
│   ├── _tab_wizard.html        #   🧙 Setup
│   ├── _tab_secrets.html       #   🔐 Secrets
│   ├── _tab_commands.html      #   ⚡ Commands
│   ├── _tab_content.html       #   📁 Content
│   ├── _tab_integrations.html  #   🔌 Integrations
│   └── _tab_debugging.html     #   🐛 Debugging
└── scripts/                    # JS logic
    ├── _globals.html           #   Shared helpers, API client
    ├── _tabs.html              #   Tab switching, hash-based deep linking
    ├── _theme.html             #   Dark/light toggle
    ├── _boot.html              #   Init on DOMContentLoaded
    ├── _dashboard.html         #   Dashboard tab logic
    ├── _wizard.html            #   Wizard step navigation
    ├── _secrets*.html          #   Secrets (form, keys, vault, render, sync)
    ├── _commands.html          #   Command execution
    ├── _content*.html          #   Content (browser, preview, upload, archive)
    └── _integrations.html      #   Git, GitHub, Pages
```

**Iron rule**: No business logic in templates. All actions call API endpoints.
Templates are purely for rendering.

---

## API Structure

All API endpoints live under `/api/`:

| Blueprint | Prefix | Purpose |
|-----------|--------|---------|
| `routes_api.py` | `/api/` | Core: status, run, detect, health, audit |
| `routes_vault.py` | `/api/vault/` | Lock, unlock, status, export, import |
| `routes_secrets.py` | `/api/secrets/` | List, set, delete, push, pull |
| `routes_content*.py` | `/api/content/` | Browse, encrypt, decrypt, upload |
| `routes_integrations.py` | `/api/git/`, `/api/gh/` | Git and GitHub operations |
| `routes_pages_api.py` | `/api/pages/` | Segments, builders, build, deploy |
| `routes_backup*.py` | `/api/backup/` | Backup, restore, archive |
| `routes_config.py` | `/api/config/` | Configuration management |

---

## Design Principles

1. **Dark mode by default** — premium dark theme with CSS custom properties
2. **Single-page app** — server-side Jinja2 rendering with client-side tab switching
3. **Polling-based reactivity** — no WebSocket complexity; simple fetch intervals
4. **Blueprint-per-domain** — each feature area is a separate Flask blueprint
5. **No frontend build step** — vanilla JS, no npm/webpack/bundler

---

## See Also

- [ARCHITECTURE.md](ARCHITECTURE.md) — System architecture
- [PAGES.md](PAGES.md) — Pages builder system
- [VAULT.md](VAULT.md) — Vault & encryption
- [CONTENT.md](CONTENT.md) — Content management
