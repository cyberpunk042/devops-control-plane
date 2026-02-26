# Phase D0 — Identity & Dev Mode Gate

> **Status:** Planning
> **Created:** 2026-02-25
> **Parent:** Stage Debugger feature
> **Depends on:** Nothing (foundation phase)

---

## Objective

Establish the identity resolution layer that determines whether the
current operator is a project owner. When true, the rest of the stage
debugger infrastructure becomes available. When false, the entire
debugger is invisible — zero runtime cost, zero UI footprint.

---

## Problem Statement

The project needs a development & QA testing capability. But this
capability must NOT be visible to random users who clone or fork the
repo. It must be gated behind **owner identity** — the person(s) who
own this instance of the control plane.

The identity mechanism must be:
1. **Fork-friendly** — no hardcoded usernames, emails, or paths
2. **Repo-tracked** — the owner list travels with the repo
3. **Naturally populated** — the owner fills it during setup, just
   like they fill `project.yml` already
4. **Disable-able** — Settings panel toggle to turn dev mode off
   even if identity matches (e.g., doing a demo)
5. **Multi-owner** — supports teams, not just solo devs

---

## Identity Source Analysis

### Where do owners come from?

#### Option A: GitHub CODEOWNERS file

Standard location: `.github/CODEOWNERS` (or root `CODEOWNERS`)

Standard format:
```
# Lines map file patterns to GitHub @usernames or @teams
* @cyberpunk042
src/core/ @cyberpunk042 @teammate
```

**Pros:**
- Industry-standard file, every GitHub user knows it
- Tracked in git → forks carry it
- GitHub uses it for PR review assignment
- Already understood by the ecosystem

**Cons:**
- Contents are GitHub @usernames, NOT git display names
- Need to bridge: `git config user.name` ("Cyberpunk 042") ≠ `@cyberpunk042`
- The file format is path-pattern → usernames, not a simple owner list
- Parsing requires understanding the glob-pattern format

**Verdict:** The file exists for GitHub PR routing, not for identity
resolution. Using it would require either:
- A mapping layer (GitHub username → git display name)
- Forcing users to set their git user.name to their GitHub handle
- Making the CODEOWNERS file do double duty (fragile)

#### Option B: `project.yml` owners field

Current `project.yml`:
```yaml
version: 1
name: devops-control-plane
description: A general-purpose project control plane for DevOps automation
repository: github.com/cyberpunk042/devops-control-plane
# ... modules, environments, etc.
```

Proposed addition:
```yaml
owners:
  - name: "Cyberpunk 042"
  - name: "Another Dev"
```

**Pros:**
- Already the project identity file
- Already tracked in git → forks carry it
- Forker already edits it in the Setup Wizard
- Adding owners is natural (wizard step: "Who are you?")
- Direct `git config user.name` match — no mapping needed
- YAML parsing already exists in the codebase

**Cons:**
- Not an industry standard specifically for ownership
- `project.yml` does several jobs already

#### Option C: Dedicated `.github/CODEOWNERS` + identity mapping

Create CODEOWNERS for GitHub (PR reviews) AND add a local mapping:
```
# .github/CODEOWNERS (standard GitHub format)
* @cyberpunk042
```

```yaml
# project.yml (local identity)
owners:
  - github: cyberpunk042
    name: "Cyberpunk 042"
```

**Pros:**
- Standard CODEOWNERS file serves its actual purpose
- project.yml carries the display-name mapping
- Both travel with the repo

**Cons:**
- Two sources of truth for "who owns this"
- Sync overhead (add to CODEOWNERS, add to project.yml)

#### Decision: Option C (both files, each for its purpose)

**Rationale:**
- CODEOWNERS is a real Git/GitHub concept. It should exist and serve
  its standard purpose (PR review assignment).
- `project.yml` already serves as the project's self-description.
  Adding `owners:` there makes the display-name mapping live next to
  the project identity, where it belongs.
- The identity check reads ONLY `project.yml` `owners[].name`.
- The CODEOWNERS file is orthogonal — it's for GitHub, not for us.
- A future enhancement could auto-generate CODEOWNERS from project.yml
  owners if the GitHub username is provided.

---

## Identity Resolution Flow

### Detection: who is running this?

