"""
Code scanners — analyze and modify Python source files.

Handlers:
  - scan_breaking_changes: find version-specific code patterns (upgrade)
  - scan_incompatible_features: find features above target (downgrade)
  - remove_future_annotations: remove __future__ imports when safe
  - add_future_annotations: add __future__ imports where needed

Reuses the feature detection patterns from module_intel.compute_code_floor().
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..context import UpgradeContext

logger = logging.getLogger(__name__)

_FUTURE_IMPORT_RE = re.compile(
    r"^from\s+__future__\s+import\s+annotations\s*\n?",
    re.MULTILINE,
)

# Full line pattern for adding the import
_FUTURE_IMPORT_LINE = "from __future__ import annotations\n"


def handle_scan_breaking_changes(ctx: UpgradeContext, mode: str) -> dict:
    """Scan code for version-specific features (upgrade direction).

    Shows what Python features the code currently uses, with file:line
    locations. This helps the user understand what version-specific
    patterns exist before upgrading.

    Read-only — both preview and execute return the same scan results.
    """
    return _scan_features(ctx, direction="upgrade")


def handle_scan_incompatible_features(ctx: UpgradeContext, mode: str) -> dict:
    """Scan code for features not available in target version (downgrade).

    Shows features that require a higher Python version than the target,
    which would need to be rewritten or backported.

    Read-only — both preview and execute return the same scan results.
    """
    return _scan_features(ctx, direction="downgrade")


def handle_fix_compat_auto(ctx: UpgradeContext, mode: str) -> dict:
    """Fix all auto-fixable compat findings in the module.

    Uses the compat v2 fix engine with verification and rollback.

    Preview: shows what would be fixed.
    Execute: applies fixes, verifies, reports results.
    """
    try:
        from src.core.services.mediator import get_mediator

        _m = get_mediator()
        analysis_data = _m.get(f"compat.analysis.{ctx.module_name}")
        result = analysis_data["data"]
        if result is None:
            return {"ok": False, "error": "No analysis results available"}

        # Filter to auto-fixable, actionable findings
        fixable = [
            f for f in result.findings
            if f.fix_available
            and f.severity in ("error", "warning")
            and f.fix_strategy != "no_fix_needed"
            and not f.is_transitive
        ]

        # If a feature hash is set, filter to just that feature
        import hashlib as _hl
        feature_hash = getattr(ctx, "_feature_hash", None)
        if feature_hash:
            fixable = [
                f for f in fixable
                if _hl.md5(f.feature_name.encode()).hexdigest()[:8] == feature_hash
            ]

        if not fixable:
            return {
                "ok": True,
                "can_apply": False,
                "preview_type": "info",
                "summary": "No auto-fixable findings",
            }

        files = sorted(set(f.file for f in fixable))

        # Build preview data (used for both preview mode AND auto_fix=False gate)
        compat = _m.get("compat.orchestrator")["data"]

        by_feature: dict[str, list] = {}
        for f in fixable:
            by_feature.setdefault(f.feature_name, []).append(f)

        feature_previews = []
        for feature_name, findings in sorted(by_feature.items()):
            entry = compat.registry.get(findings[0].feature_id)

            preview = {
                "feature": feature_name,
                "version": findings[0].version,
                "count": len(findings),
                "files": [f"{f.file}:{f.line}" for f in findings[:5]],
                "more_files": max(0, len(findings) - 5),
                "fix_strategy": findings[0].fix_strategy,
            }

            if entry and entry.test:
                if entry.test.before:
                    preview["before"] = entry.test.before.strip()
                if entry.test.after:
                    preview["after"] = entry.test.after.strip()
            if entry and entry.description:
                preview["description"] = entry.description

            feature_previews.append(preview)

        # Preview mode — always return preview
        if mode == "preview":
            return {
                "ok": True,
                "can_apply": True,
                "preview_type": "compat_fix_preview",
                "summary": f"Will fix {len(fixable)} finding(s) in {len(files)} file(s)",
                "total_findings": len(fixable),
                "total_files": len(files),
                "by_feature": feature_previews,
            }

        # Execute mode — apply fixes
        module_dir = ctx.project_root / ctx.module_path

        fix_result = compat.fix.fix_module(
            module_dir=module_dir,
            findings=fixable,
            module_name=ctx.module_name,
            project_root=ctx.project_root,
            verify=True,
        )

        summary_parts = [f"Fixed {fix_result.verified_fixes}/{len(fixable)} finding(s)"]
        summary_parts.append(f"in {fix_result.files_fixed} file(s)")
        if fix_result.files_rolled_back > 0:
            summary_parts.append(f"({fix_result.files_rolled_back} rolled back)")

        return {
            "ok": True,
            "summary": " ".join(summary_parts),
            "fixed_count": fix_result.verified_fixes,
            "failed_count": fix_result.failed_fixes,
            "files_fixed": fix_result.files_fixed,
            "files_rolled_back": fix_result.files_rolled_back,
            "duration_ms": fix_result.duration_ms,
        }

    except Exception as exc:
        return {"ok": False, "error": f"Auto-fix failed: {exc}"}


def handle_remove_future_annotations(ctx: UpgradeContext, mode: str) -> dict:
    """Remove __future__ annotations imports when target >= 3.10.

    Preview: lists files that have the import.
    Execute: removes the import line from each file.
    """
    module_dir = ctx.project_root / ctx.module_path
    if not module_dir.is_dir():
        return {"ok": False, "error": f"Module directory not found: {ctx.module_path}"}

    # Find all files with __future__ annotations
    files_with_future: list[dict] = []

    for py_file in sorted(module_dir.rglob("*.py")):
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        if _FUTURE_IMPORT_RE.search(content):
            rel_path = str(py_file.relative_to(ctx.project_root))
            files_with_future.append({"file": rel_path})

    if not files_with_future:
        return {
            "ok": True,
            "can_apply": False,
            "preview_type": "info",
            "summary": "No __future__ annotations imports found",
        }

    if mode == "preview":
        return {
            "ok": True,
            "can_apply": True,
            "preview_type": "findings",
            "summary": f"Found {len(files_with_future)} file(s) with __future__ annotations import",
            "detail": (
                f"With Python >={ctx.target_floor}, the `from __future__ import annotations` "
                "import is no longer needed for PEP 604/585 type hint syntax."
            ),
            "findings": files_with_future,
        }

    # Execute — remove the import from each file
    modified_count = 0
    for entry in files_with_future:
        file_path = ctx.project_root / entry["file"]
        try:
            content = file_path.read_text(encoding="utf-8")
            new_content = _FUTURE_IMPORT_RE.sub("", content)

            # Clean up: if removal leaves a blank line at the top, remove it
            while new_content.startswith("\n\n"):
                new_content = new_content[1:]

            if new_content != content:
                file_path.write_text(new_content, encoding="utf-8")
                modified_count += 1
        except OSError as exc:
            logger.warning("Failed to modify %s: %s", entry["file"], exc)

    return {
        "ok": True,
        "summary": f"Removed __future__ annotations from {modified_count} file(s)",
        "modified_count": modified_count,
    }


def handle_add_future_annotations(ctx: UpgradeContext, mode: str) -> dict:
    """Add __future__ annotations import to files that need it.

    Uses compat v2 engine to detect annotation-only findings,
    then applies the __future__ import fix.

    Preview: lists files that need the import.
    Execute: adds the import using the compat fix engine.
    """
    module_dir = ctx.project_root / ctx.module_path
    if not module_dir.is_dir():
        return {"ok": False, "error": f"Module directory not found: {ctx.module_path}"}

    # ── Use compat v2 analysis (cached or computed on demand) ───
    try:
        from src.core.services.mediator import get_mediator

        _m = get_mediator()
        _analysis_data = _m.get(f"compat.analysis.{ctx.module_name}")
        result = _analysis_data["data"]
        if result is None:
            raise RuntimeError("compat analysis returned None")

        # Filter to findings fixable with __future__
        future_findings = [
            f for f in result.findings
            if f.fix_strategy == "add_future_import"
        ]

        if not future_findings:
            return {
                "ok": True,
                "can_apply": False,
                "preview_type": "info",
                "summary": "No files need __future__ annotations import",
            }

        # Get unique files
        files_needing = sorted(set(f.file for f in future_findings))
        files_needing_future = [{"file": f} for f in files_needing]

        if mode == "preview":
            return {
                "ok": True,
                "can_apply": True,
                "preview_type": "findings",
                "summary": f"Found {len(files_needing)} file(s) using annotation syntax without __future__",
                "detail": (
                    f"These files use PEP 604/585 type hints but lack "
                    "`from __future__ import annotations`. Adding it will make "
                    f"them compatible with Python {ctx.target_floor}."
                ),
                "findings": files_needing_future,
            }

        # Execute — apply fixes
        _compat_data = _m.peek("compat.orchestrator")
        if _compat_data is None:
            raise RuntimeError("compat orchestrator not loaded")
        compat = _compat_data["data"]

        fixed_files = set()
        for finding in future_findings:
            fix_result = compat.fix.fix_finding(finding, ctx.project_root, verify=False)
            if fix_result.success:
                fixed_files.add(finding.file)

        return {
            "ok": True,
            "summary": f"Added __future__ annotations to {len(fixed_files)} file(s)",
            "modified_count": len(fixed_files),
        }

    except Exception as exc:
        return {"ok": False, "error": f"Future annotations analysis failed: {exc}"}


# ── Internal helpers ─────────────────────────────────────────────


def _scan_features(ctx: UpgradeContext, direction: str) -> dict:
    """Scan module source files for version-specific features.

    Uses the compat v2 AST-based detection engine for accurate results.
    Uses the compat v2 AST-based detection engine.

    For upgrade: shows all features found (what the code uses).
    For downgrade: shows only features above the target version.
    """
    if ctx.language != "python":
        return {
            "ok": True,
            "can_apply": False,
            "preview_type": "info",
            "summary": "Code scanning only available for Python",
        }

    # ── Use compat v2 AST engine ─────────────────────────────────
    try:
        from src.core.services.mediator import get_mediator

        _m = get_mediator()

        # Get compat analysis (cached or computed on demand)
        _analysis_data = _m.get(f"compat.analysis.{ctx.module_name}")
        result = _analysis_data["data"]
        if result is None:
            raise RuntimeError("compat analysis returned None")

        # Filter to actionable findings (error/warning, not info/no_fix_needed)
        actionable = [
            f for f in result.findings
            if f.severity in ("error", "warning") and f.fix_strategy != "no_fix_needed"
        ]

        if not actionable:
            return {
                "ok": True,
                "can_apply": False,
                "preview_type": "info",
                "summary": f"No actionable incompatibilities for Python {ctx.target_floor}",
            }

        # Group by feature
        by_feature: dict[str, list] = {}
        for f in actionable:
            by_feature.setdefault(f.feature_name, []).append(f)

        # Stats
        auto_fixable = [f for f in actionable if f.fix_available]
        manual_only = [f for f in actionable if not f.fix_available]
        errors = [f for f in actionable if f.severity == "error"]
        warnings = [f for f in actionable if f.severity == "warning"]
        total_files = len(set(f.file for f in actionable))

        code_floor = max(
            (f.version for f in actionable),
            default=ctx.target_floor,
        )

        # Build grouped output
        feature_groups = []
        for feature_name in sorted(by_feature.keys()):
            findings = by_feature[feature_name]
            files = sorted(set(f.file for f in findings))
            feature_groups.append({
                "feature": feature_name,
                "feature_id": findings[0].feature_id,
                "version": findings[0].version,
                "severity": findings[0].severity,
                "count": len(findings),
                "fix_available": findings[0].fix_available,
                "fix_strategy": findings[0].fix_strategy,
                "files": [f"{f.file}:{f.line}" for f in findings[:5]],
                "more": max(0, len(findings) - 5),
            })

        # Sort: errors first, then by count descending
        feature_groups.sort(key=lambda g: (0 if g["severity"] == "error" else 1, -g["count"]))

        summary_parts = []
        if errors:
            summary_parts.append(f"{len(errors)} error(s)")
        if warnings:
            summary_parts.append(f"{len(warnings)} warning(s)")
        summary_parts.append(f"in {total_files} file(s)")
        if auto_fixable:
            summary_parts.append(f"({len(auto_fixable)} auto-fixable)")

        return {
            "ok": True,
            "can_apply": bool(auto_fixable),
            "preview_type": "compat_scan",
            "summary": ", ".join(summary_parts),
            "code_floor": code_floor,
            "total_findings": len(actionable),
            "auto_fixable_count": len(auto_fixable),
            "manual_count": len(manual_only),
            "error_count": len(errors),
            "warning_count": len(warnings),
            "file_count": total_files,
            "by_feature": feature_groups,
            "findings": [
                {
                    "file": f.file,
                    "line": f.line,
                    "feature": f.feature_name,
                    "version": f.version,
                    "severity": f.severity,
                    "fix_available": f.fix_available,
                    "fix_strategy": f.fix_strategy,
                }
                for f in actionable[:100]  # Cap at 100 for UI performance
            ],
        }

    except Exception as exc:
        return {"ok": False, "error": f"Feature scan failed: {exc}"}


def _add_future_import(content: str) -> str:
    """Add 'from __future__ import annotations' to file content.

    Inserts after any existing __future__ imports, or after the module
    docstring, or at the very top of the file.
    """
    lines = content.split("\n")

    # Find insertion point
    insert_at = 0

    # Skip shebang
    if lines and lines[0].startswith("#!"):
        insert_at = 1

    # Skip encoding declaration
    if insert_at < len(lines) and re.match(r"#.*coding[:=]", lines[insert_at]):
        insert_at += 1

    # Skip module docstring (triple-quoted)
    if insert_at < len(lines):
        line = lines[insert_at].strip()
        if line.startswith('"""') or line.startswith("'''"):
            quote = line[:3]
            if line.count(quote) >= 2 and len(line) > 3:
                # Single-line docstring
                insert_at += 1
            else:
                # Multi-line docstring — find closing quotes
                for i in range(insert_at + 1, len(lines)):
                    if quote in lines[i]:
                        insert_at = i + 1
                        break

    # Skip blank lines after docstring
    while insert_at < len(lines) and not lines[insert_at].strip():
        insert_at += 1

    # Insert the import
    lines.insert(insert_at, _FUTURE_IMPORT_LINE.rstrip())

    # Add blank line after if next line isn't blank or an import
    if (insert_at + 1 < len(lines) and
            lines[insert_at + 1].strip() and
            not lines[insert_at + 1].startswith("from ") and
            not lines[insert_at + 1].startswith("import ")):
        lines.insert(insert_at + 1, "")

    return "\n".join(lines)


