"""Security scanning — secrets, sensitive files, gitignore analysis."""

from __future__ import annotations

import fnmatch
import logging
import re
from pathlib import Path

from src.core.services.security_common import (
    _SECRET_PATTERNS, _SKIP_DIRS, _SKIP_EXTENSIONS,
    _EXPECTED_SECRET_FILES, _should_scan, _has_nosec,
)

logger = logging.getLogger(__name__)

from src.core.services.audit_helpers import make_auditor

_audit = make_auditor("security")

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


def _sensitive_patterns() -> list[list]:
    """Sensitive file patterns — loaded from DataRegistry."""
    from src.core.data import get_registry
    return get_registry().sensitive_files


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

    for pattern, description in _sensitive_patterns():
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


def _gitignore_catalog() -> dict:
    """Gitignore patterns — loaded from DataRegistry."""
    from src.core.data import get_registry
    return get_registry().gitignore_patterns


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

    catalog = _gitignore_catalog()

    for pattern in catalog["universal"]:
        expected.append((pattern, "security", "Universal security pattern"))

    if stack_names:
        for stack in stack_names:
            base = stack.split("-")[0]  # python-flask → python
            patterns = catalog["stacks"].get(base, [])
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

    # Editor swap files section
    sections.append("# ── Editor ──────────────────────────────────────────────────────────")
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

        patterns = _gitignore_catalog()["stacks"].get(base)
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
