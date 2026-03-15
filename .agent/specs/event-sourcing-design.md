# Event Sourcing System — Design Scaffold

## The Pattern

```
Event Sourcing + CQRS + Observer + Chain of Responsibility
```

Every operation → immutable Event → Event Store → Projections → UI

---

## The Event

```python
@dataclass
class Event:
    id: str                    # unique, monotonic
    ts: float                  # when it happened
    type: str                  # what happened (see Event Types below)
    correlation_id: str        # groups related events (the chain)
    causation_id: str | None   # what caused this event (parent event id)
    source: str                # who emitted (mediator, route, watcher, cli)
    path: str                  # what was affected (mediator path, route path)
    status: str                # ok, error, warning
    duration_ms: int           # how long it took
    summary: str               # human-readable one-liner
    detail: dict               # event-specific payload
    origin: str                # "system" or "user"
    actor: str                 # "scheduler", "user", "automation"
```

---

## Event Types — Every Case in the Program

### Index Watcher Events
```
index.cycle.started        — watcher detected file changes, cycle begins
index.cycle.completed      — all tiers done
index.node.computed        — single node computed (e.g., index.scan)
index.node.skipped         — node was fresh, not recomputed
index.node.failed          — node computation threw error
index.tier.started         — tier dispatch began (T1, T2, etc.)
index.tier.completed       — tier dispatch finished
```

### Mediator Events
```
mediator.computed          — resolver ran and produced data
mediator.cached            — cache hit, no recomputation
mediator.invalidated       — node cache busted (cascade)
mediator.persisted         — data written to disk shard
mediator.hydrated          — data loaded from disk on startup
```

### DevOps Detection Events
```
devops.docker.scanned      — docker state detected
devops.k8s.scanned         — k8s state detected
devops.terraform.scanned   — terraform state detected
devops.git.scanned         — git state detected
devops.ci.scanned          — CI state detected
devops.env.scanned         — environment state detected
devops.security.scanned    — security state detected
devops.packages.scanned    — package state detected
devops.quality.scanned     — quality state detected
devops.testing.scanned     — testing state detected
devops.dns.scanned         — DNS state detected
devops.docs.scanned        — docs state detected
```

### Audit Events
```
audit.l0.completed         — L0 fast scan done
audit.l1.completed         — L1 deep scan done
audit.l2.completed         — L2 analysis done (risks, quality, repo, structure)
audit.scores.computed      — scores calculated
audit.scores.enriched      — scores enriched with L2 data
audit.finding.detected     — new finding discovered
audit.finding.dismissed    — finding dismissed by user
audit.finding.resolved     — finding no longer present
```

### Posture Events
```
posture.toolchain.scanned  — 50+ tools probed
posture.platform.scanned   — OS/hardware detected
posture.project.assessed   — project health evaluated
posture.full.computed      — full posture assembled
posture.summary.computed   — score computed (e.g., 72/100)
```

### GitHub Events
```
github.pulls.fetched       — PR list refreshed
github.runs.fetched        — workflow runs refreshed
github.workflows.fetched   — workflow definitions refreshed
github.pr.opened           — PR created (derived from PR data)
github.pr.merged           — PR merged
github.pr.closed           — PR closed without merge
github.workflow.triggered  — workflow run started
github.workflow.completed  — workflow run finished
github.workflow.failed     — workflow run failed
```

### Catalog Events
```
catalog.tools.scanned      — available tools detected
catalog.builders.scanned   — page builders detected
catalog.scripts.scanned    — scripts discovered
catalog.pages.scanned      — page segments detected
```

### Vault Events
```
vault.unlocked             — vault decrypted
vault.locked               — vault encrypted
vault.key.added            — key added to .env
vault.key.updated          — key value changed
vault.key.deleted          — key removed
vault.key.moved            — key moved to section
vault.section.renamed      — section renamed
vault.synced               — secrets pushed to GitHub
vault.exported             — vault exported
vault.imported             — vault imported
vault.env.activated        — environment switched
vault.env.created          — new environment created
vault.auto_locked          — auto-lock triggered
```

### Content Events
```
content.encrypted          — file encrypted
content.decrypted          — file decrypted
content.uploaded           — file uploaded
content.deleted            — file deleted
content.folder.created     — folder created
content.saved              — file content saved
content.renamed            — file renamed
content.moved              — file moved
content.optimized          — media optimized
content.enc_key.set        — encryption key configured
```

