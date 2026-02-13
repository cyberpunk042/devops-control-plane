"""
Security operations — channel-independent service.

Provides secret scanning (hardcoded secrets in source), .gitignore
analysis and generation, sensitive file detection, and a unified
security posture score.

Complements existing:
- secrets_ops.py (GitHub secrets management)
- vault.py (file encryption at rest)
- package_ops.package_audit() (dependency vulnerabilities)
- env_ops.env_validate() (env file validation)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  Secret scanning patterns
# ═══════════════════════════════════════════════════════════════════

# Each pattern: (name, regex, severity, description)
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str], str, str]] = [
    # AWS
    (
        "AWS Access Key",
        re.compile(r"AKIA[0-9A-Z]{16}"),
        "critical",
        "AWS IAM access key ID",
    ),
    (
        "AWS Secret Key",
        re.compile(r"(?i)aws[_\-]?secret[_\-]?access[_\-]?key\s*[=:]\s*['\"]?([A-Za-z0-9/+=]{40})"),
        "critical",
        "AWS secret access key",
    ),
    # GitHub
    (
        "GitHub Token (classic)",
        re.compile(r"ghp_[A-Za-z0-9]{36}"),
        "critical",
        "GitHub personal access token (classic)",
    ),
    (
        "GitHub Token (fine-grained)",
        re.compile(r"github_pat_[A-Za-z0-9_]{82}"),
        "critical",
        "GitHub fine-grained personal access token",
    ),
    (
        "GitHub OAuth",
        re.compile(r"gho_[A-Za-z0-9]{36}"),
        "high",
        "GitHub OAuth access token",
    ),
    (
        "GitHub App Token",
        re.compile(r"ghu_[A-Za-z0-9]{36}|ghs_[A-Za-z0-9]{36}"),
        "high",
        "GitHub App installation or server token",
    ),
    # Google
    (
        "Google API Key",
        re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
        "high",
        "Google API key",
    ),
    (
        "Google OAuth Client Secret",
        re.compile(r"GOCSPX-[A-Za-z0-9\-_]{28}"),
        "critical",
        "Google OAuth client secret",
    ),
    # Slack
    (
        "Slack Bot Token",
        re.compile(r"xoxb-[0-9]{10,13}-[0-9]{10,13}-[a-zA-Z0-9]{24}"),
        "high",
        "Slack bot token",
    ),
    (
        "Slack Webhook",
        re.compile(r"https://hooks\.slack\.com/services/T[A-Z0-9]{8,}/B[A-Z0-9]{8,}/[a-zA-Z0-9]{24}"),
        "high",
        "Slack incoming webhook URL",
    ),
    # Stripe
    (
        "Stripe Secret Key",
        re.compile(r"sk_live_[0-9a-zA-Z]{24}"),
        "critical",
        "Stripe live secret key",
    ),
    (
        "Stripe Publishable Key",
        re.compile(r"pk_live_[0-9a-zA-Z]{24}"),
        "medium",
        "Stripe live publishable key",
    ),
    # Generic high-entropy
    (
        "Private Key Header",
        re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
        "critical",
        "Private key file content embedded in code",
    ),
    (
        "Hex-encoded Secret",
        re.compile(r"""(?i)(?:secret|token|password|key|passwd|api[_-]?key)\s*[=:]\s*['"]?[0-9a-f]{32,}['"]?"""),
        "high",
        "Potential hardcoded hex secret",
    ),
    (
        "Base64-encoded Secret",
        re.compile(r"""(?i)(?:secret|token|password|key|passwd)\s*[=:]\s*['"]?[A-Za-z0-9+/]{40,}={0,2}['"]?"""),
        "medium",
        "Potential hardcoded base64 secret",
    ),
    # Connection strings
    (
        "Database URL",
        re.compile(r"""(?:postgres|mysql|mongodb|redis|amqp)://[^\s'"]{10,}"""),
        "high",
        "Database connection string with potential credentials",
    ),
    # JWT
    (
        "JWT Token",
        re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
        "high",
        "Hardcoded JWT token",
    ),
    # Generic password assignment
    (
        "Password Assignment",
        re.compile(r"""(?i)(?:password|passwd|pwd)\s*[=:]\s*['"][^'"]{6,}['"]"""),
        "medium",
        "Hardcoded password value",
    ),
]