```
Step 1: Read local git identity
  $ git config user.name  →  "Cyberpunk 042"

Step 2: Read project.yml owners
  project.yml → owners: [{name: "Cyberpunk 042"}, ...]

Step 3: Match
  git_user_name IN [o.name for o in owners]
  → True  = owner
  → False = non-owner (or owners list is empty/absent)

Step 4: Settings override
  If localStorage 'dcp_prefs'.devMode === false
  → force dev_mode = false (even if owner)
  If localStorage 'dcp_prefs'.devMode === true
  AND user is NOT an owner
  → dev_mode still false (can't self-promote)
```

### Edge cases

| Scenario | git user.name | project.yml owners | devMode pref | Result |
|----------|--------------|-------------------|-------------|--------|
| Owner, no override | "Cyberpunk 042" | ["Cyberpunk 042"] | undefined | dev_mode=true |
| Owner, mode disabled | "Cyberpunk 042" | ["Cyberpunk 042"] | false | dev_mode=false |
| Non-owner | "Random Fork" | ["Cyberpunk 042"] | undefined | dev_mode=false |
| Non-owner, self-promote | "Random Fork" | ["Cyberpunk 042"] | true | dev_mode=false |
| No owners list | "Cyberpunk 042" | [] or absent | undefined | dev_mode=false |
| Fresh fork, no owners | "New Person" | [] or absent | undefined | dev_mode=false |
| Fresh fork, filled | "New Person" | ["New Person"] | undefined | dev_mode=true |
| Case mismatch | "cyberpunk 042" | ["Cyberpunk 042"] | undefined | dev_mode=true (case-insensitive) |
| Multiple owners | "Teammate" | ["Cyberpunk 042", "Teammate"] | undefined | dev_mode=true |

**Case sensitivity:** Match is case-insensitive. `git config user.name`
values vary by OS and Git config. We normalize with `.lower().strip()`.

---

## Architecture

### Backend

#### New file: `src/core/services/identity.py`

Pure service — no Flask dependency. Can be used by CLI/TUI too.

```python
"""
Identity resolution.

Reads project.yml owners and matches against the local git identity.
No external dependencies. No network calls.
"""

def get_git_user_name(project_root: Path) -> str | None:
    """Read git config user.name for this repo."""
    # subprocess: git -C {project_root} config user.name
    # Returns stripped string or None if not configured

def get_project_owners(project_root: Path) -> list[dict]:
    """Read owners from project.yml."""
    # Parse YAML, return owners list
    # Returns [] if no owners field or empty

def is_owner(project_root: Path) -> bool:
    """Check if the current git user is a project owner."""
    # get_git_user_name() → match against get_project_owners()
    # Case-insensitive comparison

def get_dev_mode_status(project_root: Path) -> dict:
    """Return full dev mode status for the frontend.
    
    Returns:
        {
            "dev_mode": bool,        # final resolved state
            "is_owner": bool,        # identity match result
            "git_user": str | None,  # current git user.name
            "owners": list[str],     # configured owners
        }
    """
```

**Size estimate:** ~60-70 lines
**Dependencies:** None (subprocess for git, yaml for project.yml)
**Layer:** Core service (L2)

#### New endpoint in routes: `GET /api/dev/status`

Could live in an existing route file (routes_api.py or routes_config.py)
or a new `routes_dev.py`. Since this is the first dev endpoint and
D1/D2/D3 will add more, a dedicated route file is cleaner.

```python
# src/ui/web/routes_dev.py

from flask import Blueprint, jsonify, current_app
from src.core.services.identity import get_dev_mode_status

dev_bp = Blueprint("dev", __name__)

@dev_bp.route("/api/dev/status")
def dev_status():
    """Return dev mode status.
    
    Response:
        {
            "dev_mode": true/false,
            "is_owner": true/false,
            "git_user": "Cyberpunk 042",
            "owners": ["Cyberpunk 042"]
        }
    """
    root = current_app.config["PROJECT_ROOT"]
    return jsonify(get_dev_mode_status(root))
```

**Size estimate:** ~25 lines for this phase (will grow with D1-D3)
**Dependencies:** identity.py
**Registration:** Add to `server.py` blueprint registration

#### project.yml schema update

Current project.yml has no `owners:` field. Adding it:

