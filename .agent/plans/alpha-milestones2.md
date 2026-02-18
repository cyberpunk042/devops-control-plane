# Alpha Milestones — Phase 2

> **Status:** Vision document — deep analysis, dependency-ordered.
> **Source of truth:** `TECHNOLOGY_SPEC.md` + `PROJECT_SCOPE.md`, not the current code.
> **Created:** 2026-02-17
> **Principle:** Infrastructure first, then features that consume it.

---

## Dependency Graph

```
Phase 1 — Infrastructure
  ├── 1A. Git-Native Ledger System (refs, branches, storage)
  │     └── 1B. SCP Chat (messages, threads, publish, encrypt)
  │           └── 1C. Session Tracing (recording → auto-messages)
  │
Phase 2 — Wizard + Integrations
  ├── 2A. Setup Wizard Side Panel (assistant, context-aware)
  │     └── 2B. Integrations Step Improvements
  │           └── 2C. Individual Integration Full Setups
  │                 └── 2D. New Integrations (systemd, Ansible, Salt,
  │                       Cloudflare, OpenAPI, Bruno, HashiCorp Vault, …)
  │
Phase 3 — Visualization
  └── 3A. Project Map (imbricated solution map)
```

**Rule:** Phase 1 is foundational. Phase 2 and 3 consume Phase 1 outputs.
Nothing in Phase 2/3 starts until its Phase 1 dependency is at least
minimally viable.

---

---

# PHASE 1 — INFRASTRUCTURE

---

## 1A. Git-Native Ledger System

### What This Is

A structured data layer on top of git that stores run artifacts, event logs,
and operational history — separate from the clean code history but living
in the same repository.

This is the **storage backbone** for everything else in Phase 1.

### Git Primitives

| Primitive | Ref | Purpose | Content |
|-----------|-----|---------|---------|
| **Code** | `refs/heads/main` | Clean commit history | Source code (unchanged) |
| **Ledger branch** | `refs/heads/scp-ledger` | Operational data (big) | `ledger/runs/`, `ledger/traces/` |
| **Run anchors** | `refs/tags/scp/run/<run_id>` | Stable handles to runs | Annotated tags pointing to code commits |

### Ledger Branch Design

The `scp-ledger` branch is an **orphan branch** — no shared history with
`main`. It stores operational artifacts that are too large or too frequent
for the main history.

```
scp-ledger (orphan)
└── ledger/
    ├── runs/
    │   ├── <run_id>/
    │   │   ├── run.json          # Run metadata (type, status, timing, user)
    │   │   ├── events.jsonl      # Fine-grained event stream
    │   │   └── artifacts/        # Any associated files (reports, diffs, etc.)
    │   └── ...
    └── traces/
        ├── <trace_id>/
        │   ├── trace.json        # Session trace (see 1C)
        │   └── summary.md        # Auto-generated human summary
        └── ...
```

### Run Anchors

Each "run" is a significant operation: a wizard completion, a deployment,
a vault export, a detection scan, etc.

```
Annotated tag: refs/tags/scp/run/<run_id>
  ├── Points to: the commit on main that was HEAD at run time
  ├── Tag message: JSON metadata
  │   {
  │     "run_id": "run_2026-02-17_204500",
  │     "type": "k8s:apply",
  │     "user": "jfortin",
  │     "status": "ok",
  │     "code_ref": "abc123",
  │     "ledger_ref": "ledger/runs/run_2026-02-17_204500/"
  │   }
  └── Queryable: `git tag -l 'scp/run/*'`
```

### What Exists Today

| Existing Component | Where | Relevance |
|-------------------|-------|-----------|
| Audit ledger | `.state/audit.ndjson` | Local-only, append-only — **this is the local precursor** |
| Git adapter | `src/adapters/vcs/` | Stub — needs real git plumbing (refs, notes, tags) |
| `git_ops.py` | `src/core/services/git_ops.py` | CLI wrappers for `git` — high-level, needs low-level primitives |
| `git_gh_ops.py` | `src/core/services/git_gh_ops.py` | GitHub-specific operations — PR, releases, etc. |
| Event bus | `src/core/services/event_bus.py` | In-process pub/sub — can trigger ledger writes |

