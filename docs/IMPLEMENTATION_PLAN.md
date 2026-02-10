# Implementation Plan

> **Approach:** Infrastructure-first. Test-first. Each milestone ships something
> you can run.
>
> **Rule:** Nothing merges without tests, lint, and type checks passing.

---

## How We Work

### Principles

1. **Bootstrap the toolchain before writing features** — CI, lint, test, types
   must exist before a single domain model. If the guards aren't there from
   commit 1, they never will be.

2. **Each milestone produces a runnable artifact** — not "we designed the
   models." Instead: "you can run `python -m src.main status` and see output."

3. **Vertical slices, not horizontal layers** — don't build all models, then
   all services, then all CLI. Instead: build one complete path from config →
   model → service → CLI in each milestone.

4. **Tests are the spec** — write the test first. If you can't test it, you
   can't build it. Tests define the contract before the implementation exists.

5. **Conventional commits** — every commit message follows
   `type(scope): description`. Types: `feat`, `fix`, `refactor`, `test`,
   `docs`, `chore`, `ci`. This enables automated changelogs later.

6. **ADRs for decisions** — any non-obvious architectural choice gets a short
   Architecture Decision Record in `docs/adr/`.

### Branch Strategy

```
main                    ← always green, always runnable
├── ms/0-bootstrap      ← milestone branches
├── ms/1-kernel
├── ms/2-detection
└── ...
```

Each milestone is a branch. PR into main when all acceptance criteria pass.
Squash merge to keep history clean.

---

## Milestone Dependency Graph

```
MS-0: Bootstrap ──────────────────────────────────────┐
  │                                                    │
  ▼                                                    │
MS-1: Kernel (models + config + persistence)           │
  │                                                    │
  ├──────────────────┐                                 │
  ▼                  ▼                                 │
MS-2: Adapters     MS-3: CLI Shell                     │
  │                  │                                 │
  └────────┬─────────┘                                 │
           ▼                                           │
         MS-4: Detection (first vertical slice)        │
           │                                           │
           ▼                                           │
         MS-5: Engine + Automations                    │
           │                                           │
           ├──────────────────┐                        │
           ▼                  ▼                        │
         MS-6: Reliability  MS-7: Web Admin            │
           │                  │                        │
           └────────┬─────────┘                        │
                    ▼                                  │
                  MS-8: manage.sh + Polish             │
                    │                                  │
                    ▼                                  │
                  MS-9: Packaging + Docs               │
```

---

## MS-0: Bootstrap (Day 1)

> **Goal:** A repo you'd be proud to `git clone`. CI runs. Tests run (with 0
> tests). Lint passes. Types check. A human can run `python -m src.main` and
> see a help message.

### Tasks

| # | Task | Output |
|---|------|--------|
| 0.1 | Create `pyproject.toml` with hatchling, dev deps, scripts | Build config |
| 0.2 | Create directory scaffold (all `__init__.py` files) | Package structure |
| 0.3 | Create `src/main.py` with Click stub (`--help` works) | Runnable entrypoint |
| 0.4 | Create `pytest.ini` / conftest, run `pytest` (0 tests pass) | Test framework |
| 0.5 | Create `ruff.toml` config | Lint config |
| 0.6 | Create `mypy.ini` / pyproject section | Type check config |
| 0.7 | Create `.github/workflows/ci.yml` (lint + test + types) | CI pipeline |
| 0.8 | Create `.gitignore`, `.editorconfig`, `README.md` | Repo hygiene |
| 0.9 | Create `Makefile` with `make lint`, `make test`, `make check` | Dev shortcuts |
| 0.10 | First commit: all green, `make check` passes | ✅ Milestone complete |

### Acceptance Criteria

- [x] `pip install -e ".[dev]"` succeeds
- [x] `python -m src.main --help` prints help text
- [x] `make lint` passes (ruff)
- [x] `make test` passes (pytest, 0 tests collected)
- [x] `make types` passes (mypy)
- [x] `make check` runs all three
- [x] CI workflow exists (even if no GitHub remote yet)

### Estimated effort: 1-2 hours

---

## MS-1: Kernel (Models + Config + Persistence)

> **Goal:** The domain type system exists. You can load a `project.yml`,
> validate it, serialize state, and write audit entries. All with tests.

### Tasks

