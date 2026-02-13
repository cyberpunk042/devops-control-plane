# Git Integration — Detailed Implementation Spec

**Status**: IMPLEMENTED — ALL TODOS COMPLETE  
**Integration #1 of 8** — sets the pattern for all others.

---

## 1. SCOPE

Three components to implement/rewrite:

| Component | File | Lines | Action |
|---|---|---|---|
| **Setup Wizard** | `_integrations_setup_modals.html` | 35-127 | REWRITE `openGitSetupWizard()` |
| **Git Card** | `_integrations_git.html` | 210-221 | FIX `gitIgnoreWizard()` (placeholder → real) |
| **Backend enhance** | `routes_project.py` | 73-107 | ENHANCE `_probe_git()` with git version + hooks |
| **Backend enhance** | `routes_devops.py` | 310-332 | ENHANCE `setup_git` action with .gitignore write + hooks |

## 2. WHAT THE BACKEND ALREADY PROVIDES

### Already exists — USE THESE:
- `GET /git/status` → branch, dirty, ahead/behind, remote, last_commit  
- `GET /project/status` → `integrations.git` = initialized, has_remote, remote, branch, has_gitignore
- `GET /security/gitignore` → .gitignore coverage analysis (exists, missing patterns, coverage %)
- `POST /security/generate/gitignore` → generates .gitignore content **without writing** (returns file content)
- `GET /wizard/detect` → tool availability (git, gh), project files
- `GET /integrations/gh/status` → GitHub CLI version, auth status, repo slug

### Backend changes needed:

#### 2a. Enhance `_probe_git()` in `routes_project.py`
Add:
- `git_version` — output of `git --version` (show in wizard detection)
- `has_hooks` — check if `.git/hooks/pre-commit` exists (not samples)
- `hook_count` — count of non-sample hooks

#### 2b. Enhance `setup_git` action in `routes_devops.py`
Add support for:
- `gitignore_content` — if provided, write it as `.gitignore`
- `create_initial_commit` — if true, run `git add . && git commit -m "Initial commit"`
- `default_branch` — rename branch if different from current

#### 2c. New endpoint: preview .gitignore (OPTIONAL — may not need)
Actually, `POST /security/generate/gitignore` already returns `{ok, file: {content}}` without writing.
The wizard can call it to get the preview, then send the content back to `setup_git` to write.
→ **No new endpoint needed.** Smart.

## 3. WIZARD FLOW — STEP BY STEP

### Step 1: DETECT — "What we found"

**API calls** (parallel):
1. `GET /project/status` → git probe (initialized, remote, branch, gitignore, version)
2. `GET /wizard/detect` → tool availability (git, gh, ruff, mypy, eslint)
3. `GET /security/gitignore` → gitignore coverage analysis
4. `GET /integrations/gh/status` → GitHub CLI auth + repo (for remote pre-fill)

**What the user sees**:
```
🔀 Git Repository Status

├─ Git CLI:        ✅ Installed (v2.43.0)
├─ Repository:     ✅ Initialized (branch: main)
├─ Remote:         ⚠️ No remote configured
├─ .gitignore:     ❌ Not found
├─ Hooks:          ❌ No hooks configured
└─ gh CLI:         ✅ Authenticated as 'cyberpunk042'

📦 Detected stacks: python-flask, node
💡 We'll generate a stack-aware .gitignore for your project.
```

**Data stored**: `data._gitProbe`, `data._tools`, `data._gitignoreAnalysis`, `data._ghStatus`

### Step 2: CONFIGURE — smart defaults with preview

**Three sections**, each with its own intelligence:

#### Section A: Remote URL
- Pre-filled from: `gitProbe.remote` (if exists) → `ghStatus.repo` (if gh authenticated) → empty
- If gh is authenticated AND detects a repo → show: "🐙 Detected: github.com/user/repo"
- Input field for URL with the pre-filled value
- User can change or clear it

#### Section B: .gitignore — THE CORE INTELLIGENCE
- If .gitignore exists:
  - Show coverage: "Your .gitignore covers 75% of recommended patterns"
  - Show missing patterns grouped by category:
    - ❌ Security: .env, *.pem (missing)
    - ❌ Python: __pycache__/, .venv/ (missing)  
    - ✅ Node: node_modules/ (present)
  - Toggle: "☑ Update .gitignore with missing patterns"