### New Primitives Needed

| Primitive | Description |
|-----------|-------------|
| `git_refs.py` | Low-level ref management: create/read/list refs, tags, notes |
| `git_objects.py` | Blob/tree/commit creation for the orphan branch |
| `ledger_ops.py` | High-level: `create_run()`, `append_to_run()`, `list_runs()`, `get_run()` |
| Ledger service | Core service that wraps ledger_ops and integrates with event bus |

### Relationship to Existing Audit Log

```
.state/audit.ndjson (LOCAL, machine-generated, exhaustive, ephemeral)
        │
        │  can be promoted to ──→
        │
scp-ledger branch (GIT-HOSTED, structured, selective, permanent)
```

The local audit log continues to exist as-is. The ledger is a
**higher-tier persistence** — what gets promoted to git is a conscious
choice (automatic for runs, manual for other things).

---

## 1B. SCP Chat (Message System)

### What This Is

An **embedded messaging system** stored in git notes, attached to run
anchors. Human-authored (or trace-generated) messages that provide narrative
context around operations.

**Not a replacement** for the audit log. The audit log says _what happened_.
SCP Chat says _why it happened_ and _what it means_.

### Git Storage

```
refs/notes/scp-chat
  └── Notes attached to tag objects (run anchors)
      └── Each note: JSONL file (one message per line)
```

Why git notes?
- **Append-only** — each `git notes append` adds content without conflicts
- **Conflict-light** — notes are per-object, so concurrent writes to
  different runs don't conflict
- **Distributed** — push/pull with `git push origin refs/notes/scp-chat`
- **Invisible** — notes don't pollute the main history or the working tree

### Message Model

```json
{
  "id": "msg_01HXYZ...",
  "ts": "2026-02-17T20:45:00Z",
  "user": "jfortin",
  "thread_id": null,
  "text": "Deployed v1.2.3 to staging, all health checks passed.",
  "refs": ["@commit:abc123", "@env:staging", "@run:run_42"],
  "flags": {
    "publish": false,
    "encrypted": false
  },
  "trace_id": null,
  "source": "manual"
}
```

### Threads

Users can create **message threads** — a thread is a named conversation
anchored to a run (or free-floating).

```json
{
  "thread_id": "thread_staging-deploy-review",
  "title": "Staging Deploy Review",
  "created_at": "2026-02-17T20:45:00Z",
  "created_by": "jfortin",
  "anchor_run": "run_42",
  "tags": ["deployment", "staging"]
}
```

Messages with `thread_id` set belong to that thread. Messages with
`thread_id: null` are top-level (timeline) messages.

Thread listing is derived by scanning the JSONL — no separate index needed
(small data volumes). If performance becomes an issue, a thread index can
be cached in `.state/`.

### Publish Flag

Users can **flag a message for publish**. This means:

- The message is marked for inclusion in a public-facing view
- When pushed, published messages can be rendered via GitHub Pages
  (if the docs page integration is active)
- Unpublished messages remain git-hosted but not publicly rendered
- This enables a workflow: write internal notes first, then selectively
  publish what you want others to see

```
publish: false  →  private (visible only in DCP UI, stored in git)
publish: true   →  public-eligible (can be rendered on docs/pages)
```

### Encryption Flag

Users can **choose to encrypt** individual messages in the git notes.

- `encrypted: false` — plaintext JSONL, readable by anyone with repo access
- `encrypted: true` — the `text` field (and optionally `refs`) is encrypted
  using the DCP vault key (AES-256-GCM, same as content vault)
