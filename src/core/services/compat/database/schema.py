"""Feature database schema — data models for all entries.

Every version-specific language feature is a FeatureEntry.
Detection and fix are fields on the SAME entry — never separated.
Every entry has test cases proving detection and fix work together.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# ── Enums ────────────────────────────────────────────────────────


class Direction(Enum):
    """Which direction a feature entry applies to."""
    DOWNGRADE = "downgrade"
    UPGRADE = "upgrade"
    BOTH = "both"


class Severity(Enum):
    """How critical the finding is."""
    ERROR = "error"        # Code will crash / won't parse
    WARNING = "warning"    # Code may behave differently or is deprecated
    INFO = "info"          # Modernization opportunity, not required


class ErrorType(Enum):
    """Top-level error classification."""
    IMPORT_ERROR = "import_error"
    SYNTAX_ERROR = "syntax_error"
    RUNTIME_ERROR = "runtime_error"
    TYPE_ERROR = "type_error"
    DEPRECATION_WARNING = "deprecation_warning"
    BEHAVIORAL_CHANGE = "behavioral_change"
    DEPENDENCY_ERROR = "dependency_error"


class FixStrategy(Enum):
    """How the fix engine should handle this feature."""
    REPLACE_IMPORT = "replace_import"
    REPLACE_IMPORT_AND_USAGES = "replace_import_and_usages"
    REWRITE_EXPRESSION = "rewrite_expression"
    ADD_IMPORT = "add_import"
    REMOVE_IMPORT = "remove_import"
    ADD_BACKPORT_IMPORT = "add_backport_import"
    WRAP_IN_TRY_EXCEPT = "wrap_in_try_except"
    ADD_VERSION_GATE = "add_version_gate"
    ADD_FUTURE_IMPORT = "add_future_import"
    MANUAL = "manual"
    NO_FIX_NEEDED = "no_fix_needed"


# ── Detection rules ─────────────────────────────────────────────


@dataclass
class DetectionRule:
    """A single detection rule — matches an AST node type + attributes."""
    ast_type: str                          # AST node type name: "ImportFrom", "Match", etc.
    match: dict[str, object] = field(default_factory=dict)
    context: str | None = None             # "any", "module_level", "annotation", "runtime",
                                           # "type_checking_block", "try_block", etc.


@dataclass
class Detection:
    """Full detection specification for a feature."""
    primary: DetectionRule                 # Main detection rule
    alternatives: list[DetectionRule] = field(default_factory=list)
    exclude: list[ExclusionRule] = field(default_factory=list)


@dataclass
class ExclusionRule:
    """A pattern to EXCLUDE from detection (false positive prevention)."""
    ast_type: str | None = None
    match: dict[str, object] = field(default_factory=dict)
    context: str | None = None
    reason: str = ""


# ── Fix rules ────────────────────────────────────────────────────


@dataclass
class Transform:
    """A single code transformation to apply."""
    type: str                              # Transform type from the catalog (doc 15)
    find: dict[str, object] = field(default_factory=dict)
    replace: dict[str, object] = field(default_factory=dict)
    scope: str | None = None               # "file", "imported_name", "expression"
    condition: str | None = None           # "not_already_present", etc.


@dataclass
class BackportInfo:
    """Information about a backport package for this feature."""
    package: str                           # "tomli", "backports.strenum"
    min_version: str = ""                  # "1.0.0"
    max_version: str | None = None
    import_name: str = ""                  # What to import from the backport
    import_as: str | None = None           # Alias: import X as Y
    import_statement: str | None = None    # Full import line override
    install_command: str = ""              # "pip install tomli>=1.0.0"
    supports_versions: str = ""            # What lang versions the backport supports
    maintained: bool = True
    notes: str = ""


@dataclass
class Fix:
    """Complete fix specification for a feature."""
    strategy: FixStrategy
    transforms: list[Transform] = field(default_factory=list)
    backport: BackportInfo | None = None
    manual_instructions: str | None = None

    # Alternative fix (e.g., try/except wrapper instead of direct replacement)
    alternative: Fix | None = None


@dataclass
class Verification:
    """How to verify a fix worked."""
    re_detect: bool = True                 # Re-run detection — must find 0 matches
    syntax_check: bool = True              # File must parse without errors
    import_check: bool = True              # File must still be importable
    custom_check: CustomCheck | None = None


@dataclass
class CustomCheck:
    """Optional custom verification command."""
    command: str
    description: str = ""
    expected_exit_code: int = 0
    timeout: int = 5


# ── Edge cases ───────────────────────────────────────────────────


@dataclass
class EdgeCase:
    """A documented edge case for a feature."""
    id: str                                # "python.datetime_utc.type_checking_block"
    category: str = ""                     # "false_positive", "context_dependent", "transform_edge_case"
    description: str = ""
    handling: str = ""                     # "exclude", "downgrade_severity", "special_transform"
    severity_override: str | None = None
    detection_modifier: DetectionRule | None = None
    test: EdgeCaseTest | None = None


@dataclass
class EdgeCaseTest:
    """Test data for an edge case."""
    input: str = ""                        # Source code input (for exclusion tests)
    before: str = ""                       # Source before fix (for transform tests)
    after: str = ""                        # Expected source after fix
    expected_findings: int | None = None   # Expected number of findings
    expected_severity: str | None = None   # Expected severity if found
    notes: str = ""


# ── Test cases ───────────────────────────────────────────────────


@dataclass
class TestCase:
    """Before/after source code proving the fix works."""
    before: str                            # Code using the feature
    after: str                             # Code after fix applied


@dataclass
class AdditionalTest:
    """Named additional test case for edge cases."""
    name: str
    before: str
    after: str


# ── The main entry ───────────────────────────────────────────────


@dataclass
class FeatureEntry:
    """A single feature in the database.

    This is the fundamental unit. Detection and fix are fields on
    the SAME object. They are never separated.

    Every entry has a test case proving detection and fix work together.
    """
    # Identity
    id: str                                # "python.stdlib.datetime_utc"
    language: str                          # "python", "javascript", etc.
    feature_name: str                      # "datetime.UTC"

    # Version info
    introduced: str                        # "3.11", "ES2020", "1.21"
    removed: str | None = None             # Version removed (rare)
    deprecated: str | None = None          # Version deprecated

    # Classification
    category: str = ""                     # "stdlib", "syntax", "typing", "builtins", etc.
    description: str = ""
    direction: Direction = Direction.DOWNGRADE
    severity: Severity = Severity.ERROR
    error_type: ErrorType = ErrorType.RUNTIME_ERROR
    error_subtype: str = ""                # "missing_name", "missing_module", etc.
    tags: list[str] = field(default_factory=list)

    # Detection (REQUIRED)
    detection: Detection = field(default_factory=lambda: Detection(
        primary=DetectionRule(ast_type="")
    ))

    # Fix (REQUIRED — coupled with detection)
    fix: Fix = field(default_factory=lambda: Fix(strategy=FixStrategy.MANUAL))

    # Bidirectional entries can have separate fix for upgrade
    fix_upgrade: Fix | None = None

    # Verification
    verification: Verification = field(default_factory=Verification)

    # Edge cases
    edge_cases: list[EdgeCase] = field(default_factory=list)

    # Test (REQUIRED — proves detection + fix work together)
    test: TestCase = field(default_factory=lambda: TestCase(before="", after=""))
    test_additional: list[AdditionalTest] = field(default_factory=list)

    def is_valid(self) -> tuple[bool, list[str]]:
        """Validate this entry has all required fields.

        Returns (valid, errors).
        """
        errors: list[str] = []

        if not self.id:
            errors.append("id is required")
        if not self.language:
            errors.append("language is required")
        if not self.feature_name:
            errors.append("feature_name is required")
        if not self.introduced:
            errors.append("introduced is required")
        if not self.detection.primary.ast_type:
            errors.append("detection.primary.ast_type is required")
        if self.fix.strategy not in (FixStrategy.MANUAL, FixStrategy.NO_FIX_NEEDED):
            if not self.fix.transforms:
                errors.append("fix.transforms required for non-manual strategies")
        if not self.test.before:
            errors.append("test.before is required")
        if self.fix.strategy != FixStrategy.MANUAL and not self.test.after:
            errors.append("test.after is required for non-manual fixes")

        return (len(errors) == 0, errors)


# ── Language metadata ────────────────────────────────────────────


@dataclass
class LanguageMeta:
    """Metadata for a supported language."""
    language: str                          # "python"
    display_name: str                      # "Python"
    file_extensions: list[str]             # [".py"]
    parser: str                            # "ast", "tree-sitter-javascript", etc.
    versions: list[VersionInfo] = field(default_factory=list)
    version_format: str = "major.minor"    # How versions are compared
    default_exclusions: list[str] = field(default_factory=list)
    import_styles: list[str] = field(default_factory=list)
    package_registry: RegistryInfo | None = None


@dataclass
class VersionInfo:
    """A language version."""
    version: str                           # "3.8"
    eol: str = ""                          # "2024-10-14"
    status: str = ""                       # "active", "security", "eol"


@dataclass
class RegistryInfo:
    """Package registry configuration."""
    name: str                              # "PyPI"
    api: str = ""                          # "https://pypi.org/pypi/{package}/json"
    version_field: str = ""                # "requires_python"
