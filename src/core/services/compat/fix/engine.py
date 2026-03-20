"""Fix engine — apply transforms to source code based on detection findings.

The fix engine receives findings from the detection engine and applies
the transforms specified in the feature database entry. Detection and
fix are coupled — the fix uses the EXACT information from the detection.

Flow per file:
1. Snapshot the file
2. Parse the AST
3. Apply transforms (import fixes first, then usages, bottom-up)
4. Emit modified source
5. Write the file
6. Verify the fix (re-detect + syntax + import check)
7. If verification fails → rollback
8. If verification passes → discard snapshot
"""

from __future__ import annotations

import ast
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..analysis.engine import DetectionEngine
    from ..analysis.finding import Finding
    from ..backends.base import LanguageBackend
    from ..database.registry import FeatureRegistry
    from ..database.schema import FeatureEntry, Fix, Transform

from .rollback import SnapshotManager
from .verifier import Verifier, VerificationResult

logger = logging.getLogger(__name__)


@dataclass
class FixResult:
    """Result of applying a fix to one finding."""
    finding_feature_id: str
    finding_file: str
    finding_line: int
    success: bool
    verified: bool = False
    verification: VerificationResult | None = None
    error: str | None = None
    rolled_back: bool = False
    strategy: str = ""


@dataclass
class FileFixResult:
    """Result of applying all fixes to one file."""
    file_path: str
    fixes_applied: int = 0
    fixes_verified: int = 0
    fixes_failed: int = 0
    rolled_back: bool = False
    results: list[FixResult] = field(default_factory=list)
    diff: str | None = None


@dataclass
class ModuleFixResult:
    """Result of applying fixes across a module."""
    module_name: str
    files_fixed: int = 0
    files_verified: int = 0
    files_rolled_back: int = 0
    total_fixes: int = 0
    verified_fixes: int = 0
    failed_fixes: int = 0
    file_results: list[FileFixResult] = field(default_factory=list)
    duration_ms: int = 0

    @property
    def all_verified(self) -> bool:
        return self.failed_fixes == 0 and self.total_fixes > 0


