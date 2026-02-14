# GitHub Integration — Detailed Implementation Spec

**Status**: IMPLEMENTED — NEEDS TESTING  
**Integration #2 of 8** — depends on Git. Enables CI/CD triggers.

---

## 0. KEY ARCHITECTURAL INSIGHT FROM USER

> Environments are defined in "👋 Project Configuration" (wizard Step 1).  
> They flow into "🔐 Secrets & Encryption" (wizard Step 3) where the user  
> is already offered to configure gh CLI and align remote environments  
> with local ones.

**The GitHub setup wizard must NOT re-define environments.** It reads them  
from `project.yml` and focuses on **alignment** — making sure GitHub's  
deployment environments match what the user already defined locally,  
and that secrets are properly synced between vault and GitHub.

---

## 1. WHAT EXISTS TODAY — INVENTORY

### Backend (what's SMART and already works)

| API / Function | What it does | Location |
|---|---|---|
| `GET /integrations/gh/status` | gh CLI version, auth, repo slug | `routes_integrations.py` → `git_ops.gh_status()` |
| `GET /gh/status` | Simpler: installed + authenticated | `routes_secrets.py` → `secrets_ops.gh_status()` |
| `GET /gh/auto` | Token + repo from git remote | `routes_secrets.py` → `secrets_ops.gh_auto_detect()` |
| `GET /gh/environments` | List remote GitHub environments | `routes_secrets.py` → `secrets_ops.list_environments()` |
| `POST /gh/environment/create` | Create a deployment environment | `routes_secrets.py` → `secrets_ops.create_environment()` |
| `POST /env/cleanup` | Delete env (local + optional GitHub) | `routes_secrets.py` → `secrets_ops.cleanup_environment()` |
| `POST /env/seed` | Seed .env files for multi-env | `routes_secrets.py` → `secrets_ops.seed_environments()` |
| `GET /gh/secrets` | List secrets + variables on GitHub | `routes_secrets.py` → `secrets_ops.list_gh_secrets()` |
| `POST /secret/set` | Set a secret to .env and/or GitHub | `routes_secrets.py` → `secrets_ops.set_secret()` |
| `POST /secret/remove` | Remove a secret from .env and/or GH | `routes_secrets.py` → `secrets_ops.remove_secret()` |
| `POST /secrets/push` | Bulk push secrets to GitHub | `routes_secrets.py` → `secrets_ops.push_secrets()` |
| `GET /gh/pulls` | List open PRs | `routes_integrations.py` → `git_ops.gh_pulls()` |
| `GET /gh/actions/runs` | Recent workflow runs | `routes_integrations.py` → `git_ops.gh_actions_runs()` |
| `GET /gh/actions/workflows` | List workflows | `routes_integrations.py` → `git_ops.gh_actions_workflows()` |
| `POST /gh/actions/dispatch` | Trigger a workflow | `routes_integrations.py` → `git_ops.gh_actions_dispatch()` |
| `GET /project/status` | `_probe_github()` → cli, auth, repo, .github dir | `routes_project.py` |
| `GET /wizard/detect` | Tool detection (gh) + integration status | `routes_devops.py` |

### Backend (what's MISSING)

| What | Why |
|---|---|
| **Repo visibility** (public/private) | Nice to show in wizard |
| **Branch protection status** | Could detect if main is protected |
| **CODEOWNERS detection** | Check if .github/CODEOWNERS exists |
| **Webhook listing** | Nice for advanced view |

→ **Verdict**: Most of what's missing is _nice-to-have_, not blocking.  
The `_probe_github()` could be enriched with a few extra checks.

### Frontend — GitHub Card (`_integrations_github.html`, 289 lines)

**What's GOOD**:
- Three states handled: not installed, not authenticated, connected
- Live panel with 4 tabs: PRs, Action Runs, Environments, Secrets
- Create environment modal works
- Push secrets action works
- `cardDepHint` for Git dependency

**What's DUMB / MISSING**:
- No setup wizard — `openSetupWizard('github')` just opens `cli.github.com` in browser
- No "reconfigure" / "setup" button on the card
- No environment alignment (local envs vs GitHub envs)
- No per-environment secret push (push is bulk all-or-nothing)
- No CODEOWNERS generation

### Frontend — Wizard Step 3 (Secrets) already handles:
- GitHub auto-detect (`/gh/auto`)
- GITHUB_REPOSITORY detection + "Save to .env" button
- Environment vault status per environment
- GitHub deployment environment alignment (lists which ones exist/missing on GH)
- "Create" button for missing GitHub environments

### Frontend — Wizard Step 5 sub-wizard (`_wizard_integrations.html`):
- Shows "✓ authenticated" or install/auth instructions
- No actual setup wizard

### Frontend — Setup modal dispatcher (`_integrations_setup_modals.html`):
- `github: () => { window.open(...); toast(...); }` ← THIS IS THE PROBLEM

---

## 2. INTELLIGENCE SOURCES FOR THE WIZARD

What the GitHub wizard should READ from other systems:

