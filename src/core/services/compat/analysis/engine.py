"""Detection engine — AST-based code analysis for version compatibility.

Scans source files, matches feature database entries against AST nodes,
collects findings. Language-agnostic at the orchestration level — delegates
all language-specific operations to backends.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from ..backends.base import LanguageBackend
from ..database.registry import FeatureRegistry
from ..database.schema import Detection, DetectionRule, ExclusionRule, FeatureEntry
from .finding import AnalysisResult, Finding, ParseError

logger = logging.getLogger(__name__)

# Max files to scan in one module (safety limit)
_MAX_FILES = 5000

# Default exclusion patterns
_DEFAULT_EXCLUSIONS = {"__pycache__", ".git", ".svn", "node_modules", ".venv", "venv"}


class DetectionEngine:
    """Main API for code analysis."""

    def __init__(
        self,
        registry: FeatureRegistry,
        backend: LanguageBackend,
    ):
        self._registry = registry
        self._backend = backend
        self._ast_cache: dict[str, Any] = {}
        self._source_cache: dict[str, str] = {}

    def analyze_module(
        self,
        module_dir: Path,
        target_version: str,
        direction: str = "downgrade",
        project_root: Path | None = None,
    ) -> AnalysisResult:
        """Analyze a module for version compatibility issues.

        Args:
            module_dir: Path to the module directory
            target_version: The version we're targeting (e.g., "3.8")
            direction: "downgrade" or "upgrade"
            project_root: Project root for relative paths (default: module_dir.parent)

        Returns:
            AnalysisResult with all findings
        """
        t0 = time.time()
        project_root = project_root or module_dir.parent
        language = self._backend.language_id

        # Get entries relevant to this analysis
        if direction == "downgrade":
            entries = self._registry.above_version(language, target_version)
        else:
            entries = self._registry.below_version(language, target_version)

        if not entries:
            return AnalysisResult(
                module_dir=str(module_dir),
                language=language,
                target_version=target_version,
                direction=direction,
                scan_duration_ms=int((time.time() - t0) * 1000),
            )

        # Discover source files
        files = self._discover_files(module_dir)
        if not files:
            return AnalysisResult(
                module_dir=str(module_dir),
                language=language,
                target_version=target_version,
                direction=direction,
                scan_duration_ms=int((time.time() - t0) * 1000),
            )

        # Scan each file
        all_findings: list[Finding] = []
        parse_errors: list[ParseError] = []
        files_with_findings: set[str] = set()

        for file_path in files:
            file_findings, file_errors = self._scan_file(
                file_path, entries, project_root,
            )
            all_findings.extend(file_findings)
            parse_errors.extend(file_errors)
            if file_findings:
                files_with_findings.add(str(file_path))

        elapsed = int((time.time() - t0) * 1000)

        return AnalysisResult(
            module_dir=str(module_dir),
            language=language,
            target_version=target_version,
            direction=direction,
            findings=all_findings,
            files_scanned=len(files),
            files_with_findings=len(files_with_findings),
            parse_errors=parse_errors,
            scan_duration_ms=elapsed,
        )

    def analyze_file(
        self,
        file_path: Path,
        target_version: str,
        direction: str = "downgrade",
        project_root: Path | None = None,
        feature_ids: list[str] | None = None,
    ) -> list[Finding]:
        """Analyze a single file.

        Args:
            file_path: Path to the source file
            target_version: Target version
            direction: "downgrade" or "upgrade"
            project_root: Project root for relative paths
            feature_ids: Only check these specific features (for verification)
        """
        project_root = project_root or file_path.parent
        language = self._backend.language_id

        if feature_ids:
            entries = [
                self._registry.get(fid) for fid in feature_ids
                if self._registry.get(fid) is not None
            ]
        elif direction == "downgrade":
            entries = self._registry.above_version(language, target_version)
        else:
            entries = self._registry.below_version(language, target_version)

        findings, _ = self._scan_file(file_path, entries, project_root)
        return findings

    def analyze_transitive(
        self,
        module_dir: Path,
        module_name: str,
        target_version: str,
        project_root: Path,
        module_configs: list[dict] | None = None,
        direction: str = "downgrade",
    ) -> AnalysisResult:
        """Analyze a module INCLUDING its transitive import dependencies.

        1. Build import graph from module's files
        2. Follow imports to other project modules
        3. Analyze those files too
        4. Mark findings as direct or transitive
        5. Include import chain info for transitive findings
        """
        from .import_resolver import ImportResolver

        t0 = time.time()
        language = self._backend.language_id

        # Get entries
        if direction == "downgrade":
            entries = self._registry.above_version(language, target_version)
        else:
            entries = self._registry.below_version(language, target_version)

        if not entries:
            return AnalysisResult(
                module_dir=str(module_dir),
                language=language,
                target_version=target_version,
                direction=direction,
            )

        # Build import graph
        resolver = ImportResolver(self._backend, project_root, module_configs or [])
        graph = resolver.build_graph(
            module_dir=module_dir,
            module_name=module_name,
            follow_transitive=True,
            max_depth=5,
        )

        # Get all files to scan (module files + transitive imports)
        module_files = set(graph.files_in_module(module_name))
        all_files = set(graph.nodes.keys())

        # Scan all files
        all_findings: list[Finding] = []
        parse_errors: list[ParseError] = []
        files_with_findings: set[str] = set()

        for file_rel in sorted(all_files):
            file_path = project_root / file_rel
            if not file_path.is_file():
                continue

            file_findings, file_errors = self._scan_file(file_path, entries, project_root)

            # Mark transitive findings
            is_module_file = file_rel in module_files
            for f in file_findings:
                if not is_module_file:
                    f.is_transitive = True
                    node = graph.nodes.get(file_rel)
                    f.source_module = node.belongs_to_module if node else ""
                    # Find import chain from module to this file
                    chain = graph.shortest_path_from_module(module_name, file_rel)
                    if chain:
                        f.imported_by = chain[0]
                        f.import_chain = chain

            all_findings.extend(file_findings)
            parse_errors.extend(file_errors)
            if file_findings:
                files_with_findings.add(file_rel)

        elapsed = int((time.time() - t0) * 1000)

        return AnalysisResult(
            module_dir=str(module_dir),
            language=language,
            target_version=target_version,
            direction=direction,
            findings=all_findings,
            files_scanned=len(all_files),
            files_with_findings=len(files_with_findings),
            parse_errors=parse_errors,
            scan_duration_ms=elapsed,
        )

    def verify_fix(
        self,
        file_path: Path,
        feature_id: str,
        project_root: Path | None = None,
    ) -> bool:
        """Verify that a fix removed a specific feature from a file.

        Invalidates cache, re-scans, returns True if 0 matches.
        """
        self.invalidate_cache(file_path)
        project_root = project_root or file_path.parent

        entry = self._registry.get(feature_id)
        if not entry:
            return True  # Unknown feature — assume fixed

        findings, _ = self._scan_file(file_path, [entry], project_root)
        return len(findings) == 0

    def invalidate_cache(self, file_path: Path) -> None:
        """Invalidate cached AST for a file (after modification)."""
        key = str(file_path)
        self._ast_cache.pop(key, None)
        self._source_cache.pop(key, None)

    def invalidate_all(self) -> None:
        """Clear all caches."""
        self._ast_cache.clear()
        self._source_cache.clear()

    # ── Internal ─────────────────────────────────────────────────

    def _discover_files(self, module_dir: Path) -> list[Path]:
        """Find all source files in a module directory."""
        extensions = set(self._backend.file_extensions)
        files = []

        for f in sorted(module_dir.rglob("*")):
            if not f.is_file():
                continue
            if f.suffix not in extensions:
                continue
            # Skip excluded directories
            parts = f.parts
            if any(p in _DEFAULT_EXCLUSIONS for p in parts):
                continue
            files.append(f)
            if len(files) >= _MAX_FILES:
                logger.warning("Hit file limit (%d) for %s", _MAX_FILES, module_dir)
                break

        return files

    def _scan_file(
        self,
        file_path: Path,
        entries: list[FeatureEntry],
        project_root: Path,
    ) -> tuple[list[Finding], list[ParseError]]:
        """Scan a single file against feature entries."""
        findings: list[Finding] = []
        parse_errors: list[ParseError] = []

        # Parse (with cache)
        tree, source = self._parse_cached(file_path)
        if tree is None:
            if source:  # source contains error message
                parse_errors.append(ParseError(
                    file=str(file_path.relative_to(project_root))
                    if file_path.is_relative_to(project_root) else str(file_path),
                    error_type="syntax",
                    message=source,
                ))
            return findings, parse_errors

        # Check for __future__ annotations (Python-specific optimization)
        has_future = self._backend.has_future_annotations(tree)

        # Relative path for findings
        try:
            rel_path = str(file_path.relative_to(project_root))
        except ValueError:
            rel_path = str(file_path)

        # Match each entry
        for entry in entries:
            entry_findings = self._match_entry(
                tree, source, entry, rel_path, has_future,
            )
            findings.extend(entry_findings)

        return findings, parse_errors

    def _parse_cached(self, file_path: Path) -> tuple[Any | None, str]:
        """Parse a file with caching. Returns (tree, source) or (None, error_msg)."""
        key = str(file_path)

        if key in self._ast_cache:
            return self._ast_cache[key], self._source_cache.get(key, "")

        try:
            source = file_path.read_text(encoding="utf-8", errors="ignore")
            tree = self._backend.parse_source(source, filename=str(file_path))
            self._ast_cache[key] = tree
            self._source_cache[key] = source
            return tree, source
        except SyntaxError as e:
            return None, f"Syntax error at line {e.lineno}: {e.msg}"
        except Exception as e:
            return None, f"Parse error: {e}"

    def _match_entry(
        self,
        tree: Any,
        source: str,
        entry: FeatureEntry,
        rel_path: str,
        has_future: bool,
    ) -> list[Finding]:
        """Match a single feature entry against a file's AST."""
        findings: list[Finding] = []

        # Collect all detection rules (primary + alternatives)
        rules: list[tuple[int, DetectionRule]] = [(0, entry.detection.primary)]
        for i, alt in enumerate(entry.detection.alternatives, 1):
            rules.append((i, alt))

        for rule_index, rule in rules:
            if not rule.ast_type:
                continue

            for node in self._backend.walk_ast(tree):
                if not self._backend.node_matches(node, rule.ast_type, rule.match):
                    continue

                # Context check
                if rule.context:
                    node_context = self._backend.get_node_context(node, tree)
                    if not self._context_matches(rule.context, node_context):
                        continue

                # __future__ annotations check — skip annotation-only features
                # if __future__ is present
                if has_future and entry.category == "typing":
                    node_context = self._backend.get_node_context(node, tree)
                    if node_context == "annotation":
                        continue  # Safe with __future__

                # Exclusion rules
                if self._is_excluded(node, tree, entry.detection.exclude):
                    continue

                # Edge case exclusions
                severity = entry.severity.value
                for ec in entry.edge_cases:
                    if ec.handling == "exclude":
                        if ec.detection_modifier and self._edge_case_matches(node, tree, ec):
                            break  # Excluded by edge case
                    elif ec.handling == "downgrade_severity" and ec.severity_override:
                        if ec.detection_modifier and self._edge_case_matches(node, tree, ec):
                            severity = ec.severity_override
                else:
                    # Not excluded by any edge case — create finding
                    line, col = self._backend.node_location(node)
                    source_line = self._backend.get_source_line(source, line)

                    findings.append(Finding(
                        feature_id=entry.id,
                        feature_name=entry.feature_name,
                        file=rel_path,
                        line=line,
                        col=col,
                        source_line=source_line,
                        severity=severity,
                        error_type=entry.error_type.value,
                        error_subtype=entry.error_subtype,
                        version=entry.introduced,
                        fix_available=entry.fix.strategy.value != "manual",
                        fix_strategy=entry.fix.strategy.value,
                        ast_node_type=self._backend.node_type_name(node),
                        detection_rule_index=rule_index,
                    ))
                    continue  # for/else: this runs if inner loop didn't break

        # Deduplicate (same feature + same file + same line)
        seen: set[tuple[str, int]] = set()
        deduped: list[Finding] = []
        for f in findings:
            key = (f.feature_id, f.line)
            if key not in seen:
                seen.add(key)
                deduped.append(f)

        return deduped

    def _context_matches(self, required: str, actual: str) -> bool:
        """Check if the actual context matches the required context."""
        if required == "any":
            return True
        if required == "annotation":
            return actual == "annotation"
        if required == "runtime":
            # Runtime means NOT annotation and NOT type_checking
            return actual not in ("annotation", "type_checking_block")
        if required == "not_definition":
            return actual != "class_body"
        return required == actual

    def _is_excluded(
        self,
        node: Any,
        tree: Any,
        exclude_rules: list[ExclusionRule],
    ) -> bool:
        """Check if a matched node should be excluded."""
        for rule in exclude_rules:
            if rule.context:
                node_context = self._backend.get_node_context(node, tree)
                if node_context == rule.context:
                    return True
            if rule.ast_type and rule.match:
                if self._backend.node_matches(node, rule.ast_type, rule.match):
                    return True
        return False

    def _edge_case_matches(self, node: Any, tree: Any, edge_case: Any) -> bool:
        """Check if an edge case's detection modifier matches."""
        mod = edge_case.detection_modifier
        if not mod:
            return False

        # Context-based edge cases
        if mod.context:
            node_context = self._backend.get_node_context(node, tree)
            return node_context == mod.context

        # AST-type based edge cases
        if mod.ast_type:
            return self._backend.node_matches(node, mod.ast_type, mod.match)

        return False
