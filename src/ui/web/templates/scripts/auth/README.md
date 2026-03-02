# Auth — Git & GitHub CLI Authentication

> **2 files. 478 lines. The credential gate for all remote operations.**
>
> Before anything touches a git remote (sync, push, chat, pull requests,
> secrets sync, CI workflows), it must pass through these two gatekeepers.
> Git auth handles SSH passphrase and HTTPS token credentials. GitHub CLI
> auth handles `gh` installation and OAuth authentication. Both follow
> the same promise-based pattern: check status → show modal if needed →
> resolve when ready.

---

## How It Works

The auth system has two independent but parallel subsystems that share
the same behavioral contract:

```
┌──────────────────────────────────────────────────────────────────┐
│ Boot Sequence (_boot.html, line 48-49)                           │
│                                                                    │
│  Promise.all([                                                    │
│      checkGitAuth(),     ← probe /api/git/auth-status             │
│      checkGhStatus(),    ← probe /api/integrations/gh/status      │
│  ])                                                                │
│                                                                    │
│  Result: _gitAuthStatus and _ghAuthStatus cached for the session  │
│          Modal shown only if credentials needed AND pref allows    │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│ On-Demand Gate (called by consumers before network operations)    │
│                                                                    │
│  Git operations:                                                   │
│    if (!(await ensureGitAuth())) return;                           │
│    // SSH/HTTPS credentials are ready                              │
│                                                                    │
│  GitHub CLI operations:                                            │
│    if (!(await ensureGhReady())) return;                           │
│    // gh installed AND authenticated                               │
│                                                                    │
│  Both functions return Promise<boolean>:                           │
│    true  → proceed with the operation                              │
│    false → user cancelled or auth still broken                     │
└──────────────────────────────────────────────────────────────────┘
```

### The Two-Phase Contract

Both auth files follow the exact same pattern:

```
Phase 1 — BOOT (passive probe)
    │
    ├── Hit status endpoint
    ├── Cache result in module-level variable
    ├── If OK → do nothing
    └── If NOT OK → show modal OR defer (based on user preference)

Phase 2 — ON-DEMAND (active gate)
    │
    ├── Check cached status
    ├── If OK → resolve(true) immediately
    ├── If NOT OK → show modal, set _ensureResolve callback
    │     │
    │     ├── User provides credentials → POST to auth endpoint
    │     │     ├── Success → resolve(true), close modal
    │     │     └── Failure → show error, stay in modal
    │     │
    │     └── User cancels/closes → resolve(false)
    │
    └── Consumer uses boolean to decide whether to proceed
```

This design means:
- **No wasted modals** — if auth is already OK, the user never sees anything
- **No blocking** — consumers can proceed immediately if cached status is OK
- **No race conditions** — only one modal can be open at a time
- **No redundant checks** — status is cached after first probe

### SSE-Triggered Auth

When the backend detects an auth failure during a background operation
(e.g., auto-sync timer), it sends an `auth:needed` SSE event. The
event stream handler (`_event_stream.html`) calls `showGitAuthModal()`
with `context='event'`, which shows a context-aware message:

```
Boot prompt:                          SSE-triggered prompt:
┌──────────────────────────┐         ┌──────────────────────────────┐
│ 🔒 SSH Secure Mode       │         │ ⚠️ Git operation blocked      │
│ detected                 │         │                                │
│                          │         │ A git network operation was    │
│ Your SSH key is          │         │ attempted but your SSH key is  │
│ passphrase-protected...  │         │ not unlocked. Please enter     │
│                          │         │ your passphrase below...       │
└──────────────────────────┘         └──────────────────────────────┘
```

---

## File Map

```
auth/
├── _git_auth.html    Git SSH/HTTPS credential management (300 lines)
├── _gh_auth.html     GitHub CLI install + auth gating (178 lines)
└── README.md         This file
```

---

## `_git_auth.html` — Git SSH/HTTPS Credentials (300 lines)

Handles two credential types for git remote access:

### State Variables

| Variable | Type | Purpose |
|----------|------|---------|
| `_gitAuthStatus` | `Object\|null` | Cached auth probe result: `{ok, needs, ssh_key, remote_url}` |
| `_ensureAuthResolve` | `Function\|null` | Pending Promise `resolve()` from `ensureGitAuth()` |
| `_gitAuthContext` | `string\|null` | `'event'` when triggered by SSE, `null` for boot/manual |
| `_gitAuthModalOpen` | `boolean` | Prevents duplicate modals (single-modal guard) |

### Functions

