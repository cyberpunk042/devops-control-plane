"""
ScanActivityAdapter — reads .state/audit_activity.json.

Covers the widest range of sources: all card scans and all user-initiated
events recorded via record_scan_activity() and record_event().

Sources produced: AUDIT(local), PKG, VAULT, ENV, STACK, PLATFORM,
                  POSTURE, SECURITY, WIZARD, CONFIG(local), CI(scan),
                  TESTS(scan), TOOLS(scan)
"""

from __future__ import annotations

import logging
from pathlib import Path

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

# ── Card → (Source, subtype) mapping ───────────────────────────────────
# Evaluated after special-case wizard/config checks.
# card key may be exact or a prefix (ends with ':')

_CARD_MAP: dict[str, tuple[Source, str | None]] = {
    "packages":   (Source.PKG,      None),
    "security":   (Source.SECURITY, "finding"),
    "vault":      (Source.VAULT,    None),
    "env":        (Source.ENV,      None),
    "stack":      (Source.STACK,    "detected"),
    "platform":   (Source.PLATFORM, "detection"),
    "docker":     (Source.PLATFORM, "docker"),
    "k8s":        (Source.PLATFORM, "k8s"),
    "terraform":  (Source.PLATFORM, "terraform"),
    "git":        (Source.PLATFORM, "git"),
    "ci":         (Source.CI,       "scan"),
    "testing":    (Source.TESTS,    "scan"),
    "tools":      (Source.TOOLS,    None),
    "wiz:detect": (Source.WIZARD,   "detect"),
}

# Cards that are signal regardless of status (always kept)
_ALWAYS_SIGNAL_CARDS = frozenset({
    "wizard", "security", "vault", "env", "packages", "stack",
})

# Cards that are noise when status=ok and no action (pure refresh scans)
_NOISE_SCAN_CARDS = frozenset({
    "docker", "k8s", "terraform", "git", "ci", "testing", "platform",
})

# Audit card prefix
_AUDIT_PREFIX = "audit:"
_POSTURE_PREFIX = "posture:"


def _map_card(
    card: str,
    action: str | None,
    target: str | None,
) -> tuple[Source, str | None]:
    """Map a card key to (Source, subtype).

    Special cases (evaluated first):
      - 'wizard' + action=saved + target=project.yml  → CONFIG, saved
      - 'wizard' (any other action)                   → WIZARD, target or action
      - 'audit:*'                                     → AUDIT, level extracted from key
      - 'posture:*'                                   → POSTURE, subtype from key
    """
    # Wizard / config special cases
    if card == "wizard":
        if action == "saved" and target and "project.yml" in target:
            return Source.CONFIG, "saved"
        return Source.WIZARD, (target or action)

    # Audit cards: audit:l0, audit:l2:risks, audit:scores, etc.
    if card.startswith(_AUDIT_PREFIX):
        rest = card[len(_AUDIT_PREFIX):]  # e.g. "l2", "l2:risks", "scores"
        level = rest.split(":")[0].upper()  # "L2", "SCORES"
        # Normalise to L0/L1/L2
        if level in ("L0", "SYSTEM", "DEPS", "STRUCTURE", "CLIENTS"):
            subtype = "L1"
        elif level in ("L2", "L2:RISKS", "L2:QUALITY", "L2:REPO", "L2:STRUCTURE"):
            subtype = "L2"
        else:
            subtype = level or "L0"
        return Source.AUDIT, subtype

    # Posture cards
    if card.startswith(_POSTURE_PREFIX):
        rest = card[len(_POSTURE_PREFIX):]
        return Source.POSTURE, rest or "scan"

    # Direct lookup
    if card in _CARD_MAP:
        src, sub = _CARD_MAP[card]
        # Refine subtype from action when present
        if action and sub is None:
            return src, action
        return src, sub

    # Unknown card — treat as PLATFORM
    return Source.PLATFORM, card


def _map_status(raw: str) -> EntryStatus:
    if raw == "ok":
        return EntryStatus.OK
    if raw in ("failed", "error"):
        return EntryStatus.FAILED
    if raw in ("warn", "warning"):
        return EntryStatus.WARNING
    return EntryStatus.OK


