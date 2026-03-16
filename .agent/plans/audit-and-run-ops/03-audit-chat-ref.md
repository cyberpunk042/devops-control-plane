# Phase 3: Audit Chat Reference

> **Status**: Draft  
> **Depends on**: Phase 1 (saved audits exist on ledger branch)

---

## Goal

Upgrade `@audit:` chat references to resolve from the ledger branch (saved audit snapshots), and make saved audits available in the autocomplete dropdown.

## What Changes

### 1. Modified: `_resolve_audit()` in `chat_refs.py`

Current behavior: reads from `.state/audit.ndjson` by `operation_id`.  
New behavior: **also** checks `.scp-ledger/audits/<snapshot_id>.json` for saved scan snapshots.

```python
def _resolve_audit(audit_id: str, project_root: Path) -> dict | None:
    # 1. Try ledger branch first (saved scan snapshots)
    wt = worktree_path(project_root)
    snapshot_path = wt / "audits" / f"{audit_id}.json"
    if snapshot_path.is_file():
        data = json.loads(snapshot_path.read_text())
        return {
            "type": "audit",
            "id": audit_id,
            "exists": True,
            "card_key": data.get("card_key"),
            "status": data.get("status"),
            "summary": data.get("summary"),
            "timestamp": data.get("iso"),
            "detail": data.get("detail", {}),
        }
    
    # 2. Fall back to execution log (existing behavior)
    # ... existing AuditWriter logic ...
```

### 2. Autocomplete: add saved audits to `@audit:` category

In `chat_refs.py`'s autocomplete function, add saved audits from the ledger:

```python
def _autocomplete_audit(query: str, project_root: Path) -> list[dict]:
    results = []
    # Saved scan snapshots from ledger
    wt = worktree_path(project_root)
    audits_dir = wt / "audits"
    if audits_dir.is_dir():
        for f in sorted(audits_dir.glob("*.json"), reverse=True)[:20]:
            snapshot_id = f.stem
            if query.lower() in snapshot_id.lower():
                data = json.loads(f.read_text())
                results.append({
                    "id": snapshot_id,
                    "label": f"{data.get('card_key', '?')} — {data.get('summary', '')}",
                    "detail": data.get("iso", ""),
                })
    # Also include execution log entries (existing)
    # ...
    return results
```

### 3. Frontend: `chatRefClick('audit', ...)` handler

Currently opens a generic modal. Upgrade to show the snapshot detail:
- Card name + emoji
- Status badge (ok/error)
- Key metrics from `detail` dict
- Timestamp
- "Open in Audit Manager" button

## File Checklist

| File | Action | Lines est. |
|------|--------|-----------|
| `src/core/services/chat/chat_refs.py` | MODIFY `_resolve_audit()` + autocomplete | ~40 |
| `_content_chat_refs.html` | MODIFY `chatRefClick('audit', ...)` handler | ~20 |

## Test Criteria

1. Save an audit via Phase 1 → type `@audit:` in chat → autocomplete shows it
2. Send a message with `@audit:<id>` → chip renders with card icon
3. Click the chip → modal shows snapshot detail (card, score, metrics)
4. Old execution-log `@audit:` refs still resolve (backward compat)
