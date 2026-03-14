# Milestone: QueryMediator — Trilateral Data Hub

> **Status:** Ideation
> **Created:** 2026-03-12
> **Scope:** Core infrastructure — data mediation layer

---

## Origin — The User's Vision (verbatim)

> Great lets tackle this in order, we need the foundation and then
> infrastructure first. and then we go chunk by chunk in order. one
> thing at the time.
>
> WE lets visualize the cache tree and index map and see what we are
> missing and think inner plan communication. how we call this again?
> trilateral communication. yup.. it magically came to me, this is
> going to be a trilateral com system which will allow to optimize
> everything. a bit like a zookeeper of our marvel.
> Do you understand what I mean? maybe its a bit too advanced for
> you? I dont recall how we call this, I think the name changed based
> on the domain.. Certainly it could be named a mediator pattern I guess.
>
> Something like this:
> Backend  → Mediator
> Cache    → Mediator
> Index    → Mediator
>
> Why not the UI itself in the trilateral? because its upstream its
> receiving the informations and when it wants it refresh naturally
> over time or show that new information is available, it offers
> manual refresh, it receives stale state from update to fs tracked
> files and classified, but those are all backend. so because we can
> update anything in the frontend if needed we need to evolve the
> system behind it.
>
> We can make it a very well structured and granular aggregate, and
> use something like this pseudo code principle:
> ```python
> class QueryMediator:
>     def __init__(self, cache, index):
>         self.cache = cache
>         self.index = index
>
>     def search(self, query):
>         cached = self.cache.get(query)
>         if cached is not None:
>             return cached
>
>         results = self.index.search(query)
>         self.cache.set(query, results)
>         return results
> ```
> This is raw but remember its just a pseudo, a very partial example.
>
> Allow ourself to build a tree with multiple layers of branches
> before the leaves. There is no need to reset the whole, you always
> just get the delta, the new and or the fresh.
> No need to spiral into the spaghetti to reach the goal, you declare
> it at the top, a real strong index with in this case connection to
> fs watcher for the project folder. the mediator just give you
> anything you want and it is the data central hub so you can connect
> to everything. even the deepest layers of the indexes. Trees and
> Indexes.
> We could even give it a view in the debugging tab, it would be an
> index debug tab and the user will be able to turn all this off if
> he wants like the button in the Settings / Preferences menu but
> specially made for this view and UX proof.
> With the right map I believe you can achieve anything, its all
> about time and pruning and bust[t=x] and target and options, PUT,
> GET, refreshing, force rescan, force flush cache, diag view,
> explain, cascade, cascade depth, subscribe, dispatch, and anything
> necessary to do this to the full extend and cover 100% of what
> already existing and even another 100% more.
> A lot of concurrence and various order and priorities possible and
> different pattern to refresh and update and such.
>
> This is just a phase of ideation right now, it wasn't crystallized
> yet, we need to discuss the bullet-proof solution / model we should
> come up with. This will be a long journey, you can put this to file
> as quoted as the first message in the definition of the milestone
> and start pondering about the marvel.
> Its mostly about the bottom up. index sitting at the bottom, we want
> to make this graceful and strong and everything that connect to it
> and create a system/module that mediate this need.
> Doing this properly we would be able to loadbalance all operations
> in order to reduce duration / increase the speed of scan and such
> from result of data or tool output and call so that everywhere the
> timing can decrease by at least half via a proper data hub. Show me
> that you feel and understand me and write this document I am asking for.

---

## Full System Census — What Exists Today

**Scale:** 456 Python files, 126,003 lines in `src/core/services/`.
128 JS template files, 71,838 lines in `src/ui/web/templates/scripts/`.

### A. Backend Data Domains (35 service modules)