| Function | What It Does |
|----------|-------------|
| `checkGitAuth()` | Boot probe — `GET /api/git/auth-status`, cache result, show modal if needed based on pref |
| `ensureGitAuth()` | On-demand gate — returns `Promise<boolean>`, shows modal if auth not ready |
| `showGitAuthModal(type, context)` | Render SSH passphrase or HTTPS token modal |
| `submitGitAuthSSH()` | Submit SSH passphrase — `POST /api/git/auth-ssh` |
| `submitGitAuthHTTPS()` | Submit HTTPS token — `POST /api/git/auth-https` |
| `_gitAuthSkip()` | Close modal, save checkbox pref, resolve waiter with `false` |
| `_saveNoStartupPref()` | Persist "Don't ask on startup" checkbox to preferences |

### SSH Passphrase Flow

```
checkGitAuth()  (boot)
    │
    ├── GET /api/git/auth-status
    │     └── Response: { ok: false, needs: "ssh_passphrase",
    │                     ssh_key: "~/.ssh/id_ed25519",
    │                     remote_url: "git@github.com:user/repo.git" }
    │
    ├── Check pref: sshPassphrasePrompt
    │     ├── 'always' (default) → show modal immediately
    │     └── 'on-demand' → skip, cache status for later
    │
    └── showGitAuthModal('ssh')
          │
          ├── Show key name + remote URL
          ├── Password input with Enter-to-submit
          ├── "Don't ask on startup" checkbox
          │
          └── submitGitAuthSSH()
                ├── POST /api/git/auth-ssh { passphrase: "..." }
                ├── Success → update _gitAuthStatus, resolve waiter, toast
                └── Failure → show error, clear input, refocus
```

### HTTPS Token Flow

```
showGitAuthModal('https')
    │
    ├── Show remote URL
    ├── PAT input (placeholder: ghp_xxxxxxxxxxxx)
    │
    └── submitGitAuthHTTPS()
          ├── POST /api/git/auth-https { token: "ghp_..." }
          ├── Success → update _gitAuthStatus, resolve waiter, toast
          └── Failure → show error
```

### User Preference: Boot Prompt Control

The SSH modal includes a "Don't ask on startup" checkbox. When checked:

1. `_saveNoStartupPref()` sets preference `sshPassphrasePrompt = 'on-demand'`
2. On next boot, `checkGitAuth()` reads this pref and skips the modal
3. The status is still cached — when a consumer calls `ensureGitAuth()`,
   the modal appears then (just-in-time, not at boot)
4. The checkbox state is pre-filled from the saved preference

This lets power users avoid the passphrase popup on every boot while
still getting prompted when a feature actually needs git remote access.

### Modal Details

The SSH modal includes:
- **Context-aware explainer** — different messages for boot vs SSE trigger
- **Key name display** — shows which SSH key (`~/.ssh/id_ed25519`)
- **Remote URL** — shows the git remote being authenticated against
- **Enter-to-submit** — `onkeydown` handler for quick passphrase entry
- **Auto-focus** — input field receives focus after modal opens (100ms delay for DOM render)
- **Button state management** — disables "Unlock →" button during POST, re-enables on response
- **Error display** — inline error below input, cleared on retry

---

## `_gh_auth.html` — GitHub CLI Install + Auth (178 lines)

A two-gate system: first ensure `gh` is installed, then ensure it's
authenticated. If either check fails, the appropriate modal is shown.

### State Variables

| Variable | Type | Purpose |
|----------|------|---------|
| `_ghAuthStatus` | `Object\|null` | Cached status: `{installed, authenticated, version, repo, raw}` |
| `_ensureGhResolve` | `Function\|null` | Pending Promise `resolve()` from `ensureGhReady()` |

### Functions

| Function | What It Does |
|----------|-------------|
| `checkGhStatus()` | Boot probe — `GET /api/integrations/gh/status`, cache result |
| `ensureGhReady()` | On-demand gate — returns `Promise<boolean>` (both installed AND authenticated) |
| `_showGhGate()` | Route to install gate or auth gate based on current status |
| `_showGhInstallGate()` | Show "GitHub CLI Required" modal with install button |
| `_ghGateCancel()` | Close modal, resolve waiter with `false` |
| `_ghGateInstall()` | Delegate to `installWithPlan('gh', ...)` with chained auth check |
| `_showGhAuthGate()` | Delegate to `_showGhAuthModal()` (from globals/_auth_modal.html) |

### Two-Gate Decision Tree

