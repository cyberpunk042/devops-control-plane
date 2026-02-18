"""
Ledger models — data shapes for runs and events.

These are pure Pydantic models with no I/O. They define what gets
written to the ledger branch and embedded in annotated tags.
"""

from __future__ import annotations

import secrets
import string
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _make_run_id(run_type: str) -> str:
    """Generate a unique run ID: <ISO-timestamp>_<type>_<4-char-random>.

    Examples:
        run_20260217T204500Z_detect_a1b2
        run_20260217T210800Z_k8s-apply_c3d4
    """
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    # Sanitise type for filesystem safety (replace colons with dashes)
    safe_type = run_type.replace(":", "-").replace("/", "-")[:30]
    suffix = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(4))
    return f"run_{ts}_{safe_type}_{suffix}"


class Run(BaseModel):
    """A recorded execution run.

    Represents a single significant operation that was executed.
    Stored as:
      - ``run.json`` on the ``scp-ledger`` branch
      - Compact JSON in an annotated tag message at ``scp/run/<run_id>``
    """

    run_id: str = ""
    type: str = ""                              # "detect", "apply", "generate", etc.
    subtype: str = ""                           # more specific: "k8s:apply", "vault:unlock"
    status: Literal["ok", "failed", "partial"] = "ok"
    user: str = ""                              # from git config user.name or system
    code_ref: str = ""                          # commit SHA that was HEAD at run time
    started_at: str = Field(default_factory=_now_iso)
    ended_at: str = Field(default_factory=_now_iso)
    duration_ms: int = 0
    environment: str = ""
    modules_affected: list[str] = Field(default_factory=list)
    summary: str = ""                           # one-line human summary
    metadata: dict[str, Any] = Field(default_factory=dict)

    def ensure_id(self) -> str:
        """Ensure run_id is set, generating one from type if empty."""
        if not self.run_id:
            self.run_id = _make_run_id(self.type or "unknown")
        return self.run_id

    def to_tag_message(self) -> str:
        """Compact single-line JSON for the annotated tag message."""
        return self.model_dump_json()

    @classmethod
    def from_tag_message(cls, message: str) -> Run:
        """Parse a Run from an annotated tag message."""
        return cls.model_validate_json(message.strip())


class RunEvent(BaseModel):
    """A single fine-grained event within a run's event stream.

    Stored as one JSONL line in ``events.jsonl``.
    """

    seq: int = 0
    ts: str = Field(default_factory=_now_iso)
    type: str = ""                  # "adapter:execute", "run:complete", etc.
    adapter: str = ""
    action_id: str = ""
    target: str = ""
    status: str = ""                # "ok", "failed", "skipped"
    duration_ms: int = 0
    detail: dict[str, Any] = Field(default_factory=dict)
