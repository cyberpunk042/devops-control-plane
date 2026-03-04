# Changelog & Version System — Implementation Plan

> **Status:** Draft — awaiting review
> **Created:** 2026-03-03
> **Scope:** Changelog, versioning, breaking change flag, commit integration

---

## What the user said (verbatim requirements)

1. "proper changelog system that works fine automatically with Conventional Commits"
2. "even if people want to use it manually or customize the entries it should be possible"
3. "a proper system and integration with the git stuff"
4. "engrained with the version system where when there are fix and feat and such it impact if its a patch, minor, major"
5. "BREAKING CHANGE if the user decide to flag a feat or change in general as breaking"
6. "which was not offered yet in the commit message panel but should be"
7. "automatic pre-commit changelog update"
8. "possible customisation or additions and whatnot"

---

## Current State

| What | Where | Status |
|------|-------|--------|
| CC type selector in commit modal | `_git.html` line 117–126 | ✅ Has type + scope + description |
| Breaking change flag | commit modal | ❌ Missing entirely |
| Version resolution | `artifacts/version.py` | ✅ `resolve_version()`, `bump_version()`, `get_last_tag()` |
| Changelog generation | `docs_svc/generate.py` | ⚠️ Flat date-grouped dump, not Keep-a-Changelog format, not incremental |
| Release notes | `artifacts/release_notes.py` | ✅ Groups by CC prefix between tags — but only for GH Releases |
| Commit grouping constants | Two places | ⚠️ Duplicated: `_commit_icon()` in generate.py, `_COMMIT_GROUPS` in release_notes.py |
| CHANGELOG.md file | Root | ❌ Does not exist |
| Git tags | CLI | One tag: `content-vault`. No semver tags. |
| pyproject.toml version | Root | `0.1.0` |

---

## System Design

### The flow

```
┌──────────────────────────────────────────────────────────┐
│                    Commit Modal                          │
│                                                          │
│  [Type ▾]  [Scope ___]  [☐ Breaking Change]             │
│  [Description ________________________________]          │
│  [Body (optional, multiline) _________________]          │
│                                                          │
│  Preview: feat(k8s)!: add multi-cluster support          │
│                                                          │
│  ┌────────────────────────────────────────────┐          │
│  │ Changelog Entry Preview                    │          │
│  │ ✨ add multi-cluster support ⚠️ BREAKING   │          │
│  │ [Edit ✏️]                                  │          │
│  └────────────────────────────────────────────┘          │
│                                                          │
│  [Cancel]                              [Commit]          │
└──────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────┐
│              Pre-commit: Changelog Update                │
│                                                          │
│  1. Parse commit message (type, scope, breaking, desc)   │
│  2. Format changelog entry                               │
│  3. Insert into [Unreleased] section of CHANGELOG.md     │
│  4. Stage CHANGELOG.md alongside user's files            │
│  5. git commit (message + staged files + CHANGELOG.md)   │
└──────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────┐
│            Version Bump (when user decides)              │
│                                                          │
│  Analyze [Unreleased] section:                           │
│    - Has BREAKING CHANGE → suggest major                 │
│    - Has feat → suggest minor                            │
│    - Only fix/docs/chore → suggest patch                 │
│                                                          │
│  User confirms or overrides suggested bump.              │
│                                                          │
│  1. Bump version in pyproject.toml                       │
│  2. Move [Unreleased] entries → [x.y.z] - YYYY-MM-DD    │
│  3. Add new empty [Unreleased] section                   │
│  4. Commit "chore(release): vX.Y.Z"                      │
│  5. Tag vX.Y.Z                                           │
│  6. (Optional) Push tag                                  │
└──────────────────────────────────────────────────────────┘
```

### CHANGELOG.md format (Keep a Changelog)

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### ✨ Features
- add multi-cluster support ⚠️ **BREAKING**
- add streaming subprocess output

### 🐛 Bug Fixes
- fix mobile overflow on master scores card

### 📝 Documentation
- update generators README

## [0.1.0] - 2026-03-03

