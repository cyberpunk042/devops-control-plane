# Timeline V2 — Hard Requirements

> This is the single source of truth for Timeline V2.
> Previous plans, specs, and iterations are superseded.

---

## Mission

Integrate **RUN**, **AUDIT**, and **TIMELINE** across every route and command
that performs a meaningful operation. Every user action and system event
that changes state must appear in the timeline. No silent operations.

---

## Principle

The timeline is the **audit trail of everything that happens** in and to
the project. If a user did it, if the system triggered it, if an
integration reported it — it shows up.

---

## Event Sources — What Must Be Captured

### Git (adapter: `git_log`)
| Event | Subtype | Chain |
|-------|---------|-------|
| Commit | `commit` | branch chain (`git:{branch}`) |
| Merge | `merge` | branch chain |
| Branch created | `branch` | new chain origin |
| Tag created | `tag` | branch chain terminal |

### GitHub (NEW adapter: `github`)
| Event | Subtype | Chain |
|-------|---------|-------|
| PR opened | `pr:opened` | PR chain (`pr:{number}`) |
| PR merged/closed | `pr:closed` | PR chain terminal |
| Workflow triggered | `workflow:start` | workflow chain (`workflow:{run_id}`) |
| Workflow completed | `workflow:done` | workflow chain terminal |
| Check failed | `check:failed` | workflow chain step |
| Release published | `release` | — |

### Vault (NEW adapter: `vault`)
| Event | Subtype | Chain |
|-------|---------|-------|
| Unlock | `unlock` | session chain (`vault:{ts}`) origin |
| Lock | `lock` | session chain terminal |
| Key added | `key:add` | session chain step |
| Key updated | `key:update` | session chain step |
| Key deleted | `key:delete` | session chain step |
| Secrets synced | `sync` | session chain step |
| Export | `export` | session chain step |

### Content Vault (NEW adapter: `content`)
| Event | Subtype | Chain |
|-------|---------|-------|
| File encrypted | `encrypt` | — |
| File decrypted | `decrypt` | — |
| Media optimized | `optimize` | — |
| Upload to release | `upload` | — |

### Pages (NEW adapter: `pages`)
| Event | Subtype | Chain |
|-------|---------|-------|
| Build started | `build:start` | pages chain (`pages:{builder}:{ts}`) |
| Build completed | `build:done` | pages chain terminal |
| Deploy started | `deploy:start` | pages chain step |
| Deploy completed | `deploy:done` | pages chain terminal |

### Docker (NEW adapter: `docker`)
| Event | Subtype | Chain |
|-------|---------|-------|
| Build | `build` | — |
| Up/Down/Restart | `compose:{action}` | — |
| Prune | `prune` | — |

### Kubernetes (NEW adapter: `k8s`)
| Event | Subtype | Chain |
|-------|---------|-------|
| Apply | `apply` | — |
| Scale | `scale` | — |
| Rollback | `rollback` | — |
| Delete | `delete` | — |

### Terraform (NEW adapter: `terraform`)
| Event | Subtype | Chain |
|-------|---------|-------|
| Plan | `plan` | IaC chain (`tf:{workspace}:{ts}`) |
| Apply | `apply` | IaC chain terminal |
| Destroy | `destroy` | — |

### CI/CD (via existing routes)
| Event | Subtype | Chain |
|-------|---------|-------|
| Pipeline triggered | `trigger` | CI chain |
| Pipeline completed | `done` | CI chain terminal |
| Deploy | `deploy` | CI chain step |

### Backup (NEW adapter: `backup`)
| Event | Subtype | Chain |
|-------|---------|-------|
| Created | `create` | — |
| Restored | `restore` | — |
| Deleted | `delete` | — |
| Exported | `export` | — |

### CLI Operations (adapter: `cli_ops` — FIX)
| Event | Subtype | Chain |
|-------|---------|-------|
| Any `run` command | `run:{capability}` | operation chain (`op:{id}`) |
| detect | `detect` | — |
| status | `status` | — |
| config check | `config` | — |
| Any command | `cli:{group}:{action}` | operation chain if multi-step |

### Audit / Index (adapter: `scan_activity` — EXISTS)
| Event | Subtype | Chain |
|-------|---------|-------|
| Index cycle start | `cycle:start` | cycle chain (`cycle:{id}`) origin |
| Card computed | `card:{name}` | cycle chain step |
| Index cycle done | `cycle:done` | cycle chain terminal |
| L0 scan | `audit:L0` | audit chain step |
| L1 scan | `audit:L1` | audit chain step |
| L2 scan | `audit:L2` | audit chain step |
| Score changed | `score:changed` | audit chain step |
| Posture updated | `posture:updated` | audit chain terminal |

### Environment (NEW — emit from vault/config routes)
| Event | Subtype | Chain |
|-------|---------|-------|
| Env created | `env:create` | — |
| Env switched | `env:switch` | — |
| Config saved | `config:save` | — |

### Chat (adapter: `chat` — EXISTS)
| Event | Subtype | Chain |
|-------|---------|-------|
| Thread created | `thread` | thread chain origin |
| Message sent | `message` | thread chain step |

### Server Lifecycle (NEW — emit from server routes)
| Event | Subtype | Chain |
|-------|---------|-------|
| Server started | `start` | — |
| Server restarted | `restart` | — |
| Factory reset | `reset` | — |
| Settings changed | `settings` | — |