```yaml
# project.yml (add after 'repository:' line)
owners:
  - name: "Cyberpunk 042"
    github: "cyberpunk042"   # optional, for future CODEOWNERS auto-gen
```

The `github:` field is optional — not all owners have GitHub accounts,
and not all projects are on GitHub. The identity check uses ONLY `name:`.

We also need to update whatever reads project.yml to not break on
the new field. Let me verify what reads it:

```
project.yml consumers:
  - Setup Wizard (reads + writes)
  - l0_detection.py (reads modules/environments)
  - routes_devops_detect.py (wizard detection)
```

None of these will break on an extra field — they all do `yaml.get("key")`
style access. The new field is purely additive.

### Frontend

#### Settings panel addition

In `_settings.html`, add a "Dev Mode" toggle. This appears ONLY after
the identity check confirms the user is an owner:

```javascript
// In _renderSettingsPanel(), after the SSH Passphrase group:

if (window._devModeStatus && window._devModeStatus.is_owner) {
    const devMode = prefsGet('devMode');
    // Default to true if user is owner and hasn't explicitly disabled
    const isOn = devMode !== false;
    
    html += `<div class="settings-group">
        <div class="settings-label">🔧 Dev Mode</div>
        <div class="settings-hint">Stage debugger & QA testing tools</div>
        <div class="settings-btn-group">
            <button class="settings-btn ${isOn ? 'active' : ''}"
                onclick="_prefSetDevMode(true)">🔧 On</button>
            <button class="settings-btn ${!isOn ? 'active' : ''}"
                onclick="_prefSetDevMode(false)">Off</button>
        </div>
    </div>`;
}
```

And the setter:
```javascript
function _prefSetDevMode(enabled) {
    prefsSet('devMode', enabled);
    // Toggle the dev mode badge
    const badge = document.getElementById('dev-mode-badge');
    if (badge) badge.style.display = enabled ? '' : 'none';
    _renderSettingsPanel();
}
```

#### Dev mode badge

A subtle indicator when dev mode is active. Small pill in the topbar:

```html
<span id="dev-mode-badge" class="dev-badge" style="display:none">
    🔧 DEV
</span>
```

CSS:
```css
.dev-badge {
    font-size: 0.62rem;
    font-weight: 700;
    padding: 0.1rem 0.4rem;
    background: hsla(280, 80%, 55%, 0.15);
    color: hsl(280, 80%, 65%);
    border: 1px solid hsla(280, 80%, 55%, 0.25);
    border-radius: var(--radius-sm);
    letter-spacing: 0.04em;
    white-space: nowrap;
}
```

#### Boot sequence

On page load (in `_globals.html` or a new `_dev_mode.html` include):

```javascript
// ── Dev Mode Boot ──────────────────────────────────────────────
(async function _bootDevMode() {
    try {
        const res = await fetch('/api/dev/status');
        if (!res.ok) return;
        const status = await res.json();
        window._devModeStatus = status;
        
        if (!status.is_owner) return;
        
        // Owner detected. Check settings override.
        const devModePref = prefsGet('devMode');
        const devActive = devModePref !== false; // default ON for owners
        
        if (devActive) {
            // Show dev badge
            const badge = document.getElementById('dev-mode-badge');
            if (badge) badge.style.display = '';
            
            // Mark body for CSS selectors
            document.body.setAttribute('data-dev-mode', 'true');
            
            // Future: inject stage debugger (D1+)
        }
    } catch (e) {
        // Dev mode boot failure is never critical
        console.debug('[dev-mode] boot failed:', e);
    }
})();
```

---

## project.yml Schema

### Current shape (relevant fields)

```yaml
version: 1
name: str
description: str
repository: str
domains: list[str]
environments: list[{name, description, default}]
modules: list[{name, path, stack, domain, description}]
content_folders: list[str]
external: {ci: str}
pages: {segments: list[...]}
```

### Proposed addition

```yaml
owners:
  - name: str            # REQUIRED — matches git config user.name
    github: str          # OPTIONAL — GitHub @username
    email: str           # OPTIONAL — contact email
    role: str            # OPTIONAL — "maintainer" | "contributor"
```

**Minimum viable:**
```yaml
owners:
  - name: "Cyberpunk 042"
```

