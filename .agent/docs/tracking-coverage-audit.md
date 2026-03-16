# Tracking Coverage Audit — Complete Report

## Route Coverage

**290 write routes total. 182 have @tracked (63%). 108 missing.**

### SSE Streaming Routes — 9 total

| Route | File | @tracked | Start Event | Completion Event (ok) | Completion Event (fail) |
|-------|------|----------|-------------|----------------------|------------------------|
| `/scripts/run/stream` | scripts/execution.py:73 | YES | YES | YES | YES (3 paths) |
| `/docker/stream/<action>` | docker/stream.py:19 | YES | YES | YES | YES (3 paths) |
| `/artifacts/build/<name>/stream` | artifacts/api.py:142 | YES | YES | YES | YES (2 paths) |
| `/pages/build-stream/<name>` | pages/api.py:453 | **NO** | via generator | YES | YES (3 paths) |
| `/pages/builders/<name>/install` | pages/api.py:192 | YES | YES | YES | YES (crash + done) |
| `/audit/install-plan/execute` | tool_execution.py:134 | YES | YES | YES | YES (4 paths) |
| `/audit/install-plan/resume` | tool_execution.py:707 | YES | YES | YES | YES (3 paths) |
| `/publish/<name>/stream` | artifacts/api.py:362 | **NO** | **NO** | **NO** | **NO** |
| `/audit/remediate` | tool_install.py:56 | **NO** | **NO** | **NO** | **NO** |

### Missing: 2 SSE routes with zero tracking

1. **`/publish/<name>/stream`** — artifact publishing with SSE progress
2. **`/audit/remediate`** — tool remediation with SSE streaming

### Background Thread Operations — 24 total

#### Tracked (4):
- Plan executor → `plan.completed/failed` ✓
- CDP test replayer → `cdp_test.replay.completed/failed` ✓
- Tool plan DAG → `tools.plan.completed/failed` ✓
- Audit async scan → `audit:complete` via EventBus ✓

#### Git push threads — silent (10):
These spawn `push_ledger_branch` or `push_chat` in background. They're fire-and-forget git pushes. No events, no failure capture.

- `trace/sharing.py:58,88` — trace share/unshare push
- `plans/crud.py:219,254,290` — plan add/sync/remove from git push
- `cdp_test/suites.py:223,258,294` — suite add/sync/remove from git push
- `chat/messages.py:126` — chat message push

#### Continuous/infrastructure threads — not applicable (10):
These are long-lived daemon threads (CDP injector, WSL tunnel, project index, etc.). They don't represent user operations — no events needed.

### Write Routes Missing @tracked — Notable ones

Most of the 108 missing routes fall into categories:

**Should track (user operations that modify state):**
- `/audit/scan` — runs full L2 audit (bg thread, no @tracked)
- `/audit/remediate` — SSE remediation stream
- `/publish/<name>/stream` — artifact publish stream
- `/audit/system/deep-detect` — deep system detection
- `/audits/save`, `/audits/discard`, `/audits/saved/<id>` DELETE — audit snapshots
- `/chat/send`, `/chat/delete-message`, `/chat/update-message`, `/chat/move-message` — already have @tracked
- `/posture/rescan`, `/posture/rescan-tool` — posture rescans
- `/content/save-encrypted` — encrypted content save
- `/content/release-cancel` — release cancel
- `/git/pull`, `/git/push` — already have @tracked
- `/ledger/push`, `/ledger/resolve-conflict` — ledger operations

**Should NOT track (read-like, infrastructure, or internal):**
- `/batch` — internal batch prefetch
- `/detect`, `/run` — status detection
- `/mediator/*` — internal cache/dispatch management
- `/tab-mesh/*` — CDP session management (19 routes)
- `/notifications/*` — notification CRUD
- `/audit/check-deps`, `/audit/resolve-choices`, `/audit/install-plan`, etc. — plan resolution (read-like)
- `/k8s/wizard-state` — wizard state save
- `/server/accept-port` — port fallback accept
- `/git/auth-*`, `/git/identity` — credential management
- `/devops/prefs`, `/devops/cache/bust` — preferences
