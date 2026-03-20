#!/usr/bin/env python3
"""Audit all feature database entries for detection quality.

Categorizes every entry by detection precision and fix coverage.
Identifies broad detection rules that produce false positives.
Reports what needs to be fixed and how.

Usage:
    python -m src.core.services.compat.database.audit_entries
    python -m src.core.services.compat.database.audit_entries --fix-yaml
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# ── Entry quality categories ─────────────────────────────────────

QUALITY_PRECISE = "precise"          # Detection is specific — low false positive risk
QUALITY_BROAD = "broad"              # Detection matches too widely — high FP risk
QUALITY_UNDETECTABLE = "undetectable"  # Feature can't be detected via AST
QUALITY_NEEDS_UPGRADE = "needs_upgrade"  # Has new matchers available but doesn't use them


@dataclass
class EntryAudit:
    """Audit result for a single database entry."""
    entry_id: str
    feature_name: str
    introduced: str
    severity: str
    fix_strategy: str
    detection_type: str           # ast_type of primary rule
    detection_match: dict
    quality: str                  # precise / broad / undetectable / needs_upgrade
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    estimated_fp_rate: str = ""   # "none", "low", "high", "extreme"


def audit_entry(entry) -> EntryAudit:
    """Audit a single entry's detection quality."""
    ast_type = entry.detection.primary.ast_type
    match = entry.detection.primary.match
    fix = entry.fix.strategy.value
    sev = entry.severity.value

    audit = EntryAudit(
        entry_id=entry.id,
        feature_name=entry.feature_name,
        introduced=entry.introduced,
        severity=sev,
        fix_strategy=fix,
        detection_type=ast_type,
        detection_match=dict(match),
        quality=QUALITY_PRECISE,
    )

    # ── Check: Import-based detection (usually precise) ──────
    if ast_type in ("Import", "ImportFrom"):
        if "names_contains" in match:
            audit.estimated_fp_rate = "none"
            return audit
        # ImportFrom without names_contains — still usually OK
        audit.estimated_fp_rate = "low"
        return audit

    # ── Check: func_attr without object check ────────────────
    if "func_attr" in match and "func_value_id" not in match:
        method = match.get("func_attr", "")

        # Common method names that exist on many objects
        common_methods = {
            "compile", "match", "walk", "glob", "connect", "read",
            "write", "close", "open", "get", "set", "add", "remove",
            "update", "clear", "copy", "pop", "append", "extend",
            "insert", "sort", "reverse", "count", "index", "find",
            "replace", "split", "join", "strip", "lower", "upper",
            "format", "encode", "decode", "dump", "dumps", "load",
            "loads", "parse", "warn", "error", "info", "debug",
            "cancel", "send", "recv", "accept", "listen", "bind",
            "seek", "tell", "flush", "truncate", "serialize",
            "deserialize", "extractall", "reader", "writer",
            "Formatter", "create_default_context", "localcontext",
            "fromisoformat", "array", "bisect_left", "randbytes",
            "bit_count", "add_note", "cancelling",
        }

        if method in common_methods:
            audit.quality = QUALITY_BROAD
            audit.issues.append(
                f"func_attr='{method}' matches ANY .{method}() call, "
                f"not just the intended object"
            )
            audit.suggestions.append(
                f"Add func_value_id to constrain which object .{method}() is called on"
            )
            audit.estimated_fp_rate = "extreme"
        else:
            # Less common method names — lower FP risk but still flagged
            audit.quality = QUALITY_NEEDS_UPGRADE
            audit.issues.append(f"func_attr='{method}' without func_value_id")
            audit.suggestions.append("Add func_value_id for precision")
            audit.estimated_fp_rate = "high"

        # Check if has_keyword would help
        if "has_keyword" not in match:
            # Many of these are about new keyword args (walk_up, strict, etc.)
            feature_lower = entry.feature_name.lower()
            if any(kw in feature_lower for kw in [
                "walk_up", "strict", "kw_only", "slots", "frozen",
                "delete_on_close", "root_dir", "case_sensitive",
                "autocommit", "match_args", "msg=",
            ]):
                audit.suggestions.append(
                    "Use has_keyword to match specific keyword argument"
                )

        return audit

    # ── Check: func_id without keyword check ─────────────────
    if "func_id" in match:
        func_name = match.get("func_id", "")

        # Decorators/calls that need keyword arg checks
        needs_keyword = {
            "dataclass": ["slots", "kw_only", "match_args", "frozen"],
            "field": ["kw_only"],
            "zip": ["strict"],
            "TypeVar": ["default"],
        }

        if func_name in needs_keyword and "has_keyword" not in match:
            audit.quality = QUALITY_BROAD
            audit.issues.append(
                f"func_id='{func_name}' matches ALL {func_name}() calls, "
                f"not just ones with specific keyword arguments"
            )
            audit.suggestions.append(
                f"Add has_keyword={needs_keyword[func_name]} to match only "
                f"the specific feature usage"
            )
            audit.estimated_fp_rate = "high"
            return audit

        audit.estimated_fp_rate = "low"
        return audit

    # ── Check: BinOp BitOr without context ───────────────────
    if ast_type == "BinOp" and match.get("op_type") == "BitOr":
        if "left_is_dict" not in match and "right_is_dict" not in match:
            feature_lower = entry.feature_name.lower()
            if "dict" in feature_lower:
                audit.quality = QUALITY_BROAD
                audit.issues.append(
                    "BitOr matches ALL | operators — dict merge, "
                    "bitwise OR, set union are indistinguishable"
                )
                audit.suggestions.append(
                    "Add left_is_dict/right_is_dict for dict merge detection, "
                    "or use context=runtime to exclude annotations"
                )
                audit.estimated_fp_rate = "extreme"
            elif "union" in feature_lower or "isinstance" in feature_lower:
                audit.quality = QUALITY_NEEDS_UPGRADE
                audit.issues.append("BitOr in runtime context — may be type union or bitwise")
                audit.estimated_fp_rate = "high"
            return audit

    # ── Check: undetectable features ─────────────────────────
    # Features that are about string CONTENT, behavioral changes, etc.
    undetectable_keywords = [
        "possessive quantifier", "atomic group", "case sensitivity",
        "accepts more", "improvements", "behavioral", "format string",
    ]
    feature_lower = entry.feature_name.lower()
    desc_lower = (entry.description or "").lower()

    for kw in undetectable_keywords:
        if kw in feature_lower or kw in desc_lower:
            if ast_type == "Call" and "func_attr" in match:
                audit.quality = QUALITY_UNDETECTABLE
                audit.issues.append(
                    f"Feature '{entry.feature_name}' is a behavioral/content change "
                    f"that can't be detected via AST node matching"
                )
                audit.suggestions.append(
                    "Remove from AST detection or move to manual audit checklist"
                )
                audit.estimated_fp_rate = "extreme"
                return audit

    # ── Default: looks precise enough ────────────────────────
    audit.estimated_fp_rate = "low"
    return audit


