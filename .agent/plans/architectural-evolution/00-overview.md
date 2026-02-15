# Architectural Evolution — Master Plan

> **Milestone**: Multi-phase structural maturation of the DevOps Control Plane
> **Created**: 2026-02-14
> **Status**: Analysis & Planning

---

## 1. What We're Doing (Summary)

Maturing the platform from "working product" to "architecturally sound platform" across **8 dimensions**:

| # | Dimension | One-liner |
|---|-----------|-----------|
| A | **File Splitting & Template Extraction** | No file >500 lines (700 max exceptions). Extract → [Transform] → Move → Update refs. |
| B | **Layer Hierarchy (CLI → TUI → Web)** | CLI is core. TUI wraps CLI. Web wraps TUI concepts. Push logic DOWN. |
| C | **Static Data / Datasets** | Service catalogs, image lists, StorageClass catalogs live in data files, served at boot, configurable. |
| D | **Audit & Logging** | Audit = operational ledger (exists but underused). Logging = `--debug`/`--verbose` with file output. Two different things. |
| E | **Caching Architecture** | Onion-layer caching: server-side persistent (.state), server-side memory, client sessionStorage. Burst on demand. |
| F | **Modal Preview System** | Content Vault links open in ModalPreview by default, user-configurable (ModalPreview vs ForwardPreview). |
| G | **UI Scale & Settings** | Windows-like scaling profiles. User preferences persisted (localStorage). |
| H | **Documentation Refresh** | Outdated docs, missing docs. Update to reflect actual architecture. |

---

## 2. Current State Diagnosis

### 2.1 File Sizes (the problem)

**Critical (>1000 lines):**
| File | Lines | Problem |
|------|-------|---------|
| `_integrations_setup_modals.html` | **8,282** | The monster. All Docker + K8s + Git + GitHub + CI/CD + Pages wizards in ONE file. |
| `k8s_ops.py` | **2,753** | Detect + validate + observe + act + generate + wizard backend — all K8s logic. |
| `backup_ops.py` | **1,179** | Create + restore + archive + wipe + encrypt — all backup logic. |
| `docker_ops.py` | **1,173** | Detect + validate + compose + Dockerfile — all Docker logic. |
| `routes_devops.py` | **1,020** | Routes for 10+ DevOps sub-features in one blueprint. |
| `security_ops.py` | **994** | scan + fix + audit — all security operations. |

**Over threshold (>500 lines, need splitting):**
34 Python files and ~15 HTML scripts. See `wc -l` output above for the full list.

### 2.2 Layer Violations

**Things that belong in core but live in web/server layer:**

1. **`_infraOptions` / `_infraCategories`** (service catalog) — ~530 lines of hardwired JSON living INSIDE `_integrations_setup_modals.html` (a JS template). This is **data**, not UI. Should live in a data file (`data/catalogs/infra-services.json`), served by the server at boot, available to CLI too.

2. **`_SC_CATALOG`** (StorageClass catalog) — Same problem. ~30 entries hardwired in JS.

3. **`_dockerStackDefaults`** — Stack-specific Dockerfile defaults (images, ports, commands). Also hardwired in JS.

4. **Audit `CATALOG`** (`src/core/services/audit/catalog.py`) — 465-line Python dict of library metadata. This is **data** masquerading as code. Should be a JSON/YAML file.

### 2.3 CLI → TUI Gap

**Current `manage.sh` TUI**: 167 lines, 13 menu items. Barebones — most sub-commands just print `--help` for vault, content, pages, git, backup, secrets. No interactive sub-menus, no real TUI features.

**Reference `continuity-orchestrator/manage.sh`**: 445 lines. Each menu item has its own interactive function with prompts, confirmations, formatted output. The TUI is a first-class operator interface, not just a launcher.

**Gap**: The current TUI is a CLI launcher. The web UI has features (wizards, setup flows, content browsing) that have NO TUI equivalent. The ideal progression is: CLI (core) → TUI (interactive CLI wrapper with sub-menus) → Web (visual + extreme observability).

### 2.4 Audit vs Logging

**Audit** (`src/core/persistence/audit.py`):
- EXISTS but underused. Only the engine runner writes to it (`use_cases/run.py`, `engine/executor.py`).
- Most service operations (vault lock/unlock, content encrypt, backup create, git operations via web routes) do NOT write audit entries.
- The AuditEntry model exists but the writer is not injected widely.

**Logging**:
- `logging.getLogger(__name__)` is NOT used anywhere in `src/` Python files (the grep returned 0 results!).
- Only `server.py` creates a logger.
- `--verbose` exists on the CLI but only controls output verbosity, NOT Python log level.
- No `--debug` flag at all.
- No log-to-file support.
- No integration-level debug output.

### 2.5 Caching

**Current state**:
- Client-side: `sessionStorage` with `_CARD_PREFIX` and `_WIZ_PREFIX` namespaces. 10-min TTL. Manual bust via `cardInvalidate()`.
- Server-side: `devops_cache.py` (543 lines) — in-memory cache with mtime tracking.
- Persistent: Nothing in `.state/` for caching (only `current.json` state and `audit.ndjson`).
- No two-sided cache coherency. No global data available on `window.*` at boot.

### 2.6 Content Vault Navigation

**Current**: `openFileInEditor()` calls `switchTab()` — navigates away from current context. No modal preview option. All intra-links are "ForwardPreview" style.

### 2.7 Jinja Template Usage

