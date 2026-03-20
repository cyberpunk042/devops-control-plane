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

    # ── Use compat v2 cached analysis ───────────────────────────
    try:
        from src.core.services.mediator import get_mediator

        _m = get_mediator()

        # Read cached analysis — never run fresh analysis in a handler
        _analysis_data = _m.peek(f"compat.analysis.{ctx.module_name}")
        if _analysis_data is None:
            raise RuntimeError("compat analysis not cached yet")
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

        # Execute — use compat fix engine (single loop, no double-apply)
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
        logger.warning("Compat v2 future annotations failed, falling back: %s", exc)

    # ── Fallback: legacy regex approach ──────────────────────────
    annotation_patterns = [
        re.compile(r":\s*\w+\s*\|\s*\w+", re.MULTILINE),
        re.compile(r"\b(?:list|dict|set|tuple|frozenset)\[", re.MULTILINE),
    ]

    try:
        from src.core.services.system_posture.bridges.module_intel import (
            _strip_strings_and_comments,
        )
    except ImportError:
        _strip_strings_and_comments = None

    files_needing_future = []

    for py_file in sorted(module_dir.rglob("*.py")):
        if "__pycache__" in str(py_file):
            continue
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        if _FUTURE_IMPORT_RE.search(content):
            continue

        check_content = _strip_strings_and_comments(content) if _strip_strings_and_comments else content

        for pattern in annotation_patterns:
            if pattern.search(check_content):
                rel_path = str(py_file.relative_to(ctx.project_root))
                files_needing_future.append({"file": rel_path})
                break

    if not files_needing_future:
        return {
            "ok": True,
            "can_apply": False,
            "preview_type": "info",
            "summary": "No files need __future__ annotations import",
        }

    if mode == "preview":
        return {
            "ok": True,
            "can_apply": True,
            "preview_type": "findings",
            "summary": f"Found {len(files_needing_future)} file(s) using annotation syntax without __future__",
            "detail": (
                f"These files use PEP 604/585 type hints but lack "
                "`from __future__ import annotations`. Adding it will make "
                f"them compatible with Python {ctx.target_floor}."
            ),
            "findings": files_needing_future,
        }

    # Execute — add the import to each file
    modified_count = 0
    for entry in files_needing_future:
        file_path = ctx.project_root / entry["file"]
        try:
            content = file_path.read_text(encoding="utf-8")
            new_content = _add_future_import(content)
            if new_content != content:
                file_path.write_text(new_content, encoding="utf-8")
                modified_count += 1
        except OSError as exc:
            logger.warning("Failed to modify %s: %s", entry["file"], exc)

    return {
        "ok": True,
        "summary": f"Added __future__ annotations to {modified_count} file(s)",
        "modified_count": modified_count,
    }


# ── Internal helpers ─────────────────────────────────────────────


