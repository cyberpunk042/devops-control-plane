"""
GitLogAdapter — reads git log of the project repository.

Uses a subprocess git log call with --numstat to get file stats.
No cap — reads all available history.

Sources produced: GIT, PLAN, CONFIG(shared)

Path detection (first match wins):
  .agent/plans/ or .agent/workflows/  → PLAN, commit
  .agent/rules/                        → PLAN, rules
  project.yml                          → CONFIG, promoted
  Dockerfile / docker-compose*         → CONFIG, docker
  .github/workflows/                   → CONFIG, ci
  k8s/ or kubernetes/                  → CONFIG, k8s
  terraform/ or *.tf                   → CONFIG, terraform
  dns/ or cdn/ or CNAME                → CONFIG, dns
  (any other files)                    → GIT, commit
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from src.core.services.timeline.models import (
    Actor,
    ChainRole,
    EntryStatus,
    Locality,
    Source,
    TimelineEntry,
)

logger = logging.getLogger(__name__)

# Merge commit noise: subject starts with "Merge branch" or "Merge pull request"
_MERGE_RE = re.compile(r"^Merge (branch|pull request)\b", re.IGNORECASE)

# ── Path → (Source, subtype) detection rules (evaluated in order) ─────

_PATH_RULES: list[tuple[str, Source, str]] = [
    (".agent/plans/",       Source.PLAN,   "commit"),
    (".agent/workflows/",   Source.PLAN,   "commit"),
    (".agent/rules/",       Source.PLAN,   "rules"),
    ("project.yml",         Source.CONFIG, "promoted"),
    ("Dockerfile",          Source.CONFIG, "docker"),
    ("docker-compose",      Source.CONFIG, "docker"),
    (".github/workflows/",  Source.CONFIG, "ci"),
    ("k8s/",                Source.CONFIG, "k8s"),
    ("kubernetes/",         Source.CONFIG, "k8s"),
    ("terraform/",          Source.CONFIG, "terraform"),
    (".tf",                 Source.CONFIG, "terraform"),
    ("dns/",                Source.CONFIG, "dns"),
    ("cdn/",                Source.CONFIG, "dns"),
    ("CNAME",               Source.CONFIG, "dns"),
]


def _classify_paths(paths: list[str]) -> tuple[Source, str]:
    """Return (source, subtype) for the highest-priority path match."""
    for path in paths:
        for prefix, source, subtype in _PATH_RULES:
            if prefix in path:
                return source, subtype
    return Source.GIT, "commit"


class GitLogAdapter:
    """Reads git log with numstat and produces TimelineEntry list.

    Uses run_git() from src.core.services.git.ops directly.
    No per-entry cap — reads full project history.
    """

    def __init__(self, project_root: Path) -> None:
        self._root = project_root

    def load(self) -> list[TimelineEntry]:
        """Return all non-noise commits from git log."""
        raw_commits = self._read_git_log()
        result: list[TimelineEntry] = []

        for commit in raw_commits:
            try:
                entry = self._normalize(commit)
                if entry is not None:
                    result.append(entry)
            except Exception as exc:
                logger.warning("git_log: skipping commit: %s", exc)

        return result

    def _read_git_log(self) -> list[dict]:
        """Run git log --format with --numstat and parse into dicts."""
        try:
            r = subprocess.run(
                [
                    "git", "log",
                    "--format=COMMIT_START:%H|%P|%ae|%an|%at|%s",
                    "--numstat",
                ],
                cwd=str(self._root),
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            logger.warning("git_log: git subprocess failed: %s", exc)
            return []

        if r.returncode != 0:
            logger.warning("git_log: git log returned %d: %s", r.returncode, r.stderr.strip())
            return []

        return self._parse_git_log_output(r.stdout)

    def _parse_git_log_output(self, output: str) -> list[dict]:
        """Parse interleaved --format and --numstat output.

        Each commit block starts with a line prefixed 'COMMIT_START:'.
        Numstat lines follow (tab-separated: insertions, deletions, path).
        Empty lines separate commits.
        """
        commits: list[dict] = []
        current: dict | None = None

        for line in output.splitlines():
            if line.startswith("COMMIT_START:"):
                if current is not None:
                    commits.append(current)
                parts = line[len("COMMIT_START:"):].split("|", 5)
                if len(parts) < 6:
                    current = None
                    continue
                hash_, parents_str, email, author, ts_str, subject = parts
                try:
                    ts = float(ts_str)
                except ValueError:
                    ts = 0.0
                parent_hashes = [p.strip() for p in parents_str.strip().split() if p.strip()]
                current = {
                    "hash": hash_.strip(),
                    "parents": parent_hashes,
                    "email": email.strip(),
                    "author": author.strip(),
                    "ts": ts,
                    "subject": subject.strip(),
                    "insertions": 0,
                    "deletions": 0,
                    "files": [],
                }
            elif current is not None and line.strip() and "\t" in line:
                # Numstat line: "insertions\tdeletions\tpath"
                parts = line.split("\t", 2)
                if len(parts) == 3:
                    ins_raw, del_raw, path = parts
                    try:
                        current["insertions"] += int(ins_raw) if ins_raw != "-" else 0
                    except ValueError:
                        pass
                    try:
                        current["deletions"] += int(del_raw) if del_raw != "-" else 0
                    except ValueError:
                        pass
                    current["files"].append(path.strip())

        if current is not None:
            commits.append(current)

        return commits

    def _normalize(self, commit: dict) -> TimelineEntry | None:
        ts = commit.get("ts", 0.0)
        if ts == 0.0:
            return None

        subject: str = commit.get("subject", "")
        files: list[str] = commit.get("files", [])
        insertions: int = commit.get("insertions", 0)
        deletions: int = commit.get("deletions", 0)
        commit_hash: str = commit.get("hash", "")

        # Noise filter: drop pure merge commits with no file changes
        if _MERGE_RE.match(subject) and insertions == 0 and deletions == 0:
            return None

        source, subtype = _classify_paths(files)

        summary = subject if subject else commit_hash[:8]

        detail: dict = {
            "author": commit.get("author", ""),
            "email": commit.get("email", ""),
            "insertions": insertions,
            "deletions": deletions,
        }
        if files:
            detail["files"] = files[:50]  # cap file list to avoid bloat

        parents = commit.get("parents", [])
        parent_ref = parents[0] if parents else None

        return TimelineEntry(
            id=f"git:{commit_hash}",
            ts=ts,
            ref=commit_hash,
            source=source,
            subtype=subtype,
            actor=Actor.USER,
            status=EntryStatus.OK,
            severity=None,
            locality=Locality.SHARED,
            env=[],
            modules=[],
            summary=summary,
            detail=detail,
            chain_id=commit_hash,       # runs triggered by this commit share this chain_id
            chain_role=ChainRole.ORIGIN,
            chain_parent_ref=parent_ref,
        )