**Current**: `dashboard.html` uses `{% include %}` for all partials and scripts. But inside the scripts, Jinja is used only lightly (some files use `{{ }}` for server data injection, most don't). The data that COULD be injected at render time (catalogs, static lists) is instead fetched via API calls.

---

## 3. Phase Plan

### Phase 0: Documentation & Analysis Deep-Dive
- Update `ARCHITECTURE.md` to reflect actual state
- Document the layer hierarchy (CLI → TUI → Web)
- Document the data flow for catalogs/datasets
- Create per-dimension analysis docs (one per phase below)
- **No code changes.** Pure documentation.

### Phase 1: Logging & Debug Infrastructure
- Add `logging.getLogger(__name__)` to ALL Python modules
- Add `--debug` flag to CLI (`logging.DEBUG` level)
- Wire `--verbose` to `logging.INFO`
- Add log-to-file configuration (env var or config)
- Integration-level debug logging for subprocess calls
- **Why first**: Every subsequent phase benefits from being able to debug.

### Phase 2: Audit Expansion
- Inject `AuditWriter` into all core services that perform operations
- Standardize audit entry types (vault, content, backup, git, pages, secrets, config, docker, k8s)
- Make audit opt-in per operation category via config
- Web UI audit tab already exists — connect it to richer data
- **Why second**: Audit is a cross-cutting concern. Getting it right early means all future work is automatically tracked.

### Phase 3: Static Data / Datasets
- Extract `_infraOptions`, `_infraCategories`, `_SC_CATALOG`, `_dockerStackDefaults` to data files (`data/catalogs/*.json`)
- Create a `DatasetLoader` in core that loads base + user additions (JSON/CSV merge)
- Serve datasets via Jinja template injection at render time (`window._datasets = {{ datasets | tojson }}`)
- Make it explicit: these don't change at runtime, loaded at startup
- Fallback to defaults if user file is corrupt/missing
- Document: "restart required for data changes" or implement hot-reload
- **Why third**: This is the prerequisite for file splitting (the monster file shrinks by ~500 lines just from extracting catalogs).

### Phase 4: File Splitting & Template Extraction
- Split `_integrations_setup_modals.html` into per-wizard files
- Split `k8s_ops.py` into `k8s_detect.py`, `k8s_validate.py`, `k8s_cluster.py`, `k8s_generate.py`, `k8s_wizard.py`
- Split other >500-line files
- Update all `{% include %}` references
- Verify no broken references
- **Why fourth**: Now that data is extracted (Phase 3), the splits are cleaner.

### Phase 5: Push Logic Down (Layer Hierarchy)
- Identify web-only logic that should be in core
- Move route business logic into services (routes become thin wrappers)
- Ensure CLI can access everything core offers
- Plan TUI sub-menus (vault interactive, content browsing, backup management)
- **Why fifth**: File splitting (Phase 4) makes this easier because the code is now modular.

### Phase 6: Caching Architecture
- Design onion-layer cache: core (persistent, `.state/cache/`) → server (in-memory) → client (sessionStorage)
- Implement two-sided cache coherency
- Load static data on `window.*` at boot via Jinja injection
- Implement cache burst (server-side + client-side)
- **Why sixth**: Depends on Phase 3 (datasets) and Phase 5 (which data lives where).

### Phase 7: Modal Preview & UI Settings
- Implement ModalPreview component (Content Vault in-place modal)
- Add UI Settings section (ModalPreview vs ForwardPreview, Scale profiles)
- Persist settings in localStorage
- Wire all intra-links to use configurable preview mode
- **Why seventh**: UI polish layer, depends on stable architecture underneath.

### Phase 8: TUI Enhancement
- Progressive feature parity with key web features
- Interactive sub-menus for vault, content, backup, secrets
- Formatted table output
- Reference: continuity-orchestrator's TUI patterns
- **Why last**: The TUI wraps CLI (core). Core must be solid first.

---

## 4. Dependencies Between Phases

```
Phase 0 (docs) ← standalone, do first
Phase 1 (logging) ← standalone
Phase 2 (audit) ← benefits from Phase 1
Phase 3 (datasets) ← standalone
Phase 4 (splitting) ← benefits from Phase 3
Phase 5 (layer push-down) ← depends on Phase 4
Phase 6 (caching) ← depends on Phase 3 + Phase 5
Phase 7 (modal/UI) ← depends on Phase 4
Phase 8 (TUI) ← depends on Phase 5
```

**Suggested execution order**: 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8

But Phases 1, 2, 3 have no hard dependencies and could be parallelized.

---

## 5. Principles We Follow Throughout

1. **CLI is core. Core is CLI.** Everything must work from `python -m src.main`.
2. **No silent assumptions.** Ambiguity → ask.
3. **No scope drift.** Each phase has its own scope. New ideas → parking lot.
4. **Traceability.** Goal → Requirement → Change → Test → Evidence.
5. **Evolution, not revolution.** Each phase is independently shippable.
6. **500 line limit** (700 max for justified exceptions). Enforced going forward.
7. **Data is data, code is code.** Catalogs, lists, templates belong in data files.
8. **Audit everything.** Operations write to the ledger.
9. **Two caching layers minimum.** Server + client. Burst together.
10. **TUI deserves parity.** Not an afterthought.

---

## 6. Open Questions (for user decision)

- [ ] **Logging format**: Structured JSON logs or human-readable? Or configurable?
- [ ] **Dataset hot-reload**: Restart required for catalog changes, or file-watch + reload?
- [ ] **UI Settings persistence**: localStorage only, or server-side (per-user settings file)?
- [ ] **TUI scope for Phase 8**: Which features first? Full parity or top-5?
- [ ] **Audit retention**: Should audit entries have a TTL/rotation policy?

---

## 7. Files That Will Be Created Per Phase

Each phase will get its own detailed plan:
- `01-logging-debug.md`
- `02-audit-expansion.md`
- `03-datasets-catalogs.md`
- `04-file-splitting.md`
- `05-layer-push-down.md`
- `06-caching-architecture.md`
- `07-modal-preview-ui-settings.md`
- `08-tui-enhancement.md`