**Full example:**
```yaml
owners:
  - name: "Cyberpunk 042"
    github: "cyberpunk042"
    email: "jfm.devops.expert@gmail.com"
    role: "maintainer"
  - name: "Teammate Name"
    github: "teammate"
    role: "contributor"
```

**Why the extra fields?**
- `github:` — future CODEOWNERS auto-generation
- `email:` — future notification features
- `role:` — future permission differentiation (maintainer can delete,
  contributor can only edit)

For D0, ONLY `name` is used. The rest are future-proofing.

---

## Touch Point Inventory

### Files to create

| File | Purpose | Est. lines |
|------|---------|-----------|
| `src/core/services/identity.py` | Identity resolution (git user → owners match) | ~70 |
| `src/ui/web/routes_dev.py` | Dev mode API endpoint | ~25 |

### Files to modify

| File | Change | Est. lines changed |
|------|--------|-------------------|
| `project.yml` | Add `owners:` field | +4 |
| `src/ui/web/server.py` | Register `dev_bp` blueprint | +3 |
| `src/ui/web/templates/scripts/_settings.html` | Dev Mode toggle (owner-only) | +25 |
| `src/ui/web/templates/dashboard.html` | Dev mode badge in topbar | +3 |
| `src/ui/web/static/css/admin.css` | `.dev-badge` style | +12 |
| `src/ui/web/templates/scripts/_globals.html` or new `_dev_mode.html` | Boot sequence | +30 |

### Files to potentially create (later, inform but don't implement)

| File | Purpose | Phase |
|------|---------|-------|
| `.github/CODEOWNERS` | Standard GitHub CODEOWNERS | D0 or later |

---

## Implementation Order

```
D0.1  Create src/core/services/identity.py
      └─ Pure logic, no dependencies
      └─ Test: get_git_user_name, get_project_owners, is_owner, get_dev_mode_status

D0.2  Add owners: to project.yml
      └─ Depends on: nothing
      └─ Validate: existing YAML readers don't break

D0.3  Create src/ui/web/routes_dev.py
      └─ Depends on: D0.1 (identity.py)
      └─ Register blueprint in server.py
      └─ Test: GET /api/dev/status returns correct shape

D0.4  Frontend: dev mode boot + badge
      └─ Depends on: D0.3 (endpoint exists)
      └─ Add badge to topbar
      └─ Add boot script
      └─ Test: badge visible when owner, hidden when not

D0.5  Settings panel: dev mode toggle
      └─ Depends on: D0.4 (boot script sets window._devModeStatus)
      └─ Toggle appears only for owners
      └─ Toggle persists to localStorage
      └─ Test: toggle on/off, badge follows
```

**Parallelizable:** D0.1 + D0.2 can be done simultaneously.
**Critical path:** D0.1 → D0.3 → D0.4 → D0.5

---

## Security Considerations

### What this does NOT protect against

This is **convenience gating**, not security. A determined attacker who
has access to the running server can:
- Edit project.yml to add themselves as owner
- Hit `/api/dev/status` and see the response (no auth)
- Modify localStorage to set devMode=true