# Files / dirs to skip during scanning
_SKIP_DIRS = frozenset({
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".mypy_cache", ".ruff_cache", ".pytest_cache", ".tox",
    "dist", "build", ".eggs", ".terraform", ".pages",
    "htmlcov", ".backup", "state",
})

_SKIP_EXTENSIONS = frozenset({
    ".pyc", ".pyo", ".so", ".dll", ".exe", ".bin",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".mp4", ".mp3", ".wav", ".avi", ".mov",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z",
    ".woff", ".woff2", ".ttf", ".eot",
    ".pdf", ".doc", ".docx",
    ".lock",  # lock files often contain hashes that look like secrets
    ".vault",  # our own encrypted files
})

# Files that are expected to contain secrets (don't flag them)
_EXPECTED_SECRET_FILES = frozenset({
    ".env", ".env.example", ".env.sample", ".env.template",
    ".env.local", ".env.development", ".env.staging", ".env.production",
    ".env.test",
})


def _should_scan(path: Path, project_root: Path) -> bool:
    """Whether a file should be scanned for secrets."""
    rel = path.relative_to(project_root)

    # Skip directories
    for part in rel.parts:
        if part in _SKIP_DIRS:
            return False

    # Skip by extension
    if path.suffix.lower() in _SKIP_EXTENSIONS:
        return False

    # Skip expected secret files
    if rel.name in _EXPECTED_SECRET_FILES:
        return False

    # Skip binary-looking files
    if not path.is_file():
        return False

    return True


# Regex to detect inline nosec annotations:
#   some_code = "val"  # nosec
#   some_code = "val"  // nosec
#   some_code = "val"  # nosec: reason here
_NOSEC_RE = re.compile(r"(?:#|//)\s*nosec\b", re.IGNORECASE)

# For stripping nosec annotations from a line (undismiss)
_NOSEC_STRIP_RE = re.compile(r"\s*(?:#|//)\s*nosec\b.*$", re.IGNORECASE)


def _has_nosec(line: str) -> bool:
    """Check if a line has an inline nosec suppression comment."""
    return bool(_NOSEC_RE.search(line))


def dismiss_finding(
    project_root: Path, file: str, line: int, comment: str = "",
) -> dict:
    """Dismiss a finding by adding ``# nosec`` to the source line.

    This is the standard inline-suppression mechanism: the comment
    tells the scanner to skip this line.  The optional *comment* is
    preserved as part of the annotation so the reason is visible in
    the source code itself.

    Returns ``{"ok": True, ...}`` on success.
    """
    target = project_root / file
    if not target.is_file():
        return {"ok": False, "error": f"File not found: {file}"}

    try:
        content = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {"ok": False, "error": str(exc)}

    lines = content.splitlines(True)  # keep line endings
    if line < 1 or line > len(lines):
        return {"ok": False, "error": f"Line {line} out of range"}

    idx = line - 1
    current = lines[idx].rstrip("\n").rstrip("\r")

    # Already suppressed?
    if _has_nosec(current):
        return {"ok": True, "file": file, "line": line, "already": True}

    # Choose comment style by file extension
    ext = target.suffix.lower()
    if ext in (
        ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs",
        ".c", ".cpp", ".h", ".java", ".go", ".rs", ".cs",
    ):
        tag = f"// nosec: {comment}" if comment else "// nosec"
    else:
        tag = f"# nosec: {comment}" if comment else "# nosec"

    lines[idx] = current + "  " + tag + "\n"
    target.write_text("".join(lines), encoding="utf-8")

    logger.info("Dismissed finding in %s:%d — %s", file, line, comment or "(no reason)")
    return {"ok": True, "file": file, "line": line}