### Quality / Testing / Security (via routes)
| Event | Subtype | Chain |
|-------|---------|-------|
| Lint run | `lint` | operation chain |
| Test run | `test` | operation chain |
| Format run | `format` | operation chain |
| Security scan | `scan` | operation chain |

### Scripts / Plans (via routes)
| Event | Subtype | Chain |
|-------|---------|-------|
| Script executed | `script:{name}` | — |
| Plan created | `plan:create` | plan chain |
| Plan executed | `plan:execute` | plan chain step |

### Traces / CDP Tests (via routes)
| Event | Subtype | Chain |
|-------|---------|-------|
| Trace recorded | `trace:record` | — |
| Test replayed | `test:replay` | — |

---

## View Requirements

### Calendar View
- Every event above appears on its day
- Days with activity show a count badge
- Clicking a day filters the entry list to that day
- Current month and year auto-expand on load
- Clicking a month selects the whole month
- Clicking a year selects the whole year

### Domains View
- Tree structure: **Adapter → Source → Subtype → Entries**
- Must show 50+ nodes across all adapters
- Clicking a node filters the entry list to that domain
- Toggle principle: clicking an active filter deactivates it
- Counts reflect current filtered population

### Chains View
- Every multi-step operation appears as a chain
- Chains show origin → steps → terminal
- Git branch history as a continuous chain
- Index cycles as linked chains
- CLI `run` operations chain through their effects
- Audit lifecycle (L0 → L1 → L2 → scores → posture) as a chain
- Vault sessions (unlock → ops → lock) as a chain
- Pages pipelines (build → deploy) as a chain
- Clicking a chain filters + expands
- "Load more" for chains with 50+ members

---

## Implementation Architecture

### How Events Get Recorded

**Pattern A — Route-level emit (NEW operations):**
Routes that perform actions (POST/PUT/DELETE) emit a timeline entry
directly via `TimelineService.record(entry)`. This writes to
`.ledger/activity/{date}.jsonl`.

**Pattern B — Adapter read (existing data):**
Adapters read from existing data stores (git log, audit_activity.json,
chat threads) and produce timeline entries on demand.

**Pattern C — Subscriber (mediator events):**
The scan_activity subscriber records card computations automatically
when the mediator recomputes nodes.

### New Adapters Needed
1. `github` — reads from `github.pulls`, `github.runs`, `github.workflows` mediator nodes
2. `vault` — reads from `.ledger/activity/` vault events
3. `content` — reads from `.ledger/activity/` content events
4. `pages` — reads from `.ledger/activity/` pages events
5. `docker` — reads from `.ledger/activity/` docker events
6. `k8s` — reads from `.ledger/activity/` k8s events
7. `terraform` — reads from `.ledger/activity/` terraform events
8. `backup` — reads from `.ledger/activity/` backup events
9. `server` — reads from `.ledger/activity/` server events

### Shared Activity Ledger

All Pattern A events write to a single JSONL file per day:
```
.ledger/activity/2026-03-15.jsonl
```

Each line is a JSON object matching the `TimelineEntry` schema.
A single new adapter (`ActivityLedgerAdapter`) reads all `.jsonl` files
and produces entries. This avoids creating 9 separate adapters that all
read from the same place.

### What Routes Need Instrumentation

Every POST/PUT/DELETE route that **changes state** must call:
```python
record_activity(source, subtype, summary, detail, chain_id, chain_role, ...)
```

This is a thin helper that appends to `.ledger/activity/{date}.jsonl`.

**Priority order for instrumentation:**
1. Vault routes (lock, unlock, key ops, sync)
2. CLI `run` command (executor)
3. Pages routes (build, deploy)
4. Docker routes (build, up, down, restart)
5. Backup routes (create, restore, delete)
6. Server routes (restart, factory-reset, settings)
7. Config routes (save)
8. Content routes (encrypt, decrypt, optimize, upload)
9. K8s routes (apply, scale, rollback, delete)
10. Terraform routes (plan, apply, destroy)
11. CI routes (trigger, deploy)
12. Quality/Testing routes (lint, test, format, scan)
13. Scripts/Plans routes (execute)
14. Secrets routes (GitHub secret ops)
15. DNS routes (record ops)
16. Traces/CDP routes (record, replay)

---

## Fixes Required (Existing System)

1. **cli_ops adapter** — audit.ndjson deleted by factory reset, never regenerated.
   Fix: executor must recreate the file on first write.
2. **operation_context** — now thread-local but workers need cycle_id propagation.
   Fix: done (dispatch captures and sets in worker).
3. **Feed nodes** — never dispatched in tier5.
   Fix: done (timeline.* added to tier5_paths).
4. **Orphan scan_activity entries** — some cards compute without operation_id.
   Fix: done (thread-local propagation).
5. **Chain tree exponential bug** — `childrenOf` matched all siblings.
   Fix: done (removed `chainId` match).
6. **Git chain label** — showed "Initial commit" instead of branch name.
   Fix: done (uses branch name).

---

## Non-Goals (Out of Scope)

- Real-time collaboration / multi-user
- External webhook ingestion
- Timeline data export/import
- Timeline entry editing or deletion
- Cross-project timeline aggregation