```
src/core/services/
├── audit/              (30 files, 14,443 LOC)  ← L0/L1/L2 code analysis
│   ├── l0_detection.py         ← language & stack detection
│   ├── l0_deep_detectors.py    ← deep heuristics (frameworks, patterns)
│   ├── l0_hw_detectors.py      ← hardware/env detection
│   ├── l0_os_detection.py      ← OS family, distro, version
│   ├── l1_classification.py    ← file type classification
│   ├── l1_parsers.py           ← language-aware parsing
│   ├── l2_risk.py              ← risk analysis
│   ├── scoring.py              ← health scores → .state/audit_scores.json
│   └── parsers/                ← 10 language parsers (py,js,go,rust,c,jvm,css,config,template,fallback)
│
├── tool_install/       (137 files, 27,454 LOC) ← THE LARGEST MODULE
│   ├── data/
│   │   ├── recipes/            ← 19 system presets (core, devops, languages, network, etc.)
│   │   ├── tool_specs/         ← per-tool spec sheets
│   │   ├── tool_failure_handlers/  ← per-tool failure handlers
│   │   └── constants.py        ← shared constants
│   ├── detection/
│   │   ├── environment.py      ← sandbox, nvm, cpu features
│   │   ├── network.py          ← proxy detection
│   │   ├── hardware.py         ← gpu, kernel, build toolchain
│   │   └── service_status.py   ← running services
│   ├── resolver/
│   │   ├── plan_resolution.py  ← install plan resolution
│   │   ├── update_resolution.py ← update plan resolution
│   │   ├── choice_resolution.py ← interactive choices
│   │   ├── method_selection.py  ← PM/method selection
│   │   └── dynamic_dep_resolver.py ← transitive deps
│   ├── execution/
│   │   ├── step_executors.py   ← run install/update steps
│   │   ├── plan_state.py       ← .state/install_plans/*.json
│   │   ├── chain_state.py      ← .state/install_plans/ (chains)
│   │   ├── download.py         ← download management
│   │   └── offline_cache.py    ← offline package cache
│   └── orchestration/
│       └── orchestrator.py     ← top-level install orchestration
│
├── k8s/                (19 files, 8,620 LOC)
│   ├── detect.py               ← kubectl/helm/cluster detection
│   ├── wizard_detect.py        ← wizard environment detection
│   ├── wizard.py               ← wizard state → .state/ implied
│   ├── cluster.py              ← live cluster queries
│   ├── validate*.py            ← 5 validation modules
│   ├── helm*.py                ← Helm chart generation
│   └── common.py               ← shared K8s utilities
│
├── artifacts/          (25 files, 6,613 LOC)
│   ├── discovery.py            ← detect build targets, Makefile evolution
│   ├── engine.py               ← build/publish orchestration
│   ├── version.py              ← version resolution
│   ├── builders/               ← 6 builders (go, npm, pip, cargo, makefile, dotnet, gem, gradle, maven)
│   ├── publishers/             ← github_release, npm
│   └── workflow_gen.py         ← CI workflow generation
│
├── pages_builders/     (12 files, 6,450 LOC)
│   ├── base.py                 ← abstract builder with detect()
│   ├── mkdocs.py, hugo.py, sphinx.py, docusaurus.py, raw.py, custom.py
│   ├── template_engine.py      ← template processing
│   ├── audit_directive.py      ← audit directive resolution (1,753 lines!)
│   └── smart_folder_enrichment.py  ← smart folder content enrichment
│
├── content/            (11 files, 5,033 LOC)
│   ├── listing.py              ← folder contents, recursive listing
│   ├── file_ops.py             ← CRUD, path resolution
│   ├── file_advanced.py        ← rename, project folder listing
│   ├── outline.py              ← document outline (mtime-cached)
│   ├── release.py              ← release status tracking (in-memory)
│   ├── release_sync.py         ← release asset sync
│   ├── optimize_video.py       ← video optimization (in-memory status)
│   └── crypto_ops.py           ← content encryption
│
├── system_posture/     (11 files, 2,043 LOC)
│   ├── cache.py                ← TTL cache (file-backed → .state/posture_cache.json)
│   ├── orchestrator.py         ← pillar assembly + get_summary()
│   ├── models.py               ← PostureItem, PillarResult, SystemPosture
│   ├── ranking.py              ← rank levels + lifecycle data (JSON)
│   ├── scanners/
│   │   ├── platform.py         ← OS/kernel/glibc scan
│   │   └── toolchain.py        ← tool version scan
│   └── bridges/
│       └── project.py          ← bridge to /metrics/health
│
├── devops/             (4 files, 1,609 LOC)
│   ├── cache.py                ← mtime-based card cache (file-backed → .state/devops_cache.json)
│   ├── activity.py             ← activity log (file-backed → .state/audit_activity.json)
│   └── __init__.py             ← public API
│
├── scripts/            (9 files, 3,405 LOC)
│   ├── registry.py             ← script discovery & metadata
│   ├── executor.py             ← script execution
│   ├── plan_executor.py        ← plan execution (SSE streaming)
│   ├── plan_storage.py         ← plan persistence → .state/cdp-plans/
│   ├── config.py               ← scripts config
│   └── output_router.py        ← output routing
│
├── chat/               (8 files, 2,422 LOC)
│   ├── chat_ops.py             ← message CRUD, git sync
│   ├── chat_crypto.py          ← encryption
│   ├── refs_resolve.py         ← reference resolution (.state/ paths)
│   └── models.py               ← data models
│
├── cdp_test/           (7 files, 4,643 LOC)
│   ├── storage.py              ← suites/results → .state/cdp-tests/
│   ├── recorder.py             ← test recording
│   ├── replayer.py             ← test replay
│   ├── session.py              ← active sessions (in-memory)
│   └── models.py               ← data models
│
├── git/                (7 files, 3,560 LOC)
│   ├── ops.py                  ← git operations
│   ├── auth.py                 ← remote detection, SSH
│   ├── gh_api.py               ← GitHub API (EventBus integration)
│   └── gh_auth.py              ← GitHub OAuth device flow
│
├── docker/             (6 files, 2,074 LOC)
│   ├── detect.py               ← Docker detection (compose, daemon)
│   ├── containers.py           ← container management
│   └── generate.py             ← Dockerfile generation
│
├── vault/              (5 files, 2,074 LOC)
│   ├── core.py                 ← vault open/close/lock
│   ├── io.py                   ← file I/O, secret detection
│   ├── env_crud.py             ← env var CRUD
│   └── env_ops.py              ← env operations
│
├── security/           (5 files, 1,127 LOC)
│   ├── scan.py                 ← secret scanning, sensitive file detection
│   ├── common.py               ← security utilities
│   └── posture.py              ← security posture
│
├── ledger/             (3 files, 1,598 LOC)
│   ├── worktree.py             ← git worktree management, run tags
│   └── ledger_ops.py           ← saved audits, ledger CRUD
│
├── backup/             (4 files, 1,793 LOC)
│   ├── archive.py              ← backup creation/listing
│   ├── restore.py              ← restore operations
│   ├── common.py               ← encryption keys
│   └── extras.py               ← extra backup features
│
├── generators/         (11 files, 1,975 LOC)
│   └── dockerfile.py, ci_*, terraform_*, docker_compose, k8s_manifests, etc.
│
├── wizard/             (9 files, 2,753 LOC)
│   ├── detect.py               ← environment detection for wizard
│   ├── setup_*.py              ← 5 setup handlers (git, ci, dns, infra, docker)
│   └── helpers.py              ← wizard utilities
│
├── wsl_transport/      (8 files, 3,154 LOC)
│   ├── router.py               ← transport routing (probing)
│   ├── tunnel_backends.py      ← tunnel management
│   ├── ps_bridge.py            ← PowerShell bridge
│   ├── environment.py          ← WSL environment detection
│   └── network.py              ← network resolution
│
├── chrome/             (5 files, 1,793 LOC)
│   ├── launcher.py             ← Chrome launch/detection
│   ├── profiles.py             ← profile management
│   └── detection.py            ← Chrome binary detection
│
├── terraform/          (4 files, 1,459 LOC)
├── testing/            (3 files, 854 LOC)
├── changelog/          (3 files, 1,081 LOC)
├── trace/              (3 files, 833 LOC)
│   └── trace_recorder.py       ← EventBus listener → .state/traces/
├── dns/                (2 files, 569 LOC)
├── ci/                 (3 files, 1,163 LOC)
├── packages_svc/       (3 files, 804 LOC)
├── metrics/            (2 files, 507 LOC)
│   └── ops.py                  ← health metrics (mtime-cached via devops cache)
├── quality/            (2 files, 538 LOC)
├── docs_svc/           (3 files, 697 LOC)
├── env/                (3 files, 685 LOC)
├── secrets/            (4 files, 937 LOC)
├── pages/              (8 files, 2,387 LOC)
│   └── pipeline_scanner.py     ← CI pipeline scanning
│
├── ── Standalone services ──────────────────────
├── project_index.py    (677 LOC) ← background file/symbol/peek index
├── project_probes.py   (485 LOC) ← 9 probes (git, github, docker, cicd, k8s, terraform, pages, dns, project)
├── peek.py             (1,081 LOC) ← reference scanning & resolution
├── smart_folders.py    (303 LOC) ← smart folder discovery & resolution
├── smart_folder_peek.py (423 LOC) ← smart folder peek enrichment
├── detection.py        (300 LOC) ← stack detection (ProjectInfo singleton)
├── staleness_watcher.py (124 LOC) ← 5s mtime polling → state:stale
├── event_bus.py        (361 LOC) ← pub/sub singleton (SSE backbone)
├── run_tracker.py      (470 LOC) ← SSE run log → .state/runs.jsonl
├── audit_staging.py    (333 LOC) ← async audit queue → .state/pending_audits.json
├── error_log.py        (276 LOC) ← error log → .state/error_log.ndjson
├── notifications.py    (319 LOC) ← notification system → .state/notifications.json
├── server_settings.py  (269 LOC) ← runtime settings → .state/server_settings.json
├── server_lifecycle.py (556 LOC) ← server startup/shutdown
├── config_ops.py       (281 LOC) ← project.yml + devops_prefs
├── dev_scenarios.py    (902 LOC) ← dev/debug test scenarios
├── dev_overrides.py    (68 LOC) ← system profile overrides
├── identity.py         (90 LOC) ← git user, project owners
├── md_transforms.py    (194 LOC) ← markdown rendering
├── stream_subprocess.py (149 LOC) ← subprocess streaming (SSE)
├── terminal_ops.py     (332 LOC) ← terminal detection & ops
└── tool_requirements.py (45 LOC) ← tool requirement checking
```