- Encrypted messages can only be read when the vault is unlocked
- This allows sensitive operational context (deployment decisions, incident
  notes) to live in git without being exposed

```json
{
  "id": "msg_02...",
  "encrypted": true,
  "text": "ENC:v1:base64...",
  "refs": ["ENC:v1:base64..."],
  "flags": { "publish": false, "encrypted": true }
}
```

### Rich `@`-Referencing

The UI provides `@` detection and autocomplete, branching into sub-categories:

```
@  → top-level categories:
  ├── @commit:     → branch into recent commits (sha, message preview)
  ├── @branch:     → branch into local/remote branches
  ├── @op:         → branch into recent audit operations
  ├── @audit:      → branch into audit scan results
  ├── @run:        → branch into run anchors
  ├── @release:    → branch into GitHub releases → sub-branch into assets
  ├── @docs:       → branch into docs pages (unencrypted, linkable)
  ├── @file:       → branch into project files → optional #L10-L25 range
  ├── @media:      → branch into content vault media
  ├── @integration: → branch into integrations → sub-branch into features
  ├── @stack:      → branch into detected stacks (recursive)
  ├── @module:     → branch into project modules
  ├── @env:        → branch into environment variables (masked if secret)
  ├── @secret:     → branch into vault secrets (always masked, ref only)
  ├── @thread:     → branch into existing threads
  └── @trace:      → branch into session traces
```

Each `@`-reference is stored as a structured string in the `refs` array and
rendered as a clickable link in the UI (navigating to the referenced entity).

### What Exists Today

| Existing Component | Relevance |
|-------------------|-----------|
| Content vault encryption | Same AES-256-GCM can encrypt chat messages |
| Event bus SSE | Real-time message delivery to the UI |
| Audit activity log | Can be surfaced in the chat timeline |
| Vault key management | Reusable for chat encryption |

### New Components Needed

| Component | Layer | Description |
|-----------|-------|-------------|
| `chat_ops.py` | Core service | CRUD for messages, threads; read/write git notes |
| `chat_crypto.py` | Core service | Encrypt/decrypt message fields using vault key |
| `chat_refs.py` | Core service | Parse, validate, resolve `@`-references |
| `chat_autocomplete.py` | Core service | Generate autocomplete candidates per `@`-category |
| `routes_chat.py` | Web routes | REST API for messages, threads, autocomplete |
| `_tab_chat.html` | Web partial | Chat UI (timeline, threads, composer with `@`) |
| `_chat.html` | Web script | JS logic for chat rendering, `@`-autocomplete |
| CLI `chat` group | CLI | `chat send`, `chat list`, `chat threads`, `chat push` |

### External Integration Path (Future)

Bidirectional sync with Slack/Discord/Teams:
- Post DCP messages → Slack channel (webhook or app)
- Receive Slack messages → store in SCP Chat (via Slack Events API)
- User profile mapping (DCP user ↔ Slack user)
- This is a **future thread**, not part of Phase 1

---

## 1C. Session Tracing

### What This Is

An opt-in **recording mode** in the web UI that captures every operation
during a window, then produces a structured trace and optionally generates
an auto-summary message for SCP Chat.

### Depends On

- **1A (Ledger)** — traces are stored on the ledger branch
- **1B (Chat)** — auto-summaries are posted as chat messages

### Recording Flow

```
1. User clicks "Start Recording" (toggle in UI toolbar / settings)
2. User optionally names the recording and picks a classification
3. Every action during the session is captured:
   - API calls (type, target, result, timing)
   - Wizard step transitions
   - Vault operations
   - Git operations
   - Detection/scan results
4. User clicks "Stop Recording"
5. System generates:
   a. Raw trace → saved to ledger branch (ledger/traces/<trace_id>/)
   b. Auto-summary → human-readable markdown recap of what was done
   c. Optionally: a chat message is composed (user can edit before sending)
6. Multiple recordings per session are allowed
```

### Trace Data Model