```
ensureGhReady()
    │
    ├── installed && authenticated → resolve(true) immediately
    │
    ├── !installed → _showGhInstallGate()
    │     │
    │     ├── User clicks "Install GitHub CLI"
    │     │     └── installWithPlan('gh', 'GitHub CLI', {
    │     │           onComplete: async () => {
    │     │               await checkGhStatus();
    │     │               if (authenticated) → resolve(true)  ← DONE
    │     │               else → _showGhAuthGate()            ← CHAIN
    │     │           }
    │     │         })
    │     │
    │     └── User clicks "Cancel" → resolve(false)
    │
    └── installed && !authenticated → _showGhAuthGate()
          │
          └── _showGhAuthModal(() => {
                  await checkGhStatus();
                  resolve(authenticated);
              })
              │
              └── Auth modal from globals/_auth_modal.html
                  (device flow / terminal / token paste)
```

### Chained Install → Auth

The most interesting behavior is the install-to-auth chain. When the
user installs `gh` via `installWithPlan()`:

1. **onComplete** fires after successful installation
2. `checkGhStatus()` re-probes — `gh` is now installed
3. If also authenticated (some install methods auto-auth) → resolve immediately
4. If NOT authenticated → chain to `_showGhAuthGate()` with a 300ms delay
   (lets the install modal cleanup animation finish)

This creates a seamless two-step flow: install → auth → ready, without
the user needing to know about the two separate states.

### Status Data Shape

```javascript
_ghAuthStatus = {
    installed: true,          // gh binary found in PATH
    authenticated: true,      // gh auth status returns logged-in
    version: "2.45.0",        // gh --version output
    repo: "user/repo",        // current repo context (if detected)
    raw: { ... },             // full API response
};
```

---

## Dependency Graph

```
globals/_api.html            ← api(), esc(), toast() — used by both files
globals/_modal.html          ← modalOpen(), modalClose() — used by both files
globals/_ops_modal.html      ← installWithPlan() — used by _gh_auth.html
globals/_auth_modal.html     ← _showGhAuthModal() — used by _gh_auth.html
    ↑
_git_auth.html               ← standalone git credential management
_gh_auth.html                ← gh install + auth gating
    ↑
_boot.html                   ← calls checkGitAuth() + checkGhStatus() at boot
_event_stream.html           ← calls showGitAuthModal() on auth:needed SSE events
```

The two files are independent of each other — git auth doesn't need
gh auth, and vice versa. They share the same globals dependencies but
never call each other's functions.

---

## Consumers

### `ensureGitAuth()` Consumers

| File | Context | Why |
|------|---------|-----|
| `content/_chat.html` (line 86) | Auto-poll sync timer | Needs git remote to sync chat history |
| `content/_chat.html` (line 1051) | Manual chat sync button | Pushing chat messages to remote |
| `integrations/_git.html` (line 161) | Git push operation | Pushing commits to remote |
| `integrations/_git.html` (line 174) | Git pull operation | Pulling from remote |
| `integrations/_pages_config.html` (line 479) | Pages deploy push | Pushing site to GitHub Pages |
| `_event_stream.html` (line 411, 413) | SSE auth:needed event | Backend git operation blocked |

### `ensureGhReady()` Consumers

| File | Context | Why |
|------|---------|-----|
| `integrations/_cicd.html` (line 141) | CI/CD workflow operations | Needs `gh` for workflow management |
| `integrations/_github.html` (lines 118, 235, 297) | GitHub live panels + PR operations | Needs `gh` for API calls |
| `secrets/_render.html` (line 67) | GitHub secrets sync install button | Needs `gh` to sync secrets |
| `secrets/_sync.html` (lines 16, 170) | Secrets push to GitHub | Needs `gh` for secrets API |

### Boot Consumers

| File | Line | Function |
|------|------|----------|
| `_boot.html` | 48 | `checkGitAuth()` |
| `_boot.html` | 49 | `checkGhStatus()` |

---

## API Endpoints

### Git Auth (route: `git_auth/credentials.py`)

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/git/auth-status` | GET | Probe SSH/HTTPS auth status — returns `{ok, needs, ssh_key, remote_url}` |
| `/api/git/auth-ssh` | POST | Submit SSH passphrase — attempts `ssh-add` with the passphrase |
| `/api/git/auth-https` | POST | Store HTTPS PAT — writes to git credential helper |

### GitHub CLI Auth (route: `integrations/gh_auth.py`)

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/integrations/gh/status` | GET | Probe `gh` installation and auth status (route: `integrations/github.py`) |
| `/api/gh/auth/device` | POST | Start OAuth device flow — returns one-time code + URL |
| `/api/gh/auth/device/poll` | GET | Poll device flow session for completion |
| `/api/gh/auth/login` | POST | Submit credentials (token or interactive) |
| `/api/gh/auth/token` | GET | Check current token info |
| `/api/gh/auth/terminal/poll` | GET | Poll terminal signal file for auth status |