- If .gitignore does NOT exist:
  - Call `POST /security/generate/gitignore` to get generated content
  - Show full preview with sections:
    ```
    📋 Generated .gitignore (42 patterns)
    
    ┌──────────────────────────────────────────────┐
    │ # ── Security ──────────────────────────────  │
    │ .env                                          │
    │ .env.*                                        │
    │ *.pem                                         │
    │ *.key                                         │
    │                                               │
    │ # ── Python ────────────────────────────────  │
    │ __pycache__/                                  │
    │ *.py[cod]                                     │
    │ .venv/                                        │
    │ ...                                           │
    │                                               │
    │ # ── Node ──────────────────────────────────  │
    │ node_modules/                                 │
    │ dist/                                         │
    │ ...                                           │
    └──────────────────────────────────────────────┘
    
    [Edit content]   (shows editable textarea)
    ```
  - User can edit the content before it's written
  - Toggle: "☑ Create .gitignore" (checked by default)

#### Section C: Default Branch
- Show current branch if exists
- If no repo initialized → "main" as default
- Dropdown/input: main, master, develop, or custom

#### Section D: Pre-commit Hooks (if linting tools detected)
- Only show this section if ruff, mypy, eslint, or other lint tools are available
- "🔧 Lint tools detected: ruff, mypy"
- Checkbox: "☐ Set up pre-commit hook (runs linters on commit)"
- Expandable preview of what the hook will do

#### Section E: Initial Commit
- If repo is not initialized, or has no commits:
  - Checkbox: "☑ Create initial commit after setup"
  - Default commit message: "Initial commit" (editable)

### Step 3: APPLY & VERIFY — execute + show results

**Execute in order**:
1. `git init` (if not initialized)
2. Rename branch (if different from current)
3. Write `.gitignore` (if user selected)
4. Set remote (if user provided URL)
5. Set up pre-commit hook (if user selected)
6. Create initial commit (if user selected)

**Show results**:
```
✅ Git Setup Complete

✓ Repository initialized
✓ .gitignore created (42 patterns for Python + Node)
✓ Remote set: origin → github.com/user/my-app
✓ Initial commit created: abc1234
⊘ Pre-commit hooks: skipped (not selected)

💡 Next: Connect GitHub → 
   [Set up GitHub]  [Close]
```

**Post-actions**:
- Invalidate project status cache
- Invalidate git card cache
- Reload git card
- Store successMessage for wizard

## 4. WHAT THE CARD NEEDS

### Current state (functional):
- Status grid: branch, dirty state, ahead/behind
- Detection list: remote, HEAD
- Changes summary: staged/modified/untracked counts  
- Last commit display
- Actions: Commit, Pull, Push, Log
- Generate: .gitignore (placeholder)

### Changes needed:
1. **Fix `gitIgnoreWizard()`** — replace placeholder with real wizard that:
   - Calls `/security/gitignore` for current analysis
   - Calls `/security/generate/gitignore` for preview
   - Shows existing coverage + missing patterns
   - Lets user toggle patterns on/off
   - Writes the file via `POST /security/generate/gitignore`
   
2. **Add "Reconfigure" action** — opens `openGitSetupWizard()` from the card
   (The card already has `cardSetupBanner` for when git is missing — this is for when it's configured but user wants to change things)

3. **No other card changes needed** — the card is already well-structured.

## 5. IMPLEMENTATION ORDER

1. Backend: enhance `_probe_git()` → add `git_version`, `has_hooks`, `hook_count`
2. Backend: enhance `setup_git` action → support `gitignore_content`, `create_initial_commit`, `default_branch`  
3. Frontend: rewrite `openGitSetupWizard()` with 3 intelligent steps
4. Frontend: fix `gitIgnoreWizard()` in the card
5. Test: verify the full flow

## 6. QUALITY CHECKLIST

- [x] Detection step is fast (all API calls parallel)
- [x] .gitignore preview shows real generated content from backend
- [x] .gitignore is editable before write
- [x] Remote URL pre-filled from gh CLI when possible
- [x] User decides everything — nothing auto-applied
- [x] Review step shows exactly what will happen before applying
- [x] Apply step shows clear results for each action
- [x] Error handling: each action can fail independently
- [x] Next integration CTA: "Set up GitHub →" (if gh CLI detected) — DONE
- [x] Re-entry works: if Git is already configured, wizard opens with current state
- [x] Card gitIgnoreWizard() is functional (no more "coming soon")
- [x] Card shows "Reconfigure" option for configured state — DONE
