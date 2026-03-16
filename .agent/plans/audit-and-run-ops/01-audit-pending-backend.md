# Phase 1: Audit Pending — Backend

> **Status**: Draft  
> **Depends on**: Nothing  
> **Resolved**: Q1=full card data blob, Q2=persisted to `.state/` like cache

---

## Goal

When `devops_cache.get_cached()` computes a fresh result (cache miss → recompute), automatically stage a "pending audit snapshot" with the **full card data blob**. The user can later save it to git or discard it. Pending audits persist across server restarts (`.state/pending_audits.json`), just like the cache itself.

## What Changes

### 1. New file: `src/core/services/audit_staging.py`

Manages the pending audit staging area. Persisted to `.state/pending_audits.json`.

```python
"""
Audit staging — pending audit snapshots that can be saved to git or discarded.

Each time devops_cache computes a fresh result, a snapshot is staged here.
The user can then:
  - Save: promotes to .scp-ledger/audits/<snapshot_id>.json + git tag
  - Discard: removes from pending list (cache is NOT affected)

Persistence: .state/pending_audits.json (survives server restarts)
"""

@dataclass
class PendingAudit:
    snapshot_id: str          # e.g. "security_20260218_150300"
    card_key: str             # e.g. "security", "testing", "k8s"
    computed_at: float        # unix timestamp
    iso: str                  # ISO 8601 formatted time
    status: str               # "ok" or "error"
    duration_s: float         # how long the scan took
    summary: str              # one-line human summary (from _extract_summary)
    data: dict                # FULL card data blob (the entire compute result)

# ── Public API ──────────────────────────────────────

def stage_audit(
    project_root: Path,
    card_key: str,
    status: str,
    elapsed_s: float,
    data: dict,
    summary: str,
) -> str:
    """Create a pending audit snapshot from a cache computation.
    
    Called by devops_cache.get_cached() after a fresh compute.
    Returns the snapshot_id.
    
    Generates snapshot_id as: {card_key}_{YYYYMMDD}_{HHMMSS}
    """

def list_pending(project_root: Path) -> list[dict]:
    """Return all pending (not saved, not discarded) snapshots.
    
    Returns list of dicts with snapshot_id, card_key, iso, status, 
    summary, duration_s. Does NOT include the full data blob
    (that would be too large for a list response).
    """

def get_pending(project_root: Path, snapshot_id: str) -> dict | None:
    """Return full detail for a single pending audit (includes data blob)."""

def save_audit(project_root: Path, snapshot_id: str) -> dict:
    """Promote a pending snapshot to the ledger branch.
    
    1. Load the full pending snapshot
    2. Write to .scp-ledger/audits/{snapshot_id}.json
    3. Create annotated git tag scp/audit/{snapshot_id}
    4. Remove from pending list
    5. Persist
    6. Return metadata for frontend (snapshot_id, card_key, etc.)
    """

def save_all_pending(project_root: Path) -> list[str]:
    """Save all pending snapshots. Returns list of saved snapshot_ids."""

def discard_audit(project_root: Path, snapshot_id: str) -> bool:
    """Remove a snapshot from the pending list. Cache unaffected.
    Returns True on success."""

def discard_all_pending(project_root: Path) -> int:
    """Discard all pending. Returns count discarded."""

# ── Persistence ──────────────────────────────────────

def _persist(project_root: Path, pending: list[PendingAudit]) -> None:
    """Write pending list to .state/pending_audits.json (full data blobs included)."""

def _load(project_root: Path) -> list[PendingAudit]:
    """Load pending list from .state/pending_audits.json."""
```

### 2. Modified: `src/core/services/devops_cache.py`

In `get_cached()`, after `_record_activity()` (line ~404), add staging call:

```python
# ── Stage pending audit ─────────────────────────────────
if status == "ok":
    try:
        from src.core.services.audit_staging import stage_audit
        sid = stage_audit(
            project_root, card_key, status, elapsed,
            data, _extract_summary(card_key, data),
        )
        _publish_event("audit:pending", key=card_key, snapshot_id=sid)
    except Exception:
        pass  # staging must never break the cache
```

**Key**: This is ~6 lines, wrapped in try/except so it never breaks the cache. Same pattern as `_publish_event()`.

### 3. Modified: `src/core/services/ledger/ledger_ops.py`

Add `save_audit_snapshot()`:

