"""Finding data model — the result of detecting a feature in code."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Finding:
    """A single detected feature usage in source code.

    Created by the detection engine when an AST node matches
    a feature database entry's detection rule.
    """
    # What was found
    feature_id: str                     # "python.stdlib.datetime_utc"
    feature_name: str                   # "datetime.UTC"

    # Where it was found
    file: str                           # "src/core/models/action.py" (relative to project root)
    line: int                           # 11
    col: int = 0                        # 0
    source_line: str = ""               # "from datetime import UTC, datetime"

    # Classification
    severity: str = "error"             # "error", "warning", "info"
    error_type: str = ""                # "import_error", "syntax_error", etc.
    error_subtype: str = ""             # "missing_name", "missing_module", etc.
    version: str = ""                   # "3.11" — version the feature was introduced

    # Fix info
    fix_available: bool = True
    fix_strategy: str = ""              # "replace_import_and_usages", "manual", etc.

    # Transitive import info
    is_transitive: bool = False         # True if found via import chain (not in module being analyzed)
    imported_by: str | None = None      # File in the analyzed module that triggers this import
    import_chain: list[str] = field(default_factory=list)  # Full import path
    source_module: str | None = None    # Which project module this file belongs to

    # Status (updated by fix engine)
    status: str = "detected"            # "detected", "fixed", "verified", "failed", "excluded"

    # AST node info (for the fix engine to use)
    ast_node_type: str = ""             # "ImportFrom", "Attribute", etc.
    detection_rule_index: int = 0       # Which detection rule matched (0=primary, 1+=alternative)


@dataclass
class AnalysisResult:
    """Complete result of analyzing a module."""
    module_dir: str
    language: str
    target_version: str
    direction: str

    # Findings
    findings: list[Finding] = field(default_factory=list)

    # Scan metadata
    files_scanned: int = 0
    files_with_findings: int = 0
    parse_errors: list[ParseError] = field(default_factory=list)
    scan_duration_ms: int = 0

    @property
    def total_findings(self) -> int:
        return len(self.findings)

    @property
    def direct_findings(self) -> list[Finding]:
        return [f for f in self.findings if not f.is_transitive]

    @property
    def transitive_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.is_transitive]

    @property
    def fixable_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.fix_available]

    @property
    def manual_findings(self) -> list[Finding]:
        return [f for f in self.findings if not f.fix_available]

    @property
    def error_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    def by_feature(self) -> dict[str, list[Finding]]:
        """Group findings by feature_id."""
        groups: dict[str, list[Finding]] = {}
        for f in self.findings:
            groups.setdefault(f.feature_id, []).append(f)
        return groups

    def by_file(self) -> dict[str, list[Finding]]:
        """Group findings by file path."""
        groups: dict[str, list[Finding]] = {}
        for f in self.findings:
            groups.setdefault(f.file, []).append(f)
        return groups

    def by_severity(self) -> dict[str, list[Finding]]:
        """Group findings by severity."""
        groups: dict[str, list[Finding]] = {}
        for f in self.findings:
            groups.setdefault(f.severity, []).append(f)
        return groups

    def summary(self) -> dict:
        """Summary statistics."""
        return {
            "total": self.total_findings,
            "direct": len(self.direct_findings),
            "transitive": len(self.transitive_findings),
            "by_severity": {sev: len(items) for sev, items in self.by_severity().items()},
            "by_fix": {
                "auto_fixable": len(self.fixable_findings),
                "manual": len(self.manual_findings),
            },
            "files_scanned": self.files_scanned,
            "files_with_findings": self.files_with_findings,
            "parse_errors": len(self.parse_errors),
            "scan_duration_ms": self.scan_duration_ms,
        }


@dataclass
class ParseError:
    """A file that couldn't be parsed."""
    file: str
    error_type: str                     # "syntax", "encoding", "permission", "size"
    message: str
    line: int | None = None
