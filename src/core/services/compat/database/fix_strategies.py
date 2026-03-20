#!/usr/bin/env python3
"""Upgrade fix strategies from manual to auto-fixable where possible.

Also fixes the BinOp BitOr quadruple-counting problem.

Usage:
    python -m src.core.services.compat.database.fix_strategies
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

_ENTRIES_DIR = Path(__file__).parent / "entries" / "python"

STRATEGY_FIXES = {
    # ── Upgrade manual → rewrite_expression ──────────────────────
    # These have simple mechanical transforms: remove a keyword argument

    "python.stdlib.dataclass_slots": {
        "action": "set_strategy",
        "strategy": "rewrite_expression",
        "manual_instructions": None,  # Remove manual instructions
    },
    "python.stdlib.dataclass_kw_only": {
        "action": "set_strategy",
        "strategy": "rewrite_expression",
    },
    "python.stdlib.dataclass_match_args": {
        "action": "set_strategy",
        "strategy": "rewrite_expression",
    },
    "python.stdlib.dataclass_frozen_slots": {
        "action": "set_strategy",
        "strategy": "rewrite_expression",
    },
    "python.stdlib.field_kw_only": {
        "action": "set_strategy",
        "strategy": "rewrite_expression",
    },
    "python.stdlib.zip_strict": {
        "action": "set_strategy",
        "strategy": "rewrite_expression",
    },
    "python.stdlib.removesuffix_bytes": {
        "action": "set_strategy",
        "strategy": "rewrite_expression",
    },

    # ── Fix ChainMap | — it's a BinOp false positive ────────────
    # ChainMap | can't be detected as distinct from dict | or int |
    # → Change to info severity since we can't distinguish it
    "python.stdlib.collections_chainmap_or": {
        "action": "change_severity",
        "severity": "info",
    },

    # ── Fix isinstance union — should be on Call node, not BinOp ──
    # The isinstance(x, int|str) detection should match the isinstance Call
    # with arg_is_binop_bitor, not match BinOp directly (which matches ALL |)
    "python.builtins.isinstance_union": {
        "action": "change_detection",
        "ast_type": "Call",
        "match": {"func_id": "isinstance", "arg_is_binop_bitor": True},
    },
}


def apply_fixes(dry_run: bool = False) -> dict:
    stats = {"modified": 0, "entries_fixed": 0, "errors": 0}

    for yml_file in sorted(_ENTRIES_DIR.glob("*.yml")):
        if yml_file.name.startswith("_"):
            continue

        try:
            content = yml_file.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
        except Exception as exc:
            print(f"  ERROR: {yml_file.name}: {exc}")
            stats["errors"] += 1
            continue

        if not data:
            continue

        entries = data if isinstance(data, list) else [data]
        modified = False

        for entry in entries:
            entry_id = entry.get("id", "")
            if entry_id not in STRATEGY_FIXES:
                continue

            fix = STRATEGY_FIXES[entry_id]
            action = fix["action"]

            if action == "set_strategy":
                new_strat = fix["strategy"]
                fix_section = entry.get("fix", {})
                old_strat = fix_section.get("strategy", "?")
                fix_section["strategy"] = new_strat
                if fix.get("manual_instructions") is None and "manual_instructions" in fix_section:
                    del fix_section["manual_instructions"]
                entry["fix"] = fix_section
                modified = True
                stats["entries_fixed"] += 1
                print(f"  ✓ {entry_id}: strategy {old_strat} → {new_strat}")

            elif action == "change_severity":
                new_sev = fix["severity"]
                old_sev = entry.get("severity", "?")
                entry["severity"] = new_sev
                modified = True
                stats["entries_fixed"] += 1
                print(f"  ✓ {entry_id}: severity {old_sev} → {new_sev}")

            elif action == "change_detection":
                detection = entry.get("detection", {})
                primary = detection.get("primary", {})
                primary["ast_type"] = fix["ast_type"]
                primary["match"] = fix["match"]
                modified = True
                stats["entries_fixed"] += 1
                print(f"  ✓ {entry_id}: detection → {fix['ast_type']} {fix['match']}")

        if modified:
            if not dry_run:
                output = yaml.dump(
                    data if isinstance(data, list) else data,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                )
                yml_file.write_text(output, encoding="utf-8")
            stats["modified"] += 1

    return stats


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("DRY RUN\n")
    else:
        print("APPLYING STRATEGY FIXES\n")

    stats = apply_fixes(dry_run=dry_run)
    print(f"\nDone: {stats['entries_fixed']} entries fixed in {stats['modified']} files "
          f"({stats['errors']} errors)")
