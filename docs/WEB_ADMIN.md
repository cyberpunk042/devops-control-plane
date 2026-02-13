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

The web admin uses a **partial-per-tab** pattern with a **loader pattern** for
large tabs. Each loader is a thin `<script>` block with Jinja2 `{% include %}`
directives that pull in domain-specific modules sharing the same script scope.

> **File size rule**: No template file over **500 lines** (700 max for justified
> exceptions like tightly-coupled modal clusters).

```
templates/
├── dashboard.html                      # Master layout (includes everything)
├── partials/                           # HTML structure (one per tab)
│   ├── _head.html                      #   <head>, CSS, meta
│   ├── _nav.html                       #   Tab bar + vault toggle
│   ├── _tab_dashboard.html             #   📊 Dashboard
│   ├── _tab_wizard.html                #   🧙 Setup
│   ├── _tab_secrets.html               #   🔐 Secrets
│   ├── _tab_commands.html              #   ⚡ Commands
│   ├── _tab_content.html               #   📁 Content (+ _content_modals.html)
│   ├── _tab_integrations.html          #   🔌 Integrations
│   ├── _tab_devops.html                #   🛠 DevOps
│   ├── _tab_audit.html                 #   🔍 Audit
│   └── _tab_debugging.html             #   🐛 Debugging
│
└── scripts/                            # JS logic
    ├── _globals.html                   # Shared helpers, API client, modal system
    ├── _tabs.html                      # Tab switching, hash-based deep linking
    ├── _theme.html                     # Dark/light toggle
    ├── _boot.html                      # Init on DOMContentLoaded
    ├── _lang.html                      # i18n / Google Translate
    ├── _monaco.html                    # Monaco editor integration
    ├── _dashboard.html                 # Dashboard tab
    ├── _commands.html                  # Commands tab
    ├── _setup_wizard.html              # Setup wizard (standalone)
    ├── _debugging.html                 # Debugging tab
    │
    ├── _content.html                   # LOADER → 10 modules
    │   ├── _content_init.html          #   State, constants, categories
    │   ├── _content_nav.html           #   Folder bar, mode switch, hash nav
    │   ├── _content_archive.html       #   Archive panel, tree, export
    │   ├── _content_archive_modals.html #  Archive modal handlers
    │   ├── _content_archive_actions.html # Archive non-modal actions
    │   ├── _content_browser.html       #   File browser, search, gallery
    │   ├── _content_actions.html       #   File CRUD, encrypt, release
    │   ├── _content_preview.html       #   Plain file preview + edit
    │   ├── _content_preview_enc.html   #   Encrypted preview + rename/move
    │   └── _content_upload.html        #   Upload, drag-drop, enc key setup
    │
    ├── _secrets.html                   # LOADER → 6 modules
    │   ├── _secrets_init.html          #   State, tier logic, tab load
    │   ├── _secrets_render.html        #   Status bars, file list, form
    │   ├── _secrets_form.html          #   Target selector, dirty tracking
    │   ├── _secrets_sync.html          #   Save/push, sync, remove, refresh
    │   ├── _secrets_keys.html          #   Key management, add/create modal
    │   └── _secrets_vault.html         #   Vault lock/unlock modals
    │
    ├── _integrations.html              # LOADER → 11 modules
    │   ├── _integrations_init.html     #   State, prefs, card metadata, tab load
    │   ├── _integrations_git.html      #   Git card + actions
    │   ├── _integrations_github.html   #   GitHub card + live panels + modals
    │   ├── _integrations_cicd.html     #   CI/CD card + live panels + generate
    │   ├── _integrations_docker.html   #   Docker card + live panels + modals
    │   ├── _integrations_docker_compose.html # Compose wizard + ops
    │   ├── _integrations_k8s.html      #   K8s card + live panels + all modals
    │   ├── _integrations_terraform.html #  Terraform card + live panels + modals
    │   ├── _integrations_pages.html    #   Pages card + segment wizard
    │   ├── _integrations_pages_config.html # Pages config modal + build/deploy
    │   └── _integrations_pages_sse.html #  SSE streaming + CI gen + helpers
    │
    ├── _devops.html                    # LOADER → 10 modules
    │   ├── _devops_init.html           #   State, prefs, card metadata, tab load
    │   ├── _devops_security.html       #   Security card + live panels
    │   ├── _devops_testing.html        #   Testing card + test gen modal
    │   ├── _devops_docs.html           #   Documentation card + live panels
    │   ├── _devops_k8s.html            #   K8s card + modals
    │   ├── _devops_terraform.html      #   Terraform card + modals
    │   ├── _devops_dns.html            #   DNS & CDN card + modals
    │   ├── _devops_quality.html        #   Quality card + modals
    │   ├── _devops_packages.html       #   Packages card + modals
    │   └── _devops_env.html            #   Environment & IaC card + live panels
    │
    ├── _wizard.html                    # LOADER → 6 modules
    │   ├── _wizard_init.html           #   Config load, state, render entry
    │   ├── _wizard_steps.html          #   All 6 step renderers
    │   ├── _wizard_helpers.html        #   Module/domain/env/content helpers
    │   ├── _wizard_integrations.html   #   Integration sub-wizard UI + forms
    │   ├── _wizard_integration_actions.html # Docker/K8s live panels, backend
    │   └── _wizard_nav.html            #   Navigation, save, activate
    │
    └── _audit.html                     # LOADER → 5 modules
        ├── _audit_init.html            #   Shared data store, helpers
        ├── _audit_scores.html          #   Master L0/L1/L2 score rendering
        ├── _audit_cards_a.html         #   System Profile, Deps, Structure, Clients
        ├── _audit_cards_b.html         #   Code Health, Repo Health, Risks, Imports
        └── _audit_modals.html          #   Drill-down modals, batch dismiss
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
