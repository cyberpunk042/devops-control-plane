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
- **Docker** — container detection, image build, Dockerfile generation
- **Kubernetes** — manifest detection, cluster ops, wizard-driven generation
- **Terraform** — config detection, plan, apply, state
- **Pages** — multi-segment site builder with SSG support
- **CI/CD** — workflow dispatch, run history, pipeline generation

See [PAGES.md](PAGES.md) for the Pages builder system.

### 🛠 DevOps

Operational health cards organized by domain:

- **Security** — vulnerability scanning, dependency audit
- **Testing** — test generation, coverage tracking
- **Quality** — linting, formatting, code health
- **Packages** — dependency management, update suggestions
- **Documentation** — docs generation, coverage
- **Kubernetes** — live cluster status, validation
- **Terraform** — state management, drift detection
- **DNS & CDN** — DNS record generation, CDN configuration
- **Environment & IaC** — infrastructure detection, env management

### 🔍 Audit

Deep security and quality analysis:

- **L0 System Profile** — OS, hardware, tool detection
- **L1 Classification** — dependency parsing, structure analysis
- **L2 Scoring** — code health, repo health, risk assessment
- Findings with severity, dismiss with comments
- Drill-down modals for each audit category

### 🐛 Debugging

Diagnostic tools:
- Audit log viewer with filters
- State inspector (view raw JSON)
- Health detail (circuit breaker states, retry queue)
- Config dump

---

## Template Architecture

The web admin uses a **partial-per-tab** pattern with JS logic organized into
**domain subdirectories** under `scripts/`. Each directory is a set of raw JS
files sharing the same `<script>` scope via Jinja2 `{% include %}` directives.

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
└── scripts/                            # ⚠️ RAW JAVASCRIPT (not HTML pages)
    ├── globals/                        # Shared utilities
    │   ├── _api.html                   #   api() function, base URL
    │   ├── _cache.html                 #   Session/memory caching
    │   ├── _modal.html                 #   Modal show/hide
    │   ├── _card_builders.html         #   DevOps card rendering
    │   ├── _auth_modal.html            #   SSH passphrase auth
    │   ├── _missing_tools.html         #   Tool availability checks
    │   └── _ops_modal.html             #   Operations modal
    │
    ├── content/                        # 📁 Content tab — 17 files
    │   ├── _init.html                  #   Global variables, state
    │   ├── _content.html               #   Tab entry point
    │   ├── _nav.html                   #   Folder bar, mode switch, hash nav
    │   ├── _browser.html               #   File listing, search, gallery
    │   ├── _preview.html               #   File preview + edit
    │   ├── _preview_enc.html           #   Encrypted file preview
    │   ├── _glossary.html              #   Glossary/outline panel
    │   ├── _smart_folders.html         #   Smart folder virtual tree
    │   ├── _upload.html                #   Upload, drag-drop
    │   ├── _actions.html               #   File CRUD, encrypt, release
    │   ├── _chat.html                  #   Chat interface
    │   ├── _chat_refs.html             #   Chat reference resolution
    │   ├── _archive.html               #   Archive browser
    │   ├── _archive_actions.html       #   Archive operations
    │   ├── _archive_modals.html        #   Archive modal handlers
    │   └── _modal_preview.html         #   Modal file preview
    │
    ├── secrets/                        # 🔐 Secrets tab
    │   ├── _init.html, _render.html, _form.html
    │   ├── _sync.html, _keys.html, _vault.html
    │
    ├── integrations/                   # 🔌 Integrations tab — 15 files
    │   ├── _init.html                  #   State + card metadata
    │   ├── _git.html, _github.html     #   Git, GitHub cards
    │   ├── _cicd.html, _docker.html    #   CI/CD, Docker cards
    │   ├── _k8s.html, _terraform.html  #   K8s, Terraform cards
    │   ├── _pages.html, _pages_config.html, _pages_sse.html
    │   └── ... (+ dns, changelog, artifacts)
    │
    ├── devops/                         # 🛠 DevOps tab — 13 files
    │   ├── _init.html                  #   State + card metadata
    │   ├── _security.html, _testing.html, _quality.html
    │   ├── _packages.html, _docs.html, _env.html
    │   ├── _k8s.html, _terraform.html, _dns.html
    │   └── ...
    │
    ├── wizard/                         # 🧙 Setup wizard — 10 files
    ├── audit/                          # 🔍 Audit tab — 7 files
    ├── assistant/                      # Assistant panel — 7 files
    ├── k8s_wizard/                     # K8s sub-wizard — 9 files
    ├── docker_wizard/                  # Docker sub-wizard — 3 files
    ├── auth/                           # Auth modules — 3 files
    │
    ├── _dashboard.html                 # Dashboard tab JS
    ├── _commands.html                  # Commands tab JS
    ├── _debugging.html                 # Debugging tab JS
    ├── _settings.html                  # Settings JS
    ├── _tabs.html                      # Tab switching, hash-based deep linking
    ├── _theme.html                     # Dark/light toggle
    ├── _lang.html                      # i18n / Google Translate
    ├── _monaco.html                    # Monaco editor integration
    ├── _event_stream.html              # Server-sent events
    ├── _stage_debugger.html            # Stage debugger
    ├── _dev_mode.html                  # Dev mode toggle
    └── _boot.html                      # Init on DOMContentLoaded
```

**Iron rule**: No business logic in templates. All actions call API endpoints.
Templates are purely for rendering.

---

## API Structure

All API endpoints are Flask Blueprints organized in `routes/` sub-packages:

| Blueprint Package | Prefix | Purpose |
|-------------------|--------|---------|
| `routes/api/` | `/api/` | Core: status, run, detect, health |
| `routes/vault/` | `/api/vault/` | Lock, unlock, status, export, import |
| `routes/secrets/` | `/api/secrets/` | List, set, delete, push, pull |
| `routes/content/` | `/api/content/` | Browse, preview, encrypt, upload, glossary, peek |
| `routes/chat/` | `/api/chat/` | Chat threads, messages, sync |
| `routes/audit/` | `/api/audit/` | Security audit scan, findings, dismiss |
| `routes/devops/` | `/api/devops/` | DevOps card operations, prefs |
| `routes/integrations/` | `/api/git/`, `/api/gh/` | Git and GitHub operations |
| `routes/k8s/` | `/api/k8s/` | Kubernetes cluster, wizard, helm |
| `routes/docker/` | `/api/docker/` | Docker operations |
| `routes/terraform/` | `/api/terraform/` | Terraform operations |
| `routes/pages/` | `/api/pages/` | Segments, builders, build, deploy |
| `routes/backup/` | `/api/backup/` | Backup, restore, archive |
| `routes/smart_folders/` | `/api/smart-folders/` | Smart folder tree, file access |
| `routes/config/` | `/api/config/` | Configuration management |
| + 16 more | various | CI, DNS, events, git_auth, metrics, etc. |

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