| # | Task | Output |
|---|------|--------|
| 1.1 | `core/models/project.py` — `Project`, `Environment` (Pydantic) | Domain types |
| 1.2 | `core/models/module.py` — `Module`, `ModuleDescriptor` | Domain types |
| 1.3 | `core/models/stack.py` — `Stack`, `StackCapability` | Domain types |
| 1.4 | `core/models/action.py` — `Action`, `Receipt` | Domain types |
| 1.5 | `core/models/state.py` — `ProjectState` (root state model) | State schema |
| 1.6 | `core/config/loader.py` — Load `project.yml` → `Project` model | Config loading |
| 1.7 | `core/persistence/state_file.py` — Atomic state read/write | State persistence |
| 1.8 | `core/persistence/audit.py` — Append-only NDJSON ledger | Audit persistence |
| 1.9 | `tests/test_models.py` — Serialization roundtrips | 15+ tests |
| 1.10 | `tests/test_config.py` — Valid + invalid YAML loading | 10+ tests |
| 1.11 | `tests/test_persistence.py` — State + audit file operations | 10+ tests |
| 1.12 | Example `project.yml` in repo root (for self-hosting) | Working config |

### Acceptance Criteria

- [x] All models pass Pydantic validation roundtrip tests
- [x] `project.yml` loads into `Project` model without error
- [x] State file writes atomically and reads back identically
- [x] Audit ledger appends entries and reads back correctly
- [x] 35+ tests pass
- [x] `make check` still green

### Estimated effort: 4-6 hours

---

## MS-2: Adapter Foundation

> **Goal:** The adapter protocol exists. Mock mode works. You can call
> `registry.execute_action()` on any adapter name and get a Receipt back.

### Tasks

| # | Task | Output |
|---|------|--------|
| 2.1 | `adapters/base.py` — `Adapter` ABC, `ExecutionContext` | Protocol |
| 2.2 | `adapters/registry.py` — `AdapterRegistry`, mock swap | Registry |
| 2.3 | `adapters/mock.py` — Universal mock adapter | Testing support |
| 2.4 | `adapters/shell/command.py` — Generic shell execution | First real adapter |
| 2.5 | `adapters/shell/filesystem.py` — File operations adapter | Second adapter |
| 2.6 | `tests/test_adapters.py` — Protocol, registry, mock, shell | 20+ tests |

### Acceptance Criteria

- [x] `AdapterRegistry(mock_mode=True).execute_action(...)` returns success Receipt
- [x] `AdapterRegistry(mock_mode=False)` registers shell adapters
- [x] Shell adapter can execute a command and capture output
- [x] Filesystem adapter can check file existence, read, write
- [x] All operations return Receipt (never raise)
- [x] 20+ tests pass

### Estimated effort: 3-4 hours

---

## MS-3: CLI Shell

> **Goal:** The CLI framework is live. `status` and `config check` work end to
> end. This is the first time a human can *use* the system.

### Tasks

| # | Task | Output |
|---|------|--------|
| 3.1 | `ui/cli/main.py` — Click group with subcommands | CLI framework |
| 3.2 | `ui/cli/status.py` — `status` command (loads config + state) | First command |
| 3.3 | `ui/cli/config.py` — `config check` (validates project.yml) | Second command |
| 3.4 | `--json` output mode on both commands | Scripting support |
| 3.5 | `--env` flag for environment selection | Environment targeting |
| 3.6 | `tests/test_cli.py` — CLI invocation tests via Click runner | 10+ tests |

### Acceptance Criteria

- [x] `python -m src.main status` prints project summary
- [x] `python -m src.main status --json` outputs valid JSON
- [x] `python -m src.main config check` validates project.yml
- [x] Missing project.yml shows clear error message
- [x] Invalid project.yml shows validation errors
- [x] 10+ tests pass

### Estimated effort: 2-3 hours

### 🎉 First Demo Point

After MS-3, you can:
```bash
python -m src.main config check     # Validates your project config
python -m src.main status           # Shows project summary
python -m src.main status --json    # Machine-readable output
```

---

## MS-4: Detection (First Vertical Slice)

> **Goal:** The system can look at a directory and tell you what's in it. This
> is the first **complete vertical slice**: config → model → service → adapter
> → CLI → output.

### Tasks

| # | Task | Output |
|---|------|--------|
| 4.1 | `core/services/detection.py` — Module discovery + stack matching | Detection logic |
| 4.2 | `stacks/python/stack.yml` — Python stack definition | First stack |
| 4.3 | `stacks/node/stack.yml` — Node stack definition | Second stack |
| 4.4 | `stacks/docker-compose/stack.yml` — Docker Compose stack | Third stack |
| 4.5 | `core/config/stack_loader.py` — Load stack definitions from YAML | Stack loading |
| 4.6 | `core/use_cases/detect.py` — Detection use case | Use case |
| 4.7 | `core/use_cases/status.py` — Status use case (enriched with detection) | Use case |
| 4.8 | `ui/cli/detect.py` — `detect` command | CLI command |
| 4.9 | `tests/test_detection.py` — Detection with fixture directories | 15+ tests |
| 4.10 | `tests/fixtures/` — Sample project structures for testing | Test fixtures |

