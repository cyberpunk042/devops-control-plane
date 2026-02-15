"""
L2 — Risk & issue aggregation (on-demand).

Collects findings from security, package, quality, testing, and
documentation ops into a unified risk register.  Classifies each
finding by severity and category, then computes an overall risk
posture score.

Public API:
    l2_risks(project_root)  → risk register + posture score
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from src.core.services.audit.models import wrap_result

logger = logging.getLogger(__name__)


# ── Cache-first data access ────────────────────────────────────
# l2_risks calls many ops functions (testing_status, scan_secrets,
# package_audit, etc.) that are already cached by the devops/audit
# tabs.  Reading from cache is instant (0ms) vs re-calling the ops
# (6-30s under contention).  Falls back to None on cache miss.

def _cached_or_compute(project_root: Path, key: str) -> dict | None:
    """Read cached card data if available, else return None.

    Unlike get_cached(), this does NOT compute — it only reads.
    Callers should fall back to live ops calls if this returns None.
    """
    try:
        from src.core.services.devops_cache import _load_cache
        cache = _load_cache(project_root)
        entry = cache.get(key)
        if entry and "data" in entry:
            return entry["data"]
    except Exception:
        pass
    return None


# ═══════════════════════════════════════════════════════════════════
#  Risk finding helpers
# ═══════════════════════════════════════════════════════════════════


def _make_finding(
    category: str,
    severity: str,
    title: str,
    detail: str,
    source: str,
    *,
    recommendation: str = "",
    files: list[dict] | None = None,
) -> dict:
    """Create a standardized risk finding.

    Args:
        files: Optional list of dicts with file-level detail.
               Each: {file, line?, pattern?, match_preview?}
    """
    finding = {
        "category": category,
        "severity": severity,
        "title": title,
        "detail": detail,
        "source": source,
        "recommendation": recommendation,
    }
    if files:
        finding["files"] = files
    return finding


# ═══════════════════════════════════════════════════════════════════
#  Security findings
# ═══════════════════════════════════════════════════════════════════


def _security_findings(project_root: Path) -> list[dict]:
    """Collect security-related risk findings."""
    findings = []

    try:
        from src.core.services.security_ops import (
            detect_sensitive_files,
            gitignore_analysis,
            scan_secrets,
        )

        # Secret scanning
        try:
            secrets = scan_secrets(project_root)
            if secrets.get("ok"):
                summary = secrets.get("summary", {})
                critical = summary.get("critical", 0)
                high = summary.get("high", 0)
                medium = summary.get("medium", 0)
                raw_findings = secrets.get("findings", [])

                # Build file detail list per severity
                def _files_by_sev(sev: str) -> list[dict]:
                    return [
                        {
                            "file": f.get("file", ""),
                            "line": f.get("line"),
                            "pattern": f.get("pattern", ""),
                            "match_preview": f.get("match_preview", ""),
                        }
                        for f in raw_findings
                        if f.get("severity") == sev
                    ]

                if critical > 0:
                    findings.append(_make_finding(
                        "security", "critical",
                        "Hardcoded secrets detected",
                        f"{critical} critical secret(s) found in source code",
                        "security_ops.scan_secrets",
                        recommendation="Remove secrets and rotate credentials immediately",
                        files=_files_by_sev("critical"),
                    ))
                if high > 0:
                    findings.append(_make_finding(
                        "security", "high",
                        "Sensitive credentials in code",
                        f"{high} high-severity credential(s) detected",
                        "security_ops.scan_secrets",
                        recommendation="Move credentials to .env or vault",
                        files=_files_by_sev("high"),
                    ))
                if medium > 0:
                    findings.append(_make_finding(
                        "security", "medium",
                        "Potential secrets in code",
                        f"{medium} medium-severity pattern(s) detected",
                        "security_ops.scan_secrets",
                        recommendation="Review flagged patterns and remove real credentials",
                        files=_files_by_sev("medium"),
                    ))
        except Exception as e:
            logger.debug("Secret scan failed: %s", e)

        # Sensitive files
        try:
            sensitive = detect_sensitive_files(project_root)
            count = sensitive.get("count", 0)
            if count > 0:
                unignored = [
                    f for f in sensitive.get("files", [])
                    if not f.get("gitignored")
                ]
                if unignored:
                    file_details = [
                        {"file": f.get("file", f.get("path", "")), "pattern": f.get("reason", "")}
                        for f in unignored
                    ]
                    findings.append(_make_finding(
                        "security", "high",
                        "Sensitive files not gitignored",
                        f"{len(unignored)} sensitive file(s) tracked in git",
                        "security_ops.detect_sensitive_files",
                        recommendation="Add these files to .gitignore",
                        files=file_details,
                    ))
        except Exception as e:
            logger.debug("Sensitive file detection failed: %s", e)

        # Gitignore coverage
        try:
            gi = gitignore_analysis(project_root)
            if not gi.get("exists"):
                findings.append(_make_finding(
                    "security", "high",
                    "No .gitignore file",
                    "Project has no .gitignore — all files may be tracked",
                    "security_ops.gitignore_analysis",
                    recommendation="Create a .gitignore for your project's stacks",
                ))
            else:
                missing = gi.get("missing_patterns", [])
                if len(missing) > 3:
                    findings.append(_make_finding(
                        "security", "medium",
                        "Incomplete .gitignore",
                        f"{len(missing)} recommended patterns missing from .gitignore",
                        "security_ops.gitignore_analysis",
                        recommendation="Add missing patterns to prevent accidental commits",
                    ))
        except Exception as e:
            logger.debug("Gitignore analysis failed: %s", e)

    except ImportError:
        logger.debug("security_ops not available")

    return findings


# ═══════════════════════════════════════════════════════════════════
#  Dependency findings
# ═══════════════════════════════════════════════════════════════════


def _dependency_findings(project_root: Path) -> list[dict]:
    """Collect dependency-related risk findings."""
    findings = []

    try:
        from src.core.services.package_ops import package_audit, package_outdated

        # Vulnerability audit
        try:
            audit = package_audit(project_root)
            if audit.get("ok"):
                vulns = audit.get("vulnerabilities", 0)
                if vulns > 0:
                    findings.append(_make_finding(
                        "dependencies", "high",
                        "Known vulnerabilities in dependencies",
                        f"{vulns} vulnerability/vulnerabilities found by {audit.get('manager', 'audit')}",
                        "package_ops.package_audit",
                        recommendation="Run package audit fix or update vulnerable packages",
                    ))
            elif "error" in audit and "not installed" not in str(audit.get("error", "")):
                findings.append(_make_finding(
                    "dependencies", "info",
                    "Dependency audit tool unavailable",
                    str(audit.get("error", "Audit command failed")),
                    "package_ops.package_audit",
                    recommendation="Install pip-audit or npm audit for vulnerability scanning",
                ))
        except Exception as e:
            logger.debug("Package audit failed: %s", e)

        # Outdated packages
        try:
            outdated = package_outdated(project_root)
            if outdated.get("ok"):
                pkgs = outdated.get("outdated", [])
                if len(pkgs) > 0:
                    # Include top 20 outdated packages as entries
                    # Mark as kind='package' so the UI renders them
                    # with package registry links, not file links
                    manager = outdated.get("manager", "pip")
                    pkg_files = [
                        {
                            "file": p.get("name", "?"),
                            "pattern": f"{p.get('current', '?')} → {p.get('latest', '?')}",
                            "kind": "package",
                            "manager": manager,
                        }
                        for p in pkgs[:20]
                    ]
                    sev = "medium" if len(pkgs) > 10 else "info"
                    title = "Many outdated packages" if len(pkgs) > 10 else "Some outdated packages"
                    findings.append(_make_finding(
                        "dependencies", sev,
                        title,
                        f"{len(pkgs)} packages have available updates",
                        "package_ops.package_outdated",
                        recommendation="Update dependencies to fix bugs and security issues. Run: pip install --upgrade <pkg>",
                        files=pkg_files,
                    ))
        except Exception as e:
            logger.debug("Package outdated check failed: %s", e)

    except ImportError:
        logger.debug("package_ops not available")

    return findings


# ═══════════════════════════════════════════════════════════════════
#  Documentation findings
# ═══════════════════════════════════════════════════════════════════


def _docs_findings(project_root: Path) -> list[dict]:
    """Collect documentation-related risk findings."""
    findings = []

    try:
        from src.core.services.docs_ops import check_links, docs_status

        try:
            status = docs_status(project_root)

            # No README
            readme = status.get("readme", {})
            if not readme.get("exists"):
                findings.append(_make_finding(
                    "documentation", "medium",
                    "No README file",
                    "Project has no README.md — users won't know how to use it",
                    "docs_ops.docs_status",
                    recommendation="Create a README with project overview, setup, and usage",
                ))

            # No CHANGELOG
            changelog = status.get("changelog", {})
            if not changelog.get("exists"):
                findings.append(_make_finding(
                    "documentation", "info",
                    "No CHANGELOG",
                    "No CHANGELOG file found — change tracking is implicit",
                    "docs_ops.docs_status",
                    recommendation="Add a CHANGELOG.md to document releases and changes",
                ))

            # No LICENSE
            license_info = status.get("license", {})
            if not license_info.get("exists"):
                findings.append(_make_finding(
                    "documentation", "medium",
                    "No LICENSE file",
                    "No open-source license detected",
                    "docs_ops.docs_status",
                    recommendation="Add a LICENSE to clarify usage terms",
                ))

        except Exception as e:
            logger.debug("Docs status failed: %s", e)

        # Broken links
        try:
            links = check_links(project_root)
            broken = links.get("broken", [])
            if len(broken) > 0:
                findings.append(_make_finding(
                    "documentation", "info",
                    "Broken internal links",
                    f"{len(broken)} broken link(s) in documentation",
                    "docs_ops.check_links",
                    recommendation="Fix or remove broken documentation links",
                ))
        except Exception as e:
            logger.debug("Link check failed: %s", e)

    except ImportError:
        logger.debug("docs_ops not available")

    return findings


# ═══════════════════════════════════════════════════════════════════
#  Testing findings
# ═══════════════════════════════════════════════════════════════════


def _testing_findings(project_root: Path) -> list[dict]:
    """Collect testing-related risk findings.

    Reads from the devops cache if available (instant), otherwise
    falls back to calling testing_ops directly.
    """
    findings = []

    try:
        status = _cached_or_compute(project_root, "testing")
        if status is None:
            from src.core.services.testing_ops import testing_status
            status = testing_status(project_root)

        if not status.get("has_tests"):
            findings.append(_make_finding(
                "testing", "high",
                "No tests detected",
                "No test framework or test files found",
                "testing_ops.testing_status",
                recommendation="Add a test directory and write tests for critical modules",
            ))
        else:
            stats = status.get("stats", {})
            ratio = stats.get("test_ratio", 0)
            test_files = stats.get("test_files", 0)
            src_files = stats.get("source_files", 0)
            if ratio < 0.1 and src_files > 10:
                frameworks = status.get("frameworks", [])
                fw_str = ", ".join(frameworks) if frameworks else "unknown"

                # Include key ratio data as file-level detail
                test_detail = [
                    {"file": f"Test files: {test_files}", "pattern": f"Source files: {src_files}"},
                    {"file": f"Ratio: {ratio:.1%}", "pattern": f"Framework: {fw_str}"},
                ]

                # List test directories found
                test_dirs = status.get("test_dirs", [])
                for td in test_dirs[:5]:
                    test_detail.append({"file": td, "pattern": "test directory"})

                findings.append(_make_finding(
                    "testing", "medium",
                    "Low test coverage",
                    f"Test-to-source ratio: {ratio:.1%} ({test_files} test files vs {src_files} source files). Framework: {fw_str}",
                    "testing_ops.testing_status",
                    recommendation=f"Add tests for the largest source modules. Run: pytest --co to see existing test inventory",
                    files=test_detail,
                ))

    except Exception as e:
        logger.debug("Testing findings failed: %s", e)

    return findings


# ═══════════════════════════════════════════════════════════════════
#  Infrastructure findings
# ═══════════════════════════════════════════════════════════════════


def _infra_findings(project_root: Path) -> list[dict]:
    """Collect infrastructure-related risk findings."""
    findings = []

    try:
        from src.core.services.env_ops import env_status, env_validate

        try:
            status = env_status(project_root)
            if status.get("has_env") and not status.get("has_example"):
                findings.append(_make_finding(
                    "infrastructure", "medium",
                    "No .env.example file",
                    ".env exists but no .env.example — onboarding is harder",
                    "env_ops.env_status",
                    recommendation="Create .env.example with redacted values for team setup",
                ))
        except Exception as e:
            logger.debug("Env status failed: %s", e)

        try:
            validation = env_validate(project_root)
            if validation.get("ok") and not validation.get("valid"):
                issues = validation.get("issues", [])
                if issues:
                    findings.append(_make_finding(
                        "infrastructure", "info",
                        "Environment file issues",
                        f"{len(issues)} issue(s) in .env file",
                        "env_ops.env_validate",
                        recommendation="Review and fix .env file issues",
                    ))
        except Exception as e:
            logger.debug("Env validation failed: %s", e)

    except ImportError:
        logger.debug("env_ops not available")

    return findings


# ═══════════════════════════════════════════════════════════════════
#  Action item generation
# ═══════════════════════════════════════════════════════════════════


def _generate_action_items(findings: list[dict]) -> list[dict]:
    """Convert findings into prioritized action items.

    Groups by category, assigns priority based on severity,
    and generates concise action items.
    """
    severity_priority = {"critical": 1, "high": 2, "medium": 3, "info": 4}

    actions = []
    for f in findings:
        if not f.get("recommendation"):
            continue
        actions.append({
            "priority": severity_priority.get(f["severity"], 5),
            "severity": f["severity"],
            "category": f["category"],
            "action": f["recommendation"],
            "context": f["title"],
        })

    actions.sort(key=lambda a: a["priority"])
    return actions


# ═══════════════════════════════════════════════════════════════════
#  Risk posture score
# ═══════════════════════════════════════════════════════════════════


def _risk_posture_score(findings: list[dict]) -> dict:
    """Compute a risk posture score (0-10, higher = lower risk).

    Deductions:
        Critical: -2.0 each (capped at -6.0)
        High:     -1.0 each (capped at -4.0)
        Medium:   -0.3 each (capped at -2.0)
        Info:     -0.1 each (capped at -1.0)
    """
    score = 10.0
    deductions = {"critical": 0.0, "high": 0.0, "medium": 0.0, "info": 0.0}

    for f in findings:
        sev = f.get("severity", "info")
        if sev == "critical":
            deductions["critical"] = min(deductions["critical"] + 2.0, 6.0)
        elif sev == "high":
            deductions["high"] = min(deductions["high"] + 1.0, 4.0)
        elif sev == "medium":
            deductions["medium"] = min(deductions["medium"] + 0.3, 2.0)
        elif sev == "info":
            deductions["info"] = min(deductions["info"] + 0.1, 1.0)

    total_deduction = sum(deductions.values())
    final = max(0.0, score - total_deduction)

    # Grade mapping
    if final >= 9.0:
        grade = "A"
    elif final >= 7.0:
        grade = "B"
    elif final >= 5.0:
        grade = "C"
    elif final >= 3.0:
        grade = "D"
    else:
        grade = "F"

    return {
        "score": round(final, 1),
        "grade": grade,
        "deductions": {k: round(v, 1) for k, v in deductions.items()},
    }


# ═══════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════


def l2_risks(project_root: Path) -> dict:
    """L2: Risk & issue aggregation.

    On-demand — calls multiple ops services to build a unified
    risk register.  Typically takes 2-8s.

    Returns:
        {
            "_meta": AuditMeta,
            "findings": [{category, severity, title, detail, source, recommendation}, ...],
            "summary": {total, critical, high, medium, info},
            "posture": {score, grade, deductions},
            "action_items": [{priority, severity, category, action, context}, ...],
            "by_category": {security: int, dependencies: int, ...},
        }
    """
    started = time.time()

    # Collect findings from all sources
    findings = []
    findings.extend(_security_findings(project_root))
    findings.extend(_dependency_findings(project_root))
    findings.extend(_docs_findings(project_root))
    findings.extend(_testing_findings(project_root))
    findings.extend(_infra_findings(project_root))

    # Sort by severity
    severity_order = {"critical": 0, "high": 1, "medium": 2, "info": 3}
    findings.sort(key=lambda f: severity_order.get(f["severity"], 4))

    # Summary counts
    summary = {"total": len(findings), "critical": 0, "high": 0, "medium": 0, "info": 0}
    for f in findings:
        sev = f.get("severity", "info")
        summary[sev] = summary.get(sev, 0) + 1

    # By category
    by_category: dict[str, int] = {}
    for f in findings:
        cat = f.get("category", "other")
        by_category[cat] = by_category.get(cat, 0) + 1

    # Posture score
    posture = _risk_posture_score(findings)

    # Action items
    actions = _generate_action_items(findings)

    data = {
        "findings": findings,
        "summary": summary,
        "posture": posture,
        "action_items": actions,
        "by_category": by_category,
    }
    return wrap_result(data, "L2", "risks", started)