def _scan_features(ctx: UpgradeContext, direction: str) -> dict:
    """Scan module source files for version-specific features.

    Uses the compat v2 AST-based detection engine for accurate results.
    Falls back to the legacy regex scanner if the compat engine isn't available.

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

        # Read cached analysis — never run fresh analysis in a handler
        _analysis_data = _m.peek(f"compat.analysis.{ctx.module_name}")
        if _analysis_data is None:
            raise RuntimeError("compat analysis not cached yet")
        result = _analysis_data["data"]
        if result is None:
            raise RuntimeError("compat analysis returned None")

        if not result.findings:
            return {
                "ok": True,
                "can_apply": False,
                "preview_type": "info",
                "summary": f"No features incompatible with Python {ctx.target_floor}",
            }

        # Convert compat findings to the format the existing UI expects
        findings = []
        for f in result.findings:
            findings.append({
                "file": f.file,
                "line": f.line,
                "feature": f.feature_name,
                "version": f.version,
                "fix_available": f.fix_available,
                "fix_strategy": f.fix_strategy,
                "severity": f.severity,
            })

        # Compute code floor from findings
        code_floor = max(
            (f.version for f in result.findings),
            default=ctx.target_floor,
        )

        summary = (
            f"Found {len(findings)} version-specific feature(s) in code"
            if direction == "upgrade"
            else f"Found {len(findings)} feature(s) requiring Python > {ctx.target_floor}"
        )

        return {
            "ok": True,
            "can_apply": False,  # read-only scan
            "preview_type": "findings",
            "summary": summary,
            "code_floor": code_floor,
            "findings": findings,
        }

    except Exception as exc:
        logger.warning("Compat v2 scan failed, falling back to legacy: %s", exc)

    # ── Fallback: legacy regex scanner ───────────────────────────
    try:
        from src.core.services.system_posture.bridges.module_intel import (
            compute_code_floor,
        )

        code_floor, features = compute_code_floor(
            ctx.project_root, ctx.module_path, ctx.language,
        )
    except Exception as exc:
        return {"ok": False, "error": f"Code scan failed: {exc}"}

    if not features:
        return {
            "ok": True,
            "can_apply": False,
            "preview_type": "info",
            "summary": "No version-specific features detected in code",
        }

    if direction == "downgrade":
        target_parts = _parse_ver(ctx.target_floor)
        if target_parts:
            features = [
                f for f in features
                if _parse_ver(f.get("version", "")) and
                _parse_ver(f["version"]) > target_parts
            ]

    if not features:
        return {
            "ok": True,
            "can_apply": False,
            "preview_type": "info",
            "summary": f"No features incompatible with Python {ctx.target_floor}",
        }

    findings = []
    for f in features:
        findings.append({
            "file": f.get("file", ""),
            "line": f.get("line", 0),
            "feature": f.get("feature", ""),
            "version": f.get("version", ""),
        })

    summary = (
        f"Found {len(findings)} version-specific feature(s) in code"
        if direction == "upgrade"
        else f"Found {len(findings)} feature(s) requiring Python > {ctx.target_floor}"
    )

    return {
        "ok": True,
        "can_apply": False,
        "preview_type": "findings",
        "summary": summary,
        "code_floor": code_floor,
        "findings": findings,
    }


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
    Falls back to legacy regex scanner if v2 is unavailable.

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
        _analysis_data = _m.peek(f"compat.analysis.{ctx.module_name}")
        if _analysis_data is None:
            raise RuntimeError("compat analysis not cached yet")
        result = _analysis_data["data"]
        if result is None:
            raise RuntimeError("compat analysis returned None")

        # Need orchestrator for registry lookup (guide hints)
        _compat_data = _m.peek("compat.orchestrator")
        if _compat_data is None:
            raise RuntimeError("compat not loaded yet")
        compat = _compat_data["data"]

        if not result.findings:
            return {
                "ok": True,
                "can_apply": False,
                "preview_type": "info",
                "summary": f"No incompatible syntax found for Python {ctx.target_floor}",
            }

        # Convert to guide format with rewrite hints
        findings = []
        for f in result.findings:
            entry = compat.registry.get(f.feature_id)
            guide = {}
            if entry:
                guide = _REWRITE_GUIDES.get(f.feature_name, {})
                if not guide and entry.fix.manual_instructions:
                    guide = {
                        "fixable": entry.fix.strategy.value != "manual",
                        "hint": entry.fix.manual_instructions or f"Strategy: {entry.fix.strategy.value}",
                    }

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
        logger.warning("Compat v2 guide failed, falling back to legacy: %s", exc)

    # ── Fallback: legacy regex scanner ───────────────────────────
    target_parts = _parse_ver(ctx.target_floor)
    if not target_parts:
        return {"ok": False, "error": f"Cannot parse target version: {ctx.target_floor}"}

    try:
        from src.core.services.system_posture.bridges.module_intel import (
            _ANNOTATION_FEATURES,
            _RUNTIME_FEATURES,
            _strip_strings_and_comments,
        )
    except ImportError:
        return {"ok": False, "error": "Cannot import feature patterns"}

    findings = []
    _future_check_re = re.compile(r"^from\s+__future__\s+import\s+annotations", re.MULTILINE)
    _annotation_feature_names = {name for _, name, _ in _ANNOTATION_FEATURES}

    for py_file in sorted(module_dir.rglob("*.py"))[:500]:
        if "__pycache__" in str(py_file):
            continue
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        code_content = _strip_strings_and_comments(content)
        rel_path = str(py_file.relative_to(ctx.project_root))
        lines = content.split("\n")
        has_future = bool(_future_check_re.search(content))

        all_features = list(_RUNTIME_FEATURES) + list(_ANNOTATION_FEATURES)

        for ver_str, feature_name, pattern_str in all_features:
            ver_parts = _parse_ver(ver_str)
            if not ver_parts or ver_parts <= target_parts:
                continue

            is_annotation = feature_name in _annotation_feature_names
            if is_annotation and has_future:
                continue

            compiled = re.compile(pattern_str, re.MULTILINE)
            for match in compiled.finditer(code_content):
                line_no = code_content[:match.start()].count("\n") + 1
                source_line = lines[line_no - 1].rstrip() if line_no <= len(lines) else ""

                guide = _REWRITE_GUIDES.get(feature_name, {})

                findings.append({
                    "file": rel_path,
                    "line": line_no,
                    "source": source_line,
                    "feature": feature_name,
                    "version": ver_str,
                    "fixable": guide.get("fixable", False),
                    "rewrite_hint": guide.get("hint", "Manual rewrite required"),
                    "example_before": guide.get("before", ""),
                    "example_after": guide.get("after", ""),
                    "explanation": guide.get("explanation", ""),
                })

    if not findings:
        return {
            "ok": True,
            "can_apply": False,
            "preview_type": "info",
            "summary": f"No incompatible syntax found for Python {ctx.target_floor}",
        }

    by_feature: dict[str, list] = {}
    for f in findings:
        by_feature.setdefault(f["feature"], []).append(f)

    return {
        "ok": True,
        "can_apply": False,
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


# Rewrite guides per feature — what each pattern is, whether it can be
# mechanically rewritten, and the before/after example.
_REWRITE_GUIDES: dict[str, dict] = {
    "match/case": {
        "fixable": False,
        "hint": "Replace with if/elif chain",
        "explanation": (
            "Structural pattern matching (match/case) was introduced in Python 3.10. "
            "It cannot be mechanically rewritten because patterns can destructure objects, "
            "bind variables, and use guards. Each case must be manually converted to "
            "equivalent if/elif conditions."
        ),
        "before": "match command:\n    case 'quit':\n        quit()\n    case 'hello':\n        greet()",
        "after": "if command == 'quit':\n    quit()\nelif command == 'hello':\n    greet()",
    },
    "except* (exception groups)": {
        "fixable": False,
        "hint": "Replace with nested try/except blocks",
        "explanation": (
            "Exception groups (except*) were introduced in Python 3.11. "
            "They allow catching multiple exception types from a single operation. "
            "Rewriting requires restructuring error handling to use separate try/except "
            "blocks or the exceptiongroup backport package."
        ),
        "before": "try:\n    ...\nexcept* ValueError as eg:\n    handle(eg)",
        "after": "try:\n    ...\nexcept ValueError as e:\n    handle(e)\n# Or: pip install exceptiongroup",
    },
    "walrus operator :=": {
        "fixable": True,
        "hint": "Split into separate assignment + condition",
        "explanation": (
            "The walrus operator (:=) assigns a value inside an expression. "
            "Introduced in Python 3.8. To backport, split into a separate "
            "assignment statement before the condition."
        ),
        "before": "if (n := len(data)) > 10:\n    print(n)",
        "after": "n = len(data)\nif n > 10:\n    print(n)",
    },
    "positional-only /": {
        "fixable": True,
        "hint": "Remove the / separator from function parameters",
        "explanation": (
            "Positional-only parameters (/) were formalized in Python 3.8. "
            "Removing the / means the parameters can also be passed as keywords, "
            "which is usually acceptable."
        ),
        "before": "def func(a, b, /, c):",
        "after": "def func(a, b, c):  # a,b can now be keyword args too",
    },
    "f-strings": {
        "fixable": True,
        "hint": "Replace with str.format() or % formatting",
        "explanation": (
            "f-strings were introduced in Python 3.6. They can be mechanically "
            "rewritten to .format() calls, though the result is less readable."
        ),
        "before": 'msg = f"Hello {name}, you are {age} years old"',
        "after": 'msg = "Hello {}, you are {} years old".format(name, age)',
    },
    "type statement": {
        "fixable": False,
        "hint": "Replace with TypeAlias from typing",
        "explanation": (
            "The type statement (type X = ...) was introduced in Python 3.12. "
            "Use typing.TypeAlias instead for older versions."
        ),
        "before": "type Vector = list[float]",
        "after": "from typing import TypeAlias\nVector: TypeAlias = list[float]",
    },
    "builtin generics (runtime)": {
        "fixable": True,
        "hint": "Add from __future__ import annotations, or use typing.List/Dict",
        "explanation": (
            "Using list[], dict[], set[] etc. as generic types in runtime positions "
            "(not just annotations) requires Python 3.9+. Adding "
            "'from __future__ import annotations' defers evaluation and makes "
            "this syntax work on 3.7+. Alternatively, use typing.List, typing.Dict."
        ),
        "before": "x: list[int] = []\nd: dict[str, str] = {}",
        "after": "from __future__ import annotations\n\nx: list[int] = []\nd: dict[str, str] = {}",
    },
    "union type X | Y (runtime)": {
        "fixable": True,
        "hint": "Add from __future__ import annotations, or use typing.Union",
        "explanation": (
            "The X | Y union syntax in type hints requires Python 3.10+ at runtime. "
            "Adding 'from __future__ import annotations' defers evaluation and makes "
            "this work on 3.7+. Alternatively, use typing.Union[X, Y] or typing.Optional[X]."
        ),
        "before": "def greet(name: str | None) -> str:",
        "after": "from __future__ import annotations\n\ndef greet(name: str | None) -> str:\n# Or: from typing import Optional\ndef greet(name: Optional[str]) -> str:",
    },
    "datetime.UTC": {
        "fixable": True,
        "hint": "Replace datetime.UTC with datetime.timezone.utc",
        "explanation": (
            "datetime.UTC was added in Python 3.11 as a shorthand for "
            "datetime.timezone.utc. The longer form has been available since "
            "Python 3.2 and is functionally identical."
        ),
        "before": "from datetime import UTC\nnow = datetime.now(UTC)",
        "after": "from datetime import timezone\nnow = datetime.now(timezone.utc)",
    },
    "enum.StrEnum": {
        "fixable": False,
        "hint": "Use (str, Enum) base classes or the strenum backport",
        "explanation": (
            "enum.StrEnum was added in Python 3.11. For older versions, "
            "inherit from both str and Enum, or install the strenum backport."
        ),
        "before": "class Color(StrEnum):\n    RED = 'red'",
        "after": "class Color(str, Enum):\n    RED = 'red'",
    },
    "tomllib": {
        "fixable": False,
        "hint": "Use the tomli backport package",
        "explanation": (
            "tomllib was added to the stdlib in Python 3.11. For older "
            "versions, use the tomli package: pip install tomli"
        ),
        "before": "import tomllib",
        "after": "try:\n    import tomllib\nexcept ImportError:\n    import tomli as tomllib",
    },
    "str.removeprefix": {
        "fixable": True,
        "hint": "Replace with slicing: s[len(p):] if s.startswith(p) else s",
        "explanation": (
            "str.removeprefix() was added in Python 3.9. The equivalent "
            "operation can be done with startswith() + slicing."
        ),
        "before": "path.removeprefix('/api/')",
        "after": "path[len('/api/'):] if path.startswith('/api/') else path",
    },
    "str.removesuffix": {
        "fixable": True,
        "hint": "Replace with slicing: s[:-len(p)] if s.endswith(p) else s",
        "explanation": (
            "str.removesuffix() was added in Python 3.9. The equivalent "
            "operation can be done with endswith() + slicing."
        ),
        "before": "name.removesuffix('.py')",
        "after": "name[:-len('.py')] if name.endswith('.py') else name",
    },
}


def _parse_ver(v: str) -> list[int] | None:
    """Parse version string to integer list."""
    try:
        return [int(x) for x in v.split(".")]
    except (ValueError, AttributeError):
        return None
