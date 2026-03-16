# Timeline V2 — Pessimistic Test Requirements

> These tests run against the mediator and adapters directly.
> No UI. No HTTP requests. No Flask app.
> Every test MUST FAIL until the requirement is fully implemented.

---

## Test Strategy

Each test:
1. Creates a mediator instance
2. Registers all nodes + subscribers
3. Triggers computation cycles (force=True)
4. Reads timeline.data from the mediator
5. Asserts entries, chains, domains exist with correct structure

---

## 1. ADAPTERS — Each adapter produces entries

### 1.1 git_log adapter produces entries
```
GIVEN a git repository with commits
WHEN GitLogAdapter.load() is called
THEN it returns entries with:
  - len(entries) > 0
  - every entry has source="git"
  - every entry has subtype in ("commit", "merge", "ci", "docker", "k8s", "rules", "promoted", "tag", "branch")
  - every entry has chain_id starting with "git:"
  - every entry has chain_role in ("origin", "step")
  - entry.id starts with "git:"
  - entry.locality == "shared"
  - entry.actor == "user"
```

### 1.2 chat adapter produces entries
```
GIVEN .ledger/chat/threads/ with threads
WHEN ChatAdapter.load() is called
THEN it returns entries with:
  - thread_created entries have chain_role="origin"
  - message entries have chain_role="step"
  - all entries in same thread share chain_id
  - entry.source == "chat"
  - entry.locality == "shared"
```

### 1.3 runs adapter produces entries
```
GIVEN .state/runs.jsonl with run records
WHEN RunsAdapter.load() is called
THEN it returns entries with:
  - entry.id starts with "run:"
  - entry.chain_role == "origin" (default, no chain context)
  - entry.locality == "local"
  - source maps correctly per RUN_TYPE_MAP:
    - type="build" → source="platform"
    - type="deploy" → source="ci"
    - type="test" → source="tests"
    - type="scan" → source="security"
    - type="git" → source="git"
    - type="backup" → source="backup"
    - type="setup" → source="config"
    - type="install" → source="pkg"
    - type="validate" → source="tests"
    - type="format" → source="tools"
    - type="generate" → source="platform"
    - type="script" → source="platform"
    - type="restore" → source="backup"
    - type="ci" → source="ci"
    - type="destroy" → source="platform"
    - type="cdp_test" → source="tests"
```

### 1.4 runs adapter reads chain metadata
```
GIVEN a run record with metadata._chain_id="vault-session:123"
  AND metadata._chain_role="step"
WHEN RunsAdapter.load() is called
THEN the entry has:
  - chain_id == "vault-session:123"
  - chain_role == "step"
  - chain_id != run_id (overridden by metadata)
```

### 1.5 mediator subscriber produces entries
```
GIVEN a registered mediator with mediator_timeline subscriber
WHEN mediator.get("devops.docker", force=True) is called
THEN get_entries() returns at least 1 entry with:
  - source == "platform"
  - subtype == "docker"
  - ref == "devops.docker"
  - detail.path == "devops.docker"
  - detail.elapsed_s >= 0
```

### 1.6 mediator subscriber suppresses internal nodes
```
GIVEN a registered mediator with mediator_timeline subscriber
WHEN mediator.get("timeline.data", force=True) is called
THEN get_entries() does NOT contain any entry with ref starting with:
  - "timeline."
  - "detect."
  - "tabmesh."
```

### 1.7 mediator subscriber seeds from cache on registration
```
GIVEN a mediator with 40+ cached nodes (from hydration)
WHEN register_mediator_timeline_subscriber() is called
THEN get_entries() returns 30+ entries immediately
  AND entries cover paths from devops.*, audit.*, index.*, posture.*, catalog.*, github.*
```

### 1.8 scan_activity adapter only returns user events
```
GIVEN .state/audit_activity.json with entries
  - some with action field (from record_event)
  - some without action field (from record_scan_activity)
WHEN ScanActivityAdapter.load() is called
THEN it returns ONLY entries that had an action field
  AND entries without action are excluded (handled by mediator subscriber)
```

### 1.9 cli_ops adapter produces entries
```
GIVEN .state/audit.ndjson with operation records
WHEN CliOpsAdapter.load() is called
THEN it returns entries with:
  - entry.chain_id == operation_id
  - entry.chain_role == "origin"
  - entry.source matches operation_type mapping
```