### B. Persistence Layer — `.state/` Directory

```
.state/
├── devops_cache.json          1.2 MB   ← DevOps card data (mtime-based)
├── posture_cache.json         12 KB    ← Posture pillars (TTL-based) [NEW]
├── project_index.json         1.5 MB   ← File/symbol/peek index (mtime-based)
│
├── devops_prefs.json          537 B    ← Card visibility preferences
├── server_settings.json       105 B    ← Runtime settings (theme, dev mode)
├── current.json               1.6 KB   ← Current session/state
├── wsl_channel.json           123 B    ← WSL channel state
│
├── audit_scores.json          5 KB     ← Health scores per domain
├── audit_activity.json        70 KB    ← User activity timeline
├── pending_audits.json        1.3 MB   ← Queued audit recomputations
│
├── notifications.json         23 KB    ← Notification history
├── error_log.ndjson           4 KB     ← Structured error log
├── runs.jsonl                 77 KB    ← SSE run history
├── server.pid                 11 B     ← PID file
│
├── install_plans/             30 files ← Tool install/update plan state
│   └── {uuid}.json
│
├── cdp-tests/                          ← CDP test data
│   ├── suites/                4 files  ← Test suite definitions
│   ├── results/               ~40 files ← Test run results
│   └── screenshots/           ~55 files ← Test screenshots (.png)
│
├── cdp-plans/                          ← CDP plan data
│   ├── plans/                          ← Execution plans
│   └── results/                        ← Plan results
│
├── traces/                             ← Event trace recordings
│   └── *.json
├── traces_hidden.json         35 B     ← Hidden trace IDs
│
└── logs/
    └── web.{timestamp}.log    ← Rotated server logs
```