```json
{
  "trace_id": "trace_2026-02-17_204500",
  "name": "Staging deployment prep",
  "classification": "deployment",
  "started_at": "2026-02-17T20:45:00Z",
  "ended_at": "2026-02-17T21:15:00Z",
  "user": "jfortin",
  "code_ref": "abc123",
  "events": [
    {
      "seq": 1,
      "ts": "2026-02-17T20:45:12Z",
      "type": "vault:unlock",
      "target": "staging",
      "result": "ok",
      "duration_ms": 142
    },
    {
      "seq": 2,
      "ts": "2026-02-17T20:46:30Z",
      "type": "k8s:apply",
      "target": "deployment.yml",
      "result": "ok",
      "duration_ms": 3200,
      "detail": { "resources_applied": 3 }
    }
  ],
  "audit_refs": ["op_001", "op_002"],
  "auto_summary": "Unlocked staging vault. Applied 3 K8s resources. Committed changes."
}
```

### Auto-Summary Generation

The summary is generated from the trace events using a template-based
approach (not AI — deterministic):

```
For each event:
  "${verb} ${target}" where verb = type_to_verb_map[event.type]
Join with ". "
```

The user can edit the generated summary before posting it as a chat message.

### Integration Points

| System | How |
|--------|-----|
| Event bus | Trace recorder subscribes to all events during recording |
| Audit log | Trace events link to audit `operation_id`s for cross-reference |
| SCP Chat | Auto-summary becomes a chat message (user chooses thread, flags) |
| Ledger | Raw trace stored on `scp-ledger` branch |

### What Exists Today

| Existing Component | Relevance |
|-------------------|-----------|
| Event bus (`event_bus.py`) | Already captures all events — trace recorder = subscriber |
| Audit activity log (`devops_activity.py`) | Already has `_extract_summary()` — similar pattern |
| Devops cache events | Already published on the bus — trace can capture them |

### New Components Needed

| Component | Layer | Description |
|-----------|-------|-------------|
| `trace_recorder.py` | Core service | Start/stop recording, capture events, generate summary |
| `trace_ops.py` | Core service | Save/load traces to/from ledger branch |
| `routes_trace.py` | Web routes | Start/stop/list/get traces |
| UI recording toggle | Web JS | Toolbar button, recording indicator, stop + compose flow |

---

---

# PHASE 2 — WIZARD + INTEGRATIONS

> Phase 2 builds on Phase 1 outputs. The wizard assistant uses SCP Chat's
> message model for its guidance. Integration setups generate runs and can
> produce trace-backed chat messages.

---

## 2A. Setup Wizard Side Panel (Assistant)

### What This Is

A contextual side panel in the Setup Wizard tab that guides the user as
they work. Not a chatbot — a **scripted, state-aware assistant** that
reacts to what's happening.

### State Awareness

The assistant tracks:

```
{
  "current_step": "integrations",
  "current_integration": "kubernetes",
  "current_sub_step": "manifest-generation",
  "completed_steps": ["project", "environments", "secrets"],
  "pending_steps": ["integrations", "review"],
  "last_event": { "type": "k8s:detect", "result": "ok", "detail": {...} },
  "integration_progress": {
    "git": { "detect": true, "observe": true, "facilitate": false, "act": true },
    "kubernetes": { "detect": true, "observe": false, "facilitate": "in_progress", "act": false }
  }
}
```

### Message Types

| Type | When | Example |
|------|------|---------|
| **Welcome** | First visit to a step | "Welcome to the Integrations step. I see 3 integrations already detected..." |
| **Guidance** | Focus changes to a sub-area | "Kubernetes manifest generation will create Deployment, Service, and Ingress resources..." |
| **Reaction** | An action completes | "✅ Detection found 2 Helm charts. You can now generate values files..." |
| **Suggestion** | Gap detected | "You have Docker but no K8s manifests. Want me to generate them from your services?" |
| **Warning** | Potential issue | "⚠️ Your staging environment has 3 secrets that aren't in the vault yet." |

