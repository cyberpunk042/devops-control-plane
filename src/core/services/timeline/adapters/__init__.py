"""
Timeline source adapters — external data readers.

Each adapter reads external data (not produced by the tool) and
returns ``list[TimelineEntry]``. The event store handles everything
the tool itself does.

Adapters:
    GitLogAdapter        — git log (GIT, PLAN, CONFIG shared)
    LedgerRunsAdapter    — .ledger/ scp/run/* tags (CI, TESTS)
    LedgerAuditsAdapter  — .ledger/ scp/audit/* tags (AUDIT shared)
    ChatAdapter          — .ledger/chat/threads/ (CHAT)
    GitHubAdapter        — mediator github.* nodes (PRs, workflows)
"""

from src.core.services.timeline.adapters.git_log import GitLogAdapter
from src.core.services.timeline.adapters.ledger_runs import LedgerRunsAdapter
from src.core.services.timeline.adapters.ledger_audits import LedgerAuditsAdapter
from src.core.services.timeline.adapters.chat import ChatAdapter
from src.core.services.timeline.adapters.github import GitHubAdapter

__all__ = [
    "GitLogAdapter",
    "LedgerRunsAdapter",
    "LedgerAuditsAdapter",
    "ChatAdapter",
    "GitHubAdapter",
]