---

## 2. CHAINS — Every chain type exists

### 2.1 Git branch chain
```
GIVEN git log with commits on main
WHEN timeline.data is resolved
THEN chains contains a chain with:
  - chain_id == "git:main"
  - entry_count == number of commits
  - sources includes "git"
  - members sorted newest-first
  - first member (newest) has chain_role="step"
  - last member (oldest) has chain_role="origin"
```

### 2.2 Index cycle chain
```
GIVEN a full index cycle completes (all tiers)
WHEN timeline.data is resolved
THEN chains contains a chain with:
  - chain_id starts with "cycle-"
  - entry_count >= 40 (full cycle: index + devops + audit + posture + catalog + github)
  - sources includes at least: "platform", "audit", "tests", "tools"
  - members include entries with subtype:
    - "index:scan"
    - "index:delta"
    - "docker"
    - "k8s"
    - "L1" (audit)
    - "L2:risks" (audit)
    - "scores"
    - "full" (posture)
    - "summary" (posture)
    - "toolchain" (posture/tools)
    - "pulls" (github)
    - "runs" (github)
```

### 2.3 Chat thread chain
```
GIVEN .ledger/chat/threads/ with a thread containing messages
WHEN timeline.data is resolved
THEN chains contains a chain with:
  - chain_id == thread_id
  - sources == ["chat"]
  - first member has subtype="thread_created", chain_role="origin"
  - subsequent members have subtype="message", chain_role="step"
```

### 2.4 Vault session chain
```
GIVEN vault unlock is triggered, then key ops, then lock
WHEN timeline.data is resolved
THEN chains contains a chain with:
  - chain_id starts with "vault-session:"
  - entry_count >= 3 (unlock + ops + lock)
  - members include subtypes: unlock, key ops, lock
  - first member is the unlock (origin or step)
  - lock is the terminal
```

### 2.5 Pages pipeline chain
```
GIVEN pages build then deploy is triggered
WHEN timeline.data is resolved
THEN chains contains a chain with:
  - chain_id starts with "pages-pipeline:"
  - entry_count >= 2
  - members include build and deploy subtypes
```

### 2.6 Docker pipeline chain
```
GIVEN docker build then up is triggered
WHEN timeline.data is resolved
THEN chains contains a chain with:
  - chain_id starts with "docker-pipeline:"
  - entry_count >= 2
```

### 2.7 Terraform pipeline chain
```
GIVEN terraform plan then apply is triggered
WHEN timeline.data is resolved
THEN chains contains a chain with:
  - chain_id starts with "tf-pipeline:"
  - entry_count >= 2
```

### 2.8 K8s deployment chain
```
GIVEN k8s apply then scale is triggered
WHEN timeline.data is resolved
THEN chains contains a chain with:
  - chain_id starts with "k8s-deploy:"
  - entry_count >= 2
```

### 2.9 Git flow chain
```
GIVEN git commit then push is triggered
WHEN timeline.data is resolved
THEN chains contains a chain with:
  - chain_id starts with "git-flow:"
  - entry_count >= 2
```

### 2.10 Backup pipeline chain
```
GIVEN backup export then encrypt is triggered
WHEN timeline.data is resolved
THEN chains contains a chain with:
  - chain_id starts with "backup:"
  - entry_count >= 2
```

### 2.11 Run → scan_activity chain linking
```
GIVEN a @run_tracked route triggers mediator computations
WHEN timeline.data is resolved
THEN the run entry has chain_id == run_id, chain_role == "origin"
  AND mediator entries during that run have chain_id == run_id, chain_role == "step"
  AND both appear in the same chain
```

### 2.12 Tool installation chain
```
GIVEN a tool install operation with multiple steps
WHEN timeline.data is resolved
THEN chains contains a chain with:
  - entry_count >= 3 (plan + steps + complete)
```

### 2.13 CDP test suite chain
```
GIVEN a CDP test suite created, recorded, and replayed
WHEN timeline.data is resolved
THEN chains contains a chain with:
  - members include suite:create, record:start, record:stop, replay:start
```

### 2.14 Wizard session chain
```
GIVEN wizard setup with multiple integration setups
WHEN timeline.data is resolved
THEN chains contains a chain with:
  - members include wizard:detect, setup_git, setup_ci, config:saved
```