---

## Advanced Feature Showcase

### 1. Promise-Gate Pattern (One-Line Auth Check)

Both auth modules expose an `ensure*()` function that returns
`Promise<boolean>` — it resolves to `true` when credentials are ready,
or `false` if the user cancels. This lets every consumer gate on auth
with a single line:

```javascript
// Any consumer — one line, no try/catch, no UI flicker
if (!(await ensureGitAuth())) return;
// ... proceed with git operation

if (!(await ensureGhReady())) return;
// ... proceed with gh API call
```

The implementation stores the resolve callback in a module-level variable
so the modal's submit handler can resolve the caller's promise:

```javascript
// _git_auth.html — lines 54-81
function ensureGitAuth() {
  if (_gitAuthStatus && _gitAuthStatus.ok) return Promise.resolve(true);

  return new Promise((resolve) => {
    _ensureAuthResolve = resolve;   // stored for submitGitAuthSSH to call

    if (!_gitAuthStatus) {
      // Status not fetched yet — fetch, then decide
      api('/git/auth-status').then(status => {
        _gitAuthStatus = status;
        if (status.ok) { _ensureAuthResolve = null; resolve(true); return; }
        if (status.needs === 'ssh_passphrase') showGitAuthModal('ssh');
        else if (status.needs === 'https_credentials') showGitAuthModal('https');
        else { _ensureAuthResolve = null; resolve(false); }
      }).catch(() => { _ensureAuthResolve = null; resolve(false); });
    } else if (_gitAuthStatus.needs === 'ssh_passphrase') {
      showGitAuthModal('ssh');
    } else if (_gitAuthStatus.needs === 'https_credentials') {
      showGitAuthModal('https');
    } else {
      _ensureAuthResolve = null;
      resolve(false);
    }
  });
}
```

The modal's close handler also resolves with `false`, preventing dangling
promises if the user dismisses the modal.

### 2. Context-Aware Modal Explainer

The SSH passphrase modal renders different explanations based on how it
was triggered — boot probe vs SSE `auth:needed` event:

```javascript
// _git_auth.html — lines 96-106
const explainer = context === 'event'
  ? '<strong>⚠️ Git operation blocked</strong><br>'
    + 'A git network operation was attempted but your SSH key is not '
    + 'unlocked. Please enter your passphrase below, then retry your '
    + 'operation or refresh the page.'
  : '<strong>🔒 SSH Secure Mode detected</strong><br>'
    + 'Your SSH key is <em>passphrase-protected</em>, which is the recommended '
    + 'security configuration. Some features (Git sync, remote operations) '
    + 'require access to the remote repository through this key. '
    + 'Please enter your passphrase so we can unlock it for this session.';
```

The same context controls the success toast message (line 236-238):
- Event-triggered: `"🔓 SSH key unlocked — retry your operation or refresh"`
- Boot-triggered: `"🔓 SSH key unlocked — git sync is ready"`

### 3. Preference-Gated Boot Prompt with On-Demand Deferral

`checkGitAuth()` reads the `sshPassphrasePrompt` preference to decide
whether to show the modal at page load. When set to `on-demand`, the
function returns early without showing the modal — but still caches
the auth status so that `ensureGitAuth()` can trigger it later:

```javascript
// _git_auth.html — lines 23-44
async function checkGitAuth() {
  _gitAuthStatus = await api('/git/auth-status');
  if (_gitAuthStatus.ok) return;

  const promptPref = prefsGet('sshPassphrasePrompt');  // 'always' | 'on-demand'

  if (_gitAuthStatus.needs === 'ssh_passphrase') {
    if (promptPref === 'on-demand') {
      // Skip boot prompt — status is cached for ensureGitAuth()
      return;
    }
    showGitAuthModal('ssh');
  } else if (_gitAuthStatus.needs === 'https_credentials') {
    showGitAuthModal('https');
  }
}
```

The preference is toggled by a checkbox inside the SSH modal itself
(line 132-136), with state saved via `prefsSet()` on both Skip and
Unlock actions.

### 4. Install → Auth Chain with Status Re-Check

The GitHub CLI gate chains two sequential operations: install the `gh`
binary, then authenticate — with a status re-check between them to
determine the next step:

