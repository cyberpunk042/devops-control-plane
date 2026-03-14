# Product Evolution Ideas
> Living document — discussed March 14, 2026

---

## 1. Dependency-Aware Package Management with Live Observability

**Current state:**
The tool installer works from tool recipes (94 tools). It knows how to install individual tools. But it doesn't read the project's own dependency files to understand what the project actually needs installed.

**The evolution — what it does:**

### Dependency file detection
Scan the project for dependency manifests:
- `requirements.txt`, `pyproject.toml`, `Pipfile` → Python
- `package.json`, `yarn.lock`, `pnpm-lock.yaml` → Node
- `go.mod` → Go
- `Gemfile` → Ruby
- `Cargo.toml` → Rust
- `composer.json` → PHP
- etc.

### Tree-select operation scope
Operations (install / update / rollback) work at three levels — user picks the scope:

```
[Global]  ← install/update/rollback everything across all modules
  ├── [Python]  ← requirements.txt, pyproject.toml → pip install -r ...
  │     ├── requests 2.31.0
  │     ├── flask 3.0.1
  │     └── ...
  ├── [Node]  ← package.json → npm install
  │     ├── react 18.2.0
  │     └── ...
  └── [Go]  ← go.mod → go mod download
        └── ...
```

- Select **Global** → runs all groups in one operation
- Select **a group** → runs only that ecosystem's native command
- Select **a package** → installs/updates/rollbacks that one (current behavior)

All levels support install, update, and rollback.

### Grouped installs via native commands
Don't install packages one-by-one through recipes. Use the right native command for the group:
- `pip install -r requirements.txt` (not 40 individual pip calls)
- `npm install` (not 60 individual npm calls)
- These are batched, native, correct — exactly how the ecosystem expects them

### Live observability via SSE
Stream the installation output in real-time:
- Per-package progress as it installs
- Live log feed (same SSE infrastructure already in the platform)
- Visual progress tracker in the web panel

### Warning & error detection
During the install stream, detect:
- Version conflicts
- Missing system dependencies
- Deprecated packages
- Failed installs

### Remediation surface
When warnings/errors are detected, surface them through the existing remediation system:
- Multiple remediation options per issue (not just one recipe)
- Multi-layer remediation: simple fix → alternative approach → nuclear option
- Not recipe-only — the remediation system understands context
- The remediation system already exists and can evolve to handle ecosystem-specific cases

**What this requires:**
- Dependency file scanner (new — detects manifests across all supported ecosystems)
- Native command executor with streaming output (SSE already exists)
- Error/warning parser per ecosystem (pip output ≠ npm output)
- Hook into existing remediation system for issue surfacing

**Key distinction from current tool_install:**
Current tool_install = "install this tool on your system"
This evolution = "install what YOUR PROJECT needs, the way your project's ecosystem expects it"

---

## 2. Nested Project Support (Project-in-Project)

**Current state:**
The platform is multi-module capable — it handles mono-repos and multiple stacks within a single solution. But the gap is nested ownership: a git repo inside a git repo, a sub-project that is itself a full project.

**The evolution:**
Proper nested project detection and scoping. When the platform encounters a sub-project, it should:
- Recognize it as an independent unit with its own lifecycle
- Offer to manage it independently OR as part of the parent
- Handle nested git remotes, separate dependency trees, independent health

**Scope note (from discussion):**
Not a huge gap — the multi-module foundation is solid. This is a targeted extension, not a rewrite.

---

## 3. Environment & Tool Lifecycle Ownership

**Current state:**
The tool installer is massive (94 tools, 26K LOC) — installs tools, detects versions, handles recipes. The posture system ranks tools (SUPPORTED → DEPRECATED). But these two systems don't yet act together.

**The evolution:**
Full lifecycle ownership — not just install, but:
- **Upgrade paths**: posture detects OUTDATED → platform offers upgrade plan
- **Deprecation handling**: tool marked DEPRECATED → platform surfaces migration path
- **Configuration drift**: tool installed but not configured correctly → platform detects and proposes fix
- **Rollback**: every lifecycle action is reversible with audit trail

**What this requires:**
- Connect posture rankings to the tool installer's action system
- Upgrade/migrate recipes alongside install recipes
- Lifecycle state tracked in the audit ledger

---

## 4. Changelog & Release Intelligence

**Current state:**
The platform has git history, GitHub releases, artifact generation, and an audit ledger. Changelog generation exists but is based primarily on commit messages.

**The evolution:**
Generate changelogs from real signals — not just commits, but what actually changed across the full project surface:
- Packages bumped (from dependency files)
- Config modified (from env/vault diff)
- Infra updated (Dockerfile, K8s manifests, Terraform)
- Secrets rotated (from vault audit trail)
- Tools upgraded (from posture/tool_install history)

Tie it to a release workflow: meaningful changelog → version bump → tag → publish — all from one action with full audit trail.

---

## 5. Multi-Environment Promotion Pipeline

**Current state:**
The platform manages `.env` configs across dev/staging/production and can switch between them. But there is no concept of *flow* — no controlled, audited way to promote state from one environment to the next.

**The evolution:**
A structured promotion pipeline:

```
dev  →  staging  →  production
```