### Acceptance Criteria

- [x] `python -m src.main detect` scans and reports modules + stacks
- [x] Detects Python projects (pyproject.toml, requirements.txt)
- [x] Detects Node projects (package.json)
- [x] Detects Docker Compose projects (docker-compose.yml)
- [x] Detection results saved to `state/detected/modules.json`
- [x] `status` command shows detected modules
- [x] 15+ new tests pass

### Estimated effort: 4-6 hours

### 🎉 Second Demo Point

```bash
python -m src.main detect           # Scans project, finds modules
python -m src.main status           # Shows modules + stacks + versions
```

---

## MS-5: Engine + Automations

> **Goal:** The engine can execute named automations with steps, prerequisites,
> and receipts. Dry-run works.

### Tasks

| # | Task | Output |
|---|------|--------|
| 5.1 | `core/models/automation.py` — `Automation`, `Step`, `Prerequisite` | Automation model |
| 5.2 | `core/engine/runner.py` — Execution loop (6 phases) | Engine |
| 5.3 | `core/engine/evaluator.py` — Condition evaluation | Evaluator |
| 5.4 | `core/services/planning.py` — Build execution plans | Planner |
| 5.5 | `core/use_cases/automate.py` — Automation use case | Use case |
| 5.6 | `automations/lint.yml` — First real automation | Automation def |
| 5.7 | `automations/test.yml` — Second automation | Automation def |
| 5.8 | `adapters/languages/python.py` — Python adapter (pip, venv) | Language adapter |
| 5.9 | `adapters/languages/node.py` — Node adapter (npm, yarn) | Language adapter |
| 5.10 | `ui/cli/automate.py` — `automate` command with `--dry-run` | CLI command |
| 5.11 | `tests/test_engine.py` — Engine phases, dry-run, receipts | 20+ tests |
| 5.12 | `tests/test_automations.py` — YAML loading, plan building | 10+ tests |

### Acceptance Criteria

- [x] `python -m src.main run test` runs test on detected modules
- [x] `python -m src.main run test --dry-run` shows plan without executing
- [x] `python -m src.main run test --module api` targets specific module
- [x] Engine produces ExecutionReport with receipts
- [x] Failed actions produce failure receipts (no exceptions)
- [x] Audit ledger records execution details
- [x] 30+ new tests pass

### Estimated effort: 6-8 hours

### 🎉 Third Demo Point

```bash
python -m src.main automate lint                    # Lint all modules
python -m src.main automate lint --dry-run          # Show what would run
python -m src.main automate test --module api       # Test specific module
python -m src.main automate lint --json             # Machine-readable result
```

---

## MS-6: Reliability + Observability

> **Goal:** Production-grade plumbing. Circuit breakers protect adapters, retry
> queues handle transient failures, health checks report system status, metrics
> track everything.

### Tasks

| # | Task | Output |
|---|------|--------|
| 6.1 | `core/reliability/circuit_breaker.py` — Circuit breaker pattern | Reliability |
| 6.2 | `core/reliability/retry_queue.py` — Persistent retry queue | Reliability |
| 6.3 | `core/observability/health.py` — Health checker | Observability |
| 6.4 | `core/observability/metrics.py` — Counter/Gauge/Histogram | Observability |
| 6.5 | Wire circuit breaker into `AdapterRegistry.execute_action()` | Integration |
| 6.6 | Wire retry queue into engine failure handling | Integration |
| 6.7 | Wire metrics into engine execution phases | Integration |
| 6.8 | `ui/cli/health.py` — `health` command | CLI command |
| 6.9 | `tests/test_reliability.py` — CB states, retry backoff | 15+ tests |
| 6.10 | `tests/test_observability.py` — Health, metrics | 10+ tests |

### Acceptance Criteria

- [x] Circuit breaker transitions: CLOSED → OPEN after N failures
- [x] Circuit breaker transitions: OPEN → HALF_OPEN after timeout
- [x] Circuit breaker transitions: HALF_OPEN → CLOSED after success
- [x] Retry queue persists to disk, survives restart
- [x] Retry queue uses exponential backoff
- [x] `python -m src.main health` shows component status
- [x] 25+ new tests pass

### Estimated effort: 4-6 hours

---

## MS-7: Web Admin

> **Goal:** Local web dashboard. Status, modules, adapter health, automation
> runner — all in the browser.

### Tasks