```javascript
// _gh_auth.html — lines 136-163
function _ghGateInstall() {
  modalClose();
  setTimeout(() => {
    installWithPlan('gh', 'GitHub CLI', {
      onComplete: async () => {
        // Re-check status after install
        await checkGhStatus();
        if (_ghAuthStatus && _ghAuthStatus.installed) {
          if (_ghAuthStatus.authenticated) {
            // Fully ready — user may have been auto-logged in
            toast('✅ GitHub CLI installed and authenticated', 'success');
            if (_ensureGhResolve) { _ensureGhResolve(true); _ensureGhResolve = null; }
          } else {
            // Installed but needs auth — chain to auth gate
            toast('✅ GitHub CLI installed — authentication required', 'info');
            setTimeout(() => _showGhAuthGate(), 300);
          }
        } else {
          if (_ensureGhResolve) { _ensureGhResolve(false); _ensureGhResolve = null; }
        }
      },
      onCancel: () => {
        if (_ensureGhResolve) { _ensureGhResolve(false); _ensureGhResolve = null; }
      },
    });
  }, 200);
}
```

The 200ms/300ms delays ensure modal close animations finish before
the next modal opens — without them, the overlay transition flickers.

### 5. Singleton Modal Guard

Multiple SSE `auth:needed` events can arrive while the auth modal is
already showing (e.g., parallel git operations all fail). The singleton
guard prevents stacking duplicate modals:

```javascript
// _git_auth.html — lines 21, 83-86
let _gitAuthModalOpen = false;

function showGitAuthModal(type, context) {
  if (_gitAuthModalOpen) return;   // ← guard
  _gitAuthModalOpen = true;
  // ... render modal ...
}
```

The flag is reset to `false` in the modal's `onClose` callback
(lines 144, 180), ensuring the guard is released regardless of whether
the user submits, skips, or clicks the overlay.

---

### Feature Coverage Summary

| Feature | File | Key Functions | Detail |
|---------|------|--------------|--------|
| Promise-gate (SSH/HTTPS) | `_git_auth.html` | `ensureGitAuth()` | Returns `Promise<boolean>`, resolves via `_ensureAuthResolve` |
| Promise-gate (GitHub CLI) | `_gh_auth.html` | `ensureGhReady()` | Same pattern, checks install + auth separately |
| Boot status probe (git) | `_git_auth.html` | `checkGitAuth()` | Caches `_gitAuthStatus`, pref-gated prompt |
| Boot status probe (gh) | `_gh_auth.html` | `checkGhStatus()` | Caches `_ghAuthStatus`, best-effort |
| SSH passphrase modal | `_git_auth.html` | `showGitAuthModal('ssh')` | Context-aware explainer, preference checkbox |
| HTTPS credential modal | `_git_auth.html` | `showGitAuthModal('https')` | PAT input, same gate pattern |
| Preference persistence | `_git_auth.html` | `_saveNoStartupPref()` | `prefsSet('sshPassphrasePrompt', ...)` |
| Github CLI install gate | `_gh_auth.html` | `_showGhInstallGate()` | Delegates to `installWithPlan('gh', ...)` |
| Install → auth chaining | `_gh_auth.html` | `_ghGateInstall()` | Status re-check between steps |
| Auth gate (gh) | `_gh_auth.html` | `_showGhAuthGate()` | Delegates to `_showGhAuthModal()` from globals |
| Singleton modal guard | `_git_auth.html` | `_gitAuthModalOpen` flag | Prevents duplicate modals from SSE events |

---

## Design Decisions

### Why two separate files instead of one auth module?

Git auth (SSH/HTTPS) and GitHub CLI auth (`gh`) are **independent
concerns** that happen to share the word "auth":

- Git auth manages **transport credentials** — the plumbing layer
  that makes `git push`/`git pull` work
- GitHub CLI auth manages **a specific tool** — install it, log it in,
  then use its API

They have different status APIs, different credential types, different
failure modes, and different recovery flows. Merging them would create
a confusing module with two unrelated state machines.

### Why cache status at boot instead of checking on demand?

Boot probing is nearly free (two fast GET requests in parallel) and
enables instant gate checks. Without caching, every `ensureGitAuth()`
call would need a network request, adding latency to every git
operation. The cached status is conservative — if the cache says
"OK", the operation proceeds. If the status changes (e.g., SSH agent
times out), the backend's `auth:needed` SSE event triggers a re-prompt.

### Why a preference for boot prompt behavior?

Some users work primarily on local operations and find the SSH
passphrase modal annoying on every boot. The "Don't ask on startup"
checkbox converts to `on-demand` mode, where the modal only appears
when a feature actually needs remote access. This respects user
autonomy while still enforcing auth when required.

### Why resolve with `false` instead of rejecting the promise?

Rejection would require try/catch in every consumer. Returning `false`
lets consumers use a simple `if` statement:
```javascript
if (!(await ensureGitAuth())) return;
```
This is the lightest possible gate pattern — one line, no error handling
needed, no UI flicker.