### Rendering

- Side panel on the right (collapsible)
- Messages appear in a scrollable timeline (like a chat, but one-directional)
- Messages can contain:
  - Markdown text
  - Action buttons ("Generate manifests", "Run detection")
  - Status badges
  - Links to other parts of the UI
- Template-driven (each state transition maps to a message template)

---

## 2B–2D. Integrations

> Each follows **Detect → Observe → Facilitate → Act** from `TECHNOLOGY_SPEC.md`.
> Chef is excluded for now.

### 2D.1 Systemd / journalctl

| Phase | What |
|-------|------|
| **Detect** | `.service` unit files, `systemctl` availability, `journalctl` availability |
| **Observe** | Service status (`systemctl status`), journal logs (`journalctl -u`), enabled/disabled state, boot status |
| **Facilitate** | Generate `.service` unit files from project config (ExecStart, User, WorkingDir, Restart, After, WantedBy) |
| **Act** | Enable/disable, start/stop/restart, view logs (follow + historical), reload daemon (`systemctl daemon-reload`) |

**Adapter needs:** Shell adapter (already exists) — all operations are CLI commands.
**Detection files:** `*.service`, `systemd/`, `/etc/systemd/system/` references in project.

### 2D.2 Ansible

| Phase | What |
|-------|------|
| **Detect** | `ansible.cfg`, `playbook.yml`/`playbooks/`, `inventory/` or `hosts`, `roles/`, `group_vars/`, `host_vars/`, `requirements.yml` (galaxy), `ansible/` directory |
| **Observe** | Inventory graph (`ansible-inventory --graph`), role list, playbook list, variable precedence overview |
| **Facilitate** | Generate playbook stubs from detected stacks, generate inventory from project environments, generate role scaffolding |
| **Act** | Run playbooks (`ansible-playbook`), check mode (`--check`), diff mode (`--diff`), lint (`ansible-lint`), galaxy install |

**Adapter needs:** Shell adapter.
**Version detection:** `ansible --version`.

### 2D.3 Salt

| Phase | What |
|-------|------|
| **Detect** | `salt/` directory, `top.sls`, `pillar/`, `states/`, `minion`/`master` config files, `Saltfile`, `salt-ssh/roster` |
| **Observe** | Minion status, grain data, pillar data, state tree overview |
| **Facilitate** | Generate state files from detected stacks, generate pillar data from project environments |
| **Act** | `state.apply`, `state.highstate`, `test=True` (dry run), `pillar.items`, `salt-ssh` for agentless |

**Adapter needs:** Shell adapter.
**Version detection:** `salt --version`, `salt-call --version`.

### 2D.4 Cloudflare — Workers + Tunnels

| Phase | What |
|-------|------|
| **Detect** | `wrangler.toml`, `wrangler.jsonc`, `cloudflared` config (`config.yml` or `~/.cloudflared/config.yml`), tunnel credential files |
| **Observe** | Worker list + deployment status, tunnel status (`cloudflared tunnel info`), route mappings, DNS records (via existing DNS/CDN card) |
| **Facilitate** | Generate `wrangler.toml` from project config, generate `cloudflared` tunnel config from service definitions (hostname → service mapping) |
| **Act** | Deploy worker (`wrangler deploy`), tail worker logs (`wrangler tail`), create tunnel, route tunnel, run tunnel (`cloudflared tunnel run`) |

**Adapter needs:** Shell adapter + wrangler/cloudflared CLI detection.
**Synergy:** Extends the existing DNS & CDN card — Cloudflare is already
detected as a CDN provider.

### 2D.5 Swagger / OpenAPI [3]