def audit_all():
    """Audit all entries and print report."""
    from .registry import FeatureRegistry

    reg = FeatureRegistry.load(language="python")
    entries = reg.above_version("python", "3.8")

    audits: list[EntryAudit] = []
    for entry in entries:
        audits.append(audit_entry(entry))

    # ── Report ───────────────────────────────────────────────
    by_quality = Counter(a.quality for a in audits)
    by_fp = Counter(a.estimated_fp_rate for a in audits)
    by_fix = Counter(a.fix_strategy for a in audits)

    print(f"╔══════════════════════════════════════════════════════════════╗")
    print(f"║  COMPAT DATABASE AUDIT — {len(audits)} entries above Python 3.8       ║")
    print(f"╠══════════════════════════════════════════════════════════════╣")
    print(f"║  Quality:                                                    ║")
    print(f"║    Precise:       {by_quality.get(QUALITY_PRECISE, 0):4d}  (good detection rules)            ║")
    print(f"║    Needs upgrade: {by_quality.get(QUALITY_NEEDS_UPGRADE, 0):4d}  (new matchers available)          ║")
    print(f"║    Broad:         {by_quality.get(QUALITY_BROAD, 0):4d}  (high false positive risk)         ║")
    print(f"║    Undetectable:  {by_quality.get(QUALITY_UNDETECTABLE, 0):4d}  (can't detect via AST)            ║")
    print(f"║                                                              ║")
    print(f"║  False positive risk:                                        ║")
    print(f"║    None:    {by_fp.get('none', 0):4d}    Low:    {by_fp.get('low', 0):4d}                         ║")
    print(f"║    High:    {by_fp.get('high', 0):4d}    Extreme:{by_fp.get('extreme', 0):4d}                         ║")
    print(f"║                                                              ║")
    print(f"║  Fix strategies:                                             ║")
    for strat, count in sorted(by_fix.items(), key=lambda x: -x[1]):
        print(f"║    {strat:30s} {count:4d}                         ║")
    print(f"╚══════════════════════════════════════════════════════════════╝")

    # ── Detail: entries that need work ────────────────────────
    needs_work = [a for a in audits if a.quality != QUALITY_PRECISE]
    if needs_work:
        print(f"\n{'='*70}")
        print(f"ENTRIES THAT NEED WORK ({len(needs_work)})")
        print(f"{'='*70}")

        for quality in [QUALITY_BROAD, QUALITY_UNDETECTABLE, QUALITY_NEEDS_UPGRADE]:
            group = [a for a in needs_work if a.quality == quality]
            if not group:
                continue
            print(f"\n── {quality.upper()} ({len(group)} entries) ──\n")
            for a in sorted(group, key=lambda x: x.feature_name):
                print(f"  {a.entry_id}")
                print(f"    Feature:   {a.feature_name} ({a.introduced}+)")
                print(f"    Severity:  {a.severity}  Fix: {a.fix_strategy}")
                print(f"    Detection: {a.detection_type} {a.detection_match}")
                print(f"    FP risk:   {a.estimated_fp_rate}")
                for issue in a.issues:
                    print(f"    ❌ {issue}")
                for sug in a.suggestions:
                    print(f"    💡 {sug}")
                print()

    return audits


if __name__ == "__main__":
    audit_all()
