# Fix: _content_merge must handle ALL ledger data types

## Problem

`_content_merge` in `src/core/services/ledger/worktree.py` (lines 466-603) only
handles `chat/threads/*/messages.jsonl`. When it runs:

1. It snapshots ONLY chat message IDs
2. `git reset --hard origin/ledger` — **wipes the ENTIRE worktree**
3. Recovers ONLY chat messages that were local-only
4. Everything else (suites, plans, traces) is destroyed silently
5. Returns `{"ok": True}` — **lies about success**

## All ledger data paths

| Data Type         | Ledger Path                              | Format | Merge Strategy         |
|-------------------|------------------------------------------|--------|------------------------|
| Chat messages     | `chat/threads/<tid>/messages.jsonl`      | JSONL  | Append by unique `id`  |
| Chat thread meta  | `chat/threads/<tid>/thread.json`         | JSON   | Keep newer `updated_at`|
| Trace data        | `traces/<trace_id>/trace.json`           | JSON   | Keep newer `updated_at`|
| Trace events      | `traces/<trace_id>/events.jsonl`         | JSONL  | Append by unique `id`  |
| Test suites       | `cdp-tests/suites/<id>.json`             | JSON   | Keep newer `updated_at`|
| Exec plans        | `cdp-plans/plans/<id>.json`              | JSON   | Keep newer `updated_at`|
| Hidden suites     | `cdp-tests/.hidden-suites.json`          | JSON   | Keep local (list merge)|
| Hidden plans      | `cdp-plans/.hidden-plans.json`           | JSON   | Keep local (list merge)|
| Git attributes    | `.gitattributes`                         | text   | Skip (git plumbing)    |

Source evidence:
- `_ledger_suites_dir` → `worktree / "cdp-tests" / "suites"` (storage.py:59)
- `_ledger_plans_dir` → `worktree / "cdp-plans" / "plans"` (plan_storage.py:63)
- Chat/traces already visible in `.ledger/` listing

## Exact code changes

### File: `src/core/services/ledger/worktree.py`
### Function: `_content_merge` (lines 466-603)

Replace the chat-only logic with a generic file-level merge.

### New algorithm (5 phases):

```
Phase 1: SNAPSHOT ALL LOCAL FILES
    Walk the entire worktree (skip .git, .gitattributes)
    For each file:
        local_files[relative_path] = file_bytes
    This replaces current lines 480-508 (chat-only snapshot)

Phase 2: RESET TO REMOTE (unchanged)
    git rebase --abort (safety)
    git reset --hard origin/ledger
    This is current lines 511-518 — no change needed

Phase 3: SNAPSHOT ALL REMOTE FILES
    Walk the worktree again (now contains remote state)
    For each file:
        remote_files[relative_path] = file_bytes
    This replaces current lines 522-543 (chat-only remote read)

Phase 4: MERGE — three cases for each local file
    paths_to_restore = []
    recovered_count = 0

    For each (path, content) in local_files:
        CASE A: path NOT in remote_files
            → File is local-only. Write it back to disk.
            → paths_to_restore.append(path)
            → recovered_count += 1

        CASE B: path in remote_files AND path ends with ".jsonl"
            → JSONL merge: parse both sides by "id" field
            → Find entries in local that are NOT in remote (by id)
            → If any: append them to the remote file on disk
            → paths_to_restore.append(path)
            → recovered_count += len(missing_entries)

        CASE C: path in remote_files AND path ends with ".json"
            → If content is identical → skip (already synced)
            → If content differs:
                → Parse both as JSON
                → Compare updated_at timestamps
                → Keep whichever is newer
                → If no updated_at or parse fails → keep local
                → If local wins: overwrite remote file with local content
                → paths_to_restore.append(path)
                → recovered_count += 1

        CASE D: path in remote_files AND not .json/.jsonl
            → If content differs → keep local
            → paths_to_restore.append(path)

    This replaces current lines 545-576

Phase 5: COMMIT + PUSH (same structure as current lines 578-603)
    If paths_to_restore is not empty:
        ledger_add_and_commit(project_root, paths=paths_to_restore,
            message=f"ledger: content merge — recovered {recovered_count} item(s)")
    Push to origin
    Return result
```

### Helper functions needed:

None. All logic is inline in `_content_merge`. The file walking, JSON parsing,
and JSONL id-extraction are simple enough to inline. No new abstractions.

### Functions NOT touched:

- `ledger_sync_status` — not part of this fix (separate concern)
- `push_ledger_branch` — not touched
- `ledger_resolve_conflict` — not touched (just dispatches to _content_merge)
- Frontend code — not touched
- Per-item add/sync/remove routes — not touched

## Verification

After the change:

1. The worktree should contain suites/plans/traces AFTER a content merge
2. `git log` in the ledger should show commits with all file types
3. The push should push everything to remote
4. `sync-status` should show "synced" and the remote should actually have the data

## Risk assessment

- `git reset --hard` still wipes everything — but now we have a FULL snapshot beforehand
- JSONL merge by `id` — same proven logic as before, just applied to all `.jsonl` files
- JSON merge by `updated_at` — safe because we fall back to "keep local" if parse fails
- Worst case: local-only files are restored even if they shouldn't be — better than losing them
