
# Phase 2: The Real Product

> Phase 1 (MS-0 → MS-9) built the engine infrastructure — detection, adapters,
> CLI, test suite. Phase 2 builds the **actual product features** on top of it,
> ported and adapted from the continuity-orchestrator.

---

## Architecture: What We're Building

The devops-control-plane web admin becomes a **multi-tab application** with the
same structural pattern as the continuity-orchestrator admin:

```
┌──────────────────────────────────────────────────────────────┐
│  📊 Dashboard │ 🧙 Setup │ 🔐 Secrets │ ⚡ Commands │ ...   │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Tab content area (one tab visible at a time)                │
│                                                              │
│  Each tab is a Jinja2 partial: partials/_tab_<name>.html     │
│  Each tab's JS is a partial:   scripts/_<name>.html          │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### Templates Structure (adapted from continuity-orchestrator)

```
src/ui/web/templates/
├── dashboard.html              # Master template (includes all partials)
├── partials/
│   ├── _head.html              # <head>, CSS, meta
│   ├── _nav.html               # Tab bar navigation
│   ├── _tab_dashboard.html     # 📊 Overview, status cards, activity
│   ├── _tab_wizard.html        # 🧙 Multi-step setup flow
│   ├── _tab_secrets.html       # 🔐 Secrets manager (vault)
│   ├── _tab_commands.html      # ⚡ Execute capabilities
│   ├── _tab_content.html       # 📝 Docs, media, archive browser
│   ├── _tab_integrations.html  # 🔌 External services
│   ├── _tab_debugging.html     # 🐛 Logs, diagnostics
│   └── _vault.html             # 🔒 Vault lock/unlock modal (overlay)
└── scripts/
    ├── _globals.html           # Shared JS helpers, API client
    ├── _theme.html             # Dark/light theme toggle
    ├── _tabs.html              # Tab switching, deep linking (#hash)
    ├── _dashboard.html         # Dashboard tab logic
    ├── _wizard.html            # Wizard step navigation
    ├── _secrets.html           # Secrets form, push/pull
    ├── _commands.html          # Capability execution
    ├── _content.html           # Content browsing, media vault
    ├── _integrations.html      # Integration setup
    ├── _vault.html             # Vault lock/unlock/auto-lock logic
    └── _boot.html              # Init on DOMContentLoaded
