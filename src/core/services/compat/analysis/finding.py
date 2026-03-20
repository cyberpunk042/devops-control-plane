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

    def to_dict(self) -> dict:
        """Serialize for mediator persistence."""
        return {
            "feature_id": self.feature_id,
            "feature_name": self.feature_name,
            "file": self.file,
            "line": self.line,
            "col": self.col,
            "source_line": self.source_line,
            "severity": self.severity,
            "error_type": self.error_type,
            "error_subtype": self.error_subtype,
            "version": self.version,
            "fix_available": self.fix_available,
            "fix_strategy": self.fix_strategy,
            "is_transitive": self.is_transitive,
            "imported_by": self.imported_by,
            "import_chain": self.import_chain,
            "source_module": self.source_module,
            "status": self.status,
            "ast_node_type": self.ast_node_type,
            "detection_rule_index": self.detection_rule_index,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Finding:
        """Deserialize from mediator shard."""
        return cls(
            feature_id=d.get("feature_id", ""),
            feature_name=d.get("feature_name", ""),
            file=d.get("file", ""),
            line=d.get("line", 0),
            col=d.get("col", 0),
            source_line=d.get("source_line", ""),
            severity=d.get("severity", "error"),
            error_type=d.get("error_type", ""),
            error_subtype=d.get("error_subtype", ""),
            version=d.get("version", ""),
            fix_available=d.get("fix_available", True),
            fix_strategy=d.get("fix_strategy", ""),
            is_transitive=d.get("is_transitive", False),
            imported_by=d.get("imported_by"),
            import_chain=d.get("import_chain", []),
            source_module=d.get("source_module"),
            status=d.get("status", "detected"),
            ast_node_type=d.get("ast_node_type", ""),
            detection_rule_index=d.get("detection_rule_index", 0),
        )


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

    def to_dict(self) -> dict:
        """Serialize for mediator persistence."""
        return {
            "module_dir": self.module_dir,
            "language": self.language,
            "target_version": self.target_version,
            "direction": self.direction,
            "findings": [f.to_dict() for f in self.findings],
            "files_scanned": self.files_scanned,
            "files_with_findings": self.files_with_findings,
            "parse_errors": [
                {"file": e.file, "error_type": e.error_type,
                 "message": e.message, "line": e.line}
                for e in self.parse_errors
            ],
            "scan_duration_ms": self.scan_duration_ms,
        }

    @classmethod
    def from_dict(cls, d: dict) -> AnalysisResult:
        """Deserialize from mediator shard."""
        return cls(
            module_dir=d.get("module_dir", ""),
            language=d.get("language", ""),
            target_version=d.get("target_version", ""),
            direction=d.get("direction", ""),
            findings=[Finding.from_dict(f) for f in d.get("findings", [])],
            files_scanned=d.get("files_scanned", 0),
            files_with_findings=d.get("files_with_findings", 0),
            parse_errors=[
                ParseError(
                    file=e.get("file", ""),
                    error_type=e.get("error_type", ""),
                    message=e.get("message", ""),
                    line=e.get("line"),
                )
                for e in d.get("parse_errors", [])
            ],
            scan_duration_ms=d.get("scan_duration_ms", 0),
        )


@dataclass
class ParseError:
    """A file that couldn't be parsed."""
    file: str
    error_type: str                     # "syntax", "encoding", "permission", "size"
    message: str
    line: int | None = None