This is acceptable because:
1. The server already has no authentication (it's a local dev tool)
2. Dev mode exposes testing capabilities, not secrets
3. If someone has filesystem access, they already have everything

### What this DOES protect against

- **Accidental exposure:** A team member who clones the repo doesn't
  see dev tools they don't need
- **Demo mode:** Owner can disable dev mode for clean presentations
- **Fork clarity:** Forker sees a clean UI until they explicitly add
  themselves as owner

---

## Wizard Integration (future, NOT in D0 scope)

The Setup Wizard could add a step: "Who are you?"
- Pre-fill with `git config user.name`
- Save to project.yml `owners:`
- This would make the dev mode available immediately after setup

This is NOT part of D0. D0 requires manual editing of project.yml or
using the admin panel (which we'd also build later). For now, the user
must edit project.yml directly to add themselves.

---

## Testing Strategy

### Manual tests

1. Start server → `GET /api/dev/status`
   - With matching owner → `dev_mode: true`
   - Without matching owner → `dev_mode: false`
   - With no owners in project.yml → `dev_mode: false`

2. UI badge
   - Owner: badge visible by default
   - Non-owner: badge never visible
   - Owner + devMode=false in prefs: badge hidden

3. Settings panel
   - Owner: toggle visible
   - Non-owner: toggle not rendered
   - Toggle off: badge hides
   - Toggle on: badge shows

### Integration tests (import chain)

```python
from src.core.services.identity import (
    get_git_user_name,
    get_project_owners,
    is_owner,
    get_dev_mode_status,
)
# All import, all callable
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| project.yml YAML parsing breaks | Low | High | Additive field, no schema change |
| git config user.name not set | Low | Low | Return None, dev_mode=false |
| Slow git subprocess on boot | Low | Low | Single subprocess call, <50ms |
| Cache staleness (user changes project.yml) | Low | Low | Read fresh on each `/api/dev/status` call |
| Team member accidentally sees debug tools | Low | Low | Requires explicit owners entry |

---

## Data Flow Diagram

```
                    ┌─────────────────────┐
                    │    project.yml       │
                    │  owners:             │
                    │    - name: "Cyb…042" │
                    └─────────┬───────────┘
                              │ read at request time
                              ▼
                    ┌─────────────────────┐
                    │   identity.py       │
git config ──────── │  is_owner()         │
user.name           │  get_dev_mode_…()   │
                    └─────────┬───────────┘
                              │ returns status dict
                              ▼
                    ┌─────────────────────┐
                    │   routes_dev.py     │
                    │  GET /api/dev/status│
                    └─────────┬───────────┘
                              │ JSON response
                              ▼
                    ┌─────────────────────┐
                    │   _dev_mode.html    │  ← or _globals.html
                    │  boot script        │
                    │  window._devMode…   │
                    └────────┬──┬─────────┘
                             │  │
                    ┌────────┘  └────────┐
                    ▼                    ▼
          ┌─────────────┐     ┌──────────────┐
          │ 🔧 DEV badge│     │ Settings     │
          │ (topbar)    │     │ toggle       │
          └─────────────┘     └──────────────┘
                                      │
                                      ▼
                              ┌──────────────┐
                              │ localStorage │
                              │ dcp_prefs    │
                              │ .devMode     │
                              └──────────────┘
```

---

## Estimated Effort

| Step | New lines | Changed lines | Files |
|------|-----------|--------------|-------|
| D0.1 identity.py | 70 | 0 | 1 new |
| D0.2 project.yml | 4 | 0 | 1 modified |
| D0.3 routes_dev.py | 25 | 3 | 1 new + 1 modified |
| D0.4 UI boot + badge | 35 | 5 | 2 modified |
| D0.5 Settings toggle | 25 | 0 | 1 modified |
| **Total** | **~160** | **~8** | **2 new + 5 modified** |

---

## Traceability

| Requirement | Source | Implementation |
|------------|--------|---------------|
| Owner identity from CODEOWNERS concept | User request ("codeowner logic") | project.yml owners + git user.name match |
| Fork-friendly | User request ("if someone wants to fork") | Owners list in tracked project.yml |
| Disable in Settings | User request ("could just disable it in the Settings panel") | localStorage devMode pref + Settings toggle |
| No hardcoding | User request ("they dont have to hardcode anything") | Identity from data file, not code |
| Dev visibility gate | User request ("when we detect my name") | is_owner() → dev_mode → UI injection |

---

## What D0 Enables

With D0 complete:
- `window._devModeStatus.dev_mode` is available in the browser
- `document.body[data-dev-mode="true"]` is set when active
- The Settings panel has the toggle
- The badge is visible

D1 (Scenario Library) will use `window._devModeStatus.dev_mode` to
decide whether to inject the stage debugger drawer.

D2 (State Override Engine) will use `data-dev-mode="true"` to gate
CSS for override indicators.

D3 (Assistant Inspector) will read `window._devModeStatus.dev_mode`
before adding the inspector button.

---

## Phase D0 does NOT include

- Stage debugger drawer (D1)
- Scenario presets (D1)
- System profile overrides (D2)
- Tool state overrides (D2)
- Assistant inspector (D3)
- CODEOWNERS file generation (future)
- Wizard "Who are you?" step (future)
- Multi-factor identity (GitHub API, SSH key fingerprint — out of scope)
