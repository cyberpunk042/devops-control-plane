"""
GitHubAdapter — reads github.pulls, github.runs, github.workflows
from mediator disk shards.

Produces individual timeline entries for each PR and workflow run.
Data comes from the mediator cache, not HTTP.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.core.services.timeline.adapters._util import iso_to_ts
from src.core.services.timeline.models import (
    Actor,
    ChainRole,
    EntryStatus,
    Locality,
    Severity,
    Source,
    TimelineEntry,
)

logger = logging.getLogger(__name__)


class GitHubAdapter:

    def __init__(self, project_root: Path) -> None:
        self._root = project_root

    def load(self) -> list[TimelineEntry]:
        result: list[TimelineEntry] = []
        result.extend(self._load_pulls())
        result.extend(self._load_runs())
        return result

    def _peek(self, node: str) -> dict | None:
        p = self._root / ".state" / "mediator_index" / f"{node}.json"
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _load_pulls(self) -> list[TimelineEntry]:
        data = self._peek("github.pulls")
        if not data or not data.get("available"):
            return []
        out = []
        for pr in data.get("pulls", []):
            number = pr.get("number", 0)
            state = (pr.get("state") or "").lower()
            merged = pr.get("mergedAt") is not None
            title = pr.get("title", "")
            ts = iso_to_ts(pr.get("updatedAt") or pr.get("createdAt", ""))
            if ts == 0.0:
                continue
            if merged:
                sub = "pr:merged"
            elif state == "closed":
                sub = "pr:closed"
            else:
                sub = "pr:opened"
            out.append(TimelineEntry(
                id=f"github:pr:{number}", ts=ts, ref=str(number),
                source=Source.GIT, subtype=sub,
                actor=Actor.USER,
                status=EntryStatus.OK if sub != "pr:closed" else EntryStatus.WARNING,
                severity=None, locality=Locality.SHARED,
                env=[], modules=[],
                summary=f"#{number} {title}",
                detail={"number": number, "state": state, "merged": merged,
                        "url": pr.get("url", "")},
                chain_id=f"pr:{number}",
                chain_role=ChainRole.ORIGIN if sub == "pr:opened" else ChainRole.TERMINAL,
                chain_parent_ref=None,
            ))
        return out

    def _load_runs(self) -> list[TimelineEntry]:
        data = self._peek("github.runs")
        if not data or not data.get("available"):
            return []
        out = []
        for run in data.get("runs", []):
            rid = run.get("databaseId", 0)
            name = run.get("name", "")
            conclusion = (run.get("conclusion") or "").lower()
            ts = iso_to_ts(run.get("createdAt", ""))
            if ts == 0.0:
                continue
            if conclusion == "success":
                sub, st, sev = "workflow:completed", EntryStatus.OK, None
            elif conclusion == "failure":
                sub, st, sev = "workflow:failed", EntryStatus.FAILED, Severity.MEDIUM
            else:
                sub, st, sev = "workflow:triggered", EntryStatus.OK, None
            out.append(TimelineEntry(
                id=f"github:run:{rid}", ts=ts, ref=str(rid),
                source=Source.CI, subtype=sub,
                actor=Actor.AUTOMATION, status=st, severity=sev,
                locality=Locality.SHARED, env=[], modules=[],
                summary=f"{name}: {conclusion or 'triggered'}",
                detail={"run_id": rid, "name": name,
                        "event": run.get("event", ""),
                        "branch": run.get("headBranch", ""),
                        "url": run.get("url", "")},
                chain_id=f"workflow:{rid}",
                chain_role=ChainRole.ORIGIN if sub == "workflow:triggered" else ChainRole.TERMINAL,
                chain_parent_ref=None,
            ))
        return out