### 2.15 Secrets push chain
```
GIVEN secret set operations followed by secrets_push
WHEN timeline.data is resolved
THEN chains contains a chain with:
  - members include secret:set entries and deploy:secrets_push
```

### 2.16 Changelog release chain
```
GIVEN changelog entries added then release cut
WHEN timeline.data is resolved
THEN chains contains a chain with:
  - members include entry:add and release:cut
```

### 2.17 Artifact build chain
```
GIVEN artifact target created, built, and published
WHEN timeline.data is resolved
THEN chains contains a chain with:
  - members include target:create, build:stream, publish:stream
```

### 2.18 Trace lifecycle chain
```
GIVEN trace started, stopped, and shared
WHEN timeline.data is resolved
THEN chains contains a chain with:
  - members include trace:start, trace:stop, trace:share
```

### 2.19 Plan execution chain
```
GIVEN plan created and executed with multiple steps
WHEN timeline.data is resolved
THEN chains contains a chain with:
  - members include plan:create and plan:execute steps
```

### 2.20 Environment setup chain
```
GIVEN env created and activated
WHEN timeline.data is resolved
THEN chains contains a chain with:
  - members include env:create and env:activate
```

---

## 3. DOMAINS — Every domain has entries

### 3.1 Mediator domain has all node groups
```
GIVEN a full index cycle completes
WHEN timeline.data facets.by_adapter is checked
THEN by_adapter["mediator"] contains subtypes:
  - "index:scan", "index:delta", "index:files", "index:dirs"
  - "index:paths", "index:classify"
  - "docker", "k8s", "terraform", "dns", "docs", "pages"
  - "git status", "github"
  - "scan" (security), "scan" (testing), "quality"
  - "packages", "env"
  - "L1", "scores", "structure", "deps", "clients"
  - "L1:deep", "L2:risks", "L2:repo", "L2:quality", "L2:structure"
  - "scores:enriched"
  - "toolchain", "platform", "project", "full", "summary" (posture)
  - "pulls", "runs", "workflows" (github)
  - "tools", "builders", "scripts" (catalog)
  - "runtime", "status"
```

### 3.2 git_log domain has subtypes
```
WHEN timeline.data facets.by_adapter is checked
THEN by_adapter["git_log"] contains subtypes:
  - "commit" with count > 300
  - other subtypes present (ci, docker, k8s, rules, promoted)
```

### 3.3 chat domain has subtypes
```
WHEN timeline.data facets.by_adapter is checked
THEN by_adapter["chat"] contains:
  - "thread_created"
  - "message"
```

### 3.4 runs domain has subtypes after operations
```
GIVEN @run_tracked operations have been triggered
WHEN timeline.data facets.by_adapter is checked
THEN by_adapter["runs"] contains subtypes matching the operations:
  - e.g. "setup:vault_lock", "build:docker", "git:commit"
```

### 3.5 Every adapter appears in by_adapter
```
WHEN timeline.data facets.by_adapter is checked
THEN the following adapter keys exist:
  - "git_log"
  - "mediator"
  - "chat"
  - "runs" (after operations)
  - "scan_activity" (after wizard/security events)
  - "cli_ops" (after CLI operations)
```

---

## 4. CHAIN INTEGRITY — Structure rules

### 4.1 Every chain has at least 2 members
```
WHEN timeline.data chains is checked
THEN every chain has entry_count >= 2
  (solo entries are not chains)
```

### 4.2 Every chain has an origin
```
WHEN timeline.data chains is checked
THEN every chain has at least one member with chain_role="origin"
```

### 4.3 Chain members are sorted newest-first
```
WHEN timeline.data chains is checked
THEN every chain's members list has ts values in descending order
```

### 4.4 No duplicate entries across adapters
```
WHEN timeline.data entries is checked
THEN no two entries share the same id
  (scan_activity and mediator don't overlap)
  (runs and cli_ops don't overlap)
```

### 4.5 Chain sources are accurate
```
WHEN timeline.data chains is checked
THEN each chain's sources list matches the actual source values of its members
```

---

## 5. MEDIATOR SUBSCRIBER — Coverage rules

### 5.1 All devops nodes produce entries
```
GIVEN all devops.* nodes compute
THEN mediator buffer contains entries for:
  devops.docker, devops.k8s, devops.terraform, devops.git,
  devops.github, devops.ci, devops.env, devops.security,
  devops.packages, devops.quality, devops.testing, devops.docs,
  devops.dns, devops.status
```

