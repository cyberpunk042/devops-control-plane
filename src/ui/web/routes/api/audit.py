"""API audit — audit log and activity."""

from __future__ import annotations

from flask import jsonify, request

from src.ui.web.helpers import project_root as _project_root

from . import api_bp


@api_bp.route("/audit")
def api_audit():  # type: ignore[no-untyped-def]
    """Recent audit log entries (CLI operations from audit.ndjson)."""
    from src.core.persistence.audit import AuditWriter

    n = request.args.get("n", 20, type=int)
    audit = AuditWriter(project_root=_project_root())
    entries = audit.read_recent(n)

    return jsonify({
        "total": audit.entry_count(),
        "entries": [e.model_dump(mode="json") for e in entries],
    })


@api_bp.route("/audit/activity")
def api_audit_activity():  # type: ignore[no-untyped-def]
    """Recent audit scan activity (DevOps + Audit tab scans)."""
    from src.core.services.devops import cache as devops_cache

    n_legacy = request.args.get("n", 0, type=int)
    all_entries = devops_cache.load_activity(
        _project_root(), n=max(n_legacy, 2000)
    )
    total_all = len(all_entries)

    all_entries = list(reversed(all_entries))

    card_filter = request.args.get("card", "", type=str).strip()
    search_q = request.args.get("q", "", type=str).strip().lower()

    filtered = all_entries
    if card_filter:
        filtered = [e for e in filtered if e.get("card") == card_filter]
    if search_q:
        def _matches(entry: dict) -> bool:
            for field in ("label", "summary", "target", "card"):
                val = entry.get(field, "")
                if val and search_q in str(val).lower():
                    return True
            return False
        filtered = [e for e in filtered if _matches(e)]

    total_filtered = len(filtered)

    offset = request.args.get("offset", 0, type=int)
    limit = request.args.get("limit", n_legacy or 50, type=int)
    page = filtered[offset : offset + limit]

    cards_seen: list[str] = []
    cards_set: set[str] = set()
    for e in all_entries:
        c = e.get("card", "")
        if c and c not in cards_set:
            cards_seen.append(c)
            cards_set.add(c)

    return jsonify({
        "total_all": total_all,
        "total_filtered": total_filtered,
        "offset": offset,
        "limit": limit,
        "has_more": (offset + limit) < total_filtered,
        "cards": sorted(cards_seen),
        "entries": page,
    })