### C. Cache Systems (4 independent caches)

| System | File | Invalidation | Scope | TTL Model |
|--------|------|-------------|-------|-----------|
| **DevOps Cache** | `devops/cache.py` | mtime-based via `_WATCH_PATHS` | 30+ card keys | File mtime > cache mtime |
| **Posture Cache** | `system_posture/cache.py` | TTL-based per key | 6 keys | 0s–5min–∞ per key |
| **Project Index** | `project_index.py` | mtime signature | 4 maps | 60s rebuild check |
| **Frontend Cache** | `_cache.html` | sessionStorage TTL | card + wizard keys | 10 min client-side |

### D. FS Watch Systems (3 independent watchers)

| Watcher | File | Method | Interval | Publishes |
|---------|------|--------|----------|-----------|
| **Staleness Watcher** | `staleness_watcher.py` | mtime polling of `_WATCH_PATHS` | 5s | `state:stale` via EventBus |
| **Project Index Refresh** | `project_index.py` `_refresh_loop` | mtime signature of sentinel paths | 60s | `index:rebuilt` via EventBus |
| **DevOps Cache mtime** | `devops/cache.py` `get_cached()` | inline mtime check on read | on-demand | `cache:hit` / `cache:miss` via EventBus |

### E. Detection / Probe Systems (scattered, no unification)

| System | File | What it detects |
|--------|------|----------------|
| **Stack Detection** | `detection.py` | Languages, frameworks, modules (ProjectInfo singleton) |
| **Project Probes** | `project_probes.py` | 9 probes: git, github, docker, cicd, k8s, terraform, pages, dns, project |
| **Wizard Detection** | `wizard/detect.py` | Environment detection for initial setup |
| **K8s Detection** | `k8s/detect.py` | kubectl, helm, cluster status |
| **K8s Wizard Detection** | `k8s/wizard_detect.py` | K8s env for wizard |
| **Docker Detection** | `docker/detect.py` | Docker daemon, compose, images |
| **Tool Environment** | `tool_install/detection/environment.py` | Sandbox, NVM, CPU features |
| **Tool Network** | `tool_install/detection/network.py` | Proxy detection |
| **Tool Hardware** | `tool_install/detection/hardware.py` | GPU, kernel, build toolchain |
| **Chrome Detection** | `chrome/detection.py` | Chrome binary, profiles |
| **Pages Detection** | `pages/discovery.py` | Pages builder, segments |
| **Artifact Detection** | `artifacts/discovery.py` | Build targets, Makefile evolution |
| **Content Detection** | `content/listing.py` | Content folders |
| **Security Scan** | `security/scan.py` | Secret scanning, sensitive files |
| **Git Auth Detection** | `git/auth.py` | Remote type, SSH keys |
| **GitHub Auth** | `git/gh_auth.py` | Platform capabilities |
| **WSL Environment** | `wsl_transport/environment.py` | WSL state and capabilities |
| **Terminal Detection** | `terminal_ops.py` | Terminal type |
| **Tool Lifecycle** | `system_posture/ranking.py` | OS + tool lifecycle JSON data |
| **Posture Platform** | `system_posture/scanners/platform.py` | OS, kernel, glibc, WSL, arch |
| **Posture Toolchain** | `system_posture/scanners/toolchain.py` | Tool versions vs lifecycle |

### F. EventBus Integration Map

**Publishers** (18 services → EventBus):
```
devops/cache.py          → cache:computing, cache:done, cache:hit, cache:miss
staleness_watcher.py     → state:stale
project_index.py         → index:building, index:rebuilt, index:error
run_tracker.py           → run:start, run:done
error_log.py             → error:logged
notifications.py         → notify:new
server_lifecycle.py      → sys:starting, sys:ready
chat/chat_ops.py         → chat:sync, chat:message
ledger/ledger_ops.py     → ledger:saved, ledger:deleted
ledger/worktree.py       → ledger:worktree
git/gh_api.py            → github:api
scripts/executor.py      → script:start, script:done
scripts/plan_executor.py → plan:start, plan:step, plan:done
scripts/registry.py      → scripts:discovered
cdp_test/recorder.py     → cdp:record:*
stream_subprocess.py     → subprocess:output (SSE streaming)
trace/trace_recorder.py  → (listens to ALL events → .state/traces/)
```

**Subscribers** (via SSE `/api/events`):
```
_event_stream.html       → main SSE client, dispatches to handlers
_batch_prefetch.html     → bulk card prefetch
audit/_init.html         → audit scan events
devops/_init.html        → devops card update events
integrations/_init.html  → integration card events
_notifications.html      → notification events
auth/_git_auth.html      → git auth state events
integrations/_pages_sse.html  → pages build events
integrations/_artifacts_sse.html → artifact build events
integrations/_scripts_run.html → script run events
integrations/_plans.html → plan execution events
```

### G. Frontend Cache & State Systems

