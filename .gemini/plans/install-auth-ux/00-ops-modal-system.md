# Ops Modal System — Standardized Install & Auth UX

## Goal
Replace ad-hoc install/auth handling with a unified modal system that offers
multiple paths (in-process, terminal spawn, token paste, copy command fallback)
and detects completion automatically.

## Status: ✅ IMPLEMENTED (Phase 1)

### Completed files

| File | Action | Status |
|------|--------|--------|
| `src/core/services/terminal_ops.py` | **NEW** | ✅ Terminal detection, spawning, script spawn |
| `src/core/services/git_gh_ops.py` | **EDIT** | ✅ Added `gh_auth_login(token=)` and `gh_auth_token()` |
| `src/core/services/git_ops.py` | **EDIT** | ✅ Re-exports `gh_auth_login`, `gh_auth_token` |
| `src/ui/web/routes_integrations.py` | **EDIT** | ✅ Added `POST /gh/auth/login`, `GET /gh/auth/token` |
| `_globals.html` | **EDIT** | ✅ Unified `_showOpsModal(config)`, `_showGhAuthModal()` |
| `_integrations_github.html` | **EDIT** | ✅ Auth button replaces static "run command" |
| `_integrations_setup_github.html` | **EDIT** | ✅ Auth button replaces command copy |
| `_secrets_render.html` | **EDIT** | ✅ Auth button in status alert |
| `_wizard_integrations.html` | **EDIT** | ✅ Auth button + re-detect after success |

### Architecture

Two operation families:

| Family | Examples | Mechanism |
|--------|----------|-----------|
| **Install** (non-interactive) | apt install, snap install | sudo password piped via stdin |
| **Auth / Interactive** (interactive) | gh auth login, docker login | Spawned terminal OR token paste |

### Four strategies (multi-path)

| Strategy | When | How |
|----------|------|-----|
| **A. In-process** | Non-interactive, sudo piped | `_showInstallModal` (was `_showSudoInstallModal`) |
| **B. Spawn terminal** | Interactive (OAuth, config) | Backend spawns gnome-terminal/xterm/etc |
| **C. Token paste** | Headless / no desktop | Modal with token input → `gh auth login --with-token` |
| **D. Copy command** | Fallback when no terminal | Show command + 📋 Copy + manual Check Status |

### Frontend API

```js
// Install mode
_showOpsModal({
  type: 'install',
  toolId: 'gh',
  toolLabel: 'GitHub CLI',
  onSuccess: () => _refreshAfterInstall(),
});

// Auth mode
_showOpsModal({
  type: 'auth',
  title: '🔑 Authenticate GitHub',
  description: 'Connect your GitHub account via the gh CLI.',
  loginEndpoint: '/gh/auth/login',
  pollEndpoint: '/integrations/gh/status',
  pollCheck: (d) => d.authenticated === true,
  tokenHint: 'Use a GitHub Personal Access Token',
  tokenUrl: 'https://github.com/settings/tokens',
  onSuccess: () => _refreshAfterInstall(),
});

// Convenience
_showGhAuthModal(optionalOnSuccess);
```

### Backend endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/gh/auth/login` | POST | Token mode (`{token:"ghp_…"}`) or interactive (`{}`) |
| `/api/gh/auth/token` | GET | Extract token from already-authed gh CLI |
| `/api/gh/auth/logout` | POST | (existing) Logout |

### Completion detection

For terminal-spawned operations, the frontend polls the relevant status endpoint:
- **gh auth**: `GET /api/integrations/gh/status` → check `authenticated`
- Animated spinner + elapsed timer in the modal status area
- Timeout after 5 minutes with "Check Now" fallback button

### Backwards compatibility

- `_showSudoInstallModal` is a thin wrapper → `_showOpsModal({ type: 'install', ... })`
- `installToolFromBanner` stays unchanged (calls `_showOpsModal` internally)
- All four caller files updated to use new functions

## Future extensions (Phase 2+)

- Docker login modal (same pattern, different endpoint)
- Generic `POST /api/ops/spawn-terminal` for arbitrary commands
- Signal file based completion detection (instead of polling)
- Cloud provider auth flows (AWS, GCP, Azure)