def _derive_severity(
    source: Source,
    status: EntryStatus,
    card: str,
) -> Severity | None:
    if status == EntryStatus.FAILED:
        if source in (Source.SECURITY, Source.AUDIT):
            return Severity.HIGH
        return Severity.MEDIUM
    if status == EntryStatus.WARNING:
        return Severity.MEDIUM
    return None


def _is_noise(card: str, status: str, action: str | None) -> bool:
    """Return True if this entry should be dropped per the noise contract."""
    if card in _NOISE_SCAN_CARDS and status == "ok" and action is None:
        return True
    return False


class ScanActivityAdapter:
    """Reads .state/audit_activity.json and produces TimelineEntry list.

    One TimelineEntry per activity entry, after noise filtering.
    Uses load_activity() from devops.activity — does not read the file directly.
    """

    def __init__(self, project_root: Path) -> None:
        self._root = project_root

    def load(self) -> list[TimelineEntry]:
        """Return all non-noise entries from audit_activity.json."""
        from src.core.services.devops.activity import load_activity

        raw_entries = load_activity(self._root, n=200)
        result: list[TimelineEntry] = []

        for raw in raw_entries:
            try:
                entry = self._normalize(raw)
                if entry is not None:
                    result.append(entry)
            except Exception as exc:
                logger.warning("scan_activity: skipping corrupt entry: %s", exc)

        return result

    def _normalize(self, raw: dict) -> TimelineEntry | None:
        card: str = raw.get("card", "")
        action: str | None = raw.get("action")
        target: str | None = raw.get("target")
        status_raw: str = raw.get("status", "ok")
        ts: float = float(raw.get("ts", 0.0))

        # Noise filter
        if _is_noise(card, status_raw, action):
            return None

        source, subtype = _map_card(card, action, target)
        status = _map_status(status_raw)
        severity = _derive_severity(source, status, card)

        # Actor: user if action present, scheduler otherwise
        actor = Actor.USER if action else Actor.SCHEDULER

        # Summary: use label prefix + summary
        label: str = raw.get("label", "")
        summary_raw: str = raw.get("summary", "")
        summary = f"{label}: {summary_raw}" if label and not summary_raw.startswith(label) else summary_raw
        if not summary:
            summary = label or card

        # Detail: merge target/before/after into detail dict
        detail: dict = {}
        existing_detail = raw.get("detail")
        if isinstance(existing_detail, dict):
            detail.update(existing_detail)
        if target:
            detail["target"] = target
        if raw.get("before"):
            detail["before"] = raw["before"]
        if raw.get("after"):
            detail["after"] = raw["after"]
        duration = raw.get("duration_s")
        if duration is not None:
            detail["duration_s"] = duration

        # chain_id
        chain_id: str | None = None
        chain_role: ChainRole | None = None
        if source == Source.AUDIT:
            # Link local audit entry to its ledger commit via operation_id in detail
            op_id = detail.get("operation_id") or detail.get("context", {}).get("operation_id") if isinstance(detail.get("context"), dict) else None
            if op_id:
                chain_id = str(op_id)
                chain_role = ChainRole.ORIGIN
        elif source == Source.WIZARD or source == Source.CONFIG:
            # Wizard events are chained to the git commit that follows
            import datetime as _dt
            iso = raw.get("iso", "")
            date_part = iso[:10] if iso else ""
            chain_id = f"wizard:{target or card}:{date_part}" if date_part else None
            chain_role = ChainRole.ORIGIN if chain_id else None

        # Stable unique ID
        entry_id = f"scan_activity:{card}:{ts:.6f}"

        return TimelineEntry(
            id=entry_id,
            ts=ts,
            ref=None,
            source=source,
            subtype=subtype,
            actor=actor,
            status=status,
            severity=severity,
            locality=Locality.LOCAL,
            env=[],
            modules=[],
            summary=summary,
            detail=detail or None,
            chain_id=chain_id,
            chain_role=chain_role,
            chain_parent_ref=None,
        )