def handle_modernize_type_hints(ctx: UpgradeContext, mode: str) -> dict:
    """Replace typing.X imports with builtin generics.

    Scans for: typing.List → list, typing.Dict → dict, typing.Set → set,
    typing.Tuple → tuple, typing.FrozenSet → frozenset,
    typing.Optional[X] → X | None, typing.Union[X, Y] → X | Y.

    Preview: shows findings with file:line.
    Execute: performs the replacements.
    """
    module_dir = ctx.project_root / ctx.module_path
    if not module_dir.is_dir():
        return {"ok": False, "error": f"Module directory not found: {ctx.module_path}"}

    # Patterns: old → new (for simple generics)
    _TYPING_REPLACEMENTS = {
        "List": "list",
        "Dict": "dict",
        "Set": "set",
        "Tuple": "tuple",
        "FrozenSet": "frozenset",
        "Type": "type",
    }

    # Find files with typing imports that could be modernized
    typing_import_re = re.compile(
        r"from\s+typing\s+import\s+([^;\n]+)",
        re.MULTILINE,
    )

    findings: list[dict] = []
    file_changes: list[tuple[Path, str, str]] = []  # (path, old_content, new_content)

    for py_file in sorted(module_dir.rglob("*.py")):
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        rel_path = str(py_file.relative_to(ctx.project_root))
        new_content = content
        file_findings: list[str] = []

        # Find typing imports
        for match in typing_import_re.finditer(content):
            imports_str = match.group(1)
            imported_names = [n.strip() for n in imports_str.split(",")]

            for name in imported_names:
                if name in _TYPING_REPLACEMENTS:
                    replacement = _TYPING_REPLACEMENTS[name]
                    file_findings.append(f"typing.{name} → {replacement}")

                    # Replace usage: List[ → list[, Dict[ → dict[, etc.
                    usage_re = re.compile(rf"\b{name}\[")
                    new_content = usage_re.sub(f"{replacement}[", new_content)

                elif name == "Optional":
                    file_findings.append("typing.Optional[X] → X | None")
                    # Replace Optional[X] with X | None
                    new_content = re.sub(
                        r"\bOptional\[([^\[\]]+)\]",
                        r"\1 | None",
                        new_content,
                    )

                elif name == "Union":
                    file_findings.append("typing.Union[X, Y] → X | Y")
                    # Replace Union[X, Y] with X | Y
                    new_content = re.sub(
                        r"\bUnion\[([^\[\]]+)\]",
                        lambda m: " | ".join(a.strip() for a in m.group(1).split(",")),
                        new_content,
                    )

        if file_findings:
            line_no = content[:typing_import_re.search(content).start()].count("\n") + 1
            findings.append({
                "file": rel_path,
                "line": line_no,
                "feature": ", ".join(file_findings),
            })

            # Clean up typing import — remove modernized names
            if new_content != content:
                # Remove names that are now builtins from typing import
                for name in _TYPING_REPLACEMENTS:
                    # Remove "Name, " or ", Name" or standalone "Name"
                    new_content = re.sub(
                        rf"from\s+typing\s+import\s+{name}\s*\n",
                        "",
                        new_content,
                    )
                    new_content = re.sub(rf",\s*{name}\b", "", new_content)
                    new_content = re.sub(rf"\b{name}\s*,\s*", "", new_content)

                # Also remove Optional and Union if replaced
                for name in ("Optional", "Union"):
                    new_content = re.sub(
                        rf"from\s+typing\s+import\s+{name}\s*\n",
                        "",
                        new_content,
                    )
                    new_content = re.sub(rf",\s*{name}\b", "", new_content)
                    new_content = re.sub(rf"\b{name}\s*,\s*", "", new_content)

                # Clean empty typing import lines
                new_content = re.sub(
                    r"from\s+typing\s+import\s*\n",
                    "",
                    new_content,
                )

                file_changes.append((py_file, content, new_content))

    if not findings:
        return {
            "ok": True,
            "can_apply": False,
            "preview_type": "info",
            "summary": "No typing imports to modernize",
        }

    if mode == "preview":
        return {
            "ok": True,
            "can_apply": True,
            "preview_type": "findings",
            "summary": f"Found {len(findings)} file(s) with modernizable type hints",
            "detail": (
                "These files use typing.List, typing.Dict, etc. which can be "
                f"replaced with builtin generics on Python >={ctx.target_floor}."
            ),
            "findings": findings,
        }

    # Execute
    modified_count = 0
    for py_file, _old, new_content in file_changes:
        try:
            py_file.write_text(new_content, encoding="utf-8")
            modified_count += 1
        except OSError as exc:
            logger.warning("Failed to modify %s: %s", py_file, exc)

    return {
        "ok": True,
        "summary": f"Modernized type hints in {modified_count} file(s)",
        "modified_count": modified_count,
    }


