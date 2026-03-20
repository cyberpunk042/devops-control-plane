"""CLI interface for the compat v2 system.

Usage:
    python -m src.core.services.compat.cli analyze <module> --target <version>
    python -m src.core.services.compat.cli assess <module> --target <version>
    python -m src.core.services.compat.cli validate-db [--language python]
    python -m src.core.services.compat.cli features [--language python] [--above 3.8]
    python -m src.core.services.compat.cli fix <module> --target <version> [--dry-run]
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        _print_help()
        return

    command = args[0]

    if command == "validate-db":
        _cmd_validate_db(args[1:])
    elif command == "features":
        _cmd_features(args[1:])
    elif command == "analyze":
        _cmd_analyze(args[1:])
    elif command == "assess":
        _cmd_assess(args[1:])
    elif command == "fix":
        _cmd_fix(args[1:])
    elif command == "plan":
        _cmd_plan(args[1:])
    else:
        print(f"Unknown command: {command}")
        _print_help()
        sys.exit(1)


def _print_help() -> None:
    print("Usage: compat <command> [options]")
    print()
    print("Commands:")
    print("  validate-db   Validate feature database entries")
    print("  features      Browse feature database")
    print("  analyze       Analyze a module for compatibility")
    print("  assess        Pre-plan assessment")
    print("  plan          Create/view version plans")
    print("  fix           Apply fixes to a module")


def _cmd_validate_db(args: list[str]) -> None:
    from .database.validator import validate_database

    language = None
    verbose = "--verbose" in args or "-v" in args
    for i, a in enumerate(args):
        if a == "--language" and i + 1 < len(args):
            language = args[i + 1]

    print("Validating feature database...")
    print()

    result = validate_database(language=language, verbose=verbose)

    print()
    print(result.summary())

    if result.failed_entries > 0:
        sys.exit(1)


def _cmd_features(args: list[str]) -> None:
    from .database.registry import FeatureRegistry

    registry = FeatureRegistry.load()
    language = None
    above = None

    for i, a in enumerate(args):
        if a == "--language" and i + 1 < len(args):
            language = args[i + 1]
        if a == "--above" and i + 1 < len(args):
            above = args[i + 1]

    if language and above:
        entries = registry.above_version(language, above)
        print(f"Features above {language} {above}: {len(entries)}")
        print()
        by_ver: dict[str, list] = {}
        for e in entries:
            by_ver.setdefault(e.introduced, []).append(e)
        for ver in sorted(by_ver.keys()):
            print(f"  {ver}:")
            for e in by_ver[ver]:
                fix = "🔧" if e.fix.strategy.value != "manual" else "⚠️"
                print(f"    {fix} {e.feature_name}")
    elif language:
        entries = registry.by_language(language)
        cats = registry.count_by_category(language)
        print(f"{language}: {len(entries)} entries")
        for cat, count in sorted(cats.items()):
            print(f"  {cat}: {count}")
    else:
        print(f"Total: {registry.count()} entries")
        for lang, count in sorted(registry.count_by_language().items()):
            print(f"  {lang}: {count}")


def _cmd_analyze(args: list[str]) -> None:
    module_name = args[0] if args else ""
    target = ""
    transitive = True

    for i, a in enumerate(args):
        if a == "--target" and i + 1 < len(args):
            target = args[i + 1]
        if a == "--no-transitive":
            transitive = False

    if not module_name or not target:
        print("Usage: compat analyze <module> --target <version>")
        sys.exit(1)

    from .orchestrator import CompatOrchestrator

    compat = CompatOrchestrator.create(Path("."))

    if transitive:
        result = compat.analyze(module_name, target, include_transitive=True)
    else:
        result = compat.analyze(module_name, target, include_transitive=False)

    print(f"Analyzed: {result.files_scanned} files in {result.scan_duration_ms}ms")
    print(f"Findings: {result.total_findings}")
    print(f"  Direct: {len(result.direct_findings)}")
    print(f"  Transitive: {len(result.transitive_findings)}")
    print()

    for feature_id, findings in result.by_feature().items():
        direct = [f for f in findings if not f.is_transitive]
        trans = [f for f in findings if f.is_transitive]
        fix = "🔧" if findings[0].fix_available else "⚠️"
        print(f"  {fix} {findings[0].feature_name} ({findings[0].version}+)")
        if direct:
            print(f"     Direct: {len(direct)} file(s)")
            for f in direct[:3]:
                print(f"       {f.file}:{f.line}")
        if trans:
            print(f"     Transitive: {len(trans)} file(s)")
            for f in trans[:3]:
                chain = " → ".join(p.split("/")[-1] for p in f.import_chain) if f.import_chain else ""
                print(f"       {f.file}:{f.line} (via {chain})")
            if len(trans) > 3:
                print(f"       ... and {len(trans) - 3} more")
        print()

    if result.total_findings > 0:
        sys.exit(1)


def _cmd_assess(args: list[str]) -> None:
    module_name = args[0] if args else ""
    target = ""

    for i, a in enumerate(args):
        if a == "--target" and i + 1 < len(args):
            target = args[i + 1]

    if not module_name or not target:
        print("Usage: compat assess <module> --target <version>")
        sys.exit(1)

    from .orchestrator import CompatOrchestrator

    compat = CompatOrchestrator.create(Path("."))
    assessment = compat.assess(module_name, target)

    print("═" * 50)
    print(f"Assessment: {module_name} → {target}")
    print("═" * 50)
    print(f"Achievable: {'YES' if assessment.achievable else 'NO'}")
    print(f"Current floor: {assessment.current_floor}")
    if assessment.gap:
        print(f"Gap: {assessment.gap}")
    print()
    print(f"Code fixes: {assessment.code_fixes_auto} auto + {assessment.code_fixes_manual} manual")
    print(f"Dep changes: {assessment.dep_changes_needed}")
    print(f"Transitive: {assessment.transitive_fixes_needed}")
    if assessment.blocking_modules:
        print(f"Blocking: {assessment.blocking_modules}")
        print(f"Fix order: {assessment.fix_order}")
    print()
    print(f"Recommendation: {assessment.recommendation}")
    print(f"Effort: {assessment.estimated_effort}")
    print("═" * 50)


def _cmd_fix(args: list[str]) -> None:
    module_name = args[0] if args else ""
    target = ""
    dry_run = "--dry-run" in args

    for i, a in enumerate(args):
        if a == "--target" and i + 1 < len(args):
            target = args[i + 1]

    if not module_name or not target:
        print("Usage: compat fix <module> --target <version> [--dry-run]")
        sys.exit(1)

    from .orchestrator import CompatOrchestrator

    compat = CompatOrchestrator.create(Path("."))

    if dry_run:
        result = compat.analyze(module_name, target, include_transitive=False)
        fixable = result.fixable_findings
        print(f"Dry run — would fix {len(fixable)} finding(s):")
        by_file: dict[str, list] = {}
        for f in fixable:
            by_file.setdefault(f.file, []).append(f)
        for fp, findings in sorted(by_file.items()):
            print(f"  {fp}: {len(findings)} fix(es)")
        return

    fix_result = compat.fix_all(module_name, target)
    print(f"Fixed: {fix_result.verified_fixes}/{fix_result.total_fixes}")
    print(f"Files: {fix_result.files_fixed} modified, {fix_result.files_rolled_back} rolled back")
    if fix_result.failed_fixes > 0:
        print(f"Failed: {fix_result.failed_fixes}")
        sys.exit(1)


def _cmd_plan(args: list[str]) -> None:
    subcommand = args[0] if args else "help"

    if subcommand == "create":
        module_name = args[1] if len(args) > 1 else ""
        target = ""
        no_save = "--no-save" in args

        for i, a in enumerate(args):
            if a == "--target" and i + 1 < len(args):
                target = args[i + 1]

        if not module_name or not target:
            print("Usage: compat plan create <module> --target <version> [--no-save]")
            sys.exit(1)

        from .orchestrator import CompatOrchestrator

        compat = CompatOrchestrator.create(Path("."))
        result = compat.create_plan(module_name, target, save=not no_save)

        if not result.get("ok"):
            print(f"Error: {result.get('error')}")
            sys.exit(1)

        print(f"Plan created for '{module_name}' → Python {target}")
        print(f"Steps: {result['steps']}")
        print()

        assessment = result.get("assessment", {})
        if assessment.get("blocking_modules"):
            print(f"⚠️ Blocked by: {assessment['blocking_modules']}")

        print()
        for i, step in enumerate(result["plan"]["steps"], 1):
            state_icon = {
                "pending": "○",
                "blocked": "🔒",
                "passed": "✅",
            }.get(step["state"], "○")
            print(f"  {i}. {state_icon} {step['label']}")

        if not no_save:
            print(f"\nSaved to project.yml")

    elif subcommand == "show":
        module_name = args[1] if len(args) > 1 else ""
        if not module_name:
            print("Usage: compat plan show <module>")
            sys.exit(1)

        from .orchestrator import CompatOrchestrator

        compat = CompatOrchestrator.create(Path("."))
        plan = compat.get_plan(module_name)

        if not plan:
            print(f"No plan found for '{module_name}'")
            sys.exit(1)

        print(f"Version Plan: {module_name} → Python {plan['target']} ({plan['direction']})")
        print()

        for i, step in enumerate(plan["steps"], 1):
            state_icon = {
                "pending": "○",
                "passed": "✅",
                "failed": "❌",
                "needs_attention": "⚠️",
                "blocked": "🔒",
                "skipped": "⏭️",
            }.get(step["state"], "○")
            print(f"  {i}. {state_icon} {step['label']}")

        done = sum(1 for s in plan["steps"] if s["state"] in ("passed", "skipped"))
        total = len(plan["steps"])
        print(f"\nProgress: {done}/{total}")

    else:
        print("Usage: compat plan <create|show> <module> --target <version>")
        sys.exit(1)


if __name__ == "__main__":
    main()
