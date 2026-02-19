"""
Git-native ledger — audit snapshots stored in git.

Public API::

    from src.core.services.ledger import save_audit_snapshot, list_saved_audits

Storage:
    - Audit snapshots are stored on the ``scp-ledger`` orphan branch via a
      dedicated ``.ledger/`` worktree (gitignored, never touches main).
    - Audit metadata is also stored as annotated tags at
      ``refs/tags/scp/audit/<snapshot_id>``.

Runs are ephemeral and stored locally in ``.state/runs.jsonl``.
See ``run_tracker.py`` for run storage.
"""

from src.core.services.ledger.ledger_ops import (
    ensure_ledger,
    pull_ledger,
    push_ledger,
    save_audit_snapshot,
    list_saved_audits,
    get_saved_audit,
    delete_saved_audit,
)

__all__ = [
    "ensure_ledger",
    "pull_ledger",
    "push_ledger",
    "save_audit_snapshot",
    "list_saved_audits",
    "get_saved_audit",
    "delete_saved_audit",
]