def handle_update_ci_matrix(ctx: UpgradeContext, mode: str) -> dict:
    """Detect CI config files and show what needs updating.

    Scans for common CI config files (GitHub Actions, GitLab CI, etc.)
    and shows which ones reference Python version matrices.

    Preview: shows CI files found and Python version references.
    Execute: same as preview (read-only — CI config edits are too
    varied to automate safely, but we show exactly where to edit).
    """
    module_dir = ctx.project_root / ctx.module_path
    project_root = ctx.project_root

    # CI config file locations (relative to project root)
    ci_files = [
        (".github/workflows", "*.yml"),
        (".github/workflows", "*.yaml"),
        (".gitlab-ci.yml", None),
        (".circleci/config.yml", None),
        ("Jenkinsfile", None),
        (".travis.yml", None),
        ("azure-pipelines.yml", None),
        ("tox.ini", None),
        ("noxfile.py", None),
    ]

    # Python version patterns in CI files
    python_version_re = re.compile(
        r"""(?:python-version|python_version|PYTHON|python)\s*[:=]\s*['"]?(\d+\.\d+)""",
        re.IGNORECASE,
    )
    matrix_re = re.compile(
        r"""(?:matrix|strategy).*?python.*?\[([^\]]+)\]""",
        re.IGNORECASE | re.DOTALL,
    )

    findings: list[dict] = []

    for ci_pattern, glob_pattern in ci_files:
        ci_path = project_root / ci_pattern

        if glob_pattern:
            # Directory with glob
            if ci_path.is_dir():
                for f in ci_path.glob(glob_pattern):
                    _scan_ci_file(f, project_root, python_version_re, matrix_re, findings)
        else:
            # Direct file
            if ci_path.is_file():
                _scan_ci_file(ci_path, project_root, python_version_re, matrix_re, findings)

    if not findings:
        return {
            "ok": True,
            "can_apply": False,
            "preview_type": "info",
            "summary": "No CI configuration files with Python version references found",
        }

    return {
        "ok": True,
        "can_apply": False,  # read-only — CI configs are too varied to auto-edit
        "preview_type": "findings",
        "summary": f"Found Python version references in {len(findings)} CI file(s)",
        "detail": (
            f"Update these files to include Python {ctx.target_floor} in their "
            "test matrix or version specification."
        ),
        "findings": findings,
    }