def undismiss_finding(project_root: Path, file: str, line: int) -> dict:
    """Remove an inline ``# nosec`` annotation, restoring the finding."""
    target = project_root / file
    if not target.is_file():
        return {"ok": False, "error": f"File not found: {file}"}

    try:
        content = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {"ok": False, "error": str(exc)}

    lines = content.splitlines(True)
    if line < 1 or line > len(lines):
        return {"ok": False, "error": f"Line {line} out of range"}

    idx = line - 1
    current = lines[idx]

    if not _has_nosec(current):
        return {"ok": True, "file": file, "line": line, "already": True}

    cleaned = _NOSEC_STRIP_RE.sub("", current)
    if not cleaned.endswith("\n"):
        cleaned += "\n"

    lines[idx] = cleaned
    target.write_text("".join(lines), encoding="utf-8")

    logger.info("Undismissed finding in %s:%d", file, line)
    return {"ok": True, "file": file, "line": line}


# ═══════════════════════════════════════════════════════════════════
#  Detect: Secret scanning
# ═══════════════════════════════════════════════════════════════════


def scan_secrets(
    project_root: Path,
    *,
    max_files: int = 500,
    max_file_size: int = 512_000,  # 512KB
) -> dict:
    """Scan source code for hardcoded secrets.

    Returns:
        {
            "ok": True,
            "findings": [{
                file, line, pattern, severity, description, match_preview
            }, ...],
            "summary": {total, critical, high, medium},
            "files_scanned": int,
        }
    """
    findings: list[dict] = []
    files_scanned = 0
    suppressed = 0
    severity_counts = {"critical": 0, "high": 0, "medium": 0}

    for path in _iter_files(project_root, max_files):
        if not _should_scan(path, project_root):
            continue

        try:
            size = path.stat().st_size
            if size > max_file_size or size == 0:
                continue

            content = path.read_text(encoding="utf-8", errors="ignore")
            files_scanned += 1
        except (OSError, UnicodeDecodeError):
            continue

        rel_path = str(path.relative_to(project_root))

        for line_num, line in enumerate(content.splitlines(), 1):
            # Skip comments
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("*"):
                continue

            # Inline false-positive suppression: # nosec or // nosec
            if _has_nosec(stripped):
                for name, pattern, severity, description in _SECRET_PATTERNS:
                    if pattern.search(line):
                        suppressed += 1
                        break
                continue

            for name, pattern, severity, description in _SECRET_PATTERNS:
                match = pattern.search(line)
                if match:
                    # Redact most of the match for safety
                    raw = match.group(0)
                    preview = raw[:8] + "****" + raw[-4:] if len(raw) > 12 else "****"

                    findings.append({
                        "file": rel_path,
                        "line": line_num,
                        "pattern": name,
                        "severity": severity,
                        "description": description,
                        "match_preview": preview,
                    })
                    severity_counts[severity] = severity_counts.get(severity, 0) + 1
                    break  # One finding per line

    return {
        "ok": True,
        "findings": findings,
        "summary": {
            "total": len(findings),
            "suppressed": suppressed,
            **severity_counts,
        },
        "files_scanned": files_scanned,
    }


def _iter_files(root: Path, max_count: int) -> list[Path]:
    """Iterate files under root, respecting max count."""
    result: list[Path] = []
    try:
        for path in root.rglob("*"):
            if path.is_file():
                result.append(path)
                if len(result) >= max_count:
                    break
    except PermissionError:
        pass
    return result


# ═══════════════════════════════════════════════════════════════════
#  Detect: Sensitive file detection
# ═══════════════════════════════════════════════════════════════════


_SENSITIVE_PATTERNS = [
    ("*.pem", "PEM certificate/key file"),
    ("*.key", "Private key file"),
    ("*.p12", "PKCS12 keystore"),
    ("*.pfx", "PKCS12 keystore"),
    ("*.jks", "Java keystore"),
    ("*.keystore", "Keystore file"),
    ("id_rsa", "SSH private key"),
    ("id_ed25519", "SSH private key"),
    ("id_dsa", "SSH private key"),
    ("id_ecdsa", "SSH private key"),
    (".htpasswd", "HTTP auth password file"),
    (".netrc", "Network credentials file"),
    (".npmrc", "npm config (may contain tokens)"),
    (".pypirc", "PyPI credentials"),
    ("credentials.json", "Service account credentials"),
    ("service-account*.json", "GCP service account"),
]


