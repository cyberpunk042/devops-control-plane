#!/usr/bin/env python3
"""Fix broad detection rules in the feature database.

Applies targeted fixes to YAML entries identified by the audit:
- Adds has_keyword constraints to func_id/func_attr entries
- Removes undetectable entries (behavioral changes, string content)
- Downgrades re pattern entries to info severity

Usage:
    python -m src.core.services.compat.database.fix_broad_entries
    python -m src.core.services.compat.database.fix_broad_entries --dry-run
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

_ENTRIES_DIR = Path(__file__).parent / "entries" / "python"


# ── Fix definitions ──────────────────────────────────────────────

FIXES_ROUND2 = {
    # Entries already fixed with has_keyword but can also benefit from func_value_id
    "python.stdlib.glob_root_dir": {
        "action": "add_match_key",
        "key": "func_value_id",
        "value": ["glob", "Path"],
    },
    "python.stdlib.sqlite3_autocommit": {
        "action": "add_match_key",
        "key": "func_value_id",
        "value": "sqlite3",
    },
    "python.stdlib.csv_reader_strict": {
        "action": "add_match_key",
        "key": "func_value_id",
        "value": "csv",
    },

    # RE entries — add func_value_id=re so only re.compile() matches
    "python.stdlib.re_possessive": {
        "action": "add_match_key",
        "key": "func_value_id",
        "value": "re",
    },
    "python.stdlib.re_atomic_groups": {
        "action": "add_match_key",
        "key": "func_value_id",
        "value": "re",
    },
    "python.stdlib.re_possessive_311": {
        "action": "add_match_key",
        "key": "func_value_id",
        "value": "re",
    },

    # Other func_value_id additions for precision
    "python.stdlib.random_randbytes": {
        "action": "add_match_key",
        "key": "func_value_id",
        "value": "random",
    },
    "python.stdlib.json_default_improved": {
        "action": "add_match_key",
        "key": "func_value_id",
        "value": "json",
    },
    "python.stdlib.logging_taskname": {
        "action": "add_match_key",
        "key": "func_value_id",
        "value": "logging",
    },
    "python.stdlib.ssl_default_context": {
        "action": "add_match_key",
        "key": "func_value_id",
        "value": "ssl",
    },
    "python.stdlib.warnings_filters": {
        "action": "add_match_key",
        "key": "func_value_id",
        "value": "warnings",
    },
    "python.stdlib.datetime_fromisoformat": {
        "action": "add_match_key",
        "key": "func_value_id",
        "value": "datetime",
    },
    "python.stdlib.decimal_localcontext": {
        "action": "add_match_key",
        "key": "func_value_id",
        "value": "decimal",
    },
    "python.stdlib.int_bit_count": {
        "action": "noop",  # bit_count is unique enough
    },
    "python.stdlib.sqlite3_serialize": {
        "action": "noop",  # serialize is called on connection objects
    },

    # BinOp entries — isinstance union needs arg_is_binop_bitor on the isinstance call
    # The dict merge entries can't be further refined without type inference
    # → Change dict entries to only match when context is clearly dict
    "python.builtins.dict_merge_operator": {
        "action": "noop",  # Can't fix without type inference — accept FP
    },
    "python.builtins.dict_union_or": {
        "action": "noop",  # Same
    },

    # zip — add has_keyword (may already have it)
    "python.stdlib.zip_strict": {
        "action": "add_has_keyword",
        "keyword": "strict",
    },

    # type parameter defaults — different from TypeVar defaults
    "python.syntax.type_defaults": {
        "action": "noop",  # func_id TypeVar — broad but correct for the feature
    },
}

FIXES = {
    # RE entries — pattern syntax, not detectable via Call node
    # → Change severity to info, add note explaining limitation
    "python.stdlib.re_possessive": {
        "action": "change_severity",
        "new_severity": "info",
        "new_error_type": "behavioral_change",
        "add_description": "Note: AST detection matches re.compile() calls broadly. "
                          "The actual feature is possessive quantifier syntax within pattern strings.",
    },
    "python.stdlib.re_atomic_groups": {
        "action": "change_severity",
        "new_severity": "info",
        "new_error_type": "behavioral_change",
        "add_description": "Note: AST detection matches re.compile() calls broadly. "
                          "The actual feature is atomic group syntax within pattern strings.",
    },
    "python.stdlib.re_possessive_311": {
        "action": "change_severity",
        "new_severity": "info",
        "new_error_type": "behavioral_change",
    },

    # Path entries — remove entries that match too broadly
    "python.stdlib.pathlib_walk": {
        "action": "add_match_key",
        "key": "func_value_id",
        "value": "Path",
    },
    "python.stdlib.pathlib_relative_to_walk": {
        "action": "add_has_keyword",
        "keyword": "walk_up",
    },
    "python.stdlib.pathlib_match_pattern": {
        "action": "change_severity",
        "new_severity": "info",
        "new_error_type": "behavioral_change",
    },
    "python.stdlib.pathlib_is_relative_to": {
        "action": "noop",  # is_relative_to is unique enough
    },
    "python.stdlib.pathlib_readlink": {
        "action": "noop",
    },
    "python.stdlib.pathlib_with_stem": {
        "action": "noop",
    },
    "python.stdlib.pathlib_hardlink_to": {
        "action": "noop",
    },
    "python.stdlib.pathlib_full_match": {
        "action": "noop",
    },

    # Glob — the root_dir parameter is the feature, not glob() itself
    "python.stdlib.glob_root_dir": {
        "action": "add_has_keyword",
        "keyword": "root_dir",
    },

    # Dataclass entries — match specific keyword arguments
    "python.stdlib.dataclass_slots": {
        "action": "add_has_keyword",
        "keyword": "slots",
    },
    "python.stdlib.dataclass_kw_only": {
        "action": "add_has_keyword",
        "keyword": "kw_only",
    },
    "python.stdlib.dataclass_match_args": {
        "action": "add_has_keyword",
        "keyword": "match_args",
    },
    "python.stdlib.dataclass_frozen_slots": {
        "action": "add_has_keyword",
        "keyword": "slots",
    },
    "python.stdlib.field_kw_only": {
        "action": "add_has_keyword",
        "keyword": "kw_only",
    },

    # TypeVar — match 'default' keyword (PEP 696)
    "python.typing.type_var_defaults_312": {
        "action": "add_has_keyword",
        "keyword": "default",
    },

    # Stdlib entries with specific keyword arguments
    "python.stdlib.asyncio_cancel_msg": {
        "action": "add_has_keyword",
        "keyword": "msg",
    },
    "python.stdlib.asyncio_cancelling": {
        "action": "noop",  # cancelling is unique enough
    },
    "python.exceptions.add_note": {
        "action": "noop",  # add_note is unique enough
    },
    "python.stdlib.sqlite3_autocommit": {
        "action": "add_has_keyword",
        "keyword": "autocommit",
    },
    "python.stdlib.csv_reader_strict": {
        "action": "add_has_keyword",
        "keyword": "strict",
    },
    "python.stdlib.tarfile_data_filter": {
        "action": "add_has_keyword",
        "keyword": "filter",
    },
    "python.stdlib.tempfile_delete_param": {
        "action": "add_has_keyword",
        "keyword": "delete_on_close",
    },
    "python.stdlib.bisect_key": {
        "action": "add_has_keyword",
        "keyword": "key",
    },

    # Behavioral improvements — downgrade to info
    "python.stdlib.datetime_fromisoformat": {
        "action": "change_severity",
        "new_severity": "info",
        "new_error_type": "behavioral_change",
    },
    "python.stdlib.decimal_localcontext": {
        "action": "change_severity",
        "new_severity": "info",
        "new_error_type": "behavioral_change",
    },
    "python.stdlib.array_w_type": {
        "action": "change_severity",
        "new_severity": "info",
        "new_error_type": "behavioral_change",
    },
}


def apply_fixes(dry_run: bool = False) -> dict:
    """Apply all fixes to YAML files."""
    stats = {"modified": 0, "entries_fixed": 0, "skipped": 0, "errors": 0}

    # Merge all fix rounds
    all_fixes = {**FIXES, **FIXES_ROUND2}

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
            if entry_id not in all_fixes:
                continue

            fix = all_fixes[entry_id]
            action = fix["action"]

            if action == "noop":
                stats["skipped"] += 1
                continue

            if action == "add_has_keyword":
                keyword = fix["keyword"]
                detection = entry.get("detection", {})
                primary = detection.get("primary", {})
                match = primary.get("match", {})
                if "has_keyword" not in match:
                    match["has_keyword"] = keyword
                    modified = True
                    stats["entries_fixed"] += 1
                    print(f"  ✓ {entry_id}: added has_keyword={keyword}")

            elif action == "add_match_key":
                key = fix["key"]
                value = fix["value"]
                detection = entry.get("detection", {})
                primary = detection.get("primary", {})
                match = primary.get("match", {})
                if key not in match:
                    match[key] = value
                    modified = True
                    stats["entries_fixed"] += 1
                    print(f"  ✓ {entry_id}: added {key}={value}")

            elif action == "change_severity":
                new_sev = fix.get("new_severity")
                new_err = fix.get("new_error_type")
                if new_sev and entry.get("severity") != new_sev:
                    old_sev = entry.get("severity")
                    entry["severity"] = new_sev
                    modified = True
                    print(f"  ✓ {entry_id}: severity {old_sev} → {new_sev}")
                if new_err:
                    entry["error_type"] = new_err
                    modified = True
                stats["entries_fixed"] += 1

        if modified:
            if not dry_run:
                # Write back preserving YAML list format
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
        print("DRY RUN — no files will be modified\n")
    else:
        print("APPLYING FIXES to YAML entries\n")

    stats = apply_fixes(dry_run=dry_run)
    print(f"\nDone: {stats['entries_fixed']} entries fixed in {stats['modified']} files "
          f"({stats['skipped']} skipped, {stats['errors']} errors)")
