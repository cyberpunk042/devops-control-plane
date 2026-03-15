"""
Timeline source adapters — one per raw data source.

Each adapter reads its assigned raw source and returns ``list[TimelineEntry]``.
Adapters do not call the mediator. The mediator resolver calls the adapter.

Adapters:
    ScanActivityAdapter  — .state/audit_activity.json (17 sources via card mapping)
    CliOpsAdapter        — .state/audit.ndjson (TOOLS, BACKUP, VAULT, ENV, PKG, AUDIT)
    GitLogAdapter        — git log (GIT, PLAN, CONFIG shared)
    LedgerRunsAdapter    — .ledger/ scp/run/* tags (CI, TESTS)
    LedgerAuditsAdapter  — .ledger/ scp/audit/* tags (AUDIT shared)
    ChatAdapter          — .ledger/chat/threads/ (CHAT)
    RunsAdapter          — .state/runs.jsonl (all @run_tracked operations)
"""

from src.core.services.timeline.adapters.scan_activity import ScanActivityAdapter
from src.core.services.timeline.adapters.cli_ops import CliOpsAdapter
from src.core.services.timeline.adapters.git_log import GitLogAdapter
from src.core.services.timeline.adapters.ledger_runs import LedgerRunsAdapter
from src.core.services.timeline.adapters.ledger_audits import LedgerAuditsAdapter
from src.core.services.timeline.adapters.chat import ChatAdapter
from src.core.services.timeline.adapters.runs import RunsAdapter
from src.core.services.timeline.adapters.github import GitHubAdapter

__all__ = [
    "ScanActivityAdapter",
    "CliOpsAdapter",
    "GitLogAdapter",
    "LedgerRunsAdapter",
    "LedgerAuditsAdapter",
    "ChatAdapter",
    "RunsAdapter",
    "GitHubAdapter",
]