```python
def save_audit_snapshot(
    project_root: Path,
    snapshot_id: str,
    snapshot_data: dict,
) -> str:
    """Write an audit snapshot to .scp-ledger/audits/<snapshot_id>.json
    and create an annotated tag at scp/audit/<snapshot_id>.
    
    Args:
        project_root: Repository root.
        snapshot_id: e.g. "security_20260218_150300"
        snapshot_data: Full snapshot dict including card_key, data, etc.
    
    Returns:
        The snapshot_id.
    """
    wt = ensure_ledger(project_root)
    
    # Write to audits directory
    audit_dir = wt / "audits"
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_path = audit_dir / f"{snapshot_id}.json"
    audit_path.write_text(
        json.dumps(snapshot_data, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    
    # Commit
    ledger_add_and_commit(
        project_root,
        paths=[f"audits/{snapshot_id}.json"],
        message=f"audit: {snapshot_data.get('card_key', '?')} {snapshot_id}",
    )
    
    # Tag
    head_sha = current_head_sha(project_root)
    if head_sha:
        tag_name = f"scp/audit/{snapshot_id}"
        create_run_tag(  # reuse the tag creation helper
            project_root,
            tag_name=tag_name,
            target_sha=head_sha,
            message=json.dumps({
                "snapshot_id": snapshot_id,
                "card_key": snapshot_data.get("card_key"),
                "status": snapshot_data.get("status"),
                "iso": snapshot_data.get("iso"),
                "summary": snapshot_data.get("summary"),
            }),
        )
    
    return snapshot_id
```

### 4. New API routes in `src/ui/web/routes_audit.py`

```python
# ── Audit staging endpoints ─────────────────────────────────

@audit_bp.route("/audits/pending")
def audits_pending():
    """GET — list all unsaved audit snapshots (metadata only, no data blobs)."""
    from src.core.services.audit_staging import list_pending
    return jsonify({"pending": list_pending(_project_root())})

@audit_bp.route("/audits/pending/<snapshot_id>")
def audits_pending_detail(snapshot_id):
    """GET — full detail for a single pending audit (includes data blob)."""
    from src.core.services.audit_staging import get_pending
    result = get_pending(_project_root(), snapshot_id)
    if result is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(result)

@audit_bp.route("/audits/save", methods=["POST"])
def audits_save():
    """POST {snapshot_ids: [...] | "all"} — save to git ledger."""
    from src.core.services.audit_staging import save_audit, save_all_pending
    body = request.get_json(silent=True) or {}
    ids = body.get("snapshot_ids", "all")
    
    if ids == "all":
        saved = save_all_pending(_project_root())
    else:
        saved = []
        for sid in ids:
            try:
                save_audit(_project_root(), sid)
                saved.append(sid)
            except Exception as e:
                pass  # log but continue
    
    return jsonify({"saved": saved, "count": len(saved)})

@audit_bp.route("/audits/discard", methods=["POST"])
def audits_discard():
    """POST {snapshot_ids: [...] | "all"} — discard from pending."""
    from src.core.services.audit_staging import discard_audit, discard_all_pending
    body = request.get_json(silent=True) or {}
    ids = body.get("snapshot_ids", "all")
    
    if ids == "all":
        count = discard_all_pending(_project_root())
    else:
        count = sum(1 for sid in ids if discard_audit(_project_root(), sid))
    
    return jsonify({"discarded": count})
```

### 5. New SSE event type

`audit:pending` — emitted by `devops_cache.get_cached()` after staging.

Payload: `{ key: "security", snapshot_id: "security_20260218_150300" }`

Added to `_event_stream.html` `_eventTypes` array in Phase 2.

## File Checklist

| File | Action | Lines est. |
|------|--------|-----------|
| `src/core/services/audit_staging.py` | **CREATE** | ~150 |
| `src/core/services/devops_cache.py` | ADD ~6 lines in `get_cached()` | ~6 |
| `src/core/services/ledger/ledger_ops.py` | ADD `save_audit_snapshot()` | ~50 |
| `src/ui/web/routes_audit.py` | ADD 4 endpoints | ~60 |

## Test Criteria

1. Refresh a DevOps card → pending audit appears in `GET /api/audits/pending`
2. `GET /api/audits/pending/<id>` returns full data blob
3. `POST /api/audits/save` → snapshot appears in `.scp-ledger/audits/` + git tag
4. `POST /api/audits/discard` → snapshot removed from pending, cache unaffected
5. SSE `audit:pending` event fires with correct `card_key` and `snapshot_id`
6. Server restart → pending list reloaded from `.state/pending_audits.json`
7. Large card data blobs (50-200KB) persist and restore correctly
