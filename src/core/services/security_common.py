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