def detect_sensitive_files(project_root: Path) -> dict:
    """Find sensitive files that might be accidentally tracked.

    Returns:
        {
            "files": [{path, pattern, description, gitignored}, ...],
            "count": int,
        }
    """
    found: list[dict] = []

    # Load .gitignore patterns (simplified check)
    gitignore_path = project_root / ".gitignore"
    gitignore_content = ""
    if gitignore_path.is_file():
        try:
            gitignore_content = gitignore_path.read_text(encoding="utf-8")
        except OSError:
            pass

    for pattern, description in _SENSITIVE_PATTERNS:
        if "*" in pattern:
            matches = list(project_root.rglob(pattern))
        else:
            matches = list(project_root.rglob(pattern))

        for match in matches:
            rel = str(match.relative_to(project_root))

            # Skip files in ignored directories
            skip = False
            for part in match.relative_to(project_root).parts:
                if part in _SKIP_DIRS:
                    skip = True
                    break
            if skip:
                continue

            # Simple gitignore check (not fully spec-compliant, but practical)
            gitignored = _is_gitignored(rel, pattern, gitignore_content)

            found.append({
                "path": rel,
                "pattern": pattern,
                "description": description,
                "gitignored": gitignored,
            })

    return {
        "files": found,
        "count": len(found),
        "unprotected": sum(1 for f in found if not f["gitignored"]),
    }


def _is_gitignored(rel_path: str, pattern: str, gitignore_content: str) -> bool:
    """Simple check if a file matches any .gitignore rule."""
    name = rel_path.rsplit("/", 1)[-1] if "/" in rel_path else rel_path

    for line in gitignore_content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Direct name match
        if line == name:
            return True
        # Extension match (e.g. *.pem)
        if line.startswith("*."):
            ext = line[1:]  # .pem
            if name.endswith(ext):
                return True
        # Path match
        if line.rstrip("/") in rel_path:
            return True

    return False


# ═══════════════════════════════════════════════════════════════════
#  Observe: Gitignore analysis
# ═══════════════════════════════════════════════════════════════════


_STACK_GITIGNORE_PATTERNS: dict[str, list[str]] = {
    "python": [
        "__pycache__/", "*.py[cod]", "*$py.class", "*.so",
        "*.egg-info/", "dist/", "build/", "*.egg",
        ".venv/", "venv/", ".pytest_cache/", ".mypy_cache/",
        ".ruff_cache/", ".coverage", "htmlcov/",
    ],
    "node": [
        "node_modules/", "dist/", "build/", ".next/",
        "*.tsbuildinfo", ".npm/", ".yarn/",
    ],
    "typescript": [
        "node_modules/", "dist/", "build/", ".next/",
        "*.tsbuildinfo", "*.js.map",
    ],
    "go": [
        "*.exe", "*.exe~", "*.dll", "*.so", "*.dylib",
        "*.test", "*.out", "vendor/",
    ],
    "rust": [
        "target/", "Cargo.lock",  # lock in libraries (not apps)
    ],
    "java": [
        "*.class", "*.jar", "*.war", "*.ear",
        "target/", "build/", ".gradle/", "*.iml",
    ],
    "dotnet": [
        "bin/", "obj/", "*.user", "*.suo",
        "packages/", ".vs/",
    ],
    "ruby": [
        "*.gem", ".bundle/", "vendor/bundle/",
    ],
    "elixir": [
        "_build/", "deps/", ".fetch", "*.ez",
    ],
}

_UNIVERSAL_PATTERNS = [
    ".env", ".env.*", "*.pem", "*.key",
    ".DS_Store", "Thumbs.db",
    ".vscode/", ".idea/", "*.swp", "*.swo",
]