```

### Backend Routes (new blueprints)

```
src/ui/web/
├── routes_api.py               # Existing: status, run, detect, health, audit
├── routes_vault.py             # NEW: /api/vault/lock, unlock, status, export
├── routes_secrets.py           # NEW: /api/secrets/list, set, delete, push
├── routes_content.py           # NEW: /api/content/list, encrypt, decrypt, upload
└── vault.py                    # NEW: Core vault logic (AES-256-GCM, PBKDF2)
```

---

## Feature Breakdown

### 1. 🔐 Secrets Vault (`.env` encryption)

**Ported from**: `continuity-orchestrator/src/admin/vault.py` + `routes_vault.py`

The secrets vault encrypts `.env` files using AES-256-GCM with PBKDF2 key
derivation. The encrypted file (`.env.vault`) can be safely committed to git.

| Feature | Description |
|---|---|
| **Lock** | Encrypt `.env` → `.env.vault` + secure-delete original |
| **Unlock** | Decrypt `.env.vault` → `.env` (with passphrase) |
| **Quick-lock** | Re-lock using in-memory passphrase (no re-entry) |
| **Auto-lock** | Timer-based auto-lock after N minutes of inactivity |
| **Export** | Create portable encrypted backup (higher KDF iterations) |
| **Import** | Restore from exported vault file with diff preview |
| **Register** | Store passphrase in memory for auto-lock (no encrypt) |
| **Secrets list** | Parse `.env`, display keys (masked values) with edit UI |

**Crypto specs** (matching continuity-orchestrator):
- Algorithm: AES-256-GCM
- KDF: PBKDF2-SHA256, 480,000 iterations (600,000 for exports)
- Salt: 16 bytes random
- IV: 12 bytes random
- Tag: 16 bytes (GCM authentication)
- Secure delete: 3-pass random overwrite before unlink

**Adaptation notes**:
- The continuity-orchestrator vault targets `.env` specifically
- For devops-control-plane, we generalize: any file can be vault-protected
  (`.env`, `secrets.yml`, `credentials.json`, etc.)
- Detection: scan project for known secret file patterns
- The UI shows a secrets list with masked values, edit, and per-key management

### 2. 📁 Content Vault (docs + media encryption)

**Ported from**: `continuity-orchestrator/src/content/crypto.py` + `routes_content.py`

The content vault handles **large files** that can't go in git — encrypted
binary format (not JSON/base64, avoiding the 33% size overhead).

| Feature | Description |
|---|---|
| **Detect folders** | Auto-detect `docs/`, `content/`, `media/`, custom paths |
| **Browse** | File browser for docs and media with preview |
| **Encrypt file** | Binary envelope: COVAULT magic + metadata + AES-256-GCM ciphertext |
| **Decrypt file** | Restore original with SHA-256 integrity verification |
| **Archive** | Move files to `archive/` folder (versioned, optional encrypt) |
| **Metadata** | Read filename, MIME type, size WITHOUT decrypting |
| **Large file support** | Files too big for git → encrypted + optional GitHub Release upload |

**Binary envelope format** (from continuity-orchestrator):
```
COVAULT_v1 | filename_len(2) | filename | mime_len(2) | mime |
sha256(32) | salt(16) | iv(12) | tag(16) | ciphertext
```

**Supported media types**:
- Images: jpg, png, gif, webp, svg
- Video: mp4, webm, mov
- Audio: mp3, wav, ogg
- Documents: pdf, docx, txt, md
- Archives: zip, tar.gz, 7z
- Any other file type (generic binary)

### 3. 🧙 Setup Wizard

**Ported from**: `continuity-orchestrator/templates/partials/_tab_wizard.html`

Multi-step onboarding flow that guides new users through project setup:

| Step | What it does |
|---|---|
| **Welcome** | Project name, description, detect existing config |
| **Modules** | Scan and confirm detected modules |
| **Stacks** | Assign/override stack types for each module |
| **Environments** | Configure dev/staging/prod environments |
| **Secrets** | Set up vault passphrase, identify secret files |
| **Content** | Configure content folders, encryption preferences |
| **Review** | Summary + generate `project.yml` |

### 4. ⚡ Commands Tab

The current "Execute a Capability" section, moved to its own tab with
the full context panel, results, and history.

### 5. 🔌 Integrations Tab

Connection management for external services:

| Integration | Purpose |
|---|---|
| **GitHub** | Repo link, Actions, Pages, Release uploads |
| **Git** | Local git status, branch, remote info |
| **Docker** | Container status, compose management |
| **CI/CD** | GitHub Actions, GitLab CI status |

### 6. 🐛 Debugging Tab

Diagnostic tools:

| Feature | Purpose |
|---|---|
| **Audit log viewer** | Browse audit entries with filters |
| **State inspector** | View/edit raw state JSON |
| **Health details** | Circuit breaker status, retry queue |
| **Config dump** | Show resolved configuration |
| **Stack resolver** | Test stack name → definition resolution |

---

## Implementation Milestones

### MS-10: Multi-Tab Shell + Theme
**Build the tab structure and move existing dashboard into it.**

- [ ] Split `dashboard.html` into Jinja2 partials
- [ ] Create `_head.html`, `_nav.html` with tab buttons
- [ ] Create `_tab_dashboard.html` (move existing content)
- [ ] Create `_tab_commands.html` (move "Execute a Capability")
- [ ] Create empty shells for other tabs
- [ ] JS: Tab switching with hash-based deep linking
- [ ] JS: Theme toggle (dark/light)
- [ ] CSS: Tab bar styling, active state
- [ ] CSS: Light mode color tokens
- [ ] Test: Existing web tests still pass

### MS-11: Secrets Vault (Core)
**Port vault.py from continuity-orchestrator.**

- [ ] `src/ui/web/vault.py` — AES-256-GCM encrypt/decrypt, PBKDF2
- [ ] Secure delete (3-pass overwrite)
- [ ] Lock/unlock/quick-lock/auto-lock logic
- [ ] Session passphrase management with threading lock
- [ ] Rate limiting on failed attempts
- [ ] `src/ui/web/routes_vault.py` — API endpoints
- [ ] Tests for crypto roundtrip, lock/unlock, rate limiting

### MS-12: Secrets UI
**Build the Secrets tab with vault controls.**

- [ ] `_tab_secrets.html` — secrets list, add/edit forms
- [ ] `_vault.html` — lock/unlock modal overlay
- [ ] `_secrets.html` (script) — form handling, API calls
- [ ] `_vault.html` (script) — lock toggle, auto-lock timer
- [ ] Vault status in nav bar (🔒/🔓 toggle)
- [ ] Export/import vault file UI
- [ ] Register passphrase banner

### MS-13: Content Vault (Core)
**Port content/crypto.py for binary file encryption.**

- [ ] `src/ui/web/content_crypto.py` — encrypt_file, decrypt_file
- [ ] Binary envelope format (COVAULT magic)
- [ ] Metadata reading (filename, mime, size without decrypt)
- [ ] SHA-256 integrity verification
- [ ] `src/ui/web/routes_content.py` — API endpoints
- [ ] Content folder detection (docs/, content/, media/ + custom)
- [ ] Tests for file encrypt/decrypt roundtrip, metadata read

### MS-14: Content UI
**Build the Content tab with file browser and media support.**

- [ ] `_tab_content.html` — file browser, preview pane
- [ ] Sub-modes: Docs / Media / Archive
- [ ] Upload, encrypt, decrypt, delete actions
- [ ] Media preview (images, video, audio inline)
- [ ] Archive management (move to archive/ folder)
- [ ] Large file indicator (> git limit)

### MS-15: Setup Wizard
**Multi-step onboarding flow.**

- [ ] `_tab_wizard.html` — step navigation, progress bar
- [ ] `_wizard.html` (script) — step logic, validation
- [ ] Steps: Welcome → Modules → Stacks → Envs → Secrets → Content → Review
- [ ] Generate `project.yml` from wizard data
- [ ] Dirty-state warning when leaving wizard

### MS-16: Integrations + Debugging
**Fill in the remaining tabs.**

- [ ] `_tab_integrations.html` — git status, GitHub links
- [ ] `_tab_debugging.html` — audit viewer, state inspector, health detail
- [ ] API routes for git status, state inspection
- [ ] Debugging: config dump, stack resolution tester

---

## Dependencies

The vault features need the `cryptography` package:

```
pip install cryptography
```

This is the same library used by the continuity-orchestrator.

---

## Priority Order

1. **MS-10** — Tab shell (unlocks everything else)
2. **MS-11 + MS-12** — Secrets vault (highest value, real security)
3. **MS-15** — Wizard (onboarding experience)
4. **MS-13 + MS-14** — Content vault (large scope, builds on vault)
5. **MS-16** — Integrations + debugging (polish)

---

## Estimated Effort

| Milestone | Effort | Cumulative |
|---|---|---|
| MS-10: Tab shell | 3-4h | 3-4h |
| MS-11: Vault core | 4-5h | 7-9h |
| MS-12: Secrets UI | 3-4h | 10-13h |
| MS-13: Content core | 4-5h | 14-18h |
| MS-14: Content UI | 4-6h | 18-24h |
| MS-15: Wizard | 3-4h | 21-28h |
| MS-16: Integrations | 3-4h | 24-32h |

**Total: ~24-32 hours across 7 milestones.**