```
Client-side caching (_cache.html):
├── Card cache (sessionStorage)
│   ├── prefix: _cc:
│   ├── TTL: 10 minutes
│   ├── cascade rules: git→[github,docker,ci,pages], docker→[ci,k8s], etc.
│   ├── cardCached(), cardStore(), cardInvalidate(), cardRefresh()
│   └── cardLoad() → check cache → API fetch → store
│
├── Wizard cache (sessionStorage)
│   ├── prefix: _wz:
│   ├── TTL: 10 minutes
│   └── wizCached(), wizStore(), wizInvalidate()
│
├── Audit scan trigger
│   ├── _triggerAuditScanForCard() → POST /api/audit/scan
│   └── _waitForScanAndReload() → SSE listener for audit:done
│
└── Age display: _tickCardAges() every 5s

Frontend globals (_system_posture.html):
├── _pollTimer          ← posture polling timer
├── _lastPosture        ← last posture data
├── postureRescan()     ← full rescan
├── postureUpdateTool() ← single tool update
└── openPostureModal()  ← posture detail view

Frontend globals (_ops_modal.html):
├── window._remState    ← remediation state
├── window._remExecute  ← execute remediation
├── window._depsInstallPkgs ← dependency packages
├── window._choiceModalData ← choice modal data
├── _pendingPlansCache  ← cached pending plans
└── streamSSE()         ← SSE streaming for tool operations

Frontend globals (_auth_modal.html):
├── _opsPollingTimer    ← OAuth polling timer
├── _opsDeviceSession   ← OAuth device flow session
└── window._opsAuthConfig ← auth configuration
```

### H. Route Layer (40 blueprints)

```
src/ui/web/routes/
├── api/batch.py         ← bulk operations endpoint
├── artifacts/           ← build/publish routes
├── audit/               ← audit scan, scores, tool execution, remediation
├── backup/              ← backup/restore routes
├── cdp_test/            ← CDP test management
├── changelog.py         ← changelog routes
├── chat/                ← chat CRUD, sync
├── ci/                  ← CI/CD status
├── config/              ← project.yml, prefs, detection
├── content/             ← content vault CRUD
├── dev/                 ← dev tools, scenarios
├── devops/              ← devops card data
├── dns/                 ← DNS/CDN setup
├── docker/              ← Docker status, compose
├── docs/                ← documentation generation
├── events/              ← SSE event stream endpoint
├── git_auth/            ← git/SSH/GitHub auth
├── infra/               ← infrastructure detection
├── integrations/        ← integration cards
├── k8s/                 ← Kubernetes management
├── metrics/             ← health metrics
├── notifications/       ← notification CRUD
├── packages/            ← package management
├── pages/               ← Pages site management
├── plans/               ← execution plans
├── posture.py           ← system posture
├── project/             ← project info
├── quality/             ← code quality
├── scripts/             ← script management
├── secrets/             ← secrets/vault
├── security_scan/       ← security scanning
├── server/              ← server management
├── smart_folders/       ← smart folder resolution
├── tab_mesh/            ← tab mesh (multi-tab sync)
├── terraform/           ← Terraform management
├── testing/             ← test running
├── trace/               ← event trace management
└── vault/               ← content vault
```

---

## Connectivity Analysis — Who talks to Whom

### Current: Everything is isolated

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                            FRONTEND (128 JS files, 72K LOC)                 │
│                                                                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐           │
│  │Card Cache│ │Wiz Cache │ │Posture   │ │SSE Stream│ │Various  │           │
│  │(session) │ │(session) │ │Polling   │ │Dispatch  │ │Globals  │           │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬────┘           │
│       │             │            │             │            │                │
└───────┼─────────────┼────────────┼─────────────┼────────────┼────────────────┘
        │             │            │             │            │
  ══════╪═════════════╪════════════╪═════════════╪════════════╪═══════════════
        │             │            │             │            │
┌───────┼─────────────┼────────────┼─────────────┼────────────┼────────────────┐
│       ▼             ▼            ▼             ▼            ▼                │
│  40 Flask Blueprints (routes layer) ←──── each calls its service directly   │
│       │             │            │                                           │
└───────┼─────────────┼────────────┼──────────────────────────────────────────┘
        │             │            │
        ▼             ▼            ▼
┌──────────────┐ ┌──────────┐ ┌───────────┐
│ DevOps Cache │ │ Posture  │ │ Project   │   ← 3 ISOLATED caches
│ (mtime)      │ │ Cache    │ │ Index     │      no cross-talk
│              │ │ (TTL)    │ │ (mtime)   │
│ 30+ card keys│ │ 6 keys   │ │ 4 maps    │
└──────┬───────┘ └────┬─────┘ └─────┬─────┘
       │              │             │
       ▼              ▼             ▼
┌──────────────────────────────────────────┐
│  21+ Detection/Probe/Scan systems         │  ← each runs independently
│  (detect_*, probe_*, scan_*)              │     no shared results
│  each does its own subprocess calls,      │     no shared cache
│  file reads, and version checks           │
└──────────────────────────────────────────┘
       │              │             │
       ▼              ▼             ▼
┌──────────────────────────────────────────┐
│         FILESYSTEM + .state/ dir          │  ← source of truth
│         (project files, config, state)    │
└──────────────────────────────────────────┘
       │
       ▼
┌──────────────────┐     ┌────────────────┐
│ Staleness Watcher │────►│   EventBus     │  ← fire & forget
│ (5s poll)         │     │  (pub/sub)     │     no feedback loop
└──────────────────┘     └────────┬───────┘
                                  │
                           SSE → frontend