| Phase | What |
|-------|------|
| **Detect** | `openapi.yaml`/`.json`, `swagger.yaml`/`.json`, `*.openapi.yml`, files in `docs/api/`, `api/`, `specs/` — parse spec version (2.0 vs 3.x), endpoint count, schema count |
| **Observe** | Spec validity (schema validation), breaking changes vs. previous version, endpoint coverage, model completeness |
| **Facilitate** | Generate OpenAPI stub from detected routes (framework-aware: Flask routes, FastAPI endpoints, Express routers), suggest missing schemas |
| **Act** | Validate spec, serve Swagger UI / Redoc (local preview), diff versions, generate mock server, generate client SDKs |

**Adapter needs:** Shell adapter + spec parser (YAML/JSON).
**Synergy:** Feeds into the Bruno integration (collection generation from specs).
**Synergy:** Feeds into the Documentation card (API docs as a docs segment).

### 2D.6 Bruno (Git-Friendly API Client)

| Phase | What |
|-------|------|
| **Detect** | `bruno.json`, `*.bru` collection files, `collection/` directories, `environments/` within Bruno structure |
| **Observe** | Collection size, request count, environment configs, folder structure, schema coverage |
| **Facilitate** | Generate Bruno collections from OpenAPI specs (see 2D.5), generate environment files from DCP `.env` vault, generate request stubs from detected API routes |
| **Act** | Run collections (`bru run`), run specific folders/requests, export results, validate environment configs |

**Adapter needs:** Shell adapter + `bru` CLI detection.
**Synergy:** OpenAPI specs → Bruno collections (automated pipeline).
**Synergy:** DCP vault environments → Bruno environments (secret injection).

### 2D.7 HashiCorp Vault

| Phase | What |
|-------|------|
| **Detect** | `vault` CLI availability + version, `VAULT_ADDR` / `VAULT_TOKEN` env vars, Vault Agent configs (`vault-agent.hcl`), `.vault-token`, AppRole configs |
| **Observe** | Vault status (`vault status`), seal status, secret engine mounts, auth methods, policy list, token info + TTL |
| **Facilitate** | Generate Vault policies from project secret structure (module → path mapping), generate AppRole configs, suggest secret paths based on project modules/environments |
| **Act** | Read/write secrets, seal/unseal (if authorized), enable/disable secret engines, manage policies, token operations, agent management |

**Complement to DCP Vault:** DCP vault = local `.env` encryption. HashiCorp
Vault = centralized infrastructure secret management. The integration allows:
- **Push:** DCP vault keys → HashiCorp Vault paths
- **Pull:** HashiCorp Vault secrets → local `.env` for development
- **Sync status:** Show drift between local and central

### Additional Integration Candidates (Parking Lot)

| Integration | Category | Priority Signal |
|-------------|----------|----------------|
| ArgoCD / FluxCD | GitOps | Natural K8s extension |
| Nginx / Caddy / Traefik | Reverse Proxy | Common in Docker/K8s stacks |
| PostgreSQL / MySQL / Redis / MongoDB | Database | Already in docker-compose, just need observe/facilitate |
| S3 / MinIO | Object Storage | Content vault extension |
| Sentry / Datadog / New Relic | APM | Observe phase for production |
| RabbitMQ / Kafka | Message Queue | Common service dependency |
| Keycloak / Auth0 | Identity | Common service dependency |
| Renovate / Dependabot | Dep Updates | Package card extension |
| Pre-commit | Git Hooks | Git integration extension |
| Prometheus / Grafana | Monitoring | Already in DESIGN.md §7.1 |
| Taskfile / Just | Task Runners | Makefile complement |

---

---

# PHASE 3 — VISUALIZATION

---

## 3A. Project Map (Imbricated Solution Map)

### What This Is

An interactive **nested visual map** of the entire solution — not a file
tree, not a diagram. A "memory map" that shows the architecture with
drill-down detail at every level.

### Depends On

- Detection results (stacks, modules, versions)
- Audit L1/L2 analysis (imports, dependencies, structure classification)
- Integration status (D→O→F→A per integration)
- Wizard state (service definitions)
- Project map data from `project.yml`

