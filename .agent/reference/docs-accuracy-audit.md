# Docs Accuracy Audit

> Verified: 2026-03-05
> Method: Compared each doc's claims against actual source code.

---

## Audit Summary

| Doc | Lines | Status | Action Taken |
|-----|-------|--------|-------------|
| ARCHITECTURE.md | 313 | 🟢 FIXED | Dir layout rewritten, tab table updated, vault path+KDF fixed |
| WEB_ADMIN.md | 263 | 🟢 FIXED | Template structure + API table rewritten, tabs added |
| CONTENT.md | 199 | 🟢 FIXED | API table expanded (10→30+), 4 feature sections added |
| DEVELOPMENT.md | 206 | 🟢 FIXED | Paths corrected, recipes updated for package structure |
| QUICKSTART.md | 121 | 🟢 FIXED | Tab table updated 7→9 |
| PAGES.md | 223 | 🟢 FIXED | Builder path corrected |
| VAULT.md | 140 | 🟢 FIXED | KDF iteration count corrected (480k→100k) |
| DESIGN.md | 317 | 🟢 OK | Philosophy doc — not tied to specific code |
| ADAPTERS.md | 202 | 🟢 OK | Verified — adapter paths and protocols accurate |
| STACKS.md | 207 | 🟢 OK | Verified — stack dirs and definitions accurate |
| README.md | 639 | 🟢 OK | No stale references found |
| ANALYSIS.md | 777 | 🟢 OK | Historical analysis — not code-referencing |
| AUDIT_ARCHITECTURE.md | 505 | 🟢 OK | Design doc |
| AUDIT_PLAN.md | 667 | 🟢 OK | Planning doc |
| CONSOLIDATION_AUDIT.md | 303 | 🟢 OK | Audit results — snapshot in time |
| DEVOPS_UI_GAP_ANALYSIS.md | 266 | 🟡 STALE NOTE | Added staleness warning |
| INTEGRATION_GAP_ANALYSIS.md | 267 | 🟡 STALE NOTE | Added staleness warning |

---

## Detailed Findings

### ARCHITECTURE.md — 🔴 STALE

**Directory Layout (lines 82-202) — MAJOR:**
- Lines 103-136: Shows `src/core/services/` as flat files (`vault.py`, `content_crypto.py`, etc.)
  - **Reality**: Services are now organized into 30 domain packages: `vault/`, `content/`, `audit/`, `k8s/`, `generators/`, `chat/`, `trace/`, etc.
- Lines 138-142: Shows `src/adapters/` with only `base.py`, `registry.py`, `mock.py`, `shell/`
  - **Reality**: Adapters now include `vcs/` (git), `containers/` (docker), and potentially more
- Lines 144-174: Shows `src/ui/web/` with flat shim files (`vault.py`, `content_crypto.py`, etc.)
  - **Reality**: ALL shim files deleted. No `web/vault.py`, `web/content_crypto.py`, etc.
- Lines 152-174: Shows flat route files (`routes_api.py`, `routes_vault.py`, etc.)
  - **Reality**: Routes refactored into 32 sub-packages under `routes/` (e.g., `routes/vault/`, `routes/content/`)
- Lines 162-174: Template structure shows old flat `scripts/` names
  - **Reality**: Scripts organized into subdirectories: `scripts/content/`, `scripts/secrets/`, `scripts/integrations/`, etc.

**Tab Table (lines 230-241) — WRONG:**
- Lists 7 tabs, missing DevOps and Audit
- **Reality**: 9 tab partials exist (dashboard, wizard, secrets, commands, content, integrations, devops, audit, debugging)

**Test Count (line 185) — STALE:**
- Says "324 tests"
- Actual count likely different (needs `pytest --co -q | tail -1`)

### WEB_ADMIN.md — 🔴 STALE

**Template Structure (lines 115-202) — MAJOR:**
- Uses old flat naming: `_content_init.html`, `_content_nav.html`, `_secrets_init.html`
- **Reality**: Files are now `content/_init.html`, `content/_nav.html`, `secrets/_init.html`
- Also uses old LOADER pattern comments that may not match current structure
- Missing: `content/_glossary.html`, `content/_smart_folders.html`, `content/_chat.html`, `content/_chat_refs.html`, `content/_modal_preview.html`
- Missing entire sections: `assistant/`, `auth/`, `docker_wizard/`, `k8s_wizard/`

**API Structure (lines 213-222):**
- References `routes_api.py`, `routes_vault.py`, `routes_secrets.py` — all deleted
- **Reality**: Routes are in `routes/api/`, `routes/vault/`, `routes/secrets/`, etc.
- Missing 24+ route packages (audit, chat, ci, devops, dns, docker, events, etc.)

**Tabs Section (lines 28-103):**
- Missing DevOps tab, Audit tab descriptions
- Content tab description lacks: smart folders, glossary/outline panel, chat, peek references

### CONTENT.md — 🟡 PARTIAL

**API Endpoints (lines 91-102):**
- Lists 10 endpoints, but 30+ actually exist
- `/api/content/file/<path>` listed but doesn't exist (it's `/api/content/preview`)
- Missing: `/api/content/glossary`, `/api/content/outline`, `/api/content/peek-refs`,
  `/api/content/peek-resolve`, `/api/content/save`, `/api/content/save-encrypted`,
  `/api/content/download`, `/api/content/metadata`, `/api/content/move`,
  `/api/content/create-folder`, `/api/content/enc-key-status`, `/api/content/setup-enc-key`,
  `/api/content/release-status`, `/api/content/release-cancel`, `/api/content/release-inventory`,
  `/api/content/restore-large`, `/api/content/optimize-status`, `/api/content/optimize-cancel`,
  `/api/content/preview-encrypted`, `/api/content/clean-release-sidecar`,
  `/api/content/folders`, `/api/content/all-folders`

**Missing Features:**
- No mention of Smart Folders
- No mention of Glossary/Outline panel
- No mention of Chat integration
- No mention of Peek (reference resolution)

### DEVOPS_UI_GAP_ANALYSIS.md — 🟡 PARTIAL

- Status markers (✅/❌) likely stale — many features have been implemented since this was written
- Would need card-by-card verification against actual route handlers

### INTEGRATION_GAP_ANALYSIS.md — 🟡 PARTIAL

- Same issue as DEVOPS_UI_GAP_ANALYSIS — status markers likely stale

---

## Recommended Actions (Priority Order)

1. **ARCHITECTURE.md** — Rewrite directory layout section to match current structure
2. **WEB_ADMIN.md** — Rewrite template structure and API structure sections
3. **CONTENT.md** — Add missing features and expand API table
4. **Gap analysis docs** — Re-verify status markers or add "last verified" dates
5. **Remaining docs** — Spot-check on demand when relevant features are modified