### Pages Events
```
pages.segment.built        — single segment built
pages.all.built            — all segments built
pages.merged               — segments merged
pages.deployed             — deployed to gh-pages
pages.initialized          — pages config initialized
pages.segment.created      — segment added
pages.segment.updated      — segment config changed
pages.segment.deleted      — segment removed
pages.preview.started      — preview server started
pages.preview.stopped      — preview server stopped
```

### Docker Events
```
docker.built               — images built
docker.started             — compose services up
docker.stopped             — compose services down
docker.restarted           — compose services restarted
docker.pruned              — unused resources removed
docker.pulled              — image pulled
docker.executed            — command executed in container
docker.container.removed   — container removed
docker.image.removed       — image removed
```

### K8s Events
```
k8s.applied                — manifests applied
k8s.deleted                — resource deleted
k8s.scaled                 — deployment scaled
k8s.helm.installed         — chart installed
k8s.helm.upgraded          — release upgraded
k8s.helm.templated         — templates rendered
k8s.manifests.generated    — manifests generated
```

### Terraform Events
```
terraform.planned          — plan generated
terraform.initialized      — terraform init
terraform.applied          — plan applied
terraform.destroyed        — resources destroyed
terraform.validated        — config validated
terraform.formatted        — config formatted
terraform.workspace.switched — workspace changed
```

### Backup Events
```
backup.created             — backup archive created
backup.restored            — backup restored
backup.imported            — backup imported
backup.deleted             — backup deleted
backup.encrypted           — backup encrypted
backup.decrypted           — backup decrypted
backup.uploaded            — uploaded to GitHub Release
```

### Git Events (user operations, not git log)
```
git.committed              — user committed changes
git.pushed                 — pushed to remote
git.pulled                 — pulled from remote
git.stashed                — stash created
git.stash.popped           — stash applied
git.remote.added           — remote added
git.remote.removed         — remote removed
```

### CI Events
```
ci.workflow.dispatched     — GitHub Actions workflow triggered
ci.workflow.generated      — CI workflow file generated
```

### Quality/Testing Events
```
quality.validated          — quality check ran
quality.linted             — linter ran
quality.formatted          — formatter ran
testing.ran                — test suite executed
testing.coverage           — coverage report generated
```

### Security Events
```
security.scanned           — security scan ran
security.finding.dismissed — finding dismissed
security.finding.undismissed — dismissal reverted
```

### Secrets Events
```
secrets.key.generated      — encryption key generated
secrets.environment.created — GitHub environment created
secrets.secret.set         — secret value set
secrets.secret.deleted     — secret removed
secrets.pushed             — secrets pushed to environment
```

### Tool Installation Events
```
tools.installed            — tool installed
tools.updated              — tool updated
tools.removed              — tool removed
tools.plan.cached          — install plan cached
```

### Plan Events
```
plan.created               — automation plan created
plan.executed              — plan execution started
plan.step.completed        — plan step finished
plan.cancelled             — plan cancelled
plan.completed             — plan finished
```

### Script Events
```
script.executed            — script ran
```

### Trace Events
```
trace.started              — trace recording began
trace.stopped              — trace recording ended
trace.shared               — trace pushed to ledger
trace.deleted              — trace removed
```

### CDP Test Events
```
cdp_test.suite.created     — test suite created
cdp_test.recording.started — recording session began
cdp_test.recording.stopped — recording session ended
cdp_test.replay.started    — replay began
cdp_test.replay.completed  — replay finished
```

### Changelog Events
```
changelog.entry.added      — changelog entry created
changelog.entry.edited     — changelog entry modified
changelog.entry.deleted    — changelog entry removed
changelog.bootstrapped     — changelog generated from git
changelog.released         — release cut
```

### Artifact Events
```
artifact.target.created    — build target defined
artifact.target.updated    — build target modified
artifact.target.deleted    — build target removed
artifact.built             — artifact built
artifact.published         — artifact published
```

### Wizard Events
```
wizard.detected            — stacks detected
wizard.integration.setup   — integration configured (git, ci, dns, etc.)
wizard.config.saved        — project.yml saved
wizard.completed           — wizard session finished
```

### Server Events
```
server.started             — server process started
server.restarted           — server restarted
server.factory_reset       — .state/ cleared
server.settings.changed    — feature toggles changed
```