### Structure (Levels)

```
Level 0: Solution
  │
  ├── Level 1: Domains (library, ops, docs, ...)
  │     │
  │     ├── Level 2: Modules (core, adapters, cli, web, ...)
  │     │     │
  │     │     ├── Level 3: Inner Layers
  │     │     │     ├── Models (Pydantic types)
  │     │     │     ├── Services (business logic)
  │     │     │     ├── Engine (execution loop)
  │     │     │     └── Use Cases (entry points)
  │     │     │
  │     │     ├── Level 3: Outer Layers
  │     │     │     ├── Routes / Endpoints (Flask blueprints, CLI commands)
  │     │     │     ├── Templates (Jinja2, UI partials)
  │     │     │     └── Static assets
  │     │     │
  │     │     ├── Level 3: Sidecars / Cross-Cutting
  │     │     │     ├── Reliability (circuit breaker, retry)
  │     │     │     ├── Observability (health, metrics, logging)
  │     │     │     ├── Security (vault, encryption)
  │     │     │     └── Persistence (state, audit)
  │     │     │
  │     │     └── Level 3: Wraps
  │     │           ├── Dockerfile
  │     │           ├── K8s manifest (Deployment, Service)
  │     │           ├── Helm chart
  │     │           └── CI workflow
  │     │
  │     └── Level 2: Frameworks & Stacks
  │           ├── Detected stack (Python 3.12, Flask 3.x, Click 8.x, ...)
  │           ├── Dependencies (categorized by audit L1)
  │           └── Version info
  │
  ├── Level 1: Integrations
  │     ├── Per-integration D→O→F→A coverage (visual progress)
  │     ├── Integration graph (dependencies between integrations)
  │     └── External links (repos, dashboards, CI)
  │
  ├── Level 1: Environments
  │     ├── Per-env config diff
  │     ├── Secret coverage (which keys exist in which env)
  │     └── Deployment targets
  │
  └── Level 1: Communication (Phase 1 outputs)
        ├── Recent runs (from ledger)
        ├── Active threads (from SCP Chat)
        └── Latest traces (from session tracing)
```

### Rendering Considerations

- **Not a graph library** — this is nested boxes/cards, not a node-edge graph
- Could be HTML/CSS with collapse/expand (like nested accordions with rich content)
- Or SVG with zoom levels (treemap-style)
- Must re-render on detection/state changes (event bus subscription)
- Could be a dedicated tab or a full-screen modal from Dashboard

---

---

# CROSS-CUTTING CONCERNS

## Data Flow

```
User action in UI
  │
  ├──→ Core service (business logic)
  │     ├──→ Adapter (side effect)
  │     ├──→ Audit log (.state/audit.ndjson)  [local, auto]
  │     └──→ Event bus (pub/sub)
  │           ├──→ SSE → Web UI (live update)
  │           ├──→ Session trace recorder (if recording)
  │           │     └──→ Ledger branch (on stop)
  │           │           └──→ SCP Chat (auto-summary, if user chooses)
  │           └──→ Cache invalidation
  │
  └──→ Wizard assistant (if in wizard, reacts to event)
```

## Impact on `TECHNOLOGY_SPEC.md`

New integrations (Thread 2D) must be added to the Technology Spec once
they reach implementation. Each gets:
- Section number
- Detection rules
- Capabilities
- D→O→F→A requirements
- Version source (if applicable)

## Impact on `PROJECT_SCOPE.md`

- Thread 1 adds a new capability pillar: **Communication & Traceability**
- Thread 2A modifies the Setup Wizard description
- Thread 2D adds rows to the integration matrix
- Thread 3A adds a new tab or modal to the web dashboard

---

*This document captures the vision for Phase 2 alpha milestones. Each
thread requires its own design pass before becoming a milestone. The
dependency graph determines implementation order.*