### Filtered promotion
At promotion time, not everything travels:
- **Promote**: synced secrets, real config values, validated state
- **Strip**: dev-only flags (`DEBUG=true`, `DEV_MOCK_AUTH=true`), local overrides, mock keys, local DB URLs
- The platform already knows which keys belong to which tier — promotion uses that knowledge

### Diff before push
Before promotion lands, show exactly:
- What is being promoted (what changes in the target)
- What is being dropped (dev-only keys that don't travel)
- User approves before anything moves

### Gate (optional)
Require a health check or test pass before promotion completes.

### Rollback
Every promotion is reversible — restore target to its previous promoted state in one action.

**What this requires:**
- Promotion engine that reads env tier metadata (already exists in vault/secrets system)
- Diff view between source and target environment
- Promotion entry in the audit ledger (primitives already exist)
- Rollback via backup snapshots (backup system already exists)

**Key insight:** The backup system, vault, audit ledger, and env tier system already have all the primitives. This wires them into a deliberate, safe flow.

---

## 6. Project Timeline & Activity Intelligence

**Current state:**
The audit ledger, git history, CI runs, vault operations, and backup events all exist but live in separate domain views.

**The evolution:**
A unified timeline — every meaningful event across all domains in one chronological view.
- Filter by domain (git, vault, infra, packages, secrets...)
- Filter by environment
- See the story of the project, not just its current state

**Scope note:**
Not a prominent system — a side panel or dedicated tab you go to when you need to understand what happened. The ledger already captures everything. This is primarily a unified read surface with good filtering, not new infrastructure.

---

## 7. Security Posture as a First-Class Citizen

**Current state:**
Security is fragmented — audit (L0/L1/L2), security scanning, vault, and secrets detection all exist but in separate domains with no consolidated view.

**The evolution:**
One consolidated security posture view:
- Single score aggregated from all security signals
- One dashboard: open vulnerabilities, expired secrets, insecure configs, pending remediations
- Clear priority ranking of what to fix first
- Connects to the remediation system for acting on findings directly from the view

---

## 8. Stack Version Advisor & Annotated Decisions

**Current state:**
The platform detects stacks and their versions. The posture system ranks them (SUPPORTED → DEPRECATED). But the two don't connect into an actionable upgrade path, and there's no way to record *why* you're on a specific version.

**The evolution — two layers:**

### Layer 1 — Stack upgrade path at detection level
When a module's detected stack version is OUTDATED or DEPRECATED, surface the upgrade path directly at the module level:
- What changes in the project if you upgrade
- What the upgrade touches (dependencies, configs, Dockerfiles, CI)
- A scoped, guided migration — not just a warning

### Layer 2 — User-annotated version decisions
The user can attach a reason to their current version choice:
- "Staying on Node 18 — vendor SDK doesn't support 20 yet"
- "Python 3.9 — legacy deployment constraint until Q3"

That annotation becomes a **traceable, audited comment** on the stack state:
- Platform stops flagging it as an issue
- Reason is recorded in the audit ledger and visible in the timeline
- Surfaces in the stack view so the decision is never invisible

**Key insight:** The platform doesn't just push upgrades — it understands why you're where you are and respects documented decisions.

---

## 9. Project Readiness Score

**Current state:**
Health, security posture, audit, CI status, env completeness all exist as separate signals with no unified output.

**The evolution:**
A single readiness score per environment — not just health, but *readiness to ship*:
- "Your staging environment is 84% ready for production promotion"
- Breaks down exactly what's missing: no backup policy, 2 open CVEs, CI failing, missing prod secrets
- Actionable — each gap links directly to the thing that fixes it
- Natural companion to Evolution 5 (promotion pipeline) — before you promote, you see the score

---

## 10. Dependency Graph & Impact Analysis

**Current state:**
The platform detects stacks, modules, and dependencies but doesn't model their relationships.

**The evolution:**
Visualize the relationship web — which modules depend on which, what a change touches before you make it:
- "You're about to upgrade this shared library — here are the 4 modules it affects"
- Blast radius analysis before any upgrade or migration

**Relation to other evolutions:**
Directly complements Evolution 1 (dependency-aware package management) and Evolution 8 (stack version advisor) — both benefit from knowing the impact surface before acting.

---

## 11. Notification System — Signal Connection

**Current state:**
A notification system exists in the platform but is underutilized. The signals that should feed it (posture rankings, CVEs, vault rotation age, EOL timelines, health degradation) all exist but aren't connected.

**The evolution:**
Two tracks:

### Track 1 — Connect existing signals
Route the signals that matter into the notification system:
- Package CVEs detected
- Vault not rotated in N days
- Stack entering EOL within N days
- Health score drops below threshold
- Promotion pipeline gate failed

### Track 2 — Configurable digest
A curated, configurable summary — not noise:
- Daily / weekly digest option
- On-event notifications for critical signals only
- User controls what reaches them and at what threshold

**Key principle:** Not a new notification system — connect what's already there to the one that already exists.

---

## Notes from discussion

- Evolution 1 is the most ambitious — needs the mediator as backbone, requires careful UX design so it feels like a helpful layer not noise
- Evolution 2 is scoped and achievable — the foundation is there
- Evolution 3 is a natural extension of existing systems — posture + tool_install already know each other, they just don't act together yet