| Source | What we read | How |
|---|---|---|
| **Git** (integration #1) | Remote URL → repo slug | `GET /integrations/gh/status` → `repo` field |
| **Git** (integration #1) | Branch name | `GET /project/status` → `integrations.git.branch` |
| **Project config** | Environments defined | `GET /config` → `environments[]` |
| **Vault/Secrets** | Local secrets in .env | `GET /vault/keys` |
| **GitHub remote** | Remote environments | `GET /gh/environments` |
| **GitHub remote** | Remote secrets/vars | `GET /gh/secrets` |
| **gh CLI** | Auth status, version | `GET /integrations/gh/status` |

---

## 3. WIZARD FLOW — STEP BY STEP

### Step 1: DETECT

**API calls** (parallel):
1. `GET /integrations/gh/status` → gh CLI availability, version, auth, repo
2. `GET /project/status` → git + github probes
3. `GET /config` → project environments, name, description
4. `GET /gh/environments` → remote deployment environments
5. `GET /gh/secrets` → remote secrets + variables count

**What the user sees**:
```
🐙 GitHub Status

├─ gh CLI:         ✅ Installed (v2.45.0)
├─ Authentication: ✅ Logged in
├─ Repository:     ✅ cyberpunk042/devops-control-plane
├─ Visibility:     🔓 (public/private — if we add this)
├─ .github/ dir:   ✅ Exists
├─ Environments:   ⚠️ 1 of 3 aligned (1 local env not on GitHub)
└─ Secrets:        📊 4 secrets, 2 variables on GitHub

💡 Your project defines 3 environments: dev, staging, production
   Only 'production' exists on GitHub. We can create the missing ones.
```

**Not installed state**:
```
├─ gh CLI:         ❌ Not installed

💡 Install the GitHub CLI:
   sudo apt install gh   (Debian/Ubuntu)
   brew install gh       (macOS)
   
   Then authenticate: gh auth login
```

### Step 2: CONFIGURE — Environment Alignment & Secrets Sync

This is the KEY step. Three sections:

#### Section A: Repository Link
- Show detected repo from git remote
- If no repo detected:
  - "No GitHub repository linked. Your git remote doesn't point to GitHub."
  - Optional: field to enter repo manually (but don't create — just link)
- If repo detected:
  - Show link: "🔗 cyberpunk042/devops-control-plane" (clickable → opens GH)
  - Read-only, since this comes from git remote

#### Section B: Environment Alignment (THE CORE)
- Read local environments from `GET /config`
- Read remote environments from `GET /gh/environments`
- Show alignment matrix:

```
🌍 Environment Alignment

Local              GitHub              Action
─────              ──────              ──────
✅ dev             ✅ dev              aligned
✅ staging         ❌ —                [Create on GitHub]
✅ production      ✅ production       aligned
—                  ⚠️ test             (exists on GH but not locally)
```

- Checkboxes to select which missing environments to create
- Pre-checked: all local envs not on GitHub
- Note: "Environments defined in Project Configuration → Secrets step"

#### Section C: Secrets Sync Overview
- Read local secrets from `/vault/keys`
- Read remote secrets from `/gh/secrets`
- Show sync status:

```
🔑 Secrets Sync Status

                    Local (.env)    GitHub
──────              ────────       ──────
DATABASE_URL        ✅ set          ❌ missing
SECRET_KEY          ✅ set          ✅ synced
API_TOKEN           ✅ set          ❌ missing
GITHUB_REPOSITORY   ✅ set          — (excluded)

☐ Push missing secrets to GitHub now
```

- Checkbox: "Push missing secrets to GitHub" (default: unchecked — user decides)
- Note: "Use the 🔐 Secrets tab for granular secret management"

#### Section D: CODEOWNERS (optional, if .github/ exists)
- Check if `.github/CODEOWNERS` exists
- If not: offer to generate from project structure
- If yes: show as "✅ Already configured"
- This is low priority — can be deferred

### Step 3: REVIEW & APPLY

Show action summary:
```
📋 Actions to perform:

  ✅ Repository: cyberpunk042/devops-control-plane (linked)
  🆕 Create environment: staging
  ⊘ Secrets push: skipped (not selected)
  ⊘ CODEOWNERS: skipped
```

**Apply button** creates environments via `POST /gh/environment/create`  
and optionally pushes secrets via `POST /secrets/push`.

---

## 4. SCOPE — WHAT WE TOUCH

| Component | File | Action |
|---|---|---|
| **Setup Wizard** | `_integrations_setup_modals.html` | REPLACE `github: () => window.open(...)` with `openGitHubSetupWizard()` |
| **GitHub Card** | `_integrations_github.html` | ADD ⚙️ Setup button (like we did for Git) |
| **Backend probe** | `routes_project.py` → `_probe_github()` | OPTIONAL: add visibility, CODEOWNERS detection |
| **Backend setup** | `routes_devops.py` → `wizard_setup()` | ADD `setup_github` action (create envs, push secrets) |

### What we DON'T need to build:
- ❌ New API endpoints for listing secrets — already exists
- ❌ New API for creating environments — already exists  
- ❌ New API for pushing secrets — already exists
- ❌ Environment definition UI — wizard Step 1 handles this
- ❌ gh CLI installation — user does this in terminal
- ❌ gh auth login — user does this in terminal

### Backend work needed:

#### 4a. OPTIONAL: Enhance `_probe_github()` in `routes_project.py`

Add these fields (nice-to-have, not blocking):
```python
# Check for .github/CODEOWNERS
"has_codeowners": (root / ".github" / "CODEOWNERS").exists(),

# Check for workflows
"workflow_count": len(list((root / ".github" / "workflows").glob("*.yml")))
                  if (root / ".github" / "workflows").is_dir() else 0,
```

#### 4b. Add `setup_github` action in `routes_devops.py`

The wizard calls `POST /wizard/setup` with `action: "setup_github"`.

Payload:
```json
{
    "action": "setup_github",
    "create_environments": ["staging", "test"],
    "push_secrets": true,
    "codeowners_content": "* @cyberpunk042"
}
```

Actions:
1. Create each environment via `secrets_ops.create_environment()`
2. Push secrets via `secrets_ops.push_secrets()` if `push_secrets: true`
3. Write CODEOWNERS if content provided

Return:
```json
{
    "ok": true,
    "results": {
        "environments_created": ["staging"],
        "environments_failed": [],
        "secrets_pushed": 4,
        "codeowners_written": false
    }
}
```

---

## 5. IMPLEMENTATION ORDER

1. Backend: enhance `_probe_github()` with `has_codeowners` + `workflow_count` (5 min)
2. Backend: add `setup_github` action to `wizard_setup()` (15 min)
3. Frontend: write `openGitHubSetupWizard()` — 3 intelligent steps (main work)
4. Frontend: add ⚙️ Setup button to GitHub card
5. Frontend: update dispatcher to call new wizard
6. Test: verify the full flow

---

## 6. QUALITY CHECKLIST

- [ ] Detection step is fast (all API calls parallel)
- [ ] Environment alignment shows local vs remote comparison
- [ ] Missing envs are pre-checked for creation
- [ ] Extra remote envs (not local) shown as FYI, not as errors
- [ ] Secrets sync shows clear overview without exposing values
- [ ] Push secrets requires explicit opt-in (user decides)
- [ ] Not-installed state gives clear install instructions
- [ ] Not-authenticated state gives clear auth instructions
- [ ] Repository link comes from git remote (not editable)
- [ ] Card shows Setup button for re-entry
- [ ] CTA: "Next: Set up Docker →" after completion
- [ ] Wizard reads project.yml environments — does NOT create new ones
- [ ] Error handling: env creation failures don't block other actions

---

## 7. WHAT THE PLAN SAYS vs WHAT WE'RE DOING

Plan Section 5.2 specifies 15 features. Here's the mapping:

| # | Feature | Implementation | Status |
|---|---|---|---|
| 1 | gh CLI detection + version + auth | Detection step — from `/integrations/gh/status` | ✅ Will do |
| 2 | Repository detection from git remote | Detection step — `repo` field | ✅ Will do |
| 3 | Repository visibility (public/private) | Nice-to-have — could add to probe | ⏳ Deferred |
| 4 | Environment listing + creation | Core configure step — alignment matrix | ✅ Will do |
| 5 | Environment protection rules config | Complex GH API — not in v1 | ⏳ Deferred |
| 6 | Vault secret listing | Configure step — sync overview | ✅ Will do |
| 7 | Secret push to GitHub | Configure step — opt-in bulk push | ✅ Will do |
| 8 | Secret name mapping | Out of scope for wizard — use Secrets tab | ⏳ Deferred |
| 9 | CODEOWNERS generation | Optional section in configure step | ⏳ Deferred (v2) |
| 10 | Branch protection rules suggestion | Complex GH API — needs more research | ⏳ Deferred |
| 11 | Webhook status check | Complex — not needed for v1 | ⏳ Deferred |
| 12 | GitHub Apps detection | Complex — not needed for v1 | ⏳ Deferred |
| 13 | Verification after apply | Review step shows results | ✅ Will do |
| 14 | Next-integration CTA | "Next: Set up Docker →" | ✅ Will do |
| 15 | Re-entry with current state | Wizard reads current state on open | ✅ Will do |

**v1 delivers: 8 of 15 features.** The deferred ones are all "advanced GH API" features that don't affect the core flow. They can be added later layer by layer.

---

## 8. DIFFERENCES FROM GIT WIZARD

| Aspect | Git Wizard | GitHub Wizard |
|---|---|---|
| **Main intelligence** | Stack-aware .gitignore generation | Environment alignment + secret sync |
| **File generation** | .gitignore, hooks | CODEOWNERS (optional) |
| **Backend action** | `setup_git` — git init, remote, write files | `setup_github` — create envs, push secrets |
| **Dependencies** | None (foundation) | Needs Git configured (remote → repo slug) |
| **Complexity** | Medium | Lower (most APIs already exist) |

---

## 9. OPEN QUESTIONS

None. The analysis is clear:
- The backend has everything we need (create env, push secrets, list everything)
- The wizard just needs to orchestrate the existing APIs intelligently
- The key insight is **environment alignment** — showing local vs remote side-by-side