def gitignore_analysis(project_root: Path, *, stack_names: list[str] | None = None) -> dict:
    """Analyze .gitignore completeness for detected stacks.

    Returns:
        {
            "exists": bool,
            "current_patterns": int,
            "missing_patterns": [{pattern, category, reason}, ...],
            "coverage": float (0-1),
        }
    """
    gitignore_path = project_root / ".gitignore"

    if not gitignore_path.is_file():
        return {
            "exists": False,
            "current_patterns": 0,
            "missing_patterns": [],
            "coverage": 0.0,
        }

    try:
        content = gitignore_path.read_text(encoding="utf-8")
    except OSError:
        return {"exists": False, "current_patterns": 0, "missing_patterns": [], "coverage": 0.0}

    current_lines = {
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.strip().startswith("#")
    }

    # Build expected patterns
    expected: list[tuple[str, str, str]] = []  # (pattern, category, reason)

    for pattern in _UNIVERSAL_PATTERNS:
        expected.append((pattern, "security", "Universal security pattern"))

    if stack_names:
        for stack in stack_names:
            base = stack.split("-")[0]  # python-flask → python
            patterns = _STACK_GITIGNORE_PATTERNS.get(base, [])
            for p in patterns:
                expected.append((p, base, f"Required for {base} projects"))

    # Check which are missing
    missing: list[dict] = []
    covered = 0
    for pattern, category, reason in expected:
        # Check if pattern or close variant exists
        if pattern in current_lines:
            covered += 1
        elif pattern.rstrip("/") in current_lines:
            covered += 1
        elif any(pattern.rstrip("/") in cl for cl in current_lines):
            covered += 1
        else:
            missing.append({"pattern": pattern, "category": category, "reason": reason})

    total = len(expected) if expected else 1
    coverage = covered / total

    return {
        "exists": True,
        "current_patterns": len(current_lines),
        "missing_patterns": missing,
        "missing_count": len(missing),
        "coverage": round(coverage, 2),
    }


# ═══════════════════════════════════════════════════════════════════
#  Facilitate: Gitignore generation
# ═══════════════════════════════════════════════════════════════════


def generate_gitignore(
    project_root: Path,
    stack_names: list[str],
) -> dict:
    """Generate a comprehensive .gitignore from detected stacks.

    Returns:
        {"ok": True, "file": {path, content, ...}}
    """
    from src.core.models.template import GeneratedFile

    sections: list[str] = []

    # Security section
    sections.append("# ── Security ─────────────────────────────────────────────────────────")
    sections.append(".env")
    sections.append(".env.*")
    sections.append("!.env.example")
    sections.append("!.env.sample")
    sections.append("*.pem")
    sections.append("*.key")
    sections.append("*.p12")
    sections.append("")

    # OS section
    sections.append("# ── OS ───────────────────────────────────────────────────────────────")
    sections.append(".DS_Store")
    sections.append("Thumbs.db")
    sections.append("")

    # IDE section
    sections.append("# ── IDE ──────────────────────────────────────────────────────────────")
    sections.append(".vscode/")
    sections.append(".idea/")
    sections.append("*.swp")
    sections.append("*.swo")
    sections.append("*~")
    sections.append("")

    # Stack sections
    seen_bases: set[str] = set()
    for stack in stack_names:
        base = stack.split("-")[0]
        if base in seen_bases:
            continue
        seen_bases.add(base)

        patterns = _STACK_GITIGNORE_PATTERNS.get(base)
        if not patterns:
            continue

        sections.append(f"# ── {base.title()} {'─' * (60 - len(base))}")
        for p in patterns:
            sections.append(p)
        sections.append("")

    content = "\n".join(sections) + "\n"

    file_data = GeneratedFile(
        path=".gitignore",
        content=content,
        overwrite=False,
        reason=f"Generated .gitignore for stacks: {', '.join(stack_names)}",
    )

    return {"ok": True, "file": file_data.model_dump()}


# ═══════════════════════════════════════════════════════════════════
#  Observe: Security posture
# ═══════════════════════════════════════════════════════════════════


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