class FixEngine:
    """Apply fixes to source code based on detection findings."""

    def __init__(
        self,
        registry: FeatureRegistry,
        detection_engine: DetectionEngine,
        backend: LanguageBackend,
    ):
        self._registry = registry
        self._detection = detection_engine
        self._backend = backend
        self._snapshots = SnapshotManager()
        self._verifier = Verifier(detection_engine, backend)

    def fix_finding(
        self,
        finding: Finding,
        project_root: Path,
        verify: bool = True,
    ) -> FixResult:
        """Fix a single finding.

        Looks up the feature entry, applies transforms to the file,
        verifies the fix, rolls back on failure.
        """
        entry = self._registry.get(finding.feature_id)
        if not entry:
            return FixResult(
                finding_feature_id=finding.feature_id,
                finding_file=finding.file,
                finding_line=finding.line,
                success=False,
                error=f"No feature entry for '{finding.feature_id}'",
            )

        fix = entry.fix
        if fix.strategy.value == "manual":
            return FixResult(
                finding_feature_id=finding.feature_id,
                finding_file=finding.file,
                finding_line=finding.line,
                success=False,
                error="Manual fix required — no auto-fix available",
                strategy="manual",
            )

        if fix.strategy.value == "no_fix_needed":
            return FixResult(
                finding_feature_id=finding.feature_id,
                finding_file=finding.file,
                finding_line=finding.line,
                success=True,
                verified=True,
                strategy="no_fix_needed",
            )

        file_path = project_root / finding.file
        if not file_path.is_file():
            return FixResult(
                finding_feature_id=finding.feature_id,
                finding_file=finding.file,
                finding_line=finding.line,
                success=False,
                error=f"File not found: {finding.file}",
            )

        # Snapshot
        self._snapshots.take(file_path)

        # Apply transforms
        try:
            modified = self._apply_transforms(file_path, entry, finding)
            if modified is None:
                return FixResult(
                    finding_feature_id=finding.feature_id,
                    finding_file=finding.file,
                    finding_line=finding.line,
                    success=False,
                    error="Transform produced no changes",
                    strategy=fix.strategy.value,
                )

            # Write modified source
            file_path.write_text(modified, encoding="utf-8")

        except Exception as exc:
            self._snapshots.rollback(file_path)
            return FixResult(
                finding_feature_id=finding.feature_id,
                finding_file=finding.file,
                finding_line=finding.line,
                success=False,
                error=f"Transform failed: {exc}",
                rolled_back=True,
                strategy=fix.strategy.value,
            )

        # Verify
        if verify:
            verification = self._verifier.verify_fix(
                file_path, finding.feature_id, project_root,
                run_import_check=entry.verification.import_check,
            )

            if verification.all_passed:
                self._snapshots.discard(file_path)
                return FixResult(
                    finding_feature_id=finding.feature_id,
                    finding_file=finding.file,
                    finding_line=finding.line,
                    success=True,
                    verified=True,
                    verification=verification,
                    strategy=fix.strategy.value,
                )
            else:
                # Verification failed — rollback
                self._snapshots.rollback(file_path)
                errors = "; ".join(verification.errors)
                return FixResult(
                    finding_feature_id=finding.feature_id,
                    finding_file=finding.file,
                    finding_line=finding.line,
                    success=False,
                    verified=False,
                    verification=verification,
                    error=f"Verification failed: {errors}",
                    rolled_back=True,
                    strategy=fix.strategy.value,
                )

        # No verification requested — assume success
        self._snapshots.discard(file_path)
        return FixResult(
            finding_feature_id=finding.feature_id,
            finding_file=finding.file,
            finding_line=finding.line,
            success=True,
            verified=False,
            strategy=fix.strategy.value,
        )

    def fix_file(
        self,
        file_path: Path,
        findings: list[Finding],
        project_root: Path,
        verify: bool = True,
    ) -> FileFixResult:
        """Fix all findings in a single file.

        Groups findings by feature, applies all transforms at once,
        then verifies once. More efficient than fixing one at a time.
        """
        result = FileFixResult(file_path=str(file_path))

        if not findings:
            return result

        if not file_path.is_file():
            result.results.append(FixResult(
                finding_feature_id=findings[0].feature_id,
                finding_file=str(file_path),
                finding_line=0,
                success=False,
                error=f"File not found: {file_path}",
            ))
            result.fixes_failed = 1
            return result

        # Snapshot the file once
        self._snapshots.take(file_path)

        # Group findings by feature and apply transforms
        source = file_path.read_text(encoding="utf-8")
        modified = source
        features_fixed: list[str] = []

        for finding in findings:
            entry = self._registry.get(finding.feature_id)
            if not entry:
                result.results.append(FixResult(
                    finding_feature_id=finding.feature_id,
                    finding_file=finding.file,
                    finding_line=finding.line,
                    success=False,
                    error=f"No entry for '{finding.feature_id}'",
                ))
                result.fixes_failed += 1
                continue

            if entry.fix.strategy.value in ("manual", "no_fix_needed"):
                result.results.append(FixResult(
                    finding_feature_id=finding.feature_id,
                    finding_file=finding.file,
                    finding_line=finding.line,
                    success=entry.fix.strategy.value == "no_fix_needed",
                    error="Manual fix required" if entry.fix.strategy.value == "manual" else None,
                    strategy=entry.fix.strategy.value,
                ))
                if entry.fix.strategy.value == "manual":
                    result.fixes_failed += 1
                continue

            try:
                new_source = self._apply_transforms_to_source(modified, entry, finding)
                if new_source and new_source != modified:
                    modified = new_source
                    features_fixed.append(finding.feature_id)
                    result.fixes_applied += 1
                    result.results.append(FixResult(
                        finding_feature_id=finding.feature_id,
                        finding_file=finding.file,
                        finding_line=finding.line,
                        success=True,
                        strategy=entry.fix.strategy.value,
                    ))
                else:
                    result.results.append(FixResult(
                        finding_feature_id=finding.feature_id,
                        finding_file=finding.file,
                        finding_line=finding.line,
                        success=False,
                        error="Transform produced no changes",
                        strategy=entry.fix.strategy.value,
                    ))
                    result.fixes_failed += 1
            except Exception as exc:
                result.results.append(FixResult(
                    finding_feature_id=finding.feature_id,
                    finding_file=finding.file,
                    finding_line=finding.line,
                    success=False,
                    error=f"Transform failed: {exc}",
                    strategy=entry.fix.strategy.value,
                ))
                result.fixes_failed += 1

        # Write if anything changed
        if modified != source:
            file_path.write_text(modified, encoding="utf-8")

            # Verify all features at once
            if verify and features_fixed:
                verifications = self._verifier.verify_file(
                    file_path, features_fixed, project_root,
                )
                all_passed = all(v.all_passed for v in verifications)

                if all_passed:
                    self._snapshots.discard(file_path)
                    result.fixes_verified = result.fixes_applied
                    for vr in verifications:
                        # Update the corresponding FixResult
                        for fr in result.results:
                            if fr.finding_feature_id == vr.feature_id and fr.success:
                                fr.verified = True
                                fr.verification = vr
                else:
                    # Rollback entire file
                    self._snapshots.rollback(file_path)
                    result.rolled_back = True
                    for fr in result.results:
                        if fr.success:
                            fr.success = False
                            fr.rolled_back = True
                            fr.error = "Verification failed — file rolled back"
                    result.fixes_failed = result.fixes_applied
                    result.fixes_applied = 0
                    result.fixes_verified = 0
            elif not verify:
                self._snapshots.discard(file_path)
                result.fixes_verified = result.fixes_applied
        else:
            self._snapshots.discard(file_path)

        return result

    def fix_module(
        self,
        module_dir: Path,
        findings: list[Finding],
        module_name: str,
        project_root: Path,
        verify: bool = True,
    ) -> ModuleFixResult:
        """Fix all findings in a module.

        Only fixes DIRECT findings (not transitive).
        Groups findings by file for efficiency.
        """
        t0 = time.time()
        result = ModuleFixResult(module_name=module_name)

        # Filter to direct findings only (don't touch other modules' files)
        direct = [f for f in findings if not f.is_transitive and f.fix_available]

        # Group by file
        by_file: dict[str, list[Finding]] = {}
        for f in direct:
            by_file.setdefault(f.file, []).append(f)

        # Fix each file
        for file_rel, file_findings in sorted(by_file.items()):
            file_path = project_root / file_rel
            file_result = self.fix_file(file_path, file_findings, project_root, verify)

            result.file_results.append(file_result)
            result.total_fixes += len(file_findings)

            if file_result.rolled_back:
                result.files_rolled_back += 1
                result.failed_fixes += file_result.fixes_failed
            else:
                if file_result.fixes_applied > 0:
                    result.files_fixed += 1
                if file_result.fixes_verified > 0:
                    result.files_verified += 1
                result.verified_fixes += file_result.fixes_verified
                result.failed_fixes += file_result.fixes_failed

        result.duration_ms = int((time.time() - t0) * 1000)

        # Invalidate cached analysis for this module via mediator cascade
        # This ensures next read recomputes from the fixed files
        if result.files_fixed > 0:
            try:
                from src.core.services.mediator import get_mediator

                m = get_mediator()
                m.bust_path(f"compat.analysis.{module_name}", cascade=True)
            except (ImportError, RuntimeError):
                pass  # CLI mode — no mediator

            # Publish fix event via EventBus for SSE → frontend
            try:
                from src.core.services.event_bus import bus

                bus.publish("compat:fix:applied", key=module_name, data={
                    "module": module_name,
                    "files_fixed": result.files_fixed,
                    "total_fixes": result.total_fixes,
                    "verified_fixes": result.verified_fixes,
                    "failed_fixes": result.failed_fixes,
                    "duration_ms": result.duration_ms,
                })
            except Exception:
                pass  # events are supplementary

        return result

    # ── Transform application ────────────────────────────────────

    def _apply_transforms(
        self,
        file_path: Path,
        entry: FeatureEntry,
        finding: Finding,
    ) -> str | None:
        """Apply transforms to a file. Returns modified source or None."""
        source = file_path.read_text(encoding="utf-8")
        return self._apply_transforms_to_source(source, entry, finding)

    def _apply_transforms_to_source(
        self,
        source: str,
        entry: FeatureEntry,
        finding: Finding,
    ) -> str | None:
        """Apply transforms to source text. Returns modified source or None."""
        modified = source

        for transform in entry.fix.transforms:
            new_source = self._apply_single_transform(modified, transform, entry, finding)
            if new_source is not None:
                modified = new_source

        if modified == source:
            return None
        return modified

    def _apply_single_transform(
        self,
        source: str,
        transform: Transform,
        entry: FeatureEntry,
        finding: Finding,
    ) -> str | None:
        """Apply a single transform to source. Returns modified source or None."""
        t_type = transform.type

        if t_type == "replace_import_name":
            return self._transform_replace_import_name(source, transform)

        if t_type == "replace_usage":
            return self._transform_replace_usage(source, transform)

        if t_type == "replace_import_statement":
            return self._transform_replace_import_statement(source, transform)

        if t_type == "add_import":
            return self._transform_add_import(source, transform)

        if t_type == "remove_import":
            return self._transform_remove_import(source, transform)

        if t_type == "conditional_import":
            return self._transform_conditional_import(source, transform)

        if t_type == "rewrite_method_call":
            return self._transform_rewrite_method_call(source, transform)

        if t_type == "rewrite_binary_op":
            return self._transform_rewrite_binary_op(source, transform)

        if t_type == "replace_identifier":
            return self._transform_replace_identifier(source, transform)

        if t_type == "rewrite_walrus":
            return self._transform_rewrite_walrus(source, transform, finding)

        if t_type == "rewrite_type_alias":
            return self._transform_rewrite_type_alias(source, transform, finding)

        if t_type == "split_with_statement":
            return self._transform_split_with(source, transform, finding)

        if t_type == "rewrite_builtin_generic":
            return self._transform_rewrite_builtin_generic(source, transform)

        if t_type == "rewrite_annotation":
            return self._transform_rewrite_annotation(source, transform)

        logger.warning("Unknown transform type: %s", t_type)
        return None

    # ── Individual transform implementations ─────────────────────

    def _transform_replace_import_name(self, source: str, transform: Transform) -> str | None:
        """Replace a name in an import statement.

        from datetime import datetime, UTC → from datetime import datetime, timezone
        """
        find = transform.find
        repl = transform.replace
        old_name = find.get("import_name", "")
        new_name = repl.get("import_name", "")
        module = find.get("import_module", "")

        if not old_name:
            return None

        modified = source
        lines = modified.split("\n")
        new_lines = []

        for line in lines:
            stripped = line.strip()

            # Match: from {module} import ... {old_name} ...
            if module and stripped.startswith(f"from {module} import"):
                # Replace the specific name in the import
                # Handle: from datetime import UTC
                # Handle: from datetime import datetime, UTC
                # Handle: from datetime import datetime, UTC, timezone
                # Handle: from datetime import UTC as utc_tz
                import_part = stripped[len(f"from {module} import"):]

                # Split names (handle aliases)
                names = [n.strip() for n in import_part.split(",")]
                new_names = []
                replaced = False
                for name in names:
                    # Handle "UTC as utc_tz"
                    base = name.split(" as ")[0].strip()
                    if base == old_name:
                        if new_name:
                            # Replace with new name (check not already present)
                            existing = [n.split(" as ")[0].strip() for n in names]
                            if new_name not in existing:
                                new_names.append(new_name)
                        # else: removing the name (empty new_name)
                        replaced = True
                    else:
                        new_names.append(name)

                if replaced:
                    indent = line[:len(line) - len(stripped)]
                    if new_names:
                        new_import = f"{indent}from {module} import {', '.join(new_names)}"
                        new_lines.append(new_import)
                    # else: name was the only import — remove the entire line
                    continue

            new_lines.append(line)

        result = "\n".join(new_lines)
        return result if result != source else None

    def _transform_replace_usage(self, source: str, transform: Transform) -> str | None:
        """Replace usages of an imported name.

        UTC → timezone.utc (only where UTC refers to the import)
        """
        find = transform.find
        repl = transform.replace
        old_name = find.get("name", "")
        new_expr = repl.get("expression", "")

        if not old_name or not new_expr:
            return None

        # Use AST to find usages of the name
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return None

        # Find all Name nodes with the old name
        # (excluding the import statement itself which was already handled)
        replacements: list[tuple[int, int, int, int, str]] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == old_name:
                # Skip if this is part of an import statement
                parent_map = {}
                for parent in ast.walk(tree):
                    for child in ast.iter_child_nodes(parent):
                        parent_map[id(child)] = parent
                parent = parent_map.get(id(node))
                if isinstance(parent, (ast.Import, ast.ImportFrom)):
                    continue
                if isinstance(parent, ast.alias):
                    continue

                replacements.append((
                    node.lineno, node.col_offset,
                    node.end_lineno or node.lineno,
                    node.end_col_offset or (node.col_offset + len(old_name)),
                    new_expr,
                ))

        if not replacements:
            return None

        # Apply replacements bottom-up to preserve positions
        lines = source.split("\n")
        for lineno, col_start, end_lineno, col_end, new_text in sorted(
            replacements, reverse=True
        ):
            if lineno == end_lineno:
                line_idx = lineno - 1
                line = lines[line_idx]
                lines[line_idx] = line[:col_start] + new_text + line[col_end:]

        return "\n".join(lines)

    def _transform_replace_import_statement(self, source: str, transform: Transform) -> str | None:
        """Replace an entire import statement."""
        find = transform.find
        repl = transform.replace
        pattern = find.get("import_pattern", "")
        replacement = repl.get("import_statement", "")
        prefix = repl.get("import_prefix", "")

        if not pattern:
            return None

        lines = source.split("\n")
        new_lines = []
        changed = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith(pattern):
                indent = line[:len(line) - len(stripped)]
                if replacement:
                    new_lines.append(indent + replacement)
                elif prefix:
                    # Replace just the prefix: "from tomllib import" → "from tomli import"
                    rest = stripped[len(pattern):]
                    new_lines.append(indent + prefix + rest)
                changed = True
            else:
                new_lines.append(line)

        if changed:
            return "\n".join(new_lines)
        return None

    def _transform_add_import(self, source: str, transform: Transform) -> str | None:
        """Add an import line to the file."""
        import_line = transform.replace.get("import_statement", "")
        if not import_line:
            import_line = transform.find.get("import_statement", "")
        condition = transform.condition

        if not import_line:
            return None

        # Check if already present
        if condition == "not_already_present" or True:  # Always check
            if import_line.strip() in source:
                return None

        # Find insertion point (after existing imports or after docstring)
        lines = source.split("\n")
        insert_at = 0

        # Skip shebang
        if lines and lines[0].startswith("#!"):
            insert_at = 1

        # Skip encoding
        if insert_at < len(lines) and re.match(r"#.*coding[:=]", lines[insert_at]):
            insert_at += 1

        # Skip docstring
        if insert_at < len(lines):
            line = lines[insert_at].strip()
            if line.startswith('"""') or line.startswith("'''"):
                quote = line[:3]
                if line.count(quote) >= 2 and len(line) > 3:
                    insert_at += 1
                else:
                    for i in range(insert_at + 1, len(lines)):
                        if quote in lines[i]:
                            insert_at = i + 1
                            break

        # Skip blank lines after docstring
        while insert_at < len(lines) and not lines[insert_at].strip():
            insert_at += 1

        # Insert
        lines.insert(insert_at, import_line.strip())

        # Add blank line after if next line isn't blank or import
        if (insert_at + 1 < len(lines) and
                lines[insert_at + 1].strip() and
                not lines[insert_at + 1].strip().startswith(("from ", "import "))):
            lines.insert(insert_at + 1, "")

        return "\n".join(lines)

    def _transform_remove_import(self, source: str, transform: Transform) -> str | None:
        """Remove an import statement."""
        pattern = transform.find.get("import_statement", "")
        if not pattern:
            return None

        lines = source.split("\n")
        new_lines = [l for l in lines if l.strip() != pattern.strip()]

        if len(new_lines) < len(lines):
            return "\n".join(new_lines)
        return None

    def _transform_conditional_import(self, source: str, transform: Transform) -> str | None:
        """Wrap an import in try/except."""
        find = transform.find
        repl = transform.replace
        module = find.get("import_module", "")
        try_import = repl.get("try_import", "")
        except_import = repl.get("except_import", "")
        except_type = repl.get("except_type", "ImportError")

        if not module or not try_import or not except_import:
            return None

        lines = source.split("\n")
        new_lines = []
        changed = False

        for line in lines:
            stripped = line.strip()
            if (stripped.startswith(f"import {module}") or
                    stripped.startswith(f"from {module} import")):
                indent = line[:len(line) - len(stripped)]
                new_lines.append(f"{indent}try:")
                new_lines.append(f"{indent}    {try_import}")
                new_lines.append(f"{indent}except {except_type}:")
                new_lines.append(f"{indent}    {except_import}")
                changed = True
            else:
                new_lines.append(line)

        if changed:
            return "\n".join(new_lines)
        return None

    def _transform_rewrite_method_call(self, source: str, transform: Transform) -> str | None:
        """Rewrite a method call: s.removeprefix("x") → s[len("x"):] if ...

        Uses AST to find Call nodes with the target method name,
        then performs text replacement using the exact source positions.
        Handles complex receivers (function calls, subscripts, etc.).
        """
        method = transform.find.get("method", "")
        template = transform.replace.get("template", "")

        if not method or not template:
            return None

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return None

        lines = source.split("\n")
        replacements: list[tuple[int, int, int, str]] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            if func.attr != method:
                continue

            # Get source segments
            receiver_src = ast.get_source_segment(source, func.value)
            if not receiver_src:
                continue

            full_src = ast.get_source_segment(source, node)
            if not full_src:
                continue

            # Get the first argument
            if node.args:
                arg_src = ast.get_source_segment(source, node.args[0])
            else:
                continue
            if not arg_src:
                continue

            # Check if receiver is complex (needs temp variable)
            is_complex = isinstance(func.value, (ast.Call, ast.Subscript, ast.BinOp))

            if is_complex:
                # Complex receiver — use a temp variable to avoid double evaluation
                # Handle as a whole-line text replacement instead of position-based
                tmp_name = "_tmp"
                replacement = template.replace("{receiver}", tmp_name).replace("{arg}", arg_src)
                # Store as a special "line replacement" type
                replacements.append((
                    node.lineno, -1, -1,  # -1 signals whole-line mode
                    f"{tmp_name} = {receiver_src}\n" + lines[node.lineno - 1].replace(full_src, replacement),
                ))
            else:
                replacement = template.replace("{receiver}", receiver_src).replace("{arg}", arg_src)
                replacements.append((
                    node.lineno, node.col_offset,
                    node.end_col_offset or (node.col_offset + len(full_src)),
                    replacement,
                ))

        if not replacements:
            return None

        # Apply replacements bottom-up
        for lineno, col_start, col_end, new_text in sorted(replacements, reverse=True):
            line_idx = lineno - 1
            if line_idx < len(lines):
                if col_start == -1:
                    # Whole-line replacement (complex receiver with temp var)
                    lines[line_idx] = new_text
                else:
                    line = lines[line_idx]
                    lines[line_idx] = line[:col_start] + new_text + line[col_end:]

        return "\n".join(lines)

    def _transform_rewrite_binary_op(self, source: str, transform: Transform) -> str | None:
        """Rewrite a binary operation: a | b → {**a, **b}."""
        # This is a placeholder — proper dict | detection needs type info
        # For now, skip to avoid false positives with int | int
        return None

    def _transform_replace_identifier(self, source: str, transform: Transform) -> str | None:
        """Replace an identifier: any → interface{}."""
        old = transform.find.get("name", "")
        new = transform.replace.get("expression", "")
        if not old or not new:
            return None

        # Word-boundary replacement
        pattern = re.compile(rf'\b{re.escape(old)}\b')
        result = pattern.sub(new, source)
        return result if result != source else None

    def _transform_rewrite_walrus(self, source: str, transform: Transform, finding: Finding) -> str | None:
        """Rewrite walrus operator: (n := expr) → separate assignment + usage.

        Handles:
        - if (n := len(x)) > 10: → n = len(x); if n > 10:
        - while (chunk := f.read()): → chunk = f.read(); while chunk:
        """
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return None

        lines = source.split("\n")
        modifications = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.NamedExpr):
                continue

            line_idx = node.lineno - 1
            if line_idx >= len(lines):
                continue

            line = lines[line_idx]
            target_name = node.target.id
            # Get the value expression source
            value_source = ast.get_source_segment(source, node.value)
            if not value_source:
                continue

            # Get the full walrus expression source
            walrus_source = ast.get_source_segment(source, node)
            if not walrus_source:
                continue

            # Determine the context — if, while, or standalone
            indent = line[:len(line) - len(line.lstrip())]

            # Replace the walrus in the line with just the target name
            # and prepend an assignment line
            new_line = line.replace(f"({walrus_source})", target_name)
            new_line = new_line.replace(walrus_source, target_name)
            assignment = f"{indent}{target_name} = {value_source}"

            modifications.append((line_idx, assignment, new_line))

        if not modifications:
            return None

        # Apply modifications bottom-up
        for line_idx, assignment, new_line in sorted(modifications, reverse=True):
            lines[line_idx] = new_line
            lines.insert(line_idx, assignment)

        return "\n".join(lines)

    def _transform_rewrite_type_alias(self, source: str, transform: Transform, finding: Finding) -> str | None:
        """Rewrite type statement: type X = Y → X: TypeAlias = Y.

        Python 3.12+ type statement → typing.TypeAlias annotation.
        """
        # Match: type Name = Expression
        pattern = re.compile(r'^(\s*)type\s+(\w+)\s*=\s*(.+)$', re.MULTILINE)

        def replacer(m: re.Match) -> str:
            indent = m.group(1)
            name = m.group(2)
            value = m.group(3)
            return f"{indent}{name}: TypeAlias = {value}"

        result = pattern.sub(replacer, source)

        if result != source:
            # Add TypeAlias import if not present
            if "from typing import TypeAlias" not in result:
                # Find insertion point
                add_result = self._transform_add_import(result, type(
                    'T', (), {'replace': {'import_statement': 'from typing import TypeAlias'},
                              'condition': 'not_already_present', 'find': {}})()
                )
                if add_result:
                    return add_result
            return result
        return None

    def _transform_split_with(self, source: str, transform: Transform, finding: Finding) -> str | None:
        """Split parenthesized context managers into nested with statements.

        with (open("a") as f1, open("b") as f2): body
        →
        with open("a") as f1:
            with open("b") as f2:
                body
        """
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return None

        lines = source.split("\n")
        modifications = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.With):
                continue
            if len(node.items) <= 1:
                continue

            # Found a with statement with multiple items
            line_idx = node.lineno - 1
            # Find the end of the with header (might span multiple lines)
            end_line = node.body[0].lineno - 1 if node.body else line_idx + 1

            # Get the body lines
            body_lines = []
            if node.body:
                body_start = node.body[0].lineno - 1
                body_end = node.body[-1].end_lineno if hasattr(node.body[-1], 'end_lineno') and node.body[-1].end_lineno else body_start + 1
                body_lines = lines[body_start:body_end]

            # Get the indent of the original with
            orig_line = lines[line_idx]
            base_indent = orig_line[:len(orig_line) - len(orig_line.lstrip())]

            # Build nested with statements
            new_lines = []
            for i, item in enumerate(node.items):
                ctx = ast.get_source_segment(source, item.context_expr)
                var = ast.get_source_segment(source, item.optional_vars) if item.optional_vars else None
                extra_indent = "    " * i
                as_part = f" as {var}" if var else ""
                new_lines.append(f"{base_indent}{extra_indent}with {ctx}{as_part}:")

            # Re-indent body
            inner_indent = "    " * len(node.items)
            for bl in body_lines:
                # Determine original body indentation
                stripped = bl.lstrip()
                if stripped:
                    new_lines.append(f"{base_indent}{inner_indent}{stripped}")
                else:
                    new_lines.append("")

            modifications.append((line_idx, end_line if end_line > line_idx else line_idx + 1, body_end if node.body else line_idx + 1, new_lines))

        if not modifications:
            return None

        # Apply modifications (only handle the first one for now)
        if modifications:
            mod = modifications[0]
            start, _, end, new_lines = mod
            lines[start:end] = new_lines

        return "\n".join(lines)

    def _transform_rewrite_builtin_generic(self, source: str, transform: Transform) -> str | None:
        """Rewrite list[int] → List[int] with typing import.

        Fallback for when __future__ annotations can't be used.
        Replaces builtin generic subscripts in annotations with typing equivalents.
        """
        typing_name = transform.replace.get("typing_name", "")
        find_name = transform.find.get("annotation_value_name", "")

        if not typing_name or not find_name:
            return None

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return None

        lines = source.split("\n")
        modifications = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Subscript):
                continue
            if not isinstance(node.value, ast.Name):
                continue
            if node.value.id != find_name:
                continue

            # Replace the name in the source
            line_idx = node.value.lineno - 1
            col = node.value.col_offset
            end_col = col + len(find_name)

            modifications.append((line_idx, col, end_col, typing_name))

        if not modifications:
            return None

        # Apply bottom-up
        for line_idx, col, end_col, new_name in sorted(modifications, reverse=True):
            line = lines[line_idx]
            lines[line_idx] = line[:col] + new_name + line[end_col:]

        result = "\n".join(lines)

        # Add typing import
        add_import = transform.replace.get("add_import", "")
        if add_import and add_import not in result:
            import_transform = type('T', (), {
                'replace': {'import_statement': add_import},
                'condition': 'not_already_present',
                'find': {},
            })()
            added = self._transform_add_import(result, import_transform)
            if added:
                return added

        return result

    def _transform_rewrite_annotation(self, source: str, transform: Transform) -> str | None:
        """Rewrite type annotations: Optional[X] → X | None, Union[X, Y] → X | Y.

        Used for upgrade direction — modernize old typing imports.
        """
        find_type = transform.find.get("annotation_type", "")
        find_value = transform.find.get("annotation_value", "")
        template = transform.replace.get("template", "")

        if not find_value or not template:
            return None

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return None

        lines = source.split("\n")
        modifications = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Subscript):
                continue
            if not isinstance(node.value, ast.Name):
                continue
            if node.value.id != find_value:
                continue

            # Get the full source of this subscript
            full = ast.get_source_segment(source, node)
            if not full:
                continue

            # Extract the inner type(s)
            if find_value == "Optional":
                # Optional[X] → X | None
                inner = ast.get_source_segment(source, node.slice)
                if inner:
                    replacement = template.replace("{inner}", inner)
                    modifications.append((node.lineno - 1, node.col_offset,
                                          node.end_col_offset or (node.col_offset + len(full)),
                                          replacement))

            elif find_value == "Union":
                # Union[X, Y] → X | Y
                if isinstance(node.slice, ast.Tuple):
                    parts = []
                    for elt in node.slice.elts:
                        part = ast.get_source_segment(source, elt)
                        if part:
                            parts.append(part)
                    if parts:
                        replacement = template.replace("{args_joined_pipe}", " | ".join(parts))
                        modifications.append((node.lineno - 1, node.col_offset,
                                              node.end_col_offset or (node.col_offset + len(full)),
                                              replacement))

        if not modifications:
            return None

        # Apply bottom-up
        for line_idx, col, end_col, replacement in sorted(modifications, reverse=True):
            line = lines[line_idx]
            lines[line_idx] = line[:col] + replacement + line[end_col:]

        return "\n".join(lines)