### ✨ Features
- initial release
- conventional commits in commit modal
- ...
```

### How CC types map to sections + bump

| CC Type | Section | Bump Impact |
|---------|---------|-------------|
| `feat` | ✨ Features | **minor** |
| `fix` | 🐛 Bug Fixes | **patch** |
| `docs` | 📝 Documentation | patch |
| `style` | 🎨 Style | patch |
| `refactor` | ♻️ Refactoring | patch |
| `perf` | ⚡ Performance | patch |
| `test` | 🧪 Tests | patch |
| `build` | 📦 Build | patch |
| `ci` | ⚙️ CI/CD | patch |
| `chore` | 🔧 Chores | patch |
| Any + `!` or `BREAKING CHANGE:` | (same section) + ⚠️ flag | **major** |

Bump is determined by the **highest impact** commit since last tag:
- Any breaking → major
- Any feat (no breaking) → minor
- Only fix/docs/chore/etc → patch

---

## Implementation

### Phase 1: Core — `src/core/services/changelog/`

New module: the changelog system.

**File: `src/core/services/changelog/__init__.py`**
- Re-exports

**File: `src/core/services/changelog/parser.py`**
- `parse_cc_message(message: str) -> CCMessage` — parse a Conventional Commit message
  - Returns: `type`, `scope`, `description`, `body`, `breaking` (bool), `breaking_note` (str)
  - Handles: `feat(scope)!: desc`, `feat: desc\n\nBREAKING CHANGE: note`
- `cc_section(type: str) -> tuple[str, str]` — returns (emoji, section title) for a CC type
  - Single source of truth — replaces both `_commit_icon()` and `_COMMIT_GROUPS`
- `cc_bump_type(messages: list[CCMessage]) -> str` — returns "major", "minor", or "patch"

**File: `src/core/services/changelog/engine.py`**
- `load_changelog(project_root: Path) -> Changelog` — parse existing CHANGELOG.md
  - Returns structured object: header, unreleased entries, versioned sections
  - If file doesn't exist, returns empty Changelog with standard header
- `save_changelog(project_root: Path, changelog: Changelog) -> None` — write back
- `add_entry(changelog: Changelog, message: str) -> str` — add a CC message to [Unreleased]
  - Parses the CC message, creates formatted entry, inserts into correct section
  - Returns the formatted entry string (for UI preview)
- `remove_entry(changelog: Changelog, entry_text: str) -> bool` — remove an entry from [Unreleased]
- `edit_entry(changelog: Changelog, old_text: str, new_text: str) -> bool` — edit an entry
- `cut_release(changelog: Changelog, version: str, date: str) -> None` — move [Unreleased] → [version]
- `get_unreleased_entries(changelog: Changelog) -> list[ChangelogEntry]` — list unreleased items

**File: `src/core/services/changelog/models.py`**
- `CCMessage` — dataclass/pydantic: type, scope, description, body, breaking, breaking_note
- `ChangelogEntry` — dataclass: section, text, breaking, raw_line
- `ChangelogSection` — dataclass: version, date, entries
- `Changelog` — dataclass: header, unreleased, sections

### Phase 2: Commit Integration

**Modify: `_git.html` commit modal**

1. Add `☐ Breaking Change` checkbox after the scope input:
   ```html
   <label class="git-cc-breaking">
     <input type="checkbox" id="git-cc-breaking" onchange="_ccUpdateMsg()">
     <span>⚠️ Breaking Change</span>
   </label>
   ```

2. Update `_ccUpdateMsg()` to append `!` when checked:
   ```javascript
   let msg = type;
   if (scope) msg += `(${scope})`;
   if (breaking) msg += '!';
   msg += ': ' + desc;
   ```

3. Add optional body textarea (for `BREAKING CHANGE:` footer):
   ```html
   <textarea id="git-cc-body" placeholder="Optional body / breaking change details…"></textarea>
   ```

4. Add changelog entry preview below the commit form:
   - Shows how the entry will appear in CHANGELOG.md
   - Inline edit button to customize the entry text before commit

5. Update `doGitCommit()`:
   - Collect the full message (header + body)
   - Send `changelog_entry` override to the API if user customized it
   - Backend handles CHANGELOG.md update as part of the commit

**Modify: `POST /api/git/commit` route**

Add changelog integration:
```python
# After validating message, before git commit:
# 1. Parse the CC message
# 2. Add entry to CHANGELOG.md [Unreleased]
# 3. Stage CHANGELOG.md
# 4. Proceed with normal commit (now includes CHANGELOG.md)
```

New optional body fields:
- `changelog_entry`: custom entry text (overrides auto-generated)
- `skip_changelog`: bool — skip CHANGELOG.md update for this commit (e.g. for merge commits)
- `body`: commit body (for multi-line messages, BREAKING CHANGE footer)

### Phase 3: Version Bump Integration

This connects to `artifacts/version.py` which already has `bump_version()`.

**New API: `POST /api/changelog/release`**

1. Reads [Unreleased] from CHANGELOG.md
2. Determines suggested bump from CC types (using `cc_bump_type()`)
3. Returns: suggested version, entries, current version

**New API: `POST /api/changelog/cut-release`**

Body: `{ version: "0.2.0", date: "2026-03-03" }` (or auto)

1. Moves [Unreleased] → [0.2.0] in CHANGELOG.md
2. Bumps `pyproject.toml` version
3. Stages both files
4. Commits `chore(release): v0.2.0`
5. Tags `v0.2.0`
6. Returns result (user can push manually or auto)

**UI: Version bump can be triggered from multiple places:**
- Git card (after inspecting unreleased changes)
- Artifacts card (before a build/publish)
- GitHub card (before creating a GH Release)
- Or standalone via a "Release" action

### Phase 4: Manual Changelog Management

**New API: `GET /api/changelog`**
- Returns the parsed CHANGELOG.md structure (unreleased + all versions)

**New API: `PUT /api/changelog/entry`**
- Body: `{ old_text: "...", new_text: "..." }`
- Edit an existing entry in [Unreleased]

**New API: `POST /api/changelog/entry`**
- Body: `{ section: "Features", text: "custom manual entry", breaking: false }`
- Add a manual entry to [Unreleased] — not tied to any commit

**New API: `DELETE /api/changelog/entry`**
- Body: `{ text: "..." }`
- Remove an entry from [Unreleased]

**UI: Changelog panel** (in Git card or as a sub-panel)
- Shows [Unreleased] entries with inline edit/delete
- "Add Entry" button for manual entries
- "Cut Release" button → opens version bump flow
- Shows past releases (collapsed, expandable)

### Phase 5: Consolidate Duplicated Code

- Remove `_commit_icon()` from `docs_svc/generate.py` → use `changelog.parser.cc_section()`
- Remove `_COMMIT_GROUPS` from `artifacts/release_notes.py` → use `changelog.parser.cc_section()`
- `generate_changelog()` in `docs_svc/generate.py` → delegate to `changelog.engine` for parsing
- `generate_release_notes()` → can read from CHANGELOG.md sections instead of re-parsing git log

### Phase 6: Retroactive Changelog (Bootstrap)

For existing project with history but no CHANGELOG.md:

**New function: `bootstrap_changelog(project_root, since_tag=None)`**
- Scans git log (all commits or since tag)
- Groups by CC type
- Generates initial CHANGELOG.md with proper sections
- User reviews/edits before saving

**UI:** "Initialize Changelog" button shown when CHANGELOG.md doesn't exist

---

## Files to Create

| File | What |
|------|------|
| `src/core/services/changelog/__init__.py` | Re-exports |
| `src/core/services/changelog/models.py` | CCMessage, ChangelogEntry, ChangelogSection, Changelog |
| `src/core/services/changelog/parser.py` | CC parser, section mapping, bump determination |
| `src/core/services/changelog/engine.py` | Load/save/add/edit/remove/cut-release |
| `src/ui/web/routes/changelog.py` | API routes |

## Files to Modify

| File | What |
|------|------|
| `src/ui/web/templates/scripts/integrations/_git.html` | Breaking change checkbox, body textarea, changelog preview in commit modal |
| `src/ui/web/routes/integrations/git.py` | `POST /git/commit` → add changelog integration |
| `src/core/services/docs_svc/generate.py` | Replace `_commit_icon` with `cc_section` import |
| `src/core/services/artifacts/release_notes.py` | Replace `_COMMIT_GROUPS` with `cc_section` import |
| `src/ui/web/server.py` | Register changelog blueprint |

---

## Assumptions

1. CHANGELOG.md uses [Keep a Changelog](https://keepachangelog.com/) format
2. Semver tags use `v` prefix: `v0.1.0`, `v0.2.0`
3. `pyproject.toml` is the canonical version source
4. Every CC commit auto-updates CHANGELOG.md by default (user can skip with checkbox)
5. User can always edit/add/remove entries manually
6. The changelog system is a core service (channel-independent)
7. CC type `_ccTypes` list in `_git.html` is the UI source — the backend parser handles any valid CC prefix

---

## Implementation Order

1. **Phase 1** — Core changelog module (parser, engine, models)
2. **Phase 2** — Commit modal: breaking change + body + changelog preview + backend integration
3. **Phase 4** — Manual changelog management (API + UI panel)
4. **Phase 6** — Bootstrap (generate initial CHANGELOG.md from history)
5. **Phase 3** — Version bump / cut release flow
6. **Phase 5** — Consolidate duplicated CC grouping code