| # | Task | Output |
|---|------|--------|
| 7.1 | `ui/web/server.py` — Flask app factory, port handling | Web server |
| 7.2 | `ui/web/routes_core.py` — Dashboard + status API | Core routes |
| 7.3 | `ui/web/routes_modules.py` — Module listing API | Module routes |
| 7.4 | `ui/web/routes_adapters.py` — Adapter status API | Adapter routes |
| 7.5 | `ui/web/routes_automations.py` — Run automation API | Automation routes |
| 7.6 | Templates: index, partials, scripts (shared block pattern) | Web UI |
| 7.7 | `ui/web/static/css/admin.css` — Dark mode, theming | Styling |
| 7.8 | `core/security/vault.py` — .env vault encryption | Security |
| 7.9 | `ui/web/routes_vault.py` — Vault lock/unlock API | Vault routes |
| 7.10 | `tests/test_web.py` — Route tests (status codes, shapes) | 15+ tests |
| 7.11 | `tests/test_vault.py` — Vault encrypt/decrypt/auto-lock | 10+ tests |

### Acceptance Criteria

- [x] `python -m src.main web` starts server on 127.0.0.1:8000
- [x] Dashboard shows project status, modules, adapters
- [x] Can run automations from the browser
- [x] Vault locks/unlocks .env file
- [x] Dark mode dashboard with premium design
- [x] 25+ new tests pass

### Estimated effort: 8-12 hours

---

## MS-8: manage.sh + Polish

> **Goal:** The friendly operator console. Interactive TUI, live-reload,
> end-to-end polish.

### Tasks

| # | Task | Output |
|---|------|--------|
| 8.1 | `manage.sh` — Interactive menu, venv activation, banner | TUI wrapper |
| 8.2 | Direct mode: `./manage.sh detect`, `./manage.sh status` | Direct invocation |
| 8.3 | Web server live-reload (SPACE to restart) | Dev experience |
| 8.4 | Error message polish across all commands | UX |
| 8.5 | `--verbose` / `--quiet` modes | Output control |
| 8.6 | Color output with graceful degradation | UX |
| 8.7 | End-to-end integration tests | 10+ tests |

### Acceptance Criteria

- [x] `./manage.sh` shows interactive menu
- [x] `./manage.sh status` runs directly
- [x] All commands have helpful `--help` text
- [x] Error messages are clear and actionable
- [x] Works in CI (no TTY) and locally

### Estimated effort: 3-4 hours

---

## MS-9: Packaging + Docs

> **Goal:** Ready for other humans. Documentation complete, installable from
> git, example projects demonstrate usage.

### Tasks

| # | Task | Output |
|---|------|--------|
| 9.1 | Complete `README.md` with quickstart | Documentation |
| 9.2 | `docs/QUICKSTART.md` — 5-minute setup guide | Documentation |
| 9.3 | `docs/STACKS.md` — How to create stacks | Documentation |
| 9.4 | `docs/ADAPTERS.md` — How to create adapters | Documentation |
| 9.5 | `docs/AUTOMATIONS.md` — How to define automations | Documentation |
| 9.6 | Example: wire to this repo (self-hosting) | Example |
| 9.7 | Example: wire to a multi-service project | Example |
| 9.8 | `Dockerfile` for containerized usage | Distribution |
| 9.9 | PyPI-ready packaging | Distribution |

### Acceptance Criteria

- [ ] A new user can go from `git clone` to `./manage.sh status` in 5 minutes
- [ ] Docs explain how to add stacks, adapters, automations
- [ ] Examples demonstrate real-world usage
- [ ] 150+ total tests pass

### Estimated effort: 4-6 hours

---

## Summary

| Milestone | Deliverable | Tests | Cumulative |
|---|---|---|---|
| MS-0 | Repo, CI, toolchain | 7 | 7 |
| MS-1 | Models, config, persistence | 50+ | 57+ |
| MS-2 | Adapter protocol + shell | 30+ | 87+ |
| MS-3 | CLI (status, config) | 15+ | 102+ |
| MS-4 | Detection (first slice) | 25+ | 127+ |
| MS-5 | Engine + automations | 42+ | 169 |
| MS-6 | Reliability + observability | 65+ | **234** |
| MS-7 | Web admin + vault | 64+ | **298** |
| MS-8 | manage.sh + polish | 22+ | **320** |
| MS-9 | Docs + packaging | — | 280+ |

**Total estimated effort: 35-55 hours** across 10 milestones.

First demo (MS-3): ~7-11 hours in.  
Fully operational (MS-8): ~30-45 hours in.

---

## What "Done" Looks Like

When all milestones are complete, this is the daily experience:

```bash
# Morning: check project health
./manage.sh status

# Add a new service
./manage.sh scaffold --stack python-fastapi --name billing-api

# Run all checks
./manage.sh automate lint
./manage.sh automate test

# Open the dashboard
./manage.sh web

# CI handles the rest
git push  # → CI runs detect + lint + test automatically
```

The control plane **knows** your project. It **sees** your modules. It **drives**
your operations. Through any interface you prefer.