def _scan_ci_file(
    file_path: Path,
    project_root: Path,
    python_re: re.Pattern,
    matrix_re: re.Pattern,
    findings: list[dict],
) -> None:
    """Scan a single CI file for Python version references."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return

    rel_path = str(file_path.relative_to(project_root))
    versions_found: list[str] = []

    # Direct version references
    for match in python_re.finditer(content):
        ver = match.group(1)
        if ver not in versions_found:
            versions_found.append(ver)

    # Matrix references
    for match in matrix_re.finditer(content):
        matrix_str = match.group(1)
        for ver_match in re.finditer(r"(\d+\.\d+)", matrix_str):
            ver = ver_match.group(1)
            if ver not in versions_found:
                versions_found.append(ver)

    if versions_found:
        # Find line number from whichever regex matched first
        first_match = python_re.search(content) or matrix_re.search(content)
        line_no = content[:first_match.start()].count("\n") + 1 if first_match else 1
        findings.append({
            "file": rel_path,
            "line": line_no,
            "feature": f"Python versions: {', '.join(versions_found)}",
            "note": f"References Python {', '.join(versions_found)}",
        })


def handle_guide_incompatible_syntax(ctx: UpgradeContext, mode: str) -> dict:
    """Rich guide for incompatible syntax patterns.

    Uses the compat v2 AST engine for accurate detection.
    Uses the compat v2 AST engine for accurate detection.

    Shows each finding with source line, fix availability, and rewrite guide.
    Both preview and execute return the same guide (read-only).
    """
    module_dir = ctx.project_root / ctx.module_path
    if not module_dir.is_dir():
        return {"ok": False, "error": f"Module directory not found: {ctx.module_path}"}

    if ctx.language != "python":
        return {"ok": True, "can_apply": False, "preview_type": "info",
                "summary": "Syntax guide only available for Python"}

    # ── Use compat v2 AST engine ─────────────────────────────────
    try:
        from src.core.services.mediator import get_mediator

        _m = get_mediator()

        # Read cached analysis — never run fresh analysis in a handler
        # Get compat analysis (cached or computed on demand)
        _analysis_data = _m.get(f"compat.analysis.{ctx.module_name}")
        result = _analysis_data["data"]
        if result is None:
            raise RuntimeError("compat analysis returned None")

        # Need orchestrator for registry lookup (guide hints)
        compat = _m.get("compat.orchestrator")["data"]

        # Filter to actionable findings (same filter as scan step)
        actionable = [
            f for f in result.findings
            if f.severity in ("error", "warning") and f.fix_strategy != "no_fix_needed"
        ]

        if not actionable:
            return {
                "ok": True,
                "can_apply": False,
                "preview_type": "info",
                "summary": f"No incompatible syntax found for Python {ctx.target_floor}",
            }

        # Convert to guide format with rewrite hints from database entries
        findings = []
        for f in actionable:
            entry = compat.registry.get(f.feature_id)
            guide = {}
            if entry:
                # Read before/after from database entry test case
                guide = {
                    "fixable": entry.fix.strategy.value != "manual",
                    "hint": entry.fix.manual_instructions or entry.description or f"Strategy: {entry.fix.strategy.value}",
                }
                if entry.test and entry.test.before:
                    guide["before"] = entry.test.before.strip()
                if entry.test and entry.test.after:
                    guide["after"] = entry.test.after.strip()

            findings.append({
                "file": f.file,
                "line": f.line,
                "source": f.source_line,
                "feature": f.feature_name,
                "version": f.version,
                "fixable": f.fix_available,
                "fix_strategy": f.fix_strategy,
                "rewrite_hint": guide.get("hint", f"Fix: {f.fix_strategy}" if f.fix_available else "Manual rewrite required"),
                "example_before": guide.get("before", ""),
                "example_after": guide.get("after", ""),
                "explanation": guide.get("explanation", ""),
            })

        by_feature: dict[str, list] = {}
        for f in findings:
            by_feature.setdefault(f["feature"], []).append(f)

        return {
            "ok": True,
            "can_apply": False,  # guide only
            "preview_type": "guide",
            "summary": f"{len(findings)} incompatible pattern(s) in {len(set(f['file'] for f in findings))} file(s)",
            "findings": findings,
            "by_feature": {
                feat: {
                    "count": len(items),
                    "fixable": items[0]["fixable"],
                    "rewrite_hint": items[0]["rewrite_hint"],
                    "example_before": items[0]["example_before"],
                    "example_after": items[0]["example_after"],
                    "explanation": items[0]["explanation"],
                }
                for feat, items in by_feature.items()
            },
        }

    except Exception as exc:
        return {"ok": False, "error": f"Incompatible syntax guide failed: {exc}"}


# _REWRITE_GUIDES removed — guide handler reads from compat database entries
# (entry.test.before, entry.test.after, entry.description, entry.fix.manual_instructions)


def _parse_ver(v: str) -> list[int] | None:
    """Parse version string to integer list."""
    try:
        return [int(x) for x in v.split(".")]
    except (ValueError, AttributeError):
        return None
