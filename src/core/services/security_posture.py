"""Security posture — unified security scoring and grading."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def security_posture(project_root: Path) -> dict:
    """Compute unified security posture score.

    Aggregates:
    - Secret scanning results
    - Sensitive file detection
    - Gitignore coverage
    - Vault status
    - Dependency audit status

    Returns:
        {
            "score": float (0-100),
            "grade": str,
            "checks": [
                {name, passed, score, details, recommendations},
                ...
            ],
        }
    """
    checks: list[dict] = []
    total_weight = 0
    total_score = 0.0

    # 1. Secret scanning (weight: 30)
    weight = 30
    total_weight += weight
    try:
        scan = scan_secrets(project_root)
        critical = scan["summary"].get("critical", 0)
        high = scan["summary"].get("high", 0)
        total_findings = scan["summary"].get("total", 0)

        if total_findings == 0:
            score = 1.0
            details = f"No secrets found in {scan['files_scanned']} files"
        elif critical > 0:
            score = 0.0
            details = f"{critical} critical secret(s) found!"
        elif high > 0:
            score = 0.3
            details = f"{high} high-severity finding(s)"
        else:
            score = 0.6
            details = f"{total_findings} medium finding(s)"

        recs = []
        if total_findings > 0:
            recs.append("Run: controlplane security scan (for details)")
            recs.append("Move secrets to .env or vault")

        checks.append({
            "name": "Secret scanning",
            "passed": total_findings == 0,
            "score": score,
            "weight": weight,
            "details": details,
            "recommendations": recs,
        })
        total_score += score * weight

    except Exception as e:
        checks.append({
            "name": "Secret scanning",
            "passed": False,
            "score": 0,
            "weight": weight,
            "details": f"Error: {e}",
            "recommendations": [],
        })

    # 2. Sensitive files (weight: 15)
    weight = 15
    total_weight += weight
    try:
        sens = detect_sensitive_files(project_root)
        unprotected = sens.get("unprotected", 0)

        if sens["count"] == 0:
            score = 1.0
            details = "No sensitive files detected"
        elif unprotected == 0:
            score = 0.9
            details = f"{sens['count']} sensitive file(s), all gitignored"
        else:
            score = max(0, 1.0 - (unprotected * 0.3))
            details = f"{unprotected} sensitive file(s) NOT gitignored!"

        recs = []
        if unprotected > 0:
            recs.append("Add sensitive files to .gitignore")
            recs.append("Run: controlplane security files (for details)")

        checks.append({
            "name": "Sensitive files",
            "passed": unprotected == 0,
            "score": score,
            "weight": weight,
            "details": details,
            "recommendations": recs,
        })
        total_score += score * weight

    except Exception as e:
        checks.append({
            "name": "Sensitive files",
            "passed": False,
            "score": 0,
            "weight": weight,
            "details": f"Error: {e}",
            "recommendations": [],
        })

    # 3. Gitignore coverage (weight: 20)
    weight = 20
    total_weight += weight
    try:
        # Auto-detect stacks
        stack_names: list[str] = []
        try:
            from src.core.config.loader import load_project
            from src.core.config.stack_loader import discover_stacks
            from src.core.services.detection import detect_modules

            project = load_project(project_root / "project.yml")
            stacks = discover_stacks(project_root / "stacks")
            detection = detect_modules(project, project_root, stacks)
            stack_names = list({m.effective_stack for m in detection.modules if m.effective_stack})
        except Exception:
            pass

        gi = gitignore_analysis(project_root, stack_names=stack_names)

        if not gi["exists"]:
            score = 0.0
            details = "No .gitignore file!"
        else:
            score = gi["coverage"]
            missing = gi.get("missing_count", 0)
            details = f"Coverage: {int(score * 100)}% ({missing} pattern(s) missing)"

        recs = []
        if not gi["exists"]:
            recs.append("Generate .gitignore: controlplane security generate gitignore")
        elif gi.get("missing_count", 0) > 0:
            recs.append("Update .gitignore with missing patterns")

        checks.append({
            "name": "Gitignore coverage",
            "passed": score >= 0.9,
            "score": score,
            "weight": weight,
            "details": details,
            "recommendations": recs,
        })
        total_score += score * weight

    except Exception as e:
        checks.append({
            "name": "Gitignore coverage",
            "passed": False,
            "score": 0,
            "weight": weight,
            "details": f"Error: {e}",
            "recommendations": [],
        })

    # 4. Vault status (weight: 20)
    weight = 20
    total_weight += weight
    try:
        from src.core.services.vault import vault_status

        env_path = project_root / ".env"
        if env_path.is_file():
            vs = vault_status(env_path)
            if vs.get("locked"):
                score = 1.0
                details = "Secrets vault is locked (encrypted)"
            elif vs.get("vault_exists"):
                score = 0.5
                details = "Vault exists but currently unlocked"
            else:
                score = 0.3
                details = ".env exists without vault protection"

            recs = []
            if not vs.get("vault_exists"):
                recs.append("Lock vault: controlplane vault lock")

            checks.append({
                "name": "Vault protection",
                "passed": score >= 0.5,
                "score": score,
                "weight": weight,
                "details": details,
                "recommendations": recs,
            })
        else:
            score = 0.8  # No .env = no secrets to protect
            checks.append({
                "name": "Vault protection",
                "passed": True,
                "score": score,
                "weight": weight,
                "details": "No .env file to protect",
                "recommendations": [],
            })

        total_score += score * weight

    except Exception as e:
        checks.append({
            "name": "Vault protection",
            "passed": False,
            "score": 0,
            "weight": weight,
            "details": f"Error: {e}",
            "recommendations": [],
        })

    # 5. Dependency audit (weight: 15)
    weight = 15
    total_weight += weight
    try:
        from src.core.services.package_ops import package_audit

        result = package_audit(project_root)

        if "error" in result:
            score = 0.5
            details = f"Audit unavailable: {result['error']}"
            recs = ["Install audit tool (e.g. pip install pip-audit)"]
        elif not result.get("available"):
            score = 0.5
            details = "Audit tool not installed"
            recs = [result.get("output", "Install audit tool")]
        else:
            vulns = result.get("vulnerabilities", 0)
            if vulns == 0:
                score = 1.0
                details = "No known vulnerabilities"
                recs = []
            else:
                score = max(0, 1.0 - (vulns * 0.15))
                details = f"{vulns} vulnerability(ies) found!"
                recs = ["Run: controlplane packages audit"]

        checks.append({
            "name": "Dependency audit",
            "passed": score >= 0.8,
            "score": score,
            "weight": weight,
            "details": details,
            "recommendations": recs,
        })
        total_score += score * weight

    except Exception as e:
        checks.append({
            "name": "Dependency audit",
            "passed": False,
            "score": 0,
            "weight": weight,
            "details": f"Error: {e}",
            "recommendations": [],
        })

    # Compute final score
    final_score = round(total_score / total_weight * 100, 1) if total_weight > 0 else 0

    if final_score >= 90:
        grade = "A"
    elif final_score >= 75:
        grade = "B"
    elif final_score >= 60:
        grade = "C"
    elif final_score >= 40:
        grade = "D"
    else:
        grade = "F"

    return {
        "score": final_score,
        "grade": grade,
        "checks": checks,
        "recommendations": [
            rec
            for check in checks
            for rec in check.get("recommendations", [])
        ][:10],
    }