```

### The Gaps — Complete List

```
 1. NO MEDIATOR
    4 cache systems, 21+ detectors, 9 probes — all isolated.
    Each route handler manually calls the right service.
    No central "ask me anything" interface.

 2. NO UNIFIED QUERY
    "What's the docker status?" requires knowing to call:
    - devops cache for card data
    - posture cache for tool version
    - project_probes for docker detection
    - docker/detect for daemon status
    - project_index for Dockerfile locations
    These are 5 different calls with 5 different APIs.

 3. NO DELTA PROTOCOL
    Every refresh is a full re-fetch. state:stale fires but the
    frontend response is "re-fetch everything for that card."
    No "here's what changed since seq=N" diffing.

 4. NO TREE TAXONOMY
    Keys are flat strings across different naming conventions:
    - DevOps: "docker", "testing", "audit:scores:enriched"
    - Posture: "toolchain", "platform", "summary"
    - Index: file_map, symbol_map, peek_results (not even keys)
    - Frontend: "_cc:docker", "_wz:k8s-detect"
    No unified namespace. No hierarchy.

 5. NO SHARED DETECTION
    probe_docker() in project_probes.py runs `docker info`.
    detect.py in docker/ runs `docker info` again.
    k8s/detect.py runs `kubectl version`.
    system_posture/scanners/toolchain.py runs `kubectl version` again.
    tool_install/detection/environment.py runs its own detections.
    The SAME subprocess calls run multiple times across services.

 6. NO LOAD BALANCING
    Heavy scans (toolchain ~12s, audit ~8s, index build ~3s) run
    synchronously. No priority queue, no parallel scanning, no
    "scan cheap pillars first, return partial results."

 7. NO CASCADE GRAPH
    DevOps cache cascade is hardcoded:
      frontend: _CASCADE = {git→[github,docker,ci,pages], docker→[ci,k8s]}
      backend: AUDIT_KEYS set, explicit invalidate() calls
    Posture cascade is imperative in orchestrator.py.
    No declarative dependency graph.

 8. NO CROSS-CACHE AWARENESS
    When a tool is updated:
    - posture cache for that tool's pillar invalidates
    - devops cache for "tools" invalidates
    - project_index doesn't know
    - frontend card cache doesn't know until next poll
    - audit scores don't know until next scan
    No event saying "go updated to 1.24" that all systems hear.

 9. NO DIAGNOSTIC SURFACE
    devops cache has _publish_event for cache:hit/miss.
    posture cache has no observability.
    project_index has basic logging.
    No unified diagnostic view of "show me all caches, ages, hit rates."

10. DUPLICATE MTIME LOGIC
    _max_mtime() exists in devops/cache.py AND project_index.py
    (nearly identical implementations). _walk_max_mtime() is
    duplicated. _WALK_SKIP sets are duplicated.

11. NO PERSISTENCE STORY FOR DETECTION
    21+ detection functions run subprocess calls (docker info,
    kubectl version, etc.) every time they're called. Results
    are not cached across any of these systems. The posture
    scanner caches toolchain results (5 min TTL), but the
    detection layer underneath has no caching at all.
```

---

## The Vision — QueryMediator Architecture

### Core Principle

**One hub to rule them all.** The mediator sits between all data
consumers (routes, frontend, background jobs) and all data producers
(caches, indexes, scanners, fs watchers). No consumer ever talks
directly to a cache or index. The mediator decides HOW to fulfill
a request — cache hit, index lookup, fresh computation, or cascade.

### Trilateral Architecture

```
                         ┌──────────────────┐
                         │     FRONTEND      │  (upstream consumer)
                         │                   │  receives, requests,
                         │   poll / SSE      │  manual refresh
                         └────────┬──────────┘
                                  │
                    ══════════════╪══════════════════
                    ║     API Layer (40 routes)     ║
                    ══════════════╪══════════════════
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
                    │      QUERY MEDIATOR        │  ← THE HUB
                    │                           │
                    │  • Unified query API       │
                    │  • Cache negotiation        │
                    │    (TTL, mtime, or both)    │
                    │  • Index resolution         │
                    │  • Detection dedup          │
                    │  • Delta computation        │
                    │  • Cascade management       │
                    │    (declarative graph)      │
                    │  • Priority scheduling      │
                    │  • Diagnostic view          │
                    │                           │
                    └──┬──────┬──────┬──────┬───┘
                       │      │      │      │
             ┌─────────┤      │      │      ├───────────┐
             │         │      │      │      │           │
             ▼         ▼      ▼      ▼      ▼           ▼
       ┌──────────┐ ┌──────┐ ┌────────┐ ┌──────────┐ ┌──────────┐
       │  CACHE   │ │INDEX │ │DETECTOR│ │ SCANNER  │ │EVENT BUS │
       │  LAYER   │ │LAYER │ │ LAYER  │ │  LAYER   │ │ (pub/sub)│
       ├──────────┤ ├──────┤ ├────────┤ ├──────────┤ ├──────────┤
       │ devops   │ │file  │ │21+     │ │posture   │ │broadcast │
       │ posture  │ │symbol│ │detect/ │ │audit     │ │subscribe │
       │ audit    │ │peek  │ │probe   │ │security  │ │replay    │
       │ scripts  │ │dir   │ │funcs   │ │pipeline  │ │snapshot  │
       │ cdp-test │ │      │ │(dedup) │ │artifact  │ │          │
       │ (TTL/    │ │      │ │        │ │          │ │          │
       │  mtime)  │ │      │ │        │ │          │ │          │
       └─────┬────┘ └──┬───┘ └───┬────┘ └─────┬───┘ └─────┬────┘
             │         │         │             │           │
             ▼         ▼         ▼             ▼           ▼
       ┌────────────────────────────────────────────────────────┐
       │            FILESYSTEM + .state/ + subprocesses         │
       │      (source of truth: files, configs, tool output)    │
       └────────────────────────────────────────────────────────┘
