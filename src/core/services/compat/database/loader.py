"""Feature database loader — reads YAML entries into FeatureEntry objects.

Loads all .yml files from database/entries/{language}/ directories.
Validates each entry against the schema.
Skips invalid entries with warnings (does not crash on one bad entry).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .schema import FeatureEntry, LanguageMeta

logger = logging.getLogger(__name__)

# Where entries live relative to this file
_ENTRIES_DIR = Path(__file__).parent / "entries"


def load_all_entries(
    entries_dir: Path | None = None,
    language: str | None = None,
) -> list[FeatureEntry]:
    """Load all feature entries from the database.

    Args:
        entries_dir: Override entries directory (default: database/entries/)
        language: Only load entries for this language (default: all)

    Returns:
        List of validated FeatureEntry objects.
    """
    import yaml

    from .schema import FeatureEntry

    base = entries_dir or _ENTRIES_DIR
    if not base.is_dir():
        logger.warning("Entries directory not found: %s", base)
        return []

    entries: list[FeatureEntry] = []
    errors: list[str] = []

    # Iterate language directories
    for lang_dir in sorted(base.iterdir()):
        if not lang_dir.is_dir():
            continue
        if language and lang_dir.name != language:
            continue

        # Load all .yml files in this language dir
        for yml_file in sorted(lang_dir.glob("*.yml")):
            if yml_file.name.startswith("_"):
                continue  # Skip _meta.yml and similar

            try:
                raw = yaml.safe_load(yml_file.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(f"{yml_file}: YAML parse error: {exc}")
                continue

            if not raw:
                continue

            # File can contain a list of entries or a single entry
            raw_entries = raw if isinstance(raw, list) else [raw]

            for raw_entry in raw_entries:
                if not isinstance(raw_entry, dict):
                    errors.append(f"{yml_file}: entry is not a dict")
                    continue

                try:
                    entry = _parse_entry(raw_entry, lang_dir.name)
                    valid, entry_errors = entry.is_valid()
                    if valid:
                        entries.append(entry)
                    else:
                        for err in entry_errors:
                            errors.append(f"{yml_file} [{raw_entry.get('id', '?')}]: {err}")
                except Exception as exc:
                    entry_id = raw_entry.get("id", "unknown")
                    errors.append(f"{yml_file} [{entry_id}]: parse error: {exc}")

    if errors:
        for err in errors:
            logger.warning("Feature DB: %s", err)

    logger.info("Feature DB: loaded %d entries (%d errors)", len(entries), len(errors))
    return entries


def load_language_meta(
    language: str,
    entries_dir: Path | None = None,
) -> LanguageMeta | None:
    """Load the _meta.yml for a language.

    Returns None if not found.
    """
    import yaml

    from .schema import LanguageMeta, RegistryInfo, VersionInfo

    base = entries_dir or _ENTRIES_DIR
    meta_path = base / language / "_meta.yml"

    if not meta_path.is_file():
        return None

    try:
        raw = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to load %s: %s", meta_path, exc)
        return None

    if not isinstance(raw, dict):
        return None

    versions = []
    for v in raw.get("versions", []):
        if isinstance(v, dict):
            versions.append(VersionInfo(
                version=str(v.get("version", "")),
                eol=str(v.get("eol", "")),
                status=str(v.get("status", "")),
            ))

    registry = None
    reg_raw = raw.get("package_registry")
    if isinstance(reg_raw, dict):
        registry = RegistryInfo(
            name=reg_raw.get("name", ""),
            api=reg_raw.get("api", ""),
            version_field=reg_raw.get("version_field", ""),
        )

    return LanguageMeta(
        language=raw.get("language", language),
        display_name=raw.get("display_name", language),
        file_extensions=raw.get("file_extensions", []),
        parser=raw.get("parser", ""),
        versions=versions,
        version_format=raw.get("version_format", "major.minor"),
        default_exclusions=raw.get("default_exclusions", []),
        import_styles=raw.get("import_styles", []),
        package_registry=registry,
    )


def load_all_language_metas(
    entries_dir: Path | None = None,
) -> dict[str, LanguageMeta]:
    """Load _meta.yml for all languages."""
    base = entries_dir or _ENTRIES_DIR
    metas: dict[str, LanguageMeta] = {}

    if not base.is_dir():
        return metas

    for lang_dir in sorted(base.iterdir()):
        if not lang_dir.is_dir():
            continue
        meta = load_language_meta(lang_dir.name, entries_dir)
        if meta:
            metas[lang_dir.name] = meta

    return metas


# ── Internal parsing ─────────────────────────────────────────────


def _parse_entry(raw: dict, language: str) -> FeatureEntry:
    """Parse a raw dict into a FeatureEntry."""
    from .schema import (
        AdditionalTest,
        BackportInfo,
        CustomCheck,
        Detection,
        DetectionRule,
        Direction,
        EdgeCase,
        EdgeCaseTest,
        ErrorType,
        ExclusionRule,
        FeatureEntry,
        Fix,
        FixStrategy,
        Severity,
        TestCase,
        Transform,
        Verification,
    )

    # Detection
    det_raw = raw.get("detection", {})
    detection = Detection(
        primary=_parse_detection_rule(det_raw.get("primary", {})),
        alternatives=[
            _parse_detection_rule(alt)
            for alt in det_raw.get("alternatives", [])
        ],
        exclude=[
            ExclusionRule(
                ast_type=exc.get("ast_type"),
                match=exc.get("match", {}),
                context=exc.get("context"),
                reason=exc.get("reason", ""),
            )
            for exc in det_raw.get("exclude", [])
        ],
    )

    # Fix
    fix = _parse_fix(raw.get("fix", {}))

    # Fix upgrade (optional)
    fix_upgrade = None
    if "fix_upgrade" in raw:
        fix_upgrade = _parse_fix(raw["fix_upgrade"])

    # Verification
    ver_raw = raw.get("verification", {})
    custom = None
    custom_raw = ver_raw.get("custom_check")
    if isinstance(custom_raw, dict):
        custom = CustomCheck(
            command=custom_raw.get("command", ""),
            description=custom_raw.get("description", ""),
            expected_exit_code=custom_raw.get("expected_exit_code", 0),
            timeout=custom_raw.get("timeout", 5),
        )
    verification = Verification(
        re_detect=ver_raw.get("re_detect", True),
        syntax_check=ver_raw.get("syntax_check", True),
        import_check=ver_raw.get("import_check", True),
        custom_check=custom,
    )

    # Edge cases
    edge_cases = []
    for ec_raw in raw.get("edge_cases", []):
        ec_test = None
        ec_test_raw = ec_raw.get("test")
        if isinstance(ec_test_raw, dict):
            ec_test = EdgeCaseTest(
                input=ec_test_raw.get("input", ""),
                before=ec_test_raw.get("before", ""),
                after=ec_test_raw.get("after", ""),
                expected_findings=ec_test_raw.get("expected_findings"),
                expected_severity=ec_test_raw.get("expected_severity"),
                notes=ec_test_raw.get("notes", ""),
            )
        edge_cases.append(EdgeCase(
            id=ec_raw.get("id", ""),
            category=ec_raw.get("category", ""),
            description=ec_raw.get("description", ""),
            handling=ec_raw.get("handling", ""),
            severity_override=ec_raw.get("severity_override"),
            detection_modifier=_parse_detection_rule(ec_raw["detection_modifier"])
            if "detection_modifier" in ec_raw else None,
            test=ec_test,
        ))

    # Test cases
    test_raw = raw.get("test", {})
    test = TestCase(
        before=test_raw.get("before", ""),
        after=test_raw.get("after", ""),
    )
    test_additional = [
        AdditionalTest(
            name=t.get("name", ""),
            before=t.get("before", ""),
            after=t.get("after", ""),
        )
        for t in test_raw.get("additional", [])
    ]

    # Direction
    direction_str = raw.get("direction", "downgrade")
    try:
        direction = Direction(direction_str)
    except ValueError:
        direction = Direction.DOWNGRADE

    # Severity
    severity_str = raw.get("severity", "error")
    try:
        severity = Severity(severity_str)
    except ValueError:
        severity = Severity.ERROR

    # Error type
    error_type_str = raw.get("error_type", "runtime_error")
    try:
        error_type = ErrorType(error_type_str)
    except ValueError:
        error_type = ErrorType.RUNTIME_ERROR

    return FeatureEntry(
        id=raw.get("id", ""),
        language=raw.get("language", language),
        feature_name=raw.get("feature_name", ""),
        introduced=str(raw.get("introduced", "")),
        removed=raw.get("removed"),
        deprecated=raw.get("deprecated"),
        category=raw.get("category", ""),
        description=raw.get("description") or "",
        direction=direction,
        severity=severity,
        error_type=error_type,
        error_subtype=raw.get("error_subtype", ""),
        tags=raw.get("tags", []),
        detection=detection,
        fix=fix,
        fix_upgrade=fix_upgrade,
        verification=verification,
        edge_cases=edge_cases,
        test=test,
        test_additional=test_additional,
    )


def _parse_detection_rule(raw: dict) -> DetectionRule:
    """Parse a raw dict into a DetectionRule."""
    from .schema import DetectionRule
    return DetectionRule(
        ast_type=raw.get("ast_type", ""),
        match=raw.get("match", {}),
        context=raw.get("context"),
    )


def _parse_fix(raw: dict) -> Fix:
    """Parse a raw dict into a Fix."""
    from .schema import BackportInfo, Fix, FixStrategy, Transform

    strategy_str = raw.get("strategy", "manual")
    try:
        strategy = FixStrategy(strategy_str)
    except ValueError:
        strategy = FixStrategy.MANUAL

    transforms = [
        _parse_transform(t)
        for t in raw.get("transforms", [])
    ]

    backport = None
    bp_raw = raw.get("backport")
    if isinstance(bp_raw, dict):
        backport = BackportInfo(
            package=bp_raw.get("package", ""),
            min_version=bp_raw.get("min_version", ""),
            max_version=bp_raw.get("max_version"),
            import_name=bp_raw.get("import_name", ""),
            import_as=bp_raw.get("import_as"),
            import_statement=bp_raw.get("import_statement"),
            install_command=bp_raw.get("install_command", ""),
            supports_versions=bp_raw.get("supports_versions", ""),
            maintained=bp_raw.get("maintained", True),
            notes=bp_raw.get("notes", ""),
        )

    alternative = None
    alt_raw = raw.get("alternative")
    if isinstance(alt_raw, dict):
        alternative = _parse_fix(alt_raw)

    return Fix(
        strategy=strategy,
        transforms=transforms,
        backport=backport,
        manual_instructions=raw.get("manual_instructions"),
        alternative=alternative,
    )


def _parse_transform(t: dict) -> Transform:
    """Parse a transform dict, capturing extra keys into replace.

    YAML transforms can have keys like import_statement, position
    at the top level (not inside find/replace). Merge them into replace
    so the fix engine can access them.
    """
    from .schema import Transform

    # Known top-level keys
    known_keys = {"type", "find", "replace", "scope", "condition"}
    extra = {k: v for k, v in t.items() if k not in known_keys}

    # Merge extras into replace
    replace = dict(t.get("replace", {}))
    replace.update(extra)

    return Transform(
        type=t.get("type", ""),
        find=t.get("find", {}),
        replace=replace,
        scope=t.get("scope"),
        condition=t.get("condition"),
    )