### Notification Events
```
notification.dismissed     — notification dismissed
notification.deleted       — notification removed
```

---

## Correlation IDs — How Chains Form

Events chain themselves through `correlation_id`:

| Trigger | correlation_id | Members |
|---------|---------------|---------|
| Index cycle | `cycle:{timestamp}` | All computed nodes in that cycle |
| Vault session | `vault-session:{timestamp}` | unlock → key ops → lock |
| Pages pipeline | `pages-pipeline:{timestamp}` | build → merge → deploy |
| Docker pipeline | `docker-pipeline:{timestamp}` | build → up → restart |
| Terraform flow | `tf-pipeline:{timestamp}` | plan → init → apply |
| K8s deploy | `k8s-deploy:{timestamp}` | apply → scale → helm |
| Git flow | `git-flow:{timestamp}` | commit → push |
| Backup flow | `backup:{timestamp}` | create → encrypt → upload |
| Tool install | `install:{tool}:{timestamp}` | plan → steps → verify |
| CDP test | `test-suite:{name}:{timestamp}` | create → record → replay |
| Trace | `trace:{name}:{timestamp}` | start → stop → share |
| Plan execution | `plan:{name}:{timestamp}` | create → steps → complete |
| Wizard session | `wizard:{timestamp}` | detect → setups → save |
| Secrets push | `secrets-push:{env}:{timestamp}` | set → set → push |
| Changelog release | `changelog:{version}:{timestamp}` | entries → release |
| Artifact build | `artifact:{name}:{timestamp}` | create → build → publish |
| Audit lifecycle | `audit-cycle:{timestamp}` | L0 → L1 → L2 → scores |

---

## Event Store

**Append-only. Immutable. Ordered.**

```python
class EventStore:
    def append(self, event: Event) -> None
    def query(self, since: float, types: list[str], correlation_id: str) -> list[Event]
    def subscribe(self, callback) -> None
```

Storage: in-memory deque (hot) + JSONL file per day (cold).

```
.state/events/2026-03-15.jsonl
.state/events/2026-03-16.jsonl
```

---

## Projections (CQRS Query Side)

Each projection subscribes to the store and builds a read model:

```python
class TimelineProjection:
    """Builds the timeline entry list from events."""
    # Groups events by type, maps to TimelineEntry

class ChainProjection:
    """Builds chains from correlation_ids."""
    # Groups events by correlation_id → chain

class DomainProjection:
    """Builds domain facets (adapter → subtype → count)."""
    # Groups events by domain → subtype

class CalendarProjection:
    """Builds day-by-day counts."""
    # Groups events by date
```

The `timeline.data` mediator node reads from these projections
instead of from adapters. One source of truth: the event store.

---

## Emitters — Where Events Are Produced

| Location | How | Events |
|----------|-----|--------|
| `mediator.get()` | After resolver runs | `mediator.computed` |
| `mediator.put()` | After invalidation | `mediator.invalidated` |
| `index_watcher` | Cycle lifecycle | `index.cycle.*`, `index.node.*`, `index.tier.*` |
| `persistence` | Disk shard write | `mediator.persisted` |
| `hydrate_cache` | Startup load | `mediator.hydrated` |
| Route handlers | `@tracked` decorator | All user operation events |
| CLI executor | `execute_plan()` | CLI operation events |
| `record_event()` | Wizard/security | Wizard and security events |
| Git log adapter | Reads git history | Git commit events (external) |
| Chat adapter | Reads ledger | Chat events (external) |
| GitHub adapter | Reads mediator cache | GitHub events (derived) |

---

## What Changes From Current System

| Current | New |
|---------|-----|
| Events fire and disappear | Events stored permanently |
| 5 separate tracking mechanisms | 1 Event Store |
| Adapters read files, produce entries | Projections read Event Store |
| Chains built from chain_id fields | Chains built from correlation_id |
| Domains from adapter name | Domains from event type prefix |
| No history beyond 200 entries | Full history (JSONL per day) |
| Subscribers are observers | Emitters push to store directly |

---

## Iteration Plan

1. **Event + EventStore** — the core data model and append-only store
2. **Emitters** — wire mediator, index watcher, routes to emit events
3. **Projections** — timeline, chains, domains, calendar
4. **Wire to UI** — `timeline.data` reads from projections
5. **Tests** — validate every event type, every chain, every domain