```

### The Mediator's Vocabulary

```python
# Conceptual — NOT final API. Shows the shape of the interface.

class QueryMediator:
    """Central data hub — mediates between caches, indexes, and scanners."""

    # ── GET — read data (hierarchical path) ──────────────────────
    def get(self, path: str, **opts) -> Any:
        """
        path examples:
            "posture.toolchain"
            "posture.toolchain.items.go"
            "devops.docker"
            "devops.docker.detected"
            "index.files.README.md"
            "index.symbols.QueryMediator"
            "audit.scores.security"
            "detect.docker.daemon"
            "detect.k8s.cluster"
            "detect.tools.go.version"
            "scripts.all"
            "cdp.suites"

        opts:
            force=True         → bypass cache, force recompute
            max_age=30         → accept cached if < 30s old
            cascade_depth=2    → how deep to resolve dependencies
            explain=True       → return metadata about resolution path
            stale_ok=True      → return stale + refresh in background
        """

    # ── PUT — write/invalidate ───────────────────────────────────
    def put(self, path: str, data=None, **opts) -> dict:
        """
        opts:
            cascade=True       → invalidate dependents
            cascade_depth=-1   → infinite cascade  
            persist=True       → write to disk
            notify=True        → publish event on bus
        """

    # ── SUBSCRIBE — reactive updates ─────────────────────────────
    def subscribe(self, pattern: str, callback) -> str:
        """
        pattern: "posture.*", "devops.docker", "index.**", "detect.**"
        Returns subscription ID.
        """

    # ── DISPATCH — trigger background work ───────────────────────
    def dispatch(self, action: str, **params) -> dict:
        """
        "rescan.posture.toolchain"
        "rescan.posture.all"
        "rescan.audit.full"
        "rebuild.index"
        "flush.cache.devops"
        "flush.cache.all"
        "detect.all"

        Returns: {queued: True, eta_ms: 5000, ...}
        """

    # ── DIAG — diagnostics ───────────────────────────────────────
    def diag(self, path: str = "") -> dict:
        """
        Returns: ages, TTLs, hit rates, dependency graph,
                 pending computations, queue depth, detection results,
                 cache sizes, index stats, ...
        """
```

### The Tree Taxonomy

```
mediator
├── posture
│   ├── summary          (dict, 30s TTL)
│   ├── full             (SystemPosture, 60s TTL)
│   ├── platform         (PillarResult, ∞ TTL)
│   ├── toolchain        (PillarResult, 5min TTL)
│   │   └── items.{tool} (PostureItem — leaf level)
│   ├── project          (PillarResult, 60s TTL)
│   └── runtime          (PillarResult, 0s TTL — always fresh)
│
├── devops
│   ├── docker           (card data, mtime-based)
│   ├── k8s              (card data, mtime-based)
│   ├── security         (card data, mtime-based)
│   ├── testing          (card data, mtime-based)
│   ├── quality          (card data, mtime-based)
│   ├── packages         (card data, mtime-based)
│   ├── docs             (card data, mtime-based)
│   ├── env              (card data, mtime-based)
│   ├── terraform        (card data, mtime-based)
│   ├── dns              (card data, mtime-based)
│   └── prefs            (devops_prefs.json)
│
├── integrations
│   ├── git              (card data, mtime-based)
│   ├── github           (card data, mtime-based)
│   ├── ci               (card data, mtime-based)
│   ├── docker           (card data, mtime-based)
│   ├── k8s              (card data, mtime-based)
│   ├── terraform        (card data, mtime-based)
│   ├── pages            (card data, mtime-based)
│   └── scripts          (card data, mtime-based)
│
├── audit
│   ├── scores           (health scores)
│   ├── scores.enriched  (enriched scores + deep analysis)
│   ├── system           (system audit)
│   ├── deps             (dependency audit)
│   ├── structure        (project structure)
│   ├── clients          (client audit)
│   └── l2.*             (deep L2 analysis per domain)
│
├── index
│   ├── files            (file_map — name → paths)
│   ├── dirs             (dir_map — name → paths)
│   ├── symbols          (symbol_map — name → locations)
│   ├── peek             (pre-computed peek data)
│   └── meta             (file_count, build_time, last_built)
│
├── detect
│   ├── os               (OS, distro, kernel, glibc)
│   ├── arch             (CPU architecture, features)
│   ├── hardware         (GPU, kernel, build toolchain)
│   ├── network          (proxy, connectivity)
│   ├── sandbox          (container, VM, CI env)
│   ├── wsl              (WSL state and capabilities)
│   ├── terminal         (terminal type)
│   ├── chrome           (Chrome binary, profiles)
│   ├── docker           (daemon, compose, images)
│   ├── k8s              (kubectl, helm, cluster)
│   ├── git              (remote, SSH, HEAD)
│   ├── github           (API auth, capabilities)
│   ├── tools.{name}     (version, path for each tool)
│   ├── pages            (builder, segments)
│   ├── artifacts        (build targets, Makefile)
│   └── project          (stacks, languages, modules)
│
├── scripts
│   ├── all              (script registry)
│   ├── by_category.{c}  (filtered)
│   ├── plans            (execution plans)
│   └── runs             (run history)
│
├── content
│   ├── folders          (content folder listing)
│   ├── smart_folders    (smart folder definitions)
│   └── releases         (release status tracking)
│
├── cdp
│   ├── suites           (test suites)
│   ├── results          (test results)
│   └── active           (active recording/replay)
│
├── system
│   ├── event_bus        (pub/sub state, subscriber count)
│   ├── settings         (server settings)
│   ├── notifications    (notification history)
│   ├── errors           (error log)
│   ├── runs             (run tracker)
│   └── lifecycle        (server state)
│
└── vault
    ├── status           (locked/unlocked)
    └── secrets          (detected secret files)