### 5.2 All audit nodes produce entries
```
GIVEN all audit.* nodes compute
THEN mediator buffer contains entries for:
  audit.scores, audit.system, audit.deps, audit.structure,
  audit.clients, audit.system_deep, audit.l2_structure,
  audit.l2_quality, audit.l2_repo, audit.l2_risks,
  audit.scores_enriched
```

### 5.3 All index nodes produce entries
```
GIVEN all index.* nodes compute
THEN mediator buffer contains entries for:
  index.scan, index.delta, index.files, index.dirs,
  index.paths, index.classify, index.symbols, index.stats,
  index.view, index.peek
```

### 5.4 All posture nodes produce entries
```
GIVEN all posture.* nodes compute
THEN mediator buffer contains entries for:
  posture.full, posture.summary, posture.platform,
  posture.project, posture.toolchain
```

### 5.5 All catalog nodes produce entries
```
GIVEN all catalog.* nodes compute
THEN mediator buffer contains entries for:
  catalog.tools, catalog.builders, catalog.scripts, catalog.pages
```

### 5.6 All github nodes produce entries
```
GIVEN all github.* nodes compute
THEN mediator buffer contains entries for:
  github.pulls, github.runs, github.workflows
```

### 5.7 Cycle chain includes ALL tiers
```
GIVEN a full index cycle with all 6 tiers dispatched
THEN the cycle chain includes members from:
  - T1: catalog.* nodes
  - T2: devops.docker, devops.k8s, devops.terraform, github.*
  - T3: devops.security, devops.testing
  - T4: index.stats, index.view (+ symbols, peek on cold)
  - T5: devops.status, posture.*, audit L0/L1, timeline.*
  - T6: audit L2, audit.scores_enriched
```

### 5.8 Cycle ID propagates through ALL tiers
```
GIVEN a full index cycle with cycle_id set
THEN every mediator entry from that cycle has:
  - chain_id == cycle_id
  - chain_role == "step"
  - NO entries from the cycle have chain_id == None
```

---

## 6. RUN TRACKING — Operation coverage

### 6.1 operation_id links runs to mediator entries
```
GIVEN a @run_tracked route that triggers mediator.get() or bust()
WHEN the route completes
THEN .state/runs.jsonl contains a run with run_id
  AND mediator entries during the run have chain_id == run_id
```

### 6.2 Vault chain_context propagates
```
GIVEN vault_unlock sets chain_context("vault", session_id)
  AND vault key operations read chain_context("vault")
  AND vault_lock clears chain_context("vault")
THEN all vault runs between unlock and lock share the same chain_id
```

### 6.3 Pages chain_context propagates
```
GIVEN build_segment sets chain_context("pages", pipeline_id)
  AND merge/deploy read chain_context("pages")
THEN build, merge, deploy runs share the same chain_id
```

### 6.4 Docker chain_context propagates
```
GIVEN docker_build sets chain_context("docker", pipeline_id)
  AND docker_up reads chain_context("docker")
THEN build and up runs share the same chain_id
```

---

## 7. WIZARD — Setup chains

### 7.1 Main wizard produces chain
```
GIVEN the main wizard detect → setup integrations → save config
WHEN record_event calls fire for each step
THEN scan_activity contains entries with:
  - wizard:detect, wizard:setup_git, wizard:setup_ci, etc.
  - all sharing a wizard session chain_id
```

### 7.2 Integration setup produces sub-entries
```
GIVEN setup_git wizard runs
WHEN record_event fires
THEN entry has:
  - source == "wizard"
  - subtype includes the integration name
  - detail includes what was configured
```

---

## Summary

| Category | Test Count | What it validates |
|----------|-----------|-------------------|
| Adapters | 9 | Each adapter produces correct entries |
| Chains | 20 | Every chain type exists with correct structure |
| Domains | 5 | Every domain group has entries with subtypes |
| Chain integrity | 5 | Structure rules (origin, sort, dedup, sources) |
| Mediator subscriber | 8 | All nodes captured, cycle coverage, ID propagation |
| Run tracking | 4 | operation_id linking, chain_context propagation |
| Wizard | 2 | Setup chains with sub-entries |
| **TOTAL** | **53** | |

All 53 tests MUST PASS before Timeline V2 is complete.
