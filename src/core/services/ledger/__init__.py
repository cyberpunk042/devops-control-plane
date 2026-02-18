"""
Git-native ledger — operational history stored in git.

Public API::

    from src.core.services.ledger import record_run, list_runs, get_run

    run = Run(run_id="...", type="detect", ...)
    record_run(project_root, run)

    runs = list_runs(project_root, n=20)
    run = get_run(project_root, "run_id")
    events = get_run_events(project_root, "run_id")

Storage:
    - Runs are stored on the ``scp-ledger`` orphan branch via a dedicated
      ``.scp-ledger/`` worktree (gitignored, never touches main).
    - Run metadata is also stored as annotated tags at
      ``refs/tags/scp/run/<run_id>`` pointing to the code commit at run time.
"""

from src.core.services.ledger.ledger_ops import (
    ensure_ledger,
    get_run,
    get_run_events,
    list_runs,
    pull_ledger,
    push_ledger,
    record_run,
)
from src.core.services.ledger.models import Run

__all__ = [
    "Run",
    "ensure_ledger",
    "get_run",
    "get_run_events",
    "list_runs",
    "pull_ledger",
    "push_ledger",
    "record_run",
]