```

### Dependency Graph (Cascade Rules)

```
Posture cascades:
  posture.platform   ──invalidates──→  posture.full ──→ posture.summary
  posture.toolchain  ──invalidates──→  posture.full ──→ posture.summary
  posture.project    ──invalidates──→  posture.full ──→ posture.summary
  posture.runtime    ──invalidates──→  posture.full ──→ posture.summary

DevOps cascades:
  devops.docker      ──notifies────→  audit.system, integrations.docker
  devops.k8s         ──notifies────→  audit.system, integrations.k8s
  devops.security    ──notifies────→  audit.scores

Detection feeds:
  detect.docker      ──feeds───────→  devops.docker, integrations.docker
  detect.k8s         ──feeds───────→  devops.k8s, integrations.k8s
  detect.tools.*     ──feeds───────→  posture.toolchain
  detect.project     ──feeds───────→  posture.project, audit.structure

Frontend cascades (client-side):
  git                ──invalidates──→  github, docker, ci, pages
  docker             ──invalidates──→  ci, k8s
  github             ──invalidates──→  ci
  pages              ──invalidates──→  dns

Index cascades:
  index.files        ──invalidates──→  index.peek
  index.symbols      ──invalidates──→  index.peek
```

---

## Implementation Order (Bottom-Up)

### Phase 0: Foundation — Tree Registry & Path Resolution
The skeleton. A `DataTree` class that registers paths, their types,
TTLs, dependency edges, and resolver functions. No behavior yet. Just
the map that the mediator will navigate.

### Phase 1: Detection Dedup — Shared Detection Layer
Wrap all 21+ detect/probe functions behind the mediator's `detect.*`
namespace. Cache detection results with appropriate TTLs (OS = ∞,
docker daemon = 30s, tool versions = 5min). This immediately eliminates
duplicate subprocess calls.

### Phase 2: Mediator Core — `get()` and `put()`
Wire the mediator to existing cache systems. `mediator.get("devops.docker")`
calls `get_cached()`. `mediator.get("posture.toolchain")` calls
`get_or_compute()`. Just routing, but unified.

### Phase 3: Cascade Engine
Replace imperative cascade code with declarative dependency graph.
`mediator.put("posture.toolchain", cascade=True)` walks edges automatically.
Unify frontend and backend cascade rules into one graph.

### Phase 4: Delta & Subscription
Integrate with EventBus. Publish diffs, not just "stale." Frontend
subscribes to patterns and patches local state incrementally.

### Phase 5: Priority Scheduling & Load Balancing
Background job queue. Parallel scanning. "Cheap first, expensive deferred."
Partial results while heavy scans are in progress.

### Phase 6: Diagnostic View
Debug tab in web UI showing the full tree, ages, TTLs, dependency graph,
hit/miss rates, pending computations. Toggle on/off from Settings.

---

## Design Constraints

1. **Backward compatible.** Existing routes keep working. Migration route by route.
2. **No performance regression.** Mediator is a thin routing layer.
3. **File-backed.** Every persistent value survives restart.
4. **Thread-safe.** Per-key locking pattern.
5. **Observable.** Every operation publishes to EventBus.
6. **126K LOC of existing code.** The mediator wraps, it doesn't rewrite.

---

## Target Outcome

| Metric | Before | After |
|--------|--------|-------|
| Cold start (page load after restart) | 12–15s | <1s (file-backed) |
| Tool update → badge refresh | 10s (full rescan) | <0.5s (targeted) |
| Duplicate detection calls per page | 5–10 | 1 (deduped) |
| Page refresh data fetched | 100% refetch | Delta-only patches |
| Cross-cache awareness | None | Full cascade graph |
| Diagnostic capability | Basic logging | Full tree view |

---

## Open Questions

1. **Where does the mediator live?** — `src/core/services/mediator/`?
   Should it absorb the EventBus, or sit beside it?

2. **Migration strategy** — route-by-route, or big bang?

3. **Detection TTLs** — what's the right TTL for each detection type?
   OS = ∞, tool versions = 5min, docker daemon = 30s?

4. **Partial results** — stale-while-revalidate pattern for TTL-expired
   entries, or block until fresh?

5. **Frontend integration** — does the mediator expose its own API
   endpoints, or do existing routes become thinner wrappers?

6. **Persistence** — one aggregated `.state/mediator.json` or keep
   per-domain files?
